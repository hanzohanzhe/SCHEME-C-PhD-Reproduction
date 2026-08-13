# Validation status

Date: 13 August 2026

## Passed before publication

- The four archived core-model files match the authoritative SHA-256 values
  recorded when Scheme C was first packaged for FORCE.
- The two external storage-expansion files match their authoritative SHA-256
  values.
- All 56 immutable source, launcher, result and log artefacts match the new
  repository integrity manifest.
- Every archived Python file parses successfully.
- Both historical run manifests report return code 0 for all five scenarios.
- The 842,050,611-byte private benchmark asset passed SHA-256 verification.
- The data preparation helper expanded the asset and created the disposable
  original-filename model tree successfully.
- All PowerShell reproduction helpers passed parser validation.
- The existing `F:\newfinalweather` weather pair was independently checked
  against the retained wind and solar hashes and accepted without modification.

## Not rerun in this packaging session

The controlled local execution identity on the packaging machine could not
locate a usable `py -3.10` runtime. Therefore neither a fresh one-year run nor
the five-scenario ten-year benchmark was claimed during packaging. The
historical run outputs and successful process logs remain the numerical
reference. GitHub CI checks archive integrity with Python 3.10 on clean Windows
and Linux runners, but deliberately does not download the rights-governed data
or run the multi-hour model.

A new scientific replication requires:

1. private benchmark download and hash verification;
2. Python 3.10.11 environment creation;
3. a full 2025 run;
4. comparison with the retained 2025 result;
5. only then, the five 2025–2034 scenarios.

Do not describe a syntax check or a short diagnostic run as numerical
reproduction of the dissertation baseline.
