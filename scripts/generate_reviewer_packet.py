#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INPUT_DIR = ROOT / "data" / "input"
OUTPUT_DIR = ROOT / "data" / "output"
SCENARIOS_DIR = ROOT / "data" / "pilot_scenarios"
PACKETS_DIR = ROOT / "data" / "reviewer_packets"
PACKETS_DIR.mkdir(parents=True, exist_ok=True)


def _load_json(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text())


def _fmt_money(value) -> str:
    try:
        return f"${float(value):,.2f}"
    except Exception:
        return str(value)


def _line(form: dict | None, line_no: str, default=0):
    if not form:
        return default
    lines = form.get("lines", {})
    return lines.get(line_no, {}).get("value", default)


def build_packet(name: str, input_dir: Path) -> str:
    from src.preflight import evaluate_input_dir
    from src.engine import calculate_2025

    pre = evaluate_input_dir(input_dir)

    taxpayer = _load_json(input_dir / "taxpayer.json") or {}
    w2 = ((_load_json(input_dir / "w2.json") or {}).get("forms", []))
    forms_1099 = {
        "1099-INT": len(((_load_json(input_dir / "1099_int.json") or {}).get("forms", []))),
        "1099-DIV": len(((_load_json(input_dir / "1099_div.json") or {}).get("forms", []))),
        "1099-NEC": len(((_load_json(input_dir / "1099_nec.json") or {}).get("forms", []))),
        "1099-MISC": len(((_load_json(input_dir / "1099_misc.json") or {}).get("forms", []))),
        "1099-B": len(((_load_json(input_dir / "1099_b.json") or {}).get("forms", []))),
    }

    if pre["hard_stop"]:
        body = [
            f"# Reviewer Packet — {name}",
            "",
            "## Status",
            "HARD STOP — Not review-ready.",
            "",
            "## Missing/Conflicting Items",
        ]
        body += [f"- {x}" for x in pre["missing_or_conflicting"]] or ["- None listed"]
        body += ["", "## Reviewer Flags"]
        body += [f"- {x}" for x in pre["reviewer_flags"]] or ["- None"]
        body += ["", "## Next Action", "- Provide missing/conflicting items and rerun."]
        body += ["", "## Not Submitted Confirmation", "- Return not submitted. Not e-filed."]
        return "\n".join(body) + "\n"

    result, audit = calculate_2025()
    data = json.loads(result.model_dump_json())
    form1040 = data.get("form_1040")

    body = [
        f"# Reviewer Packet — {name}",
        "",
        "## Return Type and Tax Year",
        "- Type: 1040-family pilot return",
        "- Tax year: 2025",
        "",
        "## Taxpayer Summary",
        f"- Taxpayer: {taxpayer.get('name', 'Unknown')}",
        f"- Filing status: {taxpayer.get('filing_status', 'unknown')}",
        f"- State (taxpayer): {taxpayer.get('state', 'unknown')}",
        f"- W-2 count: {len(w2)}",
        f"- 1099 counts: {', '.join([f'{k}={v}' for k, v in forms_1099.items()])}",
        "",
        "## Key Form 1040 Totals",
        f"- Taxable income (L15): {_fmt_money(_line(form1040,'15', data.get('taxable_income',0)))}",
        f"- Total tax (L24): {_fmt_money(_line(form1040,'24', data.get('total_tax',0)))}",
        f"- Total payments (L33): {_fmt_money(_line(form1040,'33', data.get('total_payments',0)))}",
        f"- Refund (L35a): {_fmt_money(_line(form1040,'35a', 0))}",
        f"- Amount owed (L37): {_fmt_money(_line(form1040,'37', 0))}",
        "",
        "## Reviewer Attention Flags",
    ]
    body += [f"- {x}" for x in pre["reviewer_flags"]] or ["- None"]

    body += ["", "## Engine Warnings / Assumptions"]
    body += [f"- {w}" for w in data.get("warnings", [])] or ["- None"]

    body += ["", "## Audit Trail (tail)"]
    body += [f"- {x}" for x in audit[-12:]]

    body += ["", "## Not Submitted Confirmation", "- Return not submitted. Not e-filed."]
    return "\n".join(body) + "\n"


def run_for_current_input() -> None:
    packet = build_packet("current_input", INPUT_DIR)
    out = PACKETS_DIR / "current_input.md"
    out.write_text(packet)
    print(out)


def run_for_scenarios() -> None:
    backup = ROOT / "data" / "_input_backup"
    if backup.exists():
        shutil.rmtree(backup)
    shutil.copytree(INPUT_DIR, backup)
    try:
        for scenario in sorted(SCENARIOS_DIR.iterdir()):
            if not scenario.is_dir():
                continue
            if INPUT_DIR.exists():
                shutil.rmtree(INPUT_DIR)
            shutil.copytree(scenario, INPUT_DIR)
            packet = build_packet(scenario.name, INPUT_DIR)
            out = PACKETS_DIR / f"{scenario.name}.md"
            out.write_text(packet)
            print(out)
    finally:
        if INPUT_DIR.exists():
            shutil.rmtree(INPUT_DIR)
        shutil.copytree(backup, INPUT_DIR)
        shutil.rmtree(backup, ignore_errors=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenarios", action="store_true", help="Generate packets for all pilot scenarios")
    args = ap.parse_args()
    if args.scenarios:
        run_for_scenarios()
    else:
        run_for_current_input()


if __name__ == "__main__":
    main()
