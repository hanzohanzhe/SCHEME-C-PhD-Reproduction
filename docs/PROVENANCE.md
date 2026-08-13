# Provenance and scientific boundary

## What is frozen

This archive preserves the research implementation used for the retained
Scheme C 1000 TWh runs dated 18 and 19 July 2026. The files under
`original-model/`, `external-storage/`, `original-drivers/` and
`reference-results/` are historical artefacts. They are not cleaned, renamed or
made portable in place.

The original model contains hard-coded Windows paths, legacy positional result
indices and research-era logging. Those features are part of the archived
implementation. Portability is supplied separately under `reproduction-tools/`.

## Evidence levels

Six files have pre-existing authoritative SHA-256 evidence from the FORCE
packaging record:

| File | SHA-256 |
| --- | --- |
| `original-model/run_investment_analysis_case3_decarbonization_breakdown_cm.py` | `e0e11057715f5f26a99e804fdd7d9fa386a9b744c85174965584695060d373c9` |
| `original-model/run_investment_analysis.py` | `81446a975e51983aef6806a64ca1e5e7bbd70efc97903d8a08b6c9691697e528` |
| `original-model/simulation_model.py` | `434f43ca9607ba1b9588826c924d48755965ad99bcf4b3dc0e13089a512e3da0` |
| `original-model/config.py` | `587ad317e89305fb60342ed06cd309ee79a00df3e3bcc7dbc2f235fe63478de5` |
| `external-storage/storage_expansion_cap.py` | `fd8bdfa1bc71d40334d2bd8ebe88012c7489806c09af9aa7ced33f73a0f60279` |
| `external-storage/apply_storage_expansion.py` | `fef44e1ae5fbf42491a1efb3a225a5d4a472378d72eb2d6a8be51023fae3e654` |

The remaining support files were captured from the same retained research tree
and are hashed in `provenance/integrity-manifest.json`. The two launcher files
match the recorded run identifiers and environment declarations, but no
independent launcher hash was captured at execution time. The preserved run
logs therefore remain the strongest evidence of the commands and environment
actually executed.

## Data boundary

The approximately 842 MB UK benchmark is not stored in Git history. It is a
separate private GitHub Release in `hanzohanzhe/FORCE-UK-Benchmark-Data`, with
per-object sources and rights recorded under `benchmark-data-metadata/`.

Release asset SHA-256:
`0bc3a78d535fbb6198ee16d708343e6d70a01de76fa2e5459ffb27cebd2cb672`.

## Environment boundary

The historical logs prove that CPython 3.10 was used. They do not contain a
complete pip freeze. `requirements-py310.txt` is the later reconstructed and
CI-tested compatibility environment used for retained-model verification. This
distinction must be retained in publications and replication reports.

## Relationship to FORCE

Scheme C is the frozen dissertation-era research implementation. FORCE is the
later modular software platform derived from that research structure. A FORCE
run is not automatically an exact Scheme C reproduction, even when it selects a
legacy storage tariff. This repository exists so the historical baseline stays
independently inspectable and reproducible.
