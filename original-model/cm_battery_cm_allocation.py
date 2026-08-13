"""CEM Capacity Market allocation by de-rated discharge capacity."""
from __future__ import annotations

import os
from typing import Any

try:
    from storage_expansion_cap import (
        BATTERY_CM_DERATING,
        CEM_DERATING_REFERENCE,
        GENERATOR_CM_DERATING,
        PUMPED_HYDRO_CM_DERATING,
    )

    PUMPED_HYDRO_DEFAULT_DERATING = PUMPED_HYDRO_CM_DERATING
except ImportError:
    CEM_DERATING_REFERENCE = (
        "CEM: ancillary-service and CM fees allocated by discharge capacity; "
        "thermal 95%, nuclear 85%, pumped hydro 95%, "
        "1C/0.5C/0.25C batteries 5%/15%/60%"
    )
    GENERATOR_CM_DERATING = {
        "CCGT": 0.95,
        "OCGT": 0.95,
        "Nuclear": 0.85,
        "bio_and_waste": 0.95,
        "Hydro_natural_flow": 0.95,
    }
    BATTERY_CM_DERATING = {
        "1c_battery": 0.05,
        "0.5c_battery": 0.15,
        "0.25c_battery": 0.60,
    }
    PUMPED_HYDRO_DEFAULT_DERATING = 0.95


def cm_uk_derating_enabled() -> bool:
    return os.environ.get("CM_UK_DERATING", "").strip().lower() in {
        "1",
        "true",
        "yes",
    } or os.environ.get("CM_BATTERY_CM_SCENARIO4", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def scenario4_enabled() -> bool:
    """Backward-compatible alias for CEM de-rated CM allocation."""
    return cm_uk_derating_enabled()


def distribution_rule_description() -> str:
    if not cm_uk_derating_enabled():
        return "Annual CM pot allocated only to CCGT and OCGT by capacity share; biomass receives 0."
    gen_factors = ", ".join(f"{k}={v:.0%}" for k, v in sorted(GENERATOR_CM_DERATING.items()))
    bat_factors = ", ".join(f"{k}={v:.0%}" for k, v in sorted(BATTERY_CM_DERATING.items()))
    return (
        f"Annual CM pot split by de-rated discharge capacity ({CEM_DERATING_REFERENCE}). "
        f"Generators: {gen_factors}. "
        f"Batteries: {bat_factors}. "
        f"Pumped hydro: {PUMPED_HYDRO_DEFAULT_DERATING:.0%}."
    )


def _generator_nameplate_mw(name: str, asset: Any) -> float:
    return float(getattr(asset, "capacity_limit", 0.0) or 0.0)


def _battery_power_mw(name: str, asset: Any) -> float:
    return float(getattr(asset, "pool_limit", 0.0) or 0.0)


def _battery_derating(name: str, asset: Any) -> float:
    if name in BATTERY_CM_DERATING:
        return BATTERY_CM_DERATING[name]
    if name == "pumpedhydro_battery":
        return PUMPED_HYDRO_DEFAULT_DERATING
    return 0.0


def cm_derated_capacities(
    generator_objects: dict[str, Any],
    battery_objects: dict[str, Any],
) -> dict[str, float]:
    derated: dict[str, float] = {}

    for name, asset in generator_objects.items():
        if name not in GENERATOR_CM_DERATING:
            continue
        nameplate = _generator_nameplate_mw(name, asset)
        if nameplate <= 0:
            continue
        derated[name] = nameplate * GENERATOR_CM_DERATING[name]

    for name, asset in battery_objects.items():
        factor = _battery_derating(name, asset)
        if factor <= 0:
            continue
        power_mw = _battery_power_mw(name, asset)
        if power_mw <= 0:
            continue
        derated[name] = power_mw * factor

    return derated


def allocate_cm_income_scenario4(
    generator_objects: dict[str, Any],
    battery_objects: dict[str, Any],
    cm_cost_annual: float,
) -> dict[str, float]:
    """Allocate CM pot proportional to de-rated discharge capacity across eligible assets."""
    derated = cm_derated_capacities(generator_objects, battery_objects)
    total_derated = sum(derated.values())
    if total_derated <= 0 or cm_cost_annual <= 0:
        return {}
    return {
        name: float(cm_cost_annual) * capacity / total_derated
        for name, capacity in derated.items()
    }


allocate_cm_income_uk_derating = allocate_cm_income_scenario4
