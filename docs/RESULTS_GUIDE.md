# Reference-result guide

The retained runs cover five 2025–2034 scenarios.

| Code | Scenario | Meaning |
| --- | --- | --- |
| 03 | Existing decarbonisation base | Capacity Market plus the base decarbonisation pathway |
| 07 | Subsidy as usual | Continuation of the historical subsidy-expansion tendency |
| 08 | Governmental target | Expansion constrained toward the declared government target |
| 05 | Base | Base pathway without Capacity Market |
| 06 | Base with CM | Base pathway with Capacity Market |

Each scenario folder under `reference-results/` contains the compact outputs
needed for comparison:

- `system_cost_history_*.csv`: annual system cost and carbon-intensity series;
- `capacity_history_*.csv`: annual fleet and storage capacities;
- `thermal_capacity_history_*.csv`: thermal capacity trajectory;
- `investment_summary_*.csv`: agent-level annual investment results;
- `generation_manifest.json`: index and hashes for the original large
  generation trace.

The large SQLite generation traces are intentionally not committed to ordinary
Git. Their manifests and run logs are retained, while a rerun can regenerate the
traces. `run-evidence/manifest.json` records process return codes and the
historical output paths. The paths are evidence, not portable instructions.

For the 18 July run, scenarios 03 and 07 were launched in parallel, followed by
08. The logs show roughly 17 hours for the first pair and another 15 hours for
08 on the original machine. A full replication should therefore be planned as
a multi-hour or multi-day task and should retain checkpoints.
