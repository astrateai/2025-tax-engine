#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
import hashlib
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INPUT_DIR = ROOT / "data" / "input"
SCENARIOS_DIR = ROOT / "data" / "pilot_scenarios"
REPORTS_DIR = ROOT / "data" / "pilot_reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def _git_head() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:
        return "unknown"


def _input_hash(input_dir: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(input_dir.glob("*.json")):
        h.update(p.name.encode())
        h.update(p.read_bytes())
    return h.hexdigest()


def snapshot_input(tmp_dir: Path) -> None:
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    shutil.copytree(INPUT_DIR, tmp_dir)


def restore_input(tmp_dir: Path) -> None:
    if INPUT_DIR.exists():
        shutil.rmtree(INPUT_DIR)
    shutil.copytree(tmp_dir, INPUT_DIR)


def apply_scenario(scenario_dir: Path) -> None:
    if INPUT_DIR.exists():
        shutil.rmtree(INPUT_DIR)
    shutil.copytree(scenario_dir, INPUT_DIR)


def run_scenario(name: str) -> dict:
    from src.engine import calculate_2025
    from src.preflight import evaluate_input_dir

    preflight = evaluate_input_dir(INPUT_DIR)
    if preflight["hard_stop"]:
        return {
            "scenario": name,
            "status": "hard_stop",
            "missing_or_conflicting": preflight["missing_or_conflicting"],
            "reviewer_flags": preflight["reviewer_flags"],
            "notice": {
                "required": preflight["missing_or_conflicting"],
                "next_action": "Provide missing/contradicting items, then rerun prep.",
            },
        }

    result, audit = calculate_2025()
    payload = {
        "scenario": name,
        "status": "ok",
        "warnings": result.warnings,
        "reviewer_flags": preflight["reviewer_flags"],
        "audit_tail": audit[-20:],
        "summary": {
            "taxable_income": float(result.form_1040.lines.get("15").value if result.form_1040 and result.form_1040.lines.get("15") else 0),
            "total_tax": float(result.form_1040.lines.get("24").value if result.form_1040 and result.form_1040.lines.get("24") else 0),
            "total_payments": float(result.form_1040.lines.get("33").value if result.form_1040 and result.form_1040.lines.get("33") else 0),
            "refund": float(result.form_1040.lines.get("35a").value if result.form_1040 and result.form_1040.lines.get("35a") else 0),
            "amount_owed": float(result.form_1040.lines.get("37").value if result.form_1040 and result.form_1040.lines.get("37") else 0),
        },
    }
    return payload


def main() -> None:
    backup = ROOT / "data" / "_input_backup"
    snapshot_input(backup)
    matrix = []
    try:
        for scenario_dir in sorted(SCENARIOS_DIR.iterdir()):
            if not scenario_dir.is_dir():
                continue
            name = scenario_dir.name
            apply_scenario(scenario_dir)
            manifest = {
                "scenario": name,
                "gitHead": _git_head(),
                "inputHash": _input_hash(INPUT_DIR),
            }
            try:
                report = run_scenario(name)
            except Exception as exc:
                report = {
                    "scenario": name,
                    "status": "error",
                    "error": str(exc),
                }
            report["manifest"] = manifest
            matrix.append(report)
            (REPORTS_DIR / f"{name}.json").write_text(json.dumps(report, indent=2) + "\n")
    finally:
        restore_input(backup)
        shutil.rmtree(backup, ignore_errors=True)

    (REPORTS_DIR / "pilot_matrix.json").write_text(json.dumps(matrix, indent=2) + "\n")
    print(json.dumps({"scenarios": len(matrix), "report": str(REPORTS_DIR / 'pilot_matrix.json')}, indent=2))


if __name__ == "__main__":
    main()
