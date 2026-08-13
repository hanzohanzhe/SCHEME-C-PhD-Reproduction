# Decarbonization Cost Breakdown Research

This sandbox copies the existing base investment model and keeps the original folder unchanged.

## What changed

- `load_decarbonization_cost_breakdown.py` replaces the single fitted decarbonization budget with RO, FiT, and CfD components.
- `run_investment_analysis_case3_decarbonization_breakdown_cm.py` is the preferred research script. It keeps the original Case 3 Capacity Market payment to CCGT/OCGT and replaces only the decarbonization side with the RO/FiT/CfD breakdown.
- `run_investment_analysis_case2_decarbonization_breakdown.py` is retained as a decarb-only sensitivity and does not include Capacity Market.
- The preferred Case 3 script keeps the original VRE allocation mechanism, but splits each VRE asset's decarbonization income into:
  - `ro_legacy_income`
  - `fit_legacy_income`
  - `cfd_new_decarbonization_income`
  - `decarbonization_income` as the sum used by the original ROI/payback logic
- `decarbonization_cost_scenarios.csv` contains the 2025-2034 cost path for all three scenarios.
- `ro_fit_legacy_retirement_table.csv` contains the project-cohort retirement shares used to reduce inherited RO and FiT payments.

## Source assumptions

- RO: Ofgem/GOV.UK describe the RO as closed to new capacity and ending by 31 March 2037, with up to 20 years of support. The model now reads project-level `RO Banding (ROC/MWh)`, capacity, and `Operational` dates from REPD, then creates a 20-year cohort retirement table capped at 2037. Sources: Ofgem RO Annual Report SY22; GOV.UK fixed price certificates call for evidence.
- FiT: Ofgem guidance describes the scheme as closed to new applications from 1 April 2019, while existing accredited installations keep payments for their eligibility period, typically around 20 years. The model now reads project-level `FiT Tariff (p/kWh)`, capacity, and `Operational` dates from REPD, then creates a 20-year cohort retirement table. Sources: Ofgem FIT scheme closure and FIT generator guidance.
- CfD: GOV.UK/LCCC describe renewable CfDs as 15-year contracts. In this sandbox, new CfD is the expansion channel for decarbonization support. Sources: GOV.UK Contracts for Difference collection; LCCC CfD scheme pages.
- All values are interpreted as real 2025 GBP. No inflation or price-index uplift is applied.
- Caveat: REPD gives finer project-level granularity than the workbook, but FiT small-scale installations are likely under-covered. Treat the FiT retirement table as the project-visible cohort approximation unless replaced with the full Ofgem FIT installation register.

## Scenario design

- `price_smoothing_only` / `no_expansion`: CfD is only a renewable price-smoothing tool; it adds no new decarbonization subsidy.
- `normal_subsidy` / `average_expansion`: annual new CfD decarbonization support equals the mean positive annual increase in total renewable support over the available recent decade.
- `strong_subsidy` / `aggressive_expansion`: annual new CfD decarbonization support equals the historical maximum annual increase in total renewable support.

The subsidy-intensity metric is based on annual increments, not the current stock of subsidy payments. From the 2015/16-2024/25 support table, the normal increment is GBP 932.99mn/year and the strong increment is GBP 2,133.40mn/year.

## Run

```powershell
cd decarbonization_cost_research

# only regenerate the scenario table
python load_decarbonization_cost_breakdown.py

# run one investment scenario
$env:DECARB_SCENARIO="normal_subsidy"
python run_investment_analysis_case3_decarbonization_breakdown_cm.py
```

Valid `DECARB_SCENARIO` values are `price_smoothing_only`, `normal_subsidy`, `strong_subsidy`, or the aliases `no_expansion`, `average_expansion`, and `aggressive_expansion`.
