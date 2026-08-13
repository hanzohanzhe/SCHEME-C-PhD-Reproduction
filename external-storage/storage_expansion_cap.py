"""
Storage expansion cap from aligned charge/discharge utilisation spectrum.

Core method:
  1. Virtual battery charges from excess, discharges to net demand.
  2. Build duration curves on charge power and discharge power (MW).
  3. Spectrum bands use **aligned** hours = min(charge_hours, discharge_hours)
     at each MW level (charge window must match discharge — no fake high-freq MW):
       daily     : aligned hours > 730 h/y
       inter-day : 365 < aligned hours ≤ 730
       weekly    : 52  < aligned hours ≤ 365
       seasonal  : aligned hours ≤ 52
  4. Invest_High power batteries: daily + inter-day only, then × CAP_FRACTION (0.20).
     pooled/pseudo-cascade also subtracts existing_MW before ×0.20.
     scheme_c uses residual excess/net demand after existing fleet — no second MW credit.

Credit modes: scheme_c | pooled_existing_mw | post_dispatch
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping

import numpy as np

import config

PERIODS_PER_DAY = 48
PERIODS_PER_YEAR = 17520
PERIOD_HOURS = 0.5
CAP_FRACTION = float(os.getenv("STORAGE_EXPANSION_CAP_FRACTION", "0.20"))
RTE = float(os.getenv("STORAGE_EXPANSION_RTE", "0.98"))
# Virtual (infinite) pool for utilisation-spectrum sizing. Must be large enough
# that annual residual charge never hits the energy ceiling — otherwise SOC
# clamps and high-frequency aligned hours are understated. Default = 1000 TWh.
VIRTUAL_POOL_ENERGY_MWH = float(
    os.getenv("STORAGE_VIRTUAL_POOL_ENERGY_MWH", str(1000.0 * 1e6))
)  # 1000 TWh
VIRTUAL_POOL_POWER_MW = float(os.getenv("STORAGE_VIRTUAL_POOL_POWER_MW", "1e9"))

# scheme_c | post_dispatch | pooled_existing_mw
CREDIT_MODE = os.getenv("STORAGE_CAP_CREDIT_MODE", "scheme_c").strip().lower()
# Assumed duration (h) only for legacy post_dispatch offline approximation
EXISTING_STORAGE_DURATION_H = float(os.getenv("STORAGE_EXISTING_DURATION_H", "4.0"))
# Battery asset names as written in generation_trace.sqlite / Battery.name
SIM_BATTERY_TRACE_NAMES = (
    "air_battery",
    "li_battery",
    "thermal_battery",
    "pumpedhydro_battery",
    "hydrogen_battery",
)

# Aligned utilisation hour gates (hours/year) for the MW spectrum
HOURS_DAILY = 730.0
HOURS_INTERDAY = 365.0
HOURS_WEEKLY = 52.0

# Aliases kept for older call sites / ROI docs
CYCLES_DAILY_MIN = HOURS_DAILY
CYCLES_INTRADAY_MIN = HOURS_INTERDAY
CYCLES_WEEKLY_MIN = HOURS_WEEKLY

TIER_ORDER = ("daily_loop", "intraday", "weekly", "seasonal")

TIER_MIN_ROI = {
    "daily_loop": 0.165,      # >730 aligned hours/y
    "intraday": 0.0825,       # >365 aligned hours/y
    "weekly": 0.01375,        # >52 aligned hours/y
    "seasonal": 0.01375,
}

# Which tiers each technology may serve for expansion-cap eligibility
BATTERY_ELIGIBLE_TIERS: dict[str, tuple[str, ...]] = {
    "0.5c_battery": ("daily_loop",),
    "1c_battery": ("daily_loop", "intraday"),
    "0.25c_battery": ("daily_loop", "intraday", "weekly"),
    "hydrogen_battery": ("seasonal",),
}

# Duration (h) at nameplate power for energy sizing
BATTERY_DURATION_H: dict[str, float] = {
    "0.5c_battery": 2.0,
    "1c_battery": 1.0,
    "0.25c_battery": 4.0,
    "hydrogen_battery": 168.0,
}

# Half-hour periods to fully discharge at nominal C-rate (0.25C => 8 periods)
DISCHARGE_PERIODS: dict[str, int] = {
    "0.25c_battery": 8,
    "0.5c_battery": 4,
    "1c_battery": 2,
    "hydrogen_battery": 336,  # 168 h / 0.5 h
}

# CEM Capacity Market / flexibility de-rating (by discharge capacity share).
# Thermal generators 95%; nuclear 85%; pumped hydro 95%; batteries by c-rate.
CEM_DERATING_REFERENCE = (
    "CEM: ancillary-service and CM fees allocated by discharge capacity; "
    "thermal 95%, nuclear 85%, pumped hydro 95%, "
    "1C/0.5C/0.25C batteries 5%/15%/60%"
)
THERMAL_CM_DERATING = 0.95
NUCLEAR_CM_DERATING = 0.85
PUMPED_HYDRO_CM_DERATING = 0.95

GENERATOR_CM_DERATING: dict[str, float] = {
    "CCGT": THERMAL_CM_DERATING,
    "OCGT": THERMAL_CM_DERATING,
    "Nuclear": NUCLEAR_CM_DERATING,
    "bio_and_waste": THERMAL_CM_DERATING,
    "Hydro_natural_flow": THERMAL_CM_DERATING,
}

BATTERY_CM_DERATING: dict[str, float] = {
    "1c_battery": 0.05,
    "0.5c_battery": 0.15,
    "0.25c_battery": 0.60,
}

# Agent preferred ROI (Invest_High threshold) — tied to fastest loop each tech can serve
TECH_PREFERRED_RATE: dict[str, float] = {
    "0.5c_battery": 0.165,       # daily loop only for LFP 0.5C
    "1c_battery": 0.0825,        # inter-day band lower bound
    "0.25c_battery": 0.0825,     # inter-day; weekly unlocked via tier ROI gate
    "hydrogen_battery": 0.01375, # seasonal
}

EXPANDABLE_STORAGE_KEYS = tuple(BATTERY_ELIGIBLE_TIERS.keys())

BATTERY_CAP_COLUMNS: dict[str, str] = {
    "0.5c_battery": "0.5c_battery_Capacity_MW",
    "1c_battery": "1c_battery_Capacity_MW",
    "0.25c_battery": "0.25c_battery_Capacity_MW",
    "hydrogen_battery": "hydrogen_battery_Capacity_MW",
}

# Scheme C aligned-utilisation spectrum band widths (MW), decarb-base offline
# forecast (storage_cap_forecast_scheme_c_2025_2034.csv). Incremental bands:
#   daily     = MW clearing >730 aligned h/y
#   intraday  = MW clearing >365 h/y  minus daily
#   weekly    = MW clearing >52 h/y   minus (daily+intraday)
#   seasonal  = MW clearing >0 h/y    minus (daily+intraday+weekly)
# Gates / payback (Table 10 style, £200/kWh 0.5C): >16.5% / 8.25–16.5% /
# 1.375–8.25% / <1.375%. Invest_High power room = 0.20×(daily+intraday).
TABLE_10_DEMAND_MW: dict[int, dict[str, float]] = {
    2025: {"daily_loop": 17564, "intraday": 24284, "weekly": 22054, "seasonal": 20954},
    2026: {"daily_loop": 17144, "intraday": 28453, "weekly": 23764, "seasonal": 22270},
    2027: {"daily_loop": 18424, "intraday": 32847, "weekly": 51051, "seasonal": 62418},
    2028: {"daily_loop": 18653, "intraday": 32838, "weekly": 50973, "seasonal": 62386},
    2029: {"daily_loop": 18330, "intraday": 33368, "weekly": 51784, "seasonal": 62800},
    2030: {"daily_loop": 30372, "intraday": 34206, "weekly": 52509, "seasonal": 64691},
    2031: {"daily_loop": 25590, "intraday": 34196, "weekly": 64388, "seasonal": 57317},
    2032: {"daily_loop": 25344, "intraday": 33645, "weekly": 64128, "seasonal": 60362},
    2033: {"daily_loop": 21423, "intraday": 33970, "weekly": 63570, "seasonal": 4015},
    2034: {"daily_loop": 29347, "intraday": 34523, "weekly": 64643, "seasonal": 58704},
}


def _classify_cycles_per_year(cycles_per_year: float) -> str:
    """Map annual loop count to tier (>730 / >365 / >52 / else seasonal)."""
    if cycles_per_year > CYCLES_DAILY_MIN:
        return "daily_loop"
    if cycles_per_year > CYCLES_INTRADAY_MIN:
        return "intraday"
    if cycles_per_year > CYCLES_WEEKLY_MIN:
        return "weekly"
    return "seasonal"


def _simulate_virtual_pool(
    excess: np.ndarray,
    deficit: np.ndarray,
    *,
    rte: float = RTE,
    energy_cap_mwh: float = VIRTUAL_POOL_ENERGY_MWH,
    power_mw: float = VIRTUAL_POOL_POWER_MW,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Neutral pool dispatch: charge from excess, discharge to deficit each period.
    Returns SOC trace (MWh), charge MWh/period, discharge MWh/period.
    """
    excess = np.asarray(excess, dtype=float)
    deficit = np.asarray(deficit, dtype=float)
    n = len(excess)
    max_period_mwh = power_mw * PERIOD_HOURS
    soc_trace = np.zeros(n)
    charge = np.zeros(n)
    discharge = np.zeros(n)
    soc = 0.0

    for t in range(n):
        exc = float(excess[t])
        dfc = float(deficit[t])

        if exc > 1e-9 and soc < energy_cap_mwh - 1e-9:
            ch = min(exc, max_period_mwh, (energy_cap_mwh - soc) / max(rte, 1e-9))
            soc += ch * rte
            charge[t] = ch
            exc -= ch

        if dfc > 1e-9 and soc > 1e-9:
            dis = min(dfc, max_period_mwh, soc)
            soc -= dis
            discharge[t] = dis
            dfc -= dis

        soc_trace[t] = soc

    return soc_trace, charge, discharge


def hours_above_power(power_mw: np.ndarray, p_mw: float) -> float:
    """Hours in the year when power strictly exceeds p_mw."""
    power_mw = np.asarray(power_mw, dtype=float)
    if power_mw.size == 0:
        return 0.0
    return float(np.sum(power_mw > p_mw) * PERIOD_HOURS)


def max_mw_with_min_hours(power_mw: np.ndarray, min_hours: float) -> float:
    """Largest P such that hours with power > P is at least min_hours."""
    power_mw = np.asarray(power_mw, dtype=float)
    if power_mw.size == 0:
        return 0.0
    peak = float(np.max(power_mw))
    if peak <= 0.0:
        return 0.0
    if min_hours <= 0.0:
        return peak
    if hours_above_power(power_mw, 0.0) < min_hours:
        return 0.0
    lo, hi = 0.0, peak
    for _ in range(64):
        mid = 0.5 * (lo + hi)
        if hours_above_power(power_mw, mid) >= min_hours:
            lo = mid
        else:
            hi = mid
    return float(lo)


def aligned_max_mw(
    charge_mw: np.ndarray, discharge_mw: np.ndarray, min_hours: float
) -> float:
    """Largest P where BOTH charge and discharge clear the hour gate.

    This is the charge–discharge alignment constraint: a MW slice only counts
    at a frequency if it has enough charge hours AND enough discharge hours.
    """
    charge_mw = np.asarray(charge_mw, dtype=float)
    discharge_mw = np.asarray(discharge_mw, dtype=float)
    peak = min(
        float(np.max(charge_mw)) if charge_mw.size else 0.0,
        float(np.max(discharge_mw)) if discharge_mw.size else 0.0,
    )
    if peak <= 0.0:
        return 0.0
    if min_hours <= 0.0:
        return peak

    def ok(p: float) -> bool:
        return (
            hours_above_power(charge_mw, p) >= min_hours
            and hours_above_power(discharge_mw, p) >= min_hours
        )

    if not ok(0.0):
        return 0.0
    lo, hi = 0.0, peak
    for _ in range(64):
        mid = 0.5 * (lo + hi)
        if ok(mid):
            lo = mid
        else:
            hi = mid
    return float(lo)


def aligned_utilisation_spectrum(
    excess_mwh: np.ndarray,
    net_demand_mwh: np.ndarray,
) -> dict[str, float]:
    """Run virtual pool then return aligned MW spectrum bands.

    Returns keys: daily_loop, intraday, weekly, seasonal,
    plus diagnostics mw_above_730/365/52/0, charge/discharge peaks, energies.
    """
    _soc, charge_mwh, discharge_mwh = _simulate_virtual_pool(excess_mwh, net_demand_mwh)
    charge_mw = np.asarray(charge_mwh, dtype=float) / PERIOD_HOURS
    discharge_mw = np.asarray(discharge_mwh, dtype=float) / PERIOD_HOURS

    mw_730 = aligned_max_mw(charge_mw, discharge_mw, HOURS_DAILY)
    mw_365 = aligned_max_mw(charge_mw, discharge_mw, HOURS_INTERDAY)
    mw_52 = aligned_max_mw(charge_mw, discharge_mw, HOURS_WEEKLY)
    mw_0 = aligned_max_mw(charge_mw, discharge_mw, 0.0)

    daily = mw_730
    interday = max(0.0, mw_365 - mw_730)
    weekly = max(0.0, mw_52 - mw_365)
    seasonal = max(0.0, mw_0 - mw_52)

    return {
        "daily_loop": daily,
        "intraday": interday,
        "weekly": weekly,
        "seasonal": seasonal,
        "mw_above_730h": mw_730,
        "mw_above_365h": mw_365,
        "mw_above_52h": mw_52,
        "mw_above_0h": mw_0,
        "peak_charge_MW": float(np.max(charge_mw)) if charge_mw.size else 0.0,
        "peak_discharge_MW": float(np.max(discharge_mw)) if discharge_mw.size else 0.0,
        "charge_TWh": float(np.sum(charge_mwh) / 1e6),
        "discharge_TWh": float(np.sum(discharge_mwh) / 1e6),
    }


def _series_to_period_mwh(
    x: np.ndarray,
    *,
    storage_discharge: np.ndarray | None = None,
    storage_net_demand: np.ndarray | None = None,
) -> np.ndarray:
    """Convert profile to MWh/period.

    Live CEM traces (when discharge/net_demand provided) are already MWh.
    Offline yearly CSVs are MW despite *_MWh names → × PERIOD_HOURS.
    Override with STORAGE_PROFILE_UNITS=mw|mwh.
    """
    x = np.asarray(x, dtype=float)
    units = os.getenv("STORAGE_PROFILE_UNITS", "").strip().lower()
    if units in ("mw", "power"):
        return x * PERIOD_HOURS
    if units in ("mwh", "energy"):
        return x
    if storage_discharge is not None or storage_net_demand is not None:
        return x
    return x * PERIOD_HOURS


def _turning_points(y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Indices and values of local extrema in a time series."""
    n = len(y)
    if n < 2:
        return np.array([0], dtype=int), y[:1].copy()
    idx = [0]
    for i in range(1, n - 1):
        d1 = y[i] - y[i - 1]
        d2 = y[i + 1] - y[i]
        if d1 * d2 < 0 or (abs(d1) > 1e-12 and abs(d2) < 1e-12) or (abs(d2) > 1e-12 and abs(d1) < 1e-12):
            idx.append(i)
    if idx[-1] != n - 1:
        idx.append(n - 1)
    idx_arr = np.array(idx, dtype=int)
    return idx_arr, y[idx_arr]


def _rainflow_cycles(soc: np.ndarray) -> list[dict]:
    """
    ASTM-style 3-point rainflow on SOC turning points.

    Each extracted cycle has:
      period  – duration in half-hour periods (peak-to-peak span)
      range   – MWh amplitude
      t_start, t_end – period index span for attribution
      tier    – loop-frequency class from cycles/year = PERIODS_PER_YEAR / period
    """
    tp_idx, tp_val = _turning_points(soc)
    stack: list[list[float | int]] = []
    raw_cycles: list[dict] = []

    for v, t in zip(tp_val, tp_idx):
        stack.append([float(v), int(t)])
        while len(stack) >= 3:
            v0, t0 = stack[-3]  # type: ignore[misc]
            v1, t1 = stack[-2]  # type: ignore[misc]
            v2, t2 = stack[-1]  # type: ignore[misc]
            r1 = abs(float(v1) - float(v0))
            r2 = abs(float(v2) - float(v1))
            if r2 >= r1:
                period = max(int(t2) - int(t0), 1)
                cpy = PERIODS_PER_YEAR / period
                raw_cycles.append(
                    {
                        "range": r1,
                        "period": period,
                        "cycles_per_year": cpy,
                        "t_start": int(t0),
                        "t_end": int(t2),
                        "tier": _classify_cycles_per_year(cpy),
                    }
                )
                del stack[-2]
            else:
                break

    return raw_cycles


def _count_cycles_by_tier(cycles: list[dict]) -> dict[str, int]:
    """Actual number of rainflow cycles extracted in each period-class this year."""
    counts = {tier: 0 for tier in TIER_ORDER}
    for cyc in cycles:
        tier = cyc.get("tier", "seasonal")
        if tier in counts:
            counts[tier] += 1
    return counts


def _tier_active_from_annual_counts(counts: dict[str, int]) -> dict[str, bool]:
    """
    Annual count gates (user requirement):

      daily_loop  only if complete daily-period cycles  > 730 / year
      intraday    only if complete inter-day cycles     > 365 / year
      weekly      only if complete weekly cycles        > 52  / year
      seasonal    always available as residual

    A single short SOC wiggle must NOT unlock daily just because
    PERIODS_PER_YEAR / period > 730 — that was the bug.
    """
    return {
        "daily_loop": int(counts.get("daily_loop", 0)) > CYCLES_DAILY_MIN,
        "intraday": int(counts.get("intraday", 0)) > CYCLES_INTRADAY_MIN,
        "weekly": int(counts.get("weekly", 0)) > CYCLES_WEEKLY_MIN,
        "seasonal": True,
    }


def _demote_to_active_tier(tier: str, active: dict[str, bool]) -> str:
    """If a period-class fails its annual count gate, fall to the next slower active tier."""
    try:
        start = TIER_ORDER.index(tier)
    except ValueError:
        start = len(TIER_ORDER) - 1
    for j in range(start, len(TIER_ORDER)):
        cand = TIER_ORDER[j]
        if active.get(cand, False):
            return cand
    return "seasonal"


def _period_tiers_from_cycles(n: int, cycles: list[dict], active: dict[str, bool]) -> list[str]:
    """
    Assign each half-hour to a tier using rainflow cycles only.

    Faster tiers win on overlap. Cycles whose period-class fails the annual
    count gate are demoted (e.g. daily→weekly/seasonal).
    """
    tier_at = ["seasonal"] * n
    tier_rank = {tier: i for i, tier in enumerate(TIER_ORDER)}

    for cyc in cycles:
        raw_tier = cyc.get("tier", "seasonal")
        tier = _demote_to_active_tier(str(raw_tier), active)
        t0 = max(int(cyc["t_start"]), 0)
        t1 = min(int(cyc["t_end"]), n - 1)
        for t in range(t0, t1 + 1):
            if tier_rank[tier] < tier_rank[tier_at[t]]:
                tier_at[t] = tier
    return tier_at


def _tier_discharge_from_rainflow(
    excess: np.ndarray,
    deficit: np.ndarray,
) -> tuple[dict[str, np.ndarray], list[dict], np.ndarray]:
    """
    Virtual pool simulation; tier attribution from rainflow on SOC.

    Each rainflow cycle is first classed by its loop period, then **gated by
    the actual annual count** of that class:

      >730 daily-period cycles  → daily_loop may receive discharge
      >365 inter-day cycles     → intraday may receive discharge
      >52  weekly cycles        → weekly may receive discharge

    Otherwise that class contributes 0 MW peak (demoted to slower tiers).
    """
    soc_trace, _charge, discharge = _simulate_virtual_pool(excess, deficit)
    cycles = _rainflow_cycles(soc_trace)
    counts = _count_cycles_by_tier(cycles)
    active = _tier_active_from_annual_counts(counts)
    n = len(discharge)
    tier_at = _period_tiers_from_cycles(n, cycles, active)
    tier_dis_mw = {tier: np.zeros(n) for tier in TIER_ORDER}

    for t in range(n):
        if discharge[t] <= 1e-9:
            continue
        tier = tier_at[t]
        tier_dis_mw[tier][t] += discharge[t] / PERIOD_HOURS

    # Attach diagnostics on cycle list for callers / tests
    for cyc in cycles:
        cyc["annual_count_in_class"] = counts.get(cyc.get("tier", "seasonal"), 0)
        cyc["tier_gate_active"] = bool(active.get(cyc.get("tier", "seasonal"), False))
        cyc["tier_after_gate"] = _demote_to_active_tier(str(cyc.get("tier", "seasonal")), active)

    return tier_dis_mw, cycles, discharge


def rainflow_tier_series(excess: np.ndarray, deficit: np.ndarray) -> dict[str, np.ndarray]:
    """
    Half-hourly discharge power (MW) attributed to each loop-frequency tier.

    Used by ``forecast_storage_cap.py`` to write tier columns in
    ``data/storage_net_demand_profiles/storage_net_demand_profile_YYYY.csv``.
    """
    tier_dis_mw, _, _ = _tier_discharge_from_rainflow(excess, deficit)
    return tier_dis_mw


def rainflow_tier_peaks(excess: np.ndarray, deficit: np.ndarray) -> dict[str, float]:
    """
    Peak discharge **power** (MW) per loop-frequency tier for the year.

    Tier is active only when the **annual count** of rainflow cycles in that
    period-class exceeds the gate (>730 daily / >365 inter-day / >52 weekly).
    Inactive tiers return 0.0 peak.
    """
    tier_dis_mw, cycles, discharge = _tier_discharge_from_rainflow(excess, deficit)
    del cycles, discharge
    peaks = {tier: float(np.max(arr)) if arr.size else 0.0 for tier, arr in tier_dis_mw.items()}
    return peaks


def rainflow_cycle_summary(excess: np.ndarray, deficit: np.ndarray) -> dict[str, int]:
    """Rainflow cycle counts per period-class (before annual count gate)."""
    _series, cycles, _ = _tier_discharge_from_rainflow(excess, deficit)
    return _count_cycles_by_tier(cycles)


def decompose_tier_series(excess: np.ndarray, deficit: np.ndarray) -> dict[str, np.ndarray]:
    """Alias for ``rainflow_tier_series`` (legacy callers)."""
    return rainflow_tier_series(excess, deficit)


def decompose_tier_peaks(excess: np.ndarray, deficit: np.ndarray) -> dict[str, float]:
    """Alias for ``rainflow_tier_peaks`` (legacy callers)."""
    return rainflow_tier_peaks(excess, deficit)


def power_mw_from_pool(pool_limit_mw: float, battery_key: str) -> float:
    """pool_limit is stored as MW power; energy MWh = power * duration."""
    return float(pool_limit_mw)


def energy_mwh_from_power(power_mw: float, battery_key: str) -> float:
    return power_mw * BATTERY_DURATION_H.get(battery_key, 2.0)


def per_period_limit_mwh(power_mw: float, battery_key: str) -> float:
    """Max MWh charge/discharge in one half-hour period at nominal C-rate."""
    periods = DISCHARGE_PERIODS.get(battery_key, 4)
    if periods <= 0:
        return power_mw * PERIOD_HOURS
    return energy_mwh_from_power(power_mw, battery_key) / periods


def sync_battery_pool_limits(battery_objects: Mapping, battery_key: str) -> None:
    """Align per_pool_limit with C-rate: 0.25C => 8 periods to empty."""
    asset = battery_objects.get(battery_key)
    if asset is None:
        return
    power_mw = float(getattr(asset, "pool_limit", 0.0) or 0.0)
    asset.per_pool_limit = per_period_limit_mwh(power_mw, battery_key)


def sync_all_expandable_pool_limits(battery_objects: Mapping) -> None:
    for key in EXPANDABLE_STORAGE_KEYS:
        sync_battery_pool_limits(battery_objects, key)


def build_cap_row_from_batteries(battery_objects: Mapping) -> dict[str, float]:
    row: dict[str, float] = {}
    mapping = {
        "pumpedhydro_battery": "pumpedhydro_battery_Capacity_MW",
        "1c_battery": "1c_battery_Capacity_MW",
        "0.25c_battery": "0.25c_battery_Capacity_MW",
        "0.5c_battery": "0.5c_battery_Capacity_MW",
        "hydrogen_battery": "hydrogen_battery_Capacity_MW",
    }
    for key, col in mapping.items():
        if key in battery_objects:
            row[col] = float(battery_objects[key].pool_limit)
    return row


def existing_storage_mw(cap_row: dict | None) -> float:
    """Total existing storage power MW (all techs + pumped hydro), pooled."""
    if not cap_row:
        return 0.0
    cols = (
        "pumpedhydro_battery_Capacity_MW",
        "1c_battery_Capacity_MW",
        "0.25c_battery_Capacity_MW",
        "0.5c_battery_Capacity_MW",
        "hydrogen_battery_Capacity_MW",
    )
    return sum(float(cap_row.get(c, 0) or 0) for c in cols)


def existing_mw_for_battery(battery_key: str, cap_row: dict | None) -> float:
    """Existing MW for one expandable storage technology (legacy per-tech credit)."""
    if not cap_row:
        return 0.0
    col = BATTERY_CAP_COLUMNS.get(battery_key)
    if col is None:
        return 0.0
    return float(cap_row.get(col, 0) or 0)


def allocate_existing(existing_mw: float, gross: dict[str, float]) -> dict[str, float]:
    """Credit existing MW against tiers from fastest loop to slowest.

    Order: daily_loop → intraday → weekly → seasonal.
    """
    remaining = existing_mw
    net: dict[str, float] = {}
    for key in TIER_ORDER:
        g = gross[key]
        used = min(remaining, g)
        net[key] = max(g - used, 0.0)
        remaining = max(remaining - g, 0.0)
    return net


def residual_deficit_after_existing_storage(
    excess: np.ndarray,
    gross_deficit: np.ndarray,
    existing_mw: float,
    *,
    duration_h: float | None = None,
    rte: float = RTE,
) -> np.ndarray:
    """Approximate post-dispatch residual deficit with a finite aggregate storage pool.

    Used offline when CEM half-hourly storage discharge is unavailable.
    Existing fleet is modelled as one pool with power=existing_mw and
    energy=existing_mw×duration_h (default 4 h).
    """
    excess = np.asarray(excess, dtype=float)
    gross_deficit = np.asarray(gross_deficit, dtype=float)
    n = len(gross_deficit)
    if existing_mw <= 0:
        return gross_deficit.copy()

    dur = EXISTING_STORAGE_DURATION_H if duration_h is None else float(duration_h)
    energy_cap = existing_mw * dur
    power = float(existing_mw)
    soc = 0.0
    residual = np.zeros(n, dtype=float)

    for t in range(n):
        exc = max(float(excess[t]), 0.0)
        dfc = max(float(gross_deficit[t]), 0.0)

        if exc > 1e-9 and soc < energy_cap - 1e-9:
            ch = min(exc, power, (energy_cap - soc) / max(rte, 1e-9))
            soc += ch * rte

        if dfc > 1e-9 and soc > 1e-9:
            dis = min(dfc, power, soc)
            soc -= dis
            residual[t] = dfc - dis
        else:
            residual[t] = dfc

    return residual


def resolve_credit_mode(credit_mode: str | None = None) -> str:
    mode = (credit_mode or CREDIT_MODE or "scheme_c").strip().lower()
    if mode in ("scheme_c", "sim_trace", "c", "from_simulation"):
        return "scheme_c"
    if mode in ("post_dispatch", "post-storage", "after_storage", "residual"):
        return "post_dispatch"
    if mode in ("pooled_existing_mw", "pooled", "pooled_mw", "total_existing"):
        return "pooled_existing_mw"
    raise ValueError(
        f"Unknown STORAGE_CAP_CREDIT_MODE={mode!r}; "
        "use 'scheme_c', 'post_dispatch', or 'pooled_existing_mw'"
    )


def scheme_c_net_demand_from_traces(
    demand: np.ndarray,
    vre_generation: np.ndarray,
    storage_discharge: np.ndarray,
) -> np.ndarray:
    """Residual flexibility need after observed storage discharge into the VRE gap.

    gross_gap = max(demand − VRE, 0)
    net       = max(gross_gap − discharge, 0)

    Discharge is credited only against the VRE gap (not against thermal replacement).
    """
    demand = np.asarray(demand, dtype=float)
    vre = np.asarray(vre_generation, dtype=float)
    dis = np.asarray(storage_discharge, dtype=float)
    n = len(demand)
    if len(vre) < n:
        vre = np.pad(vre, (0, n - len(vre)))
    if len(dis) < n:
        dis = np.pad(dis, (0, n - len(dis)))
    gross_gap = np.maximum(demand[:n] - vre[:n], 0.0)
    return np.maximum(gross_gap - dis[:n], 0.0)


def scheme_c_excess_from_traces(
    vre_generation: np.ndarray,
    demand: np.ndarray,
    *,
    leftover_excess: np.ndarray | None = None,
    store_charge: np.ndarray | None = None,
) -> np.ndarray:
    """Charge available to *new* storage after existing fleet has already charged.

    Prefer CEM leftover excess (results[22]). Else reconstruct:
    max(VRE − demand, 0) − store_charge.
    """
    vre = np.asarray(vre_generation, dtype=float)
    demand = np.asarray(demand, dtype=float)
    n = min(len(vre), len(demand))
    if leftover_excess is not None:
        ex = np.maximum(np.asarray(leftover_excess, dtype=float), 0.0)
        if len(ex) < n:
            ex = np.pad(ex, (0, n - len(ex)))
        return ex[:n]
    gross_excess = np.maximum(vre[:n] - demand[:n], 0.0)
    if store_charge is None:
        return gross_excess
    ch = np.asarray(store_charge, dtype=float)
    if len(ch) < n:
        ch = np.pad(ch, (0, n - len(ch)))
    return np.maximum(gross_excess - ch[:n], 0.0)


def load_storage_discharge_from_generation_trace(
    sqlite_path: str | Path,
    year: int,
    n_periods: int = PERIODS_PER_YEAR,
    *,
    use_mw_equivalent: bool = False,
    battery_names: tuple[str, ...] = SIM_BATTERY_TRACE_NAMES,
) -> np.ndarray:
    """Half-hourly storage discharge from CEM generation_trace.sqlite.

    Default uses ``generation_mwh`` (same numeric convention as VRE MWh profiles
    in the offline forecast). Set ``use_mw_equivalent=True`` for MW-equivalent.
    """
    import sqlite3
    from pathlib import Path as _Path

    path = _Path(sqlite_path)
    if not path.exists():
        raise FileNotFoundError(path)

    col = "dispatch_mw_equivalent" if use_mw_equivalent else "generation_mwh"
    placeholders = ",".join("?" for _ in battery_names)
    sql = f"""
        SELECT period, SUM({col}) AS discharge
        FROM generation_by_period
        WHERE year = ? AND asset_name IN ({placeholders})
        GROUP BY period
        ORDER BY period
    """
    out = np.zeros(n_periods, dtype=float)
    with sqlite3.connect(path) as conn:
        rows = conn.execute(sql, (int(year), *battery_names)).fetchall()
    for period, discharge in rows:
        p = int(period)
        if 0 <= p < n_periods:
            out[p] = float(discharge or 0.0)
    return out


def _battery_params(battery_key: str) -> dict:
    return config.batteries[battery_key]


def _capital_cost(battery_key: str, capacity_mw: float) -> float:
    cost_per_mw = config.capital_costs_per_mw.get(battery_key, 350_000)
    return capacity_mw * cost_per_mw


def simulate_tier_arbitrage_profit(
    tier_signal: np.ndarray,
    excess: np.ndarray,
    prices: np.ndarray,
    battery_key: str,
    capacity_mw: float,
) -> float:
    """Annual arbitrage profit: zero-cost excess charging, discharge at cleared price - storage cost."""
    if capacity_mw <= 0:
        return 0.0

    params = _battery_params(battery_key)
    n1 = float(params["n_1"])
    n2 = float(params["n_2"])
    sf = float(params["storage_fee"])
    psf = float(params["per_storage_fee"])
    energy_mwh = energy_mwh_from_power(capacity_mw, battery_key)
    max_period_mwh = per_period_limit_mwh(capacity_mw, battery_key)

    soc = 0.0
    profit = 0.0
    n = min(len(tier_signal), len(excess), len(prices))

    for t in range(n):
        price = float(prices[t])
        dfc = max(float(tier_signal[t]), 0.0)
        exc = max(float(excess[t]), 0.0)

        if exc > 0 and soc < energy_mwh - 1e-9:
            ch = min(exc, max_period_mwh, (energy_mwh - soc) / max(n1, 1e-9))
            soc += ch * n1

        if dfc > 0 and soc > 1e-9:
            dis = min(dfc, max_period_mwh, soc)
            dwell = max(BATTERY_DURATION_H.get(battery_key, 2.0) * PERIODS_PER_DAY / max(DISCHARGE_PERIODS.get(battery_key, 4), 1), 1.0)
            storage_cost = sf + psf * dwell
            margin = price - storage_cost
            if margin > 0:
                profit += (dis / max(n2, 1e-9)) * margin
            soc -= dis

    return profit


def tier_roi(
    tier_signal: np.ndarray,
    excess: np.ndarray,
    prices: np.ndarray,
    battery_key: str,
    tier_mw: float,
) -> float:
    if tier_mw <= 0:
        return 0.0
    profit = simulate_tier_arbitrage_profit(tier_signal, excess, prices, battery_key, tier_mw)
    capex = _capital_cost(battery_key, tier_mw)
    return profit / capex if capex > 0 else 0.0


def preferred_rate_for_tech(battery_key: str, fallback: float = 0.08) -> float:
    return TECH_PREFERRED_RATE.get(battery_key, fallback)


def build_deficit_for_cap(
    vre_generation: np.ndarray,
    demand: np.ndarray,
    *,
    excess_generation: np.ndarray | None = None,
    storage_net_demand: np.ndarray | None = None,
    storage_discharge: np.ndarray | None = None,
    store_charge: np.ndarray | None = None,
    cap_row: dict | None = None,
    credit_mode: str | None = None,
) -> tuple[np.ndarray, np.ndarray, str]:
    """Return (excess, deficit, mode) used for rainflow tier peaks.

    scheme_c
      Requires observed storage_discharge (or precomputed storage_net_demand).
      excess = leftover after existing charge (excess_generation / store_charge).
    post_dispatch
      Same residual when discharge given; else finite-pool approximation (legacy).
    pooled_existing_mw
      deficit = max(demand−VRE, 0); existing MW credited later on tier peaks.
    """
    vre = np.asarray(vre_generation, dtype=float)
    demand = np.asarray(demand, dtype=float)
    mode = resolve_credit_mode(credit_mode)

    if mode == "scheme_c":
        if storage_net_demand is not None:
            deficit = np.maximum(np.asarray(storage_net_demand, dtype=float), 0.0)
        elif storage_discharge is not None:
            deficit = scheme_c_net_demand_from_traces(demand, vre, storage_discharge)
        else:
            raise ValueError(
                "scheme_c requires storage_discharge or storage_net_demand from "
                "run_simulation / generation_trace.sqlite — do not invent a forecast pool"
            )
        excess = scheme_c_excess_from_traces(
            vre,
            demand,
            leftover_excess=excess_generation,
            store_charge=store_charge,
        )
        return excess, deficit, mode

    if excess_generation is not None:
        excess = np.maximum(np.asarray(excess_generation, dtype=float), 0.0)
    else:
        excess = np.maximum(vre - demand, 0.0)

    if mode == "post_dispatch":
        if storage_net_demand is not None:
            deficit = np.maximum(np.asarray(storage_net_demand, dtype=float), 0.0)
        elif storage_discharge is not None:
            deficit = scheme_c_net_demand_from_traces(demand, vre, storage_discharge)
        else:
            gross = np.maximum(demand - vre, 0.0)
            deficit = residual_deficit_after_existing_storage(
                excess, gross, existing_storage_mw(cap_row)
            )
    else:
        deficit = np.maximum(demand - vre, 0.0)

    return excess, deficit, mode


def calculate_storage_expansion_limits_from_profiles(
    vre_generation: np.ndarray,
    demand: np.ndarray,
    prices: np.ndarray | None = None,
    cap_row: dict | None = None,
    preferred_rate: float = 0.08,
    agent_rois: dict[str, float] | None = None,
    preferred_rates: dict[str, float] | None = None,
    excess_generation: np.ndarray | None = None,
    storage_net_demand: np.ndarray | None = None,
    storage_discharge: np.ndarray | None = None,
    store_charge: np.ndarray | None = None,
    credit_mode: str | None = None,
) -> dict[str, float]:
    """
    Aligned utilisation spectrum → Invest_High expansion cap (MW).

    Power batteries (0.25C / 0.5C / 1C):
      spectrum from virtual pool on (excess, net_demand)
      power_room = daily_MW + interday_MW   # bands with aligned hours >365
      pooled:     cap = 0.20 × max(0, power_room − existing)
      scheme_c:   cap = 0.20 × power_room   # residual already post-existing
    """
    del prices, preferred_rate, agent_rois, preferred_rates

    excess, deficit, mode = build_deficit_for_cap(
        vre_generation,
        demand,
        excess_generation=excess_generation,
        storage_net_demand=storage_net_demand,
        storage_discharge=storage_discharge,
        store_charge=store_charge,
        cap_row=cap_row,
        credit_mode=credit_mode,
    )
    excess_mwh = _series_to_period_mwh(
        excess,
        storage_discharge=storage_discharge,
        storage_net_demand=storage_net_demand,
    )
    deficit_mwh = _series_to_period_mwh(
        deficit,
        storage_discharge=storage_discharge,
        storage_net_demand=storage_net_demand,
    )
    spec = aligned_utilisation_spectrum(excess_mwh, deficit_mwh)
    daily = float(spec["daily_loop"])
    interday = float(spec["intraday"])
    seasonal = float(spec["seasonal"])
    existing = existing_storage_mw(cap_row)

    if mode == "pooled_existing_mw":
        power_room = max(0.0, daily + interday - existing)
    else:
        # scheme_c / post_dispatch: pool already sees residual after existing
        power_room = max(0.0, daily + interday)
    power_cap = CAP_FRACTION * power_room

    limits: dict[str, float] = {}
    for battery_key in ("0.25c_battery", "0.5c_battery", "1c_battery"):
        if battery_key in config.batteries:
            limits[battery_key] = power_cap

    if "hydrogen_battery" in config.batteries:
        if mode == "pooled_existing_mw":
            leftover_existing = max(0.0, existing - daily - interday)
            limits["hydrogen_battery"] = CAP_FRACTION * max(
                0.0, seasonal - leftover_existing
            )
        else:
            limits["hydrogen_battery"] = CAP_FRACTION * seasonal

    return limits


def split_capacity_by_template_weights(
    capacity_mw: float,
    keys: tuple[str, ...] = EXPANDABLE_STORAGE_KEYS,
) -> dict[str, float]:
    """Proportional split using config template pool_limit as technology weights."""
    weights = {}
    for k in keys:
        if k in config.batteries:
            weights[k] = max(float(config.batteries[k].get("pool_limit", 0) or 0), 1.0)
    total = sum(weights.values())
    if total <= 0:
        eq = 1.0 / len(keys) if keys else 0.0
        return {k: capacity_mw * eq for k in keys}
    return {k: capacity_mw * weights[k] / total for k in keys}
