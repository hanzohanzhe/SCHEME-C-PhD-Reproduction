from __future__ import annotations

import ast
import hashlib
import json
import sys
import tokenize
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "provenance" / "integrity-manifest.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    expected = {entry["path"]: entry for entry in payload["files"]}
    actual_paths = set()
    errors: list[str] = []

    for root_name in payload["immutable_roots"]:
        for path in (ROOT / root_name).rglob("*"):
            if path.is_file():
                actual_paths.add(path.relative_to(ROOT).as_posix())

    missing = sorted(set(expected) - actual_paths)
    unexpected = sorted(actual_paths - set(expected))
    errors.extend(f"missing immutable file: {path}" for path in missing)
    errors.extend(f"unexpected immutable file: {path}" for path in unexpected)

    for relative, record in expected.items():
        path = ROOT / relative
        if not path.is_file():
            continue
        if path.stat().st_size != record["bytes"]:
            errors.append(f"size changed: {relative}")
            continue
        actual_hash = sha256(path)
        if actual_hash != record["sha256"]:
            errors.append(f"SHA-256 changed: {relative}")

    for relative, expected_hash in payload["authoritative_preexisting_sha256"].items():
        path = ROOT / relative
        if not path.is_file() or sha256(path) != expected_hash:
            errors.append(f"authoritative source mismatch: {relative}")

    for relative in sorted(actual_paths):
        if not relative.endswith(".py"):
            continue
        path = ROOT / relative
        try:
            with tokenize.open(path) as handle:
                ast.parse(handle.read(), filename=relative)
        except Exception as exc:  # pragma: no cover - diagnostic path
            errors.append(f"Python parse failure: {relative}: {exc}")

    for run in ("20260718", "20260719"):
        manifest = ROOT / "reference-results" / run / "run-evidence" / "manifest.json"
        if not manifest.is_file():
            errors.append(f"missing reference run manifest: {run}")
            continue
        run_payload = json.loads(manifest.read_text(encoding="utf-8"))
        failures = [item for item in run_payload.get("results", []) if item.get("return_code") != 0]
        if failures:
            errors.append(f"reference run {run} contains failed processes")

    if errors:
        print("Scheme C repository verification FAILED", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print(
        f"Scheme C repository verification passed: {len(expected)} immutable files, "
        f"{len(payload['authoritative_preexisting_sha256'])} authoritative historical hashes."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
