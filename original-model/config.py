# config.py

"""
This file centralizes all the parameters for the electricity market simulation model.
Modify the values in this file to run different scenarios and analyses.
"""

import os

# -----------------------------------------------------------------------------
# Simulation Parameters
# -----------------------------------------------------------------------------
simulation_parameters = {
    "output_file": "investment_results.csv",
    "solar_data": r"E:\newfinalweather\average_annual_solar_profile.nc",
    "wind_data": r"E:\newfinalweather\average_annual_wind_profile.nc",
    "simulation_years": 1,
    "price_multiplier": 1,
    "periods": 17520,  # Number of simulation periods (e.g., 17520 for 2 years of half-hourly data)
    "bidding_factor": 1.0,  # Factor to adjust bidding prices
}

# -----------------------------------------------------------------------------
# File Paths for Input Data
# -----------------------------------------------------------------------------
# Make sure to use absolute paths or paths relative to the script's location.
file_paths = {
    "forecast_demand": "2022fd.csv",
    "real_demand": "2022reald.csv",
    "solar_data": "2022solar.nc",
    "wind_data": "2022wind100m.grib",
    "france_profile": "France_profile.csv",
    "france_price": "France.csv",
    "belgium_profile": "belgium_profile.csv",
    "belgium_price": "Belgium_price.csv",
    "netherlands_profile": "nehtheralnd_profile.csv",
    "netherlands_price": "Netherlands.csv",
    "norway_profile": "Norway_profile.csv",
    "norway_price": "Norway.csv",
    "ireland_profile": "Ireland_profile.csv",
    "ireland_price": "Ireland.csv",
    # VRE capacity limit: 全网平均 profile for each tech (net demand = system demand - existing VRE; 200 negative points threshold)
    "vre_solar_profile": "sa.csv",
    "vre_onshore_profile": "wa.csv",
    "vre_offshore_profile": "we.csv",
}

# -----------------------------------------------------------------------------
# Investment Analysis Parameters
# -----------------------------------------------------------------------------
investment_parameters = {
    "hydrogen_price_per_kg": 2.0,  # Price of green hydrogen in £/kg
    "investment_increment_percentage": 1,  # Propose a 10% capacity increase for good investments
    "target_payback_years": {
        "default": 25,
        "solar": 25,
        "onshore": 30,
        "offshore": 30,
        "gas": 20,
        "bio_and_waste": 20,
        "battery": 10,
        "1c_battery": 10,
        "0.5c_battery": 10,
        "0.25c_battery": 10,
        "electrolyzer": 10
    }
}

# -----------------------------------------------------------------------------
# Generator Parameters
# -----------------------------------------------------------------------------
# Structure: 'generator_name': {**kwargs for the corresponding Generator class}
generators = {
    # Flexible Generators，ccgt cost: 800K/MW, OCGT cost 350k/MW, biomass cost 2m/MW
    "CCGT": {
        "name": "CCGT", "gen_cost": 0.1, "curtail_cost": 48.04, "carbon_emission": 0,
        "capacity_limit": 28000, "alter_limit": 14000, "startup_cost": 50,
        "carbon_intensity": 394, "capital_cost": 44800000000, "carbon_price": 15.76,
        "fuel_cost": 39.21, "real_gen_energy": 0, "unit_time_cost": 0
    },
    "OCGT": {
        "name": "OCGT", "gen_cost": 0.1, "curtail_cost": 81.95, "carbon_emission": 0,
        "capacity_limit": 4146, "alter_limit": 4146, "startup_cost": 30,
        "carbon_intensity": 651, "capital_cost": 2902200000, "carbon_price": 26.04,
        "fuel_cost": 48.78, "real_gen_energy": 0, "unit_time_cost": 0
    },
    "bio_and_waste": {
        "name": "bio_and_waste", "gen_cost": 0.2, "curtail_cost": 3, "carbon_emission": 0,
        "capacity_limit": 4762, "alter_limit": 1190, "startup_cost": 83,
        "energy_limit": 16000000, "add_energy": 913, "carbon_intensity": 120,
        "capital_cost": 9524000000, "carbon_price": 4.8, "fuel_cost": 80,
        "real_gen_energy": 0, "unit_time_cost": 0
    },
    "Hydro_natural_flow": {
        "name": "Hydro_natural_flow", "gen_cost": 0, "curtail_cost": 0, "carbon_emission": 0,
        "capacity_limit": 2000, "alter_limit": 2000, "energy_limit": 2000,
        "add_energy": 2000, "capital_cost": 200000000000, "real_gen_energy": 0, "unit_time_cost": 0
    },
    "Nuclear": {
        "name": "Nuclear", "gen_cost": 0, "curtail_cost": 91430, "carbon_emission": 0,
        "capacity_limit": 5883, "alter_limit": 500, "startup_cost": 500, "capital_cost": 470640000,
        "unit_time_cost": 0
    },

    # Renewable Generators (Solar) - Updated capital costs using £750,000 per MW
    # Initial VRE capacities are refreshed from REPD Q2 2025 operational projects.
    # Solar capacity_multiplier is MW; wind capacity_multiplier is in 20 MW model units.
    # The 'capacity_limit' for renewables is determined by weather data in the simulation loop.
    # The electrolyzer attached to each renewable generator is defined here.
    "solar_Nottingham": {"name": "solar_Nottingham", "gen_cost": 0.0001, "curtail_cost": 0, "carbon_emission": 0, "capital_cost": 1159.76 * 750000, "real_gen_energy": 0, "unit_time_cost": 0, "electrolyzer_cost": 15000, "energy_efficiency": 0.65, "electrolyzer_limit": 1, "rampup_rate": 0.125, "capacity_multiplier": 1159.76},
    "solar_Ipswich": {"name": "solar_Ipswich", "gen_cost": 0.0001, "curtail_cost": 0, "carbon_emission": 0, "capital_cost": 1748.76 * 750000, "real_gen_energy": 0, "unit_time_cost": 0, "electrolyzer_cost": 15000, "energy_efficiency": 0.65, "electrolyzer_limit": 1, "rampup_rate": 0.125, "capacity_multiplier": 1748.76},
    "solar_London": {"name": "solar_London", "gen_cost": 0.0001, "curtail_cost": 0, "carbon_emission": 0, "capital_cost": 9.02 * 750000, "real_gen_energy": 0, "unit_time_cost": 0, "electrolyzer_cost": 15000, "energy_efficiency": 0.65, "electrolyzer_limit": 1, "rampup_rate": 0.125, "capacity_multiplier": 9.02},
    "solar_Newcastle": {"name": "solar_Newcastle", "gen_cost": 0.0001, "curtail_cost": 0, "carbon_emission": 0, "capital_cost": 60.36 * 750000, "real_gen_energy": 0, "unit_time_cost": 0, "electrolyzer_cost": 15000, "energy_efficiency": 0.65, "electrolyzer_limit": 1, "rampup_rate": 0.125, "capacity_multiplier": 60.36},
    "solar_Manchester": {"name": "solar_Manchester", "gen_cost": 0.0001, "curtail_cost": 0, "carbon_emission": 0, "capital_cost": 223.56 * 750000, "real_gen_energy": 0, "unit_time_cost": 0, "electrolyzer_cost": 15000, "energy_efficiency": 0.65, "electrolyzer_limit": 1, "rampup_rate": 0.125, "capacity_multiplier": 223.56},
    "solar_Edinburgh": {"name": "solar_Edinburgh", "gen_cost": 0.0001, "curtail_cost": 0, "carbon_emission": 0, "capital_cost": 84 * 750000, "real_gen_energy": 0, "unit_time_cost": 0, "electrolyzer_cost": 15000, "energy_efficiency": 0.65, "electrolyzer_limit": 1, "rampup_rate": 0.125, "capacity_multiplier": 84},
    "solar_Portsmouth": {"name": "solar_Portsmouth", "gen_cost": 0.0001, "curtail_cost": 0, "carbon_emission": 0, "capital_cost": 1970.67 * 750000, "real_gen_energy": 0, "unit_time_cost": 0, "electrolyzer_cost": 15000, "energy_efficiency": 0.65, "electrolyzer_limit": 1, "rampup_rate": 0.125, "capacity_multiplier": 1970.67},
    "solar_Bournemouth": {"name": "solar_Bournemouth", "gen_cost": 0.0001, "curtail_cost": 0, "carbon_emission": 0, "capital_cost": 2722.21 * 750000, "real_gen_energy": 0, "unit_time_cost": 0, "electrolyzer_cost": 15000, "energy_efficiency": 0.65, "electrolyzer_limit": 1, "rampup_rate": 0.125, "capacity_multiplier": 2722.21},
    "solar_Cardiff": {"name": "solar_Cardiff", "gen_cost": 0.0001, "curtail_cost": 0, "carbon_emission": 0, "capital_cost": 897.61 * 750000, "real_gen_energy": 0, "unit_time_cost": 0, "electrolyzer_cost": 15000, "energy_efficiency": 0.65, "electrolyzer_limit": 1, "rampup_rate": 0.125, "capacity_multiplier": 897.61},
    "solar_Birmingham": {"name": "solar_Birmingham", "gen_cost": 0.0001, "curtail_cost": 0, "carbon_emission": 0, "capital_cost": 674.61 * 750000, "real_gen_energy": 0, "unit_time_cost": 0, "electrolyzer_cost": 15000, "energy_efficiency": 0.65, "electrolyzer_limit": 1, "rampup_rate": 0.125, "capacity_multiplier": 674.61},
    "solar_Sheffield": {"name": "solar_Sheffield", "gen_cost": 0.0001, "curtail_cost": 0, "carbon_emission": 0, "capital_cost": 307.12 * 750000, "real_gen_energy": 0, "unit_time_cost": 0, "electrolyzer_cost": 15000, "energy_efficiency": 0.65, "electrolyzer_limit": 1, "rampup_rate": 0.125, "capacity_multiplier": 307.12},

    # Renewable Generators (Onshore Wind) - Updated capital costs using £1,220,000 per MW
    "onshore_Nottingham": {"name": "onshore_Nottingham", "gen_cost": 0.0001, "curtail_cost": 0, "carbon_emission": 0, "capital_cost": 19.925 * 1220000, "real_gen_energy": 0, "unit_time_cost": 0, "electrolyzer_cost": 15000, "energy_efficiency": 0.65, "electrolyzer_limit": 1, "rampup_rate": 0.125, "capacity_multiplier": 19.925},
    "onshore_Ipswich": {"name": "onshore_Ipswich", "gen_cost": 0.0001, "curtail_cost": 0, "carbon_emission": 0, "capital_cost": 22.585 * 1220000, "real_gen_energy": 0, "unit_time_cost": 0, "electrolyzer_cost": 15000, "energy_efficiency": 0.65, "electrolyzer_limit": 1, "rampup_rate": 0.125, "capacity_multiplier": 22.585},
    "onshore_London": {"name": "onshore_London", "gen_cost": 0.0001, "curtail_cost": 0, "carbon_emission": 0, "capital_cost": 0.63 * 1220000, "real_gen_energy": 0, "unit_time_cost": 0, "electrolyzer_cost": 15000, "energy_efficiency": 0.65, "electrolyzer_limit": 1, "rampup_rate": 0.125, "capacity_multiplier": 0.63},
    "onshore_Newcastle": {"name": "onshore_Newcastle", "gen_cost": 0.0001, "curtail_cost": 0, "carbon_emission": 0, "capital_cost": 23.6875 * 1220000, "real_gen_energy": 0, "unit_time_cost": 0, "electrolyzer_cost": 15000, "energy_efficiency": 0.65, "electrolyzer_limit": 1, "rampup_rate": 0.125, "capacity_multiplier": 23.6875},
    "onshore_Manchester": {"name": "onshore_Manchester", "gen_cost": 0.0001, "curtail_cost": 0, "carbon_emission": 0, "capital_cost": 23.365 * 1220000, "real_gen_energy": 0, "unit_time_cost": 0, "electrolyzer_cost": 15000, "energy_efficiency": 0.65, "electrolyzer_limit": 1, "rampup_rate": 0.125, "capacity_multiplier": 23.365},
    "onshore_Edinburgh": {"name": "onshore_Edinburgh", "gen_cost": 0.0001, "curtail_cost": 0, "carbon_emission": 0, "capital_cost": 473.045 * 1220000, "real_gen_energy": 0, "unit_time_cost": 0, "electrolyzer_cost": 15000, "energy_efficiency": 0.65, "electrolyzer_limit": 1, "rampup_rate": 0.125, "capacity_multiplier": 473.045},
    "onshore_Portsmouth": {"name": "onshore_Portsmouth", "gen_cost": 0.0001, "curtail_cost": 0, "carbon_emission": 0, "capital_cost": 5.645 * 1220000, "real_gen_energy": 0, "unit_time_cost": 0, "electrolyzer_cost": 15000, "energy_efficiency": 0.65, "electrolyzer_limit": 1, "rampup_rate": 0.125, "capacity_multiplier": 5.645},
    "onshore_Bournemouth": {"name": "onshore_Bournemouth", "gen_cost": 0.0001, "curtail_cost": 0, "carbon_emission": 0, "capital_cost": 14.245 * 1220000, "real_gen_energy": 0, "unit_time_cost": 0, "electrolyzer_cost": 15000, "energy_efficiency": 0.65, "electrolyzer_limit": 1, "rampup_rate": 0.125, "capacity_multiplier": 14.245},
    "onshore_Cardiff": {"name": "onshore_Cardiff", "gen_cost": 0.0001, "curtail_cost": 0, "carbon_emission": 0, "capital_cost": 60.86 * 1220000, "real_gen_energy": 0, "unit_time_cost": 0, "electrolyzer_cost": 15000, "energy_efficiency": 0.65, "electrolyzer_limit": 1, "rampup_rate": 0.125, "capacity_multiplier": 60.86},
    "onshore_Birmingham": {"name": "onshore_Birmingham", "gen_cost": 0.0001, "curtail_cost": 0, "carbon_emission": 0, "capital_cost": 0.42 * 1220000, "real_gen_energy": 0, "unit_time_cost": 0, "electrolyzer_cost": 15000, "energy_efficiency": 0.65, "electrolyzer_limit": 1, "rampup_rate": 0.125, "capacity_multiplier": 0.42},
    "onshore_Sheffield": {"name": "onshore_Sheffield", "gen_cost": 0.0001, "curtail_cost": 0, "carbon_emission": 0, "capital_cost": 32.61 * 1220000, "real_gen_energy": 0, "unit_time_cost": 0, "electrolyzer_cost": 15000, "energy_efficiency": 0.65, "electrolyzer_limit": 1, "rampup_rate": 0.125, "capacity_multiplier": 32.61},

    # Renewable Generators (Offshore Wind) - Updated capital costs using £3,700,000 per MW
    "offshore1": {"name": "offshore1", "gen_cost": 0.0001, "curtail_cost": 0, "carbon_emission": 0, "capital_cost": 16.215 * 3700000, "real_gen_energy": 0, "unit_time_cost": 0, "electrolyzer_cost": 15000, "energy_efficiency": 0.65, "electrolyzer_limit": 1, "rampup_rate": 0.125, "capacity_multiplier": 16.215},
    "offshore2": {"name": "offshore2", "gen_cost": 0.0001, "curtail_cost": 0, "carbon_emission": 0, "capital_cost": 9.18 * 3700000, "real_gen_energy": 0, "unit_time_cost": 0, "electrolyzer_cost": 15000, "energy_efficiency": 0.65, "electrolyzer_limit": 1, "rampup_rate": 0.125, "capacity_multiplier": 9.18},
    "offshore3": {"name": "offshore3", "gen_cost": 0.0001, "curtail_cost": 0, "carbon_emission": 0, "capital_cost": 126.9 * 3700000, "real_gen_energy": 0, "unit_time_cost": 0, "electrolyzer_cost": 15000, "energy_efficiency": 0.65, "electrolyzer_limit": 1, "rampup_rate": 0.125, "capacity_multiplier": 126.9},
    "offshore4": {"name": "offshore4", "gen_cost": 0.0001, "curtail_cost": 0, "carbon_emission": 0, "capital_cost": 0 * 3700000, "real_gen_energy": 0, "unit_time_cost": 0, "electrolyzer_cost": 15000, "energy_efficiency": 0.65, "electrolyzer_limit": 1, "rampup_rate": 0.125, "capacity_multiplier": 0},
    "offshore5": {"name": "offshore5", "gen_cost": 0.0001, "curtail_cost": 0, "carbon_emission": 0, "capital_cost": 16.2 * 3700000, "real_gen_energy": 0, "unit_time_cost": 0, "electrolyzer_cost": 15000, "energy_efficiency": 0.65, "electrolyzer_limit": 1, "rampup_rate": 0.125, "capacity_multiplier": 16.2},
    "offshore6": {"name": "offshore6", "gen_cost": 0.0001, "curtail_cost": 0, "carbon_emission": 0, "capital_cost": 42.85 * 3700000, "real_gen_energy": 0, "unit_time_cost": 0, "electrolyzer_cost": 15000, "energy_efficiency": 0.65, "electrolyzer_limit": 1, "rampup_rate": 0.125, "capacity_multiplier": 42.85},
    "offshore7": {"name": "offshore7", "gen_cost": 0.0001, "curtail_cost": 0, "carbon_emission": 0, "capital_cost": 46.5 * 3700000, "real_gen_energy": 0, "unit_time_cost": 0, "electrolyzer_cost": 15000, "energy_efficiency": 0.65, "electrolyzer_limit": 1, "rampup_rate": 0.125, "capacity_multiplier": 46.5},
    "offshore8": {"name": "offshore8", "gen_cost": 0.0001, "curtail_cost": 0, "carbon_emission": 0, "capital_cost": 62.385 * 3700000, "real_gen_energy": 0, "unit_time_cost": 0, "electrolyzer_cost": 15000, "energy_efficiency": 0.65, "electrolyzer_limit": 1, "rampup_rate": 0.125, "capacity_multiplier": 62.385},
    "offshore9": {"name": "offshore9", "gen_cost": 0.0001, "curtail_cost": 0, "carbon_emission": 0, "capital_cost": 31.05 * 3700000, "real_gen_energy": 0, "unit_time_cost": 0, "electrolyzer_cost": 15000, "energy_efficiency": 0.65, "electrolyzer_limit": 1, "rampup_rate": 0.125, "capacity_multiplier": 31.05},
    "offshore10": {"name": "offshore10", "gen_cost": 0.0001, "curtail_cost": 0, "carbon_emission": 0, "capital_cost": 23.95 * 3700000, "real_gen_energy": 0, "unit_time_cost": 0, "electrolyzer_cost": 15000, "energy_efficiency": 0.65, "electrolyzer_limit": 1, "rampup_rate": 0.125, "capacity_multiplier": 23.95},
    "offshore11": {"name": "offshore11", "gen_cost": 0.0001, "curtail_cost": 0, "carbon_emission": 0, "capital_cost": 20 * 3700000, "real_gen_energy": 0, "unit_time_cost": 0, "electrolyzer_cost": 15000, "energy_efficiency": 0.65, "electrolyzer_limit": 1, "rampup_rate": 0.125, "capacity_multiplier": 20},
    "offshore12": {"name": "offshore12", "gen_cost": 0.0001, "curtail_cost": 0, "carbon_emission": 0, "capital_cost": 29.4 * 3700000, "real_gen_energy": 0, "unit_time_cost": 0, "electrolyzer_cost": 15000, "energy_efficiency": 0.65, "electrolyzer_limit": 1, "rampup_rate": 0.125, "capacity_multiplier": 29.4},
    "offshore13": {"name": "offshore13", "gen_cost": 0.0001, "curtail_cost": 0, "carbon_emission": 0, "capital_cost": 38.7 * 3700000, "real_gen_energy": 0, "unit_time_cost": 0, "electrolyzer_cost": 15000, "energy_efficiency": 0.65, "electrolyzer_limit": 1, "rampup_rate": 0.125, "capacity_multiplier": 38.7},
    "offshore14": {"name": "offshore14", "gen_cost": 0.0001, "curtail_cost": 0, "carbon_emission": 0, "capital_cost": 0 * 3700000, "real_gen_energy": 0, "unit_time_cost": 0, "electrolyzer_cost": 15000, "energy_efficiency": 0.65, "electrolyzer_limit": 1, "rampup_rate": 0.125, "capacity_multiplier": 0},
    "offshore15": {"name": "offshore15", "gen_cost": 0.0001, "curtail_cost": 0, "carbon_emission": 0, "capital_cost": 63.49 * 3700000, "real_gen_energy": 0, "unit_time_cost": 0, "electrolyzer_cost": 15000, "energy_efficiency": 0.65, "electrolyzer_limit": 1, "rampup_rate": 0.125, "capacity_multiplier": 63.49},
    "offshore16": {"name": "offshore16", "gen_cost": 0.0001, "curtail_cost": 0, "carbon_emission": 0, "capital_cost": 42.13 * 3700000, "real_gen_energy": 0, "unit_time_cost": 0, "electrolyzer_cost": 15000, "energy_efficiency": 0.65, "electrolyzer_limit": 1, "rampup_rate": 0.125, "capacity_multiplier": 42.13},
    "offshore17": {"name": "offshore17", "gen_cost": 0.0001, "curtail_cost": 0, "carbon_emission": 0, "capital_cost": 49.5 * 3700000, "real_gen_energy": 0, "unit_time_cost": 0, "electrolyzer_cost": 15000, "energy_efficiency": 0.65, "electrolyzer_limit": 1, "rampup_rate": 0.125, "capacity_multiplier": 49.5},
    "offshore18": {"name": "offshore18", "gen_cost": 0.0001, "curtail_cost": 0, "carbon_emission": 0, "capital_cost": 53.7 * 3700000, "real_gen_energy": 0, "unit_time_cost": 0, "electrolyzer_cost": 15000, "energy_efficiency": 0.65, "electrolyzer_limit": 1, "rampup_rate": 0.125, "capacity_multiplier": 53.7},
    "offshore19": {"name": "offshore19", "gen_cost": 0.0001, "curtail_cost": 0, "carbon_emission": 0, "capital_cost": 0 * 3700000, "real_gen_energy": 0, "unit_time_cost": 0, "electrolyzer_cost": 15000, "energy_efficiency": 0.65, "electrolyzer_limit": 1, "rampup_rate": 0.125, "capacity_multiplier": 0},
    "offshore20": {"name": "offshore20", "gen_cost": 0.0001, "curtail_cost": 0, "carbon_emission": 0, "capital_cost": 3.1 * 3700000, "real_gen_energy": 0, "unit_time_cost": 0, "electrolyzer_cost": 15000, "energy_efficiency": 0.65, "electrolyzer_limit": 1, "rampup_rate": 0.125, "capacity_multiplier": 3.1},
    "offshore21": {"name": "offshore21", "gen_cost": 0.0001, "curtail_cost": 0, "carbon_emission": 0, "capital_cost": 58.7 * 3700000, "real_gen_energy": 0, "unit_time_cost": 0, "electrolyzer_cost": 15000, "energy_efficiency": 0.65, "electrolyzer_limit": 1, "rampup_rate": 0.125, "capacity_multiplier": 58.7},
}

# -----------------------------------------------------------------------------
# External Investment Methodology Parameters
# -----------------------------------------------------------------------------
investment_methodology_external = {
    "preferred_rates": {
        # DESNZ/CEPA 2025 lead whole-life hurdle rates, pre-tax real CPI.
        # These are investment thresholds, not extra returns after annualized capex.
        "CCGT": 0.089,
        "OCGT": 0.089,
        "bio_and_waste": 0.089,
        "solar": 0.076,
        "onshore": 0.076,
        "offshore": 0.089,
        "1c_battery": 0.0825,
        "0.5c_battery": 0.165,
        "0.25c_battery": 0.0825,
        "hydrogen_battery": 0.01375,
        "electrolyzer": 0.101
    },
    "regulated_capacity_targets": {
        "CCGT": 1.01,           # 10% increase
        "OCGT": 1.01,           # 10% increase
        "bio_and_waste": 1.01,  # 5% increase
        "solar": 35440,         # Fixed capacity target
        "onshore": 15330,       # Fixed capacity target
        "offshore": 15330,      # Fixed capacity target
        "1c_battery": 10000,        # Fixed capacity target
        "0.5c_battery": 10000,        # Fixed capacity target
        "0.25c_battery": 10000,
        "hydrogen_battery": 10000,
        "electrolyzer": 1 # 10% increase
    }
}

# -----------------------------------------------------------------------------
# Storage (Battery) Parameters
# -----------------------------------------------------------------------------
batteries = {
    "pumpedhydro_battery": {
        "name": "pumpedhydro_battery", "pool_limit": 8000, "per_pool_limit": 2000,
        "storage_fee": 0, "per_storage_fee": 1.1008, "n_1": 0.87, "n_2": 0.87,
        "carbon_emission": 40, "capital_cost": 720000000, "battery_type": "pumped_hydro"
    },
    "1c_battery": {
        "name": "thermal_battery", "pool_limit": 100, "per_pool_limit": 50,
        "storage_fee": 0, "per_storage_fee": 1.0558, "n_1": 0.81, "n_2": 0.81,
        "carbon_emission": 50, "capital_cost": 33000000, "battery_type": "1c"
    },
    "0.25c_battery": {
        "name": "air_battery", "pool_limit": 400, "per_pool_limit": 200,
        "storage_fee": 0, "per_storage_fee": 0.7369, "n_1": 0.81, "n_2": 0.81,
        "carbon_emission": 50, "capital_cost": 45000000, "battery_type": "0.25c"
    },
    "0.5c_battery": {
        "name": "li_battery", "pool_limit": 3288, "per_pool_limit": 1644,
        "storage_fee": 135.26, "per_storage_fee": 0.1736, "n_1": 0.98, "n_2": 0.98,
        "carbon_emission": 50, "capital_cost": 597180000, "battery_type": "0.5c"
    },
    "hydrogen_battery": {
        "name": "hydrogen_battery", "pool_limit": 0, "per_pool_limit": 0,
        "storage_fee": 884.4, "per_storage_fee": 0.0055, "n_1": 0.57, "n_2": 0.57,
        "carbon_emission": 50, "capital_cost": 290000, "battery_type": "hydrogen"
    }
}

# -----------------------------------------------------------------------------
# Interconnection Parameters
# -----------------------------------------------------------------------------
connections = {
    "Interconnect_France": {"name": "Interconnect_France", "capital_cost": 394400000, "carbon_emission": 0, "carbon_intensity": 53},
    "Interconnect_Netherland": {"name": "Interconnect_Netherland", "capital_cost": 197200000, "carbon_emission": 0, "carbon_intensity": 474},
    "Interconnect_Ireland": {"name": "Interconnect_Ireland", "capital_cost": 147900000, "carbon_emission": 0, "carbon_intensity": 458},
    "Interconnect_Norway": {"name": "Interconnect_Norway", "capital_cost": 276080000, "carbon_emission": 0, "carbon_intensity": 100},
    "Interconnect_Beligum": {"name": "Interconnect_Beligum", "capital_cost": 197200000, "carbon_emission": 0, "carbon_intensity": 179},
}

# -----------------------------------------------------------------------------
# Public Electrolyzer Parameters
# -----------------------------------------------------------------------------
electrolyzer = {
    "name": "electrolyzer", "capital_cost": 1500000, "operational_cost": 30000,
    "energy_efficiency": 0.65, "cycle_life": 50000, "capacity_limit": 10,
    "rampup_rate": 0.125, "body_emission": 0
}

# -----------------------------------------------------------------------------
# Geographical Locations for Weather Data
# -----------------------------------------------------------------------------
locations = {
    "Nottingham": {"lat": 53.0, "lon": -1.2},
    "Ipswich": {"lat": 52.0567, "lon": 1.1482},
    "London": {"lat": 51.5072, "lon": -0.1276},
    "Newcastle": {"lat": 54.9783, "lon": -1.6178},
    "Manchester": {"lat": 53.4808, "lon": -2.2426},
    "Edinburgh": {"lat": 55.9533, "lon": -3.1883},
    "Portsmouth": {"lat": 50.8198, "lon": -1.0880},
    "Bournemouth": {"lat": 50.7220, "lon": -1.8667},
    "Cardiff": {"lat": 51.4837, "lon": -3.1681},
    "Birmingham": {"lat": 52.4862, "lon": -1.8904},
    "Sheffield": {"lat": 53.3811, "lon": -1.4701},
    # Offshore locations
    "offshore1": {"lat": 51.749722, "lon": 1.209167},
    "offshore2": {"lat": 54.043889, "lon": -3.521944},
    "offshore3": {"lat": 53.920000, "lon": 1.560000},
    "offshore4": {"lat": 54.043889, "lon": -3.521944}, # Note: Same as offshore2
    "offshore5": {"lat": 54.060833, "lon": -3.432500},
    "offshore6": {"lat": 51.880000, "lon": 1.940000},
    "offshore7": {"lat": 51.643889, "lon": 1.553611},
    "offshore8": {"lat": 53.153333, "lon": 0.520278},
    "offshore9": {"lat": 53.173056, "lon": 0.640833},
    "offshore10": {"lat": 53.980000, "lon": -3.460000},
    "offshore11": {"lat": 50.664700, "lon": -0.278900},
    "offshore12": {"lat": 58.133333, "lon": -3.066667},
    "offshore13": {"lat": 52.152500, "lon": 2.446389},
    "offshore14": {"lat": 53.885000, "lon": 1.791000},
    "offshore15": {"lat": 56.449722, "lon": -1.991389},
    "offshore16": {"lat": 54.044000, "lon": -3.522000},
    "offshore17": {"lat": 58.167080, "lon": -2.698520},
    "offshore18": {"lat": 53.483333, "lon": -3.166667},
    "offshore19": {"lat": 53.643889, "lon": 0.293056},
    "offshore20": {"lat": 53.810000, "lon": 0.150000},
    "offshore21": {"lat": 53.164167, "lon": 0.723333},
}

# -----------------------------------------------------------------------------
# Development Stage Timeline Parameters (in months) - Based on REPD Analysis
# -----------------------------------------------------------------------------
# Development timelines broken down by stage and project status
development_stage_timelines = {
    "solar": {
        "planning_consenting_mean": 8.1,
        "planning_consenting_median": 6.9,
        "pre_construction_mean": 18.0,
        "pre_construction_median": 14.8,
        "construction_mean": 6.4,
        "construction_median": 4.9,
        "total_mean": 32.5,
        "total_median": 27.8
    },
    "onshore": {
        "planning_consenting_mean": 24.1,
        "planning_consenting_median": 19.8,
        "pre_construction_mean": 30.4,
        "pre_construction_median": 24.3,
        "construction_mean": 18.3,
        "construction_median": 15.0,
        "total_mean": 72.8,
        "total_median": 62.5
    },
    "offshore": {
        "planning_consenting_mean": 36.3,
        "planning_consenting_median": 30.4,
        "pre_construction_mean": 48.4,
        "pre_construction_median": 41.6,
        "construction_mean": 36.0,
        "construction_median": 32.2,
        "total_mean": 120.7,
        "total_median": 110.1
    },
    "battery": {
        "planning_consenting_mean": 7.4,
        "planning_consenting_median": 6.2,
        "pre_construction_mean": 15.1,
        "pre_construction_median": 13.0,
        "construction_mean": 11.9,
        "construction_median": 10.1,
        "total_mean": 34.4,
        "total_median": 31.3
    }
}

# Map REPD development statuses to development stages and timelines (median months).
repd_status_to_timeline = {
    "Application Submitted": {
        "stage": "planning_consenting",
        "apply_success_rate": True,
        "timeline_type": "total_median",
    },
    "Appeal Lodged": {
        "stage": "planning_consenting",
        "apply_success_rate": True,
        "timeline_type": "total_median",
    },
    "Revised": {
        "stage": "planning_consenting",
        "apply_success_rate": True,
        "timeline_type": "total_median",
    },
    "Planning Permission Granted": {
        "stage": "pre_construction",
        "apply_success_rate": False,
        "timeline_type": "pre_construction_median",
    },
    "Awaiting Construction": {
        "stage": "construction",
        "apply_success_rate": False,
        "timeline_type": "construction_median",
    },
    "Under Construction": {
        "stage": "construction",
        "apply_success_rate": False,
        "timeline_type": "construction_median",
    },
}

# -----------------------------------------------------------------------------
# Legacy Development Timeline Parameters (for backward compatibility)
# -----------------------------------------------------------------------------
development_timelines = {
    "onshore": 62.5,
    "offshore": 110.1,
    "solar": 27.8,
    "gas": 62.5,
    "1c_battery": 31.3,
    "0.5c_battery": 31.3,
    "0.25c_battery": 31.3,
    "battery": 31.3,
}

construction_timelines = {
    "onshore": 18.3,
    "offshore": 36.0,
    "solar": 6.4,
    "gas": 18.3,
    "1c_battery": 11.9,
    "0.5c_battery": 11.9,
    "0.25c_battery": 11.9
}

# -----------------------------------------------------------------------------
# Capital Cost Parameters (£/MW for new builds)
# -----------------------------------------------------------------------------
_BASELINE_CAPITAL_COSTS_PER_MW = {
    "solar": 750000,
    "onshore": 1220000,
    "offshore": 2700000,
    "gas": 2400000,
    "CCGT": 2400000,
    "OCGT": 2400000,
    "bio_and_waste": 1500000,  # Estimated
    "1c_battery": 330000,
    "0.5c_battery": 350000,
    "0.25c_battery": 415000,
    "hydrogen_battery": 600000,
    "battery": 350000,  # 通用储能（含 pumpedhydro_battery）单位成本 £/MW，用于 external 项目写入投资成本
}

# DESNZ / Arup LCOE 2024 medium total capex (2023 real prices, £/kW -> £/MW).
# Sources:
# - Onshore + solar: GOV.UK onshore-wind-and-solar-pv-cost-electricity-report-update-2024
# - Offshore: DESNZ offshore-wind LCOE report update 2024
ARUP_MEDIUM_TOTAL_CAPEX_PER_MW = {
    "solar": 659_000,      # £659/kWp total capex
    "onshore": 1_588_000,  # £1,588/kW total capex
    "offshore": 3_976_000, # £3,976/kW total capex
}

_ARUP_PROFILE_KEYS = {"arup", "arup_medium", "arup-medium", "arup_cost"}


def apply_capital_cost_profile(profile: str | None = None) -> str:
    """Switch VRE new-build capex; set CAPITAL_COST_PROFILE=arup_medium to enable."""
    global capital_costs_per_mw
    key = (profile or os.getenv("CAPITAL_COST_PROFILE", "")).strip().lower()
    if key in _ARUP_PROFILE_KEYS:
        capital_costs_per_mw = {**_BASELINE_CAPITAL_COSTS_PER_MW, **ARUP_MEDIUM_TOTAL_CAPEX_PER_MW}
        return "arup_medium"
    capital_costs_per_mw = dict(_BASELINE_CAPITAL_COSTS_PER_MW)
    return "baseline"


capital_costs_per_mw = dict(_BASELINE_CAPITAL_COSTS_PER_MW)
ACTIVE_CAPITAL_COST_PROFILE = apply_capital_cost_profile()

# -----------------------------------------------------------------------------
# REPD Project Filtering Parameters
# -----------------------------------------------------------------------------
repd_filtering = {
    "apply_zombie_filter": True,  # Whether to filter out zombie projects
    "include_uncertain_projects": False,  # Whether to include uncertain projects
    "uncertainty_timeline_penalty": 1.5,  # Multiplier for uncertain project timelines
    "minimum_project_size_mw": 1.0,  # Minimum project size to include
    "max_completion_year": 2040,  # Don't include projects completing after this year
    # Status-stagnant zombie: no REPD status-progress milestone after this year (default 2015).
    "zombie_status_stale_year": 2015,
    "zombie_snapshot_year": 2025,
    
    # Project confidence scoring
    "confidence_weights": {
        "Under Construction": 0.95,
        "Awaiting Construction": 0.85,
        "Planning Permission Granted": 0.80,
        "Application Submitted": 0.40,
        "Appeal Lodged": 0.30,
        "Revised": 0.35
    }
}