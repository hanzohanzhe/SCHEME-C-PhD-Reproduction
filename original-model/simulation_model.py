# This is a sample Python script.

# Press Shift+F10 to execute it or replace it with your code.
# Press Double Shift to search everywhere for classes, files, tool windows, actions, and settings.
import gc
import xarray as xr
try:
    import cartopy.crs as ccrs
    import cartopy.feature as cf
except ModuleNotFoundError:
    ccrs = None
    cf = None
try:
    import cfgrib
    import ecmwflibs
except ModuleNotFoundError:
    cfgrib = None
    ecmwflibs = None
import pandas
import matplotlib.pyplot as plt
import math
import numpy as np
import pandas as pd
import random
import seaborn as sns
import sys
import json
import os
try:
    from netCDF4 import Dataset
except ModuleNotFoundError:
    Dataset = None
import csv
import config  # Import the configuration file

_WEATHER_LIMIT_CACHE = None
DEBUG_MARKET_STDOUT = os.getenv("SIM_DEBUG_MARKET", "0") == "1"


def physical_period_hours() -> float:
    """Hours represented by one dispatch period; default model periods are half-hours."""
    try:
        return float(os.getenv("PHYSICAL_PERIOD_HOURS", "0.5"))
    except ValueError:
        return 0.5

#read wind

class IterLimit(object):
    def __init__(self, wind_limit):
        self.limit = wind_limit
        self.idx = 0
        self.length = len(self.limit)
        self.repeat_count = 0

    def __iter__(self):
        return self

    def __next__(self):
        if self.idx < self.length:
            LIM = self.limit[self.idx]
            if self.repeat_count < 1:
                self.repeat_count += 1
            else:
                self.repeat_count = 0
                self.idx += 1
            return LIM
        else:
            # 重置索引，循环使用数据
            self.idx = 0
            self.repeat_count = 0
            LIM = self.limit[self.idx]
            self.repeat_count += 1
            return LIM

class IterLimit_new(object):
    def __init__(self, wind_limit):
        self.limit = wind_limit
        self.idx = 0
        self.length = len(self.limit)
        self.repeat_count = 0

    def __ge__(self, other):
        pass

    def __abs__(self):
        return abs(self.limit)

    def __iter__(self):
        return self

    def __next__(self):
        if self.idx < self.length:
            LIM = self.limit[self.idx]
            if self.repeat_count < 1:
                self.repeat_count += 1
            else:
                self.repeat_count = 0
                self.idx += 1
            return LIM
        else:
            # 重置索引，循环使用数据
            self.idx = 0
            self.repeat_count = 0
            LIM = self.limit[self.idx]
            self.repeat_count += 1
            return LIM

#wind generation function
WIND_UNIT_MW = 20


def _wind_power_curve(speed, cut_in, rated, cut_out, unit_mw=WIND_UNIT_MW):
    """Return output for one model wind unit from wind speed in m/s."""
    if hasattr(speed, '__len__') and len(speed) > 0:
        speed = speed[0]

    if speed < cut_in or speed > cut_out:
        return 0
    if speed >= rated:
        return unit_mw

    # Cubic interpolation between cut-in and rated speed.
    normalized = (speed**3 - cut_in**3) / (rated**3 - cut_in**3)
    return max(0, min(unit_mw, normalized * unit_mw))


def piecewise_limit1(limit):
    return _wind_power_curve(limit, cut_in=3, rated=10.5, cut_out=30)


def piecewise_limit2(limit):
    return _wind_power_curve(limit, cut_in=3, rated=10.5, cut_out=30)


def piecewise_limit3(limit):
    return _wind_power_curve(limit, cut_in=3, rated=10.5, cut_out=30)


def piecewise_limit4(limit):
    return _wind_power_curve(limit, cut_in=3, rated=10.5, cut_out=30)


def piecewise_limit5(limit):
    return _wind_power_curve(limit, cut_in=3, rated=9.7, cut_out=25)


def piecewise_limit(limit):
    # 如果limit是数组，取第一个值
    if hasattr(limit, '__len__') and len(limit) > 0:
        limit = limit[0]
    
    if limit <= 3600:
        result = 0
    elif limit > 3600 and limit <= 36000000:
        result = limit
    else:
        result = 0
    return result


# Define Generator classes
class Generator:
    def __init__(self, gen_cost, curtail_cost, carbon_emission):
        self.gen_cost = gen_cost
        self.curtail_cost = curtail_cost
        self.carbon_emission = carbon_emission


class Battery:
    def __init__(self, name, pool_limit, per_pool_limit, storage_fee, per_storage_fee, n_1, n_2, carbon_emission, capital_cost=0, battery_type=None):
        self.name = name
        self.pool_limit = pool_limit
        self.per_pool_limit = per_pool_limit
        self.storage_fee = storage_fee
        self.per_storage_fee = per_storage_fee
        self.n_1 = n_1
        self.n_2 = n_2
        self.stored_energy = {}
        self.real_gen_energy = 0
        self.carbon_emission = carbon_emission
        self.capital_cost = capital_cost
        self.run_time = 0
        # 添加电池类型属性，用于确定衰减率
        self.battery_type = battery_type

        # storage function

    def set_stored_energy_var(self, key, value):
        if key in self.stored_energy:
            self.stored_energy[key] += value
        else:
            self.stored_energy[key] = value
        # discharge from storage

    def clr_stored_energy_var(self, key, value):
        if key in self.stored_energy:
            self.stored_energy[key] -= value
            # Remove key if energy becomes negligible or negative
            if self.stored_energy[key] < 0.001:
                del self.stored_energy[key]

    def set_run_time(self):
        self.run_time +=0.5
    
    def cleanup_negligible_energy(self, threshold=0.001):
        """Remove entries with negligible energy to save memory"""
        keys_to_remove = [k for k, v in self.stored_energy.items() if v < threshold]
        for k in keys_to_remove:
            del self.stored_energy[k]
        return len(keys_to_remove)

    def __str__(self):
        return f"{self.name} "
#generators
class GasGenerator(Generator):
    def __init__(self, name, gen_cost, curtail_cost, carbon_emission, capacity_limit, alter_limit, startup_cost,
                 carbon_intensity, capital_cost, carbon_price, fuel_cost,real_gen_energy, unit_time_cost):
         super().__init__(gen_cost, curtail_cost, carbon_emission)
         self.name = name
         self.gen_cost = gen_cost + carbon_price + fuel_cost + unit_time_cost
         self.capacity_limit = capacity_limit
         self.alter_limit = alter_limit
         self.startup_cost = startup_cost
         self.real_gen_energy = real_gen_energy
         self.carbon_intensity = carbon_intensity
         self.capital_cost = capital_cost
         self.carbon_price = carbon_price
         self.fuel_cost = fuel_cost
         self.if_curtail = False
         self.run_time = 0

    def set_real_gen_energy(self, value):
        self.real_gen_energy = value

    def set_if_curtail(self):
        self.if_curtail = True

    def clr_if_curtail(self):
        self.if_curtail = False

    def set_run_time(self):
        self.run_time +=0.5

    def __str__(self):
        return f"{self.name} "


class ExpensiverenewableGenerator(Generator):
    def __init__(self, name, gen_cost, curtail_cost, carbon_emission, capital_cost,real_gen_energy,unit_time_cost,
                 electrolyzer_cost, energy_efficiency, electrolyzer_limit, rampup_rate, capacity_multiplier=0):
        super().__init__(gen_cost, curtail_cost, carbon_emission)
        self.gen_cost = gen_cost + unit_time_cost
        self.name = name
        self.capacity_limit = 0 # This will be updated in the loop
        self.if_curtail = False
        # storage for renewables
        self.stored_energy = {}
        self.real_gen_energy = real_gen_energy
        self.capital_cost = capital_cost
        self.run_time = 0
        self.electrolyzer_cost = electrolyzer_cost
        self.energy_efficiency = energy_efficiency
        self.electrolyzer_limit = electrolyzer_limit
        self.rampup_rate = rampup_rate
        self.real_energy = 0
        self.capacity_multiplier = capacity_multiplier # Add the new attribute

    def set_real_energy(self, value):#这个是真实的电解能量
            self.real_energy = value

    def set_real_gen_energy(self, value):
        self.real_gen_energy = value

    # storage function
    def set_stored_energy_var(self, key, value):
        self.stored_energy.update({key: value})

    # charge from curtailment
    def clr_stored_energy_var(self, key, value):
        self.stored_energy[key] -= value

    def set_if_curtail(self):
        self.if_curtail = True

    def clr_if_curtail(self):
        self.if_curtail = False

    def set_run_time(self):
        self.run_time +=0.5

    def __str__(self):
        return f"{self.name} "

#biomass generator
class BiomassGenerator(Generator):
    def __init__(self, name, gen_cost, curtail_cost, carbon_emission, capacity_limit, alter_limit, startup_cost,
                 energy_limit, add_energy, carbon_intensity, capital_cost, carbon_price, fuel_cost,
                 real_gen_energy, unit_time_cost):
        super().__init__(gen_cost, curtail_cost, carbon_emission)
        self.name = name
        self.gen_cost = gen_cost + carbon_price + fuel_cost + unit_time_cost
        self.capacity_limit = capacity_limit
        self.energy_limit = energy_limit
        self.alter_limit = alter_limit
        self.startup_cost = startup_cost
        self.add_energy = add_energy
        self.carbon_intensity = carbon_intensity
        self.real_gen_energy = real_gen_energy
        self.have_gen_energy = real_gen_energy
        self.capital_cost = capital_cost
        self.carbon_price = carbon_price
        self.fuel_cost = fuel_cost
        self.run_time = 0

    def set_real_gen_energy(self, value):
        self.real_gen_energy = value

    def add_energy_limit(self, add_energy):
        self.energy_limit += add_energy

    def add_have_gen_energy(self, value):
        self.have_gen_energy += value

    def dec_have_gen_energy(self, value):
        self.have_gen_energy -= value

    def set_run_time(self):
        self.run_time +=0.5

    def __str__(self):
        return f"{self.name} "


class NuclearGenerator(Generator):
    def __init__(self, name, gen_cost, curtail_cost, carbon_emission, capacity_limit, alter_limit, startup_cost,
                 capital_cost, unit_time_cost):
        super().__init__(gen_cost, curtail_cost, carbon_emission)
        self.gen_cost = gen_cost + unit_time_cost
        self.name = name
        self.capacity_limit = capacity_limit
        self.alter_limit = alter_limit
        self.startup_cost = startup_cost
        self.real_gen_energy = capacity_limit
        self.capital_cost = capital_cost
        self.run_time = 0

    def set_real_gen_energy(self, value):
        self.real_gen_energy = value

    def set_run_time(self):
        self.run_time +=0.5

    def __str__(self):
        return f"{self.name} "


class WaterGenerator(Generator):
    def __init__(self, name, gen_cost, curtail_cost, carbon_emission, capacity_limit, alter_limit, energy_limit,
                 add_energy, capital_cost,real_gen_energy, unit_time_cost):
        super().__init__(gen_cost, curtail_cost, carbon_emission)
        self.gen_cost = gen_cost + unit_time_cost
        self.name = name
        self.capacity_limit = capacity_limit
        self.energy_limit = energy_limit
        self.alter_limit = alter_limit
        self.add_energy = add_energy
        self.real_gen_energy = real_gen_energy
        self.have_gen_energy = real_gen_energy
        self.capital_cost = capital_cost
        self.run_time = 0

    def set_real_gen_energy(self, value):
        self.real_gen_energy = value

    def add_energy_limit(self, add_energy):
        self.energy_limit += add_energy

    def add_have_gen_energy(self, value):
        self.have_gen_energy += value

    def dec_have_gen_energy(self, value):
        self.have_gen_energy -= value

    def set_run_time(self):
        self.run_time +=0.5

    def __str__(self):
        return f"{self.name} "


#interconnections
class Connection:
    def __init__(self, name, capital_cost, carbon_emission, carbon_intensity):
        self.name = name
        self.transfer_constraint = 0
        self.external_price = 0
        self.capital_cost = capital_cost
        self.carbon_emission = carbon_emission
        self.carbon_intensity = carbon_intensity
        self.sold_energy = 0

    def __str__(self):
        return (f"Connection Name: {self.name}, Transfer Constraint: {self.transfer_constraint}, "
                f"External Price: {self.external_price}, Capital Cost: {self.capital_cost}, "
                f"Carbon Emission: {self.carbon_emission}, Carbon Intensity: {self.carbon_intensity}")


class Electrolyzer:
    def __init__(self, name, capital_cost, operational_cost, energy_efficiency, cycle_life, capacity_limit, rampup_rate, body_emission):
        self.capital_cost = capital_cost
        self.operational_cost = operational_cost
        self.energy_efficiency = energy_efficiency
        self.cycle_life = cycle_life
        self.capacity_limit = capacity_limit
        self.rampup_rate = rampup_rate
        self.body_emission = body_emission
        self.real_energy = 0


    def set_real_energy(self, value):
        self.real_energy = value

    def __str__(self):
        return f"{self.name} "

#storage function for storage agents
def bar_to_line1(storage_pools_composition, batterys):
    result_dict = {element: [] for element in batterys}
    #print(result_dict)
    for item in storage_pools_composition:
        keymap = []
        for element in item:
            key = element[0]
            value = element[1]
            keymap.append(key)
            if key in result_dict:
                result_dict[key].append(value)
            else:
                pass
        for key in result_dict.keys():
            if key not in keymap:
                result_dict[key].append(0)
    return result_dict


def bar_to_line2(storage_pools_composition, batterys, generators):
    result_dict = {element: [] for element in (batterys + generators)}
    #print(result_dict)
    for item in storage_pools_composition:
        keymap = []
        for element in item:
            key = element[0]
            value = element[1]
            keymap.append(key)
            if key in result_dict:
                # 如果键已存在于字典中，将值叠加到现有值
                result_dict[key].append(value)
            else:
                pass
        for key in result_dict.keys():
            if key not in keymap:
                result_dict[key].append(0)
    sum_list_offshore = [0] * len(next(iter(result_dict.values())))
    sum_list_onshore = [0] * len(next(iter(result_dict.values())))
    sum_list_solar = [0] * len(next(iter(result_dict.values())))
    for key, value_list in result_dict.items():
        if key.name.startswith('offshore') and key.name != 'offshore':
            for i, value in enumerate(value_list):
                sum_list_offshore[i] += value
        elif key.name.startswith('onshore') and key.name != 'onshore':
            for i, value in enumerate(value_list):
                sum_list_onshore[i] += value
        elif key.name.startswith('solar') and key.name != 'solar':
            for i, value in enumerate(value_list):
                sum_list_solar[i] += value
        elif key.name.startswith('planoff') and key.name != 'planoff':
            for i, value in enumerate(value_list):
                sum_list_offshore[i] += value
    keys_to_delete = [key for key in result_dict if key.name.startswith('offshore') and key.name != 'offshore']
    for key in keys_to_delete:
        del result_dict[key]
    keys_to_delete = [key for key in result_dict if key.name.startswith('onshore') and key.name != 'onshore']
    for key in keys_to_delete:
        del result_dict[key]
    keys_to_delete = [key for key in result_dict if key.name.startswith('solar') and key.name != 'solar']
    for key in keys_to_delete:
        del result_dict[key]
    keys_to_delete = [key for key in result_dict if key.name.startswith('planoff') and key.name != 'planoff']
    for key in keys_to_delete:
        del result_dict[key]
    result_dict['offshore'] = sum_list_offshore
    result_dict['onshore'] = sum_list_onshore
    result_dict['solar'] = sum_list_solar
    return result_dict


# To run for many generators
def cycle_limit(lst):
    index = 0
    while True:
        yield lst[index]
        index = (index + 1) % len(lst)



def cycle_limit1(lst):
    index = 0
    while True:
        yield lst[index]
        index = (index + 1) % len(lst)


# unfinished, attempt to level the start-up cost into agent decision
def acm_cost(generators, forecast_demand):
    curtail_bids = [(gen, gen.gen_cost, gen.capacity_limit) for gen in generators if gen.if_curtail == True]
    curtail_bids.sort(key=lambda x: x[2])
    length = len(curtail_bids)
    if length == 0:
        pass
    else:
        pass


# self-discharge for storage agents
def decay_func(stored_energy, battery_type=None):
    """
    储能衰减函数
    Args:
        stored_energy: 储能字典
        battery_type: 电池类型 ('1c', '0.5c', '0.25c', 'pumped_hydro', 'hydrogen')
    """
    # 根据电池类型确定衰减率
    if battery_type in ['1c', '0.5c', '0.25c']:
        decay_rate = 0.000021  # 0.0021% per period (half hour) for C-rate batteries
    elif battery_type == 'pumped_hydro':
        decay_rate = 0.000001  # 0.0001% per period (half hour) for pumped hydro (very low)
    elif battery_type == 'hydrogen':
        decay_rate = 0.000005  # 0.0005% per period (half hour) for hydrogen storage (low)
    else:
        decay_rate = 0.000021  # 默认衰减率
    
    for key, value in stored_energy.items():
        stored_energy[key] *= (1 - decay_rate)


def subtract_elements(list1, list2):
    result_list = []
    for item1 in list1:
        for item2 in list2:
            if item1[0] == item2[0]:
                result_list.append([item1[0],item1[1] - item2[1]])
    return result_list

def acm_energy(ds, latitude, longitude):
    if hasattr(ds, 'variables') and ('wind_speed' in ds.variables or 'u100' in ds.variables):
        lons = np.asarray(ds.variables['longitude'][:])
        lats = np.asarray(ds.variables['latitude'][:])
        lon_idx = np.abs(lons - longitude).argmin()
        lat_idx = np.abs(lats - latitude).argmin()

        # The averaged weather file stores hourly mean wind speed directly.
        # Use it rather than recomputing sqrt(mean_u100^2 + mean_v100^2), which
        # suppresses wind when directions vary across source years.
        if 'wind_speed' in ds.variables:
            speed = ds.variables['wind_speed']
            if len(speed.shape) == 4:
                energy = np.asarray(speed[lat_idx, lon_idx, :, :])**2
            else:
                energy = np.asarray(speed[:, lat_idx, lon_idx])**2
            return energy.flatten()

        u = ds.variables['u100']
        v = ds.variables['v100']
        if len(u.shape) == 4:
            energy = np.asarray(u[lat_idx, lon_idx, :, :])**2 + np.asarray(v[lat_idx, lon_idx, :, :])**2
        else:
            energy = np.asarray(u[:, lat_idx, lon_idx])**2 + np.asarray(v[:, lat_idx, lon_idx])**2
        return energy.flatten()
    # 计算风能（仅在最近网格点上进行计算，避免全场运算占用内存）
    point = ds.sel(latitude=latitude, longitude=longitude, method='nearest')
    if 'wind_speed' in point:
        energy = point['wind_speed']**2
    else:
        energy = (point['u100']**2 + point['v100']**2)
    wind_limit = energy.to_numpy().flatten()
    return wind_limit

def acm_solar(dataset, latitude, longitude):
    # 找到最接近给定经纬度的网格点的索引
    lons = np.asarray(dataset.variables['longitude'][:])
    lats = np.asarray(dataset.variables['latitude'][:])
    lon_idx = np.abs(lons - longitude).argmin()
    lat_idx = np.abs(lats - latitude).argmin()

    # The original data was 3D (time, lat, lon). The new averaged data is 4D (dayofyear, hour, lat, lon).
    # We must slice it as a 4D array and then flatten the time dimensions (dayofyear, hour)
    # into a single 1D array for the simulation to iterate through.
    var = dataset.variables['ssrd']
    if len(var.shape) == 4:
        # Handle the new 4D data structure, which appears to be (lat, lon, day, hour)
        ssrd_data = np.asarray(var[lat_idx, lon_idx, :, :]).flatten()
    else:
        # Handle the original 3D data structure
        ssrd_data = np.asarray(var[:, lat_idx, lon_idx]).flatten()

    return ssrd_data

def acm_income(bids, list, max_bat_price):
    income_dict = {}
    if not bids:
        return income_dict
    max_gen_price = max([subbid[1] for subbid in bids if len(subbid) > 1])
    period_hours = physical_period_hours()
    for subbid in bids:
        key = subbid[0].name
        value = subbid[2] * period_hours * max_gen_price
        income_dict[key] = value
    for sublist in list:
        if(type(sublist[0]) == Battery):
            key = sublist[0].name
            value = sublist[1] * period_hours * max_bat_price
            income_dict[key] = value
    return income_dict


def acm_income_balance(balance_list, max_gen_price, max_bat_price):
    income_dict = {}
    period_hours = physical_period_hours()
    for sublist in balance_list:
        if(type(sublist[0]) == Battery):
            key = sublist[0].name
            value = sublist[1] * period_hours * max_bat_price
            income_dict[key] = value
        else:
            key = sublist[0].name
            value = sublist[1] * period_hours * max_gen_price
            income_dict[key] = value
    return income_dict


def store_service_three(accepted_bids, new_bids, period, need_curtailed_energy, last_gen_energy, excess_energy,
                        gen_list, connections, electrolyzer):
    # initialize the energy to stored as zero
    global curtailed_energy
    store_energy = 0
    # curtailment fee list
    curtailed_fee = []
    curtailed_energy_list = []
    soldable = []
    #print(need_curtailed_energy)
    for pool in new_bids:
        if sum(pool[0].stored_energy.values()) <= pool[0].pool_limit and need_curtailed_energy != 0:
            # curtailed_fee.append(need_curtailed_energy*item[1])
            # store the minimum among power limit, the rest of energy limit and available energy
            limit = (pool[0].per_pool_limit - pool[0].stored_energy.get(period, 0))
            energy = min(limit, need_curtailed_energy,
                                                              (pool[0].pool_limit - sum(
                                                                  pool[0].stored_energy.values())))
            pool[0].set_stored_energy_var(period, pool[0].n_1 * energy)
            # remember this minimum
            store_energy += energy
            # energy needs to be curtailed
            need_curtailed_energy = \
                need_curtailed_energy - \
                energy
            curtailed_fee.append(energy * 0)
    if excess_energy != 0:
        for pool in new_bids:
            if sum(pool[0].stored_energy.values()) <= pool[0].pool_limit and excess_energy != 0:
                # curtailed_fee.append(need_curtailed_energy*item[1])
                # do this again for excess generation
                limit =(pool[0].per_pool_limit - pool[0].stored_energy.get(period, 0))
                energy = min(limit, excess_energy,(pool[0].pool_limit - sum(pool[0].stored_energy.values())))
                pool[0].set_stored_energy_var(period, pool[0].n_1 * energy )
                # remember this as well
                store_energy += energy
                # final curtailment
                excess_energy = \
                    excess_energy - \
                    energy
    # sell to interconnector before there is curtailment
    sold_fee = []
    for item in connections:
        if item.transfer_constraint < 0:
            soldable.append([item, item.transfer_constraint, item.external_price])
    if not soldable:
        '''没有外售部分，直接电解然后弃电了'''
        sold_fee.append(0)
        for item in connections:
            item.sold_energy = 0
        energy_cell = min((electrolyzer.real_energy + electrolyzer.rampup_rate), electrolyzer.capacity_limit)
        if excess_energy + need_curtailed_energy > 0:
            min_value = min((excess_energy + need_curtailed_energy), energy_cell)
            energy_cell_period = min_value
            if excess_energy > min_value:
                excess_energy -= min_value
                green_hy = min_value * electrolyzer.energy_efficiency
                electrolyzer.set_real_energy(min_value)
            else:
                need_curtailed_energy = (excess_energy + need_curtailed_energy) - min_value
                excess_energy = 0
                green_hy = min_value * electrolyzer.energy_efficiency
                electrolyzer.set_real_energy(min_value)
        else:
            green_hy = 0
            electrolyzer.set_real_energy(0)
            energy_cell_period = 0
        curtailed_energy = need_curtailed_energy
        for item in accepted_bids:
            if need_curtailed_energy != 0:
                if type(item[0]) == ExpensiverenewableGenerator:
                    if item[2] >= need_curtailed_energy:
                        # curtailment fee
                        curtailed_fee.append(need_curtailed_energy * item[3])
                        item[2] = item[2] - need_curtailed_energy
                        item[0].set_real_gen_energy(item[2])
                        curtailed_energy_list.append([item[0], need_curtailed_energy])
                        for gen in gen_list:
                            if gen[0] == item[0]:
                                gen[1] -= need_curtailed_energy
                                break
                        need_curtailed_energy = 0
                        break
                    else:
                        curtailed_fee.append(item[2] * item[3])
                        need_curtailed_energy = need_curtailed_energy - item[2]
                        curtailed_energy_list.append([item[0], item[2]])
                        item[0].set_real_gen_energy(0)
                        for gen in gen_list:
                            if gen[0] == item[0]:
                                gen[1] -= item[2]
                            else:
                                pass
                else:
                    for index, item in enumerate(accepted_bids):
                        if type(item[0]) != ExpensiverenewableGenerator:
                            if item[2] - last_gen_energy[index][2] == item[0].alter_limit:
                                max_curtail_energy = (
                                    2 * item[0].alter_limit if item[2] >= 2 * item[0].alter_limit else item[2])
                            else:
                                max_curtail_energy = (
                                    item[2] - (last_gen_energy[index][2] - item[0].alter_limit) if
                                    last_gen_energy[index][2] >=
                                    item[0].alter_limit else
                                    item[2])
                            if max_curtail_energy >= need_curtailed_energy:
                                curtailed_fee.append(need_curtailed_energy * item[3])
                                item[2] = item[2] - need_curtailed_energy
                                item[0].set_real_gen_energy(item[2])
                                for gen in gen_list:
                                    if gen[0] == item[0]:
                                        gen[1] = item[2]
                                    else:
                                        pass
                                if type(item[0]) == (WaterGenerator or BiomassGenerator):
                                    item[0].dec_have_gen_energy(need_curtailed_energy)
                                else:
                                    pass
                                break
                            else:
                                curtailed_fee.append(max_curtail_energy * item[3])
                                need_curtailed_energy = need_curtailed_energy - max_curtail_energy
                                item[2] = item[2] - max_curtail_energy
                                item[0].set_real_gen_energy(item[2])
                                for gen in gen_list:
                                    if gen[0] == item[0]:
                                        gen[1] = item[2]
                                    else:
                                        pass
                                if type(item[0]) == (WaterGenerator or BiomassGenerator):
                                    item[0].dec_have_gen_energy(max_curtail_energy)
                                else:
                                    pass
                        else:
                            pass
            # no curtailment means curtailment fee is zero
            elif need_curtailed_energy == 0:
                curtailed_fee.append(0)
                break
    else:
        soldable.sort(key=lambda x: x[2], reverse=True)
        # to see whether the price is positive
        for item in soldable:
            if item[2] > 0:
                # can sell this much of energy
                sell_energy = min(abs(item[1]), (excess_energy + need_curtailed_energy))
                sold_fee.append(sell_energy * item[2])
                item[0].sold_energy = sell_energy
                # rest of energy
                if excess_energy > sell_energy:
                    excess_energy -= sell_energy
                else:
                    need_curtailed_energy = (excess_energy + need_curtailed_energy) - sell_energy
                    excess_energy = 0
            else:
                sold_fee.append(0)
                item[0].sold_energy = 0
        energy_cell = min((electrolyzer.real_energy + electrolyzer.rampup_rate), electrolyzer.capacity_limit)
        if excess_energy + need_curtailed_energy > 0:
            min_value = min((excess_energy + need_curtailed_energy), energy_cell)
            energy_cell_period = min_value
            if excess_energy > min_value:
                excess_energy -= min_value
                green_hy = min_value * electrolyzer.energy_efficiency
                electrolyzer.set_real_energy(min_value)
            else:
                need_curtailed_energy = (excess_energy + need_curtailed_energy) - min_value
                excess_energy = 0
                green_hy = min_value * electrolyzer.energy_efficiency
                electrolyzer.set_real_energy(min_value)
        else:
            green_hy = 0
            electrolyzer.set_real_energy(0)
            energy_cell_period = 0
        curtailed_energy = need_curtailed_energy
        if need_curtailed_energy > 0:
            for item in accepted_bids:
                if need_curtailed_energy != 0:
                    if type(item[0]) == ExpensiverenewableGenerator:
                        if item[2] >= need_curtailed_energy:
                            curtailed_fee.append(need_curtailed_energy * item[3])
                            item[2] = item[2] - need_curtailed_energy
                            item[0].set_real_gen_energy(item[2])
                            curtailed_energy_list.append(curtailed_energy)
                            for gen in gen_list:
                                if gen[0] == item[0]:
                                    gen[1] -= need_curtailed_energy
                                    break
                            need_curtailed_energy = 0
                            break
                        else:
                            curtailed_fee.append(item[2] * item[3])
                            need_curtailed_energy = need_curtailed_energy - item[2]
                            curtailed_energy_list.append(item[2])
                            item[0].set_real_gen_energy(0)
                            for gen in gen_list:
                                if gen[0] == item[0]:
                                    gen[1] -= item[2]
                                else:
                                    pass
                    else:
                        for index, item in enumerate(accepted_bids):
                            if type(item[0]) != ExpensiverenewableGenerator:
                                if item[2] - last_gen_energy[index][2] == item[0].alter_limit:
                                    max_curtail_energy = (
                                        2 * item[0].alter_limit if item[2] >= 2 * item[0].alter_limit else item[2])
                                else:
                                    max_curtail_energy = (
                                        item[2] - (last_gen_energy[index][2] - item[0].alter_limit) if
                                        last_gen_energy[index][2] >=
                                        item[0].alter_limit else
                                        item[2])
                                if max_curtail_energy >= need_curtailed_energy:
                                    curtailed_fee.append(need_curtailed_energy * item[3])
                                    item[2] = item[2] - need_curtailed_energy
                                    item[0].set_real_gen_energy(item[2])
                                    for gen in gen_list:
                                        if gen[0] == item[0]:
                                            gen[1] = item[2]
                                        else:
                                            pass
                                    if type(item[0]) == (WaterGenerator or BiomassGenerator):
                                        item[0].dec_have_gen_energy(need_curtailed_energy)
                                    else:
                                        pass
                                    break
                                else:
                                    curtailed_fee.append(max_curtail_energy * item[3])
                                    need_curtailed_energy = need_curtailed_energy - max_curtail_energy
                                    item[2] = item[2] - max_curtail_energy
                                    item[0].set_real_gen_energy(item[2])
                                    for gen in gen_list:
                                        if gen[0] == item[0]:
                                            gen[1] = item[2]
                                        else:
                                            pass
                                    if type(item[0]) == (WaterGenerator or BiomassGenerator):
                                        item[0].dec_have_gen_energy(max_curtail_energy)
                                    else:
                                        pass
                            else:
                                pass
        else:
            sold_fee.append(0)
    #print(store_energy)
    return (curtailed_fee, store_energy, gen_list, curtailed_energy, excess_energy, sold_fee,green_hy,
            energy_cell_period,curtailed_energy_list)


# Environment functions
def ahead_market_bidding(generators, batterys, forecast_demand, period, accepted_bids,  ahead_renewables, ahead_other,
                         ahead_traditional, ahead_nuclear, bidding_factor):
    renewable_hy_list = []
    for gen in generators:
        if type(gen) == ExpensiverenewableGenerator:
            energy = min((gen.real_energy + gen.rampup_rate), gen.electrolyzer_limit)
            if gen.capacity_limit != 0:
                if energy > gen.capacity_limit:
                    gen.capacity_limit = 0
                    renewable_green_hy = gen.capacity_limit * gen.energy_efficiency
                    gen.set_real_energy(gen.capacity_limit)
                    renewable_hy_list.append([gen, gen.capacity_limit * gen.electrolyzer_cost, renewable_green_hy])
                else:
                    gen.capacity_limit -= energy
                    renewable_green_hy = energy * gen.energy_efficiency
                    gen.set_real_energy(energy)
                    renewable_hy_list.append([gen, energy * gen.electrolyzer_cost, renewable_green_hy])
    # bids among generator agent characteristics
    bids = [[gen, gen.gen_cost * bidding_factor, gen.capacity_limit, gen.curtail_cost, 0] for gen in generators]
    # initialize excess energy
    excess_energy = 0
    max_bat_price =0
    # add start-up cost
    gen_list = []
    excess_energy_list = []
    accepted_bids_name = []
    for item in accepted_bids:
        accepted_bids_name.append(item[0])
    for item in bids:
        if (item[0] not in accepted_bids_name and (type(item[0]) != WaterGenerator and type(item[0]) != ExpensiverenewableGenerator)):
            item[1] += item[0].startup_cost
        else:
            pass
        # limit for hydro and biomass, natural storage consideration
        if type(item[0]) == BiomassGenerator or type(item[0]) == WaterGenerator:
            # add natural output of hydro and biomass
            item[0].add_energy_limit(item[0].add_energy)
            #if item[0].energy_limit - item[0].have_gen_energy < item[0].have_gen_energy:
                #bids.remove(item)
    # conisder the storage
    new_bids = [[bat, bat.pool_limit] for bat in batterys]
    # selectable discharge
    for item in new_bids:
        decay_func(item[0].stored_energy, item[0].battery_type)
    # storage composition
    storage_pool_composition = []
    for item in new_bids:
        storage_pool_composition.append([item[0], sum(item[0].stored_energy.values())])
    # print(storage_pool_composition)
    # send storage amount to storage_pool_list
    storage_pool_list = []
    for i in range(len(new_bids)):
        original_dict = new_bids[i][0].stored_energy
        # run through energy period of pool
        for key in original_dict:
            # storage_pool_list 's characteristics [generator，price，stored at which price，charge amount]
            storage_pool_list.append([new_bids[i][0],
                                      ((period - key) * new_bids[i][0].per_storage_fee
                                     + new_bids[i][0].storage_fee) * bidding_factor,
                                      key,
                                      original_dict[key]])
        # storage_pool and merge_storage_pool to plot
        # ps:with discharge
    storage_pool = {}
    if new_bids:  # Safety check to prevent IndexError
        for key, value in new_bids[0][0].stored_energy.items():
            if key in storage_pool:
                storage_pool[key] += value
            else:
                storage_pool[key] = value
    # charge amount in no-charge period is 0（or keyerror）
    # Keep dictionary sparse - only store keys with actual values to save memory
    # Only remove entries with truly negligible energy (< 0.001) to save memory
    # Don't filter by age since decay is slow and old energy still matters
    if storage_pool:
        # Remove entries with negligible energy (below threshold)
        # This helps with memory while preserving all meaningful energy
        ENERGY_THRESHOLD = 0.001  # Remove entries with energy < 0.001
        # Silently remove entries with negligible energy to save memory
        storage_pool = {k: v for k, v in storage_pool.items() if v >= ENERGY_THRESHOLD}
        # Sort efficiently by creating new dict with sorted keys only
        # This avoids creating intermediate large lists
        if storage_pool:
            sorted_keys = sorted(storage_pool.keys())
            storage_pool = {k: storage_pool[k] for k in sorted_keys}
    # overall storage
    merge_storage_pool = {}
    for d in new_bids:
        for key, value in d[0].stored_energy.items():
            if key in merge_storage_pool:
                merge_storage_pool[key] += value
            else:
                merge_storage_pool[key] = value
    if merge_storage_pool:
        # Only remove entries with truly negligible energy (< 0.001) to save memory
        # Don't filter by age since decay is slow and old energy still matters
        ENERGY_THRESHOLD = 0.001  # Remove entries with energy < 0.001
        # Silently remove entries with negligible energy to save memory
        merge_storage_pool = {k: v for k, v in merge_storage_pool.items() if v >= ENERGY_THRESHOLD}
        # Sort efficiently by creating new dict with sorted keys only
        # This avoids creating intermediate large lists
        if merge_storage_pool:
            sorted_keys = sorted(merge_storage_pool.keys())
            merge_storage_pool = {k: merge_storage_pool[k] for k in sorted_keys}
    
    # Force garbage collection to free memory
    gc.collect()
    
    new_list = bids + storage_pool_list
    # bid
    new_list.sort(key=lambda x: x[1])
    # print(new_list)
    # benchmark
    demand_met = 0
    # nuclear may lead to excess generation because can't ramp down
    # take down this to check
    real_forecast_demand = 0
    # chosen generators in wholesale market
    last_gen_energy = [(item[0], item[3], item[0].real_gen_energy) for item in bids]
    accepted_gens = []
    accepted_bids_period = []
    # calculate price
    add_price_ahead = []
    for item in new_list:
        # loop if generation is small than demand
        if demand_met < forecast_demand:
            # if generator instead of storage, use this method
            if len(item) == 5:
                # check if beyond limit
                if item[2] != 0:
                    # if no enough capacity
                    if type(item[0]) != ExpensiverenewableGenerator:
                        if type(item[0]) != WaterGenerator and type(item[0]) != BiomassGenerator:
                            if min((item[0].real_gen_energy + item[0].alter_limit), item[2]) <= forecast_demand:
                                energy = min((item[0].real_gen_energy + item[0].alter_limit), item[2])
                                item[0].set_real_gen_energy(
                                    energy)
                                accepted_bids_period.append(
                                    [item[0], item[1], energy,
                                     item[3]])
                                gen_list.append([item[0], energy])
                                forecast_demand -= energy
                                accepted_gens.append(item[0])
                                item[0].set_run_time()
                                if type(item[0]) == NuclearGenerator:
                                    ahead_nuclear[period] += item[1] * energy
                                else:
                                    ahead_traditional[period] += item[1] * energy
                            else:
                                if type(item[0]) != NuclearGenerator:
                                    item[0].set_real_gen_energy(forecast_demand)
                                    accepted_gens.append(item[0])
                                    item[0].set_run_time()
                                    accepted_bids_period.append([item[0], item[1], forecast_demand, item[3]])
                                    gen_list.append([item[0], forecast_demand])
                                    ahead_traditional[period] += item[1] * forecast_demand
                                else:
                                    energy = max((item[0].real_gen_energy - item[0].alter_limit), forecast_demand)
                                    excess_energy = energy - forecast_demand
                                    excess_energy_list.append([item[0],excess_energy])
                                    item[0].set_real_gen_energy(energy)
                                    ahead_nuclear[period] += item[1] * energy
                                    accepted_gens.append(item[0])
                                    item[0].set_run_time()
                                    accepted_bids_period.append([item[0], item[1], energy, item[3]])
                                    gen_list.append([item[0], energy])
                                forecast_demand = 0
                                break
                        else:
                            if min((item[0].real_gen_energy + item[0].alter_limit), item[2],
                                   (item[0].energy_limit - item[0].have_gen_energy)) <= forecast_demand:
                                energy =  min((item[0].real_gen_energy + item[0].alter_limit), item[2],
                                   (item[0].energy_limit - item[0].have_gen_energy))
                                item[0].set_real_gen_energy(energy)
                                accepted_gens.append(item[0])
                                item[0].set_run_time()
                                accepted_bids_period.append(
                                    [item[0], item[1], energy, item[3]])
                                gen_list.append([item[0], energy])
                                forecast_demand -= energy
                                item[0].add_have_gen_energy(energy)
                                ahead_other[period] += item[1] * energy
                            else:
                                item[0].set_real_gen_energy(forecast_demand)
                                accepted_gens.append(item[0])
                                item[0].set_run_time()
                                accepted_bids_period.append([item[0], item[1], forecast_demand, item[3]])
                                gen_list.append([item[0], forecast_demand])
                                ahead_other[period] += item[1] * forecast_demand
                                item[0].add_have_gen_energy(forecast_demand)
                                forecast_demand = 0
                                break
                    else:
                        if item[2] <= forecast_demand:
                            # print(accepted_bids)
                            accepted_gens.append(item[0])
                            item[0].set_run_time()
                            accepted_bids_period.append([item[0], item[1], item[2], item[3]])
                            gen_list.append([item[0], item[2]])
                            item[0].set_real_gen_energy(item[2])
                            ahead_renewables[period] += item[1] * item[2]
                            forecast_demand -= item[2]
                        else:
                            accepted_gens.append(item[0])
                            item[0].set_run_time()
                            accepted_bids_period.append([item[0], item[1], forecast_demand, item[3]])
                            excess_energy = item[2] - forecast_demand
                            excess_energy_list.append([item[0], excess_energy])
                            bids_copy = bids.copy()
                            bids_copy.remove(item)
                            set_gen = set(item[0] for item in accepted_bids_period)
                            for gen in bids_copy:
                                if type(gen[0]) == ExpensiverenewableGenerator and gen[0] not in set_gen:
                                    excess_energy += gen[0].capacity_limit
                                    excess_energy_list.append([item[0], gen[0].capacity_limit])
                            item[0].set_real_gen_energy(forecast_demand)
                            ahead_renewables[period] += item[1] * forecast_demand
                            gen_list.append([item[0], forecast_demand])
                            forecast_demand = 0
                            break
                else:
                    pass
                #print(item[0])
            # if chose storage pool
            else:
                if item[3] <= (forecast_demand/item[0].n_2):
                    forecast_demand -= item[0].n_2*item[3]
                    gen_list.append([item[0], item[0].n_2*item[3]])
                    # discharge
                    item[0].clr_stored_energy_var(item[2], item[3])
                    # calculate storage cost
                    add_price_ahead.append(item[1] * item[3])
                    max_bat_price = item[1]
                else:
                    item[0].clr_stored_energy_var(item[2], (forecast_demand/item[0].n_2))
                    gen_list.append([item[0], forecast_demand/item[0].n_2])
                    add_price_ahead.append((forecast_demand/item[0].n_2) * item[1])
                    forecast_demand = 0
                    max_bat_price = item[1]
                    break
        else:
            pass
    accepted_bids[:] = accepted_bids_period
    if any(isinstance(obj, NuclearGenerator) for obj in accepted_gens):
        pass
    else:
        for gen in generators:
            if type(gen) == NuclearGenerator:
                gen.set_real_gen_energy(gen.real_gen_energy*0.99)
    # calculate overall storage fee，add each storage pool together
    total_add_price_ahead = sum(add_price_ahead)
    '''
    for item in new_bids:
        if DEBUG_MARKET_STDOUT:
            print(item[0].stored_energy)
    '''
    gen_list_name = []
    for item in gen_list:
        if item[1] != 0:
            gen_list_name.append([item[0].name, item[1]])
    income_dict = acm_income(accepted_bids, gen_list, max_bat_price)
    return accepted_bids, total_add_price_ahead, storage_pool, merge_storage_pool, storage_pool_composition, \
           last_gen_energy, excess_energy, ahead_renewables, ahead_other, ahead_traditional, gen_list, ahead_nuclear, \
        gen_list_name, bids, income_dict,excess_energy_list,renewable_hy_list


def curtailment_market_bidding(period, real_demand, forecast_demand, accepted_bids, last_gen_energy, excess_energy,
                               gen_list, connections,electrolyzer, batterys):
    # choose available renewables for charging
    new_bids = [[bat, bat.storage_fee, bat.per_storage_fee, bat.n_1, bat.n_2] for bat in batterys]
    #print(new_bids)
    # curtailment fee rand
    new_bids.sort(key=lambda x: (x[1], x[2], (x[3] * x[4])))
    # new storage pool composition
    storage_pool_composition_after = []
    for item in new_bids:
        storage_pool_composition_after.append([item[0], sum(item[0].stored_energy.values())])
    accepted_bids.sort(key=lambda x: x[3])
    last_gen_energy.sort(key=lambda x: x[1])
    # calculate needed curtailment
    need_curtailed_energy = forecast_demand - real_demand
    # storage service 3(central dispatch curtailment and excess generation instead of attach storage to generator)
    (curtailed_fee, store_energy, gen_list, curtailed_energy, excess_energy, sold_fee,
     green_hy,energy_cell_period,curtailed_energy_list) \
        = store_service_three(accepted_bids, new_bids, period, need_curtailed_energy, last_gen_energy, excess_energy,
                              gen_list, connections,electrolyzer)
    real_list = [[sub_list[0], sub_list[2]] for sub_list in accepted_bids if sub_list[2] != 0]
    #print(curtailed_fee)
    #test_gen.capacity_limit = test_gen.capacity_limit + need_curtailed_energy #恢复
    return curtailed_fee, store_energy, real_list, storage_pool_composition_after, gen_list, curtailed_energy, \
           excess_energy,sold_fee, green_hy,energy_cell_period,curtailed_energy_list


def balancing_market_bidding(generators, period, real_demand, forecast_demand, accepted_bids, excess_energy,
                             balance_renewables, balance_other, balance_traditional, gen_list, balance_nuclear,
                             connections, gen_list_name, bids, electrolyzer,excess_energy_list, batterys, bidding_factor):
    # calculate energy gap
    energy_provided = real_demand - forecast_demand
    #print(energy_provided)
    #print('excess_energy', excess_energy)
    # initialize balancing biddings
    balancing_fee = []
    store_energy = 0
    accepted_list = [[sub_list[0], sub_list[2]] for sub_list in accepted_bids]
    balance_list = []
    max_gen_price =0
    max_bat_price =0
    # biddings
    bids.sort(key=lambda x: x[1])
    sold_fee = []
    bought_fee = []
    soldable = []
    buable = []
    for item in connections:
        item.sold_energy = 0
    #gens = iter(bids)
    # rememmber available generators，namely generation after test_gen(included)
    # use test_gen to the marginal generator,，who has rest availability（generators before used up），from hime to bid
    if len(accepted_bids) != 0:
        test_gen = accepted_bids[-1]
    # if only use storage，then test-gen is the first generator
    else:
        test_gen = bids[0]
    #print(test_gen)
    new_bids = [[bat, bat.pool_limit] for bat in batterys]
    if excess_energy_list:
        # 如果需要补充发电的电量小于所有子列表的和，按比例分配
        if energy_provided <= excess_energy:
            total_excess_for_proportion = sum(item[1] for item in excess_energy_list)
            if total_excess_for_proportion > 0:
                for item in excess_energy_list:
                    proportion = item[1] / total_excess_for_proportion
                    energy_from_this = energy_provided * proportion
                    balancing_fee.append(item[0].gen_cost * bidding_factor * energy_from_this)
                    balance_renewables[period] += item[0].gen_cost * bidding_factor * energy_from_this
                    balance_list.append([item[0], energy_from_this])
                    for gen in gen_list:
                        if gen[0] == item[0]:
                            gen[1] += energy_from_this
                    item[1] -= energy_from_this
            excess_energy -= energy_provided
            energy_provided = 0
        #否则就全用上了
        else:
            energy_provided = energy_provided - excess_energy
            excess_energy = 0
            for item in excess_energy_list:
                if(item[1] == 0):
                    pass
                else:
                    balancing_fee.append(item[0].gen_cost * bidding_factor * item[1])
                    balance_renewables[period] += item[0].gen_cost * bidding_factor * item[1]
                    balance_list.append([item[0], item[1]])
                    for gen in gen_list:
                        if gen[0] == item[0]:
                            gen[1] += item[1]
                        else:
                            pass
                item[1] = 0
    '''
    if excess_energy != 0:
        if excess_energy > energy_provided:
            balancing_fee.append(test_gen[1] * energy_provided)
            balance_renewables[period] += test_gen[1] * energy_provided
            balance_list.append([test_gen[0], energy_provided])
            for gen in gen_list:
                if gen[0] == test_gen[0]:
                    gen[1] += energy_provided
                else:
                    pass
            excess_energy = excess_energy - energy_provided
            energy_provided = 0
        else:
            balancing_fee.append(test_gen[1] * excess_energy)
            balance_renewables[period] += test_gen[1] * excess_energy
            balance_list.append([test_gen[0], excess_energy])
            for gen in gen_list:
                if gen[0] == test_gen[0]:
                    gen[1] += excess_energy
                else:
                    pass
            energy_provided = energy_provided - excess_energy
            excess_energy = 0
    #print('excess_energy', excess_energy)
    '''
    if excess_energy != 0:
        for pool in new_bids:
            if sum(pool[0].stored_energy.values()) <= pool[0].pool_limit and excess_energy != 0:
                # curtailed_fee.append(need_curtailed_energy*item[1])
                # store energy
                limit = (pool[0].per_pool_limit - pool[0].stored_energy.get(period, 0))
                energy = min(limit, excess_energy, (pool[0].pool_limit - sum(pool[0].stored_energy.values())))
                pool[0].set_stored_energy_var(period, pool[0].n_1 * energy)
                # take down this minimum
                store_energy += energy
                # rest of excess energy
                excess_energy = \
                    excess_energy - energy

    # calculate storage price
    add_price_balance = [0]
    #print('excess_energy', excess_energy)
    #print(energy_provided)
    if energy_provided >= 0:
        # add revelent parameters to storage_pool_list
        storage_pool_list = []
        for i in range(len(new_bids)):
            # change the original_dict
            original_dict = new_bids[i][0].stored_energy
            # run through the original dict
            for key in original_dict:
                # stored energy can only be used after 2 periods
                if period - key >= 2:
                    # storage_pool_list parameter[generator，price，when，charge amount]
                    storage_pool_list.append([new_bids[i][0],
                                              ((period - key) * new_bids[i][0].per_storage_fee
                                              + new_bids[i][0].storage_fee) * bidding_factor,
                                              key,
                                              original_dict[key]])
        # find test_gen，loop from the last one with availability
        search_element = test_gen[0]
        start_index = None
        '''
        bids_name = []
        for item in bids:
            bids_name.append(item[0].name)
        if DEBUG_MARKET_STDOUT:
            print(bids_name)
        '''
        for index, element in enumerate(bids):
            if element[0] == search_element:
                start_index = index
                break
        if start_index is not None:
            # from test_gen to loop
            add_bids = bids[start_index:]
        # add storage and generator，bid together，note that generators in forms of tuple but storage in forms of list to distinguish
        new_list = add_bids + storage_pool_list
        for item in connections:
            if item.transfer_constraint < 0:
                soldable.append([item, item.transfer_constraint, item.external_price])
            else:
                buable.append((item, item.transfer_constraint, item.external_price, 0))
        if soldable and excess_energy > 0:
            soldable.sort(key=lambda x: x[2])
            # positive price can sell
            for item in soldable:
                if item[2] > 0:
                    sell_energy = min(abs(item[1]), excess_energy)
                    sold_fee.append(sell_energy * item[2])
                    item[0].sold_energy = sell_energy
                    excess_energy -= sell_energy
                else:
                    sold_fee.append(0)
                    item[0].sold_energy = 0
        if not buable:
            pass
        else:
            sold_fee.append(0)
        if excess_energy != 0:
            energy_cell = min((electrolyzer.real_energy + electrolyzer.rampup_rate), electrolyzer.capacity_limit)
            min_value = min(excess_energy, energy_cell)
            energy_cell_period = min_value
            excess_energy -= min_value
            green_hy = min_value * electrolyzer.energy_efficiency
            electrolyzer.set_real_energy(min_value)
        else:
            green_hy = 0
            electrolyzer.set_real_energy(0)
            energy_cell_period = 0
        # bids
        new_list.sort(key=lambda x: x[1])
        # distinguish storage or generator, distinguish if generate in wholesale
        '''
        new_list_copy = []
        for item in new_list:
            if type(item[0]) != Battery:
                new_list_copy.append(item)
            if DEBUG_MARKET_STDOUT:
                print(new_list_copy)
        '''
        for element in new_list:
            # if choose generator
            if type(element) == list and len(element) == 5:
                # check the ramp-up down limit
                if element[0] == test_gen[0]:
                    if type(element[0]) != ExpensiverenewableGenerator:
                        if type(element[0]) != WaterGenerator and type(element[0]) != BiomassGenerator:
                            valid_energy = min((element[0].real_gen_energy + element[0].alter_limit), element[2]) - \
                                           test_gen[2]
                            if valid_energy >= energy_provided:
                                balancing_fee.append(element[1] * energy_provided)
                                if type(element[0]) == NuclearGenerator:
                                    balance_nuclear[period] += element[1] * energy_provided
                                else:
                                    balance_traditional[period] += element[1] * energy_provided
                                balance_list.append([element[0], energy_provided])

                                max_gen_price = element[1]
                                for gen in gen_list:
                                    if gen[0] == test_gen[0]:
                                        gen[1] += energy_provided
                                    else:
                                        pass
                                element[0].set_real_gen_energy(test_gen[2] + energy_provided)
                                energy_provided = 0
                                break
                            else:
                                balancing_fee.append(element[1] * valid_energy)
                                balance_list.append([element[0], valid_energy])

                                max_gen_price = element[1]
                                element[0].set_real_gen_energy(test_gen[2] + valid_energy)
                                energy_provided = energy_provided - valid_energy
                                for gen in gen_list:
                                    if gen[0] == test_gen[0]:
                                        gen[1] += valid_energy
                                    else:
                                        pass
                                if type(element[0]) == NuclearGenerator:
                                    balance_nuclear[period] += element[1] * valid_energy
                                else:
                                    balance_traditional[period] += element[1] * valid_energy
                        else:
                            valid_energy = min((element[0].real_gen_energy + element[0].alter_limit), element[2],
                                               (element[0].energy_limit - element[0].have_gen_energy)) - test_gen[2]
                            if valid_energy >= energy_provided:
                                balancing_fee.append(element[1] * energy_provided)
                                balance_other[period] += element[1] * energy_provided
                                balance_list.append([element[0], energy_provided])

                                max_gen_price = element[1]
                                for gen in gen_list:
                                    if gen[0] == test_gen[0]:
                                        gen[1] += energy_provided
                                    else:
                                        pass
                                element[0].set_real_gen_energy(test_gen[2] + energy_provided)
                                element[0].add_have_gen_energy(energy_provided)
                                energy_provided = 0
                                break
                            else:
                                balancing_fee.append(element[1] * valid_energy)
                                balance_other[period] += element[1] * valid_energy
                                balance_list.append([element[0], valid_energy])

                                max_gen_price = element[1]
                                for gen in gen_list:
                                    if gen[0] == test_gen[0]:
                                        gen[1] += valid_energy
                                    else:
                                        pass
                                element[0].set_real_gen_energy(test_gen[2] + valid_energy)
                                element[0].add_have_gen_energy(valid_energy)
                                energy_provided = energy_provided - valid_energy
                    else:
                        pass
                else:
                    if type(element[0]) != ExpensiverenewableGenerator:
                        if type(element[0]) != WaterGenerator and type(element[0]) != BiomassGenerator:
                            valid_energy = min((element[0].real_gen_energy + element[0].alter_limit), element[2])
                            if valid_energy >= energy_provided:
                                balancing_fee.append(element[1] * energy_provided)
                                if type(element[0]) == NuclearGenerator:
                                    balance_nuclear[period] += element[1] * energy_provided
                                else:
                                    balance_traditional[period] += element[1] * energy_provided
                                balance_list.append([element[0], energy_provided])
                                element[0].set_run_time()
                                max_gen_price = element[1]
                                gen_list.append([element[0], energy_provided])
                                element[0].set_real_gen_energy(energy_provided)
                                energy_provided = 0
                                break
                            else:
                                balancing_fee.append(element[1] * valid_energy)
                                if type(element[0]) == NuclearGenerator:
                                    balance_nuclear[period] += element[1] * valid_energy
                                else:
                                    balance_traditional[period] += element[1] * valid_energy
                                balance_list.append([element[0], valid_energy])
                                element[0].set_run_time()
                                max_gen_price = element[1]
                                gen_list.append([element[0], valid_energy])
                                element[0].set_real_gen_energy(valid_energy)
                                energy_provided = energy_provided - valid_energy
                        else:
                            valid_energy = min((element[0].real_gen_energy + element[0].alter_limit), element[2],
                                               (element[0].energy_limit - element[0].have_gen_energy))
                            if valid_energy >= energy_provided:
                                balancing_fee.append(element[1] * energy_provided)
                                balance_other[period] += element[1] * energy_provided
                                balance_list.append([element[0], energy_provided])
                                element[0].set_run_time()
                                max_gen_price = element[1]
                                gen_list.append([element[0], energy_provided])
                                element[0].set_real_gen_energy(energy_provided)
                                element[0].add_have_gen_energy(energy_provided)
                                energy_provided = 0
                                break
                            else:
                                balancing_fee.append(element[1] * valid_energy)
                                balance_other[period] += element[1] * valid_energy
                                balance_list.append([element[0], valid_energy])
                                element[0].set_run_time()
                                max_gen_price = element[1]
                                gen_list.append([element[0], valid_energy])
                                element[0].set_real_gen_energy(valid_energy)
                                element[0].add_have_gen_energy(valid_energy)
                                energy_provided = energy_provided - valid_energy
                    else:
                        '''
                        valid_energy = element[2]
                        if valid_energy >= energy_provided:
                            balancing_fee.append(element[1] * energy_provided)
                            balance_renewables[period] += element[1] * energy_provided
                            element[0].set_real_gen_energy(test_gen[2] + energy_provided)
                            balance_list.append([element[0], energy_provided])
                            gen_list.append([element[0], energy_provided])
                            energy_provided = 0
                            break
                        else:
                            balancing_fee.append(element[1] * valid_energy)
                            balance_renewables[period] += element[1] * valid_energy
                            element[0].set_real_gen_energy(test_gen[2] + energy_provided)
                            balance_list.append([element[0], valid_energy])
                            gen_list.append([element[0], valid_energy])
                            energy_provided = energy_provided - valid_energy
                        '''
                        pass
            # if choose storage pool
            elif type(element) == list and len(element) == 4:
                # can't use when empty
                if element[3] != 0:
                    # can only discharge to zero
                    if element[3] <= (energy_provided/element[0].n_2):
                        max_bat_price = element[1]
                        energy_provided -= element[0].n_2*element[3]
                        # discharge from stock
                        element[0].clr_stored_energy_var(element[2], element[3])
                        # calculate cost
                        add_price_balance.append(element[1] * element[3])
                        balance_list.append([element[0], element[0].n_2*element[3]])
                        found = False
                        for gen in gen_list:
                            if gen[0] == element[0]:
                                gen[1] += element[0].n_2*element[3]
                                found = True
                                break
                        if not found:
                            gen_list.append([element[0], element[0].n_2*element[3]])
                    else:
                        max_bat_price = element[1]
                        element[0].clr_stored_energy_var(element[2], (energy_provided/element[0].n_2))
                        add_price_balance.append((energy_provided/element[0].n_2) * element[1])
                        balance_list.append([element[0], energy_provided])
                        found = False
                        for gen in gen_list:
                            if gen[0] == element[0]:
                                gen[1] += energy_provided
                                found = True
                                break
                        if not found:
                            gen_list.append([element[0], energy_provided])
                        energy_provided = 0
                        break
            elif type(element) == tuple and len(element) == 4:
                valid_energy = min(excess_energy,element[2])
                if valid_energy >= energy_provided:
                    balancing_fee.append(element[1] * energy_provided)
                    bought_fee.append(element[1] * energy_provided)
                    gen_list.append([element[0], energy_provided])
                    balance_list.append([element[0], energy_provided])
                    energy_provided = 0
                    break
                else:
                    balancing_fee.append(element[1] * valid_energy)
                    balance_list.append([element[0], valid_energy])
                    gen_list.append([element[0], valid_energy])
                    bought_fee.append(element[1] * valid_energy)
    else:
        if excess_energy != 0:
            energy_cell = min((electrolyzer.real_energy + electrolyzer.rampup_rate), electrolyzer.capacity_limit)
            min_value = min(excess_energy, energy_cell)
            energy_cell_period = min_value
            excess_energy -= min_value
            green_hy = min_value * electrolyzer.energy_efficiency
            electrolyzer.set_real_energy(min_value)
        else:
            green_hy = 0
            electrolyzer.set_real_energy(0)
            energy_cell_period = 0
    #print('excess_energy', excess_energy)
    #print(energy_provided)
    balance_list_name = []
    for item in balance_list:
        balance_list_name.append([item[0].name, item[1]])
    if energy_provided != 0:
        if DEBUG_MARKET_STDOUT:
            print('insufficient energy', period)
            print(energy_provided)
            print(gen_list_name)
            print(balance_list_name)
            print('----------------------------------------------------', period)
    total_add_price_balance = sum(add_price_balance)
    real_list = [x for x in accepted_list] + [y for y in balance_list if y[0] not in [x[0] for x in accepted_list]] + \
                [[x[0], x[1] + y[1]] for x in accepted_list for y in balance_list if x[0] == y[0]]
    storage_pool_composition_after = []
    for item in new_bids:
        storage_pool_composition_after.append([item[0], sum(item[0].stored_energy.values())])
    income_dict_balance = acm_income_balance(balance_list, max_gen_price, max_bat_price)
    return balancing_fee, total_add_price_balance, real_list, store_energy, storage_pool_composition_after, \
           balance_renewables, balance_other, balance_traditional, gen_list ,balance_nuclear, excess_energy, sold_fee, \
           bought_fee, green_hy, energy_cell_period, income_dict_balance, energy_provided


def save_blackout_data_to_csv(blackout_periods, filename='blackout_data.csv'):
    """
    Save blackout (energy deficit) data to a CSV file.
    
    Parameters:
    -----------
    blackout_periods : list
        List of energy deficits for each period (in MWh)
    filename : str
        Output CSV filename (default: 'blackout_data.csv')
    """
    import csv
    
    # Calculate total annual energy deficit
    total_annual_deficit = sum(blackout_periods)
    
    # Prepare data for CSV
    with open(filename, 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        
        # Write header
        writer.writerow(['Period', 'Energy_Deficit_MWh'])
        
        # Write period-by-period data
        for period, deficit in enumerate(blackout_periods):
            writer.writerow([period, deficit])
        
        # Write a blank row for separation
        writer.writerow([])
        
        # Write summary statistics
        writer.writerow(['Summary Statistics'])
        writer.writerow(['Total Annual Energy Deficit (MWh)', total_annual_deficit])
        writer.writerow(['Number of Blackout Periods', sum(1 for d in blackout_periods if d > 0)])
        writer.writerow(['Total Periods', len(blackout_periods)])
        writer.writerow(['Average Deficit per Blackout Period (MWh)', 
                        total_annual_deficit / sum(1 for d in blackout_periods if d > 0) if sum(1 for d in blackout_periods if d > 0) > 0 else 0])
        writer.writerow(['Maximum Period Deficit (MWh)', max(blackout_periods) if blackout_periods else 0])
    
    print(f"Blackout data saved to {filename}")
    print(f"Total Annual Energy Deficit: {total_annual_deficit:.2f} MWh")
    print(f"Number of Blackout Periods: {sum(1 for d in blackout_periods if d > 0)} out of {len(blackout_periods)} periods")


# Simulation and plotting functions
def cleanup_accumulating_lists(total_renew_capacity, renew_capacity, gen_list_composition, 
                                 storage_pool_composition):
    """Clean up accumulating lists to prevent memory bloat"""
    import gc
    
    # Clear lists that accumulate over periods - removed global variables
    
    # Clear if they get too large
    if len(total_renew_capacity) > 500:
        total_renew_capacity.clear()
    if len(renew_capacity) > 500:
        renew_capacity.clear()
    # Do NOT clear gen_list_composition; it is used for analysis after simulation
    # Optionally trim storage_pool_composition if only plots use it
    if len(storage_pool_composition) > 2000:
        del storage_pool_composition[:1000]
    # The following lists were in the original function but are not defined in run_simulation.
    # It's safer to handle them separately if they cause issues.
    # if len(storage_pool_list) > 500:
    #     storage_pool_list.clear()
    # if len(accepted_bids_period) > 500:
    #     accepted_bids_period.clear()
    # if len(gen_list_name) > 500:
    #     gen_list_name.clear()
    # if len(storage_pool_composition_after) > 500:
    #     storage_pool_composition_after.clear()
    
    # Force garbage collection
    gc.collect()


def run_simulation(periods, generators, batterys, forecast_demands, real_demands, connections, electrolyzer):
    # plot average generation price
    avg_electricity_prices = []
    avg_gen_fees = []
    avg_balancing_fees = []
    avg_curtailment_fees = []
    avg_storage_fees = []
    # storage in each period
    curtailment_fees = []
    # balancing in each period
    balancing_fees = []
    # overall storage fee
    storage_fees = []
    # stored energy in each periods
    store_electricity = []
    # curtailment fee in each period
    generation_costs = []
    # single storage pool
    storage_pool = []
    # overall storage
    total_storage_pool = []
    # balancing fee, initialize as 0，undate only enter balancing(instead of curtail)
    total_storage_fee_balance = 0
    # storage composition
    storage_pools_composition = []
    storage_pool_composition = []
    # selected generators
    accepted_bids = []
    # used energy(discharge)
    usage_storage_pool_composition = []
    gen_fees = []
    # Preallocate as float32 to halve memory vs float64
    ahead_renewables = np.zeros(periods, dtype=np.float32)
    ahead_traditional = np.zeros(periods, dtype=np.float32)
    ahead_other = np.zeros(periods, dtype=np.float32)
    ahead_nuclear = np.zeros(periods, dtype=np.float32)
    balance_renewables = np.zeros(periods, dtype=np.float32)
    balance_traditional = np.zeros(periods, dtype=np.float32)
    balance_other = np.zeros(periods, dtype=np.float32)
    balance_nuclear = np.zeros(periods, dtype=np.float32)
    gen_list_composition  = []
    curtailed_electricity = []
    excess_electricity = []
    total_annual_cost = []
    total_annual_demand = []
    carbon_emission = []
    sold_fees = []
    purchase_fees = []
    total_green_hy = []
    total_renew_capacity = []
    renew_capacity = []
    traditional_gen = {'ccgt': 0, 'ocgt': 0, 'biomass': 0}
    total_annual_energycell = []
    total_income_dict = {}
    excess_energy_dict = {}
    excess_energy_final_dict = {}
    curtailed_energy_dict = {}
    renewable_hy_dict = {}
    flexible_demand_list = []
    interconnector_exports_list = []
    blackout_periods = []  # Track energy deficit (blackout) for each period

    bidding_factor = config.simulation_parameters["bidding_factor"]
    trace_enabled = os.getenv("SAVE_MARKET_TRACE", "1") != "0"
    trace_scenario = os.getenv("DECARB_SCENARIO", "scenario")
    trace_year = os.getenv("SIMULATION_YEAR", "year")
    trace_run_id = os.getenv("MARKET_TRACE_RUN_ID")
    market_trace_file = None
    income_trace_file = None
    market_writer = None
    income_writer = None
    agent_names_for_trace = [
        getattr(asset, "name", asset.__class__.__name__)
        for asset in list(generators) + list(batterys) + [electrolyzer]
    ]
    if trace_enabled:
        from pathlib import Path as _Path
        trace_parts = ["market_trace_outputs"]
        if trace_run_id:
            trace_parts.extend([trace_run_id, trace_scenario])
        else:
            trace_parts.append(trace_scenario)
        trace_base = os.getenv("MARKET_TRACE_BASE_DIR", "").strip()
        if trace_base:
            trace_root = _Path(trace_base)
        else:
            trace_root = _Path(__file__).resolve().parent
        trace_dir = trace_root.joinpath(*trace_parts)
        trace_dir.mkdir(parents=True, exist_ok=True)
        market_trace_path = trace_dir / f"market_auction_results_{trace_year}.csv"
        income_trace_path = trace_dir / f"agent_period_income_{trace_year}.csv"
        market_trace_file = open(str(market_trace_path), "w", newline="", encoding="utf-8")
        income_trace_file = open(str(income_trace_path), "w", newline="", encoding="utf-8")
        market_writer = csv.DictWriter(market_trace_file, fieldnames=[
            "scenario", "year", "period", "market_stage", "asset_name",
            "accepted_energy_mwh", "accepted_price_gbp_per_mwh", "bid_cost_or_curtail_cost",
            "forecast_demand_mwh", "real_demand_mwh", "period_total_gen_cost_gbp",
            "storage_fee_gbp", "curtailment_fee_gbp", "balancing_fee_gbp",
            "sold_fee_gbp", "purchase_fee_gbp", "energy_deficit_mwh", "excess_energy_mwh",
        ])
        income_writer = csv.DictWriter(income_trace_file, fieldnames=[
            "scenario", "year", "period", "asset_name",
            "ahead_income_gbp", "balancing_income_gbp", "total_income_gbp",
        ])
        market_writer.writeheader()
        income_writer.writeheader()

    # This part was moved from the if __name__ == '__main__' block.
    # It initializes the weather data iterators needed for the simulation loop.
    global _WEATHER_LIMIT_CACHE
    
    # 硬编码E盘路径
    filein = r'F:\newfinalweather\average_annual_wind_profile.nc'
    solar_file = r'F:\newfinalweather\average_annual_solar_profile.nc'
    
    print(f"尝试打开wind文件: {filein}")
    print(f"文件是否存在: {os.path.exists(filein)}")

    if _WEATHER_LIMIT_CACHE is None:
        print("Preparing weather profiles from netCDF files...", flush=True)
        if Dataset is not None:
            ds = Dataset(filein, 'r')
            dataset = Dataset(solar_file, 'r')
        else:
            ds = xr.open_dataset(filein)
            dataset = xr.open_dataset(solar_file)

        print("  Solar profiles...", flush=True)
        solar_limit_Nottingham = acm_solar(dataset, config.locations["Nottingham"]["lat"], config.locations["Nottingham"]["lon"])
        solar_limit_Ipswich = acm_solar(dataset, config.locations["Ipswich"]["lat"], config.locations["Ipswich"]["lon"])
        solar_limit_London = acm_solar(dataset, config.locations["London"]["lat"], config.locations["London"]["lon"])
        solar_limit_Newcastle = acm_solar(dataset, config.locations["Newcastle"]["lat"], config.locations["Newcastle"]["lon"])
        solar_limit_Manchester = acm_solar(dataset, config.locations["Manchester"]["lat"], config.locations["Manchester"]["lon"])
        solar_limit_Edinburgh = acm_solar(dataset, config.locations["Edinburgh"]["lat"], config.locations["Edinburgh"]["lon"])
        solar_limit_Portsmouth = acm_solar(dataset, config.locations["Portsmouth"]["lat"], config.locations["Portsmouth"]["lon"])
        solar_limit_Bournemouth = acm_solar(dataset, config.locations["Bournemouth"]["lat"], config.locations["Bournemouth"]["lon"])
        solar_limit_Cardiff = acm_solar(dataset, config.locations["Cardiff"]["lat"], config.locations["Cardiff"]["lon"])
        solar_limit_Birmingham = acm_solar(dataset, config.locations["Birmingham"]["lat"], config.locations["Birmingham"]["lon"])
        solar_limit_Sheffield = acm_solar(dataset, config.locations["Sheffield"]["lat"], config.locations["Sheffield"]["lon"])
        try:
            dataset.close()
        except Exception:
            pass

        print("  Onshore wind profiles...", flush=True)
        onshore_limit_Nottingham = acm_energy(ds, config.locations["Nottingham"]["lat"], config.locations["Nottingham"]["lon"])
        onshore_limit_Ipswich = acm_energy(ds, config.locations["Ipswich"]["lat"], config.locations["Ipswich"]["lon"])
        onshore_limit_London = acm_energy(ds, config.locations["London"]["lat"], config.locations["London"]["lon"])
        onshore_limit_Newcastle = acm_energy(ds, config.locations["Newcastle"]["lat"], config.locations["Newcastle"]["lon"])
        onshore_limit_Manchester = acm_energy(ds, config.locations["Manchester"]["lat"], config.locations["Manchester"]["lon"])
        onshore_limit_Edinburgh = acm_energy(ds, config.locations["Edinburgh"]["lat"], config.locations["Edinburgh"]["lon"])
        onshore_limit_Portsmouth = acm_energy(ds, config.locations["Portsmouth"]["lat"], config.locations["Portsmouth"]["lon"])
        onshore_limit_Bournemouth = acm_energy(ds, config.locations["Bournemouth"]["lat"], config.locations["Bournemouth"]["lon"])
        onshore_limit_Cardiff = acm_energy(ds, config.locations["Cardiff"]["lat"], config.locations["Cardiff"]["lon"])
        onshore_limit_Birmingham = acm_energy(ds, config.locations["Birmingham"]["lat"], config.locations["Birmingham"]["lon"])
        onshore_limit_Sheffield = acm_energy(ds, config.locations["Sheffield"]["lat"], config.locations["Sheffield"]["lon"])

        print("  Offshore wind profiles...", flush=True)
        offshore_limit1 = acm_energy(ds, config.locations["offshore1"]["lat"], config.locations["offshore1"]["lon"])
        offshore_limit2 = acm_energy(ds, config.locations["offshore2"]["lat"], config.locations["offshore2"]["lon"])
        offshore_limit3 = acm_energy(ds, config.locations["offshore3"]["lat"], config.locations["offshore3"]["lon"])
        offshore_limit4 = acm_energy(ds, config.locations["offshore4"]["lat"], config.locations["offshore4"]["lon"])
        offshore_limit5 = acm_energy(ds, config.locations["offshore5"]["lat"], config.locations["offshore5"]["lon"])
        offshore_limit6 = acm_energy(ds, config.locations["offshore6"]["lat"], config.locations["offshore6"]["lon"])
        offshore_limit7 = acm_energy(ds, config.locations["offshore7"]["lat"], config.locations["offshore7"]["lon"])
        offshore_limit8 = acm_energy(ds, config.locations["offshore8"]["lat"], config.locations["offshore8"]["lon"])
        offshore_limit9 = acm_energy(ds, config.locations["offshore9"]["lat"], config.locations["offshore9"]["lon"])
        offshore_limit10 = acm_energy(ds, config.locations["offshore10"]["lat"], config.locations["offshore10"]["lon"])
        offshore_limit11 = acm_energy(ds, config.locations["offshore11"]["lat"], config.locations["offshore11"]["lon"])
        offshore_limit12 = acm_energy(ds, config.locations["offshore12"]["lat"], config.locations["offshore12"]["lon"])
        offshore_limit13 = acm_energy(ds, config.locations["offshore13"]["lat"], config.locations["offshore13"]["lon"])
        offshore_limit14 = acm_energy(ds, config.locations["offshore14"]["lat"], config.locations["offshore14"]["lon"])
        offshore_limit15 = acm_energy(ds, config.locations["offshore15"]["lat"], config.locations["offshore15"]["lon"])
        offshore_limit16 = acm_energy(ds, config.locations["offshore16"]["lat"], config.locations["offshore16"]["lon"])
        offshore_limit17 = acm_energy(ds, config.locations["offshore17"]["lat"], config.locations["offshore17"]["lon"])
        offshore_limit18 = acm_energy(ds, config.locations["offshore18"]["lat"], config.locations["offshore18"]["lon"])
        offshore_limit19 = acm_energy(ds, config.locations["offshore19"]["lat"], config.locations["offshore19"]["lon"])
        offshore_limit20 = acm_energy(ds, config.locations["offshore20"]["lat"], config.locations["offshore20"]["lon"])
        offshore_limit21 = acm_energy(ds, config.locations["offshore21"]["lat"], config.locations["offshore21"]["lon"])
        try:
            ds.close()
        except Exception:
            pass

        _WEATHER_LIMIT_CACHE = (
            solar_limit_Nottingham, solar_limit_Ipswich, solar_limit_London, solar_limit_Newcastle,
            solar_limit_Manchester, solar_limit_Edinburgh, solar_limit_Portsmouth, solar_limit_Bournemouth,
            solar_limit_Cardiff, solar_limit_Birmingham, solar_limit_Sheffield,
            onshore_limit_Nottingham, onshore_limit_Ipswich, onshore_limit_London, onshore_limit_Newcastle,
            onshore_limit_Manchester, onshore_limit_Edinburgh, onshore_limit_Portsmouth, onshore_limit_Bournemouth,
            onshore_limit_Cardiff, onshore_limit_Birmingham, onshore_limit_Sheffield,
            offshore_limit1, offshore_limit2, offshore_limit3, offshore_limit4, offshore_limit5, offshore_limit6,
            offshore_limit7, offshore_limit8, offshore_limit9, offshore_limit10, offshore_limit11, offshore_limit12,
            offshore_limit13, offshore_limit14, offshore_limit15, offshore_limit16, offshore_limit17, offshore_limit18,
            offshore_limit19, offshore_limit20, offshore_limit21,
        )
        print("Weather profiles ready and cached for this run.", flush=True)
    else:
        print("Using cached weather profiles.", flush=True)

    (
        solar_limit_Nottingham, solar_limit_Ipswich, solar_limit_London, solar_limit_Newcastle,
        solar_limit_Manchester, solar_limit_Edinburgh, solar_limit_Portsmouth, solar_limit_Bournemouth,
        solar_limit_Cardiff, solar_limit_Birmingham, solar_limit_Sheffield,
        onshore_limit_Nottingham, onshore_limit_Ipswich, onshore_limit_London, onshore_limit_Newcastle,
        onshore_limit_Manchester, onshore_limit_Edinburgh, onshore_limit_Portsmouth, onshore_limit_Bournemouth,
        onshore_limit_Cardiff, onshore_limit_Birmingham, onshore_limit_Sheffield,
        offshore_limit1, offshore_limit2, offshore_limit3, offshore_limit4, offshore_limit5, offshore_limit6,
        offshore_limit7, offshore_limit8, offshore_limit9, offshore_limit10, offshore_limit11, offshore_limit12,
        offshore_limit13, offshore_limit14, offshore_limit15, offshore_limit16, offshore_limit17, offshore_limit18,
        offshore_limit19, offshore_limit20, offshore_limit21,
    ) = _WEATHER_LIMIT_CACHE

    LIMIT1 = IterLimit(solar_limit_Nottingham)
    LIMIT2 = IterLimit(solar_limit_Ipswich)
    LIMIT3 = IterLimit(solar_limit_London)
    LIMIT4 = IterLimit(solar_limit_Newcastle)
    LIMIT5 = IterLimit(solar_limit_Manchester)
    LIMIT6 = IterLimit(solar_limit_Edinburgh)
    LIMIT7 = IterLimit(solar_limit_Portsmouth)
    LIMIT8 = IterLimit(solar_limit_Bournemouth)
    LIMIT9 = IterLimit(solar_limit_Cardiff)
    LIMIT10 = IterLimit(solar_limit_Birmingham)
    LIMIT11 = IterLimit(solar_limit_Sheffield)
    LIMIT12 = IterLimit(onshore_limit_Nottingham)
    LIMIT13 = IterLimit(onshore_limit_Ipswich)
    LIMIT14 = IterLimit(onshore_limit_London)
    LIMIT15 = IterLimit(onshore_limit_Newcastle)
    LIMIT16 = IterLimit(onshore_limit_Manchester)
    LIMIT17 = IterLimit(onshore_limit_Edinburgh)
    LIMIT18 = IterLimit(onshore_limit_Portsmouth)
    LIMIT19 = IterLimit(onshore_limit_Bournemouth)
    LIMIT20 = IterLimit(onshore_limit_Cardiff)
    LIMIT21 = IterLimit(onshore_limit_Birmingham)
    LIMIT22 = IterLimit(onshore_limit_Sheffield)
    LIMIT23 = IterLimit(offshore_limit1)
    LIMIT24 = IterLimit(offshore_limit2)
    LIMIT25 = IterLimit(offshore_limit3)
    LIMIT26 = IterLimit(offshore_limit4)
    LIMIT27 = IterLimit(offshore_limit5)
    LIMIT28 = IterLimit(offshore_limit6)
    LIMIT29 = IterLimit(offshore_limit7)
    LIMIT30 = IterLimit(offshore_limit8)
    LIMIT31 = IterLimit(offshore_limit9)
    LIMIT32 = IterLimit(offshore_limit10)
    LIMIT33 = IterLimit(offshore_limit11)
    LIMIT34 = IterLimit(offshore_limit12)
    LIMIT35 = IterLimit(offshore_limit13)
    LIMIT36 = IterLimit(offshore_limit14)
    LIMIT37 = IterLimit(offshore_limit15)
    LIMIT38 = IterLimit(offshore_limit16)
    LIMIT39 = IterLimit(offshore_limit17)
    LIMIT40 = IterLimit(offshore_limit18)
    LIMIT41 = IterLimit(offshore_limit19)
    LIMIT42 = IterLimit(offshore_limit20)
    LIMIT43 = IterLimit(offshore_limit21)

    # Find the generator objects by name to assign capacity updates in the loop
    # This is a bit brittle but necessary given the original structure.
    solar_Nottingham = next((g for g in generators if g.name == 'solar_Nottingham'), None)
    solar_Ipswich = next((g for g in generators if g.name == 'solar_Ipswich'), None)
    solar_London = next((g for g in generators if g.name == 'solar_London'), None)
    solar_Newcastle = next((g for g in generators if g.name == 'solar_Newcastle'), None)
    solar_Manchester = next((g for g in generators if g.name == 'solar_Manchester'), None)
    solar_Edinburgh = next((g for g in generators if g.name == 'solar_Edinburgh'), None)
    solar_Portsmouth = next((g for g in generators if g.name == 'solar_Portsmouth'), None)
    solar_Bournemouth = next((g for g in generators if g.name == 'solar_Bournemouth'), None)
    solar_Cardiff = next((g for g in generators if g.name == 'solar_Cardiff'), None)
    solar_Birmingham = next((g for g in generators if g.name == 'solar_Birmingham'), None)
    solar_Sheffield = next((g for g in generators if g.name == 'solar_Sheffield'), None)

    onshore_Nottingham = next((g for g in generators if g.name == 'onshore_Nottingham'), None)
    onshore_Ipswich = next((g for g in generators if g.name == 'onshore_Ipswich'), None)
    onshore_London = next((g for g in generators if g.name == 'onshore_London'), None)
    onshore_Newcastle = next((g for g in generators if g.name == 'onshore_Newcastle'), None)
    onshore_Manchester = next((g for g in generators if g.name == 'onshore_Manchester'), None)
    onshore_Edinburgh = next((g for g in generators if g.name == 'onshore_Edinburgh'), None)
    onshore_Portsmouth = next((g for g in generators if g.name == 'onshore_Portsmouth'), None)
    onshore_Bournemouth = next((g for g in generators if g.name == 'onshore_Bournemouth'), None)
    onshore_Cardiff = next((g for g in generators if g.name == 'onshore_Cardiff'), None)
    onshore_Birmingham = next((g for g in generators if g.name == 'onshore_Birmingham'), None)
    onshore_Sheffield = next((g for g in generators if g.name == 'onshore_Sheffield'), None)

    offshore1 = next((g for g in generators if g.name == 'offshore1'), None)
    offshore2 = next((g for g in generators if g.name == 'offshore2'), None)
    offshore3 = next((g for g in generators if g.name == 'offshore3'), None)
    offshore4 = next((g for g in generators if g.name == 'offshore4'), None)
    offshore5 = next((g for g in generators if g.name == 'offshore5'), None)
    offshore6 = next((g for g in generators if g.name == 'offshore6'), None)
    offshore7 = next((g for g in generators if g.name == 'offshore7'), None)
    offshore8 = next((g for g in generators if g.name == 'offshore8'), None)
    offshore9 = next((g for g in generators if g.name == 'offshore9'), None)
    offshore10 = next((g for g in generators if g.name == 'offshore10'), None)
    offshore11 = next((g for g in generators if g.name == 'offshore11'), None)
    offshore12 = next((g for g in generators if g.name == 'offshore12'), None)
    offshore13 = next((g for g in generators if g.name == 'offshore13'), None)
    offshore14 = next((g for g in generators if g.name == 'offshore14'), None)
    offshore15 = next((g for g in generators if g.name == 'offshore15'), None)
    offshore16 = next((g for g in generators if g.name == 'offshore16'), None)
    offshore17 = next((g for g in generators if g.name == 'offshore17'), None)
    offshore18 = next((g for g in generators if g.name == 'offshore18'), None)
    offshore19 = next((g for g in generators if g.name == 'offshore19'), None)
    offshore20 = next((g for g in generators if g.name == 'offshore20'), None)
    offshore21 = next((g for g in generators if g.name == 'offshore21'), None)

    # Same for connections
    Interconnect_France = next((c for c in connections if c.name == 'Interconnect_France'), None)
    Interconnect_Netherland = next((c for c in connections if c.name == 'Interconnect_Netherland'), None)
    Interconnect_Ireland = next((c for c in connections if c.name == 'Interconnect_Ireland'), None)
    Interconnect_Norway = next((c for c in connections if c.name == 'Interconnect_Norway'), None)
    Interconnect_Beligum = next((c for c in connections if c.name == 'Interconnect_Beligum'), None)

    transfer_constraint_france = np.array(pd.read_csv(config.file_paths["france_profile"])).flatten()
    external_price_france = pd.to_numeric(pd.read_csv(config.file_paths["france_price"], header=None).iloc[:, 0], errors='coerce').fillna(0).values
    transfer_constraint_beligum = np.array(pd.read_csv(config.file_paths["belgium_profile"])).flatten()
    external_price_beligum = pd.to_numeric(pd.read_csv(config.file_paths["belgium_price"], header=None).iloc[:, 0], errors='coerce').fillna(0).values
    transfer_constraint_netherland = np.array(pd.read_csv(config.file_paths["netherlands_profile"])).flatten()
    external_price_netherland = pd.to_numeric(pd.read_csv(config.file_paths["netherlands_price"], header=None).iloc[:, 0], errors='coerce').fillna(0).values
    transfer_constraint_norway = np.array(pd.read_csv(config.file_paths["norway_profile"])).flatten()
    external_price_norway = pd.to_numeric(pd.read_csv(config.file_paths["norway_price"], header=None).iloc[:, 0], errors='coerce').fillna(0).values
    transfer_constraint_Ireland = np.array(pd.read_csv(config.file_paths["ireland_profile"])).flatten()
    external_price_Ireland = pd.to_numeric(pd.read_csv(config.file_paths["ireland_price"], header=None).iloc[:, 0], errors='coerce').fillna(0).values

    data1 = IterLimit_new(transfer_constraint_france)
    data2 = IterLimit_new(external_price_france)
    data3 = IterLimit_new(transfer_constraint_beligum)
    data4 = IterLimit_new(external_price_beligum)
    data5 = IterLimit_new(transfer_constraint_netherland)
    data6 = IterLimit_new(external_price_netherland)
    data7 = IterLimit_new(transfer_constraint_norway)
    data8 = IterLimit_new(external_price_norway)
    data9 = IterLimit_new(transfer_constraint_Ireland)
    data10 = IterLimit_new(external_price_Ireland)

    for period in range(periods):
        # Memory cleanup every 100 periods to prevent MemoryError
        if period % 100 == 0:
            cleanup_accumulating_lists(total_renew_capacity, renew_capacity, gen_list_composition, 
                                 storage_pool_composition)
            # Periodic GC only; datasets already closed after limits computed
            pass
        
        solar_Nottingham.capacity_limit = (piecewise_limit(next(LIMIT1))) * solar_Nottingham.capacity_multiplier / 3600000
        solar_Ipswich.capacity_limit = (piecewise_limit(next(LIMIT2))) * solar_Ipswich.capacity_multiplier / 3600000
        solar_London.capacity_limit = (piecewise_limit(next(LIMIT3))) * solar_London.capacity_multiplier / 3600000
        solar_Newcastle.capacity_limit = (piecewise_limit(next(LIMIT4))) * solar_Newcastle.capacity_multiplier / 3600000
        solar_Manchester.capacity_limit = (piecewise_limit(next(LIMIT5))) * solar_Manchester.capacity_multiplier / 3600000
        solar_Edinburgh.capacity_limit = (piecewise_limit(next(LIMIT6))) * solar_Edinburgh.capacity_multiplier / 3600000
        solar_Portsmouth.capacity_limit = (piecewise_limit(next(LIMIT7))) * solar_Portsmouth.capacity_multiplier / 3600000
        solar_Bournemouth.capacity_limit = (piecewise_limit(next(LIMIT8))) * solar_Bournemouth.capacity_multiplier / 3600000
        solar_Cardiff.capacity_limit = (piecewise_limit(next(LIMIT9))) * solar_Cardiff.capacity_multiplier / 3600000
        solar_Birmingham.capacity_limit = (piecewise_limit(next(LIMIT10))) * solar_Birmingham.capacity_multiplier / 3600000
        solar_Sheffield.capacity_limit = (piecewise_limit(next(LIMIT11))) * solar_Sheffield.capacity_multiplier / 3600000

        onshore_speed_Nottingham = next(LIMIT12) ** 0.5
        onshore_speed_Ipswich = next(LIMIT13) ** 0.5
        onshore_speed_London = next(LIMIT14) ** 0.5
        onshore_speed_Newcastle = next(LIMIT15) ** 0.5
        onshore_speed_Manchester = next(LIMIT16) ** 0.5
        onshore_speed_Edinburgh = next(LIMIT17) ** 0.5
        onshore_speed_Portsmouth = next(LIMIT18) ** 0.5
        onshore_speed_Bournemouth = next(LIMIT19) ** 0.5
        onshore_speed_Cardiff = next(LIMIT20) ** 0.5
        onshore_speed_Birmingham = next(LIMIT21) ** 0.5
        onshore_speed_Sheffield = next(LIMIT22) ** 0.5

        onshore_Nottingham.capacity_limit = onshore_Nottingham.capacity_multiplier * piecewise_limit5((onshore_speed_Nottingham))
        onshore_Ipswich.capacity_limit = onshore_Ipswich.capacity_multiplier * (piecewise_limit5(onshore_speed_Ipswich))
        onshore_London.capacity_limit = onshore_London.capacity_multiplier * (piecewise_limit5(onshore_speed_London))
        onshore_Newcastle.capacity_limit = onshore_Newcastle.capacity_multiplier * (piecewise_limit5(onshore_speed_Newcastle))
        onshore_Manchester.capacity_limit = onshore_Manchester.capacity_multiplier * (piecewise_limit5(onshore_speed_Manchester))
        onshore_Edinburgh.capacity_limit = onshore_Edinburgh.capacity_multiplier * piecewise_limit5((onshore_speed_Edinburgh))
        onshore_Portsmouth.capacity_limit = onshore_Portsmouth.capacity_multiplier * (piecewise_limit5(onshore_speed_Portsmouth))
        onshore_Bournemouth.capacity_limit = onshore_Bournemouth.capacity_multiplier * (piecewise_limit5(onshore_speed_Bournemouth))
        onshore_Cardiff.capacity_limit = onshore_Cardiff.capacity_multiplier * (piecewise_limit5(onshore_speed_Cardiff))
        onshore_Birmingham.capacity_limit = onshore_Birmingham.capacity_multiplier * (piecewise_limit5(onshore_speed_Birmingham))
        onshore_Sheffield.capacity_limit = onshore_Sheffield.capacity_multiplier * piecewise_limit5((onshore_speed_Sheffield))

        offshore_speed1 = next(LIMIT23) ** 0.5
        offshore_speed2 = next(LIMIT24) ** 0.5
        offshore_speed3 = next(LIMIT25) ** 0.5
        offshore_speed4 = next(LIMIT26) ** 0.5
        offshore_speed5 = next(LIMIT27) ** 0.5
        offshore_speed6 = next(LIMIT28) ** 0.5
        offshore_speed7 = next(LIMIT29) ** 0.5
        offshore_speed8 = next(LIMIT30) ** 0.5
        offshore_speed9 = next(LIMIT31) ** 0.5
        offshore_speed10 = next(LIMIT32) ** 0.5
        offshore_speed11 = next(LIMIT33) ** 0.5
        offshore_speed12 = next(LIMIT34) ** 0.5
        offshore_speed13 = next(LIMIT35) ** 0.5
        offshore_speed14 = next(LIMIT36) ** 0.5
        offshore_speed15 = next(LIMIT37) ** 0.5
        offshore_speed16 = next(LIMIT38) ** 0.5
        offshore_speed17 = next(LIMIT39) ** 0.5
        offshore_speed18 = next(LIMIT40) ** 0.5
        offshore_speed19 = next(LIMIT41) ** 0.5
        offshore_speed20 = next(LIMIT42) ** 0.5
        offshore_speed21 = next(LIMIT43) ** 0.5

        # piecewise_limit is a function for simple wind generator,how many 10MW wind turbines
        offshore1.capacity_limit = offshore1.capacity_multiplier * piecewise_limit1((offshore_speed1))
        offshore2.capacity_limit = offshore2.capacity_multiplier * (piecewise_limit2(offshore_speed2))
        offshore3.capacity_limit = offshore3.capacity_multiplier * (piecewise_limit3(offshore_speed3))
        offshore4.capacity_limit = offshore4.capacity_multiplier * (piecewise_limit4(offshore_speed4))
        offshore5.capacity_limit = offshore5.capacity_multiplier * (piecewise_limit1(offshore_speed5))
        offshore6.capacity_limit = offshore6.capacity_multiplier * piecewise_limit1((offshore_speed6))
        offshore7.capacity_limit = offshore7.capacity_multiplier * (piecewise_limit2(offshore_speed7))
        offshore8.capacity_limit = offshore8.capacity_multiplier * (piecewise_limit3(offshore_speed8))
        offshore9.capacity_limit = offshore9.capacity_multiplier * (piecewise_limit4(offshore_speed9))
        offshore10.capacity_limit = offshore10.capacity_multiplier * (piecewise_limit1(offshore_speed10))
        offshore11.capacity_limit = offshore11.capacity_multiplier * piecewise_limit1((offshore_speed11))
        offshore12.capacity_limit = offshore12.capacity_multiplier * (piecewise_limit2(offshore_speed12))
        offshore13.capacity_limit = offshore13.capacity_multiplier * (piecewise_limit3(offshore_speed13))
        offshore14.capacity_limit = offshore14.capacity_multiplier * (piecewise_limit4(offshore_speed14))
        offshore15.capacity_limit = offshore15.capacity_multiplier * (piecewise_limit1(offshore_speed15))
        offshore16.capacity_limit = offshore16.capacity_multiplier * piecewise_limit1((offshore_speed16))
        offshore17.capacity_limit = offshore17.capacity_multiplier * (piecewise_limit2(offshore_speed17))
        offshore18.capacity_limit = offshore18.capacity_multiplier * (piecewise_limit3(offshore_speed18))
        offshore19.capacity_limit = offshore19.capacity_multiplier * (piecewise_limit4(offshore_speed19))
        offshore20.capacity_limit = offshore20.capacity_multiplier * (piecewise_limit3(offshore_speed20))
        offshore21.capacity_limit = offshore21.capacity_multiplier * (piecewise_limit4(offshore_speed21))

        Interconnect_France.transfer_constraint = next(data1)
        Interconnect_France.external_price = next(data2)
        Interconnect_Netherland.transfer_constraint = next(data3)
        Interconnect_Netherland.external_price = next(data4)
        Interconnect_Ireland.transfer_constraint = next(data5)
        Interconnect_Ireland.external_price = next(data6)
        Interconnect_Norway.transfer_constraint =next(data7)
        Interconnect_Norway.external_price = next(data8)
        Interconnect_Beligum.transfer_constraint = next(data9)
        Interconnect_Beligum.external_price = next(data10)

        # chosen generation in wholesale，cost from stored energy and two storage pool variable for plotting
        # accepted_bids use for balancing, other three for plotting
        accepted_bids, total_storage_fee_ahead, per_storage_pool, merge_storage_pool, storage_pool_composition, \
        last_gen_energy, excess_energy, ahead_renewables, ahead_other, ahead_traditional, gen_list, ahead_nuclear,\
            gen_list_name, bids, income_dict,excess_energy_list,renewable_hy_list = ahead_market_bidding(
            generators, batterys,
            forecast_demands[period],
            period, accepted_bids, ahead_renewables, ahead_other, ahead_traditional, ahead_nuclear, bidding_factor)
        for key, value in income_dict.items():
            if key in total_income_dict:
                total_income_dict[key] += value
            else:
                total_income_dict[key] = value
        # print(accepted_bids)
        # compare forecast and read demand
        real_demand = real_demands[period]

        renewable_hy_dict[period] = renewable_hy_list
        income_dict_balance = {}
        energy_deficit = 0
        
        # Memory management: Clear lists periodically to prevent MemoryError
        if period % 100 == 0:  # Every 100 periods
            import gc
            gc.collect()
            # Clear accumulated lists to prevent memory bloat
            if len(total_renew_capacity) > 1000:
                total_renew_capacity.clear()
            if len(renew_capacity) > 1000:
                renew_capacity.clear()
        
        for item in generators:
            if type(item) == ExpensiverenewableGenerator:
                total_renew_capacity.append(item.capacity_limit)
        for item in generators:
            if item.name == 'onshore_Edinburgh':
                renew_capacity.append(item.capacity_limit)
        if excess_energy_list:
            excess_energy_dict[period] = excess_energy_list
        else:
            excess_energy_dict[period] = 0
        if real_demand < forecast_demands[period]:
            # return to curtailment fee and charged amount
            curtailed_fee, store_energy, real_list, storage_pool_composition_after, gen_list, curtailed_energy, \
            excess_energy, sold_fee, green_hy, energy_cell_period,curtailed_energy_list = \
                curtailment_market_bidding(period, real_demand, forecast_demands[period], accepted_bids,
                                           last_gen_energy, excess_energy, gen_list, connections, electrolyzer, batterys)
            #print(sold_fee)
            # curtailment fee is a list, add them upu
            total_fee = sum(curtailed_fee)
            curtailed_energy_dict[period] = curtailed_energy_list
            # add curtailment fee in this period to total
            curtailment_fees.append(total_fee)
            curtailed_electricity.append(curtailed_energy)
            excess_electricity.append(excess_energy)
            # no balancing fee, add 0
            balancing_fees.append(0)
            # add storage to overall storage
            store_electricity.append(store_energy)
            sold_fees.append(sum(sold_fee))
            purchase_fees.append(0)
            total_green_hy.append(green_hy)
            gen=[]
            for item in gen_list:
                if item[1] != 0:
                    gen.append(item[0])
            #print('gen', gen)
            #print('generators',generators)
            for item in generators:
                if item not in gen:
                    item.set_real_gen_energy(0)
            excess_energy_final_dict[period] = excess_energy
            blackout_periods.append(0)  # No blackout in curtailment market
        else:
            # ruturn to continue bidding
            balancing_fee, total_storage_fee_balance, real_list, store_energy, storage_pool_composition_after, \
            balance_renewables, balance_other, balance_traditional, gen_list, balance_nuclear, excess_energy, sold_fee, \
            bought_fee, green_hy, energy_cell_period, income_dict_balance, energy_deficit = balancing_market_bidding(generators, period, real_demand, forecast_demands[period],
                                                  accepted_bids, excess_energy, balance_renewables, balance_other,
                                                  balance_traditional, gen_list, balance_nuclear, connections,
                                                  gen_list_name, bids, electrolyzer,excess_energy_list, batterys, bidding_factor)
            blackout_periods.append(energy_deficit)  # Track energy deficit for this period
            for key, value in income_dict_balance.items():
                if key in total_income_dict:
                    total_income_dict[key] += value
                else:
                    total_income_dict[key] = value
            # add continue bidding in this period to total balancing fee list
            balancing_fees.append(sum(balancing_fee))
            curtailed_energy_dict[period] = 0
        #    print(sold_fee)
            # no curtailment, curtailment is 0
            curtailment_fees.append(0)
            curtailed_electricity.append(0)
            excess_electricity.append(excess_energy)
            # no storage, storage is 0
            store_electricity.append(store_energy)
            sold_fees.append(sum(sold_fee))
            purchase_fees.append(sum(bought_fee))
            total_green_hy.append(green_hy)
            gen = []
            for item in gen_list:
                if item[1] != 0:
                    gen.append(item[0])
            #print('gen',gen)
            #print('generators', generators)
            for item in generators:
                if item not in gen:
                    item.set_real_gen_energy(0)
            excess_energy_final_dict[period] = excess_energy
        filtered_list = [sublist for sublist in gen_list if sublist[1] != 0]
        result_dict = {}
        for item in filtered_list:
            key = item[0]
            value = item[1]
            if key in result_dict:
                result_dict[key] += value
            else:
                result_dict[key] = value
        result_list = [[key, value] for key, value in result_dict.items()]
        gen_list_composition.append(result_list)
        # add storage fee to overall storage fee
        storage_fees.append(total_storage_fee_ahead + total_storage_fee_balance)
        # oVeraall cost=storage cost+generation cost+curtailment cost +balancing cost
        gen_fees.append(sum([item1*item2 for _, item1, item2, _ in accepted_bids]))
        total_gen_cost = gen_fees[period]\
                         + storage_fees[period] + curtailment_fees[period] + balancing_fees[period]
        total_annual_cost.append(total_gen_cost)
        total_annual_demand.append(real_demand)
        if real_demand > 0:
            avg_gen_fees.append(gen_fees[period]/real_demand)
            avg_curtailment_fees.append(curtailment_fees[period]/real_demand)
            avg_balancing_fees.append(balancing_fees[period] / real_demand)
            avg_storage_fees.append(storage_fees[period] / real_demand)
            ahead_renewables[period] = ahead_renewables[period] / real_demand
            ahead_other[period] = ahead_other[period] / real_demand
            ahead_traditional[period] = ahead_traditional[period] / real_demand
            ahead_nuclear[period] = ahead_nuclear[period]/ real_demand
            balance_renewables[period] = balance_renewables[period] / real_demand
            balance_other[period] = balance_other[period] / real_demand
            balance_traditional[period] = balance_traditional[period] / real_demand
            balance_nuclear[period] = balance_nuclear[period] / real_demand
            avg_price = total_gen_cost / real_demand
        else: # Avoid division by zero
            avg_gen_fees.append(0)
            avg_curtailment_fees.append(0)
            avg_balancing_fees.append(0)
            avg_storage_fees.append(0)
            avg_price = 0

        total_annual_energycell.append(energy_cell_period)
        total_gen_cost = sum([item1*item2 for _, item1, item2, _ in accepted_bids])\
                         + storage_fees[period] + curtailment_fees[period] + balancing_fees[period]

        if trace_enabled:
            for accepted_asset, accepted_price, accepted_energy, accepted_cost in accepted_bids:
                market_writer.writerow({
                    "scenario": trace_scenario,
                    "year": trace_year,
                    "period": period,
                    "market_stage": "ahead_accepted",
                    "asset_name": getattr(accepted_asset, "name", str(accepted_asset)),
                    "accepted_energy_mwh": accepted_energy,
                    "accepted_price_gbp_per_mwh": accepted_price,
                    "bid_cost_or_curtail_cost": accepted_cost,
                    "forecast_demand_mwh": forecast_demands[period],
                    "real_demand_mwh": real_demand,
                    "period_total_gen_cost_gbp": total_gen_cost,
                    "storage_fee_gbp": storage_fees[period],
                    "curtailment_fee_gbp": curtailment_fees[period],
                    "balancing_fee_gbp": balancing_fees[period],
                    "sold_fee_gbp": sold_fees[period],
                    "purchase_fee_gbp": purchase_fees[period],
                    "energy_deficit_mwh": energy_deficit,
                    "excess_energy_mwh": excess_energy,
                })
            for dispatch_asset, dispatch_energy in real_list:
                market_writer.writerow({
                    "scenario": trace_scenario,
                    "year": trace_year,
                    "period": period,
                    "market_stage": "real_dispatch",
                    "asset_name": getattr(dispatch_asset, "name", str(dispatch_asset)),
                    "accepted_energy_mwh": dispatch_energy,
                    "accepted_price_gbp_per_mwh": "",
                    "bid_cost_or_curtail_cost": "",
                    "forecast_demand_mwh": forecast_demands[period],
                    "real_demand_mwh": real_demand,
                    "period_total_gen_cost_gbp": total_gen_cost,
                    "storage_fee_gbp": storage_fees[period],
                    "curtailment_fee_gbp": curtailment_fees[period],
                    "balancing_fee_gbp": balancing_fees[period],
                    "sold_fee_gbp": sold_fees[period],
                    "purchase_fee_gbp": purchase_fees[period],
                    "energy_deficit_mwh": energy_deficit,
                    "excess_energy_mwh": excess_energy,
                })
            for agent_name in agent_names_for_trace:
                ahead_income = income_dict.get(agent_name, 0.0)
                balancing_income = income_dict_balance.get(agent_name, 0.0)
                income_writer.writerow({
                    "scenario": trace_scenario,
                    "year": trace_year,
                    "period": period,
                    "asset_name": agent_name,
                    "ahead_income_gbp": ahead_income,
                    "balancing_income_gbp": balancing_income,
                    "total_income_gbp": ahead_income + balancing_income,
                })
            if period % 100 == 0:
                market_trace_file.flush()
                income_trace_file.flush()

        #print(sum([item1*item2 for _, item1, item2, _ in accepted_bids]))
        #print(storage_fees[period])
        #print(curtailment_fees[period])
        #print(balancing_fees[period])
        # average=total/real demand

        #print(storage_pool_composition)
        #print(storage_pool_composition_after)
        #print('1')
        usage_storage = subtract_elements(storage_pools_composition, storage_pool_composition_after)
        # plotting
        generation_costs.append(total_gen_cost)
        storage_pool.append(per_storage_pool)
        total_storage_pool.append(merge_storage_pool)
        avg_electricity_prices.append(avg_price)
        storage_pools_composition.append(storage_pool_composition)
        usage_storage_pool_composition.append(usage_storage)
        total_gen_ems = 0
        for item in gen_list:
            total_gen_ems += item[0].carbon_emission
        total_gen_ems += electrolyzer.body_emission
        total_gen_intensity = 0
        for item in gen_list:
            if hasattr(item[0], 'carbon_intensity'):
                total_gen_intensity += item[0].carbon_intensity * item[1]
        carbon_emission.append((total_gen_ems + total_gen_intensity))
        
        # Collect data for consumption plot
        flexible_demand_list.append(electrolyzer.real_energy)
        interconnector_export = sum(c.sold_energy for c in connections)
        interconnector_exports_list.append(interconnector_export)

        for item in generators:
            if item.name == 'CCGT':
                traditional_gen['ccgt'] += item.real_gen_energy
            elif item.name == 'OCGT':
                traditional_gen['ocgt'] += item.real_gen_energy
            elif item.name == 'bio_and_waste':
                traditional_gen['biomass'] += item.real_gen_energy
        if period == 248:
                if DEBUG_MARKET_STDOUT:
                    print(gen_list_name)

    # Final memory cleanup before returning results
    cleanup_accumulating_lists(total_renew_capacity, renew_capacity, gen_list_composition, 
                                 storage_pool_composition)
    if trace_enabled:
        market_trace_file.flush()
        income_trace_file.flush()
        market_trace_file.close()
        income_trace_file.close()
    
    return (avg_electricity_prices, storage_fees, store_electricity, generation_costs, storage_pool, total_storage_pool, \
           storage_pools_composition, usage_storage_pool_composition, avg_gen_fees, avg_curtailment_fees, \
           avg_balancing_fees, avg_storage_fees, ahead_renewables, ahead_other, ahead_traditional, ahead_nuclear, \
           balance_renewables, balance_other, balance_traditional, balance_nuclear, gen_list_composition, \
           curtailed_electricity, excess_electricity, total_annual_cost, total_annual_demand, carbon_emission, \
           sold_fees, purchase_fees, traditional_gen, total_green_hy,total_renew_capacity, renew_capacity,\
           total_annual_energycell, total_income_dict,excess_energy_dict,excess_energy_final_dict,
            curtailed_energy_dict,renewable_hy_dict, flexible_demand_list, interconnector_exports_list, blackout_periods)



# 生成颜色函数
def generate_colors(num_colors):
    colors = []
    random.seed(2)
    while len(colors) < num_colors:
        r = random.random()
        g = random.random()
        b = random.random()
        color = (r, g, b)
        if color not in colors:
            colors.append(color)
    return colors


def plot_results(avg_electricity_prices, periods):
    plt.figure(figsize=(12, 4))
    sns.lineplot(x=range(periods), y=avg_electricity_prices)
    plt.xlabel('periods')
    plt.ylabel('avg_electricity_prices')
    plt.show()


def storage_composition_show(storage_pools_composition, batterys):
    periods = len(storage_pools_composition)
    labels = [battery.name for battery in batterys]
    data = {label: np.zeros(periods, dtype=np.float32) for label in labels}

    for i, period_data in enumerate(storage_pools_composition):
        for comp in period_data:
            battery_name = comp[0].name
            if battery_name in data:
                data[battery_name][i] += comp[1]

    x = np.arange(periods)
    fig, ax = plt.subplots(figsize=(16, 9))
    
    stack = ax.stackplot(x, data.values(), labels=data.keys(), alpha=0.8)
    ax.legend(loc='upper left')
    ax.set_title('Storage Composition Over Time')
    ax.set_xlabel('Period')
    ax.set_ylabel('Energy (MWh)')
    plt.show()

def gen_list_show(gen_list_composition, batterys, generators):
    periods = len(gen_list_composition)
    
    source_names = [gen.name for gen in generators] + [bat.name for bat in batterys]
    data = {name: np.zeros(periods, dtype=np.float32) for name in source_names}

    for i, period_data in enumerate(gen_list_composition):
        for source, value in period_data:
            if source.name in data:
                data[source.name][i] += value

    x = np.arange(periods)
    fig, ax = plt.subplots(figsize=(16, 9))
    
    ax.stackplot(x, data.values(), labels=data.keys(), alpha=0.8)
    ax.legend(loc='upper left')
    ax.set_title('Generation Composition Over Time')
    ax.set_xlabel('Period')
    ax.set_ylabel('Energy (MWh)')
    plt.show()

def plot_generation_share(gen_list_composition, batterys, generators, connections, colors=None):
    periods = len(gen_list_composition)
    
    generation_data = {
        'CCGT': np.zeros(periods, dtype=np.float32), 'OCGT': np.zeros(periods, dtype=np.float32), 'Nuclear': np.zeros(periods, dtype=np.float32),
        'Biomass': np.zeros(periods, dtype=np.float32), 'Solar': np.zeros(periods, dtype=np.float32), 'Onshore Wind': np.zeros(periods, dtype=np.float32),
        'Offshore Wind': np.zeros(periods, dtype=np.float32), 'Battery': np.zeros(periods, dtype=np.float32), 'Pumped Hydro': np.zeros(periods, dtype=np.float32),
        'Interconnector': np.zeros(periods, dtype=np.float32)
    }

    # This pre-processing is much more efficient than iterating inside the plotting function
    for period, snapshot in enumerate(gen_list_composition):
        for gen, energy in snapshot:
            name = gen.name
            if 'CCGT' in name: generation_data['CCGT'][period] += energy
            elif 'OCGT' in name: generation_data['OCGT'][period] += energy
            elif 'Nuclear' in name: generation_data['Nuclear'][period] += energy
            elif 'bio_and_waste' in name: generation_data['Biomass'][period] += energy
            elif 'solar' in name: generation_data['Solar'][period] += energy
            elif 'onshore' in name: generation_data['Onshore Wind'][period] += energy
            elif 'offshore' in name: generation_data['Offshore Wind'][period] += energy
            elif any(bat.name in name for bat in batterys): generation_data['Battery'][period] += energy
            elif 'pumpedhydro' in name: generation_data['Pumped Hydro'][period] += energy
            elif any(conn.name in name for conn in connections): generation_data['Interconnector'][period] += energy
            
    x = np.arange(periods)
    fig, ax = plt.subplots(figsize=(16, 9))

    ax.stackplot(x, generation_data.values(), labels=generation_data.keys(), alpha=0.8)
    ax.legend(loc='upper left')
    ax.set_title('Generation Share Over Time')
    ax.set_xlabel('Period')
    ax.set_ylabel('Energy (MWh)')
    plt.show()

def plot_consumption_share(real_demands, flexible_demand, interconnector_exports, periods):
    """
    Plots the demand and exports as a stacked area chart.
    """
    x = np.arange(periods)
    fig, ax = plt.subplots(figsize=(16, 9))

    # Convert lists to numpy arrays
    real_demands = np.array(real_demands, dtype=np.float32)
    flexible_demand = np.array(flexible_demand, dtype=np.float32)
    interconnector_exports = np.array(interconnector_exports, dtype=np.float32)
    
    # Data for stackplot
    y = np.vstack([real_demands, flexible_demand, interconnector_exports])
    
    # Labels for each area
    labels = ['Realtime Demand', 'Flexible Demand', 'Interconnector Exports']
    
    # Colors for each area
    colors = ['blue', 'lightgreen', 'salmon']

    ax.stackplot(x, y, labels=labels, colors=colors, alpha=0.8)

    ax.legend(loc='upper left')
    ax.set_title('Demand and Exports Analysis')
    ax.set_xlabel('Period')
    ax.set_ylabel('Energy (MWh)')
    plt.show()

if __name__ == '__main__':
    # -------------------------------------------------------------------------
    # This block is for testing the simulation script directly.
    # The primary workflow is handled by 'run_investment_analysis.py'.
    # -------------------------------------------------------------------------

    # 1. Load parameters from the configuration file
    periods = config.simulation_parameters["periods"]

    # Load demand data
    forecast_demands0 = pd.read_csv(config.file_paths["forecast_demand"])
    real_demands0 = pd.read_csv(config.file_paths["real_demand"])
    forecast_demands = np.array(forecast_demands0).flatten()[:periods]
    real_demands = np.array(real_demands0).flatten()[:periods]

    # 2. Initialize all model components from the config file

    # Initialize generators
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
        else: # Renewables
            generator_objects[name] = ExpensiverenewableGenerator(**params)

    generators = list(generator_objects.values())

    # Initialize batteries
    battery_objects = {name: Battery(**params) for name, params in config.batteries.items()}
    for bat in battery_objects.values():
        bat.set_stored_energy_var(0, 0)
    batterys = list(battery_objects.values())

    # Initialize connections and electrolyzer
    connections = [Connection(**params) for name, params in config.connections.items()]
    electrolyzer = Electrolyzer(**config.electrolyzer)


    # 3. Run the simulation
    results = run_simulation(periods, generators, batterys, forecast_demands, real_demands, connections, electrolyzer)

    # 4. Unpack and plot results (optional, for direct testing)
    (avg_electricity_prices, storage_fees, store_electricity, generation_costs, storage_pool, total_storage_pool,
     storage_pools_composition, usage_storage_pool_composition, avg_gen_fees, avg_curtailment_fees,
     avg_balancing_fees, avg_storage_fees, ahead_renewables, ahead_other, ahead_traditional, ahead_nuclear,
     balance_renewables, balance_other, balance_traditional, balance_nuclear, gen_list_composition,
     curtailed_electricity, excess_electricity, total_annual_cost, total_annual_demand, carbon_emission,
     sold_fees, purchase_fees, traditional_gen, total_green_hy, total_renew_capacity, renew_capacity,
     total_annual_energycell, total_income_dict, excess_energy_dict, excess_energy_final_dict,
     curtailed_energy_dict, renewable_hy_dict, flexible_demand_list, interconnector_exports_list, blackout_periods) = results
    
    # 4.5 Save blackout data to CSV
    save_blackout_data_to_csv(blackout_periods, 'blackout_data.csv')

    print("Simulation finished. Plotting results...")

    # 5. Call the new plotting functions
    plot_generation_share(gen_list_composition, batterys, generators, connections)
    plot_consumption_share(real_demands, flexible_demand_list, interconnector_exports_list, periods)

    plot_results(avg_electricity_prices, periods)
    storage_composition_show(storage_pools_composition, batterys)
    gen_list_show(gen_list_composition, batterys, generators)