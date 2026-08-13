from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "provenance" / "integrity-manifest.json"
IMMUTABLE_ROOTS = (
    "original-model",
    "external-storage",
    "original-drivers",
    "reference-results",
)
AUTHORITATIVE = {
    "original-model/run_investment_analysis_case3_decarbonization_breakdown_cm.py": "e0e11057715f5f26a99e804fdd7d9fa386a9b744c85174965584695060d373c9",
    "original-model/run_investment_analysis.py": "81446a975e51983aef6806a64ca1e5e7bbd70efc97903d8a08b6c9691697e528",
    "original-model/simulation_model.py": "434f43ca9607ba1b9588826c924d48755965ad99bcf4b3dc0e13089a512e3da0",
    "original-model/config.py": "587ad317e89305fb60342ed06cd309ee79a00df3e3bcc7dbc2f235fe63478de5",
    "external-storage/storage_expansion_cap.py": "fd8bdfa1bc71d40334d2bd8ebe88012c7489806c09af9aa7ced33f73a0f60279",
    "external-storage/apply_storage_expansion.py": "fef44e1ae5fbf42491a1efb3a225a5d4a472378d72eb2d6a8be51023fae3e654",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    records = []
    for root_name in IMMUTABLE_ROOTS:
        for path in sorted((ROOT / root_name).rglob("*")):
            if not path.is_file():
                continue
            records.append(
                {
                    "path": path.relative_to(ROOT).as_posix(),
                    "bytes": path.stat().st_size,
                    "sha256": sha256(path),
                }
            )
    payload = {
        "schema_version": "scheme-c.integrity-manifest/v1",
        "captured_at": "2026-08-13",
        "source_release": "scheme-c-1000twh-2026-07-18_19",
        "immutable_roots": list(IMMUTABLE_ROOTS),
        "authoritative_preexisting_sha256": AUTHORITATIVE,
        "benchmark_asset": {
            "repository": "hanzohanzhe/FORCE-UK-Benchmark-Data",
            "release_tag": "force-uk-benchmark-2025-v1",
            "filename": "force-uk-benchmark-2025-v1.zip",
            "bytes": 842050611,
            "sha256": "0bc3a78d535fbb6198ee16d708343e6d70a01de76fa2e5459ffb27cebd2cb672",
        },
        "files": records,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(records)} immutable records to {OUTPUT}")


if __name__ == "__main__":
    main()
