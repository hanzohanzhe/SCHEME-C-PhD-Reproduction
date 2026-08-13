# run_investment_analysis.py

import hashlib
import os
import pandas as pd
import numpy as np
import random
import config
from pathlib import Path
from simulation_model import run_simulation, GasGenerator, BiomassGenerator, WaterGenerator, NuclearGenerator, ExpensiverenewableGenerator, Connection, Electrolyzer, Battery, IterLimit, IterLimit_new, acm_solar, acm_energy
from datetime import datetime
from dateutil.relativedelta import relativedelta

PHYSICAL_PERIOD_HOURS = float(os.getenv("PHYSICAL_PERIOD_HOURS", "0.5"))


def _stable_int_hash(text: str) -> int:
    """Process-independent digest (Python's hash() is salted per process)."""
    digest = hashlib.md5(str(text).encode("utf-8")).hexdigest()
    return int(digest[:16], 16)

_STORAGE_EXPANSION_DIR = os.getenv(
    "STORAGE_EXPANSION_MODULE_DIR",
    str(Path.home() / "Desktop" / "storage_expansion_corrected_caps"),
)


def _import_storage_expansion_modules():
    import sys
    from pathlib import Path as _Path

    mod_dir = _Path(_STORAGE_EXPANSION_DIR)
    if mod_dir.is_dir() and str(mod_dir) not in sys.path:
        sys.path.insert(0, str(mod_dir))
    import storage_expansion_cap as sec
    import apply_storage_expansion as ase

    return sec, ase


def get_asset_type_from_repd(repd_tech_type):
    """Maps REPD technology types to internal asset types."""
    if 'Onshore' in repd_tech_type: return 'onshore'
    if 'Offshore' in repd_tech_type: return 'offshore'
    if 'Solar' in repd_tech_type: return 'solar'
    if 'Battery' in repd_tech_type: return 'battery'
    # Pumped storage in REPD is excluded; pumped hydro follows the exogenous plan only.
    if 'Pumped Storage' in repd_tech_type: return None
    if 'Gas' in repd_tech_type: return 'gas'
    return None


ELECTROCHEMICAL_BATTERY_KEYS = ('1c_battery', '0.5c_battery', '0.25c_battery', 'hydrogen_battery')


def apply_electrochemical_battery_expansion(
    battery_objects,
    capacity_to_add,
    current_year,
    investment_summary,
    source,
    assignment_method='Proportional four-tech storage split',
):
    """Add REPD/model capacity to 0.25c / 0.5c / 1c / hydrogen (never pumped hydro)."""
    _, ase = _import_storage_expansion_modules()
    ase.apply_expandable_storage_expansion(
        battery_objects,
        capacity_to_add,
        current_year,
        investment_summary,
        source,
        assignment_method=assignment_method,
        )


def load_regional_technology_success_rates():
    """
    Load regional technology success rates from CSV file.
    
    Returns:
    - dict: Technology success rates by technology and region
    """
    try:
        df_success_rates = pd.read_csv('regional_technology_success_rates.csv')
        
        # Create a nested dictionary for easy lookup
        # Structure: success_rates[technology][region] = success_rate
        success_rates = {}
        
        for _, row in df_success_rates.iterrows():
            technology = row['Technology']
            region = row['Region'].strip()  # Remove any leading/trailing spaces
            success_rate = row['Success_Rate']
            
            if technology not in success_rates:
                success_rates[technology] = {}
            
            success_rates[technology][region] = success_rate
        
        print(f"Loaded success rates for {len(success_rates)} technologies across {sum(len(regions) for regions in success_rates.values())} technology-region combinations")
        
        return success_rates
        
    except FileNotFoundError:
        print("Warning: regional_technology_success_rates.csv not found. Using default success rates.")
        return {}
    except Exception as e:
        print(f"Warning: Error loading success rates: {e}. Using default success rates.")
        return {}


def region_to_generator_name(region, tech_type):
    """
    Map REPD Region to generator name for solar/onshore. Used when project has no lat/lon.
    Returns (e.g. 'solar_Nottingham') or None if no mapping.
    """
    if tech_type not in ('solar', 'onshore'):
        return None
    if pd.isna(region):
        region = ''
    region = str(region or '').strip()
    region_to_city = {
        'East Midlands': 'Nottingham',
        'Eastern': 'Ipswich',
        'London': 'London',
        'North East': 'Newcastle',
        'North West': 'Manchester',
        'Scotland': 'Edinburgh',
        'South East': 'Portsmouth',
        'South West': 'Bournemouth',
        'Wales': 'Cardiff',
        'West Midlands': 'Birmingham',
        'Yorkshire and Humber': 'Sheffield',
    }
    city = region_to_city.get(region)
    if city:
        return f"{tech_type}_{city}"
    return None


def _repd_numeric_capacity(row):
    return pd.to_numeric(str(row.get('Installed Capacity (MWelec)', '')).replace(',', ''), errors='coerce')


def _repd_operational_year(row):
    op_date = pd.to_datetime(row.get('Operational'), errors='coerce', dayfirst=True)
    if pd.isna(op_date):
        return None
    return int(op_date.year)


def _extract_repd_wgs84(row):
    from map_projects_to_generators_by_location import extract_location_from_repd

    lat, lon = extract_location_from_repd(row)
    if lat is not None and lon is not None:
        return lat, lon

    x = pd.to_numeric(row.get('X-coordinate'), errors='coerce')
    y = pd.to_numeric(row.get('Y-coordinate'), errors='coerce')
    if pd.isna(x) or pd.isna(y):
        return None, None

    try:
        from pyproj import Transformer
        transformer = Transformer.from_crs("EPSG:27700", "EPSG:4326", always_xy=True)
        lon, lat = transformer.transform(float(x), float(y))
        return lat, lon
    except Exception:
        return None, None


def build_repd_operational_snapshot(snapshot_year=2015, repd_file='repd-q2-jul-2025.csv'):
    """Build generator-level operational capacity snapshot from REPD Operational dates."""
    try:
        df = pd.read_csv(repd_file, encoding='utf-8')
    except UnicodeDecodeError:
        df = pd.read_csv(repd_file, encoding='latin1')

    capacities = {name: 0.0 for name in config.generators}
    battery_mw = 0.0

    # Lightweight generator-object substitute for nearest-location mapping.
    class _Dummy:
        def __init__(self, name):
            self.name = name

    generator_stubs = {name: _Dummy(name) for name in config.generators}

    from map_projects_to_generators_by_location import find_nearest_generator

    for _, row in df.iterrows():
        if row.get('Development Status (short)') != 'Operational':
            continue
        op_year = _repd_operational_year(row)
        if op_year is None or op_year > snapshot_year:
            continue

        tech_type = get_asset_type_from_repd(row.get('Technology Type', ''))
        if tech_type not in {'solar', 'onshore', 'offshore', 'battery'}:
            continue

        capacity = _repd_numeric_capacity(row)
        if pd.isna(capacity) or capacity <= 0:
            continue

        if tech_type == 'battery':
            battery_mw += float(capacity)
            continue

        assigned = region_to_generator_name(row.get('Region'), tech_type)
        if assigned is None:
            lat, lon = _extract_repd_wgs84(row)
            if lat is not None and lon is not None:
                assigned, _ = find_nearest_generator(lat, lon, tech_type, generator_stubs)

        if assigned in capacities:
            capacities[assigned] += float(capacity)

    return capacities, battery_mw


def apply_validation_initial_capacity_snapshot(
    generator_objects,
    battery_objects,
    snapshot_year=2015,
    repd_file='repd-q2-jul-2025.csv',
):
    """Reset VRE and electrochemical BESS to a historical REPD operational snapshot."""
    capacities, battery_mw = build_repd_operational_snapshot(snapshot_year, repd_file)
    for name, asset in generator_objects.items():
        asset_type = get_asset_type(name)
        if asset_type in {'solar', 'onshore', 'offshore'} and hasattr(asset, 'capacity_multiplier'):
            base_unit = 20 if asset_type in {'onshore', 'offshore'} else 1
            capacity_mw = capacities.get(name, 0.0)
            asset.capacity_multiplier = capacity_mw / base_unit
            asset.capital_cost = capacity_mw * config.capital_costs_per_mw.get(asset_type, 0)

    # Split REPD battery MW across four expandable storage agents (loop-frequency methodology).
    _, ase = _import_storage_expansion_modules()
    ase.apply_repd_battery_stock_split(battery_objects, battery_mw)

    totals = {}
    for name, asset in generator_objects.items():
        asset_type = get_asset_type(name)
        if asset_type in {'solar', 'onshore', 'offshore'} and hasattr(asset, 'capacity_multiplier'):
            base_unit = 20 if asset_type in {'onshore', 'offshore'} else 1
            totals[asset_type] = totals.get(asset_type, 0.0) + asset.capacity_multiplier * base_unit
    print(
        f"--- REPD operational stock snapshot {snapshot_year}: "
        f"solar={totals.get('solar', 0):.2f} MW, "
        f"onshore={totals.get('onshore', 0):.2f} MW, "
        f"offshore={totals.get('offshore', 0):.2f} MW, "
        f"battery={battery_mw:.2f} MW ---"
    )


def apply_forward_repd_initial_stock_if_enabled(
    generator_objects,
    battery_objects,
    *,
    start_year: int | None = None,
    repd_file: str = "repd-q2-jul-2025.csv",
) -> bool:
    """Seed forward CEM runs from REPD operational stock at START_YEAR (smoke-test parity)."""
    if os.getenv("VALIDATION_MODE", "").strip().lower() in {"1", "true", "yes"}:
        return False
    flag = os.getenv("APPLY_REPD_INITIAL_SNAPSHOT", "1").strip().lower()
    if flag in {"0", "false", "no"}:
        return False
    snapshot_year = int(
        os.getenv("FORWARD_INITIAL_CAPACITY_YEAR", str(start_year or os.getenv("START_YEAR", "2025")))
    )
    apply_validation_initial_capacity_snapshot(
        generator_objects,
        battery_objects,
        snapshot_year=snapshot_year,
        repd_file=repd_file,
    )
    return True


def exclude_external_projects_already_in_stock(
    project_pipeline: list,
    *,
    snapshot_year: int | None = None,
) -> tuple[list, int]:
    """Drop external projects already represented in the operational stock snapshot."""
    snapshot_year = int(snapshot_year or os.getenv("START_YEAR", "2025"))
    kept: list = []
    removed = 0
    for project in project_pipeline:
        if project.get("source") != "external":
            kept.append(project)
            continue
        if project.get("development_status") == "Operational":
            removed += 1
            continue
        if project.get("completion_year_clipped"):
            removed += 1
            continue
        completion_year = project.get("completion_year")
        if completion_year is not None and int(completion_year) < snapshot_year:
            removed += 1
            continue
        kept.append(project)
    return kept, removed


def defer_start_year_external_pipeline_completions(
    project_pipeline: list,
    *,
    start_year: int | None = None,
) -> tuple[list, int]:
    """When REPD operational stock seeds START_YEAR, pipeline builds begin in START_YEAR+1.

    First-year investment ROI is calibrated on the operational snapshot (~10 GW solar).
    External projects scheduled to complete in START_YEAR are deferred so they do not
    inflate capacity before the year-1 simulation and investment analysis.

    Deferred projects are spread over PIPELINE_DEFER_SPREAD_YEARS (default 3) so
    near-completion REPD entries (especially BESS) do not dump in a single year.
    """
    if os.getenv("APPLY_REPD_INITIAL_SNAPSHOT", "1").strip().lower() in {"0", "false", "no"}:
        return project_pipeline, 0
    start_year = int(start_year or os.getenv("START_YEAR", "2025"))
    spread_years = max(1, int(os.getenv("PIPELINE_DEFER_SPREAD_YEARS", "3")))
    deferred = 0
    out: list = []
    for project in project_pipeline:
        if (
            project.get("source") == "external"
            and project.get("completion_year") is not None
            and int(project["completion_year"]) == start_year
        ):
            updated = dict(project)
            offset = 1 + (_stable_int_hash(str(project.get("name", ""))) % spread_years)
            updated["completion_year"] = start_year + offset
            updated["deferred_from_start_year"] = True
            deferred += 1
            out.append(updated)
        else:
            out.append(project)
    return out, deferred


def get_asset_region(asset_name):
    """
    Determine the region for a given asset based on its name or location.
    This function maps asset names to UK regions for success rate lookup.
    
    Args:
    - asset_name (str): Name of the asset
    
    Returns:
    - str: Region name matching the success rates CSV
    """
    # Map asset names to regions based on location indicators
    region_mappings = {
        # Solar assets by location
        'solar_Nottingham': 'East Midlands',
        'solar_Ipswich': 'Eastern', 
        'solar_London': 'London',
        'solar_Newcastle': 'North East',
        'solar_Manchester': 'North West',
        'solar_Edinburgh': 'Scotland',
        'solar_Portsmouth': 'South East',
        'solar_Bournemouth': 'South West',
        'solar_Cardiff': 'Wales',
        'solar_Birmingham': 'West Midlands',
        'solar_Sheffield': 'Yorkshire and Humber',
        
        # Onshore wind assets by location
        'onshore_Nottingham': 'East Midlands',
        'onshore_Ipswich': 'Eastern',
        'onshore_London': 'London',
        'onshore_Newcastle': 'North East',
        'onshore_Manchester': 'North West',
        'onshore_Edinburgh': 'Scotland',
        'onshore_Portsmouth': 'South East',
        'onshore_Bournemouth': 'South West',
        'onshore_Cardiff': 'Wales',
        'onshore_Birmingham': 'West Midlands',
        'onshore_Sheffield': 'Yorkshire and Humber',
        
        # Default regions for other assets
        'CCGT': 'England',  # Gas plants distributed
        'OCGT': 'England',
        'bio_and_waste': 'England',
        'Nuclear': 'England',
        'electrolyzer': 'England',
    }
    
    # Check for direct mapping first
    if asset_name in region_mappings:
        return region_mappings[asset_name]
    
    # For offshore wind, use "All Offshore" region
    if 'offshore' in asset_name.lower():
        return 'All Offshore'
    
    # For battery storage, default to a representative region
    if 'battery' in asset_name.lower():
        return 'England'  # Use average across England regions
    
    # Default fallback
    return 'England'


def apply_success_rates_to_model_investments(project_pipeline, success_rates):
    """
    Apply regional technology success rates to model investment projects.
    
    Args:
    - project_pipeline (list): List of project dictionaries
    - success_rates (dict): Technology success rates by technology and region
    
    Returns:
    - list: Updated project pipeline with success rates and success determinations
    """
    updated_pipeline = []
    
    # Set random seed for reproducible results
    random.seed(42)
    
    for project in project_pipeline:
        # Create a copy of the project to avoid modifying the original
        updated_project = project.copy()
        
        # Only apply success rates to model investments
        if project.get('source') in ['model', 'model_electrolyzer']:
            tech_type = project.get('technology_type', '')
            success_tech = _tech_label_for_success_rate(tech_type)

            asset_name = project.get('target_asset_name') or project.get('name', '')
            if 'Model Investment:' in asset_name or 'Model Decision:' in asset_name:
                asset_name = asset_name.replace('Model Investment: ', '').replace('Model Decision: ', '').split()[0]
            
            region = get_asset_region(asset_name)
            success_rate = _lookup_regional_success_rate(success_rates, success_tech, region)

            original_capacity = float(
                project.get('original_capacity', project.get('capacity', 0)) or 0
            )
            final_capacity, project_succeeds, random_draw, status = _resolve_model_success_capacity(
                original_capacity,
                success_rate,
                project_key=project.get("name", "unknown"),
                region=region,
                success_tech=success_tech,
            )

            updated_project.update({
                'success_rate': success_rate,
                'success_technology': success_tech,
                'success_region': region,
                'project_succeeds': project_succeeds,
                'success_rate_applied': True,
                'success_mode': _model_success_mode(),
                'original_capacity': original_capacity,
                'capacity': final_capacity,
                'status': status,
            })
            if random_draw is not None:
                updated_project['random_draw'] = random_draw
            else:
                updated_project.pop('random_draw', None)
            
        else:
            # For external projects, mark as not having success rates applied
            updated_project['success_rate_applied'] = False
        
        updated_pipeline.append(updated_project)
    
    return updated_pipeline


def _planning_use_median() -> bool:
    return os.getenv("PLANNING_USE_MEDIAN", "1").strip().lower() in {"1", "true", "yes"}


def _map_repd_tech_type(tech_type) -> str:
    if tech_type in {"solar", "onshore", "offshore", "battery"}:
        return tech_type
    tech_mapping = {
        "Solar Photovoltaics": "solar",
        "Wind Onshore": "onshore",
        "Wind Offshore": "offshore",
        "Battery": "battery",
    }
    mapped = tech_mapping.get(str(tech_type), "solar")
    if mapped in {"1c_battery", "0.5c_battery", "0.25c_battery"}:
        return "battery"
    return mapped


def _timeline_months_for_type(mapped_tech: str, timeline_type: str, *, use_median: bool) -> float:
    stage_timelines = config.development_stage_timelines.get(
        mapped_tech, config.development_stage_timelines["solar"]
    )
    suffix = "median" if use_median else "mean"

    if timeline_type in {f"total_{suffix}", "total_mean", "total_median"}:
        key = f"total_{suffix}"
        return float(stage_timelines.get(key, stage_timelines["total_median"]))
    if timeline_type in {f"pre_construction_{suffix}", "pre_construction_mean", "pre_construction_median"}:
        return float(stage_timelines[f"pre_construction_{suffix}"]) + float(
            stage_timelines[f"construction_{suffix}"]
        )
    if timeline_type in {f"construction_{suffix}", "construction_mean", "construction_median"}:
        return float(stage_timelines[f"construction_{suffix}"])
    if timeline_type in {
        f"planning_consenting_{suffix}",
        "planning_consenting_mean",
        "planning_consenting_median",
    }:
        return float(stage_timelines[f"planning_consenting_{suffix}"])
    return float(stage_timelines[f"total_{suffix}"])


def completion_year_from_months(base_year: int, timeline_months: float, project_key: str = "") -> int:
    """Calendar completion year from months after 1 Jan of base_year, with per-project dispersion."""
    jitter = 0
    if project_key:
        jitter = (_stable_int_hash(project_key) % 13) - 6
    total_months = max(1.0, float(timeline_months) + jitter)
    completion = datetime(base_year, 1, 1) + relativedelta(months=int(round(total_months)))
    return int(completion.year)


def deterministic_success_draw(project_key: str, region: str, tech: str) -> float:
    raw = f"{project_key}|{region}|{tech}"
    return (_stable_int_hash(raw) % 1_000_000) / 1_000_000.0


def _model_success_mode() -> str:
    """lottery: binary pass/fail; expected: capacity * success_rate (mean expansion)."""
    mode = os.getenv("MODEL_SUCCESS_MODE", "expected").strip().lower()
    if mode in {"lottery", "draw", "binary"}:
        return "lottery"
    if mode in {"expected", "expectation", "mean"}:
        return "expected"
    return "expected"


def _lookup_regional_success_rate(success_rates: dict, success_tech: str, region: str) -> float:
    if success_tech in success_rates and region in success_rates[success_tech]:
        return float(success_rates[success_tech][region])
    if success_tech in success_rates:
        rates = list(success_rates[success_tech].values())
        return sum(rates) / len(rates) if rates else 0.75
    return 0.75


def _tech_label_for_success_rate(technology_type: str) -> str:
    mapping = {
        "solar": "Solar Photovoltaics",
        "onshore": "Wind Onshore",
        "offshore": "Wind Offshore",
        "battery": "Battery",
        "1c_battery": "Battery",
        "0.5c_battery": "Battery",
        "0.25c_battery": "Battery",
        "electrolyzer": "Battery",
        "electrolyzer_attached": "Battery",
        "gas": "Wind Onshore",
        "CCGT": "Wind Onshore",
        "OCGT": "Wind Onshore",
        "bio_and_waste": "Wind Onshore",
    }
    return mapping.get(technology_type, "Solar Photovoltaics")


def _resolve_model_success_capacity(
    original_capacity: float,
    success_rate: float,
    *,
    project_key: str,
    region: str,
    success_tech: str,
) -> tuple[float, bool, float | None, str]:
    """Return (final_capacity, project_succeeds, random_draw_or_none, status)."""
    original_capacity = float(original_capacity)
    success_rate = float(success_rate)
    if _model_success_mode() == "expected":
        final_capacity = original_capacity * success_rate
        succeeds = final_capacity > 1e-6
        status = "active" if succeeds else "zero_expected_capacity"
        return final_capacity, succeeds, None, status

    random_draw = deterministic_success_draw(project_key, region, success_tech)
    project_succeeds = random_draw <= success_rate
    final_capacity = original_capacity if project_succeeds else 0.0
    status = "active" if project_succeeds else "failed_due_to_success_rate"
    return final_capacity, project_succeeds, random_draw, status


def _repd_model_status_for_asset(asset_type: str) -> str:
    if asset_type in {"solar", "onshore", "offshore", "battery", "1c_battery", "0.5c_battery", "0.25c_battery"}:
        return "Application Submitted"
    return "Application Submitted"


def _repd_tech_label_for_asset(asset_type: str) -> str:
    return _tech_label_for_success_rate(asset_type)


def calculate_development_timeline(tech_type, development_status, base_year=2025, project_key=""):
    """
    Estimate completion year from REPD status and Table 13 median stage timelines.
    Stage 1 (planning & consenting) applies to early-status projects;
    Stage 2+3 to permission-granted; Stage 3 only to awaiting/under construction.
    """
    use_median = _planning_use_median()
    mapped_tech = _map_repd_tech_type(tech_type)
    status_config = config.repd_status_to_timeline.get(
        development_status,
        {"timeline_type": "total_median" if use_median else "total_mean"},
    )
    timeline_type = status_config.get("timeline_type", "total_median")
    if not use_median and timeline_type.endswith("_median"):
        timeline_type = timeline_type.replace("_median", "_mean")
    elif use_median and timeline_type.endswith("_mean"):
        timeline_type = timeline_type.replace("_mean", "_median")

    months = _timeline_months_for_type(mapped_tech, timeline_type, use_median=use_median)
    return completion_year_from_months(int(base_year), months, project_key=project_key)


def _pipeline_earliest_completion_year(cem_start_year: int) -> int | None:
    """Earliest external-pipeline completion when operational stock is seeded at START_YEAR."""
    if os.getenv("APPLY_REPD_INITIAL_SNAPSHOT", "1").strip().lower() in {"0", "false", "no"}:
        return None
    return int(cem_start_year) + 1


def _estimate_repd_historical_completion_year(row, status: str, cem_start_year: int = 2025) -> int:
    """Completion year from actual REPD milestone dates (for overdue/zombie screening only)."""
    tech_type_str = row.get("Technology Type", "")
    project_key = str(row.get("Site Name", row.get("Ref ID", "unknown")))

    perm_year = _parse_repd_year(row.get("Planning Permission  Granted"))
    if perm_year is None:
        perm_year = _parse_repd_year(row.get("Planning Permission Granted"))

    if status in {"Planning Permission Granted", "Awaiting Construction", "Under Construction"} and perm_year:
        return calculate_development_timeline(tech_type_str, status, perm_year, project_key=project_key)

    app_year = _parse_repd_year(row.get("Planning Application Submitted"))
    base_year = app_year if app_year and app_year >= 2000 else cem_start_year
    return calculate_development_timeline(tech_type_str, status, base_year, project_key=project_key)


def estimate_repd_completion_year(row, status: str, cem_start_year: int = 2025) -> int:
    """Project-specific REPD completion year using status stage and key milestone dates.

    Uses Table 13 median stage timelines for all technologies (including battery BESS).
    REPD 'Operational' forecast dates are not used — they bypass the 3-stage pipeline.

    Milestone years before cem_start_year are anchored to cem_start_year so remaining
    stage durations are forward-looking from the model start (same rule as VRE).
    """
    tech_type_str = row.get("Technology Type", "")
    project_key = str(row.get("Site Name", row.get("Ref ID", "unknown")))
    cem_start_year = int(cem_start_year)

    perm_year = _parse_repd_year(row.get("Planning Permission  Granted"))
    if perm_year is None:
        perm_year = _parse_repd_year(row.get("Planning Permission Granted"))

    app_year = _parse_repd_year(row.get("Planning Application Submitted"))

    if status in {"Planning Permission Granted", "Awaiting Construction", "Under Construction"} and perm_year:
        base_year = max(int(perm_year), cem_start_year)
        completion_year = calculate_development_timeline(
            tech_type_str, status, base_year, project_key=project_key
        )
    else:
        base_year = max(int(app_year) if app_year and app_year >= 2000 else cem_start_year, cem_start_year)
        completion_year = calculate_development_timeline(
            tech_type_str, status, base_year, project_key=project_key
        )

    # Recent applications still in late stages: full notional pipeline from application
    # can land later than a short remaining-stage estimate from START_YEAR alone.
    if app_year and app_year >= 2000:
        full_from_app = calculate_development_timeline(
            tech_type_str,
            "Application Submitted",
            max(int(app_year), cem_start_year),
            project_key=project_key,
        )
        completion_year = max(completion_year, full_from_app)

    floor_year = _pipeline_earliest_completion_year(cem_start_year)
    if floor_year is not None:
        completion_year = max(completion_year, floor_year)

    return int(completion_year)


def _repd_zombie_status_stale_year() -> int:
    """Last calendar year that still counts as stagnant (default 2015 — no status change after 2015)."""
    explicit = os.getenv("REPD_ZOMBIE_STATUS_STALE_YEAR", "").strip()
    if explicit:
        return int(explicit)
    configured = config.repd_filtering.get("zombie_status_stale_year")
    if configured is not None:
        return int(configured)
    return 2015


def _repd_zombie_snapshot_year() -> int:
    return int(
        os.getenv(
            "REPD_ZOMBIE_SNAPSHOT_YEAR",
            str(config.repd_filtering.get("zombie_snapshot_year", os.getenv("START_YEAR", "2025"))),
        )
    )


_REPD_STATUS_PROGRESS_COLUMNS = (
    "Planning Application Submitted",
    "Appeal Lodged",
    "Appeal Granted",
    "Planning Permission Granted",
    "Planning Permission  Granted",
    "Secretary of State - Granted",
    "Under Construction",
    "Operational",
)


def _repd_last_status_progress_year(row) -> int | None:
    """Latest REPD milestone year indicating forward development status progress."""
    years = []
    for column in _REPD_STATUS_PROGRESS_COLUMNS:
        year = _parse_repd_year(row.get(column))
        if year is not None:
            years.append(year)
    if not years:
        return None
    return int(max(years))


def _repd_row_is_operational(row, snapshot_year: int | None = None) -> bool:
    snapshot_year = int(snapshot_year or _repd_zombie_snapshot_year())
    status = row.get("Development Status (short)")
    if status == "Operational":
        return True
    op_date = pd.to_datetime(row.get("Operational"), errors="coerce", dayfirst=True)
    return pd.notna(op_date) and int(op_date.year) <= snapshot_year


def is_status_stagnant_repd_zombie(row) -> bool:
    """
    Zombie if still non-operational at snapshot and the latest REPD status-progress
    milestone is on/before the stale year (default 2015) — no status change after 2015.
    """
    if not config.repd_filtering.get("apply_zombie_filter", True):
        return False

    snapshot_year = _repd_zombie_snapshot_year()
    if _repd_row_is_operational(row, snapshot_year):
        return False

    status = row.get("Development Status (short)")
    if pd.isna(status):
        return False

    terminal_statuses = {
        "Application Refused",
        "Application Withdrawn",
        "Abandoned",
        "Appeal Refused",
        "Appeal Withdrawn",
        "Decommissioned",
        "Application Expired",
        "Finished",
    }
    if status in terminal_statuses:
        return False

    last_progress_year = _repd_last_status_progress_year(row)
    if last_progress_year is None:
        return False
    return int(last_progress_year) <= _repd_zombie_status_stale_year()


def _repd_zombie_schedule_deadline_year() -> int:
    """Implied completion on/before this year (with grace) marks a schedule-overdue zombie."""
    grace_years = int(os.getenv("REPD_ZOMBIE_CONSTRUCTION_GRACE_YEARS", "2"))
    return _repd_zombie_snapshot_year() - grace_years


def is_schedule_overdue_repd_zombie(row) -> bool:
    """
    Zombie if still non-operational at snapshot and historical median timelines implied
    completion on/before the schedule deadline (snapshot minus construction grace).
    """
    if not config.repd_filtering.get("apply_zombie_filter", True):
        return False

    snapshot_year = _repd_zombie_snapshot_year()
    if _repd_row_is_operational(row, snapshot_year):
        return False

    status = row.get("Development Status (short)")
    if pd.isna(status):
        return False

    terminal_statuses = {
        "Application Refused",
        "Application Withdrawn",
        "Abandoned",
        "Appeal Refused",
        "Appeal Withdrawn",
        "Decommissioned",
        "Application Expired",
        "Finished",
    }
    if status in terminal_statuses:
        return False

    historical_completion = _estimate_repd_historical_completion_year(
        row, status, cem_start_year=snapshot_year
    )
    return int(historical_completion) <= _repd_zombie_schedule_deadline_year()


def is_schedule_repd_zombie(row) -> bool:
    """Schedule-overdue zombie (historical timeline) or status-stagnant zombie."""
    return is_schedule_overdue_repd_zombie(row) or is_status_stagnant_repd_zombie(row)


def is_dynamic_repd_zombie(row) -> bool:
    return is_status_stagnant_repd_zombie(row)


def _project_is_status_stagnant_zombie(project: dict, repd_rows_by_name: dict | None = None) -> bool:
    if project.get("source") != "external":
        return False
    last_progress_year = project.get("last_status_progress_year")
    if last_progress_year is None and repd_rows_by_name is not None:
        row = repd_rows_by_name.get(project.get("name"))
        if row is not None:
            last_progress_year = _repd_last_status_progress_year(row)
    if last_progress_year is None:
        return False
    return int(last_progress_year) <= _repd_zombie_status_stale_year()


def _project_is_schedule_overdue_zombie(project: dict, repd_rows_by_name: dict | None = None) -> bool:
    if project.get("source") != "external":
        return False
    if repd_rows_by_name is None:
        return False
    row = repd_rows_by_name.get(project.get("name"))
    if row is None:
        return False
    return is_schedule_overdue_repd_zombie(row)


def filter_zombie_external_pipeline(
    project_pipeline: list,
    *,
    start_year: int | None = None,
    repd_rows_by_name: dict | None = None,
) -> tuple[list, int]:
    """Remove external REPD entries that are status-stagnant or schedule-overdue zombies."""
    start_year = int(start_year or os.getenv("START_YEAR", "2025"))
    kept: list = []
    removed = 0
    for project in project_pipeline:
        if project.get("source") != "external":
            kept.append(project)
            continue
        if _project_is_status_stagnant_zombie(project, repd_rows_by_name):
            removed += 1
            continue
        if _project_is_schedule_overdue_zombie(project, repd_rows_by_name):
            removed += 1
            continue
        completion_year = project.get("completion_year")
        if completion_year is not None and int(completion_year) < start_year:
            removed += 1
            continue
        kept.append(project)
    return kept, removed


def normalize_external_pipeline_completion_years(
    project_pipeline: list,
    *,
    start_year: int | None = None,
) -> tuple[list, int]:
    """Remove external projects scheduled before START_YEAR (already in operational stock)."""
    start_year = int(start_year or os.getenv("START_YEAR", "2025"))
    excluded = 0
    normalized: list = []
    for project in project_pipeline:
        if project.get("source") != "external":
            normalized.append(project)
            continue
        completion_year = project.get("completion_year")
        if completion_year is None:
            normalized.append(project)
            continue
        cy = int(completion_year)
        if cy < start_year:
            excluded += 1
            continue
        normalized.append(project)
    return normalized, excluded


REPD_UNCERTAIN_DEVELOPMENT_STATUSES = frozenset({
    "Application Submitted",
    "Appeal Lodged",
    "Revised",
})


def _env_bool_flag(name: str) -> bool | None:
    val = os.getenv(name, "").strip().lower()
    if val in {"1", "true", "yes"}:
        return True
    if val in {"0", "false", "no"}:
        return False
    return None


def _repd_include_uncertain_projects_enabled() -> bool:
    env_val = _env_bool_flag("REPD_INCLUDE_UNCERTAIN_PROJECTS")
    if env_val is not None:
        return env_val
    return bool(config.repd_filtering.get("include_uncertain_projects", False))


def _repd_uncertain_as_model_decision_enabled() -> bool:
    env_val = _env_bool_flag("REPD_UNCERTAIN_AS_MODEL_DECISION")
    if env_val is not None:
        return env_val
    return False


def _repd_uncertain_decision_year() -> int:
    return int(os.getenv("REPD_UNCERTAIN_DECISION_YEAR", "2024"))


def _placeholder_target_asset_for_repd_region(technology_type: str, region: str) -> str:
    tech = str(technology_type or "").lower()
    reg = str(region or "England").lower()
    if tech == "offshore":
        return "offshore1"
    if tech == "onshore":
        return "onshore_Edinburgh" if reg == "scotland" else "onshore_Nottingham"
    if tech == "solar":
        return "solar_Edinburgh" if reg == "scotland" else "solar_Nottingham"
    return tech or "solar_Nottingham"


def repackage_uncertain_repd_as_model_decisions(
    project_pipeline: list,
    success_rates: dict,
    *,
    decision_year: int | None = None,
) -> tuple[list, dict]:
    """Treat uncertain REPD rows like year-end model investments (timeline + success rate)."""
    if not _repd_uncertain_as_model_decision_enabled():
        return project_pipeline, {"converted_projects": 0, "converted_mw": 0.0, "decision_year": None}

    decision_year = int(decision_year or _repd_uncertain_decision_year())
    kept: list = []
    to_convert: list = []
    for project in project_pipeline:
        is_uncertain_external = (
            project.get("source") == "external"
            and (
                project.get("development_status") in REPD_UNCERTAIN_DEVELOPMENT_STATUSES
                or project.get("confidence_level") == "uncertain"
            )
        )
        if is_uncertain_external:
            to_convert.append(project)
    else:
            kept.append(project)

    converted_mw = 0.0
    for project in to_convert:
        tech = project.get("technology_type")
        cap = float(project.get("capacity", 0) or 0)
        if cap < 1e-6 or not tech:
            kept.append(project)
            continue
        region = str(project.get("region") or "England")
        append_model_investment_to_pipeline(
            kept,
            name=str(project.get("name") or "uncertain_repd"),
            technology_type=tech,
            capacity=cap,
            decision_year=decision_year,
            target_asset_name=_placeholder_target_asset_for_repd_region(tech, region),
            success_rates=success_rates,
            source="model",
            region=region,
            latitude=project.get("latitude"),
            longitude=project.get("longitude"),
            planning_origin="uncertain_repd",
            repd_development_status=project.get("development_status"),
        )
        converted_mw += cap

    stats = {
        "converted_projects": len(to_convert),
        "converted_mw": converted_mw,
        "decision_year": decision_year,
    }
    if to_convert:
        print("\n--- Uncertain REPD repackaged as model planning decisions ---")
        print(
            f"Decision year: {decision_year} | Projects: {stats['converted_projects']} | "
            f"Nameplate: {stats['converted_mw']/1000:.2f} GW"
        )
        print(
            "Timeline: median stage-1 (Application Submitted) via calculate_development_timeline; "
            "success rate: regional technology rate with MODEL_SUCCESS_MODE."
        )
    return kept, stats


def append_model_investment_to_pipeline(
    project_pipeline,
    *,
    name: str,
    technology_type: str,
    capacity: float,
    decision_year: int,
    target_asset_name: str,
    success_rates: dict,
    assigned_generator: str | None = None,
    source: str = "model",
    region: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    planning_origin: str | None = None,
    repd_development_status: str | None = None,
):
    """Enter a model investment into the planning pipeline (median stage-1 timeline + success rate)."""
    if abs(capacity) < 1e-6:
        return

    if capacity < 0:
        project_pipeline.append(
            {
                "name": name,
                "technology_type": technology_type,
                "capacity": capacity,
                "completion_year": decision_year + 1,
                "source": source,
                "target_asset_name": target_asset_name,
                "assigned_generator": assigned_generator or target_asset_name,
                "development_status": "depletion",
                "success_rate_applied": False,
            }
        )
        return

    region = region or get_asset_region(target_asset_name)
    tech_label = _repd_tech_label_for_asset(technology_type)
    dev_status = _repd_model_status_for_asset(technology_type)

    success_tech = tech_label
    success_rate = _lookup_regional_success_rate(success_rates, success_tech, region)

    original_capacity = float(capacity)
    final_capacity, project_succeeds, random_draw, status = _resolve_model_success_capacity(
        original_capacity,
        success_rate,
        project_key=name,
        region=region,
        success_tech=success_tech,
    )

    completion_year = calculate_development_timeline(
        tech_label,
        dev_status,
        decision_year,
        project_key=name,
    )

    entry = {
        "name": name,
        "technology_type": technology_type,
        "capacity": final_capacity,
        "original_capacity": original_capacity,
        "completion_year": completion_year,
        "source": source,
        "target_asset_name": target_asset_name,
        "assigned_generator": assigned_generator or target_asset_name,
        "development_status": dev_status,
        "region": region,
        "success_rate": success_rate,
        "success_technology": success_tech,
        "success_region": region,
        "project_succeeds": project_succeeds,
        "success_rate_applied": True,
        "success_mode": _model_success_mode(),
        "status": status,
    }
    if random_draw is not None:
        entry["random_draw"] = random_draw
    if latitude is not None:
        entry["latitude"] = latitude
    if longitude is not None:
        entry["longitude"] = longitude
    if planning_origin:
        entry["planning_origin"] = planning_origin
    if repd_development_status:
        entry["repd_development_status"] = repd_development_status
    project_pipeline.append(entry)


def apply_success_rates_to_repd_projects(project_pipeline, success_rates):
    """
    Apply regional technology success rates to REPD projects that require it
    (Application Submitted, Appeal Lodged, Revised status).
    
    Args:
    - project_pipeline (list): List of project dictionaries  
    - success_rates (dict): Technology success rates by technology and region
    
    Returns:
    - list: Updated project pipeline with success rates applied
    """
    updated_pipeline = []
    
    # Set random seed for reproducible results
    random.seed(42)
    
    for project in project_pipeline:
        updated_project = project.copy()
        
        # Check if this project needs success rate application
        development_status = project.get('development_status', '')
        needs_success_rate = config.repd_status_to_timeline.get(development_status, {}).get('apply_success_rate', False)
        
        if needs_success_rate:
            tech_type = project.get('technology_type', '')
            success_tech = _tech_label_for_success_rate(tech_type)
            region = project.get('region', 'England')
            success_rate = _lookup_regional_success_rate(success_rates, success_tech, region)

            original_capacity = float(
                project.get('original_capacity', project.get('capacity', 0)) or 0
            )
            final_capacity, project_succeeds, random_draw, status = _resolve_model_success_capacity(
                original_capacity,
                success_rate,
                project_key=project.get("name", "unknown"),
                region=region,
                success_tech=success_tech,
            )

            updated_project.update({
                'success_rate': success_rate,
                'success_technology': success_tech,
                'success_region': region,
                'project_succeeds': project_succeeds,
                'success_rate_applied': True,
                'success_mode': _model_success_mode(),
                'original_capacity': original_capacity,
                'capacity': final_capacity,
                'status': status,
            })
            if random_draw is not None:
                updated_project['random_draw'] = random_draw
            else:
                updated_project.pop('random_draw', None)
                
        else:
            updated_project['success_rate_applied'] = False
            
        updated_pipeline.append(updated_project)
    
    return updated_pipeline


def generate_success_rate_summary(project_pipeline, investment_summary_df):
    """
    Generate detailed success rate analysis and save to files.
    
    Args:
    - project_pipeline (list): List of all projects with success rate information
    - investment_summary_df (DataFrame): Investment summary dataframe
    """
    print("\n" + "="*60)
    print("DETAILED SUCCESS RATE ANALYSIS")
    print("="*60)
    
    # Filter model projects with success rates applied
    model_projects = [p for p in project_pipeline if p.get('success_rate_applied', False)]
    
    if not model_projects:
        print("No model projects found with success rates applied.")
        return
    
    # Create detailed success rate dataframe
    success_rate_data = []
    for project in model_projects:
        success_rate_data.append({
            'Project_Name': project.get('name', 'Unknown'),
            'Technology_Type': project.get('technology_type', 'Unknown'),
            'Region': project.get('success_region', 'Unknown'),
            'Success_Technology': project.get('success_technology', 'Unknown'),
            'Original_Capacity_MW': project.get('original_capacity', project.get('capacity', 0)),
            'Final_Capacity_MW': project.get('capacity', 0),
            'Completion_Year': project.get('completion_year', 'Unknown'),
            'Success_Rate': project.get('success_rate', 0),
            'Random_Draw': project.get('random_draw', 0),
            'Project_Succeeds': project.get('project_succeeds', True),
            'Status': project.get('status', 'active'),
            'Source': project.get('source', 'Unknown')
        })
    
    df_success = pd.DataFrame(success_rate_data)
    
    # Summary statistics
    print("\nSuccess Rate Summary Statistics:")
    print("-" * 40)
    
    total_projects = len(df_success)
    successful_projects = len(df_success[df_success['Project_Succeeds'] == True])
    failed_projects = total_projects - successful_projects
    
    total_capacity = df_success['Original_Capacity_MW'].sum()
    successful_capacity = df_success[df_success['Project_Succeeds'] == True]['Final_Capacity_MW'].sum()
    failed_capacity = df_success[df_success['Project_Succeeds'] == False]['Original_Capacity_MW'].sum()
    
    print(f"Total Model Projects: {total_projects}")
    print(f"Successful Projects: {successful_projects} ({(successful_projects/total_projects)*100:.1f}%)")
    print(f"Failed Projects: {failed_projects} ({(failed_projects/total_projects)*100:.1f}%)")
    print(f"Total Original Capacity: {total_capacity:.1f} MW")
    print(f"Successful Capacity: {successful_capacity:.1f} MW ({(successful_capacity/total_capacity)*100:.1f}%)")
    print(f"Failed Capacity: {failed_capacity:.1f} MW ({(failed_capacity/total_capacity)*100:.1f}%)")
    
    # Analysis by technology
    print("\nSuccess Rate by Technology:")
    print("-" * 40)
    tech_analysis = df_success.groupby('Technology_Type').agg({
        'Project_Succeeds': ['count', 'sum'],
        'Original_Capacity_MW': 'sum',
        'Final_Capacity_MW': 'sum',
        'Success_Rate': 'mean'
    }).round(3)
    
    tech_analysis.columns = ['Total_Projects', 'Successful_Projects', 'Original_Capacity_MW', 'Final_Capacity_MW', 'Avg_Success_Rate']
    tech_analysis['Success_Percentage'] = (tech_analysis['Successful_Projects'] / tech_analysis['Total_Projects'] * 100).round(1)
    print(tech_analysis)
    
    # Analysis by region
    print("\nSuccess Rate by Region:")
    print("-" * 40)
    region_analysis = df_success.groupby('Region').agg({
        'Project_Succeeds': ['count', 'sum'],
        'Original_Capacity_MW': 'sum',
        'Final_Capacity_MW': 'sum',
        'Success_Rate': 'mean'
    }).round(3)
    
    region_analysis.columns = ['Total_Projects', 'Successful_Projects', 'Original_Capacity_MW', 'Final_Capacity_MW', 'Avg_Success_Rate']
    region_analysis['Success_Percentage'] = (region_analysis['Successful_Projects'] / region_analysis['Total_Projects'] * 100).round(1)
    print(region_analysis)
    
    # Save detailed results
    df_success.to_csv('model_investment_success_rates.csv', index=False)
    print(f"\nDetailed success rate analysis saved to 'model_investment_success_rates.csv'")
    
    # Save summary statistics
    summary_stats = {
        'Total_Model_Projects': total_projects,
        'Successful_Projects': successful_projects,
        'Failed_Projects': failed_projects,
        'Overall_Success_Rate_Projects': (successful_projects/total_projects)*100 if total_projects > 0 else 0,
        'Total_Original_Capacity_MW': total_capacity,
        'Successful_Capacity_MW': successful_capacity,
        'Failed_Capacity_MW': failed_capacity,
        'Overall_Success_Rate_Capacity': (successful_capacity/total_capacity)*100 if total_capacity > 0 else 0
    }
    
    df_summary_stats = pd.DataFrame([summary_stats])
    df_summary_stats.to_csv('success_rate_summary_statistics.csv', index=False)
    print("Summary statistics saved to 'success_rate_summary_statistics.csv'")
    
    # Show failed projects details
    failed_projects_df = df_success[df_success['Project_Succeeds'] == False]
    if not failed_projects_df.empty:
        print(f"\nFailed Projects Details ({len(failed_projects_df)} projects):")
        print("-" * 40)
        print(failed_projects_df[['Project_Name', 'Technology_Type', 'Region', 'Original_Capacity_MW', 'Success_Rate']].to_string(index=False))


def _parse_repd_year(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    dt = pd.to_datetime(value, errors="coerce", dayfirst=True)
    if pd.isna(dt):
        return None
    return int(dt.year)


def load_validation_planning_pipeline_snapshot():
    """Load REPD projects in planning as of a historical snapshot year for validation."""
    snapshot_year = int(
        os.getenv(
            "VALIDATION_PIPELINE_SNAPSHOT_YEAR",
            os.getenv("VALIDATION_INITIAL_CAPACITY_YEAR", "2015"),
        )
    )
    max_app_year = int(os.getenv("VALIDATION_PIPELINE_MAX_APP_YEAR", str(snapshot_year)))
    end_year = int(os.getenv("END_YEAR", "2025"))
    repd_file = os.getenv("VALIDATION_REPD_FILE", "repd-q2-jul-2025.csv")
    use_operational_date = os.getenv("VALIDATION_PIPELINE_USE_OPERATIONAL_DATE", "1").strip().lower() in {
        "1", "true", "yes",
    }

    status_str = os.getenv("VALIDATION_PIPELINE_STATUSES", "").strip()
    if status_str:
        pipeline_statuses = {s.strip() for s in status_str.split(",") if s.strip()}
    else:
        pipeline_statuses = {
            "Under Construction",
            "Awaiting Construction",
            "Planning Permission Granted",
            "Application Submitted",
            "Appeal Lodged",
            "Revised",
        }

    zombie_statuses = {
        "Application Refused",
        "Application Withdrawn",
        "Abandoned",
        "Appeal Refused",
        "Appeal Withdrawn",
        "Decommissioned",
        "Application Expired",
        "Finished",
    }
    high_confidence_statuses = {
        "Under Construction",
        "Awaiting Construction",
        "Planning Permission Granted",
    }

    min_size = config.repd_filtering["minimum_project_size_mw"]

    try:
        df = pd.read_csv(repd_file, encoding="utf-8")
    except UnicodeDecodeError:
        df = pd.read_csv(repd_file, encoding="latin1")

    from map_projects_to_generators_by_location import extract_location_from_repd

    project_pipeline = []
    counts = {
        "total_projects": 0,
        "app_year_filtered": 0,
        "already_operational": 0,
        "zombie_filtered": 0,
        "schedule_zombie_filtered": 0,
        "status_filtered": 0,
        "included": 0,
    }

    for _, row in df.iterrows():
        counts["total_projects"] += 1

        tech_type = get_asset_type_from_repd(row.get("Technology Type", ""))
        if not tech_type:
            continue

        status = row.get("Development Status (short)")
        if status in zombie_statuses:
            counts["zombie_filtered"] += 1
            continue

        if config.repd_filtering.get("apply_zombie_filter", True) and is_schedule_repd_zombie(row):
            counts["schedule_zombie_filtered"] += 1
            continue

        if config.repd_filtering.get("apply_zombie_filter", True) and is_status_stagnant_repd_zombie(row):
            counts["schedule_zombie_filtered"] += 1
            continue

        app_year = _parse_repd_year(row.get("Planning Application Submitted"))
        if app_year is None or app_year > max_app_year:
            counts["app_year_filtered"] += 1
            continue

        op_year = _parse_repd_year(row.get("Operational"))
        if op_year is not None and op_year <= snapshot_year:
            counts["already_operational"] += 1
            continue

        capacity = pd.to_numeric(row.get("Installed Capacity (MWelec)"), errors="coerce")
        if pd.isna(capacity) or capacity < min_size:
            continue

        completion_year = None
        if status == "Operational" and use_operational_date and op_year is not None:
            if snapshot_year < op_year <= end_year:
                completion_year = op_year
        elif status in pipeline_statuses:
            completion_year = calculate_development_timeline(
                row.get("Technology Type", ""),
                status,
                snapshot_year,
                project_key=str(row.get("Site Name", row.get("Ref ID", "unknown"))),
            )
        else:
            counts["status_filtered"] += 1
            continue

        if completion_year is None or completion_year <= snapshot_year or completion_year > end_year:
            continue

        confidence_weight = config.repd_filtering["confidence_weights"].get(status, 0.1)
        lat, lon = extract_location_from_repd(row)
        counts["included"] += 1
        project_pipeline.append({
            "name": row.get("Site Name", "Unknown"),
            "technology_type": tech_type,
            "capacity": capacity,
            "completion_year": completion_year,
            "source": "external",
            "development_status": status,
            "region": row.get("Region", "England"),
            "confidence_level": "high" if status in high_confidence_statuses else "uncertain",
            "confidence_score": confidence_weight,
            "adjusted_capacity": capacity * confidence_weight,
            "latitude": lat,
            "longitude": lon,
        })

    print("\n--- REPD Project Filtering Summary ---")
    print(
        f"Validation planning pipeline snapshot {snapshot_year}: "
        f"app submitted <= {max_app_year}, operational after {snapshot_year}"
    )
    print(f"Total projects processed: {counts['total_projects']}")
    print(f"Filtered (planning app after snapshot): {counts['app_year_filtered']}")
    print(f"Filtered (already operational by snapshot): {counts['already_operational']}")
    print(f"Zombie projects filtered out: {counts['zombie_filtered']}")
    print(f"Status-stagnant zombie projects filtered out: {counts['schedule_zombie_filtered']}")
    print(f"Filtered (status not in planning set): {counts['status_filtered']}")
    print(f"Projects included in pipeline: {counts['included']}")

    return project_pipeline


def load_external_projects(include_uncertain_projects=None, zombie_filter=None):
    """
    Loads projects from REPD CSV files with advanced filtering for zombie projects.
    
    Parameters:
    - include_uncertain_projects (bool): Whether to include projects with uncertain timelines (from config if None)
    - zombie_filter (bool): Whether to apply zombie project filtering (from config if None)
    
    Returns:
    - project_pipeline (list): Filtered list of viable projects
    """
    # Use config defaults if not specified (env REPD_INCLUDE_UNCERTAIN_PROJECTS overrides config)
    if include_uncertain_projects is None:
        env_uncertain = os.getenv("REPD_INCLUDE_UNCERTAIN_PROJECTS", "").strip().lower()
        if env_uncertain in {"1", "true", "yes"}:
            include_uncertain_projects = True
        elif env_uncertain in {"0", "false", "no"}:
            include_uncertain_projects = False
        else:
            include_uncertain_projects = config.repd_filtering["include_uncertain_projects"]
    if zombie_filter is None:
        zombie_filter = config.repd_filtering["apply_zombie_filter"]

    if os.getenv("VALIDATION_DISABLE_EXTERNAL_PROJECTS", "").strip().lower() in {"1", "true", "yes"}:
        print("\n--- REPD Project Filtering Summary ---")
        print("Validation mode: external REPD project pipeline disabled; REPD is used for initial snapshot/comparison only.")
        return []

    validation_mode = os.getenv("VALIDATION_MODE", "").strip().lower() in {"1", "true", "yes"}
    if validation_mode and os.getenv("VALIDATION_PIPELINE_SNAPSHOT_YEAR", "").strip():
        return load_validation_planning_pipeline_snapshot()
    
    project_pipeline = []
    repd_files = ['repd-q2-jul-2025.csv'] 
    
    # Define zombie project statuses (projects unlikely to be completed)
    zombie_statuses = {
        'Application Refused', 'Application Withdrawn', 'Abandoned', 
        'Appeal Refused', 'Appeal Withdrawn', 'Decommissioned', 
        'Application Expired', 'Finished'
    }
    
    # Define high-confidence statuses (very likely to be completed)
    high_confidence_statuses = {
        'Under Construction', 'Awaiting Construction', 'Planning Permission Granted'
    }
    
    # Define uncertain statuses (may or may not be completed)
    uncertain_statuses = {
        'Application Submitted', 'Appeal Lodged', 'Revised'
    }
    
    # Get filtering parameters from config
    min_size = config.repd_filtering["minimum_project_size_mw"]
    max_year = config.repd_filtering["max_completion_year"]
    uncertainty_penalty = config.repd_filtering["uncertainty_timeline_penalty"]
    
    filtered_counts = {
        'total_projects': 0,
        'zombie_filtered': 0,
        'schedule_zombie_filtered': 0,
        'status_stagnant_zombie_filtered': 0,
        'uncertain_filtered': 0,
        'missing_status': 0,
        'past_completion_filtered': 0,
        'already_operational_filtered': 0,
        'included': 0
    }
    
    cem_start_year = int(os.getenv("START_YEAR", "2025"))
    status_stale_year = _repd_zombie_status_stale_year()
    
    for file in repd_files:
        try:
            df = pd.read_csv(file, encoding='utf-8')
        except UnicodeDecodeError:
            df = pd.read_csv(file, encoding='latin1')

        for _, row in df.iterrows():
            filtered_counts['total_projects'] += 1
            
            # Use 'Technology Type' column
            tech_type_str = row.get('Technology Type', '')
            tech_type = get_asset_type_from_repd(tech_type_str)
            if not tech_type:
                continue
            
            # Use 'Development Status (short)'
            status = row.get('Development Status (short)')
            
            # Apply zombie project filtering
            if zombie_filter and status in zombie_statuses:
                filtered_counts['zombie_filtered'] += 1
                continue

            if zombie_filter and is_status_stagnant_repd_zombie(row):
                filtered_counts['status_stagnant_zombie_filtered'] += 1
                continue

            if zombie_filter and is_schedule_overdue_repd_zombie(row):
                filtered_counts['schedule_zombie_filtered'] += 1
                continue
            
            # Handle uncertain projects
            if not include_uncertain_projects and status in uncertain_statuses:
                filtered_counts['uncertain_filtered'] += 1
                continue
            
            # Handle missing or unknown status
            if pd.isna(status) or status not in (high_confidence_statuses | uncertain_statuses):
                filtered_counts['missing_status'] += 1
                if not include_uncertain_projects:  # Be conservative with unknown statuses
                    continue
            
            # Use 'Installed Capacity (MWelec)'
            capacity = pd.to_numeric(row.get('Installed Capacity (MWelec)'), errors='coerce')
            if pd.isna(capacity) or capacity < min_size:
                continue

            if _repd_row_is_operational(row, snapshot_year=cem_start_year):
                filtered_counts['already_operational_filtered'] += 1
                continue

            historical_completion = _estimate_repd_historical_completion_year(
                row, status, cem_start_year=cem_start_year
            )
            if int(historical_completion) < cem_start_year:
                filtered_counts['past_completion_filtered'] += 1
                continue

            completion_year = estimate_repd_completion_year(row, status, cem_start_year=cem_start_year)
            est_completion_date = datetime(completion_year, 6, 1)

            status_config = config.repd_status_to_timeline.get(status)
            if not status_config:
                if status in uncertain_statuses and not include_uncertain_projects:
                    continue
                elif status in zombie_statuses and zombie_filter:
                    continue

            # Apply completion year filter
            completion_year_int = int(est_completion_date.year)
            if completion_year_int < cem_start_year:
                filtered_counts['past_completion_filtered'] += 1
                continue
            if completion_year_int <= max_year:
                # Calculate confidence score
                confidence_weight = config.repd_filtering["confidence_weights"].get(status, 0.1)
                last_progress_year = _repd_last_status_progress_year(row)
                
                filtered_counts['included'] += 1
                # Extract location information
                from map_projects_to_generators_by_location import extract_location_from_repd
                lat, lon = extract_location_from_repd(row)
                
                project_pipeline.append({
                    'name': row.get('Site Name', 'Unknown'),
                    'technology_type': tech_type,
                    'capacity': capacity,
                    'completion_year': completion_year_int,
                    'source': 'external',
                    'development_status': status,
                    'region': row.get('Region', 'England'),  # Add region for success rate mapping
                    'confidence_level': 'high' if status in high_confidence_statuses else 'uncertain',
                    'confidence_score': confidence_weight,
                    'adjusted_capacity': capacity * confidence_weight,  # Capacity weighted by confidence
                    'latitude': lat,  # Add latitude
                    'longitude': lon,  # Add longitude
                    'last_status_progress_year': last_progress_year,
                })

    # Print filtering summary
    print(f"\n--- REPD Project Filtering Summary ---")
    print(
        f"Status-stagnant zombie rule: last REPD status-progress milestone <= {status_stale_year} "
        f"and still non-operational at snapshot {_repd_zombie_snapshot_year()}"
    )
    print(
        f"Schedule-overdue zombie rule: historical median completion <= "
        f"{_repd_zombie_schedule_deadline_year()} (snapshot minus "
        f"{os.getenv('REPD_ZOMBIE_CONSTRUCTION_GRACE_YEARS', '2')}y grace)"
    )
    print(f"Total projects processed: {filtered_counts['total_projects']}")
    print(f"Zombie projects filtered out: {filtered_counts['zombie_filtered']}")
    print(f"Status-stagnant zombie projects filtered out: {filtered_counts['status_stagnant_zombie_filtered']}")
    print(f"Schedule-overdue zombie projects filtered out: {filtered_counts['schedule_zombie_filtered']}")
    print(f"Already-operational stock excluded: {filtered_counts['already_operational_filtered']}")
    print(f"Pre-START_YEAR completions excluded: {filtered_counts['past_completion_filtered']}")
    print(f"Uncertain projects filtered out: {filtered_counts['uncertain_filtered']}")
    print(f"Missing/unknown status: {filtered_counts['missing_status']}")
    print(f"Projects included in pipeline: {filtered_counts['included']}")
    print(f"Filtering effectiveness: {(filtered_counts['zombie_filtered'] + filtered_counts['uncertain_filtered']) / filtered_counts['total_projects'] * 100:.1f}% filtered")
    
    return project_pipeline


def analyze_zombie_filtering_impact():
    """
    Analyze the impact of different zombie project filtering approaches.
    """
    print("\n" + "="*70)
    print("ZOMBIE PROJECT FILTERING ANALYSIS")
    print("="*70)
    
    # Load projects with different filtering settings
    scenarios = {
        "No Filtering": {"zombie_filter": False, "include_uncertain_projects": True},
        "Zombie Filter Only": {"zombie_filter": True, "include_uncertain_projects": True},
        "Conservative (Recommended)": {"zombie_filter": True, "include_uncertain_projects": False},
        "Ultra Conservative": {"zombie_filter": True, "include_uncertain_projects": False}
    }
    
    results = {}
    
    for scenario_name, settings in scenarios.items():
        print(f"\n--- {scenario_name} ---")
        projects = load_external_projects(**settings)
        
        if projects:
            df_projects = pd.DataFrame(projects)
            
            # Calculate statistics
            total_capacity = df_projects['capacity'].sum()
            total_projects = len(df_projects)
            avg_confidence = df_projects['confidence_score'].mean() if 'confidence_score' in df_projects.columns else 0
            weighted_capacity = df_projects['adjusted_capacity'].sum() if 'adjusted_capacity' in df_projects.columns else total_capacity
            
            # Technology breakdown
            tech_breakdown = df_projects.groupby('technology_type').agg({
                'capacity': 'sum',
                'confidence_score': 'mean'
            }).round(2)
            
            # Status breakdown
            status_breakdown = df_projects.groupby('development_status')['capacity'].sum().round(1)
            
            results[scenario_name] = {
                'total_projects': total_projects,
                'total_capacity_mw': total_capacity,
                'weighted_capacity_mw': weighted_capacity,
                'avg_confidence': avg_confidence,
                'tech_breakdown': tech_breakdown,
                'status_breakdown': status_breakdown
            }
            
            print(f"Projects: {total_projects}")
            print(f"Total Capacity: {total_capacity:.1f} MW")
            if 'confidence_score' in df_projects.columns:
                print(f"Weighted Capacity: {weighted_capacity:.1f} MW")
                print(f"Average Confidence: {avg_confidence:.2f}")
        else:
            results[scenario_name] = {
                'total_projects': 0,
                'total_capacity_mw': 0,
                'weighted_capacity_mw': 0,
                'avg_confidence': 0
            }
    
    # Comparison analysis
    print(f"\n" + "="*70)
    print("FILTERING IMPACT COMPARISON")
    print("="*70)
    
    if "No Filtering" in results and results["No Filtering"]['total_projects'] > 0:
        baseline = results["No Filtering"]
        
        print(f"{'Scenario':<25} {'Projects':<10} {'Capacity (MW)':<15} {'Reduction %':<12}")
        print("-" * 62)
        
        for scenario, data in results.items():
            reduction_pct = (1 - data['total_projects'] / baseline['total_projects']) * 100 if baseline['total_projects'] > 0 else 0
            print(f"{scenario:<25} {data['total_projects']:<10} {data['total_capacity_mw']:<15.1f} {reduction_pct:<12.1f}")
    
    # Save detailed analysis
    comparison_df = pd.DataFrame(results).T
    comparison_df.to_csv('zombie_filtering_analysis.csv')
    print(f"\nDetailed analysis saved to: zombie_filtering_analysis.csv")
    
    return results


def critical_capacity_for_threshold(reald_path, profile_path, negative_threshold=200):
    """
    Returns the raw critical capacity (MW) such that net_demand = demand - cap*profile
    has at least negative_threshold negative points. Used for plotting; no 0.1 factor.
    """
    reald = pd.read_csv(reald_path)
    demand = reald.iloc[:, 0].values
    profile = pd.read_csv(profile_path, header=None).squeeze().values
    min_len = min(len(demand), len(profile))
    demand = demand[:min_len]
    profile = profile[:min_len]

    def count_negative(cap):
        net_demand = demand - (cap * profile)
        return np.sum(net_demand < 0)

    left, right = 0, max(demand) * 10
    critical_capacity = 0
    for _ in range(30):
        mid = (left + right) / 2
        if count_negative(mid) >= negative_threshold:
            critical_capacity = mid
            right = mid
        else:
            left = mid
    return critical_capacity


def calculate_expansion_limit(reald_path, sa_path, negative_threshold=200):
    """
    Returns the raw critical capacity (MW) such that net_demand = demand - cap*profile
    has at least negative_threshold negative points. Callers apply 0.03 only (no 0.1).
    Uses 全网平均 profile: solar/onshore/offshore each with its own profile path.
    """
    return critical_capacity_for_threshold(reald_path, sa_path, negative_threshold)

def calculate_storage_expansion_limit(
    results,
    battery_objects,
    real_demands,
    preferred_rate=0.08,
    cap_row=None,
    agent_rois=None,
):
    """
    Loop-frequency storage expansion cap from **run_simulation traces** (scheme_c).

    Default STORAGE_CAP_CREDIT_MODE=scheme_c:
      gross_gap = max(demand − VRE, 0)
      net_demand = max(gross_gap − storage_discharge, 0)   # gen_list Battery energy
      excess     = leftover after storage charged          # results[22]
    No invented offline storage forecast; no second MW credit.

    Also supports pooled_existing_mw / post_dispatch via env.
    """
    sec, _ = _import_storage_expansion_modules()

    gen_list_composition = results[20]
    avg_electricity_prices = np.asarray(results[0], dtype=float)
    n = len(real_demands)

    total_vre_generation = np.zeros(n)
    storage_discharge = np.zeros(n)
    for period_index, period_data in enumerate(gen_list_composition):
        if period_index >= n:
            break
        for asset, energy in period_data:
            name = getattr(asset, "name", "") or ""
            energy_f = float(energy) if energy is not None else 0.0
            if "solar" in name or "onshore" in name or "offshore" in name:
                total_vre_generation[period_index] += energy_f
            elif isinstance(asset, Battery):
                storage_discharge[period_index] += energy_f

    # results[2] = store_electricity (charge into storage each period)
    store_charge = None
    if len(results) > 2 and results[2] is not None:
        raw = results[2]
        try:
            if isinstance(raw, list) and raw and isinstance(raw[0], (list, tuple)):
                store_charge = np.array(
                    [sum(float(x or 0) for x in item) if isinstance(item, (list, tuple)) else float(item or 0)
                     for item in raw],
                    dtype=float,
                )
            else:
                store_charge = np.asarray(raw, dtype=float)
            if len(store_charge) < n:
                store_charge = np.pad(store_charge, (0, n - len(store_charge)))
            else:
                store_charge = store_charge[:n]
        except (TypeError, ValueError):
            store_charge = None

    excess_generation = None
    if len(results) > 22 and results[22] is not None:
        excess_generation = np.asarray(results[22], dtype=float)
        if len(excess_generation) < n:
            excess_generation = np.pad(
                excess_generation, (0, n - len(excess_generation))
            )

    prices = avg_electricity_prices
    if len(prices) < n:
        prices = np.pad(prices, (0, n - len(prices)))

    preferred_rates = {
        k: sec.preferred_rate_for_tech(k, preferred_rate)
        for k in sec.EXPANDABLE_STORAGE_KEYS
        if k in battery_objects
    }

    # Scheme C residual: credit discharge only against the VRE gap
    if hasattr(sec, "scheme_c_net_demand_from_traces"):
        storage_net_demand = sec.scheme_c_net_demand_from_traces(
            real_demands, total_vre_generation, storage_discharge
        )
    else:
        gross_gap = np.maximum(
            np.asarray(real_demands, dtype=float) - total_vre_generation, 0.0
        )
        storage_net_demand = np.maximum(gross_gap - storage_discharge, 0.0)

    credit_mode = os.getenv("STORAGE_CAP_CREDIT_MODE", "scheme_c")

    kwargs = dict(
        cap_row=cap_row,
        preferred_rate=preferred_rate,
        agent_rois=agent_rois,
        preferred_rates=preferred_rates,
        excess_generation=excess_generation,
    )
    try:
        limits = sec.calculate_storage_expansion_limits_from_profiles(
            total_vre_generation,
            real_demands,
            prices,
            storage_net_demand=storage_net_demand,
            storage_discharge=storage_discharge,
            store_charge=store_charge,
            credit_mode=credit_mode,
            **kwargs,
        )
    except TypeError:
        try:
            limits = sec.calculate_storage_expansion_limits_from_profiles(
                total_vre_generation,
                real_demands,
                prices,
                storage_net_demand=storage_net_demand,
                storage_discharge=storage_discharge,
                credit_mode=credit_mode,
                **kwargs,
            )
        except TypeError:
            limits = sec.calculate_storage_expansion_limits_from_profiles(
                total_vre_generation,
                real_demands,
                prices,
                **kwargs,
            )
    return {k: v for k, v in limits.items() if k in battery_objects}


def get_asset_type(name):
    """Maps an asset name to a generic asset type."""
    if 'solar' in name.lower(): return 'solar'
    if 'onshore' in name.lower(): return 'onshore'
    if 'offshore' in name.lower(): return 'offshore'
    if '1c_battery' in name.lower(): return '1c_battery'
    if '0.5c_battery' in name.lower(): return '0.5c_battery'
    if '0.25c_battery' in name.lower(): return '0.25c_battery'
    if 'pumpedhydro' in name.lower(): return 'pumped_hydro'
    if 'hydrogen' in name.lower() and 'battery' in name.lower(): return 'hydrogen_battery'
    if 'battery' in name.lower(): return 'battery'
    if 'ccgt' in name.lower() or 'ocgt' in name.lower(): return 'gas'
    if 'bio' in name.lower(): return 'bio_and_waste'
    return name


def analyze_investment(iteration, generator_objects, battery_objects, electrolyzer_objects):
    """
    Runs the full simulation and then performs an investment analysis based on the results.
    This function is designed to be called in a loop for iterative analysis.
    """
    print(f"\n--- Starting Iteration {iteration}: Electricity Market Simulation ---")

    # -------------------------------------------------------------------------
    # 1. Prepare simulation inputs
    # -------------------------------------------------------------------------
    periods = config.simulation_parameters["periods"]
    forecast_demands0 = pd.read_csv(config.file_paths["forecast_demand"])
    real_demands0 = pd.read_csv(config.file_paths["real_demand"])
    forecast_demands = np.array(forecast_demands0).flatten()[:periods]
    real_demands = np.array(real_demands0).flatten()[:periods]
    
    generators_list = list(generator_objects.values())
    batteries_list = list(battery_objects.values())
    # 移除储能库清零，允许跨年累积
    # for bat in batteries_list:
    #     bat.set_stored_energy_var(0, 0)

    connections_list = [Connection(**params) for params in config.connections.values()]
    # Electrolyzers removed; use a zero-capacity dummy to satisfy API
    dummy_electrolyzer = Electrolyzer("electrolyzer_dummy", 0, 0, 0, 0, 0, 0, 0)


    # -------------------------------------------------------------------------
    # 2. Run the full simulation
    # -------------------------------------------------------------------------
    results = run_simulation(periods, generators_list, batteries_list, forecast_demands, real_demands, connections_list, dummy_electrolyzer)
    
    gen_list_composition = results[20]
    # Note: simulation_model.py returns blackout_periods as the last item, so indices are shifted by 1
    # simuold.py: ..., total_income_dict(-7), ..., renewable_hy_dict(-3), flexible_demand_list(-2), interconnector_exports_list(-1)
    # simulation_model.py: ..., total_income_dict(-8), ..., renewable_hy_dict(-4), flexible_demand_list(-3), interconnector_exports_list(-2), blackout_periods(-1)
    total_income_dict = results[-8]  # Changed from -7 to -8 due to blackout_periods being added
    renewable_hy_dict = results[-4]  # Changed from -3 to -4 due to blackout_periods being added
    flexible_demand_list = []  # Electrolyzer flexible demand disabled

    # Ensure total_income_dict values are numeric (simulation may return lists per period)
    def safe_sum(value):
        if isinstance(value, list):
            total = 0
            for item in value:
                if isinstance(item, (int, float)):
                    total += item
                elif isinstance(item, list):
                    total += safe_sum(item)
            return total
        elif isinstance(value, (int, float)):
            return float(value)
        return 0.0

    clean_income_dict = {}
    for key, value in total_income_dict.items():
        clean_income_dict[key] = safe_sum(value) if value is not None else 0.0

    # -------------------------------------------------------------------------
    # CRITICAL: Remap income from simulation asset.name to config keys
    # -------------------------------------------------------------------------
    # Simulation uses Battery.name from config "name" field (e.g. thermal_battery)
    # but analysis uses config dict keys (e.g. 1c_battery). Without remapping,
    # battery income is dropped and batteries get zero income → no Invest_High.
    battery_name_mapping = {
        'thermal_battery': '1c_battery',
        'li_battery': '0.5c_battery',
        'air_battery': '0.25c_battery',
        'pumpedhydro_battery': 'pumpedhydro_battery',
        'hydrogen_battery': 'hydrogen_battery'
    }
    for sim_name, config_key in battery_name_mapping.items():
        if sim_name in clean_income_dict and sim_name != config_key:
            clean_income_dict[config_key] = clean_income_dict.get(config_key, 0.0) + clean_income_dict[sim_name]
            del clean_income_dict[sim_name]

    # Debug: Check which generators participated in simulation but have no income
    if iteration == 1:
        generators_in_simulation = set(generator_objects.keys())
        generators_with_income = set(clean_income_dict.keys())
        generators_no_income = generators_in_simulation - generators_with_income
        if generators_no_income:
            print(f"--- Iteration {iteration}: {len(generators_no_income)} generators participated in simulation but have no income ---")
            print(f"  (This is normal if they were never selected in bidding due to high bid prices or zero capacity)")
    
    # The result is a list of tuples, e.g., [(gen_obj, energy), ...], convert to dict for easy lookup
    excess_energy_list = results[-5]  # Changed from -4 to -5 due to blackout_periods being added
    # Check if the list items are tuples of (object, value) and convert
    if excess_energy_list and isinstance(excess_energy_list[0], tuple) and len(excess_energy_list[0]) > 1:
        excess_energy_final_dict = {item[0].name: item[1] for item in excess_energy_list if hasattr(item[0], 'name')}
    else:
        excess_energy_final_dict = {} # Or handle as an empty list if conversion is not possible


    print(f"--- Iteration {iteration}: Simulation Finished. Starting Investment Analysis ---")

    # -------------------------------------------------------------------------
    # 3. Process results to calculate revenues and operational costs
    # -------------------------------------------------------------------------
    total_energy_generated = {}
    for period_data in gen_list_composition:
        for asset, energy in period_data:
            if not isinstance(asset, Battery):
                asset_name = asset.name
                total_energy_generated[asset_name] = total_energy_generated.get(asset_name, 0) + energy

    total_operational_costs = {
        asset.name: total_energy_generated.get(asset.name, 0) * PHYSICAL_PERIOD_HOURS * asset.gen_cost
        for asset in generators_list
    }
    
    df_income = pd.Series(clean_income_dict, name='electricity_income').to_frame()
    df_income.index.name = 'asset_name'
    df_op_costs = pd.Series(total_operational_costs, name='operational_cost').to_frame()
    df_op_costs.index.name = 'asset_name'

    hydrogen_income = {}
    H2_PRICE_PER_KG = config.investment_parameters['hydrogen_price_per_kg']
    for _, productions in renewable_hy_dict.items():
        if isinstance(productions, list):
            for gen_obj, _, hy_kg in productions:
                revenue = hy_kg * PHYSICAL_PERIOD_HOURS * H2_PRICE_PER_KG
                hydrogen_income[gen_obj.name] = hydrogen_income.get(gen_obj.name, 0) + revenue
    
    df_hydrogen = pd.DataFrame.from_dict(hydrogen_income, orient='index', columns=['hydrogen_income'])
    df_hydrogen.index.name = 'asset_name'

    df_analysis = pd.merge(df_income, df_hydrogen, on='asset_name', how='outer').fillna(0)
    df_analysis = pd.merge(df_analysis, df_op_costs, on='asset_name', how='left').fillna(0)
    
    # Define valid asset names (all 54 agents: generators + batteries)
    valid_asset_names = set(generator_objects.keys()) | set(battery_objects.keys())
    
    # Filter out invalid assets (Interconnect, REPD project names, etc.)
    invalid_assets = [name for name in df_analysis.index if name not in valid_asset_names]
    if invalid_assets:
        print(f"--- Iteration {iteration}: Filtering out {len(invalid_assets)} non-investable assets ---")
        # Group invalid assets by type for better debugging
        invalid_by_type = {}
        for name in invalid_assets:
            # Check if it looks like a REPD project name (contains common REPD patterns)
            if any(keyword in name for keyword in ['Site', 'Farm', 'Park', 'Project', 'Wind', 'Solar', 'Energy']):
                asset_type = 'REPD_project_name'
            elif 'Interconnect' in name:
                asset_type = 'Interconnect'
            else:
                asset_type = 'other'
            if asset_type not in invalid_by_type:
                invalid_by_type[asset_type] = []
            invalid_by_type[asset_type].append(name)
        
        for asset_type, names in invalid_by_type.items():
            print(f"  - {asset_type}: {len(names)} assets - {', '.join(names[:5])}{'...' if len(names) > 5 else ''}")
    
    # Remove invalid assets
    df_analysis = df_analysis[df_analysis.index.isin(valid_asset_names)]
    
    # Ensure ALL valid assets are included in the analysis
    # Note: income_dict only contains generators/batteries that were selected in bidding
    # If a generator has capacity > 0 but no income, it means it was never selected (e.g., bid price too high)
    # We still include it in analysis with zero income so all 54 agents appear
    missing_assets = valid_asset_names - set(df_analysis.index)
    if missing_assets:
        if iteration == 1:
            print(f"--- Iteration {iteration}: {len(missing_assets)} assets had no income in simulation (not selected in bidding) ---")
            # Check why they have no income - show capacity and gen_cost
            for asset_name in sorted(missing_assets):
                if asset_name in generator_objects:
                    asset = generator_objects[asset_name]
                    if isinstance(asset, ExpensiverenewableGenerator):
                        BASE_WIND = 20
                        BASE_SOLAR = 1
                        asset_type = get_asset_type(asset_name)
                        base = BASE_WIND if asset_type in ('onshore', 'offshore') else BASE_SOLAR
                        capacity_mw = asset.capacity_multiplier * base
                    else:
                        capacity_mw = asset.capacity_limit
                    gen_cost = asset.gen_cost if hasattr(asset, 'gen_cost') else 'N/A'
                    print(f"  - {asset_name}: capacity={capacity_mw:.2f} MW, gen_cost={gen_cost}, but never selected in bidding")
                elif asset_name in battery_objects:
                    asset = battery_objects[asset_name]
                    capacity_mw = asset.pool_limit
                    print(f"  - {asset_name}: capacity={capacity_mw:.2f} MW, but no income recorded")
        
        # Add them to analysis with zero income so all 54 agents appear
        for asset_name in missing_assets:
            df_analysis.loc[asset_name] = {
                'electricity_income': 0.0,
                'hydrogen_income': 0.0,
                'operational_cost': 0.0
            }
    
    # Debug: Print summary of assets in analysis
    if iteration == 1:
        print(f"--- Iteration {iteration}: Investment analysis includes {len(df_analysis)} assets (all {len(valid_asset_names)} valid agents) ---")
        # Show breakdown by asset type
        asset_type_counts = {}
        for name in df_analysis.index:
            asset_type = get_asset_type(name)
            asset_type_counts[asset_type] = asset_type_counts.get(asset_type, 0) + 1
        print(f"  Asset breakdown: {', '.join([f'{k}: {v}' for k, v in sorted(asset_type_counts.items())])}")
    
    df_analysis['total_income'] = df_analysis['electricity_income'] + df_analysis['hydrogen_income']
    df_analysis['net_revenue'] = df_analysis['total_income'] - df_analysis['operational_cost']

    # -------------------------------------------------------------------------
    # 4. Fetch capital costs and calculate payback period
    # -------------------------------------------------------------------------

    # Fetch the *current* capital cost from the asset objects, not the initial config
    current_capital_costs = {name: asset.capital_cost for name, asset in {**generator_objects, **battery_objects}.items() if hasattr(asset, 'capital_cost')}
    df_analysis['capital_cost'] = df_analysis.index.map(lambda name: current_capital_costs.get(name, 0))

    df_analysis['payback_years'] = np.where(df_analysis['net_revenue'] > 0, df_analysis['capital_cost'] / df_analysis['net_revenue'], np.inf)

    # -------------------------------------------------------------------------
    # 5. Generate investment recommendations using the new Four-Tiered Methodology
    # -------------------------------------------------------------------------
    df_analysis['asset_type'] = df_analysis.index.map(get_asset_type)

    # Get parameters for decision making
    preferred_rates = config.investment_methodology_external['preferred_rates']
    payback_targets = config.investment_parameters['target_payback_years']
    
    df_analysis['preferred_rate'] = df_analysis['asset_type'].map(preferred_rates)
    df_analysis['target_payback'] = df_analysis['asset_type'].map(payback_targets).fillna(payback_targets['default'])
    df_analysis['ROI'] = df_analysis['net_revenue'] / df_analysis['capital_cost'].replace(0, np.nan)

    # Determine investment tier based on the four-tiered logic
    def assign_recommendation(row):
        if row['ROI'] > row['preferred_rate']:
            return 'Invest_High'  # Tier 1: Highly Profitable
        elif row['payback_years'] <= row['target_payback']:
            return 'Invest_Profit' # Tier 2: Moderately Profitable
        elif row['net_revenue'] < 0:
            return 'Deplete'      # Tier 4: Unprofitable
        else:
            return 'Do_Nothing'   # Tier 3: Marginally Profitable
            
    df_analysis['recommendation'] = df_analysis.apply(assign_recommendation, axis=1)

    # --- Calculate the suggested new capacity based on the recommendation ---
    current_capacities = {}
    BASE_WIND_UNIT_MW = 20  # Base capacity of a single wind turbine or unit
    BASE_SOLAR_UNIT_MW = 1   # Base capacity of a single solar unit
    for name, asset in {**generator_objects, **battery_objects}.items():
        asset_type = get_asset_type(name)
        if isinstance(asset, (GasGenerator, BiomassGenerator, WaterGenerator, NuclearGenerator)):
            current_capacities[name] = asset.capacity_limit
        elif isinstance(asset, ExpensiverenewableGenerator):
            if asset_type in ['onshore', 'offshore']:
                current_capacities[name] = asset.capacity_multiplier * BASE_WIND_UNIT_MW
            elif asset_type == 'solar':
                current_capacities[name] = asset.capacity_multiplier * BASE_SOLAR_UNIT_MW
            else:
                current_capacities[name] = asset.capacity_multiplier # Fallback
        elif isinstance(asset, Battery):
            current_capacities[name] = asset.pool_limit
    df_analysis['current_capacity'] = df_analysis.index.map(current_capacities)

    # Get aggressive expansion targets for the 'Invest_High' tier
    solar_limit = 0.03*calculate_expansion_limit('2022reald.csv', 'sa.csv')
    wind_limit = 0.03*calculate_expansion_limit('2022reald.csv', 'wa.csv')
    _sec, _ase = _import_storage_expansion_modules()

    cap_row = _sec.build_cap_row_from_batteries(battery_objects)
    agent_rois: dict[str, float] = {}
    for bat_key in _sec.EXPANDABLE_STORAGE_KEYS:
        bat_rows = df_analysis[df_analysis["asset_type"] == bat_key]
        if not bat_rows.empty:
            agent_rois[bat_key] = float(bat_rows["ROI"].max())

    storage_limits = calculate_storage_expansion_limit(
        results,
        battery_objects,
        real_demands,
        preferred_rate=0.08,
        cap_row=cap_row,
        agent_rois=agent_rois,
    )
    regulated_targets = config.investment_methodology_external['regulated_capacity_targets'].copy()
    regulated_targets['solar'] = solar_limit
    regulated_targets['onshore'] = wind_limit
    regulated_targets['offshore'] = wind_limit
    regulated_targets.update(storage_limits)

    def _profit_based_addition_mw(row) -> float:
        """Invest_Profit rule: fund expansion from own net revenue / CAPEX."""
        cost_per_mw = config.capital_costs_per_mw.get(row["asset_type"])
        if cost_per_mw and cost_per_mw > 0 and float(row["net_revenue"]) > 0:
            return float(row["net_revenue"]) / float(cost_per_mw)
        return 0.0

    def calculate_new_capacity(row):
        asset_type = row['asset_type']
        
        if row['recommendation'] == 'Invest_High':
            # This function now ONLY handles the multiplier-based expansions for this tier
            if asset_type in ['CCGT', 'OCGT', 'bio_and_waste']:
                target = regulated_targets.get(asset_type) or regulated_targets.get(row.name)
                return row['current_capacity'] * target  # Multiplier-based
            elif asset_type in _sec.EXPANDABLE_STORAGE_KEYS:
                # Residual/frequency cap is Invest_High headroom; never below Invest_Profit.
                cap_addition = float(regulated_targets.get(asset_type, 0) or 0)
                profit_addition = _profit_based_addition_mw(row)
                return row['current_capacity'] + max(cap_addition, profit_addition)
            else:
                cost_per_mw = config.capital_costs_per_mw.get(asset_type)
                if cost_per_mw and cost_per_mw > 0:
                    capacity_to_add = row['net_revenue'] / cost_per_mw
                    return row['current_capacity'] + capacity_to_add
                return row['current_capacity']
        
        elif row['recommendation'] == 'Invest_Profit':
            return row['current_capacity'] + _profit_based_addition_mw(row)
        
        elif row['recommendation'] == 'Deplete':
            cost_per_mw = config.capital_costs_per_mw.get(asset_type)
            if cost_per_mw and cost_per_mw > 0:
                losses = abs(row['net_revenue'])
                target_payback = row['target_payback']
                depleted_capital_value = losses * target_payback
                capacity_to_remove = depleted_capital_value / cost_per_mw
                # Ensure capacity does not go below zero
                return max(0, row['current_capacity'] - capacity_to_remove)

        # Default for 'Do_Nothing' or cases with missing cost data
        return row['current_capacity']

    df_analysis['suggested_new_capacity'] = df_analysis.apply(calculate_new_capacity, axis=1)

    # --- New Step: Handle Proportional Allocation for VRE/Battery 'Invest_High' ---

    # Calculate total current capacity for each technology type
    tech_capacity_totals = df_analysis.groupby('asset_type')['current_capacity'].sum().to_dict()

    # Identify which technologies have a fixed MW expansion target
    vre_battery_techs = ['solar', 'onshore', 'offshore', '1c_battery', '0.5c_battery', '0.25c_battery', 'hydrogen_battery']

    battery_techs = {"1c_battery", "0.5c_battery", "0.25c_battery", "hydrogen_battery"}

    for tech_type in vre_battery_techs:
        # Regulated targets are annual expansion ceilings, not mandatory builds.
        annual_expansion_cap_mw = float(regulated_targets.get(tech_type, 0) or 0)
        if tech_type in battery_techs:
            # Residual/frequency cap applies only to Invest_High (not Invest_Profit).
            tech_agent_indices = df_analysis[
                (df_analysis["asset_type"] == tech_type)
                & (df_analysis["recommendation"] == "Invest_High")
            ].index
        else:
            tech_agent_indices = df_analysis[df_analysis["asset_type"] == tech_type].index
        if len(tech_agent_indices) == 0:
            continue

        current_caps = df_analysis.loc[tech_agent_indices, 'current_capacity'].astype(float)
        proposed_caps = df_analysis.loc[tech_agent_indices, 'suggested_new_capacity'].astype(float)
        proposed_additions = (proposed_caps - current_caps).clip(lower=0)
        total_proposed_addition = float(proposed_additions.sum())
        if total_proposed_addition <= 0:
            continue

        if tech_type in battery_techs:
            profit_floors = pd.Series(
                {
                    idx: _profit_based_addition_mw(df_analysis.loc[idx])
                    for idx in tech_agent_indices
                },
                dtype=float,
            )
            floor_total = float(profit_floors.sum())
            allowed_addition = max(
                floor_total,
                min(total_proposed_addition, max(annual_expansion_cap_mw, 0.0)),
            )
            if allowed_addition <= 0:
                df_analysis.loc[tech_agent_indices, "suggested_new_capacity"] = current_caps
                continue
            scale = allowed_addition / total_proposed_addition
            scaled = current_caps + proposed_additions * scale
            floored = current_caps + profit_floors
            df_analysis.loc[tech_agent_indices, "suggested_new_capacity"] = np.maximum(
                scaled, floored
            )
        else:
            allowed_addition = min(total_proposed_addition, max(annual_expansion_cap_mw, 0.0))
            if allowed_addition <= 0:
                df_analysis.loc[tech_agent_indices, 'suggested_new_capacity'] = current_caps
                continue

            scale = allowed_addition / total_proposed_addition
            df_analysis.loc[tech_agent_indices, 'suggested_new_capacity'] = current_caps + proposed_additions * scale

    # -------------------------------------------------------------------------
    # 6. External Investment Methodology (for analysis/output only)
    # -------------------------------------------------------------------------
    df_analysis['external_investment_recommendation'] = np.where(df_analysis['ROI'] > df_analysis['preferred_rate'], 'External Invest', 'No External Investment')
    
    def calculate_regulated_capacity(row):
        if row['external_investment_recommendation'] == 'External Invest':
            asset_type = row['asset_type']
            target = regulated_targets.get(asset_type) or regulated_targets.get(row.name)

            if asset_type in ['CCGT', 'OCGT', 'bio_and_waste', 'electrolyzer']:
                return row['current_capacity'] * target
            else:
                return target
        return row['current_capacity']

    df_analysis['suggested_capacity_external'] = df_analysis.apply(calculate_regulated_capacity, axis=1)


    # -------------------------------------------------------------------------
    # 8. VRE Expansion Trade-off: Generation vs. Attached Electrolyzer
    # -------------------------------------------------------------------------
    df_analysis['expand_electrolyzer'] = False
    vre_investments = df_analysis[
        (df_analysis['recommendation'].isin(['Invest_High', 'Invest_Profit'])) & 
        (df_analysis['asset_type'].isin(['solar', 'onshore', 'offshore']))
    ]

    for asset_name, row in vre_investments.iterrows():
        # Energy used for hydrogen production by this VRE
        energy_for_hydrogen = excess_energy_final_dict.get(asset_name, 0)
        
        # Income from hydrogen for this VRE
        hydrogen_income = row['hydrogen_income']
        
        # Income from electricity for this VRE
        electricity_income = row['electricity_income']
        
        # To get electricity sold, we need total energy generated for the asset
        total_energy = total_energy_generated.get(asset_name, 0)
        energy_sold_as_electricity = total_energy - energy_for_hydrogen

        if energy_sold_as_electricity > 0 and energy_for_hydrogen > 0:
            # Calculate the average revenue per MWh for each stream
            avg_rev_per_mwh_elec = electricity_income / energy_sold_as_electricity
            avg_rev_per_mwh_hydro = hydrogen_income / energy_for_hydrogen

            # If hydrogen revenue per MWh is higher, prioritize electrolyzer expansion
            if avg_rev_per_mwh_hydro > avg_rev_per_mwh_elec:
                df_analysis.loc[asset_name, 'expand_electrolyzer'] = True
                # Divert the capacity expansion from the generator to its electrolyzer
                # Note: This assumes a 1-to-1 MW capacity trade-off logic for simplicity
                new_electrolyzer_capacity = generator_objects[asset_name].electrolyzer_limit * (1 + INVEST_INCREMENT)
                
                # We modify the 'suggested_new_capacity' to be the electrolyzer's new capacity
                # And keep the generator's capacity the same.
                df_analysis.loc[asset_name, 'suggested_new_capacity'] = row['current_capacity'] # Keep generator capacity
                
                # Store the suggested new electrolyzer capacity in a new column for clarity
                df_analysis.loc[asset_name, 'suggested_electrolyzer_capacity'] = new_electrolyzer_capacity


    # -------------------------------------------------------------------------
    # 7. Add comprehensive electrolyzer analysis
    # -------------------------------------------------------------------------
    
    # Collect electrolyzer performance and expansion data
    electrolyzer_results = {}
    
    # Public electrolyzer results
    for name, electrolyzer_obj in electrolyzer_objects.items():
        if hasattr(electrolyzer_obj, 'real_energy'):
            total_energy_consumed = sum(flexible_demand_list) if flexible_demand_list else 0
            capacity_utilization = (total_energy_consumed / (electrolyzer_obj.capacity_limit * periods * 0.5)) * 100 if electrolyzer_obj.capacity_limit > 0 else 0
            
            electrolyzer_results[name] = {
                'type': 'public',
                'current_capacity_mw': electrolyzer_obj.capacity_limit,
                'energy_consumed_mwh': total_energy_consumed,
                'capacity_utilization_percent': capacity_utilization,
                'hydrogen_production_kg': total_energy_consumed * electrolyzer_obj.energy_efficiency if hasattr(electrolyzer_obj, 'energy_efficiency') else 0,
                'investment_recommendation': 'Invest' if capacity_utilization > 70 else 'Do Not Invest',
                'suggested_expansion_mw': electrolyzer_obj.capacity_limit * INVEST_INCREMENT if capacity_utilization > 70 else 0
            }
    
    # Attached electrolyzer results (from VRE)
    for asset_name in df_analysis.index:
        if asset_name in generator_objects and hasattr(generator_objects[asset_name], 'electrolyzer_limit'):
            gen_obj = generator_objects[asset_name]
            if gen_obj.electrolyzer_limit > 0:
                # Get hydrogen production for this VRE
                hydrogen_income = df_analysis.loc[asset_name, 'hydrogen_income'] if 'hydrogen_income' in df_analysis.columns else 0
                energy_for_hydrogen = excess_energy_final_dict.get(asset_name, 0)
                
                # Calculate metrics
                capacity_utilization = 0
                if gen_obj.electrolyzer_limit > 0 and periods > 0:
                    max_possible_energy = gen_obj.electrolyzer_limit * periods * 0.5
                    capacity_utilization = (energy_for_hydrogen / max_possible_energy) * 100 if max_possible_energy > 0 else 0
                
                electrolyzer_results[f"{asset_name}_electrolyzer"] = {
                    'type': 'attached',
                    'parent_asset': asset_name,
                    'current_capacity_mw': gen_obj.electrolyzer_limit,
                    'energy_consumed_mwh': energy_for_hydrogen,
                    'capacity_utilization_percent': capacity_utilization,
                    'hydrogen_income': hydrogen_income,
                    'hydrogen_production_kg': energy_for_hydrogen * gen_obj.energy_efficiency if hasattr(gen_obj, 'energy_efficiency') else 0,
                    'expansion_recommended': df_analysis.loc[asset_name, 'expand_electrolyzer'] if 'expand_electrolyzer' in df_analysis.columns else False,
                    'suggested_expansion_mw': df_analysis.loc[asset_name, 'suggested_electrolyzer_capacity'] - gen_obj.electrolyzer_limit if 'suggested_electrolyzer_capacity' in df_analysis.columns else 0
                }
    
    # Add electrolyzer results to the analysis dataframe for reference
    df_analysis.attrs['electrolyzer_results'] = electrolyzer_results

    # -------------------------------------------------------------------------
    # 8. Save and return the analysis
    # -------------------------------------------------------------------------
    output_filename = f'investment_analysis_iter_{iteration}.xlsx'
    with pd.ExcelWriter(output_filename, engine='xlsxwriter') as writer:
        # Write main investment analysis
        df_analysis.to_excel(writer, sheet_name='Investment Analysis', index=True)
        for column in df_analysis:
            column_length = max(df_analysis[column].astype(str).map(len).max(), len(column))
            col_idx = df_analysis.columns.get_loc(column) + 1
            writer.sheets['Investment Analysis'].set_column(col_idx, col_idx, column_length)
        
        # Write electrolyzer analysis if available
        if electrolyzer_results:
            df_electrolyzer = pd.DataFrame.from_dict(electrolyzer_results, orient='index')
            df_electrolyzer.to_excel(writer, sheet_name='Electrolyzer Analysis', index=True)
    
    print(f"--- Iteration {iteration}: Analysis complete. Results saved to '{output_filename}' ---")
    if electrolyzer_results:
        print(f"--- Electrolyzer analysis included with {len(electrolyzer_results)} electrolyzers ---")
    
    return df_analysis

def extract_model_decisions():
    """
    Extract model investment decisions made in 2024 and 2025 from the analysis results.
    This function should be called after running the main analysis to capture decisions.
    """
    model_decisions_2024_2025 = []
    
    # Check if investment summary files exist
    try:
        df_summary = pd.read_csv('investment_summary.csv')
        
        # Filter for decisions made in 2024 and 2025 (these are decisions for future years)
        # Year in the summary represents when capacity comes online, 
        # so we need to look at decisions made by the model in iterations 2 and 3 (modeling years 2024 and 2025)
        model_decisions = df_summary[df_summary['Source'] == 'model']
        
        # Group by asset type and year to get total model decisions
        model_summary = model_decisions.groupby(['Year', 'Asset']).agg({
            'Added_Capacity_MW': 'sum',
            'Investment_Cost': 'sum'
        }).reset_index()
        
        return model_summary
        
    except FileNotFoundError:
        print("No investment_summary.csv found. Please run the main analysis first.")
        return pd.DataFrame()

def compare_model_vs_reality():
    """
    Compare model investment decisions for 2024-2025 with real-world REPD data.
    """
    print("\n" + "="*50)
    print("MODEL vs REALITY COMPARISON (2024-2025)")
    print("="*50)
    
    # 1. Extract model decisions
    model_decisions = extract_model_decisions()
    
    if model_decisions.empty:
        print("No model decisions found. Running analysis to generate decisions...")
        return
    
    # 2. Load real-world data from REPD files
    actuals = []
    repd_files = ['repd-october-2023.csv', 'repd-q1-apr-2025.csv']
    
    for file in repd_files:
        try:
            df = pd.read_csv(file, encoding='utf-8')
        except UnicodeDecodeError:
            df = pd.read_csv(file, encoding='latin1')
        
        # Convert operational date
        df['Operational'] = pd.to_datetime(df['Operational'], errors='coerce', dayfirst=True)
        df_operational = df.dropna(subset=['Operational'])
        
        for _, row in df_operational.iterrows():
            op_year = row['Operational'].year
            if 2024 <= op_year <= 2025:  # Focus on 2024-2025
                tech_type_str = row.get('Technology Type', '')
                tech_type = get_asset_type_from_repd(tech_type_str)
                capacity = pd.to_numeric(row.get('Installed Capacity (MWelec)'), errors='coerce')
                
                if tech_type and pd.notna(capacity) and capacity > 0:
                    actuals.append({
                        'Year': op_year,
                        'Technology': tech_type,
                        'Actual_Capacity_MW': capacity,
                        'Project_Name': row.get('Site Name', 'Unknown'),
                        'Status': row.get('Development Status (short)', 'Unknown'),
                        'Source_File': file
                    })
    
    if not actuals:
        print("No real-world operational data found for 2024-2025")
        return
    
    # 3. Process and aggregate data
    df_actual = pd.DataFrame(actuals)
    df_actual_summary = df_actual.groupby(['Year', 'Technology']).agg({
        'Actual_Capacity_MW': 'sum',
        'Project_Name': 'count'
    }).reset_index()
    df_actual_summary.rename(columns={'Project_Name': 'Number_of_Projects'}, inplace=True)
    
    # Process model decisions
    model_decisions['Technology'] = model_decisions['Asset'].apply(get_asset_type)
    model_summary = model_decisions.groupby(['Year', 'Technology']).agg({
        'Added_Capacity_MW': 'sum',
        'Investment_Cost': 'sum'
    }).reset_index()
    model_summary.rename(columns={'Added_Capacity_MW': 'Model_Capacity_MW'}, inplace=True)
    
    # 4. Merge and compare
    comparison = pd.merge(
        df_actual_summary, 
        model_summary[['Year', 'Technology', 'Model_Capacity_MW', 'Investment_Cost']], 
        on=['Year', 'Technology'], 
        how='outer'
    ).fillna(0)
    
    # Calculate accuracy metrics
    comparison['Capacity_Difference'] = comparison['Model_Capacity_MW'] - comparison['Actual_Capacity_MW']
    comparison['Relative_Error'] = np.where(
        comparison['Actual_Capacity_MW'] > 0,
        (comparison['Capacity_Difference'] / comparison['Actual_Capacity_MW']) * 100,
        np.inf
    )
    comparison['Absolute_Error'] = np.abs(comparison['Capacity_Difference'])
    
    # 5. Display results
    print("\nDETAILED COMPARISON TABLE:")
    print("-" * 100)
    print(f"{'Year':<6} {'Technology':<15} {'Actual (MW)':<12} {'Model (MW)':<12} {'Diff (MW)':<12} {'Error %':<10} {'Projects':<10}")
    print("-" * 100)
    
    for _, row in comparison.iterrows():
        year = int(row['Year']) if row['Year'] > 0 else 'N/A'
        tech = row['Technology'][:14]
        actual = f"{row['Actual_Capacity_MW']:.1f}" if row['Actual_Capacity_MW'] > 0 else "0.0"
        model = f"{row['Model_Capacity_MW']:.1f}" if row['Model_Capacity_MW'] > 0 else "0.0"
        diff = f"{row['Capacity_Difference']:.1f}"
        error = f"{row['Relative_Error']:.1f}%" if row['Relative_Error'] != np.inf else "N/A"
        projects = int(row['Number_of_Projects']) if row['Number_of_Projects'] > 0 else 0
        
        print(f"{year:<6} {tech:<15} {actual:<12} {model:<12} {diff:<12} {error:<10} {projects:<10}")
    
    # 6. Summary statistics
    valid_comparisons = comparison[
        (comparison['Actual_Capacity_MW'] > 0) & 
        (comparison['Model_Capacity_MW'] > 0)
    ]
    
    if not valid_comparisons.empty:
        avg_error = valid_comparisons['Absolute_Error'].mean()
        total_actual = comparison['Actual_Capacity_MW'].sum()
        total_model = comparison['Model_Capacity_MW'].sum()
        
        print("\n" + "="*50)
        print("SUMMARY STATISTICS")
        print("="*50)
        print(f"Total Actual Capacity (2024-2025): {total_actual:.1f} MW")
        print(f"Total Model Predicted Capacity: {total_model:.1f} MW")
        print(f"Total Difference: {total_model - total_actual:.1f} MW")
        print(f"Average Absolute Error: {avg_error:.1f} MW")
        
        if total_actual > 0:
            overall_error = abs(total_model - total_actual) / total_actual * 100
            print(f"Overall Relative Error: {overall_error:.1f}%")
    
    # 7. Technology-specific analysis
    print("\n" + "="*50)
    print("TECHNOLOGY-SPECIFIC ANALYSIS")
    print("="*50)
    
    tech_summary = comparison.groupby('Technology').agg({
        'Actual_Capacity_MW': 'sum',
        'Model_Capacity_MW': 'sum',
        'Number_of_Projects': 'sum'
    }).reset_index()
    
    tech_summary['Total_Difference'] = tech_summary['Model_Capacity_MW'] - tech_summary['Actual_Capacity_MW']
    
    for _, row in tech_summary.iterrows():
        if row['Actual_Capacity_MW'] > 0 or row['Model_Capacity_MW'] > 0:
            print(f"\n{row['Technology'].upper()}:")
            print(f"  Actual: {row['Actual_Capacity_MW']:.1f} MW ({int(row['Number_of_Projects'])} projects)")
            print(f"  Model:  {row['Model_Capacity_MW']:.1f} MW")
            print(f"  Difference: {row['Total_Difference']:.1f} MW")
    
    # 8. Save detailed results
    comparison.to_csv('model_vs_reality_comparison_2024_2025.csv', index=False)
    df_actual.to_csv('actual_projects_2024_2025_detailed.csv', index=False)
    
    print(f"\n" + "="*50)
    print("FILES SAVED:")
    print("- model_vs_reality_comparison_2024_2025.csv")
    print("- actual_projects_2024_2025_detailed.csv")
    print("="*50)
    
    return comparison, df_actual

def main():
    """
    Main function to run the iterative investment analysis for 10 cycles.
    """
    # Pre-defined expansion plan for Pumped Hydro based on provided table
    pumped_hydro_expansion_plan = {
        2025: 2828.00,
        2026: 2927.90,
        2027: 2927.90,
        2028: 3377.90,
        2029: 3587.90,
        2030: 4187.90,
        2031: 5687.90,
        2032: 5687.90,
        2033: 5687.90,
        2034: 5687.90,
        2035: 11387.90,
    }
    pumped_hydro_energy_storage_plan = {
        2025: 26700,  # 26.7 GWh
        2026: 27400,  # 27.4 GWh
        2027: 27400,  # 27.4 GWh
        2028: 30200,  # 30.2 GWh
        2029: 31800,  # 31.8 GWh
        2030: 40800,  # 40.8 GWh
        2031: 70800,  # 70.8 GWh
        2032: 70800,  # 70.8 GWh
        2033: 70800,  # 70.8 GWh
        2034: 70800,  # 70.8 GWh
        2035: 195800, # 195.8 GWh
    }
    pumped_hydro_capex_plan = {
        2025: 377900000, # ~£377.9m
        2026: 388500000, # ~£388.5m
        2027: 388500000, # ~£388.5m
        2028: 425100000, # ~£425.1m
        2029: 441500000, # ~£441.5m
        2030: 496800000, # ~£496.8m
        2031: 596400000, # ~£596.4m
        2032: 596400000, # ~£596.4m
        2033: 596400000, # ~£596.4m
        2034: 596400000, # ~£596.4m
        2035: 1070800000, # ~£1,070.8m
    }

    # Initialize generators and batteries from config ONCE
    generator_objects = {}
    for name, params in config.generators.items():
        if name in ["CCGT", "OCGT"]:
            generator_objects[name] = GasGenerator(**params)
        elif name == "bio_and_waste":
            generator_objects[name] = BiomassGenerator(**params)
        elif name == "Hydro_natural_flow":
            generator_objects[name] = WaterGenerator(**params)
        elif name == "Nuclear":
            generator_objects[name] = NuclearGenerator(**params)
        else:
            generator_objects[name] = ExpensiverenewableGenerator(**params)

    battery_objects = {name: Battery(**params) for name, params in config.batteries.items()}
    electrolyzer_objects = {'electrolyzer': Electrolyzer(**config.electrolyzer)}
    
    # --- Override Initial Pumped Hydro State with Schedule Baseline ---
    # The provided table is the single source of truth for this asset.
    # We set the initial state (for 2023) to the first value in the schedule (2025's data).
    if 'pumpedhydro_battery' in battery_objects:
        initial_capacity = pumped_hydro_expansion_plan[2025]
        initial_energy_storage = pumped_hydro_energy_storage_plan[2025]
        initial_capex = pumped_hydro_capex_plan[2025]
        print(f"--- Overriding initial Pumped Hydro state. Start Capacity: {initial_capacity} MW, Start CAPEX: £{initial_capex:,} ---")
        battery_objects['pumpedhydro_battery'].pool_limit = initial_capacity
        battery_objects['pumpedhydro_battery'].per_pool_limit = initial_energy_storage
        battery_objects['pumpedhydro_battery'].capital_cost = initial_capex

    # Load external projects into the pipeline
    project_pipeline = load_external_projects()
    project_pipeline, zombie_removed = filter_zombie_external_pipeline(project_pipeline)
    if zombie_removed:
        print(f"Removed {zombie_removed} schedule-zombie external projects from pipeline")
    project_pipeline, stock_removed = exclude_external_projects_already_in_stock(
        project_pipeline, snapshot_year=int(os.getenv("START_YEAR", "2025"))
    )
    if stock_removed:
        print(f"Excluded {stock_removed} external projects already in REPD operational stock")
    print("\n--- Loading Regional Technology Success Rates ---")
    success_rates = load_regional_technology_success_rates()
    project_pipeline, uncertain_repack = repackage_uncertain_repd_as_model_decisions(
        project_pipeline, success_rates
    )
    project_pipeline, clipped = normalize_external_pipeline_completion_years(project_pipeline)
    if clipped:
        print(f"Excluded {clipped} external projects scheduled before START_YEAR={os.getenv('START_YEAR', '2025')}")
    project_pipeline, deferred_start = defer_start_year_external_pipeline_completions(project_pipeline)
    if deferred_start:
        print(
            f"Deferred {deferred_start} external projects from START_YEAR={os.getenv('START_YEAR', '2025')} "
            f"to {int(os.getenv('START_YEAR', '2025')) + 1}"
        )
    
    # Load regional technology success rates
    print("\n--- Loading Regional Technology Success Rates ---")
    success_rates = load_regional_technology_success_rates()
    
    # Apply success rates to REPD projects that require it
    print("\n--- Applying Success Rates to REPD Projects ---")
    project_pipeline = apply_success_rates_to_repd_projects(project_pipeline, success_rates)

    # Map projects to generators: REPD by region (solar/onshore) or lat/lon (offshore when available)
    from map_projects_to_generators_by_location import map_projects_to_generators
    project_pipeline, _ = map_projects_to_generators(
        project_pipeline, generator_objects, repd_file='repd-q2-jul-2025.csv'
    )
    n_mapped = sum(1 for p in project_pipeline if p.get('assigned_generator') is not None)
    print(f"--- Mapped {n_mapped} / {len(project_pipeline)} projects to generators (region or lat/lon) ---")
    
    # Report on REPD success rate applications
    repd_projects_with_success_rates = [p for p in project_pipeline if p.get('success_rate_applied', False)]
    if repd_projects_with_success_rates:
        successful_repd = [p for p in repd_projects_with_success_rates if p.get('project_succeeds', True)]
        failed_repd = [p for p in repd_projects_with_success_rates if not p.get('project_succeeds', True)]
        
        total_repd_capacity = sum(p.get('capacity', 0) for p in repd_projects_with_success_rates)
        successful_repd_capacity = sum(p.get('capacity', 0) for p in successful_repd)
        failed_repd_capacity = sum(p.get('original_capacity', 0) for p in failed_repd)
        
        print(f"✓ Applied success rates to {len(repd_projects_with_success_rates)} REPD projects")
        print(f"  - Successful: {len(successful_repd)} projects ({successful_repd_capacity:.1f} MW)")
        print(f"  - Failed: {len(failed_repd)} projects ({failed_repd_capacity:.1f} MW)")
        if total_repd_capacity > 0:
            print(f"  - REPD Success Rate: {(successful_repd_capacity/(successful_repd_capacity + failed_repd_capacity))*100:.1f}%")
    
    investment_summary = []

    start_year = 2025
    for i in range(10): # Loop for 10 iterations (2025-2034)
        current_year = start_year + i
        print(f"\n{'='*20} YEAR {current_year} {'='*20}")
        
        # 每年开始前清理内存（除了第一年）
        if i > 0:
            import gc
            gc.collect()
            print(f"--- Year {current_year}: Memory cleaned ---")

        # --- Apply Pre-defined Pumped Hydro Expansion Plan ---
        if current_year in pumped_hydro_expansion_plan:
            if 'pumpedhydro_battery' in battery_objects:
                # Update Capacity
                new_capacity = pumped_hydro_expansion_plan[current_year]
                current_capacity = battery_objects['pumpedhydro_battery'].pool_limit
                if new_capacity != current_capacity:
                    print(f"--- Year {current_year}: Updating Pumped Hydro capacity as per schedule to {new_capacity} MW ---")
                    battery_objects['pumpedhydro_battery'].pool_limit = new_capacity

                # Update Energy Storage
                if current_year in pumped_hydro_energy_storage_plan:
                    new_energy_storage = pumped_hydro_energy_storage_plan[current_year]
                    current_energy_storage = battery_objects['pumpedhydro_battery'].per_pool_limit
                    if new_energy_storage != current_energy_storage:
                        print(f"--- Year {current_year}: Updating Pumped Hydro energy storage as per schedule to {new_energy_storage} MWh ---")
                        battery_objects['pumpedhydro_battery'].per_pool_limit = new_energy_storage
                
                # Update Capital Cost based on the schedule
                if current_year in pumped_hydro_capex_plan:
                    new_capex = pumped_hydro_capex_plan[current_year]
                    battery_objects['pumpedhydro_battery'].capital_cost = new_capex

        # Check for completed projects from the pipeline
        newly_added_capacity = {}
        for project in project_pipeline[:]:
            if project['completion_year'] != current_year:
                continue
            if project.get('capacity', 0) <= 0 or project.get('project_succeeds') is False:
                project_pipeline.remove(project)
                continue

                # Handle attached electrolyzer expansion
                if project.get('source') == 'model_electrolyzer':
                    target_asset_name = project['target_asset_name']
                    capacity_to_add = project['capacity']
                    if target_asset_name in generator_objects:
                        generator_objects[target_asset_name].electrolyzer_limit += capacity_to_add
                        print(f"--- Year {current_year}: ATTACHED ELECTROLYZER for {target_asset_name} expanded by {capacity_to_add:.2f} MW ---")
                    project_pipeline.remove(project)
                    continue

                asset_type = project['technology_type']

                if asset_type == 'battery':
                    apply_electrochemical_battery_expansion(
                        battery_objects,
                        project['capacity'],
                        current_year,
                        investment_summary,
                        project.get('source', 'unknown'),
                    )
                    project_pipeline.remove(project)
                    continue

                asset_name = None
                # Use assigned_generator (REPD region/lat-lon) or target_asset_name (model) so each project goes to the correct agent
                if project.get('assigned_generator') is not None:
                    asset_name = project['assigned_generator']
                elif project.get('source') == 'model' and project.get('target_asset_name'):
                    asset_name = project['target_asset_name']
                if asset_name is None:
                    # Fallback: try to find matching generator by asset_type
                    if asset_type == 'gas':
                        asset_name = next((name for name in generator_objects if 'ccgt' in name.lower()), 'CCGT')
                    else:
                        # Use get_asset_type to match properly
                        asset_name = next((name for name in {**generator_objects, **battery_objects, **electrolyzer_objects} 
                                         if get_asset_type(name) == asset_type), None)
                    
                    # If still None, skip this project (don't create new assets)
                    if asset_name is None:
                        print(f"--- Year {current_year}: WARNING - Project '{project.get('name', 'Unknown')}' (type: {asset_type}) could not be matched to any existing asset. Skipping. ---")
                        project_pipeline.remove(project)
                        continue

                # Validate that asset_name exists in generator_objects, battery_objects, or electrolyzer_objects
                if asset_name not in {**generator_objects, **battery_objects, **electrolyzer_objects}:
                    print(f"--- Year {current_year}: ERROR - Asset '{asset_name}' not found in generator/battery/electrolyzer objects. Skipping project '{project.get('name', 'Unknown')}'. ---")
                    project_pipeline.remove(project)
                    continue

                if asset_name:
                    capacity_to_add = project['capacity']
                    source = project['source']
                    
                    # Track capacity before installation for verification
                    capacity_before = None
                    if asset_name in generator_objects:
                        target_asset = generator_objects[asset_name]
                        if isinstance(target_asset, ExpensiverenewableGenerator):
                            BASE_WIND = 20
                            BASE_SOLAR = 1
                            base = BASE_WIND if asset_type in ('onshore', 'offshore') else BASE_SOLAR
                            capacity_before = target_asset.capacity_multiplier * base
                        else:
                            capacity_before = target_asset.capacity_limit
                    elif asset_name in battery_objects:
                        target_asset = battery_objects[asset_name]
                        capacity_before = target_asset.pool_limit
                    elif asset_name in electrolyzer_objects:
                        target_asset = electrolyzer_objects[asset_name]
                        capacity_before = target_asset.capacity_limit
                    
                    cost_per_mw = config.capital_costs_per_mw.get(asset_type, 0)
                    investment_cost = capacity_to_add * cost_per_mw
                    
                    target_asset = None
                    BASE_WIND = 20
                    BASE_SOLAR = 1
                    if asset_name in generator_objects:
                        target_asset = generator_objects[asset_name]
                        if isinstance(target_asset, ExpensiverenewableGenerator):
                            base = BASE_WIND if asset_type in ('onshore', 'offshore') else BASE_SOLAR
                            old_multiplier = target_asset.capacity_multiplier
                            target_asset.capacity_multiplier += capacity_to_add / base
                            # Verify installation
                            capacity_after = target_asset.capacity_multiplier * base
                            actual_capacity_added = capacity_after - capacity_before
                            if abs(actual_capacity_added - capacity_to_add) > 0.01:
                                print(f"  ⚠ WARNING: Capacity mismatch for {asset_name}: expected {capacity_to_add:.2f} MW, actual {actual_capacity_added:.2f} MW")
                        else:
                            old_capacity = target_asset.capacity_limit
                            target_asset.capacity_limit += capacity_to_add
                            # Verify installation
                            actual_capacity_added = target_asset.capacity_limit - old_capacity
                            if abs(actual_capacity_added - capacity_to_add) > 0.01:
                                print(f"  ⚠ WARNING: Capacity mismatch for {asset_name}: expected {capacity_to_add:.2f} MW, actual {actual_capacity_added:.2f} MW")
                    elif asset_name in battery_objects:
                        target_asset = battery_objects[asset_name]
                        old_capacity = target_asset.pool_limit
                        target_asset.pool_limit = max(0, target_asset.pool_limit + capacity_to_add)
                        _sec, _ase = _import_storage_expansion_modules()
                        _sec.sync_battery_pool_limits(battery_objects, asset_name)
                        actual_capacity_added = target_asset.pool_limit - old_capacity
                        if abs(actual_capacity_added - capacity_to_add) > 0.01:
                            print(f"  ⚠ WARNING: Capacity mismatch for {asset_name}: expected {capacity_to_add:.2f} MW, actual {actual_capacity_added:.2f} MW (clamped to non-negative)")
                    elif asset_name in electrolyzer_objects:
                        target_asset = electrolyzer_objects[asset_name]
                        old_capacity = target_asset.capacity_limit
                        target_asset.capacity_limit += capacity_to_add
                        # Verify installation
                        actual_capacity_added = target_asset.capacity_limit - old_capacity
                        if abs(actual_capacity_added - capacity_to_add) > 0.01:
                            print(f"  ⚠ WARNING: Capacity mismatch for {asset_name}: expected {capacity_to_add:.2f} MW, actual {actual_capacity_added:.2f} MW")
                    
                    # Update the asset's cumulative capital cost
                    if target_asset:
                        if not hasattr(target_asset, 'capital_cost'):
                            target_asset.capital_cost = 0
                        target_asset.capital_cost += investment_cost

                    key = (asset_name, source)
                    newly_added_capacity[key] = newly_added_capacity.get(key, 0) + capacity_to_add
                    investment_summary.append({
                        'Year': current_year, 
                        'Asset': asset_name, 
                        'Source': source, 
                        'Added_Capacity_MW': capacity_to_add,
                        'Investment_Cost': investment_cost
                    })
                    project_pipeline.remove(project)
        
        if newly_added_capacity:
            print(f"\n--- Year {current_year}: New Capacities Online ---")
            summary_df = pd.DataFrame([
                {'Asset': k[0], 'Source': k[1], 'Capacity_MW': v} for k, v in newly_added_capacity.items()
            ])
            print(summary_df.to_string(index=False))
            
            # Verify total capacity installed matches expected
            total_installed = sum(newly_added_capacity.values())
            print(f"  ✓ Total capacity installed this year: {total_installed:.2f} MW")
            
            # Show breakdown by source
            by_source = {}
            for (asset, source), capacity in newly_added_capacity.items():
                by_source[source] = by_source.get(source, 0) + capacity
            print(f"  Breakdown by source: {', '.join([f'{k}: {v:.2f} MW' for k, v in by_source.items()])}")

        df_analysis = analyze_investment(i + 1, generator_objects, battery_objects, electrolyzer_objects)
        
        # Extract and display electrolyzer results for this iteration
        if hasattr(df_analysis, 'attrs') and 'electrolyzer_results' in df_analysis.attrs:
            electrolyzer_results = df_analysis.attrs['electrolyzer_results']
            display_iteration_electrolyzer_summary(current_year, electrolyzer_results)
        
        # 清理内存，避免内存溢出
        import gc
        gc.collect()
        
        # Add new model-driven investments to the pipeline
        model_investment_summary = {}  # Track model investments by asset
        for asset_name, row in df_analysis.iterrows():
            # Check for any recommendation that involves a capacity change (Invest or Deplete)
            if row['recommendation'] != 'Do_Nothing':
                capacity_to_add = row['suggested_new_capacity'] - row['current_capacity']
                
                # Skip if there's no actual change in capacity
                if abs(capacity_to_add) < 1e-6:
                    continue

                # Handle the special case of VRE electrolyzer expansion
                if row.get('expand_electrolyzer', False):
                    target_asset = generator_objects[asset_name]
                    new_capacity = row['suggested_electrolyzer_capacity']
                    electrolyzer_capacity_to_add = new_capacity - target_asset.electrolyzer_limit
                    
                    print(f"--- Year {current_year}: Model decision for {asset_name}: Expanding ATTACHED ELECTROLYZER to {new_capacity:.2f} MW (adding {electrolyzer_capacity_to_add:.2f} MW) ---")
                    
                    project_pipeline.append({
                        'name': f"Model Investment: {asset_name} Electrolyzer",
                        'technology_type': 'electrolyzer_attached',
                        'capacity': electrolyzer_capacity_to_add,
                        'completion_year': current_year + 1,
                        'source': 'model_electrolyzer',
                        'target_asset_name': asset_name
                    })
                    
                    # Track electrolyzer investment
                    if asset_name not in model_investment_summary:
                        model_investment_summary[asset_name] = {'generator': 0, 'electrolyzer': 0}
                    model_investment_summary[asset_name]['electrolyzer'] = electrolyzer_capacity_to_add

                else:  # Handle standard generator/battery investment or depletion
                    asset_type = get_asset_type(asset_name)
                    append_model_investment_to_pipeline(
                        project_pipeline,
                        name=f"Model Decision: {asset_name}",
                        technology_type=asset_type,
                        capacity=capacity_to_add,
                        decision_year=current_year,
                        target_asset_name=asset_name,
                        success_rates=success_rates,
                        assigned_generator=asset_name,
                    )

                    if asset_name not in model_investment_summary:
                        model_investment_summary[asset_name] = {'generator': 0, 'electrolyzer': 0}
                    model_investment_summary[asset_name]['generator'] = capacity_to_add
        
        # Print summary of model investments added to pipeline
        if model_investment_summary:
            print(f"\n--- Year {current_year}: Model Investment Decisions Added to Pipeline ---")
            total_gen_capacity = sum(v['generator'] for v in model_investment_summary.values())
            total_elec_capacity = sum(v['electrolyzer'] for v in model_investment_summary.values())
            print(f"  Total Generator/Battery Capacity: {total_gen_capacity:.2f} MW")
            print(f"  Total Electrolyzer Capacity: {total_elec_capacity:.2f} MW")
            print(f"  Investments for {len(model_investment_summary)} assets")

    # Backfill success rates for legacy model projects loaded from old checkpoints only.
    legacy_model = [
        p for p in project_pipeline
        if p.get("source") == "model" and not p.get("success_rate_applied")
    ]
    if legacy_model:
        print("\n--- Applying success rates to legacy model pipeline entries ---")
        updated = apply_success_rates_to_model_investments(legacy_model, success_rates)
        by_name = {p["name"]: p for p in updated}
        project_pipeline = [by_name.get(p.get("name"), p) for p in project_pipeline]

    model_projects = [p for p in project_pipeline if p.get('success_rate_applied', False)]
    if model_projects:
        successful_projects = [p for p in model_projects if p.get('project_succeeds', True)]
        failed_projects = [p for p in model_projects if not p.get('project_succeeds', True)]
        
        total_model_capacity = sum(p.get('original_capacity', p.get('capacity', 0)) for p in model_projects)
        successful_capacity = sum(p.get('capacity', 0) for p in successful_projects)
        failed_capacity = sum(p.get('original_capacity', 0) for p in failed_projects)
        
        print(f"✓ Applied success rates to {len(model_projects)} model investment projects")
        print(f"  - Successful: {len(successful_projects)} projects ({successful_capacity:.1f} MW)")
        print(f"  - Failed: {len(failed_projects)} projects ({failed_capacity:.1f} MW)")
        print(f"  - Overall Success Rate: {(successful_capacity/total_model_capacity)*100:.1f}%" if total_model_capacity > 0 else "  - No capacity to analyze")
    
    print("\n--- Summary of All Capacity Additions Over 10 Years ---")
    df_summary = pd.DataFrame(investment_summary)
    if not df_summary.empty:
        print(df_summary.to_string())
        df_summary.to_csv('investment_summary.csv', index=False)
        print("\nFull summary saved to 'investment_summary.csv'")
        
        # Generate electrolyzer-specific summary
        electrolyzer_investments = df_summary[
            (df_summary['Asset'].str.contains('electrolyzer', case=False, na=False)) |
            (df_summary['Source'] == 'model_electrolyzer')
        ]
        
        if not electrolyzer_investments.empty:
            print("\n" + "="*50)
            print("ELECTROLYZER EXPANSION SUMMARY")
            print("="*50)
            print(electrolyzer_investments.to_string(index=False))
            
            # Summary statistics for electrolyzers
            total_electrolyzer_capacity = electrolyzer_investments['Added_Capacity_MW'].sum()
            total_electrolyzer_investment = electrolyzer_investments['Investment_Cost'].sum()
            
            print(f"\nTotal Electrolyzer Capacity Added: {total_electrolyzer_capacity:.1f} MW")
            print(f"Total Electrolyzer Investment: £{total_electrolyzer_investment:,.0f}")
            
            # Breakdown by type
            print("\nBreakdown by Electrolyzer Type:")
            attached_electrolyzers = electrolyzer_investments[electrolyzer_investments['Source'] == 'model_electrolyzer']
            public_electrolyzers = electrolyzer_investments[
                electrolyzer_investments['Asset'].str.contains('electrolyzer', case=False, na=False) &
                (electrolyzer_investments['Source'] != 'model_electrolyzer')
            ]
            
            if not attached_electrolyzers.empty:
                attached_capacity = attached_electrolyzers['Added_Capacity_MW'].sum()
                attached_investment = attached_electrolyzers['Investment_Cost'].sum()
                print(f"  Attached to VRE: {attached_capacity:.1f} MW (£{attached_investment:,.0f})")
            
            if not public_electrolyzers.empty:
                public_capacity = public_electrolyzers['Added_Capacity_MW'].sum()
                public_investment = public_electrolyzers['Investment_Cost'].sum()
                print(f"  Public/Standalone: {public_capacity:.1f} MW (£{public_investment:,.0f})")
            
            # Save electrolyzer summary separately
            electrolyzer_investments.to_csv('electrolyzer_investment_summary.csv', index=False)
            print("\nElectrolyzer summary saved to 'electrolyzer_investment_summary.csv'")
        else:
            print("\nNo electrolyzer investments were made during the simulation.")
        
        # Generate and save detailed success rate analysis
        generate_success_rate_summary(project_pipeline, df_summary)
        
    else:
        print("No new capacity was added during the simulation.")
    
    # Generate comprehensive electrolyzer performance report
    generate_electrolyzer_performance_report()
    
    return df_summary


def display_iteration_electrolyzer_summary(year, electrolyzer_results):
    """
    Display electrolyzer performance summary for a specific iteration/year.
    """
    if not electrolyzer_results:
        return
    
    print(f"\n--- Year {year}: Electrolyzer Performance Summary ---")
    
    # Filter by type
    public_electrolyzers = {k: v for k, v in electrolyzer_results.items() if v.get('type') == 'public'}
    attached_electrolyzers = {k: v for k, v in electrolyzer_results.items() if v.get('type') == 'attached'}
    
    # Display public electrolyzer summary
    if public_electrolyzers:
        print("Public Electrolyzers:")
        for name, data in public_electrolyzers.items():
            utilization = data.get('capacity_utilization_percent', 0)
            capacity = data.get('current_capacity_mw', 0)
            recommendation = data.get('investment_recommendation', 'Unknown')
            expansion = data.get('suggested_expansion_mw', 0)
            print(f"  {name}: {capacity:.1f} MW, {utilization:.1f}% utilization, {recommendation}" + 
                  (f" (+{expansion:.1f} MW)" if expansion > 0 else ""))
    
    # Display attached electrolyzer summary
    if attached_electrolyzers:
        print("Attached Electrolyzers (VRE):")
        for name, data in attached_electrolyzers.items():
            utilization = data.get('capacity_utilization_percent', 0)
            capacity = data.get('current_capacity_mw', 0)
            expansion_rec = data.get('expansion_recommended', False)
            expansion = data.get('suggested_expansion_mw', 0)
            parent = data.get('parent_asset', 'Unknown')
            print(f"  {parent}: {capacity:.1f} MW, {utilization:.1f}% utilization" +
                  (f", Expansion: +{expansion:.1f} MW" if expansion_rec and expansion > 0 else ""))
    
    # Summary statistics
    total_capacity = sum(data.get('current_capacity_mw', 0) for data in electrolyzer_results.values())
    avg_utilization = sum(data.get('capacity_utilization_percent', 0) for data in electrolyzer_results.values()) / len(electrolyzer_results)
    total_hydrogen = sum(data.get('hydrogen_production_kg', 0) for data in electrolyzer_results.values())
    
    print(f"Total Electrolyzer Capacity: {total_capacity:.1f} MW")
    print(f"Average Utilization: {avg_utilization:.1f}%")
    print(f"Total Hydrogen Production: {total_hydrogen:,.0f} kg")


def generate_electrolyzer_performance_report():
    """
    Generate a comprehensive report on electrolyzer performance and capacity utilization
    across all analysis iterations.
    """
    print("\n" + "="*60)
    print("COMPREHENSIVE ELECTROLYZER PERFORMANCE REPORT")
    print("="*60)
    
    # Try to load existing analysis files to extract electrolyzer data
    electrolyzer_data = []
    
    # Look for investment analysis files from all iterations
    import glob
    analysis_files = glob.glob('investment_analysis_iter_*.xlsx')
    
    if analysis_files:
        for file in sorted(analysis_files):
            try:
                # Extract iteration number from filename
                iter_num = file.split('_')[-1].split('.')[0]
                
                # Try to read electrolyzer analysis sheet if it exists
                try:
                    df_electrolyzer = pd.read_excel(file, sheet_name='Electrolyzer Analysis', index_col=0)
                    for electrolyzer_name, row in df_electrolyzer.iterrows():
                        electrolyzer_data.append({
                            'iteration': iter_num,
                            'electrolyzer': electrolyzer_name,
                            'type': row.get('type', 'unknown'),
                            'capacity_mw': row.get('current_capacity_mw', 0),
                            'utilization_percent': row.get('capacity_utilization_percent', 0),
                            'energy_consumed_mwh': row.get('energy_consumed_mwh', 0),
                            'hydrogen_production_kg': row.get('hydrogen_production_kg', 0),
                            'hydrogen_income': row.get('hydrogen_income', 0),
                            'expansion_recommended': row.get('expansion_recommended', False),
                            'suggested_expansion_mw': row.get('suggested_expansion_mw', 0)
                        })
                except Exception:
                    # Electrolyzer analysis sheet doesn't exist for this iteration
                    continue
                    
            except Exception as e:
                print(f"Could not process file {file}: {e}")
                continue
    
    if electrolyzer_data:
        df_electrolyzer_report = pd.DataFrame(electrolyzer_data)
        
        # Summary statistics
        print("\nElectrolyzer Performance Summary:")
        print("-" * 40)
        
        # Overall statistics
        total_capacity = df_electrolyzer_report['capacity_mw'].sum()
        avg_utilization = df_electrolyzer_report['utilization_percent'].mean()
        total_hydrogen = df_electrolyzer_report['hydrogen_production_kg'].sum()
        total_expansion_recommended = df_electrolyzer_report['suggested_expansion_mw'].sum()
        
        print(f"Total Electrolyzer Capacity: {total_capacity:.1f} MW")
        print(f"Average Capacity Utilization: {avg_utilization:.1f}%")
        print(f"Total Hydrogen Production: {total_hydrogen:,.0f} kg")
        print(f"Total Expansion Recommended: {total_expansion_recommended:.1f} MW")
        
        # Performance by type
        print("\nPerformance by Electrolyzer Type:")
        print("-" * 40)
        type_summary = df_electrolyzer_report.groupby('type').agg({
            'capacity_mw': 'sum',
            'utilization_percent': 'mean',
            'hydrogen_production_kg': 'sum',
            'suggested_expansion_mw': 'sum'
        }).round(1)
        print(type_summary)
        
        # Top performing electrolyzers
        print("\nTop 10 Electrolyzers by Utilization:")
        print("-" * 40)
        top_performers = df_electrolyzer_report.nlargest(10, 'utilization_percent')[
            ['electrolyzer', 'type', 'capacity_mw', 'utilization_percent', 'hydrogen_production_kg']
        ]
        print(top_performers.to_string(index=False))
        
        # Electrolyzers recommended for expansion
        expansion_candidates = df_electrolyzer_report[df_electrolyzer_report['expansion_recommended'] == True]
        if not expansion_candidates.empty:
            print("\nElectrolyzers Recommended for Expansion:")
            print("-" * 40)
            print(expansion_candidates[['electrolyzer', 'type', 'capacity_mw', 'utilization_percent', 'suggested_expansion_mw']].to_string(index=False))
        
        # Save detailed report
        df_electrolyzer_report.to_csv('electrolyzer_performance_report.csv', index=False)
        print(f"\nDetailed electrolyzer performance report saved to 'electrolyzer_performance_report.csv'")
        
    else:
        print("No electrolyzer performance data found from previous iterations.")
        print("Run the investment analysis first to generate electrolyzer data.")


def perform_validation(df_summary):
    """
    Compares the model's projected capacity additions for 2023-2025 against
    actual operational data from the REPD files.
    """
    print("\n" + "="*20 + " MODEL VALIDATION (2023-2025) " + "="*20)
    
    # 1. Load actual operational data from REPD files
    actuals = []
    repd_files = ['repd-october-2023.csv', 'repd-q1-apr-2025.csv']
    for file in repd_files:
        try:
            df = pd.read_csv(file, encoding='utf-8')
        except UnicodeDecodeError:
            df = pd.read_csv(file, encoding='latin1')
        
        df['Operational'] = pd.to_datetime(df['Operational'], errors='coerce', dayfirst=True)
        df_operational = df.dropna(subset=['Operational'])
        
        for _, row in df_operational.iterrows():
            op_year = row['Operational'].year
            if 2023 <= op_year <= 2025:
                tech_type_str = row.get('Technology Type', '')
                tech_type = get_asset_type_from_repd(tech_type_str)
                capacity = pd.to_numeric(row.get('Installed Capacity (MWelec)'), errors='coerce')
                if tech_type and pd.notna(capacity):
                    actuals.append({
                        'Year': op_year,
                        'Technology': tech_type,
                        'Actual_Capacity_MW': capacity
                    })

    if not actuals:
        print("Could not find any actual operational data for 2023-2025 in REPD files for validation.")
        return

    df_actual = pd.DataFrame(actuals).groupby(['Year', 'Technology'])['Actual_Capacity_MW'].sum().reset_index()

    # 2. Process projected data from the simulation
    df_projected = df_summary[df_summary['Year'].isin([2023, 2024, 2025])].copy()
    if df_projected.empty:
        print("The simulation did not project any new capacity for 2023-2025.")
        df_projected_grouped = pd.DataFrame(columns=['Year', 'Technology', 'Projected_Capacity_MW'])
    else:
        df_projected['Technology'] = df_projected['Asset'].apply(get_asset_type)
        df_projected_grouped = df_projected.groupby(['Year', 'Technology'])['Added_Capacity_MW'].sum().reset_index()
        df_projected_grouped.rename(columns={'Added_Capacity_MW': 'Projected_Capacity_MW'}, inplace=True)

    # 3. Compare the results
    df_comparison = pd.merge(df_actual, df_projected_grouped, on=['Year', 'Technology'], how='outer').fillna(0)
    
    print("Comparison of Projected vs. Actual Capacity Additions (MW):")
    print(df_comparison.to_string(index=False))


def save_model_investment_decisions():
    """
    Save model investment decisions made in 2024 and 2025 to a separate file for analysis.
    This extracts decisions made by the model (not external projects) for validation.
    """
    try:
        # Read the investment summary if it exists
        df_summary = pd.read_csv('investment_summary.csv')
        
        # Filter for model decisions only
        model_decisions = df_summary[df_summary['Source'] == 'model'].copy()
        
        # Focus on 2024-2025 decisions (decisions that come online in these years)
        model_2024_2025 = model_decisions[model_decisions['Year'].isin([2024, 2025])].copy()
        
        # Add technology mapping
        model_2024_2025['Technology_Type'] = model_2024_2025['Asset'].apply(get_asset_type)
        
        # Add decision year (the year the model made the decision, not when it comes online)
        # For simplicity, we assume decisions for year X were made in year X-1
        model_2024_2025['Decision_Year'] = model_2024_2025['Year'] - 1
        
        # Save to file
        output_file = 'model_investment_decisions_2024_2025.csv'
        model_2024_2025.to_csv(output_file, index=False)
        
        print(f"\nModel investment decisions for 2024-2025 saved to: {output_file}")
        print(f"Total decisions captured: {len(model_2024_2025)}")
        
        # Summary by technology
        if not model_2024_2025.empty:
            summary = model_2024_2025.groupby(['Technology_Type', 'Year']).agg({
                'Added_Capacity_MW': 'sum',
                'Investment_Cost': 'sum'
            }).reset_index()
            
            print("\nSUMMARY OF MODEL DECISIONS:")
            print("-" * 50)
            for _, row in summary.iterrows():
                print(f"{row['Technology_Type']:<15} {row['Year']}: {row['Added_Capacity_MW']:.1f} MW")
        
        return model_2024_2025
        
    except FileNotFoundError:
        print("Investment summary not found. Please run the main analysis first.")
        return pd.DataFrame()

def run_model_reality_validation():
    """
    Standalone function to run the model vs reality validation.
    Can be called independently if investment_summary.csv already exists.
    """
    print("="*60)
    print("STANDALONE MODEL vs REALITY VALIDATION")
    print("="*60)
    
    # Save model decisions
    model_decisions = save_model_investment_decisions()
    
    # Run comparison
    comparison_results, detailed_actuals = compare_model_vs_reality()
    
    return model_decisions, comparison_results, detailed_actuals

if __name__ == "__main__":
    main()