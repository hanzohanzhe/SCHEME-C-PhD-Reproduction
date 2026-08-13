#!/usr/bin/env python3
"""VRE expansion policy helpers for scenarios_v2."""
from __future__ import annotations

from typing import Dict

import config

from scenarios_v2.load_scenarios_v2 import (
    desnz_capacity_ceiling_mw,
    desnz_headroom_mw,
    techs_below_desnz_ceiling,
)

VRE_TYPES = ("solar", "onshore", "offshore")


def compute_cfd_mw_by_tech(
    investable_gbp: float,
    tech_capacity_totals: Dict[str, float],
) -> Dict[str, float]:
    vre_total = sum(tech_capacity_totals.get(t, 0.0) for t in VRE_TYPES)
    out = {t: 0.0 for t in VRE_TYPES}
    if investable_gbp <= 0 or vre_total <= 0:
        return out
    for tech in VRE_TYPES:
        cost = config.capital_costs_per_mw.get(tech, 0)
        if cost <= 0:
            continue
        share = tech_capacity_totals.get(tech, 0.0) / vre_total
        out[tech] = (investable_gbp * share) / cost
    return out


def compute_cfd_mw_by_tech_until_tech_cap(
    investable_gbp: float,
    tech_capacity_totals: Dict[str, float],
    year: int,
) -> Dict[str, float]:
    """Allocate CfD stimulus only to VRE types still below DESNZ ceiling (no MW build cap)."""
    out = {t: 0.0 for t in VRE_TYPES}
    if investable_gbp <= 0:
        return out
    eligible = techs_below_desnz_ceiling(tech_capacity_totals, year)
    if not eligible:
        return out
    eligible_cap = sum(float(tech_capacity_totals.get(t, 0.0)) for t in eligible)
    if eligible_cap <= 0:
        per_tech = investable_gbp / len(eligible)
        for tech in eligible:
            cost = config.capital_costs_per_mw.get(tech, 0)
            if cost > 0:
                out[tech] = per_tech / cost
        return out
    for tech in eligible:
        cost = config.capital_costs_per_mw.get(tech, 0)
        if cost <= 0:
            continue
        share = float(tech_capacity_totals.get(tech, 0.0)) / eligible_cap
        out[tech] = (investable_gbp * share) / cost
    for tech in VRE_TYPES:
        if tech not in eligible:
            out[tech] = 0.0
    return out


def compute_cfd_mw_by_operational_headroom(
    investable_gbp: float,
    tech_capacity_totals: Dict[str, float],
    year: int,
) -> Dict[str, float]:
    """Allocate CfD only to techs below DESNZ operational target, by headroom gap share."""
    out = {t: 0.0 for t in VRE_TYPES}
    if investable_gbp <= 0:
        return out
    headroom = desnz_headroom_mw(tech_capacity_totals, year)
    eligible = [t for t in VRE_TYPES if headroom.get(t, 0.0) > 1.0]
    if not eligible:
        return out
    total_headroom = sum(headroom[t] for t in eligible)
    for tech in eligible:
        cost = config.capital_costs_per_mw.get(tech, 0)
        if cost <= 0:
            continue
        share = headroom[tech] / total_headroom
        out[tech] = (investable_gbp * share) / cost
    return out


def apply_desnz_regulated_cap(
    regulated_targets: Dict[str, float],
    tech_capacity_totals: Dict[str, float],
    year: int,
) -> Dict[str, float]:
    """Clip regulated new-build to remaining DESNZ ceiling headroom per technology."""
    ceilings = desnz_capacity_ceiling_mw(year)
    capped = dict(regulated_targets)
    for tech in VRE_TYPES:
        current = float(tech_capacity_totals.get(tech, 0.0))
        headroom = max(0.0, ceilings[tech] - current)
        if tech in capped and capped[tech] is not None:
            capped[tech] = min(float(capped[tech] or 0.0), headroom)
    return capped


def clip_cfd_mw_to_desnz_headroom(
    cfd_mw_by_tech: Dict[str, float],
    tech_capacity_totals: Dict[str, float],
    year: int,
) -> Dict[str, float]:
    ceilings = desnz_capacity_ceiling_mw(year)
    clipped = {}
    for tech in VRE_TYPES:
        current = float(tech_capacity_totals.get(tech, 0.0))
        headroom = max(0.0, ceilings[tech] - current)
        clipped[tech] = min(cfd_mw_by_tech.get(tech, 0.0), headroom)
    return clipped
