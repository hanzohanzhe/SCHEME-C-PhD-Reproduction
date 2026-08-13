#!/usr/bin/env python3
"""Re-run Scheme C Base + Base+CM with process-stable REPD completion years.

Uses the same planning-time fix as the three decarb runs:
  md5-stable digests in the model + PYTHONHASHSEED=0.

Scenarios (parallel pair):
  05 future_base          (basic, no CM)
  06 future_base_with_cm  (with CM)
"""
from __future__ import annotations

import glob
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

RUN_ID = os.getenv(
    "PHYSICAL_INCOME_RUN_ID",
    "20260719_base_cm_aligned_repd_virtual_pool_1000twh_scheme_c",
)
FUTURE_END_YEAR = int(os.getenv("FUTURE_END_YEAR", "2034"))
OUTPUT_ROOT = Path(
    os.getenv(
        "INCLUDE_UNCERTAIN_OUTPUT_ROOT",
        str(Path.home() / "Desktop" / "five_scenario_include_uncertain_freq_cap_runs"),
    )
)
STORAGE_EXPANSION_DIR = Path(
    os.getenv(
        "STORAGE_EXPANSION_MODULE_DIR",
        str(Path.home() / "Desktop" / "storage_expansion_corrected_caps"),
    )
)
STORAGE_CAP_CREDIT_MODE = os.getenv("STORAGE_CAP_CREDIT_MODE", "scheme_c")
LOG_DIR = OUTPUT_ROOT / "run_logs" / RUN_ID
QUEUE_LOG = LOG_DIR / "queue.log"

SCENARIO_GROUPS: list[tuple[str, ...]] = [
    ("05_future_base_2025_2035", "06_future_base_with_cm_2025_2035"),
]

SCENARIOS: dict[str, dict] = {
    "05_future_base_2025_2035": {
        "years": (2025, FUTURE_END_YEAR),
        "env": {
            "RUN_SUITE": "basic",
            "SCENARIO_V2": "0",
            "DECARB_SCENARIO": "future_base_2025_2035",
            "OUTPUT_SUFFIX": "future_base_2025_2035",
        },
    },
    "06_future_base_with_cm_2025_2035": {
        "years": (2025, FUTURE_END_YEAR),
        "env": {
            "RUN_SUITE": "with_cm",
            "SCENARIO_V2": "0",
            "DECARB_SCENARIO": "future_base_with_cm_2025_2035",
            "OUTPUT_SUFFIX": "future_base_with_cm_2025_2035",
        },
    },
}


def _find_model_parent() -> Path:
    pattern = str(
        Path.home()
        / "Desktop"
        / "Dr.seal"
        / "**"
        / "newpredictedVRE0.03 - sum - seperate prediction - 0.2c43_REPD2025_physical_income_fixed"
        / "decarbonization_cost_research"
        / "run_investment_analysis_case3_decarbonization_breakdown_cm.py"
    )
    hits = glob.glob(pattern, recursive=True)
    if not hits:
        raise FileNotFoundError("Could not locate REPD2025_physical_income_fixed model script")
    return Path(hits[0]).resolve().parent


PARENT = _find_model_parent()
MODEL_SCRIPT = PARENT / "run_investment_analysis_case3_decarbonization_breakdown_cm.py"


def _python_cmd() -> list[str]:
    if shutil.which("py"):
        return ["py", "-3.10", "-B", "-u", str(MODEL_SCRIPT)]
    return [sys.executable, "-B", "-u", str(MODEL_SCRIPT)]


def log(message: str) -> None:
    print(message, flush=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with QUEUE_LOG.open("a", encoding="utf-8", errors="replace") as handle:
        handle.write(message + "\n")


def base_env(output_dir: Path, start_year: int, end_year: int) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "PYTHONHASHSEED": "0",
            "START_YEAR": str(start_year),
            "END_YEAR": str(end_year),
            "OUTPUT_DIR": str(output_dir),
            "ENABLE_CHECKPOINT": "1",
            "PLANNING_USE_MEDIAN": "1",
            "PIPELINE_DEFER_SPREAD_YEARS": "3",
            "CAPITAL_COST_PROFILE": "arup_medium",
            "PHYSICAL_PERIOD_HOURS": "0.5",
            "FAST_ANALYSIS_OUTPUT": "1",
            "TRACE_FORMAT": "sqlite",
            "SAVE_GENERATION_TRACE": "1",
            "SAVE_MARKET_TRACE": "0",
            "MARKET_TRACE_RUN_ID": RUN_ID,
            "MARKET_TRACE_BASE_DIR": str(OUTPUT_ROOT),
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUNBUFFERED": "1",
            "VALIDATION_MODE": "0",
            "VALIDATION_DISABLE_EXTERNAL_PROJECTS": "0",
            "VALIDATION_HISTORICAL_DECARB": "0",
            "VALIDATION_INITIAL_CAPACITY_YEAR": "",
            "VALIDATION_REPD_FILE": "",
            "REPD_ZOMBIE_STATUS_STALE_YEAR": "2015",
            "REPD_ZOMBIE_SNAPSHOT_YEAR": str(start_year),
            "APPLY_REPD_INITIAL_SNAPSHOT": "1",
            "REPD_INCLUDE_UNCERTAIN_PROJECTS": "1",
            "REPD_UNCERTAIN_AS_MODEL_DECISION": "0",
            "STORAGE_EXPANSION_CAP_FRACTION": "0.20",
            "STORAGE_EXPANSION_MODULE_DIR": str(STORAGE_EXPANSION_DIR),
            "STORAGE_CAP_CREDIT_MODE": STORAGE_CAP_CREDIT_MODE,
            "STORAGE_CAP_METHOD": "scheme_c_sim_trace",
            "STORAGE_VIRTUAL_POOL_ENERGY_MWH": str(1000.0 * 1e6),
            "STORAGE_VIRTUAL_POOL_POWER_MW": "1e9",
            "MODEL_SUCCESS_MODE": "expected",
        }
    )
    return env


def _output_dir_for(key: str) -> Path:
    return OUTPUT_ROOT / f"{key}_{RUN_ID}"


def _scenario_complete(key: str) -> bool:
    log_path = LOG_DIR / f"{key}.log"
    if log_path.exists():
        text = log_path.read_text(encoding="utf-8", errors="replace")
        matches = re.findall(r"RETURN_CODE=(\d+)", text)
        if matches and int(matches[-1]) == 0:
            return True
    return False


def start_scenario(key: str) -> dict:
    spec = SCENARIOS[key]
    start_year, end_year = spec["years"]
    output_dir = _output_dir_for(key)
    ckpt = output_dir / "checkpoints"
    has_ckpt = ckpt.exists() and any(ckpt.glob("*_checkpoint.pkl"))
    resume = output_dir.exists() and not _scenario_complete(key) and has_ckpt
    output_dir.mkdir(parents=True, exist_ok=True)

    scenario_log = LOG_DIR / f"{key}.log"
    env = base_env(output_dir, start_year, end_year)
    env.update(spec["env"])

    cmd = _python_cmd()
    started = datetime.now().isoformat(timespec="seconds")
    mode = "a" if scenario_log.exists() else "w"
    handle = scenario_log.open(mode, encoding="utf-8", errors="replace")
    ckpt_files = sorted(ckpt.glob("*_checkpoint*.pkl")) if ckpt.exists() else []
    latest = max(ckpt_files, key=lambda p: p.stat().st_mtime).name if ckpt_files else "none"
    handle.write(
        f"\n{'=' * 80}\n"
        f"{'RESUMED' if resume else 'STARTED'}={started}\n"
        f"RUN_ID={RUN_ID}\nSCENARIO={key}\nOUTPUT_DIR={output_dir}\n"
        f"YEARS={start_year}-{end_year}\nPYTHONHASHSEED=0\n"
        f"REPD_TIMELINE_HASH=md5_stable\nCHECKPOINT={latest}\n"
        f"STORAGE_CAP_CREDIT_MODE={STORAGE_CAP_CREDIT_MODE}\n"
        f"CMD={' '.join(cmd)}\n{'=' * 80}\n"
    )
    handle.flush()

    popen_kwargs: dict = {
        "cwd": str(PARENT),
        "env": env,
        "stdout": handle,
        "stderr": subprocess.STDOUT,
        "text": True,
        "errors": "replace",
    }
    if sys.platform == "win32":
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

    proc = subprocess.Popen(cmd, **popen_kwargs)
    action = "Resumed" if resume else "Started"
    log(f"{action} {key}: pid={proc.pid}, output={output_dir}, checkpoint={latest}")
    return {
        "key": key,
        "proc": proc,
        "handle": handle,
        "log": str(scenario_log),
        "output_dir": str(output_dir),
        "started": started,
        "resumed": resume,
    }


def wait_scenarios(runs: list[dict]) -> list[dict]:
    live = list(runs)
    results: list[dict] = []
    while live:
        for run in list(live):
            proc: subprocess.Popen = run["proc"]
            rc = proc.poll()
            if rc is None:
                continue
            finished = datetime.now().isoformat(timespec="seconds")
            run["handle"].write(f"\n{'=' * 80}\nFINISHED={finished}\nRETURN_CODE={rc}\n")
            run["handle"].close()
            results.append(
                {
                    "scenario": run["key"],
                    "return_code": rc,
                    "started": run["started"],
                    "finished": finished,
                    "output_dir": run["output_dir"],
                    "log": run["log"],
                }
            )
            live.remove(run)
            log(f"Finished {run['key']} with return_code={rc}")
        if live:
            time.sleep(15)
    return results


def main() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log(f"RUN_ID={RUN_ID}")
    log(f"MODEL={MODEL_SCRIPT}")
    log(f"STORAGE_EXPANSION_MODULE_DIR={STORAGE_EXPANSION_DIR}")
    log("REPD timeline: md5-stable jitter + PYTHONHASHSEED=0")
    log("Scenarios: 05 Base + 06 Base with CM (Scheme C, 1000 TWh virtual pool)")

    sys.path.insert(0, str(PARENT))
    from run_investment_analysis import completion_year_from_months  # noqa: E402

    a = completion_year_from_months(2025, 24, "Dogger Bank A")
    b = completion_year_from_months(2025, 24, "Dogger Bank A")
    assert a == b
    log(f"Stable completion smoke: Dogger Bank A @24m from 2025 -> {a}")

    all_results: list[dict] = []
    for group in SCENARIO_GROUPS:
        pending = [k for k in group if not _scenario_complete(k)]
        if not pending:
            log(f"Skip complete group: {group}")
            continue
        log(f"Starting group: {', '.join(pending)}")
        runs = [start_scenario(k) for k in pending]
        all_results.extend(wait_scenarios(runs))

    manifest = {
        "run_id": RUN_ID,
        "finished": datetime.now().isoformat(timespec="seconds"),
        "planning": "md5_stable + PYTHONHASHSEED=0",
        "storage_cap": "scheme_c + 1000 TWh virtual pool",
        "results": all_results,
    }
    (LOG_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    log(f"Wrote {LOG_DIR / 'manifest.json'}")
    bad = [r for r in all_results if r["return_code"] != 0]
    if bad:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
