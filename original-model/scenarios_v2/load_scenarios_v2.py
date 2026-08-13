#!/usr/bin/env python3
"""V2 decarbonization scenarios (separate from low/mid/high).

Scenarios:
- existing_decarb_base: CM + existing RO/FiT/baseline CfD levy only (system cost).
- governmental_target: DESNZ path; per-tech new CfD to agents stops at ceiling (no build cap).
- operational_capacity_target: yearly operational MW vs DESNZ; subsidy only to close under-target gaps.
- subsidy_as_usual: marginal CfD increment (YoY additional payment) -> agents, no DESNZ cap.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable
import os
import sys
from pathlib import Path

import pandas as pd

_PARENT = Path(__file__).resolve().parent.parent
if str(_PARENT) not in sys.path:
    sys.path.insert(0, str(_PARENT))

from load_decarbonization_cost_breakdown import (  # noqa: E402
    BASELINE_CFD_MN,
    HISTORICAL_SUPPORT_MN,
    annual_increment_metrics,
    build_legacy_retirement_table,
)

# DESNZ Clean Power annex (April 2025): 2024 installed -> 2035 upper bound (MW).
DESNZ_INSTALLED_2024_MW = {"solar": 16600.0, "onshore": 14200.0, "offshore": 14800.0}
DESNZ_UPPER_2035_MW = {"solar": 69000.0, "onshore": 37000.0, "offshore": 89000.0}
DESNZ_TOTAL_UPPER_2035_MW = sum(DESNZ_UPPER_2035_MW.values())  # 195 GW


@dataclass(frozen=True)
class ScenarioV2:
    name: str
    description: str
    annual_cfd_increment_mn: float
    agent_income_mode: str  # none | annual_increment | annual_increment_until_cap | annual_increment_until_tech_cap | subsidy_to_operational_target
    use_desnz_regulated_cap: bool


def scenarios_v2() -> Dict[str, ScenarioV2]:
    metrics = annual_increment_metrics()
    increment = metrics["recent_10y_mean_annual_new_subsidy_mn"]
    return {
        "existing_decarb_base": ScenarioV2(
            name="existing_decarb_base",
            description="CM (UK de-rating) + existing decarbonization levy only; no new CfD to agents.",
            annual_cfd_increment_mn=0.0,
            agent_income_mode="none",
            use_desnz_regulated_cap=False,
        ),
        "governmental_target": ScenarioV2(
            name="governmental_target",
            description=(
                "DESNZ target-driven path: new CfD income is scaled by the remaining "
                "operational capacity gap and allocated only to technologies below target."
            ),
            annual_cfd_increment_mn=increment,
            agent_income_mode="subsidy_to_operational_target",
            use_desnz_regulated_cap=False,
        ),
        "operational_capacity_target": ScenarioV2(
            name="operational_capacity_target",
            description=(
                "Each year: compare operational (installed) MW per tech to DESNZ path; "
                "extra CfD only for under-target techs, weighted by headroom gap; no pipeline check."
            ),
            annual_cfd_increment_mn=increment,
            agent_income_mode="subsidy_to_operational_target",
            use_desnz_regulated_cap=False,
        ),
        "subsidy_as_usual": ScenarioV2(
            name="subsidy_as_usual",
            description="Marginal annual CfD increment flows to VRE agents (1x); ignores DESNZ cap.",
            annual_cfd_increment_mn=increment,
            agent_income_mode="annual_increment",
            use_desnz_regulated_cap=False,
        ),
    }


def desnz_capacity_ceiling_mw(year: int) -> Dict[str, float]:
    """Linear path from DESNZ 2024 installed to 2035 upper bound."""
    span = 2035 - 2024
    frac = max(0.0, min(1.0, (year - 2024) / span))
    return {
        tech: DESNZ_INSTALLED_2024_MW[tech] + frac * (DESNZ_UPPER_2035_MW[tech] - DESNZ_INSTALLED_2024_MW[tech])
        for tech in DESNZ_INSTALLED_2024_MW
    }


def desnz_total_ceiling_mw(year: int) -> float:
    return sum(desnz_capacity_ceiling_mw(year).values())


def techs_below_desnz_ceiling(tech_capacity_totals: Dict[str, float], year: int) -> list[str]:
    ceilings = desnz_capacity_ceiling_mw(year)
    return [
        tech
        for tech in DESNZ_INSTALLED_2024_MW
        if float(tech_capacity_totals.get(tech, 0.0)) < ceilings[tech] - 1.0
    ]


def desnz_headroom_mw(tech_capacity_totals: Dict[str, float], year: int) -> Dict[str, float]:
    """Operational MW gap to DESNZ path target (installed only, not pipeline)."""
    ceilings = desnz_capacity_ceiling_mw(year)
    return {
        tech: max(0.0, ceilings[tech] - float(tech_capacity_totals.get(tech, 0.0)))
        for tech in DESNZ_INSTALLED_2024_MW
    }


def agent_investable_income_v2(
    scenario: ScenarioV2,
    annual_increment_gbp: float,
    total_vre_mw: float,
    year: int,
    tech_capacity_totals: Dict[str, float] | None = None,
) -> float:
    if scenario.agent_income_mode == "none" or annual_increment_gbp <= 0:
        return 0.0
    if scenario.agent_income_mode == "annual_increment":
        return annual_increment_gbp
    if scenario.agent_income_mode == "annual_increment_until_cap":
        if total_vre_mw >= desnz_total_ceiling_mw(year) - 1.0:
            return 0.0
        return annual_increment_gbp
    if scenario.agent_income_mode == "annual_increment_until_tech_cap":
        if not tech_capacity_totals:
            return annual_increment_gbp
        if not techs_below_desnz_ceiling(tech_capacity_totals, year):
            return 0.0
        return annual_increment_gbp
    if scenario.agent_income_mode == "subsidy_to_operational_target":
        if not tech_capacity_totals:
            return annual_increment_gbp
        headroom = desnz_headroom_mw(tech_capacity_totals, year)
        total_headroom = sum(v for v in headroom.values() if v > 1.0)
        if total_headroom <= 1.0:
            return 0.0
        total_target = desnz_total_ceiling_mw(year)
        if total_target <= 0:
            return 0.0
        return annual_increment_gbp * min(1.0, total_headroom / total_target)
    return 0.0


def build_scenario_v2_cost_path(
    scenario: str = "existing_decarb_base",
    years: Iterable[int] = range(2025, 2035),
    repd_path: str = "repd-q2-jul-2025.csv",
) -> pd.DataFrame:
    scenario_map = scenarios_v2()
    if scenario not in scenario_map:
        valid = ", ".join(sorted(scenario_map))
        raise ValueError(f"Unknown V2 scenario '{scenario}'. Valid: {valid}")

    selected = scenario_map[scenario]
    latest = HISTORICAL_SUPPORT_MN[-1]
    retirement = build_legacy_retirement_table(years=years, repd_path=repd_path)
    retirement_lookup = {(int(r.Year), r.Scheme): r for r in retirement.itertuples(index=False)}

    rows = []
    for i, year in enumerate(years, start=1):
        ro_r = retirement_lookup[(int(year), "RO")]
        fit_r = retirement_lookup[(int(year), "FiT")]
        ro_mn = latest["RO"] * ro_r.Payment_Share_vs_2025
        fit_mn = latest["FiT"] * fit_r.Payment_Share_vs_2025
        existing_mn = ro_mn + fit_mn + BASELINE_CFD_MN
        annual_inc_mn = selected.annual_cfd_increment_mn
        additional_mn = annual_inc_mn * i
        total_mn = existing_mn + additional_mn
        annual_inc_gbp = annual_inc_mn * 1e6

        # Placeholder VRE for pre-run path table; runtime recalculates with live capacity.
        agent_gbp = agent_investable_income_v2(selected, annual_inc_gbp, 0.0, int(year))
        ceilings = desnz_capacity_ceiling_mw(int(year))

        rows.append({
            "Year": int(year),
            "Year_Index": i,
            "Scenario": selected.name,
            "Agent_Income_Mode": selected.agent_income_mode,
            "Use_DESNZ_Regulated_Cap": selected.use_desnz_regulated_cap,
            "Existing_Decarbonization_mn": existing_mn,
            "Additional_Decarbonization_mn": additional_mn,
            "Annual_CfD_Increment_mn": annual_inc_mn,
            "Total_Decarbonization_Cost_mn": total_mn,
            "Existing_Decarbonization_Cost_GBP": existing_mn * 1e6,
            "Additional_Decarbonization_Cost_GBP": additional_mn * 1e6,
            "Annual_CfD_Increment_GBP": annual_inc_gbp,
            "Agent_Investable_Decarb_Income_GBP": agent_gbp,
            "Decarbonization_Cost": total_mn * 1e6,
            "DESNZ_Solar_Ceiling_MW": ceilings["solar"],
            "DESNZ_Onshore_Ceiling_MW": ceilings["onshore"],
            "DESNZ_Offshore_Ceiling_MW": ceilings["offshore"],
            "DESNZ_Total_Ceiling_MW": sum(ceilings.values()),
            "V2_Policy": selected.name,
        })
    return pd.DataFrame(rows)


def load_scenarios_v2_costs(
    scenario: str | None = None,
    years: Iterable[int] = range(2025, 2035),
    repd_path: str = "repd-q2-jul-2025.csv",
) -> Dict[int, Dict[str, float]]:
    name = scenario or os.getenv("DECARB_V2_SCENARIO", "existing_decarb_base")
    df = build_scenario_v2_cost_path(scenario=name, years=years, repd_path=repd_path)
    selected = scenarios_v2()[name]
    return {
        int(row.Year): {
            "Decarbonization_Cost": float(row.Decarbonization_Cost),
            "Existing_Decarbonization_Cost_GBP": float(row.Existing_Decarbonization_Cost_GBP),
            "Additional_Decarbonization_Cost_GBP": float(row.Additional_Decarbonization_Cost_GBP),
            "Annual_CfD_Increment_GBP": float(row.Annual_CfD_Increment_GBP),
            "Agent_Investable_Decarb_Income_GBP": float(row.Agent_Investable_Decarb_Income_GBP),
            "RO_Legacy_GBP": 0.0,
            "FiT_Legacy_GBP": 0.0,
            "CfD_Baseline_GBP": 0.0,
            "CfD_New_Decarbonization_GBP": float(row.Additional_Decarbonization_Cost_GBP),
            "Inherited_CfD_Agent_Income_GBP": 0.0,
            "New_CfD_Stimulus_GBP": float(row.Agent_Investable_Decarb_Income_GBP),
            "RO_Payment_Share_vs_2025": 1.0,
            "FiT_Payment_Share_vs_2025": 1.0,
            "V2_Scenario": name,
            "V2_Agent_Income_Mode": selected.agent_income_mode,
            "V2_Use_DESNZ_Regulated_Cap": selected.use_desnz_regulated_cap,
            "DESNZ_Total_Ceiling_MW": float(row.DESNZ_Total_Ceiling_MW),
            "DESNZ_Solar_Ceiling_MW": float(row.DESNZ_Solar_Ceiling_MW),
            "DESNZ_Onshore_Ceiling_MW": float(row.DESNZ_Onshore_Ceiling_MW),
            "DESNZ_Offshore_Ceiling_MW": float(row.DESNZ_Offshore_Ceiling_MW),
        }
        for row in df.itertuples(index=False)
    }


def refresh_runtime_decarb_costs(
    decarb_components: Dict[str, float],
    agent_investable_gbp: float,
    cumulative_additional_gbp: float,
) -> tuple[Dict[str, float], float]:
    """Consumer additional CfD = cumulative agent investable (pay only when VRE gets stimulus)."""
    mode = str(decarb_components.get("V2_Agent_Income_Mode", ""))
    if mode not in {"annual_increment_until_tech_cap", "subsidy_to_operational_target"}:
        return decarb_components, cumulative_additional_gbp

    cumulative_additional_gbp += max(0.0, float(agent_investable_gbp))
    existing = float(decarb_components.get("Existing_Decarbonization_Cost_GBP", 0.0))
    out = dict(decarb_components)
    out["Additional_Decarbonization_Cost_GBP"] = cumulative_additional_gbp
    out["CfD_New_Decarbonization_GBP"] = cumulative_additional_gbp
    out["Decarbonization_Cost"] = existing + cumulative_additional_gbp
    return out, cumulative_additional_gbp


def refresh_runtime_agent_income(
    decarb_components: Dict[str, float],
    total_vre_mw: float,
    current_year: int,
    tech_capacity_totals: Dict[str, float] | None = None,
) -> Dict[str, float]:
    """Recompute agent investable income using live VRE capacity."""
    name = decarb_components.get("V2_Scenario", os.getenv("DECARB_V2_SCENARIO", ""))
    if not name:
        return decarb_components
    selected = scenarios_v2().get(name)
    if not selected:
        return decarb_components
    annual_gbp = float(decarb_components.get("Annual_CfD_Increment_GBP", 0.0))
    agent = agent_investable_income_v2(
        selected, annual_gbp, total_vre_mw, current_year, tech_capacity_totals
    )
    out = dict(decarb_components)
    out["Agent_Investable_Decarb_Income_GBP"] = agent
    out["New_CfD_Stimulus_GBP"] = agent
    return out


def write_scenarios_v2_csv(output_path: str | None = None) -> pd.DataFrame:
    out_dir = Path(__file__).resolve().parent
    path = output_path or str(out_dir / "decarbonization_cost_scenarios_v2.csv")
    frames = [build_scenario_v2_cost_path(name) for name in scenarios_v2()]
    df = pd.concat(frames, ignore_index=True)
    df.to_csv(path, index=False)
    return df


if __name__ == "__main__":
    df = write_scenarios_v2_csv()
    print(df[["Year", "Scenario", "Existing_Decarbonization_mn", "Additional_Decarbonization_mn",
              "Agent_Investable_Decarb_Income_GBP", "DESNZ_Total_Ceiling_MW"]].to_string(index=False))
