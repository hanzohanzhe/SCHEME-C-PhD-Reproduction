#!/usr/bin/env python3
"""
Investment Analysis - Case 3: Both Decarbonization Cost and Capacity Market Cost

This script modifies the base investment analysis to include:
1. Decarbonization costs as annual payments to all Variable Renewable Energy (VRE) generators 
   (solar, onshore, offshore), distributed proportionally based on their capacity.
2. Capacity Market (CM) costs as annual payments to CCGT and OCGT generators,
   distributed proportionally based on their capacity.
"""

import os
import pickle
import shutil
from pathlib import Path

# CEM de-rating + fixed 2025 CM pot — see cm_battery_cm_allocation.py
os.environ.setdefault("CM_UK_DERATING", "1")
os.environ.setdefault("CM_FIXED_TO_2025_VALUE", "1")

_SCRIPT_DIR = Path(__file__).resolve().parent
RUN_SUITE = os.getenv("RUN_SUITE", "").strip().lower()
SCENARIO_V2 = os.getenv("SCENARIO_V2", "").strip().lower() in {"1", "true", "yes"}
START_YEAR = int(os.getenv("START_YEAR", "2025"))
END_YEAR = int(os.getenv("END_YEAR", "2034"))
VALIDATION_MODE = os.getenv("VALIDATION_MODE", "").strip().lower() in {"1", "true", "yes"}
PHYSICAL_PERIOD_HOURS = float(os.getenv("PHYSICAL_PERIOD_HOURS", "0.5"))


_OUTPUT_DIR: Path | None = None


def _output_dir() -> Path:
    global _OUTPUT_DIR
    if _OUTPUT_DIR is None:
        raw = os.getenv("OUTPUT_DIR", "").strip()
        if raw:
            _OUTPUT_DIR = Path(raw).expanduser().resolve()
            _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        else:
            _OUTPUT_DIR = _SCRIPT_DIR
    return _OUTPUT_DIR


def _io_path(path: Path) -> str:
    """Return a path string safe for open()/pandas on Windows (MAX_PATH)."""
    text = os.fspath(path.expanduser().resolve())
    if os.name == "nt" and len(text) >= 248 and not text.startswith("\\\\?\\"):
        return "\\\\?\\" + text
    return text


def _iter_analysis_path(iteration: int) -> Path:
    return _output_dir() / f"inv_analysis_{OUTPUT_SUFFIX}_i{iteration:02d}.xlsx"


def _checkpoint_enabled() -> bool:
    return os.getenv("ENABLE_CHECKPOINT", "1").strip().lower() not in {"0", "false", "no"}


def _checkpoint_path() -> Path:
    return _output_dir() / "checkpoints" / f"{OUTPUT_SUFFIX}_checkpoint.pkl"


def _save_checkpoint(
    *,
    completed_year: int,
    next_iteration_index: int,
    generator_objects: dict,
    battery_objects: dict,
    electrolyzer_objects: dict,
    project_pipeline: list,
    investment_summary: list,
    success_rates: dict,
) -> None:
    if not _checkpoint_enabled():
        return

    path = _checkpoint_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    state = {
        "schema_version": 1,
        "completed_year": int(completed_year),
        "next_iteration_index": int(next_iteration_index),
        "start_year": int(START_YEAR),
        "end_year": int(END_YEAR),
        "output_suffix": OUTPUT_SUFFIX,
        "decarb_scenario": DECARB_SCENARIO,
        "generator_objects": generator_objects,
        "battery_objects": battery_objects,
        "electrolyzer_objects": electrolyzer_objects,
        "project_pipeline": project_pipeline,
        "investment_summary": investment_summary,
        "success_rates": success_rates,
        "thermal_capacity_history": thermal_capacity_history,
        "system_cost_history": system_cost_history,
        "capacity_history": capacity_history,
        "vre_generation_profile": vre_generation_profile,
        "excess_generation_profile": excess_generation_profile,
        "final_year": final_year,
        "edinburgh_onshore_profiles": edinburgh_onshore_profiles,
        "vre_excess_profiles": vre_excess_profiles,
        "v2_cumulative_additional_decarb": _v2_cumulative_additional_decarb,
    }
    tmp_path = path.with_suffix(".tmp")
    try:
        with tmp_path.open("wb") as handle:
            pickle.dump(state, handle, protocol=pickle.HIGHEST_PROTOCOL)
        tmp_path.replace(path)
        year_archive = path.with_name(f"{OUTPUT_SUFFIX}_checkpoint_{completed_year}.pkl")
        try:
            shutil.copy2(path, year_archive)
        except Exception as archive_exc:
            print(f"⚠ Per-year checkpoint archive failed for {completed_year}: {archive_exc}")
        print(f"✓ Checkpoint saved after {completed_year}: {path}")
    except Exception as exc:
        print(f"⚠ Checkpoint save failed after {completed_year}: {exc}")
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass


def _load_checkpoint() -> dict | None:
    if not _checkpoint_enabled():
        return None

    path = _checkpoint_path()
    if not path.exists():
        return None

    try:
        with path.open("rb") as handle:
            state = pickle.load(handle)
        if int(state.get("start_year", START_YEAR)) != int(START_YEAR):
            print(f"⚠ Ignoring checkpoint with different START_YEAR: {path}")
            return None
        if str(state.get("output_suffix", OUTPUT_SUFFIX)) != str(OUTPUT_SUFFIX):
            print(f"⚠ Ignoring checkpoint with different OUTPUT_SUFFIX: {path}")
            return None
        print(
            f"✓ Loaded checkpoint after {state.get('completed_year')} "
            f"(next iteration index {state.get('next_iteration_index')}): {path}"
        )
        return state
    except Exception as exc:
        print(f"⚠ Failed to load checkpoint {path}: {exc}")
        return None


def _zero_decarb_cost_dict() -> dict:
    years = range(START_YEAR, END_YEAR + 1)
    zero = {
        "Decarbonization_Cost": 0.0,
        "Existing_Decarbonization_Cost_GBP": 0.0,
        "Additional_Decarbonization_Cost_GBP": 0.0,
        "Annual_CfD_Increment_GBP": 0.0,
        "Agent_Investable_Decarb_Income_GBP": 0.0,
        "RO_Legacy_GBP": 0.0,
        "FiT_Legacy_GBP": 0.0,
        "CfD_Baseline_GBP": 0.0,
        "CfD_New_Decarbonization_GBP": 0.0,
        "Inherited_CfD_Agent_Income_GBP": 0.0,
        "New_CfD_Stimulus_GBP": 0.0,
        "RO_Payment_Share_vs_2025": 1.0,
        "FiT_Payment_Share_vs_2025": 1.0,
    }
    return {int(y): dict(zero) for y in years}

# Import everything from the base analysis
from run_investment_analysis import *
from run_investment_analysis import (
    _import_storage_expansion_modules,
    calculate_storage_expansion_limit,
)
from load_mechanism_costs import load_mechanism_costs
from load_decarbonization_cost_breakdown import HISTORICAL_SUPPORT_MN, load_decarbonization_costs, write_scenario_csv
from map_projects_to_generators_by_location import map_projects_to_generators, extract_location_from_repd
import pandas as pd
import numpy as np

if SCENARIO_V2:
    from scenarios_v2.load_scenarios_v2 import (
        load_scenarios_v2_costs,
        refresh_runtime_agent_income,
        refresh_runtime_decarb_costs,
    )
    from scenarios_v2.expansion_policy_v2 import (
        apply_desnz_regulated_cap,
        clip_cfd_mw_to_desnz_headroom,
        compute_cfd_mw_by_tech,
        compute_cfd_mw_by_tech_until_tech_cap,
        compute_cfd_mw_by_operational_headroom,
    )
    DECARB_V2_SCENARIO = os.getenv("DECARB_V2_SCENARIO", "existing_decarb_base")
    OUTPUT_SUFFIX = f"case3_v2_{DECARB_V2_SCENARIO}"
    DECARB_COSTS = load_scenarios_v2_costs(DECARB_V2_SCENARIO)
    DECARB_SCENARIO = DECARB_V2_SCENARIO
elif RUN_SUITE == "basic":
    DECARB_SCENARIO = os.getenv("DECARB_SCENARIO", "basic")
    OUTPUT_SUFFIX = os.getenv("OUTPUT_SUFFIX", "archive_basic")
    DECARB_COSTS = _zero_decarb_cost_dict()
elif RUN_SUITE == "with_cm":
    DECARB_SCENARIO = "with_cm"
    OUTPUT_SUFFIX = "archive_with_cm"
    DECARB_COSTS = _zero_decarb_cost_dict()
else:
    DECARB_SCENARIO = os.getenv("DECARB_SCENARIO", "normal_subsidy")
    OUTPUT_SUFFIX = f"case3_cm_decarbonization_breakdown_{DECARB_SCENARIO}"
    DECARB_COSTS = load_decarbonization_costs(DECARB_SCENARIO)

TRACE_SCENARIO_NAME = os.getenv("DECARB_SCENARIO", DECARB_SCENARIO)

CM_COSTS = load_mechanism_costs()

VALIDATION_VRE_CAPEX_PER_MW = {
    2015: {"solar": 1.34e6, "onshore": 1.45e6, "offshore": 5.20e6, "0.25c_battery": 1.30e6},
    2016: {"solar": 1.28e6, "onshore": 1.41e6, "offshore": 4.85e6, "0.25c_battery": 1.30e6},
    2017: {"solar": 1.19e6, "onshore": 1.36e6, "offshore": 4.50e6, "0.25c_battery": 1.05e6},
    2018: {"solar": 1.10e6, "onshore": 1.32e6, "offshore": 4.15e6, "0.25c_battery": 0.90e6},
    2019: {"solar": 1.01e6, "onshore": 1.28e6, "offshore": 3.80e6, "0.25c_battery": 0.78e6},
    2020: {"solar": 0.92e6, "onshore": 1.24e6, "offshore": 3.45e6, "0.25c_battery": 0.68e6},
    2021: {"solar": 0.83e6, "onshore": 1.20e6, "offshore": 3.10e6, "0.25c_battery": 0.62e6},
    2022: {"solar": 0.75e6, "onshore": 1.18e6, "offshore": 2.85e6, "0.25c_battery": 0.75e6},
    2023: {"solar": 0.81e6, "onshore": 1.26e6, "offshore": 3.56e6, "0.25c_battery": 0.65e6},
    2024: {"solar": 0.78e6, "onshore": 1.24e6, "offshore": 3.85e6, "0.25c_battery": 0.54e6},
    2025: {"solar": 0.75e6, "onshore": 1.22e6, "offshore": 3.70e6, "0.25c_battery": 0.42e6},
}

VALIDATION_GAS_PRICE_P_PER_KWH = {
    2015: 1.59,
    2016: 1.27,
    2017: 1.52,
    2018: 1.92,
    2019: 1.40,
    2020: 1.19,
    2021: 3.10,
    2022: 6.19,
    2023: 6.68,
    2024: 3.35,
    2025: 3.05,
}


def _apply_validation_dynamic_costs(current_year: int, generator_objects: dict | None = None) -> None:
    if not VALIDATION_MODE:
        return

    capex = VALIDATION_VRE_CAPEX_PER_MW.get(current_year)
    if capex:
        config.capital_costs_per_mw.update(capex)
        config.capital_costs_per_mw["battery"] = capex["0.25c_battery"]

    gas_price = VALIDATION_GAS_PRICE_P_PER_KWH.get(current_year)
    if gas_price and generator_objects:
        scale = gas_price / VALIDATION_GAS_PRICE_P_PER_KWH[2025]
        for name, base_fuel in {"CCGT": 39.21, "OCGT": 48.78}.items():
            asset = generator_objects.get(name)
            if asset and isinstance(asset, GasGenerator):
                asset.fuel_cost = base_fuel * scale
                base_gen_cost = config.generators[name].get("gen_cost", 0)
                unit_time_cost = config.generators[name].get("unit_time_cost", 0)
                asset.gen_cost = base_gen_cost + asset.carbon_price + asset.fuel_cost + unit_time_cost
        print(
            f"--- Validation dynamic costs {current_year}: gas={gas_price:.2f} p/kWh, "
            f"solar={config.capital_costs_per_mw.get('solar')/1e6:.2f} £m/MW, "
            f"onshore={config.capital_costs_per_mw.get('onshore')/1e6:.2f}, "
            f"offshore={config.capital_costs_per_mw.get('offshore')/1e6:.2f}, "
            f"0.25C={config.capital_costs_per_mw.get('0.25c_battery')/1e6:.2f} ---"
        )


def _validation_historical_decarb_costs() -> dict[int, dict]:
    """Historical validation decarb: stock subsidy is system cost; positive scheme deltas stimulate agents."""
    historical = {int(row["year"]): dict(row) for row in HISTORICAL_SUPPORT_MN}
    last = dict(HISTORICAL_SUPPORT_MN[-1])
    out = {}
    previous = None
    for year in range(START_YEAR, END_YEAR + 1):
        row = dict(historical.get(year, last))
        scheme_values = {scheme: float(row.get(scheme, 0.0)) for scheme in ("RO", "FiT", "CfD", "REGO")}
        total_mn = sum(scheme_values.values())
        if previous is None:
            positive_delta_mn = 0.0
            positive_cfd_delta_mn = 0.0
        else:
            positive_delta_mn = sum(max(0.0, scheme_values[s] - previous.get(s, 0.0)) for s in scheme_values)
            positive_cfd_delta_mn = max(0.0, scheme_values["CfD"] - previous.get("CfD", 0.0))
        out[int(year)] = {
            "Decarbonization_Cost": total_mn * 1e6,
            "Existing_Decarbonization_Cost_GBP": total_mn * 1e6,
            "Additional_Decarbonization_Cost_GBP": positive_delta_mn * 1e6,
            "Annual_CfD_Increment_GBP": positive_delta_mn * 1e6,
            "Agent_Investable_Decarb_Income_GBP": positive_delta_mn * 1e6,
            "RO_Legacy_GBP": scheme_values["RO"] * 1e6,
            "FiT_Legacy_GBP": scheme_values["FiT"] * 1e6,
            "CfD_Baseline_GBP": scheme_values["CfD"] * 1e6,
            "CfD_New_Decarbonization_GBP": positive_cfd_delta_mn * 1e6,
            "Inherited_CfD_Agent_Income_GBP": 0.0,
            "New_CfD_Stimulus_GBP": positive_delta_mn * 1e6,
            "RO_Payment_Share_vs_2025": 1.0,
            "FiT_Payment_Share_vs_2025": 1.0,
            "Validation_Historical_RO_mn": scheme_values["RO"],
            "Validation_Historical_FiT_mn": scheme_values["FiT"],
            "Validation_Historical_CfD_mn": scheme_values["CfD"],
            "Validation_Historical_REGO_mn": scheme_values["REGO"],
            "Validation_Positive_Scheme_Delta_mn": positive_delta_mn,
        }
        previous = scheme_values
    return out


if VALIDATION_MODE and os.getenv("VALIDATION_HISTORICAL_DECARB", "").strip().lower() in {"1", "true", "yes"}:
    DECARB_SCENARIO = os.getenv("VALIDATION_DECARB_SCENARIO", "validation_with_cm_decarbonization")
    OUTPUT_SUFFIX = os.getenv("OUTPUT_SUFFIX", DECARB_SCENARIO)
    TRACE_SCENARIO_NAME = os.getenv("DECARB_SCENARIO", DECARB_SCENARIO)
    DECARB_COSTS = _validation_historical_decarb_costs()


def _apply_cm_fixed_2025() -> None:
    """Fix CM pot at 2025 value for 2025-2035 (matches latest CM rerun)."""
    cm_value = float(CM_COSTS.get(2025, {}).get("CM_Cost", 749.3e6))
    for year in list(CM_COSTS.keys()):
        if year >= 2025:
            CM_COSTS[year]["CM_Cost"] = cm_value


if os.environ.get("CM_FIXED_TO_2025_VALUE", "1").strip().lower() not in {"0", "false", "no"}:
    _apply_cm_fixed_2025()

# Override get_asset_type to include electrolyzer recognition
def get_asset_type(name):
    """Maps an asset name to a generic asset type, including electrolyzer."""
    if 'electrolyzer' in name.lower(): return 'electrolyzer'
    if 'solar' in name.lower(): return 'solar'
    if 'onshore' in name.lower(): return 'onshore'
    if 'offshore' in name.lower(): return 'offshore'
    if '1c_battery' in name.lower(): return '1c_battery'
    if '0.5c_battery' in name.lower(): return '0.5c_battery'
    if '0.25c_battery' in name.lower(): return '0.25c_battery'
    if 'pumpedhydro' in name.lower(): return 'pumped_hydro'
    if 'hydrogen' in name.lower() and 'battery' in name.lower(): return 'hydrogen_battery'
    if 'battery' in name.lower(): return 'battery'
    if 'ccgt' in name.lower(): return 'CCGT'
    if 'ocgt' in name.lower(): return 'OCGT'
    if 'bio' in name.lower(): return 'bio_and_waste'
    return name

# Track thermal capacity over time
thermal_capacity_history = []

# Track system cost metrics over time
system_cost_history = []

# Track VRE generation and excess generation profiles for final year analysis
vre_generation_profile = None
excess_generation_profile = None
final_year = None

# Track Edinburgh onshore wind generation only (no excess; excess is always system-wide)
edinburgh_onshore_profiles = {}  # {year: {'generation': [...], 'capacity_mw': float}}

# Track total VRE generation and overall excess generation for each year
vre_excess_profiles = {}  # {year: {'total_vre_generation': [...], 'overall_excess': [...], 'total_vre_annual': float, 'total_excess_annual': float}}

# Track capacity evolution over time for all technologies
capacity_history = []  # List of dicts with year, technology, and capacity

# Runtime cumulative additional CfD levy (governmental_target: tracks agent stimulus only).
_v2_cumulative_additional_decarb = 0.0


def analyze_investment_case3(iteration, generator_objects, battery_objects, electrolyzer_objects):
    """
    Modified investment analysis with both Decarbonization cost payments to all VRE 
    and Capacity Market cost payments to CCGT/OCGT.
    """
    print(f"\n--- Starting Iteration {iteration}: Electricity Market Simulation (Case 3: Decarbonization Cost to VRE + CM Cost to CCGT/OCGT) ---")

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
    connections_list = [Connection(**params) for params in config.connections.values()]
    # -------------------------------------------------------------------------
    # 2. Run the full simulation
    # -------------------------------------------------------------------------
    # Use actual electrolyzer from electrolyzer_objects (use first one if multiple exist)
    electrolyzer_obj = list(electrolyzer_objects.values())[0] if electrolyzer_objects else Electrolyzer("electrolyzer_dummy", 0, 0, 0, 0, 0, 0, 0)
    current_year = START_YEAR + iteration - 1
    os.environ["SIMULATION_YEAR"] = str(current_year)
    os.environ["DECARB_SCENARIO"] = TRACE_SCENARIO_NAME
    print(f"--- Iteration {iteration}: calling run_simulation(periods={periods}, generators={len(generators_list)}, batteries={len(batteries_list)}) ---", flush=True)
    results = run_simulation(periods, generators_list, batteries_list, forecast_demands, real_demands, connections_list, electrolyzer_obj)
    print(f"--- Iteration {iteration}: run_simulation returned. Processing results. ---", flush=True)
    
    gen_list_composition = results[20]
    # Note: simulation_model.py returns blackout_periods as the last item, so indices are shifted by 1
    # simuold.py: ..., total_income_dict(-7), ..., renewable_hy_dict(-3), flexible_demand_list(-2), interconnector_exports_list(-1)
    # simulation_model.py: ..., total_income_dict(-8), ..., renewable_hy_dict(-4), flexible_demand_list(-3), interconnector_exports_list(-2), blackout_periods(-1)
    total_income_dict = results[-8]  # Changed from -7 to -8 due to blackout_periods being added
    renewable_hy_dict = results[-4]  # Changed from -3 to -4 due to blackout_periods being added
    flexible_demand_list = results[-3]  # Changed from -2 to -3 due to blackout_periods being added
    excess_energy_list = results[-5]  # Changed from -4 to -5 due to blackout_periods being added
    blackout_periods = results[-1]  # Energy deficit (blackout) for each period
    excess_electricity = results[22]  # Excess electricity per period
    
    if excess_energy_list and isinstance(excess_energy_list[0], tuple) and len(excess_energy_list[0]) > 1:
        excess_energy_final_dict = {item[0].name: item[1] for item in excess_energy_list if hasattr(item[0], 'name')}
    else:
        excess_energy_final_dict = {}

    print(f"--- Iteration {iteration}: Simulation Finished. Starting Investment Analysis (Case 3) ---")

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
    
    # Ensure total_income_dict values are numeric (sum lists if present)
    # Handle nested lists and mixed types safely
    def safe_sum(value):
        """Safely sum a value, handling lists, nested lists, and mixed types"""
        if isinstance(value, list):
            # Sum all numeric values in the list, handling nested lists
            total = 0
            for item in value:
                if isinstance(item, (int, float)):
                    total += item
                elif isinstance(item, list):
                    total += safe_sum(item)  # Recursively handle nested lists
            return total
        elif isinstance(value, (int, float)):
            return float(value)
        else:
            return 0.0
    
    clean_income_dict = {}
    for key, value in total_income_dict.items():
        if value is None:
            clean_income_dict[key] = 0.0
        else:
            clean_income_dict[key] = safe_sum(value)
    
    # ========================================================================
    # CRITICAL FIX: Remap income from simulation names to config keys
    # ========================================================================
    # Simulation returns income_dict with keys = asset.name (from config "name" field)
    # But analysis uses config keys (dictionary keys in config.generators/batteries)
    # We need to map: simulation_name -> config_key
    
    # 1. Remap battery income: simulation uses Battery.name (e.g. "thermal_battery") 
    #    but analysis uses config key (e.g. "1c_battery")
    battery_name_mapping = {
        'thermal_battery': '1c_battery',      # config: "1c_battery" has name "thermal_battery"
        'li_battery': '0.5c_battery',         # config: "0.5c_battery" has name "li_battery"
        'air_battery': '0.25c_battery',      # config: "0.25c_battery" has name "air_battery"
        'pumpedhydro_battery': 'pumpedhydro_battery',  # Same name
        'hydrogen_battery': 'hydrogen_battery'  # Same name
    }
    
    for sim_name, config_key in battery_name_mapping.items():
        if sim_name in clean_income_dict and sim_name != config_key:
            # Transfer income from simulation name to config key
            income_value = clean_income_dict[sim_name]
            clean_income_dict[config_key] = clean_income_dict.get(config_key, 0.0) + income_value
            if iteration == 1 and income_value > 0:
                print(f"  ✓ Remapped battery income: {sim_name} → {config_key} ({income_value:,.2f} GBP)")
            del clean_income_dict[sim_name]
    
    # 2. Verify all generator names match config keys (offshore, onshore, solar should match)
    # For generators, config key should equal name, but let's verify and fix if needed
    generator_name_mismatches = []
    for config_key, gen_obj in generator_objects.items():
        sim_name = getattr(gen_obj, 'name', None)
        if sim_name and sim_name != config_key:
            # Check if income exists with simulation name but not config key
            if sim_name in clean_income_dict and config_key not in clean_income_dict:
                income_value = clean_income_dict[sim_name]
                clean_income_dict[config_key] = income_value
                generator_name_mismatches.append((sim_name, config_key, income_value))
                if iteration == 1 and income_value > 0:
                    print(f"  ✓ Remapped generator income: {sim_name} → {config_key} ({income_value:,.2f} GBP)")
                del clean_income_dict[sim_name]
    
    # 3. Debug: Print all income keys vs expected config keys
    if iteration == 1:
        print(f"\n  Income Dictionary Keys Verification:")
        print(f"    Total income keys in simulation result: {len(clean_income_dict)}")
        
        # Check which expected assets have income
        all_expected_keys = set(generator_objects.keys()) | set(battery_objects.keys())
        income_keys = set(clean_income_dict.keys())
        
        missing_income = all_expected_keys - income_keys
        unexpected_income = income_keys - all_expected_keys
        
        if missing_income:
            print(f"    ⚠️  Assets with no income: {sorted(missing_income)}")
        if unexpected_income:
            print(f"    ⚠️  Unexpected income keys (not in config): {sorted(unexpected_income)}")
        
        # Check specific technologies (offshore, onshore, solar, batteries)
        for tech_type in ['offshore', 'onshore', 'solar', '1c_battery', '0.5c_battery', '0.25c_battery']:
            tech_assets = [k for k in all_expected_keys if tech_type in k.lower()]
            tech_with_income = [k for k in tech_assets if k in income_keys and clean_income_dict.get(k, 0) > 0]
            tech_without_income = [k for k in tech_assets if k not in income_keys or clean_income_dict.get(k, 0) == 0]
            if tech_with_income:
                print(f"    ✓ {tech_type}: {len(tech_with_income)} assets with income")
            if tech_without_income:
                print(f"    ⚠️  {tech_type}: {len(tech_without_income)} assets without income: {tech_without_income[:3]}{'...' if len(tech_without_income) > 3 else ''}")
    
    df_income = pd.Series(clean_income_dict, name='electricity_income', dtype=float).to_frame()
    df_income.index.name = 'asset_name'
    # Ensure index is string type for consistent merging
    df_income.index = df_income.index.astype(str)
    
    df_op_costs = pd.Series(total_operational_costs, name='operational_cost', dtype=float).to_frame()
    df_op_costs.index.name = 'asset_name'
    # Ensure index is string type for consistent merging
    df_op_costs.index = df_op_costs.index.astype(str)

    hydrogen_income = {}
    H2_PRICE_PER_KG = config.investment_parameters['hydrogen_price_per_kg']
    
    # Handle both dict and list structures for renewable_hy_dict
    if isinstance(renewable_hy_dict, dict):
        for _, productions in renewable_hy_dict.items():
            if isinstance(productions, list):
                for production_item in productions:
                    if isinstance(production_item, (list, tuple)) and len(production_item) >= 3:
                        gen_obj, _, hy_kg = production_item[0], production_item[1], production_item[2]
                        if hasattr(gen_obj, 'name'):
                            revenue = hy_kg * PHYSICAL_PERIOD_HOURS * H2_PRICE_PER_KG
                            hydrogen_income[gen_obj.name] = hydrogen_income.get(gen_obj.name, 0) + revenue
    elif isinstance(renewable_hy_dict, list):
        # If it's a list, it might be a list of lists (one per period) or a flat list
        for item in renewable_hy_dict:
            if isinstance(item, list):
                # This is a list of production items for one period
                for production_item in item:
                    if isinstance(production_item, (list, tuple)) and len(production_item) >= 3:
                        gen_obj, _, hy_kg = production_item[0], production_item[1], production_item[2]
                        if hasattr(gen_obj, 'name'):
                            revenue = hy_kg * PHYSICAL_PERIOD_HOURS * H2_PRICE_PER_KG
                            hydrogen_income[gen_obj.name] = hydrogen_income.get(gen_obj.name, 0) + revenue
            elif isinstance(item, (list, tuple)) and len(item) >= 3:
                # This is a single production item
                gen_obj, _, hy_kg = item[0], item[1], item[2]
                if hasattr(gen_obj, 'name'):
                    revenue = hy_kg * PHYSICAL_PERIOD_HOURS * H2_PRICE_PER_KG
                    hydrogen_income[gen_obj.name] = hydrogen_income.get(gen_obj.name, 0) + revenue
    
    df_hydrogen = pd.DataFrame.from_dict(hydrogen_income, orient='index', columns=['hydrogen_income'])
    df_hydrogen.index.name = 'asset_name'
    # Ensure index is string type for consistent merging
    df_hydrogen.index = df_hydrogen.index.astype(str)
    # Ensure numeric dtype
    df_hydrogen['hydrogen_income'] = pd.to_numeric(df_hydrogen['hydrogen_income'], errors='coerce').fillna(0)

    df_analysis = pd.merge(df_income, df_hydrogen, left_index=True, right_index=True, how='outer')
    df_analysis = pd.merge(df_analysis, df_op_costs, left_index=True, right_index=True, how='left')
    
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
    
    # Ensure ALL valid assets are included, even if they have no income
    # This ensures all 54 agents appear in the analysis
    missing_assets = valid_asset_names - set(df_analysis.index)
    if missing_assets:
        print(f"--- Iteration {iteration}: Adding {len(missing_assets)} assets with zero income to analysis ---")
        for asset_name in missing_assets:
            df_analysis.loc[asset_name] = {
                'electricity_income': 0.0,
                'hydrogen_income': 0.0,
                'operational_cost': 0.0
            }
    
    # Debug: Print summary of assets in analysis
    if iteration == 1:
        print(f"--- Iteration {iteration}: Investment analysis includes {len(df_analysis)} assets (all {len(valid_asset_names)} valid agents) ---")
        # Show breakdown by asset type (use module-level get_asset_type)
        asset_type_counts = {}
        for name in df_analysis.index:
            asset_type = get_asset_type(name)
            asset_type_counts[asset_type] = asset_type_counts.get(asset_type, 0) + 1
        print(f"  Asset breakdown: {', '.join([f'{k}: {v}' for k, v in sorted(asset_type_counts.items())])}")
    
    # Ensure all batteries are included in the analysis DataFrame
    # Batteries may not have electricity income but they have storage income from total_income_dict
    for battery_name, battery_obj in battery_objects.items():
        if battery_name not in df_analysis.index:
            # Add battery with zero income if not already present
            df_analysis.loc[battery_name] = {
                'electricity_income': 0.0,
                'hydrogen_income': 0.0,
                'operational_cost': 0.0
            }
        # Ensure battery has operational cost (batteries don't have gen_cost, so operational cost is 0)
        if battery_name in df_analysis.index:
            if pd.isna(df_analysis.loc[battery_name, 'operational_cost']):
                df_analysis.loc[battery_name, 'operational_cost'] = 0.0
    
    # Convert all numeric columns to float and fill NaN with 0, avoiding FutureWarning
    # Use pd.to_numeric instead of fillna(0) on object dtype to avoid deprecation warning
    numeric_cols = ['electricity_income', 'hydrogen_income', 'operational_cost']
    for col in numeric_cols:
        if col in df_analysis.columns:
            # Convert to numeric, handling any lists or non-numeric values
            df_analysis[col] = df_analysis[col].apply(
                lambda x: sum(x) if isinstance(x, list) else (float(x) if x is not None and pd.notna(x) else 0)
            )
            df_analysis[col] = pd.to_numeric(df_analysis[col], errors='coerce').fillna(0)
    
    # -------------------------------------------------------------------------
    # CASE 3: Decarbonization levy (existing → system cost; additional → agents)
    #         + CM income via UK de-rated capacity allocation
    # -------------------------------------------------------------------------
    current_year = START_YEAR + iteration - 1
    if os.getenv("SAVE_GENERATION_TRACE", "").strip().lower() in {"1", "true", "yes"}:
        from generation_trace_io import save_period_generation_trace

        save_period_generation_trace(
            gen_list_composition,
            current_year,
            TRACE_SCENARIO_NAME,
            _output_dir(),
            get_asset_type,
        )
    decarb_components = DECARB_COSTS.get(current_year, {})
    existing_decarb_cost = decarb_components.get('Existing_Decarbonization_Cost_GBP', 0.0)
    additional_decarb_cost = decarb_components.get('Additional_Decarbonization_Cost_GBP', 0.0)
    decarbonization_cost_annual = decarb_components.get('Decarbonization_Cost', 0.0)
    ro_legacy_cost_annual = decarb_components.get('RO_Legacy_GBP', 0.0)
    fit_legacy_cost_annual = decarb_components.get('FiT_Legacy_GBP', 0.0)
    cfd_baseline_cost = decarb_components.get('CfD_Baseline_GBP', 0.0)
    cfd_new_cost_annual = decarb_components.get('CfD_New_Decarbonization_GBP', 0.0)
    annual_cfd_increment = decarb_components.get('Annual_CfD_Increment_GBP', 0.0)
    agent_investable_decarb = decarb_components.get('Agent_Investable_Decarb_Income_GBP', 0.0)
    inherited_cfd_agent_income = decarb_components.get('Inherited_CfD_Agent_Income_GBP', 0.0)
    new_cfd_stimulus = decarb_components.get('New_CfD_Stimulus_GBP', 0.0)
    ro_payment_share = decarb_components.get('RO_Payment_Share_vs_2025', 1.0)
    fit_payment_share = decarb_components.get('FiT_Payment_Share_vs_2025', 1.0)
    cm_cost_annual = CM_COSTS.get(current_year, {}).get('CM_Cost', 749.3e6)
    if RUN_SUITE == "basic":
        existing_decarb_cost = 0.0
        additional_decarb_cost = 0.0
        decarbonization_cost_annual = 0.0
        agent_investable_decarb = 0.0
        new_cfd_stimulus = 0.0
        cfd_new_cost_annual = 0.0
        cm_cost_annual = 0.0
    elif RUN_SUITE == "with_cm":
        existing_decarb_cost = 0.0
        additional_decarb_cost = 0.0
        decarbonization_cost_annual = 0.0
        agent_investable_decarb = 0.0
        new_cfd_stimulus = 0.0
        cfd_new_cost_annual = 0.0
    
    # Calculate total VRE capacity (solar, onshore, offshore)
    BASE_WIND_UNIT_MW = 20
    BASE_SOLAR_UNIT_MW = 1
    
    total_vre_capacity = 0
    vre_capacities = {}
    
    for name, asset in generator_objects.items():
        asset_type = get_asset_type(name)
        if asset_type in ['solar', 'onshore', 'offshore']:
            if isinstance(asset, ExpensiverenewableGenerator):
                if asset_type in ['onshore', 'offshore']:
                    capacity = asset.capacity_multiplier * BASE_WIND_UNIT_MW
                elif asset_type == 'solar':
                    capacity = asset.capacity_multiplier * BASE_SOLAR_UNIT_MW
                else:
                    capacity = asset.capacity_multiplier
                
                vre_capacities[name] = capacity
                total_vre_capacity += capacity

    tech_capacity_totals_runtime = {}
    for name, capacity in vre_capacities.items():
        asset_type = get_asset_type(name)
        if asset_type in ('solar', 'onshore', 'offshore'):
            tech_capacity_totals_runtime[asset_type] = (
                tech_capacity_totals_runtime.get(asset_type, 0.0) + capacity
            )

    if SCENARIO_V2:
        global _v2_cumulative_additional_decarb
        decarb_components = refresh_runtime_agent_income(
            decarb_components,
            total_vre_capacity,
            current_year,
            tech_capacity_totals=tech_capacity_totals_runtime,
        )
        agent_investable_decarb = decarb_components.get('Agent_Investable_Decarb_Income_GBP', 0.0)
        new_cfd_stimulus = decarb_components.get('New_CfD_Stimulus_GBP', 0.0)
        decarb_components, _v2_cumulative_additional_decarb = refresh_runtime_decarb_costs(
            decarb_components, agent_investable_decarb, _v2_cumulative_additional_decarb
        )
        additional_decarb_cost = decarb_components.get('Additional_Decarbonization_Cost_GBP', 0.0)
        decarbonization_cost_annual = decarb_components.get('Decarbonization_Cost', 0.0)
        cfd_new_cost_annual = decarb_components.get('CfD_New_Decarbonization_GBP', 0.0)
    
    # Calculate thermal capacity for CM cost distribution
    ccgt_capacity = 0
    ocgt_capacity = 0
    for name, asset in generator_objects.items():
        if 'CCGT' in name.upper():
            if isinstance(asset, GasGenerator):
                ccgt_capacity += asset.capacity_limit
        elif 'OCGT' in name.upper():
            if isinstance(asset, GasGenerator):
                ocgt_capacity += asset.capacity_limit
    
    total_thermal_capacity = ccgt_capacity + ocgt_capacity
    
    # Initialize income columns as float
    df_analysis['ro_legacy_income'] = 0.0
    df_analysis['fit_legacy_income'] = 0.0
    df_analysis['cfd_baseline_income'] = 0.0
    df_analysis['cfd_new_decarbonization_income'] = 0.0
    df_analysis['agent_decarbonization_income'] = 0.0
    df_analysis['decarbonization_income'] = 0.0
    df_analysis['cm_income'] = 0.0

    agent_income_mode_runtime = str(decarb_components.get('V2_Agent_Income_Mode', '')) if SCENARIO_V2 else ''
    subsidy_eligible_vre_capacities = dict(vre_capacities)
    if SCENARIO_V2 and agent_income_mode_runtime in {
        'annual_increment_until_tech_cap',
        'subsidy_to_operational_target',
    }:
        from scenarios_v2.load_scenarios_v2 import desnz_headroom_mw, techs_below_desnz_ceiling

        if agent_income_mode_runtime == 'subsidy_to_operational_target':
            headroom = desnz_headroom_mw(tech_capacity_totals_runtime, current_year)
            eligible_techs = {tech for tech, gap in headroom.items() if gap > 1.0}
        else:
            eligible_techs = set(techs_below_desnz_ceiling(tech_capacity_totals_runtime, current_year))

        subsidy_eligible_vre_capacities = {
            name: capacity
            for name, capacity in vre_capacities.items()
            if get_asset_type(name) in eligible_techs
        }

    eligible_vre_capacity = sum(subsidy_eligible_vre_capacities.values())

    # Only additional CfD investable income flows to VRE agents (not existing RO/FiT/baseline CfD).
    # V2 as-usual allocates across all existing VRE capacity; governmental-target allocates
    # only to technologies still below the DESNZ target path.
    if eligible_vre_capacity > 0 and agent_investable_decarb > 0:
        for name in df_analysis.index:
            if name in subsidy_eligible_vre_capacities:
                capacity_share = subsidy_eligible_vre_capacities[name] / eligible_vre_capacity
                df_analysis.loc[name, 'agent_decarbonization_income'] = float(
                    agent_investable_decarb * capacity_share
                )
                df_analysis.loc[name, 'decarbonization_income'] = df_analysis.loc[name, 'agent_decarbonization_income']

    from cm_battery_cm_allocation import allocate_cm_income_uk_derating, cm_uk_derating_enabled

    if cm_uk_derating_enabled():
        cm_alloc = allocate_cm_income_uk_derating(
            generator_objects, battery_objects, cm_cost_annual
        )
        for name, income in cm_alloc.items():
            if name in df_analysis.index:
                df_analysis.loc[name, 'cm_income'] = income
    elif total_thermal_capacity > 0:
        for name in df_analysis.index:
            if 'CCGT' in name.upper():
                asset = generator_objects.get(name)
                if asset and isinstance(asset, GasGenerator):
                    capacity_share = asset.capacity_limit / total_thermal_capacity
                    df_analysis.loc[name, 'cm_income'] = cm_cost_annual * capacity_share
            elif 'OCGT' in name.upper():
                asset = generator_objects.get(name)
                if asset and isinstance(asset, GasGenerator):
                    capacity_share = asset.capacity_limit / total_thermal_capacity
                    df_analysis.loc[name, 'cm_income'] = cm_cost_annual * capacity_share

    # Ensure income columns are numeric
    for col in ['ro_legacy_income', 'fit_legacy_income', 'cfd_baseline_income',
                'cfd_new_decarbonization_income', 'agent_decarbonization_income', 'decarbonization_income']:
        df_analysis[col] = pd.to_numeric(df_analysis[col], errors='coerce').fillna(0)
    df_analysis['cm_income'] = pd.to_numeric(df_analysis['cm_income'], errors='coerce').fillna(0)
    
    # Track thermal capacity (will be saved after analysis completes)
    # Note: Thermal capacity is also automatically extracted from Excel files
    # using extract_thermal_capacity_from_analysis.py, so this tracking is optional
    thermal_capacity_history.append({
        'Year': current_year,
        'Iteration': iteration,
        'CCGT_Capacity_MW': ccgt_capacity,
        'OCGT_Capacity_MW': ocgt_capacity,
        'Total_Thermal_Capacity_MW': total_thermal_capacity,
        'Scenario': DECARB_SCENARIO,
        'RO_Payment_Share_vs_2025': ro_payment_share,
        'FiT_Payment_Share_vs_2025': fit_payment_share,
        'RO_Legacy_Cost_Annual_GBP': ro_legacy_cost_annual,
        'FiT_Legacy_Cost_Annual_GBP': fit_legacy_cost_annual,
        'CfD_Baseline_Cost_Annual_GBP': cfd_baseline_cost,
        'CfD_New_Decarbonization_Cost_Annual_GBP': cfd_new_cost_annual,
        'Existing_Decarbonization_Cost_Annual_GBP': existing_decarb_cost,
        'Additional_Decarbonization_Cost_Annual_GBP': additional_decarb_cost,
        'Inherited_CfD_Agent_Income_GBP': inherited_cfd_agent_income,
        'New_CfD_Stimulus_GBP': new_cfd_stimulus,
        'Agent_Investable_Decarb_Income_GBP': agent_investable_decarb,
        'Annual_CfD_Increment_GBP': annual_cfd_increment,
        'Decarbonization_Cost_Annual_GBP': decarbonization_cost_annual,
        'CM_Cost_Annual_GBP': cm_cost_annual,
        'Total_VRE_Capacity_MW': total_vre_capacity
    })
    
    # Ensure all income columns are numeric before addition
    df_analysis['electricity_income'] = pd.to_numeric(df_analysis['electricity_income'], errors='coerce').fillna(0)
    df_analysis['hydrogen_income'] = pd.to_numeric(df_analysis['hydrogen_income'], errors='coerce').fillna(0)
    for col in ['ro_legacy_income', 'fit_legacy_income', 'cfd_baseline_income',
                'cfd_new_decarbonization_income', 'agent_decarbonization_income', 'decarbonization_income']:
        df_analysis[col] = pd.to_numeric(df_analysis[col], errors='coerce').fillna(0)
    df_analysis['cm_income'] = pd.to_numeric(df_analysis['cm_income'], errors='coerce').fillna(0)

    # total_income: market + agent investable decarb (existing levy excluded) + CM
    df_analysis['total_income'] = (
        df_analysis['electricity_income']
        + df_analysis['hydrogen_income']
        + df_analysis['agent_decarbonization_income']
        + df_analysis['cm_income']
    )
    df_analysis['net_revenue'] = df_analysis['total_income'] - df_analysis['operational_cost']

    # -------------------------------------------------------------------------
    # 4. Fetch capital costs and calculate payback period
    # -------------------------------------------------------------------------
    current_capital_costs = {name: asset.capital_cost for name, asset in {**generator_objects, **battery_objects}.items() if hasattr(asset, 'capital_cost')}
    df_analysis['capital_cost'] = df_analysis.index.map(lambda name: current_capital_costs.get(name, 0))

    df_analysis['payback_years'] = np.where(df_analysis['net_revenue'] > 0, df_analysis['capital_cost'] / df_analysis['net_revenue'], np.inf)

    # -------------------------------------------------------------------------
    # 5. Generate investment recommendations using the Four-Tiered Methodology
    # -------------------------------------------------------------------------
    df_analysis['asset_type'] = df_analysis.index.map(get_asset_type)

    preferred_rates = config.investment_methodology_external['preferred_rates']
    payback_targets = config.investment_parameters['target_payback_years']
    
    df_analysis['preferred_rate'] = df_analysis['asset_type'].map(preferred_rates)
    df_analysis['target_payback'] = df_analysis['asset_type'].map(payback_targets).fillna(payback_targets['default'])
    df_analysis['ROI'] = df_analysis['net_revenue'] / df_analysis['capital_cost'].replace(0, np.nan)

    def assign_recommendation(row):
        if row['ROI'] > row['preferred_rate']:
            return 'Invest_High'
        elif row['payback_years'] <= row['target_payback']:
            return 'Invest_Profit'
        elif row['net_revenue'] < 0:
            return 'Deplete'
        else:
            return 'Do_Nothing'
            
    df_analysis['recommendation'] = df_analysis.apply(assign_recommendation, axis=1)

    # Calculate suggested new capacity
    current_capacities = {}
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
                current_capacities[name] = asset.capacity_multiplier
        elif isinstance(asset, Battery):
            current_capacities[name] = asset.pool_limit
    
    # Map current capacities, filling missing values with 0 instead of NaN
    df_analysis['current_capacity'] = df_analysis.index.map(current_capacities).fillna(0)

    def replacement_capital_cost(row):
        """Use current capacity x current CAPEX for scalable technologies.

        Some wind agents store legacy capital_cost per weather-profile unit rather
        than per physical MW, which understates the ROI denominator after REPD
        capacity scaling. Investment decisions should compare annual net revenue
        with current replacement capital at the technology CAPEX.
        """
        asset_type = row['asset_type']
        cost_per_mw = config.capital_costs_per_mw.get(asset_type)
        if cost_per_mw and asset_type in {
            'solar', 'onshore', 'offshore',
            '1c_battery', '0.5c_battery', '0.25c_battery', 'battery',
        }:
            return float(row['current_capacity']) * float(cost_per_mw)
        return row['capital_cost']

    df_analysis['capital_cost'] = df_analysis.apply(replacement_capital_cost, axis=1)
    df_analysis['payback_years'] = np.where(
        df_analysis['net_revenue'] > 0,
        df_analysis['capital_cost'] / df_analysis['net_revenue'],
        np.inf,
    )
    df_analysis['ROI'] = df_analysis['net_revenue'] / df_analysis['capital_cost'].replace(0, np.nan)
    df_analysis['recommendation'] = df_analysis.apply(assign_recommendation, axis=1)
    
    # Debug: Check for any suspiciously large capacity values
    large_capacity = df_analysis[df_analysis['current_capacity'] > 10000]
    if not large_capacity.empty:
        print(f"  ⚠ Warning: Found {len(large_capacity)} assets with capacity > 10,000 MW:")
        for idx, row in large_capacity.iterrows():
            print(f"      {idx}: {row['current_capacity']:.2f} MW (asset_type: {row.get('asset_type', 'unknown')})")

    # Get expansion targets: each tech uses its own 全网平均 profile for 200 negative-demand-point limit
    # 原 0.03 导致 VRE 扩张过慢；改为 0.10 加快 VRE 扩张（每年上限约为临界容量的 10%）
    reald_path = config.file_paths.get('real_demand', '2022reald.csv')
    solar_limit = 0.20 * calculate_expansion_limit(reald_path, config.file_paths['vre_solar_profile'], negative_threshold=200)
    onshore_limit = 0.20 * calculate_expansion_limit(reald_path, config.file_paths['vre_onshore_profile'], negative_threshold=200)
    offshore_limit = 0.20 * calculate_expansion_limit(reald_path, config.file_paths['vre_offshore_profile'], negative_threshold=200)
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
    regulated_targets['onshore'] = onshore_limit
    regulated_targets['offshore'] = offshore_limit
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
            # Thermal expansion is enabled for CCGT, OCGT, and bio_and_waste.
            if asset_type in ['CCGT', 'OCGT', 'bio_and_waste']:
                target = regulated_targets.get(asset_type) or regulated_targets.get(row.name)
                return row['current_capacity'] * target
            elif asset_type in _sec.EXPANDABLE_STORAGE_KEYS:
                # Residual/frequency cap is the Invest_High headroom, but High must
                # never invest less than the Invest_Profit (own-profit) amount.
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
                return max(0, row['current_capacity'] - capacity_to_remove)

        return row['current_capacity']

    df_analysis['suggested_new_capacity'] = df_analysis.apply(calculate_new_capacity, axis=1)

    # ========================================================================
    # REVENUE-TO-INVESTMENT VERIFICATION MECHANISM
    # ========================================================================
    # This section verifies that revenue correctly flows into investment decisions
    if iteration == 1 or iteration % 5 == 0:  # Print every 5 iterations to avoid spam
        print(f"\n{'='*80}")
        print(f"REVENUE-TO-INVESTMENT VERIFICATION (Iteration {iteration})")
        print(f"{'='*80}")
        
        # Check key technologies: batteries, offshore, onshore, solar
        key_techs = ['1c_battery', '0.5c_battery', '0.25c_battery', 'offshore', 'onshore', 'solar']
        
        for tech in key_techs:
            tech_assets = df_analysis[df_analysis['asset_type'] == tech]
            if tech_assets.empty:
                print(f"\n  {tech.upper()}: No assets found in analysis")
                continue
            
            total_income = tech_assets['total_income'].sum()
            total_net_revenue = tech_assets['net_revenue'].sum()
            total_current_capacity = tech_assets['current_capacity'].sum()
            total_suggested_capacity = tech_assets['suggested_new_capacity'].sum()
            capacity_change = total_suggested_capacity - total_current_capacity
            
            recommendations = tech_assets['recommendation'].value_counts().to_dict()
            
            print(f"\n  {tech.upper()}:")
            print(f"    Total Income: {total_income:,.2f} GBP")
            print(f"    Total Net Revenue: {total_net_revenue:,.2f} GBP")
            print(f"    Current Capacity: {total_current_capacity:.2f} MW")
            print(f"    Suggested Capacity: {total_suggested_capacity:.2f} MW")
            print(f"    Capacity Change: {capacity_change:+.2f} MW")
            print(f"    Recommendations: {recommendations}")
            
            # Check if revenue exists but no investment
            if total_income > 0 and capacity_change <= 0.01:
                print(f"    ⚠️  WARNING: Has revenue ({total_income:,.2f} GBP) but no capacity expansion!")
                # Show individual assets
                for asset_name, row in tech_assets.iterrows():
                    if row['total_income'] > 0:
                        print(f"      - {asset_name}: Income={row['total_income']:,.2f}, "
                              f"Net Revenue={row['net_revenue']:,.2f}, "
                              f"ROI={row.get('ROI', 0):.4f}, "
                              f"Recommendation={row['recommendation']}, "
                              f"Capacity Change={row['suggested_new_capacity'] - row['current_capacity']:.2f} MW")
            
            # Check if no revenue but should have
            if total_income == 0 and total_current_capacity > 0:
                print(f"    ⚠️  WARNING: Has capacity ({total_current_capacity:.2f} MW) but no income!")
                # Check if income exists in original dict but wasn't mapped
                for asset_name in tech_assets.index:
                    if asset_name in clean_income_dict:
                        print(f"      - {asset_name}: Found in clean_income_dict with {clean_income_dict[asset_name]:,.2f} GBP")
                    elif asset_name in total_income_dict:
                        print(f"      - {asset_name}: Found in total_income_dict with {total_income_dict[asset_name]}")
        
        print(f"\n{'='*80}\n")

    # Handle Proportional Allocation for VRE/Battery 'Invest_High'
    tech_capacity_totals = df_analysis.groupby('asset_type')['current_capacity'].sum().to_dict()
    vre_battery_techs = [
        'solar', 'onshore', 'offshore',
        '1c_battery', '0.5c_battery', '0.25c_battery', 'hydrogen_battery',
    ]
    battery_techs = {"1c_battery", "0.5c_battery", "0.25c_battery", "hydrogen_battery"}
    vre_types = ['solar', 'onshore', 'offshore']
    vre_total_capacity = sum(tech_capacity_totals.get(t, 0) for t in vre_types)

    if SCENARIO_V2:
        use_desnz = bool(decarb_components.get('V2_Use_DESNZ_Regulated_Cap', False))
        agent_income_mode = str(decarb_components.get('V2_Agent_Income_Mode', ''))
        if use_desnz:
            regulated_targets = apply_desnz_regulated_cap(
                regulated_targets, tech_capacity_totals, current_year
            )
        agent_investable_decarb = float(decarb_components.get('Agent_Investable_Decarb_Income_GBP', 0.0))
        if agent_income_mode == 'annual_increment_until_tech_cap':
            cfd_driven_mw_by_tech = compute_cfd_mw_by_tech_until_tech_cap(
                agent_investable_decarb, tech_capacity_totals, current_year
            )
        elif agent_income_mode == 'subsidy_to_operational_target':
            cfd_driven_mw_by_tech = compute_cfd_mw_by_operational_headroom(
                agent_investable_decarb, tech_capacity_totals, current_year
            )
        else:
            cfd_driven_mw_by_tech = compute_cfd_mw_by_tech(
                agent_investable_decarb, tech_capacity_totals
            )
            if use_desnz:
                cfd_driven_mw_by_tech = clip_cfd_mw_to_desnz_headroom(
                    cfd_driven_mw_by_tech, tech_capacity_totals, current_year
                )
    else:
        investable_decarb = float(decarb_components.get('Agent_Investable_Decarb_Income_GBP', 0.0))
        cfd_driven_mw_by_tech: dict[str, float] = {t: 0.0 for t in vre_types}
        if investable_decarb > 0 and vre_total_capacity > 0:
            for tech_type in vre_types:
                cost_per_mw = config.capital_costs_per_mw.get(tech_type, 0)
                if cost_per_mw <= 0:
                    continue
                tech_share = tech_capacity_totals.get(tech_type, 0) / vre_total_capacity
                cfd_driven_mw_by_tech[tech_type] = (investable_decarb * tech_share) / cost_per_mw
        agent_investable_decarb = investable_decarb

    if iteration == 1 or iteration % 5 == 0:
        driven_total = sum(cfd_driven_mw_by_tech.values())
        tag = "V2 " if SCENARIO_V2 else ""
        if agent_investable_decarb > 0:
            print(
                f"  {tag}Agent investable decarb £{agent_investable_decarb/1e6:.1f}m is included "
                f"as agent revenue only; it is not converted into a direct MW top-up."
            )
        if SCENARIO_V2 and agent_income_mode in {
            "annual_increment_until_tech_cap",
            "subsidy_to_operational_target",
        }:
            from scenarios_v2.load_scenarios_v2 import desnz_headroom_mw, techs_below_desnz_ceiling

            eligible = techs_below_desnz_ceiling(tech_capacity_totals, current_year)
            headroom = desnz_headroom_mw(tech_capacity_totals, current_year)
            headroom_str = ", ".join(f"{t}={headroom[t]/1000:.1f}GW" for t in eligible) if eligible else "none"
            print(
                f"  {tag}Under-target techs: {eligible or 'none'}; headroom [{headroom_str}]; "
                f"agent £{agent_investable_decarb/1e6:.1f}m; consumer additional (cum) "
                f"£{_v2_cumulative_additional_decarb/1e6:.1f}m"
            )
        elif SCENARIO_V2 and agent_investable_decarb <= 0 and agent_income_mode in {
            "annual_increment_until_tech_cap",
            "subsidy_to_operational_target",
        }:
            print(
                f"  {tag}No new CfD stimulus or consumer additional increment "
                f"(all techs at operational DESNZ target)"
            )

    for tech_type in vre_battery_techs:
        # Demand-driven regulated_targets are annual expansion ceilings, not mandatory builds.
        annual_expansion_cap_mw = float(regulated_targets.get(tech_type, 0) or 0)
        if tech_type in battery_techs:
            # Residual/frequency cap applies only to Invest_High.
            # Invest_Profit uses own profit and must not be clamped by that cap.
            tech_agent_indices = df_analysis[
                (df_analysis["asset_type"] == tech_type)
                & (df_analysis["recommendation"] == "Invest_High")
            ].index
        else:
            tech_agent_indices = df_analysis[df_analysis['asset_type'] == tech_type].index
        if len(tech_agent_indices) == 0:
            continue

        current_caps = df_analysis.loc[tech_agent_indices, 'current_capacity'].astype(float)
        proposed_caps = df_analysis.loc[tech_agent_indices, 'suggested_new_capacity'].astype(float)
        proposed_additions = (proposed_caps - current_caps).clip(lower=0)
        total_proposed_addition = float(proposed_additions.sum())
        if total_proposed_addition <= 0:
            continue

        if tech_type in battery_techs:
            # Profit floor for each Invest_High agent (same formula as Invest_Profit).
            profit_floors = pd.Series(
                {
                    idx: _profit_based_addition_mw(df_analysis.loc[idx])
                    for idx in tech_agent_indices
                },
                dtype=float,
            )
            floor_total = float(profit_floors.sum())
            # Cap may raise High above profit; it must never push High below profit.
            allowed_addition = max(floor_total, min(total_proposed_addition, max(annual_expansion_cap_mw, 0.0)))
            if allowed_addition <= 0:
                df_analysis.loc[tech_agent_indices, "suggested_new_capacity"] = current_caps
                continue
            scale = allowed_addition / total_proposed_addition
            scaled = current_caps + proposed_additions * scale
            floored = current_caps + profit_floors
            df_analysis.loc[tech_agent_indices, "suggested_new_capacity"] = np.maximum(scaled, floored)
        else:
            allowed_addition = min(total_proposed_addition, max(annual_expansion_cap_mw, 0.0))
            if allowed_addition <= 0:
                df_analysis.loc[tech_agent_indices, 'suggested_new_capacity'] = current_caps
                continue

            scale = allowed_addition / total_proposed_addition
            df_analysis.loc[tech_agent_indices, 'suggested_new_capacity'] = current_caps + proposed_additions * scale

    # -------------------------------------------------------------------------
    # 6. Calculate and track system cost metrics
    # -------------------------------------------------------------------------
    # Calculate total levelized capital cost (annualized)
    total_capital_cost = 0
    discount_rate = 0.05  # 5% discount rate for levelization
    lifetimes = {
        'CCGT': 25, 'OCGT': 25, 'bio_and_waste': 25, 'Nuclear': 40, 'Hydro_natural_flow': 50,
        'solar': 25, 'onshore': 30, 'offshore': 30,
        '1c_battery': 10, '0.5c_battery': 10, '0.25c_battery': 10, 'battery': 10
    }
    
    for name, asset in {**generator_objects, **battery_objects}.items():
        if hasattr(asset, 'capital_cost'):
            asset_type = get_asset_type(name)
            lifetime = lifetimes.get(asset_type, 25)  # Default 25 years
            # Levelize capital cost: CRF = r(1+r)^n / ((1+r)^n - 1)
            if discount_rate > 0 and lifetime > 0:
                crf = (discount_rate * (1 + discount_rate)**lifetime) / ((1 + discount_rate)**lifetime - 1)
                annualized_capital_cost = asset.capital_cost * crf
            else:
                annualized_capital_cost = asset.capital_cost / lifetime if lifetime > 0 else 0
            total_capital_cost += annualized_capital_cost
    
    # Calculate total operational cost
    total_operational_cost_annual = sum(total_operational_costs.values())
    
    # Calculate energy deficit costs (lost value of electricity)
    # Record the scale of deficit and calculate lost value at 8000 per unit (MWh)
    DEFICIT_VALUE_PER_MWH = 8000  # Lost value per MWh of energy deficit
    total_energy_deficit_mwh = (sum(blackout_periods) * PHYSICAL_PERIOD_HOURS) if blackout_periods else 0
    number_of_deficit_periods = sum(1 for d in blackout_periods if d > 0) if blackout_periods else 0
    max_period_deficit_mwh = max(blackout_periods) if blackout_periods and len(blackout_periods) > 0 else 0
    lost_value_of_electricity = total_energy_deficit_mwh * DEFICIT_VALUE_PER_MWH
    
    # Calculate total system cost (physical + decarbonization levy + CM levy + deficit)
    decarb_levy_annual = existing_decarb_cost + additional_decarb_cost
    total_system_cost = (
        total_capital_cost
        + total_operational_cost_annual
        + lost_value_of_electricity
        + decarb_levy_annual
        + cm_cost_annual
    )
    
    # Calculate total energy generated
    total_energy_generated_mwh = sum(total_energy_generated.values()) * PHYSICAL_PERIOD_HOURS
    
    # Calculate cost per MWh
    if total_energy_generated_mwh > 0:
        cost_per_mwh = total_system_cost / total_energy_generated_mwh
    else:
        cost_per_mwh = 0
    
    # Store system cost metrics
    system_cost_history.append({
        'Year': current_year,
        'Iteration': iteration,
        'Total_Levelized_Capital_Cost_GBP': total_capital_cost,
        'Total_Operational_Cost_GBP': total_operational_cost_annual,
        'Total_Energy_Deficit_MWh': total_energy_deficit_mwh,
        'Number_of_Deficit_Periods': number_of_deficit_periods,
        'Max_Period_Deficit_MWh': max_period_deficit_mwh,
        'Lost_Value_of_Electricity_GBP': lost_value_of_electricity,
        'CM_Mechanism_Cost_Added_to_System_GBP': cm_cost_annual,
        'Decarbonization_Mechanism_Cost_Added_to_System_GBP': decarb_levy_annual,
        'Existing_Decarbonization_Cost_GBP': existing_decarb_cost,
        'Additional_Decarbonization_Cost_GBP': additional_decarb_cost,
        'Agent_Investable_Decarb_Income_GBP': agent_investable_decarb,
        'Total_System_Cost_GBP': total_system_cost,
        'Total_Energy_Generated_MWh': total_energy_generated_mwh,
        'Cost_per_MWh_GBP': cost_per_mwh
    })
    
    # Save analysis. FAST_ANALYSIS_OUTPUT avoids slow per-iteration Excel writes;
    # convert the SQLite tables to Excel after the run if a workbook is needed.
    financial_cols = ['asset_type', 'current_capacity', 'capital_cost', 'operational_cost', 'total_income']
    df_financials = df_analysis[financial_cols].copy() if all(c in df_analysis.columns for c in financial_cols) else df_analysis.copy()
    if os.getenv("FAST_ANALYSIS_OUTPUT", "0").strip().lower() in {"1", "true", "yes"}:
        import sqlite3

        output_file = _output_dir() / "investment_analysis_trace.sqlite"
        output_file.parent.mkdir(parents=True, exist_ok=True)
        df_analysis_out = df_analysis.reset_index().rename(columns={"index": "asset_name"})
        df_analysis_out.insert(0, "iteration", iteration)
        df_analysis_out.insert(0, "year", current_year)
        df_financials_out = df_financials.reset_index().rename(columns={"index": "asset_name"})
        df_financials_out.insert(0, "iteration", iteration)
        df_financials_out.insert(0, "year", current_year)
        with sqlite3.connect(output_file) as conn:
            for table in ("investment_analysis", "asset_financials"):
                if conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                    (table,),
                ).fetchone():
                    conn.execute(f"DELETE FROM {table} WHERE year = ? AND iteration = ?", (current_year, iteration))
            df_analysis_out.to_sql("investment_analysis", conn, if_exists="append", index=False)
            df_financials_out.to_sql("asset_financials", conn, if_exists="append", index=False)
        print(f"✓ Fast investment analysis saved to {output_file}")
    else:
        output_file = _iter_analysis_path(iteration)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with pd.ExcelWriter(_io_path(output_file), engine='openpyxl') as writer:
            df_analysis.to_excel(writer, sheet_name='Investment Analysis')
            df_financials.to_excel(writer, sheet_name='Asset Financials')
        print(f"✓ CM + decarbonization breakdown analysis saved to {output_file}")
    print(f"  System Cost: £{total_system_cost/1e9:.2f}bn | Cost/MWh: £{cost_per_mwh:.2f}")
    if total_energy_deficit_mwh > 0:
        print(f"  ⚠ Energy Deficit: {total_energy_deficit_mwh:.2f} MWh ({number_of_deficit_periods} periods) | Lost Value: £{lost_value_of_electricity/1e6:.2f}M")
    
    # -------------------------------------------------------------------------
    # Track VRE generation and excess generation profiles for final year (2034/iteration 10)
    # -------------------------------------------------------------------------
    global vre_generation_profile, excess_generation_profile, final_year, edinburgh_onshore_profiles, vre_excess_profiles
    
    # Store profiles for the final iteration (year 2034, iteration 10)
    if iteration == 10:
        # Calculate VRE generation per period (onshore + offshore + solar)
        vre_generation_by_period = []
        
        for period_idx, period_data in enumerate(gen_list_composition):
            vre_period_total = 0.0
            for asset, energy in period_data:
                if not isinstance(asset, Battery):
                    asset_name = asset.name
                    asset_type = get_asset_type(asset_name)
                    # Sum generation from solar, onshore, and offshore
                    if asset_type in ['solar', 'onshore', 'offshore']:
                        vre_period_total += energy
            vre_generation_by_period.append(vre_period_total)
        
        vre_generation_profile = vre_generation_by_period
        excess_generation_profile = excess_electricity if excess_electricity else []
        final_year = current_year
        
        print(f"  📊 VRE and excess generation profiles recorded for year {final_year}")
    
    # -------------------------------------------------------------------------
    # Track total VRE generation and overall excess generation for each year
    # -------------------------------------------------------------------------
    global vre_excess_profiles
    
    # Calculate total VRE and thermal generation per period
    total_vre_generation = []
    total_thermal_generation = []
    for period_idx, period_data in enumerate(gen_list_composition):
        vre_period_total = 0.0
        thermal_period_total = 0.0
        for asset, energy in period_data:
            if not isinstance(asset, Battery):
                asset_name = asset.name
                asset_type = get_asset_type(asset_name)
                if asset_type in ['solar', 'onshore', 'offshore']:
                    vre_period_total += energy
                else:
                    thermal_period_total += energy
        total_vre_generation.append(vre_period_total)
        total_thermal_generation.append(thermal_period_total)
    
    # Store totals (annual)
    total_vre_annual = sum(total_vre_generation)
    total_thermal_annual = sum(total_thermal_generation)
    total_excess_annual = sum(excess_electricity) if excess_electricity else 0
    
    # Calculate excess BEFORE storage/interconnection for comparison (VRE - forecast demand)
    # This helps diagnose why final excess might be low
    excess_before_storage = []
    for period_idx in range(len(total_vre_generation)):
        vre_gen = total_vre_generation[period_idx]
        forecast_demand_period = forecast_demands[period_idx] if period_idx < len(forecast_demands) else 0
        excess_pre_storage = max(0.0, vre_gen - forecast_demand_period)
        excess_before_storage.append(excess_pre_storage)
    total_excess_before_storage = sum(excess_before_storage)
    
    # Calculate what was absorbed: storage + interconnection + final excess
    # Get storage energy from results (store_electricity is at index 2: list of energy stored per period)
    store_electricity_list = results[2] if len(results) > 2 else []  # store_electricity is at index 2
    # Safely sum store_electricity, handling both lists and numbers
    total_stored = 0
    if store_electricity_list:
        try:
            # Try to sum directly if it's a list of numbers
            if isinstance(store_electricity_list, list):
                # Check if first element is a list (nested structure)
                if store_electricity_list and isinstance(store_electricity_list[0], (list, tuple)):
                    # Flatten nested lists
                    total_stored = sum(sum(float(x) if x is not None else 0 for x in item) if isinstance(item, (list, tuple)) else float(item) if item is not None else 0 for item in store_electricity_list)
                else:
                    # List of numbers
                    total_stored = sum(float(x) if x is not None else 0 for x in store_electricity_list)
            else:
                total_stored = float(store_electricity_list) if store_electricity_list is not None else 0
        except (TypeError, ValueError) as e:
            # If summing fails, just use 0 (diagnostic info not critical)
            total_stored = 0
            print(f"      ⚠ Could not calculate total stored energy: {e}")
    
    # Get sold fees (interconnection exports) from results - need to check index
    # sold_fees might be in results, let's check structure
    # For now, calculate absorbed as: excess_before - excess_after
    total_absorbed_by_storage_interconn = max(0, total_excess_before_storage - total_excess_annual)
    
    # Calculate total storage capacity
    total_storage_capacity = sum(bat.pool_limit for bat in batteries_list if hasattr(bat, 'pool_limit'))
    
    vre_excess_profiles[current_year] = {
        'total_vre_generation': list(total_vre_generation) if total_vre_generation else [],  # Make a copy
        'overall_excess': list(excess_electricity) if excess_electricity else [],  # Excess AFTER storage/interconnection
        'total_vre_annual': total_vre_annual,
        'total_excess_annual': total_excess_annual,
        'total_thermal_annual': total_thermal_annual,
        'total_generation_annual': total_vre_annual + total_thermal_annual
    }
    
    # Debug: Print capacity info for VRE generators
    vre_capacity_info = []
    total_solar_capacity = 0.0
    total_onshore_capacity = 0.0
    total_offshore_capacity = 0.0
    
    for name, asset in generator_objects.items():
        asset_type = get_asset_type(name)
        if asset_type in ['solar', 'onshore', 'offshore']:
            if isinstance(asset, ExpensiverenewableGenerator):
                BASE_UNIT = 20 if asset_type in ['onshore', 'offshore'] else 1
                capacity_mw = asset.capacity_multiplier * BASE_UNIT
                vre_capacity_info.append(f"{name}: {capacity_mw:.1f}MW")
                
                if asset_type == 'solar':
                    total_solar_capacity += capacity_mw
                elif asset_type == 'onshore':
                    total_onshore_capacity += capacity_mw
                elif asset_type == 'offshore':
                    total_offshore_capacity += capacity_mw
    
    total_vre_capacity_mw = total_solar_capacity + total_onshore_capacity + total_offshore_capacity
    
    # Track capacities for all technologies
    global capacity_history
    capacity_record = {
        'Year': current_year,
        'Iteration': iteration,
        'Solar_Capacity_MW': total_solar_capacity,
        'Onshore_Capacity_MW': total_onshore_capacity,
        'Offshore_Capacity_MW': total_offshore_capacity,
        'Total_VRE_Capacity_MW': total_vre_capacity_mw,
        'Total_Storage_Capacity_MW': total_storage_capacity,
    }
    
    # Track individual battery capacities
    for bat_name, bat_obj in battery_objects.items():
        if hasattr(bat_obj, 'pool_limit'):
            capacity_record[f'{bat_name}_Capacity_MW'] = bat_obj.pool_limit
        if hasattr(bat_obj, 'per_pool_limit'):
            capacity_record[f'{bat_name}_Per_Pool_Limit_MW'] = bat_obj.per_pool_limit
    
    # Track thermal and zero-carbon baseload capacities (CCGT, OCGT, Nuclear, Hydro, bio)
    ccgt_capacity = 0
    ocgt_capacity = 0
    nuclear_capacity = 0
    hydro_capacity = 0
    bio_capacity = 0
    for name, asset in generator_objects.items():
        if 'CCGT' in name.upper() and isinstance(asset, GasGenerator):
            ccgt_capacity += asset.capacity_limit
        elif 'OCGT' in name.upper() and isinstance(asset, GasGenerator):
            ocgt_capacity += asset.capacity_limit
        elif name == 'Nuclear' and isinstance(asset, NuclearGenerator):
            nuclear_capacity += getattr(asset, 'capacity_limit', 0)
        elif name == 'Hydro_natural_flow' and isinstance(asset, WaterGenerator):
            hydro_capacity += getattr(asset, 'capacity_limit', 0)
        elif name == 'bio_and_waste' and isinstance(asset, BiomassGenerator):
            bio_capacity += getattr(asset, 'capacity_limit', 0)
    capacity_record['CCGT_Capacity_MW'] = ccgt_capacity
    capacity_record['OCGT_Capacity_MW'] = ocgt_capacity
    capacity_record['Nuclear_Capacity_MW'] = nuclear_capacity
    capacity_record['Hydro_natural_flow_Capacity_MW'] = hydro_capacity
    capacity_record['bio_and_waste_Capacity_MW'] = bio_capacity
    capacity_record['Total_Thermal_Capacity_MW'] = ccgt_capacity + ocgt_capacity
    
    # Track electrolyzer capacity
    total_electrolyzer_capacity = 0
    for elec_name, elec_obj in electrolyzer_objects.items():
        if hasattr(elec_obj, 'capacity_limit'):
            capacity_record[f'{elec_name}_Capacity_MW'] = elec_obj.capacity_limit
            total_electrolyzer_capacity += elec_obj.capacity_limit
    capacity_record['Total_Electrolyzer_Capacity_MW'] = total_electrolyzer_capacity
    
    capacity_history.append(capacity_record)
    
    # Calculate total forecast demand
    total_forecast_demand = sum(forecast_demands) if forecast_demands is not None else 0
    
    print(f"  📊 Total VRE profiles recorded for year {current_year}")
    print(f"      CAPACITY EXPANSION:")
    print(f"         - Solar: {total_solar_capacity:.2f} MW | Onshore: {total_onshore_capacity:.2f} MW | Offshore: {total_offshore_capacity:.2f} MW")
    print(f"         - Total VRE Capacity: {total_vre_capacity_mw:.2f} MW")
    print(f"      GENERATION:")
    total_vre_mwh = total_vre_annual * PHYSICAL_PERIOD_HOURS
    total_thermal_mwh = total_thermal_annual * PHYSICAL_PERIOD_HOURS
    total_generation_mwh = total_vre_mwh + total_thermal_mwh
    total_forecast_mwh = total_forecast_demand * PHYSICAL_PERIOD_HOURS
    print(f"         - Total VRE Generation: {total_vre_mwh/1e6:.2f} TWh")
    print(f"         - Total Thermal Generation: {total_thermal_mwh/1e6:.2f} TWh")
    print(f"         - Total Generation (VRE+Thermal): {total_generation_mwh/1e6:.2f} TWh")
    print(f"         - Total Forecast Demand: {total_forecast_mwh/1e6:.2f} TWh")
    print(f"      EXCESS ANALYSIS:")
    print(f"         - Excess BEFORE storage/interconn: {total_excess_before_storage * PHYSICAL_PERIOD_HOURS / 1e6:.2f} TWh (VRE - Forecast)")
    print(f"         - Excess AFTER storage/interconn: {total_excess_annual * PHYSICAL_PERIOD_HOURS / 1e6:.2f} TWh (final excess)")
    print(f"         - Absorbed by storage/interconn: {total_absorbed_by_storage_interconn * PHYSICAL_PERIOD_HOURS / 1e6:.2f} TWh")
    print(f"         - Storage Capacity: {total_storage_capacity:.2f} MW")
    print(f"         - Excess/VRE Ratio (after): {(total_excess_annual/total_vre_annual*100) if total_vre_annual > 0 else 0:.2f}%")
    print(f"         - Excess/VRE Ratio (before): {(total_excess_before_storage/total_vre_annual*100) if total_vre_annual > 0 else 0:.2f}%")
    
    # -------------------------------------------------------------------------
    # Track Edinburgh onshore wind generation only (excess is always system-wide, see vre_excess_profiles)
    # -------------------------------------------------------------------------
    edinburgh_onshore_generation = []
    for period_idx, period_data in enumerate(gen_list_composition):
        edinburgh_period_total = 0.0
        for asset, energy in period_data:
            if not isinstance(asset, Battery) and asset.name == 'onshore_Edinburgh':
                edinburgh_period_total += energy
        edinburgh_onshore_generation.append(edinburgh_period_total)
    
    BASE_WIND_UNIT_MW = 20
    edinburgh_asset = generator_objects.get('onshore_Edinburgh')
    edinburgh_capacity_mw = (edinburgh_asset.capacity_multiplier * BASE_WIND_UNIT_MW) if (edinburgh_asset and isinstance(edinburgh_asset, ExpensiverenewableGenerator)) else 0
    
    edinburgh_onshore_profiles[current_year] = {
        'generation': list(edinburgh_onshore_generation) if edinburgh_onshore_generation else [],
        'capacity_mw': edinburgh_capacity_mw
    }
    print(f"  📊 Edinburgh onshore wind generation recorded for year {current_year} (Capacity: {edinburgh_capacity_mw:.2f} MW, Generation: {sum(edinburgh_onshore_generation):.2f} MWh)")
    
    return df_analysis


def main():
    """Main function to run Case 3 investment analysis"""
    global _v2_cumulative_additional_decarb
    global vre_generation_profile, excess_generation_profile, final_year
    global edinburgh_onshore_profiles, vre_excess_profiles

    os.environ["DECARB_SCENARIO"] = TRACE_SCENARIO_NAME
    print("="*80)
    if SCENARIO_V2:
        print(f"INVESTMENT ANALYSIS - CASE 3 V2 ({DECARB_V2_SCENARIO})")
    elif RUN_SUITE:
        print(f"INVESTMENT ANALYSIS - CASE 3 ARCHIVE ({RUN_SUITE})")
    else:
        print(f"INVESTMENT ANALYSIS - CASE 3 CM + DECARBONIZATION BREAKDOWN ({DECARB_SCENARIO})")
    print(f"OUTPUT_DIR={_output_dir()}")
    print("="*80)
    if SCENARIO_V2:
        from scenarios_v2.load_scenarios_v2 import write_scenarios_v2_csv
        v2_csv = _SCRIPT_DIR / "scenarios_v2" / "decarbonization_cost_scenarios_v2.csv"
        write_scenarios_v2_csv(str(v2_csv))
    else:
        write_scenario_csv()
    
    # Initialize generators and batteries from config
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
    # Initialize electrolyzers from config
    electrolyzer_objects = {'electrolyzer': Electrolyzer(**config.electrolyzer)}

    if VALIDATION_MODE:
        snapshot_year = int(os.getenv("VALIDATION_INITIAL_CAPACITY_YEAR", str(START_YEAR)))
        repd_file = os.getenv("VALIDATION_REPD_FILE", "repd-q2-jul-2025.csv")
        apply_validation_initial_capacity_snapshot(
            generator_objects,
            battery_objects,
            snapshot_year=snapshot_year,
            repd_file=repd_file,
        )
    else:
        apply_forward_repd_initial_stock_if_enabled(
            generator_objects,
            battery_objects,
            start_year=START_YEAR,
        )

    # Load external projects
    project_pipeline = load_external_projects()
    project_pipeline, zombie_removed = filter_zombie_external_pipeline(project_pipeline)
    if zombie_removed:
        print(f"Removed {zombie_removed} schedule-zombie external projects from pipeline (checkpoint-safe sweep)")
    project_pipeline, stock_removed = exclude_external_projects_already_in_stock(
        project_pipeline, snapshot_year=START_YEAR
    )
    if stock_removed:
        print(
            f"Excluded {stock_removed} external projects already in REPD operational stock "
            f"at {START_YEAR}"
        )
    success_rates = load_regional_technology_success_rates()
    project_pipeline, uncertain_repack = repackage_uncertain_repd_as_model_decisions(
        project_pipeline, success_rates
    )
    project_pipeline, excluded_past = normalize_external_pipeline_completion_years(project_pipeline)
    if excluded_past:
        print(f"Excluded {excluded_past} external projects scheduled before START_YEAR={START_YEAR}")
    project_pipeline, deferred_start = defer_start_year_external_pipeline_completions(
        project_pipeline, start_year=START_YEAR
    )
    if deferred_start:
        print(
            f"Deferred {deferred_start} external projects from START_YEAR={START_YEAR} "
            f"to {START_YEAR + 1} (operational stock already seeded)"
        )
    project_pipeline = apply_success_rates_to_repd_projects(project_pipeline, success_rates)
    
    # Map projects to generators based on location
    print("\n--- Mapping Projects to Generators by Location ---")
    project_pipeline, generator_weather_locations = map_projects_to_generators(
        project_pipeline, generator_objects, repd_file='repd-q2-jul-2025.csv'
    )
    
    # Count projects with location-based assignment
    location_mapped = sum(1 for p in project_pipeline if p.get('assigned_generator') is not None)
    print(f"Projects mapped to generators by location: {location_mapped} / {len(project_pipeline)}")
    
    # Store generator weather locations for later use in simulation
    # This will be used to create location-specific weather profiles
    if generator_weather_locations.get('offshore'):
        print(f"Offshore generators with location-specific weather profiles: {len(generator_weather_locations['offshore'])}")
    
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
    
    # Initialize pumped hydro with 2025 values for forward runs. Validation keeps
    # the config/start snapshot value so historical runs do not inject future plans.
    if (not VALIDATION_MODE) and 'pumpedhydro_battery' in battery_objects:
        initial_capacity = pumped_hydro_expansion_plan[2025]
        initial_energy_storage = pumped_hydro_energy_storage_plan[2025]
        initial_capex = pumped_hydro_capex_plan[2025]
        print(f"--- Case 3: Initializing Pumped Hydro. Start Capacity: {initial_capacity} MW, Start Energy Storage: {initial_energy_storage} MWh, Start CAPEX: £{initial_capex:,} ---")
        battery_objects['pumpedhydro_battery'].pool_limit = initial_capacity
        battery_objects['pumpedhydro_battery'].per_pool_limit = initial_energy_storage
        battery_objects['pumpedhydro_battery'].capital_cost = initial_capex
    
    investment_summary = []
    start_year = START_YEAR
    end_year = END_YEAR
    _v2_cumulative_additional_decarb = 0.0
    start_iteration_index = 0

    checkpoint_state = _load_checkpoint()
    if checkpoint_state:
        generator_objects = checkpoint_state["generator_objects"]
        battery_objects = checkpoint_state["battery_objects"]
        electrolyzer_objects = checkpoint_state["electrolyzer_objects"]
        project_pipeline = checkpoint_state["project_pipeline"]
        project_pipeline, zombie_removed = filter_zombie_external_pipeline(project_pipeline)
        if zombie_removed:
            print(
                f"Removed {zombie_removed} schedule-zombie external projects from restored checkpoint pipeline "
                f"(deadline <= {_repd_zombie_status_stale_year()})"
            )
        project_pipeline, stock_removed = exclude_external_projects_already_in_stock(
            project_pipeline, snapshot_year=START_YEAR
        )
        if stock_removed:
            print(
                f"Excluded {stock_removed} stock-overlap external projects from restored checkpoint "
                f"pipeline at {START_YEAR}"
            )
        project_pipeline, excluded_past = normalize_external_pipeline_completion_years(project_pipeline)
        if excluded_past:
            print(
                f"Excluded {excluded_past} pre-{START_YEAR} external projects from restored checkpoint pipeline"
            )
        project_pipeline, deferred_start = defer_start_year_external_pipeline_completions(
            project_pipeline, start_year=START_YEAR
        )
        if deferred_start:
            print(
                f"Deferred {deferred_start} START_YEAR external projects in restored checkpoint "
                f"pipeline to {START_YEAR + 1}"
            )
        investment_summary = checkpoint_state.get("investment_summary", [])
        success_rates = checkpoint_state.get("success_rates", success_rates)

        thermal_capacity_history[:] = checkpoint_state.get("thermal_capacity_history", [])
        system_cost_history[:] = checkpoint_state.get("system_cost_history", [])
        capacity_history[:] = checkpoint_state.get("capacity_history", [])

        vre_generation_profile = checkpoint_state.get("vre_generation_profile")
        excess_generation_profile = checkpoint_state.get("excess_generation_profile")
        final_year = checkpoint_state.get("final_year")
        edinburgh_onshore_profiles = checkpoint_state.get("edinburgh_onshore_profiles", {})
        vre_excess_profiles = checkpoint_state.get("vre_excess_profiles", {})
        _v2_cumulative_additional_decarb = float(checkpoint_state.get("v2_cumulative_additional_decarb", 0.0))

        start_iteration_index = int(checkpoint_state.get("next_iteration_index", 0))
        if start_iteration_index >= (end_year - start_year + 1):
            print("✓ Checkpoint indicates all years already completed; final outputs will be regenerated from saved history.")

    for i in range(start_iteration_index, end_year - start_year + 1):
        current_year = start_year + i
        print(f"\n{'='*20} YEAR {current_year} (CASE 3) {'='*20}")
        _apply_validation_dynamic_costs(current_year, generator_objects)
        
        # --- Apply Pre-defined Pumped Hydro Expansion Plan ---
        if (not VALIDATION_MODE) and current_year in pumped_hydro_expansion_plan:
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
        
        # Diagnostic: Count projects in pipeline by completion year
        pipeline_by_year = {}
        for project in project_pipeline:
            year = project.get('completion_year', 'Unknown')
            if year not in pipeline_by_year:
                pipeline_by_year[year] = []
            pipeline_by_year[year].append(project)
        
        if i == 0:  # Print pipeline distribution in first year
            print(f"\n  📋 Project Pipeline Status (Year {current_year}):")
            print(f"      Total projects in pipeline: {len(project_pipeline)}")
            upcoming_years = sorted([y for y in pipeline_by_year.keys() if isinstance(y, int) and y >= current_year])[:5]
            for year in upcoming_years:
                count = len(pipeline_by_year[year])
                capacity = sum(p.get('capacity', 0) for p in pipeline_by_year[year])
                print(f"      Year {year}: {count} projects ({capacity:.2f} MW scheduled)")
        
        # Process completed projects
        # First, group projects by technology type to enable proportional allocation
        projects_by_type = {}
        projects_completing_this_year = []
        for project in project_pipeline[:]:
            if project.get('completion_year') != current_year:
                continue
            if project.get('capacity', 0) <= 0 or project.get('project_succeeds') is False:
                project_pipeline.remove(project)
                continue
            asset_type = project['technology_type']
            if asset_type not in projects_by_type:
                projects_by_type[asset_type] = []
            projects_by_type[asset_type].append(project)
            projects_completing_this_year.append(project)
        
        if projects_completing_this_year:
            total_completing_capacity = sum(p.get('capacity', 0) for p in projects_completing_this_year)
            external_completing = [p for p in projects_completing_this_year if p.get('source') == 'external']
            model_completing = [p for p in projects_completing_this_year if p.get('source') == 'model']
            print(f"  📦 Projects completing in {current_year}: {len(projects_completing_this_year)} "
                  f"({total_completing_capacity:.2f} MW)")
            if external_completing:
                external_cap = sum(p.get('capacity', 0) for p in external_completing)
                print(f"      - External (REPD): {len(external_completing)} projects ({external_cap:.2f} MW)")
            if model_completing:
                model_cap = sum(p.get('capacity', 0) for p in model_completing)
                print(f"      - Model-driven: {len(model_completing)} projects ({model_cap:.2f} MW)")
        
        # Process each technology type
        for asset_type, projects in projects_by_type.items():
            # Calculate total capacity to add for this technology type in this year
            total_capacity_to_add = sum(p['capacity'] for p in projects)
            
            if asset_type == 'gas':
                # External gas projects are applied to their model target when
                # available; otherwise use CCGT as the generic gas representative.
                cost_per_mw = config.capital_costs_per_mw.get(asset_type, 0)
                for project in projects:
                    asset_name = project.get('target_asset_name') or project.get('assigned_generator') or 'CCGT'
                    if asset_name not in generator_objects:
                        asset_name = 'CCGT'
                    target_asset = generator_objects[asset_name]
                    old_limit = target_asset.capacity_limit
                    capacity_to_add = project['capacity']
                    target_asset.capacity_limit += capacity_to_add
                    investment_cost = capacity_to_add * cost_per_mw
                    if not hasattr(target_asset, 'capital_cost'):
                        target_asset.capital_cost = 0
                    target_asset.capital_cost += investment_cost
                    investment_summary.append({
                        'Year': current_year,
                        'Asset': asset_name,
                        'Source': project.get('source', 'unknown'),
                        'Added_Capacity_MW': capacity_to_add,
                        'Investment_Cost': investment_cost,
                        'Assignment_Method': 'Gas target or CCGT fallback'
                    })
                    print(f"    ✓ Updated {asset_name}: capacity_limit {old_limit:.2f} → {target_asset.capacity_limit:.2f} (+{capacity_to_add:.2f} MW)")
                    project_pipeline.remove(project)
            
            elif asset_type in ['solar', 'onshore', 'offshore']:
                # Separate projects with assigned generators from those without
                projects_with_assignment = [p for p in projects if p.get('assigned_generator') is not None]
                projects_without_assignment = [p for p in projects if p.get('assigned_generator') is None]
                
                cost_per_mw = config.capital_costs_per_mw.get(asset_type, 0)
                
                # Process projects with location-based assignments
                for project in projects_with_assignment:
                    assigned_gen = project['assigned_generator']
                    if assigned_gen in generator_objects:
                        asset = generator_objects[assigned_gen]
                        if isinstance(asset, ExpensiverenewableGenerator):
                            capacity_to_add = project['capacity']
                            BASE_UNIT = 20 if asset_type in ['onshore', 'offshore'] else 1
                            
                            old_multiplier = asset.capacity_multiplier
                            multiplier_increment = capacity_to_add / BASE_UNIT
                            asset.capacity_multiplier += multiplier_increment
                            old_capacity = old_multiplier * BASE_UNIT
                            new_capacity = asset.capacity_multiplier * BASE_UNIT
                            investment_cost = capacity_to_add * cost_per_mw
                            
                            if not hasattr(asset, 'capital_cost'):
                                asset.capital_cost = 0
                            asset.capital_cost += investment_cost
                            
                            location_info = project.get('location', {})
                            distance = project.get('distance_to_generator_km', 'N/A')
                            print(f"      ✓ {assigned_gen}: {old_capacity:.1f}MW → {new_capacity:.1f}MW "
                                  f"(+{capacity_to_add:.2f} MW, location-based assignment, "
                                  f"distance: {distance} km)")
                            
                            investment_summary.append({
                                'Year': current_year, 
                                'Asset': assigned_gen, 
                                'Source': project.get('source', 'unknown'), 
                                'Added_Capacity_MW': capacity_to_add,
                                'Investment_Cost': investment_cost,
                                'Assignment_Method': 'Location-based',
                                'Project_Location': f"{location_info.get('lat', 'N/A')}, {location_info.get('lon', 'N/A')}"
                            })
                            project_pipeline.remove(project)
                
                # Process projects without location assignments using proportional allocation
                if projects_without_assignment:
                    total_capacity_unassigned = sum(p['capacity'] for p in projects_without_assignment)
                    
                    matching_assets = []
                    total_existing_capacity = 0
                    
                    for name, asset in generator_objects.items():
                        if isinstance(asset, ExpensiverenewableGenerator):
                            name_asset_type = get_asset_type(name)
                            if name_asset_type == asset_type:
                                BASE_UNIT = 20 if asset_type in ['onshore', 'offshore'] else 1
                                current_capacity = asset.capacity_multiplier * BASE_UNIT
                                matching_assets.append({
                                    'name': name,
                                    'asset': asset,
                                    'current_capacity': current_capacity,
                                    'base_unit': BASE_UNIT
                                })
                                total_existing_capacity += current_capacity
                    
                    if matching_assets and total_existing_capacity > 0:
                        remaining_capacity = total_capacity_unassigned
                        matching_assets.sort(key=lambda x: x['name'])
                        
                        print(f"    📊 Allocating {total_capacity_unassigned:.2f} MW {asset_type} capacity (no location data) "
                              f"across {len(matching_assets)} generators (total existing: {total_existing_capacity:.2f} MW)")
                        
                        for idx, match_info in enumerate(matching_assets):
                            name = match_info['name']
                            asset = match_info['asset']
                            BASE_UNIT = match_info['base_unit']
                            current_capacity = match_info['current_capacity']
                            capacity_share = current_capacity / total_existing_capacity
                            
                            if idx == len(matching_assets) - 1:
                                allocated_capacity = remaining_capacity
                            else:
                                allocated_capacity = total_capacity_unassigned * capacity_share
                                remaining_capacity -= allocated_capacity
                            
                            if allocated_capacity > 1e-6:
                                old_multiplier = asset.capacity_multiplier
                                multiplier_increment = allocated_capacity / BASE_UNIT
                                asset.capacity_multiplier += multiplier_increment
                                old_capacity = old_multiplier * BASE_UNIT
                                new_capacity = asset.capacity_multiplier * BASE_UNIT
                                investment_cost = allocated_capacity * cost_per_mw
                                
                                if not hasattr(asset, 'capital_cost'):
                                    asset.capital_cost = 0
                                asset.capital_cost += investment_cost
                                
                                print(f"      ✓ {name}: {old_capacity:.1f}MW → {new_capacity:.1f}MW "
                                      f"(+{allocated_capacity:.2f} MW, {capacity_share*100:.2f}% share, proportional)")
                        
                        # Record investments
                        for project in projects_without_assignment:
                            project_capacity = project['capacity']
                            for match_info in matching_assets:
                                name = match_info['name']
                                current_capacity = match_info['current_capacity']
                                asset_share = current_capacity / total_existing_capacity
                                allocated_capacity = project_capacity * asset_share
                                if allocated_capacity > 1e-6:
                                    investment_summary.append({
                                        'Year': current_year, 
                                        'Asset': name, 
                                        'Source': project.get('source', 'unknown'), 
                                        'Added_Capacity_MW': allocated_capacity,
                                        'Investment_Cost': allocated_capacity * cost_per_mw,
                                        'Assignment_Method': 'Proportional'
                                    })
                            project_pipeline.remove(project)
                    else:
                        # Fallback: no matching VRE assets, use first matching generator
                        asset_name = next((name for name in {**generator_objects, **battery_objects}
                                         if asset_type in name.lower()), None)
                        if asset_name:
                            capacity_to_add = total_capacity_unassigned
                            investment_cost = capacity_to_add * cost_per_mw
                            target_asset = None
                            if asset_name in generator_objects:
                                target_asset = generator_objects[asset_name]
                                if isinstance(target_asset, ExpensiverenewableGenerator):
                                    old_multiplier = target_asset.capacity_multiplier
                                    BASE_UNIT = 20 if asset_type in ['onshore', 'offshore'] else 1
                                    target_asset.capacity_multiplier += capacity_to_add / BASE_UNIT
                                    old_capacity = old_multiplier * BASE_UNIT
                                    new_capacity = target_asset.capacity_multiplier * BASE_UNIT
                                    print(f"    ✓ Fallback {asset_name}: {old_capacity:.1f}MW → {new_capacity:.1f}MW (+{capacity_to_add:.2f} MW)")
                                else:
                                    target_asset.capacity_limit += capacity_to_add
                            elif asset_name in battery_objects:
                                target_asset = battery_objects[asset_name]
                                target_asset.pool_limit = max(0, target_asset.pool_limit + capacity_to_add)
                            if target_asset:
                                if not hasattr(target_asset, 'capital_cost'):
                                    target_asset.capital_cost = 0
                                target_asset.capital_cost += investment_cost
                            for project in projects_without_assignment:
                                investment_summary.append({
                                    'Year': current_year, 'Asset': asset_name, 'Source': project.get('source', 'unknown'),
                                    'Added_Capacity_MW': project['capacity'], 'Investment_Cost': project['capacity'] * cost_per_mw
                                })
                                project_pipeline.remove(project)
            
            elif asset_type == 'battery':
                for project in projects:
                    apply_electrochemical_battery_expansion(
                        battery_objects,
                        project['capacity'],
                        current_year,
                        investment_summary,
                        project.get('source', 'unknown'),
                        assignment_method='REPD/model battery → 1C/0.5C/0.25C proportional',
                    )
                    project_pipeline.remove(project)

            elif asset_type == 'pumped_hydro':
                # Pumped hydro capacity is governed only by the exogenous schedule.
                for project in projects:
                    project_pipeline.remove(project)

            else:
                # For other types (battery, electrolyzer), use first matching asset
                asset_name = None
                if projects and projects[0].get('target_asset_name'):
                    asset_name = projects[0]['target_asset_name']
                elif projects and projects[0].get('assigned_generator'):
                    asset_name = projects[0]['assigned_generator']
                if asset_name is None:
                    asset_name = next((name for name in {**generator_objects, **battery_objects, **electrolyzer_objects}
                                     if get_asset_type(name) == asset_type or asset_type.lower() in name.lower()), None)
                if asset_name:
                    capacity_to_add = total_capacity_to_add
                    cost_per_mw = config.capital_costs_per_mw.get(asset_type, 0)
                    investment_cost = capacity_to_add * cost_per_mw
                    
                    target_asset = None
                    if asset_name in generator_objects:
                        target_asset = generator_objects[asset_name]
                        old_limit = target_asset.capacity_limit
                        target_asset.capacity_limit += capacity_to_add
                        print(f"    ✓ Updated {asset_name}: capacity_limit {old_limit:.2f} → {target_asset.capacity_limit:.2f}")
                    elif asset_name in battery_objects:
                        target_asset = battery_objects[asset_name]
                        target_asset.pool_limit = max(0, target_asset.pool_limit + capacity_to_add)
                    elif asset_name in electrolyzer_objects:
                        target_asset = electrolyzer_objects[asset_name]
                        old_limit = target_asset.capacity_limit
                        target_asset.capacity_limit += capacity_to_add
                        print(f"    ✓ Updated {asset_name}: capacity_limit {old_limit:.2f} → {target_asset.capacity_limit:.2f}")
                    
                    if target_asset:
                        if not hasattr(target_asset, 'capital_cost'):
                            target_asset.capital_cost = 0
                        target_asset.capital_cost += investment_cost

                    for project in projects:
                        investment_summary.append({
                            'Year': current_year, 
                            'Asset': asset_name, 
                            'Source': project.get('source', 'unknown'), 
                            'Added_Capacity_MW': project['capacity'],
                            'Investment_Cost': project['capacity'] * cost_per_mw
                        })
                        project_pipeline.remove(project)
        
        # Run investment analysis
        df_analysis = analyze_investment_case3(i + 1, generator_objects, battery_objects, electrolyzer_objects)
        
        # Add new model-driven investments to pipeline
        battery_investments_count = 0
        for asset_name, row in df_analysis.iterrows():
            if row['recommendation'] != 'Do_Nothing':
                capacity_to_add = row['suggested_new_capacity'] - row['current_capacity']
                
                if abs(capacity_to_add) < 1e-6:
                    continue

                asset_type = get_asset_type(asset_name)
                if asset_type == 'pumped_hydro':
                    continue

                # Debug output for batteries
                if asset_type in ['1c_battery', '0.5c_battery', '0.25c_battery', 'battery']:
                    battery_investments_count += 1
                    print(f"    🔋 Battery Investment: {asset_name} - Recommendation: {row['recommendation']}, "
                          f"Current: {row['current_capacity']:.2f} MW, Suggested: {row['suggested_new_capacity']:.2f} MW, "
                          f"Add: {capacity_to_add:.2f} MW, ROI: {row.get('ROI', 'N/A'):.4f}")
                
                append_model_investment_to_pipeline(
                    project_pipeline,
                    name=f"Model Decision (Case 3): {asset_name}",
                    technology_type=asset_type,
                    capacity=capacity_to_add,
                    decision_year=current_year,
                    target_asset_name=asset_name,
                    success_rates=success_rates,
                    assigned_generator=asset_name,
                )
        _save_checkpoint(
            completed_year=current_year,
            next_iteration_index=i + 1,
            generator_objects=generator_objects,
            battery_objects=battery_objects,
            electrolyzer_objects=electrolyzer_objects,
            project_pipeline=project_pipeline,
            investment_summary=investment_summary,
            success_rates=success_rates,
        )
        
        if battery_investments_count == 0:
            # Check if batteries are in the analysis
            battery_names = [name for name in df_analysis.index if get_asset_type(name) in ['1c_battery', '0.5c_battery', '0.25c_battery', 'battery']]
            if battery_names:
                print(f"    ⚠️ Batteries found in analysis but no investments recommended:")
                for bat_name in battery_names:
                    if bat_name in df_analysis.index:
                        row = df_analysis.loc[bat_name]
                        print(f"      - {bat_name}: Recommendation={row.get('recommendation', 'N/A')}, "
                              f"ROI={row.get('ROI', 'N/A'):.4f}, Net Revenue={row.get('net_revenue', 'N/A'):.2f}, "
                              f"Current Capacity={row.get('current_capacity', 'N/A'):.2f} MW")
            else:
                print(f"    ⚠️ No batteries found in analysis DataFrame!")
    
    legacy_model = [
        p for p in project_pipeline
        if p.get("source") == "model" and not p.get("success_rate_applied")
    ]
    if legacy_model:
        updated = apply_success_rates_to_model_investments(legacy_model, success_rates)
        by_name = {p["name"]: p for p in updated}
        project_pipeline = [by_name.get(p.get("name"), p) for p in project_pipeline]

    # Save thermal capacity history (optional - can also extract from Excel files)
    if thermal_capacity_history:
        df_thermal = pd.DataFrame(thermal_capacity_history)
        thermal_file = _output_dir() / f'thermal_capacity_history_{OUTPUT_SUFFIX}.csv'
        df_thermal.to_csv(_io_path(thermal_file), index=False)
        print(f"\n✓ Thermal capacity history saved to {thermal_file}")
    else:
        print(f"\n⚠ No thermal capacity history tracked. You can extract it from Excel files using:")
        print(f"   python extract_thermal_capacity_from_analysis.py")
    
    # Save system cost history
    if system_cost_history:
        df_system_cost = pd.DataFrame(system_cost_history)
        system_cost_file = _output_dir() / f'system_cost_history_{OUTPUT_SUFFIX}.csv'
        df_system_cost.to_csv(_io_path(system_cost_file), index=False)
        print(f"✓ System cost history saved to {system_cost_file}")
    
    # Save capacity history
    if capacity_history:
        df_capacity = pd.DataFrame(capacity_history)
        capacity_file = _output_dir() / f'capacity_history_{OUTPUT_SUFFIX}.csv'
        df_capacity.to_csv(_io_path(capacity_file), index=False)
        print(f"✓ Capacity history saved to {capacity_file}")
    
    # Save investment summary
    df_summary = pd.DataFrame(investment_summary)
    if not df_summary.empty:
        summary_file = _output_dir() / f'investment_summary_{OUTPUT_SUFFIX}.csv'
        df_summary.to_csv(_io_path(summary_file), index=False)
        print(f"✓ Investment summary saved to {summary_file}")
    
    # -------------------------------------------------------------------------
    # Calculate and save VRE vs Excess Generation comparison for final year
    # -------------------------------------------------------------------------
    if vre_generation_profile is not None and excess_generation_profile is not None:
        print(f"\n{'='*80}")
        print(f"VRE vs 全网 EXCESS GENERATION ANALYSIS - YEAR {final_year}")
        print(f"{'='*80}")
        
        # Ensure both profiles have the same length
        min_length = min(len(vre_generation_profile), len(excess_generation_profile))
        vre_profile = vre_generation_profile[:min_length]
        excess_profile = excess_generation_profile[:min_length]
        
        # Create comparison DataFrame
        comparison_data = {
            'Period': range(min_length),
            'VRE_Generation_MWh': vre_profile,
            'Excess_Generation_MWh': excess_profile,
            'Difference_MWh': [vre - excess for vre, excess in zip(vre_profile, excess_profile)],
            'Excess_as_Percent_of_VRE': [100 * (excess / vre) if vre > 0 else 0 for vre, excess in zip(vre_profile, excess_profile)]
        }
        
        df_comparison = pd.DataFrame(comparison_data)
        
        # Calculate summary statistics
        total_vre_generation = sum(vre_profile)
        total_excess_generation = sum(excess_profile)
        avg_vre_generation = np.mean(vre_profile) if vre_profile else 0
        avg_excess_generation = np.mean(excess_profile) if excess_profile else 0
        max_vre_generation = max(vre_profile) if vre_profile else 0
        max_excess_generation = max(excess_profile) if excess_profile else 0
        periods_with_excess = sum(1 for e in excess_profile if e > 0)
        excess_periods_percent = (periods_with_excess / min_length * 100) if min_length > 0 else 0
        
        output_file = f'vre_vs_system_wide_excess_comparison_{final_year}.csv'
        df_comparison.to_csv(output_file, index=False)
        print(f"✓ VRE vs 全网 excess comparison saved to {output_file}")
        
        # Print summary
        print(f"\nSummary Statistics for Year {final_year}:")
        print(f"  Total VRE Generation: {total_vre_generation:,.2f} MWh")
        print(f"  Total Excess Generation: {total_excess_generation:,.2f} MWh")
        print(f"  Excess as % of VRE: {(total_excess_generation/total_vre_generation*100) if total_vre_generation > 0 else 0:.2f}%")
        print(f"  Average VRE per Period: {avg_vre_generation:.2f} MWh")
        print(f"  Average Excess per Period: {avg_excess_generation:.2f} MWh")
        print(f"  Maximum VRE (single period): {max_vre_generation:.2f} MWh")
        print(f"  Maximum Excess (single period): {max_excess_generation:.2f} MWh")
        print(f"  Periods with Excess: {periods_with_excess} out of {min_length} ({excess_periods_percent:.1f}%)")
        
        # Save summary statistics
        summary_data = {
            'Year': [final_year],
            'Total_VRE_Generation_MWh': [total_vre_generation],
            'Total_Excess_Generation_MWh': [total_excess_generation],
            'Excess_as_Percent_of_VRE': [(total_excess_generation/total_vre_generation*100) if total_vre_generation > 0 else 0],
            'Average_VRE_per_Period_MWh': [avg_vre_generation],
            'Average_Excess_per_Period_MWh': [avg_excess_generation],
            'Max_VRE_Single_Period_MWh': [max_vre_generation],
            'Max_Excess_Single_Period_MWh': [max_excess_generation],
            'Periods_with_Excess': [periods_with_excess],
            'Total_Periods': [min_length],
            'Excess_Periods_Percent': [excess_periods_percent]
        }
        df_summary_stats = pd.DataFrame(summary_data)
        summary_file = f'vre_vs_system_wide_excess_summary_{final_year}.csv'
        df_summary_stats.to_csv(summary_file, index=False)
        print(f"✓ 全网 excess summary saved to {summary_file}")
    else:
        print(f"\n⚠ VRE and 全网 excess generation profiles not available for final year analysis")
    
    # -------------------------------------------------------------------------
    # Extract and save Edinburgh onshore wind generation only (no excess; excess = 全网 only)
    # -------------------------------------------------------------------------
    if edinburgh_onshore_profiles:
        print(f"\n{'='*80}")
        print(f"EDINBURGH ONSHORE WIND GENERATION (generation only; excess = 全网, see below)")
        print(f"{'='*80}")
        
        sorted_years = sorted(edinburgh_onshore_profiles.keys())
        all_periods_data = []
        summary_data = []
        
        for year in sorted_years:
            profile_data = edinburgh_onshore_profiles[year]
            generation = profile_data['generation']
            capacity_mw = profile_data.get('capacity_mw', 0)
            min_len = len(generation)
            
            for period in range(min_len):
                all_periods_data.append({
                    'Year': year,
                    'Period': period,
                    'Edinburgh_Onshore_Generation_MWh': generation[period],
                    'Capacity_MW': capacity_mw
                })
            
            total_gen = sum(generation)
            avg_gen = np.mean(generation) if generation else 0
            max_gen = max(generation) if generation else 0
            summary_data.append({
                'Year': year,
                'Capacity_MW': capacity_mw,
                'Total_Edinburgh_Onshore_Generation_MWh': total_gen,
                'Average_Generation_per_Period_MWh': avg_gen,
                'Max_Generation_Single_Period_MWh': max_gen,
                'Total_Periods': min_len
            })
        
        df_all_periods = pd.DataFrame(all_periods_data)
        df_all_periods.to_csv('edinburgh_onshore_generation_all_years_detailed.csv', index=False)
        print(f"✓ Edinburgh generation (all years) saved to edinburgh_onshore_generation_all_years_detailed.csv")
        
        df_summary_yearly = pd.DataFrame(summary_data)
        df_summary_yearly.to_csv('edinburgh_onshore_generation_summary_by_year.csv', index=False)
        print(f"✓ Edinburgh generation summary saved to edinburgh_onshore_generation_summary_by_year.csv")
        
        for year in sorted_years:
            g = edinburgh_onshore_profiles[year]['generation']
            c = edinburgh_onshore_profiles[year].get('capacity_mw', 0)
            df_year = pd.DataFrame({'Period': range(len(g)), 'Edinburgh_Onshore_Generation_MWh': g, 'Capacity_MW': [c] * len(g)})
            df_year.to_csv(f'edinburgh_onshore_generation_{year}.csv', index=False)
        print(f"✓ Individual year files saved (edinburgh_onshore_generation_YYYY.csv for years {min(sorted_years)}-{max(sorted_years)})")
        
        print(f"\nSummary for Edinburgh Onshore Wind ({min(sorted_years)}-{max(sorted_years)}):")
        print(f"  Years tracked: {len(sorted_years)}")
        print(f"  Total generation across all years: {sum(s['Total_Edinburgh_Onshore_Generation_MWh'] for s in summary_data):,.2f} MWh")
        avg_gen_all = np.mean([s['Average_Generation_per_Period_MWh'] for s in summary_data])
        print(f"  Average generation per period (all years): {avg_gen_all:.4f} MWh")
        print(f"\n  Year-by-year breakdown:")
        for s in summary_data:
            print(f"    {s['Year']}: Capacity={s['Capacity_MW']:.2f} MW, Gen={s['Total_Edinburgh_Onshore_Generation_MWh']:,.2f} MWh")
    else:
        print(f"\n⚠ Edinburgh onshore wind profiles not available")
    
    # -------------------------------------------------------------------------
    # Save 全网 (system-wide) excess generation profile: total VRE + overall excess only
    # -------------------------------------------------------------------------
    if vre_excess_profiles:
        print(f"\n{'='*80}")
        print(f"全网 EXCESS GENERATION PROFILE (Total VRE + System-Wide Excess)")
        print(f"{'='*80}")
        
        sorted_years = sorted(vre_excess_profiles.keys())
        vre_excess_data = []
        vre_excess_summary = []
        
        for year in sorted_years:
            profile_data = vre_excess_profiles[year]
            vre_gen = profile_data['total_vre_generation']
            overall_excess = profile_data['overall_excess']
            
            min_len = min(len(vre_gen), len(overall_excess))
            vre_gen = vre_gen[:min_len]
            overall_excess = overall_excess[:min_len]
            
            # Period-by-period data
            for period in range(min_len):
                vre_excess_data.append({
                    'Year': year,
                    'Period': period,
                    'Total_VRE_Generation_MWh': vre_gen[period],
                    'Overall_Excess_Generation_MWh': overall_excess[period],
                    'Excess_as_Ratio_of_VRE': (overall_excess[period] / vre_gen[period]) if vre_gen[period] > 0 else 0
                })
            
            # Summary statistics
            total_vre = sum(vre_gen)
            total_excess = sum(overall_excess)
            avg_vre = np.mean(vre_gen) if vre_gen else 0
            avg_excess = np.mean(overall_excess) if overall_excess else 0
            max_vre = max(vre_gen) if vre_gen else 0
            max_excess = max(overall_excess) if overall_excess else 0
            periods_with_excess = sum(1 for e in overall_excess if e > 0)
            excess_ratio = (total_excess / total_vre) if total_vre > 0 else 0
            
            vre_excess_summary.append({
                'Year': year,
                'Total_VRE_Generation_MWh': total_vre,
                'Total_Overall_Excess_MWh': total_excess,
                'Excess_as_Ratio_of_VRE': excess_ratio,
                'Average_VRE_per_Period_MWh': avg_vre,
                'Average_Excess_per_Period_MWh': avg_excess,
                'Max_VRE_Single_Period_MWh': max_vre,
                'Max_Excess_Single_Period_MWh': max_excess,
                'Periods_with_Excess': periods_with_excess,
                'Total_Periods': min_len
            })
        
        # Save detailed data
        df_vre_excess = pd.DataFrame(vre_excess_data)
        vre_excess_file = 'system_wide_excess_generation_profile_all_years.csv'
        df_vre_excess.to_csv(vre_excess_file, index=False)
        print(f"✓ 全网 excess generation profile (all years) saved to {vre_excess_file}")
        
        df_vre_excess_summary = pd.DataFrame(vre_excess_summary)
        vre_excess_summary_file = 'system_wide_excess_summary_by_year.csv'
        df_vre_excess_summary.to_csv(vre_excess_summary_file, index=False)
        print(f"✓ 全网 excess summary by year saved to {vre_excess_summary_file}")
        
        # Save individual year files
        for year in sorted_years:
            profile_data = vre_excess_profiles[year]
            vre_gen = profile_data['total_vre_generation']
            overall_excess = profile_data['overall_excess']
            
            min_len = min(len(vre_gen), len(overall_excess))
            year_data = {
                'Period': range(min_len),
                'Total_VRE_Generation_MWh': vre_gen[:min_len],
                'Overall_Excess_Generation_MWh': overall_excess[:min_len],
                'Excess_as_Ratio_of_VRE': [(e / v) if v > 0 else 0 for v, e in zip(vre_gen[:min_len], overall_excess[:min_len])]
            }
            df_year = pd.DataFrame(year_data)
            year_file = f'system_wide_excess_generation_profile_{year}.csv'
            df_year.to_csv(year_file, index=False)
        
        print(f"✓ Individual year files saved (system_wide_excess_generation_profile_YYYY.csv for years {min(sorted_years)}-{max(sorted_years)})")
    
    print("\n" + "="*80)
    print("CASE 3 ANALYSIS COMPLETE")
    print("="*80)
    
    return df_thermal, df_summary


if __name__ == "__main__":
    import sys
    import io

    class Tee(io.TextIOBase):
        """Duplicate stdout to console and buffer."""
        def __init__(self, original, buffer):
            self.original = original
            self.buffer = buffer
        def write(self, s):
            self.original.write(s)
            self.buffer.write(s)
            return len(s)
        def flush(self):
            self.original.flush()
            self.buffer.flush()

    original_stdout = sys.stdout
    buffer = io.StringIO()
    sys.stdout = Tee(original_stdout, buffer)

    try:
        main()
    finally:
        # Restore stdout
        sys.stdout = original_stdout
        try:
            log_lines = buffer.getvalue().splitlines()
            if log_lines:
                if os.getenv("FAST_ANALYSIS_OUTPUT", "0").strip().lower() in {"1", "true", "yes"}:
                    console_log = _output_dir() / 'console_log_case3.log'
                    console_log.write_text("\n".join(log_lines), encoding="utf-8", errors="replace")
                else:
                    df_log = pd.DataFrame({'log': log_lines})
                    console_log = _output_dir() / 'console_log_case3.xlsx'
                    df_log.to_excel(_io_path(console_log), index=False)
                print(f"✓ Console log saved to {console_log}")
        except Exception as e:
            print(f"⚠ Failed to save console log: {e}")

