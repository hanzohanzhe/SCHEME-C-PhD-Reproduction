#!/usr/bin/env python3
"""Save per-period, per-asset generation traces for scenario archive runs."""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Callable, Iterable, Any

import pandas as pd


def _period_hours() -> float:
    try:
        return float(os.getenv("PHYSICAL_PERIOD_HOURS", "0.5"))
    except ValueError:
        return 0.5


def save_period_generation_trace(
    gen_list_composition: Iterable,
    year: int,
    scenario: str,
    output_dir: Path,
    get_asset_type: Callable[[str], str],
) -> dict[str, Path]:
    """Write long-format period generation + annual by-asset summary.

    TRACE_FORMAT=sqlite writes compact queryable traces without expensive Excel/CSV
    churn. The `generation_mwh` column is physical MWh for the half-hour dispatch
    period; `dispatch_mw_equivalent` preserves the raw model period value.
    """
    trace_format = os.getenv("TRACE_FORMAT", "sqlite").strip().lower()
    period_hours = _period_hours()
    rows = []
    for period_idx, period_data in enumerate(gen_list_composition):
        for asset, energy in period_data:
            name = getattr(asset, "name", str(asset))
            dispatch_mw_equivalent = float(energy)
            generation_mwh = dispatch_mw_equivalent * period_hours
            if generation_mwh == 0.0:
                continue
            rows.append(
                {
                    "scenario": scenario,
                    "year": int(year),
                    "period": int(period_idx),
                    "asset_name": name,
                    "asset_type": get_asset_type(name),
                    "generation_mwh": generation_mwh,
                    "dispatch_mw_equivalent": dispatch_mw_equivalent,
                    "period_hours": period_hours,
                    "source": "psm_dispatch",
                }
            )

    out_dir = Path(output_dir)
    period_dir = out_dir / "generation_by_period"
    period_dir.mkdir(parents=True, exist_ok=True)

    df = pd.DataFrame(rows)
    if trace_format == "sqlite":
        sqlite_path = out_dir / "generation_trace.sqlite"
        with sqlite3.connect(sqlite_path) as conn:
            # Re-running a year in the same output folder should replace that
            # year's rows rather than append duplicates.
            conn.execute(
                "DELETE FROM generation_by_period WHERE scenario = ? AND year = ?",
                (str(scenario), int(year)),
            ) if conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='generation_by_period'"
            ).fetchone() else None
            df.to_sql("generation_by_period", conn, if_exists="append", index=False)
        period_path = sqlite_path
    else:
        period_path = period_dir / f"generation_{year}.csv"
        df.to_csv(period_path, index=False)

    if not df.empty:
        annual = (
            df.groupby(["asset_name", "asset_type"], as_index=False)["generation_mwh"]
            .sum()
            .sort_values("generation_mwh", ascending=False)
        )
    else:
        annual = pd.DataFrame(columns=["asset_name", "asset_type", "generation_mwh"])
    annual.insert(0, "scenario", scenario)
    annual.insert(1, "year", int(year))
    if trace_format == "sqlite":
        annual_path = out_dir / "generation_trace.sqlite"
        with sqlite3.connect(annual_path) as conn:
            conn.execute(
                "DELETE FROM generation_annual WHERE scenario = ? AND year = ?",
                (str(scenario), int(year)),
            ) if conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='generation_annual'"
            ).fetchone() else None
            annual.to_sql("generation_annual", conn, if_exists="append", index=False)
    else:
        annual_path = out_dir / "generation_annual" / f"generation_annual_{year}.csv"
        annual_path.parent.mkdir(parents=True, exist_ok=True)
        annual.to_csv(annual_path, index=False)

    manifest_path = out_dir / "generation_manifest.json"
    manifest: dict[str, Any] = {}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest[str(year)] = {
        "format": trace_format,
        "period_trace": str(period_path.relative_to(out_dir)),
        "annual_trace": str(annual_path.relative_to(out_dir)),
        "n_periods": int(df["period"].nunique()) if not df.empty else 0,
        "n_assets": int(df["asset_name"].nunique()) if not df.empty else 0,
        "total_generation_mwh": float(df["generation_mwh"].sum()) if not df.empty else 0.0,
        "period_hours": period_hours,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    return {"period": period_path, "annual": annual_path, "manifest": manifest_path}
