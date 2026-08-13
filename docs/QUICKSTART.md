# Scheme C reproduction quick start

This repository has two distinct access levels. Keeping them separate prevents
the public source archive from making a false promise about third-party data.

## A. Public audit — no benchmark data required

You need Windows 10/11 and CPython 3.10.11. Git is optional if you download the
repository ZIP.

```powershell
git clone https://github.com/hanzohanzhe/SCHEME-C-PhD-Reproduction.git
cd SCHEME-C-PhD-Reproduction
py -3.10 reproduction-tools/verify_repository.py
```

Expected result: the integrity checker confirms the frozen files and six
authoritative historical hashes. You can then inspect the original PSM/CEM,
the retained launchers, reference results, logs, licences and provenance.

This level does **not** run the numerical model.

## B. Full numerical reproduction — benchmark data required

In addition to Windows and Python, allow at least 5 GB of free space and obtain
the exact `force-uk-benchmark-2025-v1.zip` archive. Its required SHA-256 is:

```text
0bc3a78d535fbb6198ee16d708343e6d70a01de76fa2e5459ffb27cebd2cb672
```

You can obtain it in either of two ways:

1. be granted access to `hanzohanzhe/FORCE-UK-Benchmark-Data`, install and
   authenticate GitHub CLI (`gh`), then double-click `install-scheme-c.cmd`; or
2. receive the fixed ZIP through an authorised channel and run:

```powershell
powershell -ExecutionPolicy Bypass -File reproduction-tools/install-scheme-c.ps1 `
  -ArchivePath "D:\path\force-uk-benchmark-2025-v1.zip"
```

The installer verifies the immutable source, builds `.venv`, verifies the data
hash, creates a disposable `work/` tree and mounts the historical `F:` weather
path. It never edits `original-model/`, `external-storage/`,
`original-drivers/` or `reference-results/`.

If `F:` is already used for unrelated files, stop. Use a Windows machine or VM
where that drive letter can be assigned safely.

Run one year before attempting the full benchmark:

```powershell
powershell -ExecutionPolicy Bypass -File reproduction-tools/run-scheme-c.ps1 `
  -Scenario existing_decarb_base -StartYear 2025 -EndYear 2025
```

Only after that succeeds, run all five ten-year scenarios:

```powershell
powershell -ExecutionPolicy Bypass -File reproduction-tools/run-thesis-benchmark.ps1
```

## Current public-install boundary

The repository itself is public. The exact UK research data asset remains a
separate rights-governed release and is not anonymously downloadable. Therefore
the current public release supports anonymous source audit and result
inspection, while full numerical reproduction requires data access. This is an
access limitation, not a hidden code dependency.

For result interpretation, see [RESULTS_GUIDE.md](RESULTS_GUIDE.md). For the
scientific evidence boundary, see [PROVENANCE.md](PROVENANCE.md) and
[VALIDATION_STATUS.md](VALIDATION_STATUS.md).
