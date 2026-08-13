# UK local data source register

This register describes the installed 25-role Scheme C data pack without copying or modifying it. A local file is usable by the model but is not automatically approved for public redistribution.

- Local pack: `uk-scheme-c-1000twh`
- Manifest SHA-256: `0098ea69257edb97ca84e0ce00e40b7cc2acb9ade2d449e0db55196d210ea995`
- Roles present: 25/25
- Sources identified: 25/25
- Objects included in a public archive: 0

| Role | Local file | Source | Licence label | Public treatment |
| --- | --- | --- | --- | --- |
| `fleet.generators` | `files/fleet__generators/fleet.json` | Hanzhe Xing / FORCE — Scheme C existing-fleet assumptions | Apache-2.0 for the owner-authored software configuration | owner_licensed_configuration_source_evidence_to_strengthen |
| `demand.forecast` | `files/demand__forecast/2022fd.csv` | National Grid ESO (now NESO) — 1-Day Ahead Demand Forecast | NESO Open Data Licence v1.0 | redistributable_neso_open_licence_with_attribution |
| `demand.real` | `files/demand__real/2022reald.csv` | National Grid ESO (now NESO) — Historic Demand Data | NESO Open Data Licence v1.0 | redistributable_neso_open_licence_with_attribution |
| `weather.wind` | `files/weather__wind/average_annual_wind_profile.nc` | Copernicus Climate Change Service / ECMWF — ERA5 hourly data on single levels | CC-BY-4.0 | redistributable_cc_by_4_with_attribution |
| `weather.solar` | `files/weather__solar/average_annual_solar_profile.nc` | Copernicus Climate Change Service / ECMWF — ERA5 hourly data on single levels | CC-BY-4.0 | redistributable_cc_by_4_with_attribution |
| `market.france.profile` | `files/market__france__profile/France_profile.csv` | National Grid ESO (now NESO) — Historic Demand Data | NESO Open Data Licence v1.0 | redistributable_neso_open_licence_with_attribution |
| `market.france.price` | `files/market__france__price/France.csv` | Ember — European Wholesale Electricity Price Data | CC-BY-4.0 | redistributable_cc_by_4_with_attribution |
| `market.belgium.profile` | `files/market__belgium__profile/belgium_profile.csv` | National Grid ESO (now NESO) — Historic Demand Data | NESO Open Data Licence v1.0 | redistributable_neso_open_licence_with_attribution |
| `market.belgium.price` | `files/market__belgium__price/Belgium_price.csv` | Ember — European Wholesale Electricity Price Data | CC-BY-4.0 | redistributable_cc_by_4_with_attribution |
| `market.netherlands.profile` | `files/market__netherlands__profile/nehtheralnd_profile.csv` | National Grid ESO (now NESO) — Historic Demand Data | NESO Open Data Licence v1.0 | redistributable_neso_open_licence_with_attribution |
| `market.netherlands.price` | `files/market__netherlands__price/Netherlands.csv` | Ember — European Wholesale Electricity Price Data | CC-BY-4.0 | redistributable_cc_by_4_with_attribution |
| `market.norway.profile` | `files/market__norway__profile/Norway_profile.csv` | National Grid ESO (now NESO) — Historic Demand Data | NESO Open Data Licence v1.0 | redistributable_neso_open_licence_with_attribution |
| `market.norway.price` | `files/market__norway__price/Norway.csv` | Ember — European Wholesale Electricity Price Data | CC-BY-4.0 | redistributable_cc_by_4_with_attribution |
| `market.ireland.profile` | `files/market__ireland__profile/Ireland_profile.csv` | National Grid ESO (now NESO) — Historic Demand Data | NESO Open Data Licence v1.0 | redistributable_neso_open_licence_with_attribution |
| `market.ireland.price` | `files/market__ireland__price/Ireland.csv` | Ember — European Wholesale Electricity Price Data | CC-BY-4.0 | redistributable_cc_by_4_with_attribution |
| `profiles.vre_solar` | `files/profiles__vre_solar/sa.csv` | Copernicus Climate Change Service / ECMWF — ERA5 hourly data on single levels | CC-BY-4.0 | redistributable_cc_by_4_with_attribution |
| `profiles.vre_onshore` | `files/profiles__vre_onshore/wa.csv` | Copernicus Climate Change Service / ECMWF — ERA5 hourly data on single levels | CC-BY-4.0 | redistributable_cc_by_4_with_attribution |
| `profiles.vre_offshore` | `files/profiles__vre_offshore/we.csv` | Copernicus Climate Change Service / ECMWF — ERA5 hourly data on single levels | CC-BY-4.0 | redistributable_cc_by_4_with_attribution |
| `projects.repd` | `files/projects__repd/repd_projects_normalized.csv` | Department for Energy Security and Net Zero — Renewable Energy Planning Database quarterly extract | OGL-UK-3.0 | redistributable_ogl_uk_3_with_attribution |
| `source.repd_raw` | `files/source__repd_raw/repd-q2-jul-2025.csv` | Department for Energy Security and Net Zero — Renewable Energy Planning Database quarterly extract | OGL-UK-3.0 | redistributable_ogl_uk_3_with_attribution |
| `costs.capital` | `files/costs__capital/capital_costs.json` | Hanzhe Xing / FORCE — Scheme C capital-cost assumptions (Arup medium profile) | Apache-2.0 for the owner-authored software configuration | owner_licensed_configuration_source_evidence_to_strengthen |
| `policy.support` | `files/policy__support/mechansim cost.xlsx` | Hanzhe Xing aggregation from UK public-policy sources — Capacity Market, balancing and decarbonisation support-cost workbook | CC-BY-4.0 for the owner-authored aggregation and projections; upstream public facts retain source terms | owner_licensed_research_input_with_column_sources |
| `planning.timelines` | `files/planning__timelines/planning_timelines.json` | Department for Energy Security and Net Zero — Renewable Energy Planning Database quarterly extract | OGL-UK-3.0 | redistributable_ogl_uk_3_with_attribution |
| `planning.success_rates` | `files/planning__success_rates/regional_technology_success_rates.csv` | Department for Energy Security and Net Zero — Renewable Energy Planning Database quarterly extract | OGL-UK-3.0 | redistributable_ogl_uk_3_with_attribution |
| `config.model_parameters` | `files/config__model_parameters/model_parameters.json` | Hanzhe Xing / FORCE — Scheme C investment, storage and policy parameters | Apache-2.0 for the owner-authored software configuration | owner_licensed_software_configuration |

## Provenance rules

- The existing installed pack remains the runtime source of truth; this audit writes only publication metadata.
- DESNZ REPD derivatives retain OGL attribution, and the raw table is not placed in a public archive before excluded-rights and personal-data review.
- NESO licensing is checked per dataset; the portal-level licence page alone is not treated as proof for every acquired object.
- ERA5 adaptations retain DOI, product, variables, year and adaptation wording.
- Ember wholesale-price inputs are CC-BY-4.0 with attribution. The policy workbook is an owner-authored CC-BY-4.0 research input; its approximate and projected cells remain scientifically qualified in policy-provenance.json.
- Apache-2.0 for FORCE software does not relicense upstream data.

See `local-source-inventory.json` for hashes, transformation notes, source URLs and attribution text.
