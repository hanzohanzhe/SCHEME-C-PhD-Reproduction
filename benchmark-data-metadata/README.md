# FORCE UK Benchmark Data

Private research-data companion for the FORCE power-system modelling platform.
This repository describes the frozen `force-uk-benchmark-2025-v1` asset used to
reproduce the UK Scheme C 1000 TWh model interfaces.

## Contents

- 25/25 FORCE data interfaces
- exact object byte counts and SHA-256 values
- source and licence register
- transformation and policy provenance
- semantic preflight evidence
- one versioned GitHub Release asset containing the data payload

The two large ERA5-derived NetCDF objects are distributed in the private
Release asset, not ordinary Git history. Download the asset, verify its SHA-256
against `release-manifest.json`, and extract it into the FORCE data-pack root.

## Scientific identity

- Data release: `force-uk-benchmark-2025-v1`
- Local source pack: `uk-scheme-c-1000twh`
- Source manifest SHA-256:
  `0098ea69257edb97ca84e0ce00e40b7cc2acb9ade2d449e0db55196d210ea995`

This is a private research benchmark, not a claim that every upstream object
has been relicensed by FORCE. See `LICENSING.md`, `SOURCE_REGISTER.md` and
`ATTRIBUTION.md` before sharing any object beyond authorised collaborators.
