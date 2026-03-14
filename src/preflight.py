"""Preflight guardrails for Kevin-style review-ready gating."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .validator import validate_input_dir


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _load_coverage_lock() -> dict[str, Any]:
    path = Path(__file__).resolve().parent.parent / "config" / "coverage_lock.json"
    return _load_json(path) or {}


def evaluate_input_dir(input_dir: Path) -> dict[str, Any]:
    """
    Returns:
      {
        "hard_stop": bool,
        "missing_or_conflicting": [str],
        "reviewer_flags": [str],
      }
    """
    missing_or_conflicting: list[str] = []
    reviewer_flags: list[str] = []

    taxpayer = _load_json(input_dir / "taxpayer.json") or {}
    filing_status = (taxpayer.get("filing_status") or "").strip()
    if filing_status != "married_filing_jointly":
        missing_or_conflicting.append(
            "Unsupported filing status for current pilot boundary: "
            f"'{filing_status or 'missing'}'. Supported: married_filing_jointly."
        )

    # Load common income docs
    w2 = (_load_json(input_dir / "w2.json") or {}).get("forms", [])
    f1099_nec = (_load_json(input_dir / "1099_nec.json") or {}).get("forms", [])
    f1099_misc = (_load_json(input_dir / "1099_misc.json") or {}).get("forms", [])
    f1099_int = (_load_json(input_dir / "1099_int.json") or {}).get("forms", [])
    f1099_div = (_load_json(input_dir / "1099_div.json") or {}).get("forms", [])
    f1099_b = (_load_json(input_dir / "1099_b.json") or {}).get("forms", [])

    k1_files = list(input_dir.glob("k1_*.json"))

    has_income_docs = any(
        [
            len(w2) > 0,
            len(f1099_nec) > 0,
            len(f1099_misc) > 0,
            len(f1099_int) > 0,
            len(f1099_div) > 0,
            len(f1099_b) > 0,
            len(k1_files) > 0,
        ]
    )

    if not has_income_docs:
        missing_or_conflicting.append(
            "No income documents found (W-2/1099/K-1). Cannot produce review-ready return."
        )

    # Basic identity minima
    if not taxpayer.get("name") or not taxpayer.get("ssn"):
        missing_or_conflicting.append("Missing taxpayer identity fields (name and/or SSN).")

    # Schema + contradiction validation
    validation = validate_input_dir(input_dir)
    missing_or_conflicting.extend(validation.get("errors", []))
    reviewer_flags.extend(validation.get("warnings", []))

    # Coverage lock policy
    coverage = _load_coverage_lock()
    unsupported = set(coverage.get("unsupported_or_not_implemented", []))
    if "form_2210" in unsupported:
        reviewer_flags.append("Coverage lock: Form 2210 is unsupported in pilot.")
    if "form_6251_amt" in unsupported:
        reviewer_flags.append("Coverage lock: AMT/Form 6251 is unsupported in pilot.")

    # State complexity guardrail (pilot mode C: reviewer flag first)
    taxpayer_state = (taxpayer.get("state") or "").strip().upper()
    w2_states = {str(f.get("state", "")).strip().upper() for f in w2 if f.get("state")}
    w2_states.discard("")

    if len(w2_states) > 1:
        reviewer_flags.append(
            f"Multi-state wage exposure detected in W-2s: {sorted(w2_states)}."
        )
    if taxpayer_state and w2_states and taxpayer_state not in w2_states:
        reviewer_flags.append(
            f"Taxpayer state '{taxpayer_state}' differs from W-2 state set {sorted(w2_states)}."
        )
    if "VA" in w2_states or taxpayer_state == "VA":
        reviewer_flags.append("VA state handling requires mandatory reviewer validation in pilot.")
    if "TX" in w2_states or taxpayer_state == "TX":
        reviewer_flags.append("TX state handling requires mandatory reviewer validation in pilot.")

    return {
        "hard_stop": len(missing_or_conflicting) > 0,
        "missing_or_conflicting": missing_or_conflicting,
        "reviewer_flags": reviewer_flags,
    }
