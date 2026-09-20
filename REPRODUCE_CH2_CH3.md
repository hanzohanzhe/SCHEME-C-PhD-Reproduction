# Reproducing Chapters 2 and 3

**Author-review draft — 20 September 2026**

This guide records the model configuration, dispatch choices and accounting needed to reproduce the Chapter 2 power-system model (PSM) and the Chapter 3 hydrogen comparisons. It is intended to sit in the root of the [SCHEME-C-PhD-Reproduction repository](https://github.com/hanzohanzhe/SCHEME-C-PhD-Reproduction).

The specification was checked against `PhD_thesis_final9.19.docx` and repository commit `de3d14044c85464d718631b3640d7ab878b9e2fa`. The thesis file has SHA-256 `514a0ff742a1754663478da3692d067c8784130fac34767d2f21586696bd3bbc`. Figure and table numbers below refer to that thesis version.

**Scope and availability.** This document supplies the chapter parameter tables, the retained 2022 input-file manifest, the fixed-portfolio procedure, the five hydrogen-allocation rules and the annual fair-cost/intensity calculation. The public commit identified above contains the later Scheme C/CEM archive and its launchers. Chapter-specific data delivery and executable strategy entry points have separate availability requirements, recorded in Section 7. The instructions below distinguish the published source interfaces from the chapter procedures that those interfaces must support. This guide makes no claim that every thesis result has been numerically reproduced.

## 1. Repository and environment

Relevant existing files are:

| File | Role |
| --- | --- |
| [original-model/simulation_model.py](original-model/simulation_model.py) | PSM agents, dispatch and simulation routine |
| [original-model/config.py](original-model/config.py) | Archived defaults; these are not a frozen Chapter 2/3 scenario specification |
| [requirements-py310.txt](requirements-py310.txt) | Reconstructed compatibility environment |
| [docs/QUICKSTART.md](docs/QUICKSTART.md) | Existing archive installation procedure |
| [docs/PROVENANCE.md](docs/PROVENANCE.md) | Source and historical-run provenance |
| [benchmark-data-metadata/SOURCE_REGISTER.md](benchmark-data-metadata/SOURCE_REGISTER.md) | Input-source and access information |
| [docs/VALIDATION_STATUS.md](docs/VALIDATION_STATUS.md) | Limits of the existing validation evidence |

Use Windows 10/11 and CPython 3.10.11 for the documented archive environment. The installation helpers check Python 3.10 but do not enforce the patch version. The requirements file is a reconstructed environment, not a complete package freeze from the original chapter runs.

In PowerShell, from a directory in which a new clone can be created:

```powershell
git clone https://github.com/hanzohanzhe/SCHEME-C-PhD-Reproduction.git
Set-Location SCHEME-C-PhD-Reproduction
git checkout --detach de3d14044c85464d718631b3640d7ab878b9e2fa
git rev-parse HEAD
py -3.10 -c "import sys; print(sys.version)"
py -3.10 reproduction-tools/verify_repository.py
```

At this commit, the expected integrity-check result is:

```text
Scheme C repository verification passed: 56 immutable files, 6 authoritative historical hashes.
```

This checks the archived files and retained records, not agreement with the thesis results. Keep the output of `git rev-parse HEAD` in each run record.

The existing numerical archive requires the separate, access-controlled `force-uk-benchmark-2025-v1.zip` asset from `hanzohanzhe/FORCE-UK-Benchmark-Data`. It is not anonymously downloadable. An authorised reader who already has the archive can prepare a fresh clone with:

```powershell
powershell -ExecutionPolicy Bypass -File reproduction-tools/install-scheme-c.ps1 -ArchivePath ".\force-uk-benchmark-2025-v1.zip"
```

Place the supplied archive in the repository root for this command. Its required SHA-256 is:

```text
0bc3a78d535fbb6198ee16d708343e6d70a01de76fa2e5459ffb27cebd2cb672
```

The helper creates `.venv`, installs dependencies, prepares a disposable `work/` directory and mounts the historical weather path on `F:`. Allow at least 5 GB for the archive setup and additional space for simulation outputs. Use an environment where `F:` is available or already contains the verified weather files; do not replace an unrelated drive. The command deliberately omits the option that replaces an existing `work/` directory.

Access to this archive does **not** establish that its inputs are the historical Chapter 2/3 inputs. Confirm that correspondence before treating a run as chapter reproduction. Existing CEM scenario names, including `base`, must not be interpreted as the chapter baselines.

## 2. Shared inputs, chronology and units

Both chapters describe the 2022 GB demand and demand-forecast series and 2022 ERA5 weather. The weather specification uses a 0.25-degree grid, nearest-point selection and repetition of each hourly value into two half-hour periods. A complete year has 17,520 periods.

### 2.1 Chapter parameter list

Use the parameter tables in **this repository document**, together with the capacity and price cases in Section 3.1 and the Chapter 3 electrolyser settings in Section 4.1. The tables below reproduce Chapter 2, Tables 4–6, so the reader does not need a separate copy of the thesis to obtain these numerical inputs. The archived [original-model/config.py](original-model/config.py) supplies the configuration structure and field names; its later CEM defaults are not the Chapter 2/3 parameter set.

**Thermal-generator parameters — thesis Table 4**

| Parameter | CCGT | OCGT | Biomass |
| --- | ---: | ---: | ---: |
| Fixed O&M, GBP/MW as printed in Table 4 | 231.82 | 99.00 | 350.00 |
| Variable O&M, GBP/MWh | 0.1 | 0.1 | 0.2 |
| Fuel-to-electricity efficiency | 0.51 | 0.41 | 0.25 |
| Ramp limit, fraction of capacity per half-hour | 0.50 | 1.00 | 0.25 |
| Start-up cost, GBP/MW | 50 | 30 | 83 |
| Annual fuel-availability limit, TWh | Not constrained | Not constrained | 16 |
| Fuel replenishment, MWh per half-hour | Not constrained | Not constrained | 913 |
| Operational carbon intensity, tonnes CO2/MWh | 0.394 | 0.651 | 0.120 |

The fixed-O&M row preserves the printed values and unit; Table 4 does not label its time basis. Do not silently interpret that row as either an annual charge or a period charge. The biomass annual limit and replenishment are separate published inputs: 913 MWh × 17,520 periods is approximately, rather than exactly, 16 TWh.

**Annualised generation/interconnector parameters — thesis Table 5**

| Technology | Capital plus fixed O&M, GBP/MW/year | Embodied emissions, tonnes CO2/MW/year |
| --- | ---: | ---: |
| Onshore wind | 40,000 | 10 |
| Offshore wind | 80,000 | 11 |
| Solar | 24,000 | 16 |
| Interconnectors | 20,000 | 8 |

Wind and solar use a 25-year lifetime in the chapter. These annualised cost coefficients are used in the chapter's annual accounting; they are not the overnight `capital_costs_per_mw` values used by the CEM investment model.

**Storage parameters — thesis Table 6**

| Parameter | Pumped hydro | Compressed air | Thermal | Li-ion | Hydrogen electricity storage |
| --- | ---: | ---: | ---: | ---: | ---: |
| Round-trip efficiency | 0.75 | 0.65 | 0.65 | 0.85 | 0.32 |
| Time for stored energy to fall below 80% through self-discharge, hours | 87,600 | 9,600 | 480 | 1,560 | 2,500 |
| Nominal discharge duration, hours | 4 | 4 | 4 | 4 | 250 |
| CAPEX, GBP/kW | 985.4 | 759.2 | 687.8 | 676.3 | 723.6 |
| Annual OPEX, GBP/kW/year | 13.4 | 9.5 | 20.6 | 6.6 | 19.7 |
| Cycle life | 1,000,000 | 50,000 | 50,000 | 5,000 | 1,000 |
| Calendar life, years | 30 | 25 | 20 | 15 | 10 |
| Storage embodied emissions, tonnes CO2/MWh of energy capacity | 0.5 | 2.8 | 0.2 | 0.3 | 0.0006 |

The hydrogen column also reports an equipment-emission value of 7.5 for generation equipment. The paragraph preceding Table 6 distinguishes its MW equipment basis from the MWh storage basis, although the table has a shared tonnes/MWh row label. Keep this term separate from the 0.0006 storage coefficient; the ambiguous table label is not a basis for adding the two coefficients. These hydrogen-storage parameters apply to Chapter 2 where specified; Chapter 3 uses the separate consumptive-electrolyser parameters in Section 4.1.

**Corresponding fields in the archived source**

| Parameter group | Repository configuration/interface |
| --- | --- |
| Thermal capacities and ramp increments | `generators['CCGT']`, `generators['OCGT']`, `generators['bio_and_waste']`: `capacity_limit`, `alter_limit` |
| Thermal operating costs and emissions | The same dictionaries: `gen_cost`, `startup_cost`, `fuel_cost`, `carbon_price`, `carbon_intensity`, `unit_time_cost`; fuel efficiency and annual fixed-cost accounting are not a complete standalone parameter table in these dictionaries |
| Biomass availability | `generators['bio_and_waste']['energy_limit']` and `['add_energy']` |
| VRE locations and installed capacity | `locations` and the corresponding entries in `generators`; use Section 3.1 for chapter capacity totals, not the archived 2025 site capacities |
| Storage capacities and charge/discharge efficiencies | `batteries`: `pool_limit`, `per_pool_limit`, `n_1`, `n_2`; round-trip efficiency is the product of the two one-way efficiencies |
| Storage cost inputs | `batteries`: `storage_fee`, `per_storage_fee`, `capital_cost`; the complete Table 6 life/cycle/self-discharge parameter set is recorded above and is not represented by one equivalent dictionary in the archived configuration |
| Interconnector parameters | `connections`; annualised chapter cost/emission coefficients are the Table 5 values above |
| Consumptive electrolyser | `electrolyzer`; use Section 4.1 for chapter values and the ramp conversion |

These are field correspondences, not instructions to copy unlike units directly. For example, Table 4's carbon coefficients are in tonnes/MWh whereas the archived `carbon_intensity` values are 394, 651 and 120, and storage power and energy must follow the half-hour convention below. The archived storage labels `1c_battery`, `0.25c_battery` and `0.5c_battery` also coexist with legacy thermal/air/Li-ion names; use the technology definition and Table 6 coefficients when constructing the chapter configuration.

### 2.2 Chapter inputs and access

Use the retained dataset **`chapter23-legacy-2022-inputs`**, packaged as **`CH2_CH3_INPUTS_2022.zip`**. Its 16 numerical files total 351,219,457 bytes. The file manifest below is included directly in this guide so that it remains available when the guide is placed in the repository. The archive SHA-256 is `06fc45c1356d4171612fbdb49c4c50468f4e489f4c4b4a35971e4a2521fce858`.

The pinned public model commit does not include this chapter archive. Request the named dataset and its delivery terms from the [repository maintainer](https://github.com/hanzohanzhe/SCHEME-C-PhD-Reproduction), identifying the model commit and archive hash. A public download requires a release asset or data-repository link supplied by the maintainer. Access to the GitHub source alone therefore leaves a separate data-acquisition step. Retain the upstream attribution and access conditions accompanying the supplied files.

| Chapter input | Bytes | SHA-256 |
| --- | ---: | --- |
| `2022fd.csv` | 183,431 | `a2d21ff52366c36f8711333a12c3a7a7bc3b34017cca852f330a0189dfe4ddfc` |
| `2022reald.csv` | 183,438 | `8298d9b62f89116c56d1ae8b8ffe9ef5ceea2f8fca0f4d8290b24913e5b1ae56` |
| `France_profile.csv` | 114,178 | `4392a914281816eae8ec230aa290ea0326d2de0aa96b326e02b1979c354e5240` |
| `France.csv` | 379,586 | `03ad5c0e77cb6b21f17e2eb33cf880c01531456b94248352cde4ea31ee88a79c` |
| `belgium_profile.csv` | 96,890 | `c7d727db62077cacdfb3955aa2daa239d394cdc4a94a66a20be71ce1fa28ae10` |
| `Belgium.csv` | 361,860 | `25e1fb97a74e062c49e83e1b7d8271b66029759c82ef7915dea1f451fabe0876` |
| `nehtheralnd_profile.csv` | 96,417 | `ccda2a9e30bdea9a25173423a42ba864d47a0f1cf958abe1dc9c150830e248b8` |
| `Netherlands.csv` | 301,950 | `59a74a9d0bd72c6742d3c89f76a8eb2b58e9338b24044a58add7020e7439de1c` |
| `Norway_profile.csv` | 97,041 | `088041cf8b38a724c06d0cb99d263135b7ccf2ed119b2f8c316b702572f1c6d8` |
| `Norway.csv` | 378,974 | `2f85207bddbf04db4c015d56252e866551cea5a68a720ee928a231fa6bade1a5` |
| `Ireland_profile.csv` | 91,116 | `182e1d00588a46c636c75864b74b9db7a77facf5f47b0bd1a761eeba67c05104` |
| `Ireland.csv` | 215,744 | `f26616315e13051365b55aa86b0fba7a8d0f7e4d64d9c9d4371f6824870cdb70` |
| `2022wind100m.grib` | 233,366,400 | `7a238a23a984cc379d54c29b12ec0293b3c4969ffaf9c2da9df4e4ce52d277a3` |
| `2022solar.nc` | 114,985,584 | `ecefe3b7d851b24af7475c8b46079b0c161bcd9688490259154f38d8ea3b4cfd` |
| `2022fd1.csv` | 183,417 | `5e5a1c3a683c3898fd3b8917353d0a97610bd273d3b099ab7f9a2633ff748a41` |
| `2022reald1.csv` | 183,431 | `fca3f04acc7573e80cad74a8979b48ebee142426665154dfbd4604946c6f7bed` |

`2022fd.csv` and `2022reald.csv` supply ordinary electricity-demand forecasts and realised demand. The `fd1`/`reald1` variants contain a fixed 10,000 MW addition used by the historical on-grid drivers. Select the demand pair explicitly in the run record. Adding actual electrolyser demand to an already augmented input would count that component twice; the ordinary-demand arrays are the starting point for a driver that adds the actual consumptive load itself.

The chapter files are distinct from the separate `force-uk-benchmark-2025-v1.zip` required by the later archive installer in Section 1. The latter's [bill-of-data.json](benchmark-data-metadata/bill-of-data.json) and [release-manifest.json](benchmark-data-metadata/release-manifest.json) describe that benchmark release, including `average_annual_solar_profile.nc` and `average_annual_wind_profile.nc`. Chapter weather uses the chronological `2022solar.nc` and `2022wind100m.grib` identified above. A successful benchmark installation establishes access to that release only.

**Reading and time conventions.** Preserve the retained arrays when replaying a historical calculation:

1. Demand CSVs are read with the historical `pandas.read_csv` default `header=0`, flattened and restricted to the first 17,520 data values. `2022fd.csv` has a numeric first row that this convention treats as a header; `2022reald.csv` has the text header `reald`. The selected realised-demand samples are MW and integrate to 232.9051895 TWh after multiplication by 0.5 hours. Changing header handling creates a different input series.
2. The weather files each contain 8,760 hourly times from 1 January 2022 00:00 through 31 December 2022 23:00 UTC. The 0.25-degree grid spans 67 to 47 degrees north and −13 to 7 degrees east. Wind uses the 100 m u/v components; solar uses `ssrd`. Select the nearest grid point and repeat each hourly value twice. Preserve the archived wind/solar conversion function for the selected scenario: weather extraction and the conversion to generator output are separate operations.
3. The retained interconnector readers also use `header=0`, flatten the arrays and repeat each scalar twice. Several files already contain repeated or half-hour-looking records. Historical replay preserves this behaviour; a corrected calendar alignment requires a separately identified input revision. Preserve the actual object-to-file routing below, including its inconsistent country labels.
4. The scalar demand, flow and price CSVs contain no timestamp columns. Their original time zone and daylight-saving alignment cannot be recovered from row order alone. The legacy reader performs no timestamp join, sorting, gap interpolation or duplicate removal. Record that limitation explicitly. Do not describe those CSVs as timestamp-validated UTC series. A reconstruction from timestamped upstream data must document its own missing-value, duplicate and daylight-saving rules.
5. The retained numerical CSV values are finite. Public-archive loaders that replace invalid price entries with zero have an additional preprocessing rule; record whether that rule is exercised in a particular input revision. External prices enter the model as GBP/MWh; the retained scalar files do not preserve the original currency-conversion script or exchange-rate record.

| Historical connection object | Flow file | Price file |
| --- | --- | --- |
| `Interconnect_France` | `France_profile.csv` | `France.csv` |
| `Interconnect_Netherland` | `belgium_profile.csv` | `Belgium.csv` |
| `Interconnect_Ireland` | `nehtheralnd_profile.csv` | `Netherlands.csv` |
| `Interconnect_Norway` | `Norway_profile.csv` | `Norway.csv` |
| `Interconnect_Beligum` | `Ireland_profile.csv` | `Ireland.csv` |

There is no separate generator-location CSV in the retained chapter drivers. Coordinates are literal inputs to the weather-extraction calls; Appendix A reproduces those coordinates from the retained future after-storage source. The public archive's `locations` dictionary in [original-model/config.py](original-model/config.py) supplies its own coordinate configuration. Associate a location list with its actual driver and capacity allocation, because the later archive's fleet defaults have a different scenario identity.

Upstream sources are the [NESO demand-data portal](https://www.neso.energy/data-portal/historic-demand-data), [NESO day-ahead forecasts](https://www.neso.energy/data-portal/1-day-ahead-demand-forecast), [ERA5 hourly single-level data](https://doi.org/10.24381/cds.adbb2d47) and [Ember European wholesale prices](https://ember-energy.org/data/european-wholesale-electricity-price-data/). Rebuilding from these sources requires the recorded selection and preprocessing choices; a fresh download can differ from the pinned historical arrays.

### 2.3 Units and run state

Use explicit units throughout the chapter driver and output files:

| Quantity | Convention |
| --- | --- |
| Generation, demand and electrolyser input power | MW |
| Interval length | 0.5 h |
| Interval electrical energy | MW × 0.5 h, in MWh |
| Annual electrical energy | Sum of interval MWh |
| Annual hydrogen output | MWh of hydrogen, lower heating value (LHV) |
| Annual system cost | GBP/year |
| Annual system emissions | tonnes CO2/year, converted explicitly for reported intensities |

Do not apply the half-hour conversion twice if a recovered input or output already contains interval energy. The current source mixes names suggesting energy with quantities subsequently integrated as power samples; the chapter driver must establish that mapping explicitly.

Each independent run must start from the specified generator states, storage stocks and electrolyser state. Record the initial and terminal storage treatment, utilisation-factor initialisation, convergence history and any random seed used. Do not carry the final state of one scenario into another unless the historical procedure explicitly requires it.

## 3. Chapter 2: fixed-portfolio PSM

### 3.1 Scenario inputs

The generation and interconnector portfolios below are transcribed from Table 2. Values are MW. Scenarios B–D share the planned generation portfolio.

| Technology | A: 2022 | B–D: planned |
| --- | ---: | ---: |
| CCGT | 28,000 | 28,000 |
| OCGT | 4,146 | 4,146 |
| Biomass | 4,163 | 4,762 |
| Nuclear | 5,883 | 9,143 |
| Solar | 8,687 | 31,351 |
| Onshore wind | 12,692 | 55,352 |
| Offshore wind | 9,860 | 36,782 |
| Interconnection | 8,400 | 14,500 |

Storage entries are **power MW / energy MWh**:

| Technology | A | B | C | D, as listed in Table 2 |
| --- | ---: | ---: | ---: | ---: |
| Pumped hydro | 3,233 / 12,932 | 3,233 / 12,932 | 4,337 / 17,348 | 5,000 / 20,000 |
| Compressed air | 0 | 0 | 0 | 5,000 / 20,000 |
| Thermal storage | 0 | 0 | 0 | 5,000 / 20,000 |
| Li-ion battery | 1,614 / 6,456 | 1,614 / 6,456 | 18,211 / 72,844 | 5,000 / 20,000 |
| Hydrogen electricity storage | 0 | 0 | 468 / 117,000 | 5,000 / 1,250,000 |

Table 2's D entries sum to 25 GW and 1,330 GWh of storage. The recovered D source assigns a complete five-technology portfolio with 5,000 MW for each technology. Use that total-portfolio interpretation when identifying the archived D case. Its internal stock units and the printed MWh capacities still need to be reconciled before applying the thesis table as a physical-energy configuration.

Run each A–D portfolio under both paired price cases:

| Price case | Gas, GBP/MWh fuel | Carbon, GBP/tonne CO2 |
| --- | ---: | ---: |
| Low | 20 | 40 |
| High | 50 | 60 |

### 3.2 Execution sequence

Use the parameter list in Sections 2.1 and 3.1 for the chapter specification. The published source exposes `run_simulation(periods, generators, batterys, forecast_demands, real_demands, connections, electrolyzer)` in [original-model/simulation_model.py](original-model/simulation_model.py). This is the fixed-portfolio simulation routine. Its object lists must be constructed from the chapter case before calling it; the existing Scheme C launchers additionally perform capacity-expansion work. The pinned public commit has no dedicated Chapter 2 case-selection command, so no such command is assumed here.

1. Load the fixed portfolio and the chapter input files. Disable consumptive hydrogen production, including any VRE-attached electrolyser allocation. Retain the hydrogen **electricity-storage** technology where Table 2 requires it.
2. Execute the two-stage wholesale and balancing-market PSM over the full 2022 chronology, using forecast demand in the ahead stage and realised demand in the balancing stage.
3. Recalculate storage utilisation factors and repeat the annual dispatch as specified in Appendix 2B. The stated convergence criterion is a change no greater than 0.001 between iterations. Record the change for every active storage technology and retain the iteration history. Do not substitute a fixed nine-iteration stopping rule for the convergence check.
4. Save period dispatch, storage charging/discharging and stocks, imports/exports, curtailment, prices, costs and emissions. Aggregate using the documented energy and accounting conventions.
5. Compare the annual results with Table 3 and the relevant time-series and sensitivity figures. Keep any disagreement visible; changing a parameter merely to match one displayed number is not a reproduction procedure.

The sequence above states the chapter procedure. The recovered scripts run an annual dispatch with stored tariff parameters and then update utilisation-derived quantities. That observation alone does not establish the repeated annual convergence at 0.001 described in Appendix 2B. A frozen-tariff replay and a repeated-year convergence calculation must therefore have separate descriptions and records. The preserved parameter tables remain the thesis specification; source settings that differ from them must be listed with the selected driver.

### 3.3 Outputs and additional experiments

| Thesis output | Required experiment or saved data |
| --- | --- |
| Table 3; Figures 5 and 11 | A–D under both price cases; Figure 5 specifically uses B at high prices |
| Figures 6–9 | B-prime: no storage and nuclear disabled; then separate additions of 5 GW OCGT, 5 GW interconnection, or 1 GW of each of five storage technologies; display the first 1,200 periods |
| Figure 10 | VRE-capacity multiplier sweep around B, under the two price cases |
| Figure 12 | Interconnector-capacity sweep and the separate availability/profile constraints |
| Figures 13–14 | Storage-capacity/composition sweeps, with the reference portfolio and addition-versus-total convention recorded |
| Figure 16 | Storage-utilisation convergence history |
| Figures 17–18 | Planned-location versus representative-location onshore wind profiles |

Recover and publish the exact sweep grids and plotting definitions with these experiments. Structural diagrams and externally sourced Capacity Market statistics are not outputs of the PSM run.

## 4. Chapter 3: consumptive hydrogen production

### 4.1 Baselines and electrolyser settings

Use the current and future portfolios from Table 7. Their generation and interconnection capacities match the two columns in Section 3.1. Chapter 3 storage consists of pumped hydro and Li-ion batteries: current power capacities are 3,233 and 1,614 MW; future capacities are 4,337 and 18,211 MW. Freeze their energy capacities and other properties from the chapter source configuration. Table 7 lists storage power, not all those properties.

**Chapter 3 excludes electricity storage through hydrogen.** Do not copy the 468 MW hydrogen-storage entry from Chapter 2 scenario C into the future Chapter 3 baseline. The Chapter 3 electrolyser consumes electricity and produces hydrogen for use outside the electricity model; it does not discharge electricity back to the grid.

| Parameter | Chapter 3 specification |
| --- | --- |
| Gas price | GBP 50/MWh fuel |
| Biomass price | GBP 80/MWh fuel |
| Carbon price | GBP 60/tonne CO2 |
| Main electrolyser electrical input capacity | 10 GW |
| Capacity comparison | 2, 4, 6, 8 and 10 GW, plus a zero-electrolysis baseline |
| Electricity-to-hydrogen efficiency | 0.65, LHV |
| Ramp-up time | 4 hours |
| Annualised electrolyser capital cost | GBP 15/kW/year |
| Annual electrolyser O&M cost | GBP 3/kW/year |
| Transmission/distribution charge | GBP 1/MWh of electrolyser electricity input |
| Electrolyser equipment-emission term | Set to zero in the thesis accounting |

For each portfolio, first converge and save a zero-electrolysis baseline. For each hydrogen strategy/capacity, run the corresponding annual PSM with identical non-hydrogen assumptions and a separately converged storage-utilisation solution. Endogenous dispatch and utilisation may change; the exogenous portfolio, inputs and accounting boundary must remain paired.

In the archived source, the relevant independent load is `Electrolyzer(**config.electrolyzer)`. It is distinct from `config.batteries['hydrogen_battery']`. VRE agents also have an `electrolyzer_limit`; control those allocations explicitly. Set all consumptive paths to zero for the baseline. A single national capacity of 10 GW must not become 10 GW independently at every VRE site.

The independent load uses an additive per-step ramp increment through a limit of the form `min(real_energy + rampup_rate, capacity_limit)`. With half-hour updates, a four-hour ramp means:

```text
rampup_rate = capacity_limit × 0.5 / 4 = capacity_limit / 8
```

Both values must use the same internal dispatch units. Under an MW convention, 10 GW is 10,000 MW and the increment is 1,250 MW per half-hour. A raw value of `0.125` is not a universal four-hour ramp setting. If a recovered chapter variant uses interval MWh, convert both values consistently. Also specify startup/reset behaviour and ramp-down treatment: the archived ramp-up expression alone does not impose symmetric ramp-down constraints.

### 4.2 Five electricity-sourcing strategies

| Strategy | Allocation of electricity to the electrolyser |
| --- | --- |
| On-grid | Add electrolyser demand to grid demand; operation is close to full load, subject to the stated technical constraints |
| VRE-ahead | Withdraw available electricity from the aggregate VRE portfolio before electricity is offered to meet ordinary demand |
| Before-storage | Serve ordinary demand, then allocate eligible excess electricity to electrolysis before storage charging and exports |
| After-storage | Serve ordinary demand and storage charging first, then allocate eligible excess electricity to electrolysis before exports |
| After-inter | Serve ordinary demand, storage charging and exports first, then allocate remaining eligible excess electricity to electrolysis |

**Applying the five policies.** The current independent `Electrolyzer` operates in residual-electricity branches, while VRE objects have separate `electrolyzer_limit` fields ahead of market dispatch. The pinned public source has no five-strategy selector. The table therefore defines the required dispatch positions; editing only `config.electrolyzer['capacity_limit']` supplies a capacity change at the existing position.

Use one shared national electrical-input budget in each half-hour. The following pseudocode defines that budget and its allocation; it is an algorithm specification for the chapter driver:

```text
At the beginning of period t:
    upper_t = min(P_max, p_previous + P_max * 0.5 / ramp_hours)
    p_t = 0

At the allocation point for the selected strategy:
    q = min(max(eligible_electricity_MW, 0), max(upper_t - p_t, 0))
    eligible_electricity_MW -= q
    p_t += q

At the end of the period, after any balancing-stage allocation:
    p_previous = p_t
    hydrogen_MWh_LHV_t = p_t * 0.5 * 0.65
```

All allocation calls within a period share `p_t` and `upper_t`, including calls for different VRE sites or market stages. Update the previous-period state once after the period is complete. A shortage can reduce consumption immediately; the next upward step begins at that actual consumption. The four-hour limit constrains upward changes by 1,250 MW per half-hour at 10 GW.

| Policy | Required placement and accounting of the withdrawal |
| --- | --- |
| On-grid | Add the feasible electrolyser input to ordinary electricity demand once, and retain actual supplied input as `p_t`. Start from the ordinary `fd`/`reald` series when the driver itself adds this load. |
| VRE-ahead | Allocate from aggregated available VRE before ordinary-market offers. Deduct each accepted withdrawal from the corresponding VRE offer, and carry the same remaining national budget across sites. Record the site/technology allocation order used by the selected historical driver. |
| Before-storage | After meeting ordinary electricity demand, allocate eligible surplus to electrolysis, then offer the remainder to storage and exports. Apply the same priority to any eligible balancing-stage surplus. |
| After-storage | Charge storage first, allocate the remaining eligible surplus to electrolysis, then offer the remainder to exports. |
| After-inter | Charge storage and satisfy export opportunities first; allocate the remaining eligible surplus to electrolysis. |

For a zero-hydrogen comparator, use the same policy driver with `P_max=0`, zero the independent load's state and ramp increment, and set every VRE-attached `electrolyzer_limit` to zero. Restore ordinary demand if the positive case used a pre-augmented on-grid file. Check every period for zero consumptive-hydrogen withdrawal. Chapter 2 hydrogen electricity storage follows its own portfolio specification; Chapter 3 keeps that storage technology disabled.

Pair each hydrogen case with the zero case from the same driver, data, generator/storage portfolio, cost assumptions and accounting rules. Capacity changes require the matching ramp increment to be changed as well. Frozen parameter files, ordinary demand and non-hydrogen settings identify the comparison; a baseline copied from another strategy is usable only after those settings have been shown to match. This guide defines the controls and allocation order. The public release still needs to identify the actual executable entry point for each policy before readers can launch all five directly.

The dedicated Edinburgh wind-to-hydrogen comparison is a separate experiment, not a sixth dispatch position in the GB system. Reproducing it requires its wind profile, wind/electrolyser sizing procedure and equipment-cost/emission assumptions.

## 5. Hydrogen accounting and fair metrics

For a run expressed as half-hourly electrolyser input power `p[t]` in MW:

```text
E_input_MWh = 0.5 × sum(p[t])
P_H2_MWh_LHV = 0.65 × E_input_MWh
H2_tonnes = 0.03 × P_H2_MWh_LHV
```

The conversion uses 120 MJ/kg LHV: 1 MWh of hydrogen corresponds to 30 kg, and 1 TWh corresponds to 30 kt. Use measured electrolyser electrical input as the common production basis. The name `total_green_hy` has different meanings across retained source variants: the on-grid scripts record electrical input, while other branches apply an efficiency conversion. A before-storage branch also contains an exponentiation expression in that reported variable. Record a legacy output separately and identify its actual expression and units before using it. The electrical-input formula above applies the half-hour duration and efficiency exactly once.

For each hydrogen run, retain its paired baseline's annual totals and calculate:

```text
fair_cost_GBP_per_MWh_H2 = (C - Cb + CE + CT) / P_H2_MWh_LHV
fair_intensity_kgCO2_per_MWh_H2 = 1000 × (e - eb + eE) / P_H2_MWh_LHV
```

Here `C` and `Cb` are annual power-system costs in GBP; `e` and `eb` are annual emissions in tonnes CO2. `CE` is annual electrolyser equipment cost, `CT` is the electricity transmission/distribution charge, and `eE` is the equipment-emission term on the same annual basis. A zero-output run has undefined hydrogen-normalised metrics; report them as unavailable rather than zero.

Use an explicit accounting ledger for generation capital and O&M costs, thermal operating costs, storage costs/payments and net interconnector expenditure. Export income reduces the relevant net expenditure. Identify any overlap between marginal generation cost and separately reported variable O&M, and avoid counting the same storage cost twice.

For power-rate payments in GBP/hour, integrate each period once with 0.5 hours, then add annual fixed GBP charges once. An annual fixed charge must retain its annual basis. The retained sources can record the same import payment in both a balancing list and a separate purchase list, and can carry a balancing-storage fee into a later period. Build the annual ledger from the actual period's transactions with each payment counted once; retain the source totals when explaining any correction. Price imports from the observed imported MW and the corresponding external GBP/MWh price. A negative price can produce a negative payment, while imported quantity remains nonnegative. A source branch that produces a negative import quantity needs a separately documented dispatch correction before that result is used for a physical fair-cost comparison.

Save one record for the hydrogen run and one for its paired zero case with the following fields. These field names define the documented result record; they are independent of any later launcher's output schema.

| Saved field | Meaning |
| --- | --- |
| `run_id`, `baseline_id`, `strategy`, `portfolio` | Identity of both members of the comparison |
| `source_commit`, `input_hashes`, `parameters` | Exact source, the input files above, and the full selected chapter settings |
| `periods`, `period_hours`, `ordinary_demand_MWh` | 17,520 periods, 0.5 hours, and the common ordinary-demand basis |
| `electrolyser_input_MWh`, `hydrogen_output_MWh_LHV` | Actual electrical input and its 65% LHV hydrogen output |
| `C`, `Cb`, `CE`, `CT` | Annual costs with the exclusions and additions defined below |
| `e`, `eb`, `eE` | Annual emissions on one declared boundary |
| `fair_cost`, `fair_intensity` | Annual differences divided by actual hydrogen output |
| `storage_solution`, `dispatch_revision` | Frozen tariffs or convergence record, and any source correction applied equally to the paired cases |

For the chapter's GB operational-emissions comparison, use operational emissions consistently in `e` and `eb`. Retain equipment emissions separately; the source's combined emission variable can include both components.

For the formula above, define `C` and `Cb` to exclude the target electrolyser equipment charges and the separately added `CT`; then add each once:

```text
CE_GBP_per_year = (15 + 3) × electrolyser_capacity_kW
CT_GBP_per_year = 1 × E_input_MWh
eE_tonnes_per_year = 0
```

At 10 GW, `CE` is GBP 180 million/year. The archived class storing a capital/operating-cost parameter is not proof that the PSM annual total includes that charge. Conversely, if a recovered chapter postprocessor already includes it in `C`, adjust the ledger before adding `CE` again. Neither a sum of period bid payments nor the later CEM annual cost field can be assumed to equal the chapter's `C` without this reconciliation.

Subtract **annual totals**, not average system prices or carbon intensities with different denominators. Divide by actual annual hydrogen output only after subtraction. For a per-kg hydrogen result, divide either per-MWh hydrogen metric by 30. These fair metrics quantify the chapter's incremental system-accounting result; they are not automatically a producer's electricity bill, a conventional standalone LCOH or a social optimum.

### 5.1 Production categories and system boundary

Using annual hydrogen output for the same portfolio and electrolyser capacity:

```text
clean = after_storage
additionality = VRE_ahead - after_storage
dirty = on_grid - VRE_ahead
clean + additionality + dirty = on_grid

storage_diversion = before_storage - after_storage
ordinary_demand_diversion = VRE_ahead - before_storage
```

The thesis defines clean production by zero additional **GB operational emissions**. The difference between after-storage and after-inter can reduce exports and change export revenue or emissions displaced abroad; it remains within the chapter's domestic clean-production definition. The zero equipment-emission assumption does not imply a zero lifecycle footprint.

### 5.2 VRE-offset experiment: Figure 24

Record which VRE capacities are scaled and hold other exogenous assumptions fixed. The offset criterion compares the hydrogen scenario with additional VRE against the original no-hydrogen portfolio's **total annual emissions**:

```text
e_with_hydrogen(VRE_multiplier) = e_without_hydrogen(original_portfolio)
```

When displaying this comparison as intensity, divide both emission totals by the same electricity-consumption denominator used for the corresponding hydrogen scenario. Consequently, the plotted no-hydrogen reference can be lower than the original no-hydrogen system's own average intensity. This alignment is intentional. Preserve it; replacing that reference with the original average intensity changes the offset test. Publish both annual emission totals and the plotting denominator for every point.

## 6. Thesis checkpoints and output mapping

The following are **reported thesis values**, not results independently reproduced by this guide. Use them to locate mismatches after the inputs and accounting have been verified. They do not establish a numerical acceptance tolerance.

| Chapter 3 checkpoint | Current | Future |
| --- | ---: | ---: |
| Table 7 baseline system cost, GBP/MWh electricity | 54.91 | 62.30 |
| Table 7 baseline intensity, g CO2/kWh electricity | 154.39 | 44.79 |
| Main after-storage hydrogen output at 10 GW | 1.77 TWh (53.14 kt) | 25.90 TWh (777.00 kt) |
| Table 8 after-storage fair cost, GBP/MWh H2 | 70.93 | 14.90 |
| Table 8 after-storage fair intensity, kg CO2/MWh H2 | 0 | 0 |
| Table 8 on-grid fair cost, GBP/MWh H2 | 164.16 | 147.00 |
| Table 8 on-grid fair intensity, kg CO2/MWh H2 | 356.70 | 169.29 |

Rounded TWh and kt entries need not convert exactly at their displayed precision. At 10 GW and 65% efficiency, the theoretical full-year hydrogen upper bound is 56.94 TWh (1,708.20 kt); the thesis reports approximately 56.92 TWh (1,707.65 kt) for on-grid operation.

| Thesis output | Required saved results |
| --- | --- |
| Table 7 | Paired no-electrolysis baseline for each portfolio |
| Figure 20 | Annual output under on-grid, VRE-ahead and after-storage, plus the category differences above |
| Figures 21–22 | Timestamped generation and electrolyser electrical-power series for the plotted window |
| Figure 23 | Capacity sweep for on-grid, VRE-ahead and **after-inter**; its curtailment series is not the main after-storage case |
| Table 8 | Five strategies at 10 GW and the separate dedicated-wind comparator |
| Figure 24 | VRE multiplier, annual emissions and common-denominator offset comparison |
| Appendix 3A, Figure 25 | Ramp-up times of 0.5, 1, 2 and 4 hours, for 10 GW of electrolysers in the future system |
| Appendix 3B, Figure 26 | Gas/electrolyser-cost sensitivities; reported gas range GBP 10–50/MWh and annual electrolyser cost range GBP 18–90/kW; the retained curtailment series is **after-inter**, not after-storage |

For every run, preserve the source commit, environment/package record, input hashes, complete parameters, baseline ID, initial conditions and convergence history. Save period-level energy-balance components and an annual ledger containing at least hydrogen input/output, `C`, `Cb`, `CE`, `CT`, `e`, `eb`, `eE`, and the resulting fair metrics. Include a mapping from each plotted series/table row to its run and output file.

Check period energy balance, storage bounds, shared electrolyser capacity, the specified ramp behaviour, and annual unit conversions. The zero-electrolysis baseline must have no electricity diverted through any consumptive hydrogen path. Record numerical residuals and the tolerance used rather than presenting visually similar plots as sufficient verification.

## 7. Public-release requirements and the scope of this guide

The parameter tables, exact input manifest, time-reading conventions, five allocation rules, zero-hydrogen controls and fair-metric definitions are provided in this document. Readers also need the following repository assets to execute the procedure:

| Required asset | Availability at the pinned public commit and action needed |
| --- | --- |
| Chapter input data | The exact 16 files and hashes are listed in Section 2.2. Supply the named archive through a public release or an explicit maintainer delivery route, retaining upstream terms. The later private benchmark asset has a separate dataset identity. |
| Chapter parameter configurations | The thesis numerical specification is contained in Sections 2.1, 3.1 and 4.1. Publish the selected executable per-case settings alongside the chapter drivers, including storage stock units and any differences from the printed tables. |
| Chapter 2 and five Chapter 3 entry points | The public PSM routine and source interfaces are identified in Sections 3–4. Publish or identify the actual fixed-portfolio wrapper and each strategy driver, with their source revision and invocation. The public archive currently supplies no five-policy command. |
| Paired accounting and output mapping | Section 5 gives the calculation and required fields; Section 6 maps outputs to the thesis. Supply the actual extraction/plotting entry points with the selected driver revision. Record reference agreement only for calculations that have been compared. |

Uploading this MD makes the written parameter and procedure specification available. Access to the frozen data and callable chapter drivers remains a separate release requirement. The distinction prevents a description of five strategies from being mistaken for five implemented selections in the public model.

## Appendix A. Retained chapter weather-extraction coordinates

The entries below are the literal call arguments in the recovered future after-storage driver, source SHA-256 `8b011c1afe598d239e42138cd52b2bb0e1ea2942edaa1cfe0b454dedb16fa846`. Names identify the corresponding profile variables; coordinates are in decimal degrees. Installed capacities remain those of the selected portfolio. The latitude/longitude list fixes weather-extraction locations and supplies no additional capacity allocation.

| Profile variable | Latitude | Longitude |
| --- | ---: | ---: |
| `solar_limit_Nottingham` | 53.0 | -1.2 |
| `solar_limit_Ipswich` | 52.0567 | 1.1482 |
| `solar_limit_London` | 51.5072 | -0.1276 |
| `solar_limit_Newcastle` | 54.9783 | -1.6178 |
| `solar_limit_Manchester` | 53.4808 | -2.2426 |
| `solar_limit_Edinburgh` | 55.9533 | -3.1883 |
| `solar_limit_Portsmouth` | 50.8198 | -1.088 |
| `solar_limit_Bournemouth` | 50.722 | -1.8667 |
| `solar_limit_Cardiff` | 51.4837 | -3.1681 |
| `solar_limit_Birmingham` | 52.4862 | -1.8904 |
| `solar_limit_Sheffield` | 53.3811 | -1.4701 |
| `onshore_limit_Nottingham` | 53.0 | -1.2 |
| `onshore_limit_Ipswich` | 52.0567 | 1.1482 |
| `onshore_limit_London` | 51.5072 | -0.1276 |
| `onshore_limit_Newcastle` | 54.9783 | -1.6178 |
| `onshore_limit_Manchester` | 53.4808 | -2.2426 |
| `onshore_limit_Edinburgh` | 55.9533 | -3.1883 |
| `onshore_limit_Portsmouth` | 50.8198 | -1.088 |
| `onshore_limit_Bournemouth` | 50.722 | -1.8667 |
| `onshore_limit_Cardiff` | 51.4837 | -3.1681 |
| `onshore_limit_Birmingham` | 52.4862 | -1.8904 |
| `onshore_limit_Sheffield` | 53.3811 | -1.4701 |
| `offshore_limit1` | 51.749722 | 1.209167 |
| `offshore_limit2` | 54.043889 | -3.521944 |
| `offshore_limit3` | 53.92 | 1.56 |
| `offshore_limit4` | 54.043889 | -3.521944 |
| `offshore_limit5` | 54.060833 | -3.4325 |
| `offshore_limit6` | 51.88 | 1.94 |
| `offshore_limit7` | 51.643889 | 1.553611 |
| `offshore_limit8` | 53.153333 | 0.520278 |
| `offshore_limit9` | 53.173056 | 0.640833 |
| `offshore_limit10` | 53.98 | -3.46 |
| `offshore_limit11` | 50.6647 | -0.2789 |
| `offshore_limit12` | 58.133333 | -3.066667 |
| `offshore_limit13` | 52.1525 | 2.446389 |
| `offshore_limit14` | 53.885 | 1.791 |
| `offshore_limit15` | 56.449722 | -1.991389 |
| `offshore_limit16` | 54.044 | -3.522 |
| `offshore_limit17` | 58.16708 | -2.69852 |
| `offshore_limit18` | 53.483333 | -3.166667 |
| `offshore_limit19` | 53.643889 | 0.293056 |
| `offshore_limit20` | 53.81 | 0.15 |
| `offshore_limit21` | 53.164167 | 0.723333 |
| `planoff_limit1` | 52.7 | 2.859972 |
| `planoff_limit2` | 52.658889 | 2.149722 |
| `planoff_limit3` | 53.92 | 1.33 |
| `planoff_limit4` | 54.039972 | 1.27 |
| `planoff_limit5` | 52.6196 | 2.552 |
| `planoff_limit6` | 54.75 | 1.916667 |
| `planoff_limit7` | 56.2678 | -2.3208 |
| `planoff_limit8` | 56.425278 | -2.007222 |
| `planoff_limit9` | 56.588 | -1.741 |
| `planoff_limit10` | 54.75 | 1.916667 |
| `planoff_limit11` | 52.226111 | 2.288333 |
| `planoff_limit12` | 58.232778 | -2.814167 |
| `planoff_limit13` | 52.66 | 3.071389 |
| `planoff_limit14` | 55.005833 | 2.979722 |
| `planoff_limit15` | 53.000833 | 1.273889 |
| `planoff_limit16` | 53.279 | 1.374 |
| `planoff_limit17` | 53.465 | -3.803972 |
| `planoff_limit18` | 51.457972 | -5.602 |
| `planoff_limit19` | 56.470972 | -1.576 |
| `planoff_limit20` | 58.700556 | -3.849167 |
| `planoff_limit21` | 56.587778 | -2.126389 |
