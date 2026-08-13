# Scheme C 1000 TWh — PhD thesis reproduction archive

This public repository preserves the original Scheme C research model used for
the 1000 TWh virtual-storage-pool runs of 18–19 July 2026. Its purpose is to
reproduce and audit the numerical results associated with Hanzhe Xing's PhD
research. It is a historical baseline, not the modular FORCE application.

For Chinese instructions, see [README.zh-CN.md](README.zh-CN.md).

For the shortest installation path, see [docs/QUICKSTART.md](docs/QUICKSTART.md).
Public access covers the source, documentation and retained compact results.
Running the numerical model also requires the separately governed UK benchmark
archive; public repository access alone does not grant access to that data.

## What is here

| Path | Purpose | May it be edited? |
| --- | --- | --- |
| `original-model/` | Original PSM/CEM research implementation | No; create a new version instead |
| `external-storage/` | Original Scheme C storage-expansion-cap modules | No |
| `original-drivers/` | Original 18/19 July batch launchers | No |
| `reference-results/` | Compact outputs and logs from the retained five-scenario runs | No |
| `benchmark-data-metadata/` | Sources, rights and checksums for the separate UK data asset | Only through a new data release |
| `reproduction-tools/` | New portability, validation and execution helpers | Yes, through normal Git review |
| `docs/` | Provenance, result and versioning notes | Yes, with a new commit |

The historical files retain their original names, encoding, Windows paths and
research-era structure. The helpers never rewrite them. They make a disposable
copy under `work/` and run that copy.

## Model represented by this archive

- Great Britain is modelled as one node without internal transmission limits.
- Interconnectors are external import offers, not GB transmission branches.
- The PSM clears 17,520 half-hour periods per full year using continuous
  bid-at-cost competition between VRE, thermal plant, storage and imports.
- The original implementation omits unit start/stop, ramp, minimum-output and
  minimum up/down constraints.
- The CEM advances annually from the PSM result through agent investment,
  planning-pipeline completion, VRE expansion limits and storage expansion
  limits.
- The `1e9 MWh` (1000 TWh) and `1e9 MW` virtual storage pool is a diagnostic
  non-binding pool used to expose the cycle-frequency spectrum. It is not the
  installed physical storage capacity reported by the model.
- The retained storage-cap credit mode is `scheme_c`, and project success is
  represented using the expected-value mode used in the historical batch.

## Requirements

- Windows 10 or 11;
- Git (or a downloaded source ZIP);
- GitHub CLI (`gh`) authenticated to the data repository, or a local copy of
  the fixed UK benchmark archive;
- CPython 3.10.11 through the Windows `py` launcher;
- at least 5 GB free for the data, environment and a short run;
- substantially more space for full generation traces and checkpoints.

The full five-scenario ten-year reproduction can take one to several days,
depending on CPU and disk speed. Start with a one-year run.

## Fast installation

After cloning or downloading this repository, an authorised data user can
double-click `install-scheme-c.cmd`. It verifies the frozen archive, creates the
locked Python environment, downloads or accepts the fixed benchmark archive,
prepares a disposable work tree and mounts the historical weather path.

If you already have the benchmark ZIP, use:

```powershell
powershell -ExecutionPolicy Bypass -File reproduction-tools/install-scheme-c.ps1 `
  -ArchivePath "D:\path\force-uk-benchmark-2025-v1.zip"
```

An anonymous public user can clone the repository and run the integrity check,
but cannot complete a numerical reproduction until the separately governed data
asset is supplied. See [docs/QUICKSTART.md](docs/QUICKSTART.md) for the two access
levels and precise expected outcomes.

## Manual first-time setup

Open PowerShell in the repository root.

```powershell
# 1. Confirm that the historical files have not changed.
py -3.10 reproduction-tools/verify_repository.py

# 2. Create the accepted Python 3.10 environment.
powershell -ExecutionPolicy Bypass -File reproduction-tools/create-environment.ps1

# 3. Download the separately governed UK benchmark, or pass -ArchivePath,
#    and prepare a disposable work tree.
powershell -ExecutionPolicy Bypass -File reproduction-tools/prepare-data.ps1

# 4. Map the repository weather folder to the original model's F: path.
powershell -ExecutionPolicy Bypass -File reproduction-tools/mount-weather-drive.ps1
```

The data helper downloads
`force-uk-benchmark-2025-v1.zip` from the private repository
`hanzohanzhe/FORCE-UK-Benchmark-Data`, checks its fixed SHA-256, expands it
under `work/`, and places the original filenames beside the disposable model
copy. Nothing under `original-model/` is changed.

If the 842 MB ZIP is already available:

```powershell
powershell -ExecutionPolicy Bypass -File reproduction-tools/prepare-data.ps1 `
  -ArchivePath "D:\path\force-uk-benchmark-2025-v1.zip"
```

If `F:` already contains the two weather files with the retained hashes, the
mount helper verifies and reuses it without modification. If `F:` is used for
anything else, stop: the helper will not replace it. Use an isolated Windows
machine or virtual machine where `F:` can be assigned safely; changing the
historical source paths would create a new model version rather than reproduce
the archived version.

## Recommended first run

Run one full model year for the existing-decarbonisation-base scenario:

```powershell
powershell -ExecutionPolicy Bypass -File reproduction-tools/run-scheme-c.ps1 `
  -Scenario existing_decarb_base -StartYear 2025 -EndYear 2025
```

Results are written under `outputs/`, not into the historical source tree. The
command records the Git commit, data-asset hash, scenario and environment in a
run declaration before launching the original Python entry point.

Available scenario names are:

- `existing_decarb_base` (historical code 03);
- `subsidy_as_usual` (07);
- `governmental_target` (08);
- `base` (05);
- `base_with_cm` (06).

## Full 2025–2034 thesis benchmark

After the one-year run succeeds:

```powershell
powershell -ExecutionPolicy Bypass -File reproduction-tools/run-thesis-benchmark.ps1
```

The helper runs the five scenarios sequentially to avoid accidental resource
contention. The historical 18 July launcher ran 03 and 07 in parallel and then
08; the preserved original launcher is available for forensic inspection under
`original-drivers/`, but it contains the original machine's path-discovery
logic and is not the recommended portable command.

## What to compare

For each run compare at least:

1. `system_cost_history_*.csv`;
2. `capacity_history_*.csv`;
3. `thermal_capacity_history_*.csv`;
4. `investment_summary_*.csv`;
5. process completion and scenario declarations in the logs.

The retained files are described in [docs/RESULTS_GUIDE.md](docs/RESULTS_GUIDE.md).
An exact byte match is the strongest result. If a fresh environment differs,
report the Python/package versions, first divergent year and first divergent
field rather than overwriting the reference output.

## Scientific and licensing boundary

The six pre-recorded core/storage hashes match the earlier FORCE authoritative
source record. Other retained files are captured in the repository integrity
manifest. Evidence levels and environment limitations are documented in
[docs/PROVENANCE.md](docs/PROVENANCE.md).

Software is Apache-2.0. Documentation is CC BY 4.0. UK and third-party research
data retains its per-object terms and is distributed as a separate private
release asset. See `benchmark-data-metadata/SOURCE_REGISTER.md`.

Copyright owner: Hanzhe Xing (`hx279`). Stuart Scott and John Miles are
acknowledged as contributing supervisors and advisors.

## Version identity

Git commits and immutable annotated tags are the authoritative snapshots. The
initial scientific tag is `scheme-c-1000twh-2026-07-18_19`. See
[docs/GIT_VERSIONING.md](docs/GIT_VERSIONING.md).
