#!/usr/bin/env python3
"""Scenario loader for UK renewable decarbonization support costs.

Splits decarbonization levy into:
- **Existing** (RO + FiT + baseline CfD from 2024/25): system cost only, no VRE agent income.
- **Additional** (scenario CfD increment): system cost + conditional agent investable income.

CfD contracts pay for 20 years. Agent investable income rules:
- Low (price_smoothing_only): no additional CfD; existing levy only.
- Mid (normal_subsidy): each year's new CfD annual payment × 20 → VRE investment stimulus.
- High (strong_subsidy): inherit prior cohorts' 1× annual payments + new increment × 20.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable
import os

import pandas as pd


CFD_SUPPORT_YEARS = 20

HISTORICAL_SUPPORT_MN = [
    {"delivery_year": "2015/16", "year": 2015, "RO": 3910.0, "FiT": 1200.0, "CfD": 0.0, "REGO": 0.0},
    {"delivery_year": "2016/17", "year": 2016, "RO": 4500.0, "FiT": 1280.0, "CfD": 100.0, "REGO": 0.0},
    {"delivery_year": "2017/18", "year": 2017, "RO": 5300.0, "FiT": 1380.0, "CfD": 500.0, "REGO": 0.0},
    {"delivery_year": "2018/19", "year": 2018, "RO": 5900.0, "FiT": 1410.0, "CfD": 1000.0, "REGO": 0.0},
    {"delivery_year": "2019/20", "year": 2019, "RO": 6310.0, "FiT": 1500.0, "CfD": 1800.0, "REGO": 0.0},
    {"delivery_year": "2020/21", "year": 2020, "RO": 5730.0, "FiT": 1600.0, "CfD": 2300.0, "REGO": 0.0},
    {"delivery_year": "2021/22", "year": 2021, "RO": 6100.0, "FiT": 1700.0, "CfD": 300.0, "REGO": 0.0},
    {"delivery_year": "2022/23", "year": 2022, "RO": 6756.0, "FiT": 1630.0, "CfD": -132.0, "REGO": 0.1},
    {"delivery_year": "2023/24", "year": 2023, "RO": 7023.0, "FiT": 1840.0, "CfD": 1524.0, "REGO": 0.5},
    {"delivery_year": "2024/25", "year": 2024, "RO": 7737.3, "FiT": 2000.0, "CfD": 2238.6, "REGO": 1.0},
]

BASELINE_CFD_MN = float(HISTORICAL_SUPPORT_MN[-1]["CfD"])


@dataclass(frozen=True)
class DecarbonizationScenario:
    name: str
    description: str
    annual_cfd_decarbonization_increment_mn: float


def _historical_frame() -> pd.DataFrame:
    df = pd.DataFrame(HISTORICAL_SUPPORT_MN)
    df["Total_Decarbonization_mn"] = df[["RO", "FiT", "CfD", "REGO"]].sum(axis=1)
    df["Annual_New_Subsidy_mn"] = df["Total_Decarbonization_mn"].diff().clip(lower=0).fillna(0)
    return df


def annual_increment_metrics() -> Dict[str, float]:
    """Return the annual new-subsidy intensity used by scenarios 2 and 3."""
    df = _historical_frame()
    increments = df.loc[df["year"] > df["year"].min(), "Annual_New_Subsidy_mn"]
    return {
        "recent_10y_mean_annual_new_subsidy_mn": float(increments.mean()),
        "historical_max_annual_new_subsidy_mn": float(increments.max()),
    }


def scenarios() -> Dict[str, DecarbonizationScenario]:
    metrics = annual_increment_metrics()
    return {
        "price_smoothing_only": DecarbonizationScenario(
            name="price_smoothing_only",
            description="CfD is treated only as a renewable price-smoothing tool; no new decarbonization subsidy is added.",
            annual_cfd_decarbonization_increment_mn=0.0,
        ),
        "normal_subsidy": DecarbonizationScenario(
            name="normal_subsidy",
            description="Government keeps the recent renewable support intensity: mean annual new subsidy over the available last decade.",
            annual_cfd_decarbonization_increment_mn=metrics["recent_10y_mean_annual_new_subsidy_mn"],
        ),
        "strong_subsidy": DecarbonizationScenario(
            name="strong_subsidy",
            description="Government raises support to the historical maximum annual new renewable subsidy increment.",
            annual_cfd_decarbonization_increment_mn=metrics["historical_max_annual_new_subsidy_mn"],
        ),
    }


SCENARIO_ALIASES = {
    "no_expansion": "price_smoothing_only",
    "average_expansion": "normal_subsidy",
    "aggressive_expansion": "strong_subsidy",
}


def _canonical_scenario_name(scenario: str) -> str:
    return SCENARIO_ALIASES.get(scenario, scenario)


def agent_investable_income_gbp(
    scenario_name: str,
    year_index: int,
    annual_increment_gbp: float,
) -> tuple[float, float, float]:
    """Return (inherited_annual_gbp, new_stimulus_gbp, total_investable_gbp)."""
    if annual_increment_gbp <= 0 or scenario_name == "price_smoothing_only":
        return 0.0, 0.0, 0.0

    new_stimulus = annual_increment_gbp * CFD_SUPPORT_YEARS

    if scenario_name == "normal_subsidy":
        return 0.0, new_stimulus, new_stimulus

    if scenario_name == "strong_subsidy":
        inherited = max(0, year_index - 1) * annual_increment_gbp
        return inherited, new_stimulus, inherited + new_stimulus

    return 0.0, 0.0, 0.0


def _clean_numeric(value) -> float:
    if pd.isna(value):
        return 0.0
    if isinstance(value, str):
        value = value.replace(",", "").replace("~", "").strip()
        if not value:
            return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _read_repd(repd_path: str = "repd-q2-jul-2025.csv") -> pd.DataFrame:
    for encoding in ("utf-8", "latin1", "cp1252"):
        try:
            return pd.read_csv(repd_path, encoding=encoding, low_memory=False)
        except UnicodeDecodeError:
            continue
    return pd.read_csv(repd_path, encoding="latin1", low_memory=False)


def _support_cohort_frame(
    scheme: str,
    repd_path: str = "repd-q2-jul-2025.csv",
    support_years: int = 20,
) -> pd.DataFrame:
    df = _read_repd(repd_path)
    marker_col = "RO Banding (ROC/MWh)" if scheme == "RO" else "FiT Tariff (p/kWh)"
    required_cols = ["Site Name", "Technology Type", "Installed Capacity (MWelec)", "Operational", marker_col]
    missing = [col for col in required_cols if col not in df.columns]
    if missing:
        raise ValueError(f"REPD file is missing columns for {scheme}: {missing}")

    out = df[required_cols + [c for c in ["Development Status (short)", "Development Status"] if c in df.columns]].copy()
    out["capacity_mw"] = out["Installed Capacity (MWelec)"].apply(_clean_numeric)
    out["support_marker"] = out[marker_col].apply(_clean_numeric)
    out["operational_date"] = pd.to_datetime(out["Operational"], dayfirst=True, errors="coerce")
    out["operational_year"] = out["operational_date"].dt.year

    status_cols = [c for c in ["Development Status (short)", "Development Status"] if c in out.columns]
    if status_cols:
        status_mask = pd.Series(False, index=out.index)
        for col in status_cols:
            status_mask = status_mask | out[col].astype(str).str.contains("Operational", case=False, na=False)
    else:
        status_mask = pd.Series(True, index=out.index)

    out = out[
        status_mask
        & (out["capacity_mw"] > 0)
        & (out["support_marker"] > 0)
        & out["operational_year"].notna()
    ].copy()
    out["scheme"] = scheme
    out["retirement_year"] = out["operational_year"].astype(int) + support_years
    if scheme == "RO":
        out["retirement_year"] = out["retirement_year"].clip(upper=2037)
    return out[["scheme", "Site Name", "Technology Type", "capacity_mw", "support_marker", "operational_year", "retirement_year"]]


def build_legacy_retirement_table(
    years: Iterable[int] = range(2025, 2035),
    repd_path: str = "repd-q2-jul-2025.csv",
    support_years: int = 20,
) -> pd.DataFrame:
    """Build project-cohort retirement shares from REPD support markers."""
    cohorts = pd.concat([
        _support_cohort_frame("RO", repd_path=repd_path, support_years=support_years),
        _support_cohort_frame("FiT", repd_path=repd_path, support_years=support_years),
    ], ignore_index=True)

    rows = []
    for scheme, scheme_df in cohorts.groupby("scheme"):
        base_active_capacity = scheme_df.loc[
            (scheme_df["operational_year"] <= 2025) & (scheme_df["retirement_year"] > 2025),
            "capacity_mw",
        ].sum()
        for year in years:
            active_capacity = scheme_df.loc[
                (scheme_df["operational_year"] <= year) & (scheme_df["retirement_year"] > year),
                "capacity_mw",
            ].sum()
            retired_capacity = max(0.0, base_active_capacity - active_capacity)
            share = active_capacity / base_active_capacity if base_active_capacity > 0 else 1.0
            rows.append({
                "Year": int(year),
                "Scheme": scheme,
                "Base_2025_Active_Capacity_MW": float(base_active_capacity),
                "Active_Supported_Capacity_MW": float(active_capacity),
                "Retired_vs_2025_Capacity_MW": float(retired_capacity),
                "Payment_Share_vs_2025": float(max(0.0, min(1.0, share))),
                "Project_Count": int(len(scheme_df)),
            })
    return pd.DataFrame(rows)


def build_decarbonization_cost_path(
    scenario: str = "normal_subsidy",
    years: Iterable[int] = range(2025, 2035),
    repd_path: str = "repd-q2-jul-2025.csv",
) -> pd.DataFrame:
    scenario = _canonical_scenario_name(scenario)
    scenario_map = scenarios()
    if scenario not in scenario_map:
        valid = ", ".join(sorted(set(scenario_map) | set(SCENARIO_ALIASES)))
        raise ValueError(f"Unknown decarbonization scenario '{scenario}'. Valid scenarios: {valid}")

    selected = scenario_map[scenario]
    latest = HISTORICAL_SUPPORT_MN[-1]
    retirement = build_legacy_retirement_table(years=years, repd_path=repd_path)
    retirement_lookup = {
        (int(row.Year), row.Scheme): row
        for row in retirement.itertuples(index=False)
    }
    rows = []
    for i, year in enumerate(years, start=1):
        ro_retirement = retirement_lookup[(int(year), "RO")]
        fit_retirement = retirement_lookup[(int(year), "FiT")]
        ro_mn = latest["RO"] * ro_retirement.Payment_Share_vs_2025
        fit_mn = latest["FiT"] * fit_retirement.Payment_Share_vs_2025
        cfd_baseline_mn = BASELINE_CFD_MN

        annual_cfd_increment_mn = selected.annual_cfd_decarbonization_increment_mn
        additional_cfd_mn = annual_cfd_increment_mn * i
        existing_mn = ro_mn + fit_mn + cfd_baseline_mn
        total_mn = existing_mn + additional_cfd_mn

        annual_increment_gbp = annual_cfd_increment_mn * 1e6
        inherited_gbp, new_stimulus_gbp, agent_investable_gbp = agent_investable_income_gbp(
            selected.name, i, annual_increment_gbp
        )

        rows.append({
            "Year": int(year),
            "Year_Index": i,
            "Scenario": selected.name,
            "RO_Payment_Share_vs_2025": ro_retirement.Payment_Share_vs_2025,
            "FiT_Payment_Share_vs_2025": fit_retirement.Payment_Share_vs_2025,
            "RO_Active_Supported_Capacity_MW": ro_retirement.Active_Supported_Capacity_MW,
            "FiT_Active_Supported_Capacity_MW": fit_retirement.Active_Supported_Capacity_MW,
            "RO_Legacy_mn": ro_mn,
            "FiT_Legacy_mn": fit_mn,
            "CfD_Baseline_mn": cfd_baseline_mn,
            "CfD_New_Decarbonization_mn": additional_cfd_mn,
            "Existing_Decarbonization_mn": existing_mn,
            "Additional_Decarbonization_mn": additional_cfd_mn,
            "Annual_CfD_Increment_mn": annual_cfd_increment_mn,
            "Total_Decarbonization_Cost_mn": total_mn,
            "RO_Legacy_GBP": ro_mn * 1e6,
            "FiT_Legacy_GBP": fit_mn * 1e6,
            "CfD_Baseline_GBP": cfd_baseline_mn * 1e6,
            "CfD_New_Decarbonization_GBP": additional_cfd_mn * 1e6,
            "Existing_Decarbonization_Cost_GBP": existing_mn * 1e6,
            "Additional_Decarbonization_Cost_GBP": additional_cfd_mn * 1e6,
            "Inherited_CfD_Agent_Income_GBP": inherited_gbp,
            "New_CfD_Stimulus_GBP": new_stimulus_gbp,
            "Agent_Investable_Decarb_Income_GBP": agent_investable_gbp,
            "Decarbonization_Cost": total_mn * 1e6,
        })
    return pd.DataFrame(rows)


def load_decarbonization_costs(
    scenario: str | None = None,
    years: Iterable[int] = range(2025, 2035),
    repd_path: str = "repd-q2-jul-2025.csv",
) -> Dict[int, Dict[str, float]]:
    """Return year-keyed costs compatible with the investment scripts."""
    scenario_name = _canonical_scenario_name(scenario or os.getenv("DECARB_SCENARIO", "normal_subsidy"))
    df = build_decarbonization_cost_path(
        scenario=scenario_name,
        years=years,
        repd_path=repd_path,
    )
    return {
        int(row.Year): {
            "Decarbonization_Cost": float(row.Decarbonization_Cost),
            "Existing_Decarbonization_Cost_GBP": float(row.Existing_Decarbonization_Cost_GBP),
            "Additional_Decarbonization_Cost_GBP": float(row.Additional_Decarbonization_Cost_GBP),
            "RO_Legacy_GBP": float(row.RO_Legacy_GBP),
            "FiT_Legacy_GBP": float(row.FiT_Legacy_GBP),
            "CfD_Baseline_GBP": float(row.CfD_Baseline_GBP),
            "CfD_New_Decarbonization_GBP": float(row.CfD_New_Decarbonization_GBP),
            "Annual_CfD_Increment_GBP": float(row.Annual_CfD_Increment_mn * 1e6),
            "Inherited_CfD_Agent_Income_GBP": float(row.Inherited_CfD_Agent_Income_GBP),
            "New_CfD_Stimulus_GBP": float(row.New_CfD_Stimulus_GBP),
            "Agent_Investable_Decarb_Income_GBP": float(row.Agent_Investable_Decarb_Income_GBP),
            "RO_Payment_Share_vs_2025": float(row.RO_Payment_Share_vs_2025),
            "FiT_Payment_Share_vs_2025": float(row.FiT_Payment_Share_vs_2025),
        }
        for row in df.itertuples(index=False)
    }


def write_scenario_csv(output_path: str = "decarbonization_cost_scenarios.csv") -> pd.DataFrame:
    frames = [build_decarbonization_cost_path(name) for name in scenarios()]
    out = pd.concat(frames, ignore_index=True)
    out.to_csv(output_path, index=False)
    build_legacy_retirement_table().to_csv("ro_fit_legacy_retirement_table.csv", index=False)
    return out


if __name__ == "__main__":
    print("Annual new-subsidy intensity metrics (real 2025 GBP mn):")
    for key, value in annual_increment_metrics().items():
        print(f"  {key}: {value:,.2f}")
    df_out = write_scenario_csv()
    print("\nScenario paths written to decarbonization_cost_scenarios.csv")
    cols = [
        "Year", "Scenario", "Existing_Decarbonization_mn", "Additional_Decarbonization_mn",
        "Agent_Investable_Decarb_Income_GBP", "Total_Decarbonization_Cost_mn",
    ]
    print(df_out[cols].to_string(index=False))
