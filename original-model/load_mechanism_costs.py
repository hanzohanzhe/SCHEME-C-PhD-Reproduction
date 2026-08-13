#!/usr/bin/env python3
"""Helper module to load mechanism cost data.
   Reads historical data from Excel, fits growth trends for CM and Decarbonization
   (only where data exists), extrapolates 2025-2035, writes fitted values to Excel,
   and returns cost dict so 2025-2035 vary by year (not constant average).
"""
import pandas as pd
import numpy as np
import os

# Default Excel path: support both 'mechansim cost.xlsx' and 'mechanism.xlsx'
MECHANISM_EXCEL = 'mechansim cost.xlsx'
SHEET1_NAME = 'Sheet1'


def _clean_cost(value):
    if pd.isna(value):
        return 0.0
    if isinstance(value, str):
        value = value.replace('~', '').replace('£', '').replace(',', '').strip()
        try:
            return float(value)
        except ValueError:
            return 0.0
    return float(value)


def _fit_and_extrapolate(years, values, target_years):
    """
    Fit linear trend (only if we have at least 2 valid points) and extrapolate.
    years, values: 1D arrays of same length; only use points where value > 0.
    target_years: list of years to predict (e.g. 2025..2035).
    Returns: dict year -> predicted value in same unit as values; if no fit, returns None.
    """
    mask = np.array([v > 0 for v in values], dtype=bool)
    y = np.asarray(years)[mask]
    v = np.asarray(values, dtype=float)[mask]
    if len(y) < 2:
        return None
    # Linear trend: value = a + b * year
    coefs = np.polyfit(y, v, 1)
    out = {}
    for yr in target_years:
        out[yr] = float(np.polyval(coefs, yr))
    return out


def _append_fitted_to_sheet1(filepath, fitted_cm_mn, fitted_decarb_mn):
    """Append 2025-2035 fitted values to Sheet1, below existing data (same columns, £mn).
       If 2025-2035 rows already exist at the bottom, overwrite them (no duplicate blocks)."""
    try:
        import openpyxl
        book = openpyxl.load_workbook(filepath)
        if SHEET1_NAME not in book.sheetnames:
            book.save(filepath)
            return
        ws = book[SHEET1_NAME]
        # Find column indices by header (row 1)
        col_year_idx = None
        col_security_idx = None
        col_decarb_idx = None
        for col in range(1, ws.max_column + 1):
            val = ws.cell(1, col).value
            if val is None:
                continue
            s = str(val).lower()
            if 'delivery' in s and 'year' in s:
                col_year_idx = col
            if 'security' in s and 'budget' in s:
                col_security_idx = col
            if 'decarbonization' in s and 'budget' in s:
                col_decarb_idx = col
        if col_year_idx is None:
            col_year_idx = 1
        if col_security_idx is None:
            col_security_idx = 2
        if col_decarb_idx is None:
            col_decarb_idx = 3
        # Last row with data
        last_row = 1
        for row in range(2, ws.max_row + 2):
            if ws.cell(row, col_year_idx).value is None or str(ws.cell(row, col_year_idx).value).strip() == '':
                last_row = row - 1
                break
            last_row = row
        # If last 11 rows are already 2025-2035, overwrite; else append
        n_fitted = 11
        years_sorted = sorted(fitted_cm_mn.keys())
        start_write_row = last_row + 1
        if last_row >= n_fitted:
            try:
                first_yr = str(ws.cell(last_row - n_fitted + 1, col_year_idx).value or '')
                last_yr = str(ws.cell(last_row, col_year_idx).value or '')
                if '2025' in first_yr and '2035' in last_yr:
                    start_write_row = last_row - n_fitted + 1
            except Exception:
                pass
        for i, yr in enumerate(years_sorted):
            r = start_write_row + i
            ws.cell(r, col_year_idx, f"{yr}/{str(yr)[2:]}")
            ws.cell(r, col_security_idx, round(fitted_cm_mn[yr], 2))
            ws.cell(r, col_decarb_idx, round(fitted_decarb_mn[yr], 2))
        book.save(filepath)
    except Exception as e:
        print(f"Warning: could not append fitted rows to {filepath}: {e}")


def load_mechanism_costs(excel_path=None):
    """
    Load mechanism cost data from Excel file.
    - Sheet1: historical Delivery Year, Security Budget (£mn), Decarbonization Budget (£mn).
    - Fits linear trend per series only where valid data exists; extrapolates 2025-2035.
    - Appends 2025-2035 fitted values to Sheet1 below existing data (or overwrites if already present).
    - For years before 2025 missing in data, still fills with average of available history.
    """
    path = excel_path or MECHANISM_EXCEL
    if not os.path.isfile(path):
        path = 'mechanism.xlsx'
    if not os.path.isfile(path):
        path = MECHANISM_EXCEL

    try:
        df = pd.read_excel(path, sheet_name='Sheet1')
    except Exception as e:
        print(f"Error loading mechanism costs: {e}")
        return _default_cost_dict()

    # Normalize column names (allow slight variants)
    col_year = None
    col_security = None
    col_decarb = None
    for c in df.columns:
        c_lower = str(c).lower()
        if 'delivery' in c_lower and 'year' in c_lower:
            col_year = c
        if 'security' in c_lower and 'budget' in c_lower:
            col_security = c
        if 'decarbonization' in c_lower and 'budget' in c_lower:
            col_decarb = c
    if col_year is None:
        col_year = 'Delivery Year'
    if col_security is None:
        col_security = 'Security Budget (£mn)'
    if col_decarb is None:
        col_decarb = 'Decarbonization Budget (£mn)'

    df = df[df[col_year].astype(str).str.lower() != 'average'].copy()
    df['Year'] = pd.to_numeric(
        df[col_year].astype(str).str.split('/').str[0],
        errors='coerce'
    ).fillna(0).astype(int)
    df = df[df['Year'] > 2000]

    df['CM_mn'] = df[col_security].apply(_clean_cost)
    df['Decarb_mn'] = df[col_decarb].apply(_clean_cost)

    # Historical cost dict (from table)
    cost_dict = {}
    for _, row in df.iterrows():
        yr = int(row['Year'])
        cost_dict[yr] = {
            'CM_Cost': row['CM_mn'] * 1e6,
            'Decarbonization_Cost': row['Decarb_mn'] * 1e6,
        }

    # Fit only on years < 2025 so 2025-2035 are always extrapolated from real history (not from previously written fitted rows)
    df_hist = df[df['Year'] < 2025] if (df['Year'] < 2025).any() else df
    years_arr = df_hist['Year'].values
    cm_mn_arr = df_hist['CM_mn'].values
    decarb_mn_arr = df_hist['Decarb_mn'].values

    # Averages from history only (years < 2025), for missing years and for 2025-2035 if no fit
    hist_years = [y for y in cost_dict if y < 2025]
    all_cm = [cost_dict[y]['CM_Cost'] / 1e6 for y in hist_years if cost_dict[y]['CM_Cost'] > 0]
    all_decarb = [cost_dict[y]['Decarbonization_Cost'] / 1e6 for y in hist_years if cost_dict[y]['Decarbonization_Cost'] > 0]
    avg_cm_mn = float(np.mean(all_cm)) if all_cm else 749.3
    avg_decarb_mn = float(np.mean(all_decarb)) if all_decarb else 8443.69

    target_years = list(range(2025, 2036))

    # Fit and extrapolate: only use series that have data (no fit => don't use that series in fit)
    fitted_cm = _fit_and_extrapolate(years_arr, cm_mn_arr, target_years)
    fitted_decarb = _fit_and_extrapolate(years_arr, decarb_mn_arr, target_years)

    # 2025-2035: use fitted values where we have a fit, else average (same unit: £mn then *1e6)
    fitted_cm_mn = {}
    fitted_decarb_mn = {}
    for yr in target_years:
        if fitted_cm is not None and yr in fitted_cm:
            val = fitted_cm[yr]
            fitted_cm_mn[yr] = max(0.0, val)
        else:
            fitted_cm_mn[yr] = avg_cm_mn
        if fitted_decarb is not None and yr in fitted_decarb:
            val = fitted_decarb[yr]
            fitted_decarb_mn[yr] = max(0.0, val)
        else:
            fitted_decarb_mn[yr] = avg_decarb_mn

    for yr in target_years:
        cost_dict[yr] = {
            'CM_Cost': fitted_cm_mn[yr] * 1e6,
            'Decarbonization_Cost': fitted_decarb_mn[yr] * 1e6,
        }

    # Append 2025-2035 fitted values to Sheet1, below existing data
    _append_fitted_to_sheet1(path, fitted_cm_mn, fitted_decarb_mn)

    # Fill missing years 2015-2024 with average of available historical (only for years not in cost_dict)
    for year in range(2015, 2025):
        if year not in cost_dict:
            cost_dict[year] = {
                'CM_Cost': avg_cm_mn * 1e6,
                'Decarbonization_Cost': avg_decarb_mn * 1e6,
            }
        else:
            if cost_dict[year]['CM_Cost'] == 0:
                cost_dict[year]['CM_Cost'] = avg_cm_mn * 1e6
            if cost_dict[year]['Decarbonization_Cost'] == 0:
                cost_dict[year]['Decarbonization_Cost'] = avg_decarb_mn * 1e6

    return cost_dict


def _default_cost_dict():
    """Return constant default for all 2015-2035 when file/parse fails."""
    default_costs = {}
    for year in range(2015, 2036):
        default_costs[year] = {
            'CM_Cost': 749.3e6,
            'Decarbonization_Cost': 8443.69e6,
        }
    return default_costs


if __name__ == '__main__':
    # 验证：跑投资分析时用的 mechanism cost 是 2025-2035 逐年（拟合增长），不是每年相同
    costs = load_mechanism_costs()
    print("2025-2035 Mechanism costs (used when you run Case 1/2/3) — should GROW by year:\n")
    print("Year    CM_Cost (£mn)   Decarbonization_Cost (£mn)")
    print("-" * 52)
    for y in range(2025, 2036):
        cm_mn = costs[y]['CM_Cost'] / 1e6
        dec_mn = costs[y]['Decarbonization_Cost'] / 1e6
        print(f"{y}     {cm_mn:>12.2f}   {dec_mn:>12.2f}")
    print("-" * 52)
    print("If numbers increase from 2025 to 2035 → mechanism cost is growing. Confirmed.")
