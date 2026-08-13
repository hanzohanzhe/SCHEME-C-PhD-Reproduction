"""Helpers to add capacity to four expandable storage agents and sync C-rate limits."""

from __future__ import annotations

from typing import Mapping

import config

from storage_expansion_cap import (
    EXPANDABLE_STORAGE_KEYS,
    split_capacity_by_template_weights,
    sync_battery_pool_limits,
)


def apply_expandable_storage_expansion(
    battery_objects,
    capacity_to_add,
    current_year,
    investment_summary,
    source,
    assignment_method="Proportional four-tech storage split",
):
    """Add capacity to 0.25c / 0.5c / 1c / hydrogen (never pumped hydro)."""
    keys = tuple(k for k in EXPANDABLE_STORAGE_KEYS if k in battery_objects)
    if not keys or capacity_to_add <= 0:
        return

    pools = {k: float(battery_objects[k].pool_limit) for k in keys}
    total_pool = sum(pools.values())
    if total_pool <= 0:
        allocation = split_capacity_by_template_weights(capacity_to_add, keys)
    else:
        allocation = {k: capacity_to_add * pools[k] / total_pool for k in keys}

    for key in keys:
        allocated = allocation.get(key, 0.0)
        if allocated <= 1e-9:
            continue
        asset = battery_objects[key]
        old_limit = asset.pool_limit
        asset.pool_limit = max(0.0, old_limit + allocated)
        sync_battery_pool_limits(battery_objects, key)
        cost_per_mw = config.capital_costs_per_mw.get(key, config.capital_costs_per_mw.get("battery", 0))
        investment_cost = allocated * cost_per_mw
        if not hasattr(asset, "capital_cost"):
            asset.capital_cost = 0
        asset.capital_cost += investment_cost
        investment_summary.append(
            {
                "Year": current_year,
                "Asset": key,
                "Source": source,
                "Added_Capacity_MW": allocated,
                "Investment_Cost": investment_cost,
                "Assignment_Method": assignment_method,
            }
        )
        print(
            f"    ✓ Updated {key}: pool_limit {old_limit:.2f} → {asset.pool_limit:.2f} "
            f"(+{allocated:.2f} MW, per_pool_limit={asset.per_pool_limit:.2f} MWh/period from {source})"
        )


def apply_repd_battery_stock_split(battery_objects, battery_mw: float) -> None:
    """Distribute REPD operational battery MW across four expandable technologies."""
    allocation = split_capacity_by_template_weights(battery_mw)
    for key in EXPANDABLE_STORAGE_KEYS:
        if key not in battery_objects:
            continue
        mw = allocation.get(key, 0.0)
        battery_objects[key].pool_limit = mw
        sync_battery_pool_limits(battery_objects, key)
        battery_objects[key].capital_cost = mw * config.capital_costs_per_mw.get(key, 0)
