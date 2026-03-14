"""Schema + contradiction validator for pilot gating."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text())


def validate_input_dir(input_dir: Path) -> dict[str, list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    taxpayer = _load_json(input_dir / "taxpayer.json") or {}
    if not taxpayer.get("name"):
        errors.append("taxpayer.name is required")
    if not taxpayer.get("ssn"):
        errors.append("taxpayer.ssn is required")
    if taxpayer.get("filing_status") != "married_filing_jointly":
        errors.append("Only married_filing_jointly is supported in pilot")

    w2_forms = ((_load_json(input_dir / "w2.json") or {}).get("forms", []))
    for i, w2 in enumerate(w2_forms):
        wages = float(w2.get("wages", 0) or 0)
        ss_wages = float(w2.get("social_security_wages", 0) or 0)
        ss_withheld = float(w2.get("social_security_withheld", 0) or 0)
        med_wages = float(w2.get("medicare_wages", 0) or 0)
        med_withheld = float(w2.get("medicare_withheld", 0) or 0)

        if wages < 0 or ss_wages < 0 or med_wages < 0:
            errors.append(f"w2.forms[{i}] has negative wage value")
        if abs(ss_withheld - (ss_wages * 0.062)) > 5:
            warnings.append(f"w2.forms[{i}] social security withheld appears inconsistent with wages")
        if abs(med_withheld - (med_wages * 0.0145)) > 5:
            warnings.append(f"w2.forms[{i}] medicare withheld appears inconsistent with wages")

    f1099b = ((_load_json(input_dir / "1099_b.json") or {}).get("forms", []))
    for fi, form in enumerate(f1099b):
        txs = form.get("transactions", [])
        if len(txs) == 0:
            warnings.append(f"1099_b.forms[{fi}] has no transactions")
        for ti, tx in enumerate(txs):
            if tx.get("proceeds") is None or tx.get("cost_basis") is None:
                errors.append(f"1099_b.forms[{fi}].transactions[{ti}] missing proceeds/cost_basis")

    # duplicate-ish payer/entity warning
    k1_files = list(input_dir.glob("k1_*.json"))
    k1_entities = set()
    for p in k1_files:
        payload = _load_json(p) or {}
        name = (payload.get("entity_name") or "").strip().lower()
        if name:
            k1_entities.add(name)

    div_payers = {str((f.get("payer") or "")).strip().lower() for f in ((_load_json(input_dir / "1099_div.json") or {}).get("forms", []))}
    overlaps = sorted([x for x in k1_entities if x and x in div_payers])
    if overlaps:
        warnings.append(f"Potential duplicated portfolio income sources across K-1 and 1099-DIV: {overlaps}")

    return {"errors": errors, "warnings": warnings}
