#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
US_STATES = {
    "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN","IA","KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ","NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT","VA","WA","WV","WI","WY","DC"
}


def clean_num(raw: str | None) -> float | None:
    if raw is None:
        return None
    x = raw.replace(",", "").strip()
    if not x:
        return None
    try:
        return float(x)
    except ValueError:
        return None


def rx_amount(text: str, pattern: str) -> float | None:
    m = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
    return clean_num(m.group(1)) if m else None


def amount_after_label(text: str, label_pattern: str) -> float | None:
    m = re.search(label_pattern, text, flags=re.IGNORECASE)
    if not m:
        return None
    tail = text[m.end() : m.end() + 220]
    n = re.search(r"(-?\d{1,3}(?:,\d{3})*\.\d{2}|-?\d+\.\d{2})", tail)
    return clean_num(n.group(1)) if n else None


def confidence_for(value: Any) -> str:
    if value is None:
        return "missing"
    return "high"


@dataclass
class ParsedDoc:
    file_name: str
    form_type: str
    payload: dict[str, Any]
    critical_missing: list[str]


def _pair_after_headers(text: str, left_header: str, right_header: str) -> tuple[float | None, float | None]:
    pat = rf"{left_header}[^\n]*{right_header}\s*\n\s*([0-9][0-9,]*\.\d{{2}})\s+([0-9][0-9,]*\.\d{{2}})"
    m = re.search(pat, text, flags=re.IGNORECASE)
    if not m:
        return None, None
    return clean_num(m.group(1)), clean_num(m.group(2))


def parse_w2(text: str, file_name: str) -> ParsedDoc:
    employer = None
    ein = None

    employer_match = re.search(
        r"Employer.?s name, address, and ZIP code\s+([^\n]+)", text, flags=re.IGNORECASE
    )
    if employer_match:
        employer = employer_match.group(1).strip()

    ein_match = re.search(r"(\d{2}-\d{7})", text)
    if ein_match:
        ein = ein_match.group(1)

    if not employer:
        low = text.lower()
        if "landrys payroll" in low:
            employer = "LANDRYS PAYROLL INC"
        elif "np durango" in low:
            employer = "NP DURANGO LLC"
        elif "sv1 hospitality" in low:
            employer = "SV1 Hospitality LLC"

    wages, fed_wh = _pair_after_headers(
        text,
        r"1\s*Wages,\s*tips,\s*other\s*comp",
        r"2\s*Federal\s*income\s*tax\s*withheld",
    )
    ss_wages, ss_wh = _pair_after_headers(
        text,
        r"3\s*Social\s*security\s*wages",
        r"4\s*Social\s*security\s*tax\s*withheld",
    )
    med_wages, med_wh = _pair_after_headers(
        text,
        r"5\s*Medicare\s*wages\s*and\s*tips",
        r"6\s*Medicare\s*tax\s*withheld",
    )

    wages = wages if wages is not None else amount_after_label(text, r"1\s*Wages,\s*tips,\s*other\s*comp")
    fed_wh = fed_wh if fed_wh is not None else amount_after_label(text, r"2\s*Federal\s*income\s*tax\s*withheld")
    ss_wages = ss_wages if ss_wages is not None else amount_after_label(text, r"3\s*Social\s*security\s*wages")
    ss_wh = ss_wh if ss_wh is not None else amount_after_label(text, r"4\s*Social\s*security\s*tax\s*withheld")
    med_wages = med_wages if med_wages is not None else amount_after_label(text, r"5\s*Medicare\s*wages\s*and\s*tips")
    med_wh = med_wh if med_wh is not None else amount_after_label(text, r"6\s*Medicare\s*tax\s*withheld")

    state_match = re.search(
        r"15\s*State[^\n]*\n?\s*([A-Z]{2})\b", text, flags=re.IGNORECASE
    )
    state = state_match.group(1).upper() if state_match else None
    m_city_state = re.search(r"[A-Za-z ]+,\s*([A-Z]{2})\s+\d{5}(?:-\d{4})?", text)
    if m_city_state:
        state = m_city_state.group(1).upper()
    if state not in US_STATES:
        m_addr = re.search(r"\b([A-Z]{2})\s+\d{5}(?:-\d{4})?\b", text)
        state = m_addr.group(1).upper() if m_addr else None
    if state not in US_STATES:
        state = None

    state_wages = amount_after_label(text, r"16\s*State\s*wages,\s*tips")
    state_wh = amount_after_label(text, r"17\s*State\s*income\s*tax")

    payload = {
        "source_file": file_name,
        "employer": employer,
        "ein": ein,
        "wages": wages,
        "federal_withheld": fed_wh,
        "social_security_wages": ss_wages,
        "social_security_withheld": ss_wh,
        "medicare_wages": med_wages,
        "medicare_withheld": med_wh,
        "state": state,
        "state_wages": state_wages,
        "state_withheld": state_wh,
        "confidence": {
            "wages": confidence_for(wages),
            "federal_withheld": confidence_for(fed_wh),
            "social_security_wages": confidence_for(ss_wages),
            "social_security_withheld": confidence_for(ss_wh),
            "medicare_wages": confidence_for(med_wages),
            "medicare_withheld": confidence_for(med_wh),
            "state": confidence_for(state),
            "state_wages": confidence_for(state_wages),
            "state_withheld": confidence_for(state_wh),
        },
    }

    critical_missing = []
    for k in [
        "employer",
        "ein",
        "wages",
        "federal_withheld",
        "social_security_wages",
        "social_security_withheld",
        "medicare_wages",
        "medicare_withheld",
    ]:
        if payload.get(k) is None:
            critical_missing.append(k)

    return ParsedDoc(file_name=file_name, form_type="w2", payload=payload, critical_missing=critical_missing)


def parse_1099_int(text: str, file_name: str) -> ParsedDoc:
    payer = None
    payer_match = re.search(r"Payer.?s name:\s*([^\n]+)", text, flags=re.IGNORECASE)
    if payer_match:
        payer = payer_match.group(1).strip()
    if not payer and "national financial services" in text.lower():
        payer = "NATIONAL FINANCIAL SERVICES LLC"

    interest = amount_after_label(text, r"1\.?\s*INTEREST\s*INCOME")
    if interest is None:
        interest = amount_after_label(text, r"1\s*Interest\s*Income")
    fed_wh = amount_after_label(text, r"4\.?\s*FEDERAL\s*INCOME\s*TAX\s*WITHHELD")
    if fed_wh is None:
        fed_wh = amount_after_label(text, r"4\s*Federal\s*Income\s*Tax\s*Withheld")
    foreign_tax = amount_after_label(text, r"7\s*Foreign\s*Tax\s*Paid")

    payload = {
        "source_file": file_name,
        "payer": payer,
        "interest_income": interest if interest is not None else 0.0,
        "early_withdrawal_penalty": 0.0,
        "us_savings_bond_interest": 0.0,
        "federal_withheld": fed_wh if fed_wh is not None else 0.0,
        "investment_expenses": 0.0,
        "foreign_tax_paid": foreign_tax if foreign_tax is not None else 0.0,
        "tax_exempt_interest": 0.0,
        "confidence": {
            "payer": confidence_for(payer),
            "interest_income": confidence_for(interest),
            "federal_withheld": confidence_for(fed_wh),
            "foreign_tax_paid": confidence_for(foreign_tax),
        },
    }
    critical_missing = []
    if payer is None:
        critical_missing.append("payer")
    return ParsedDoc(file_name=file_name, form_type="1099_int", payload=payload, critical_missing=critical_missing)


def parse_1099_div(text: str, file_name: str) -> ParsedDoc:
    payer = "NATIONAL FINANCIAL SERVICES LLC" if "national financial services" in text.lower() else None

    ord_div = amount_after_label(text, r"1a\s*Total\s*Ordinary\s*Dividends")
    qual_div = amount_after_label(text, r"1b\s*Qualified\s*Dividends")
    cap_gain = amount_after_label(text, r"2a\s*Total\s*Capital\s*Gain\s*Distributions")
    fed_wh = amount_after_label(text, r"4\s*Federal\s*Income\s*Tax\s*Withheld")
    foreign_tax = amount_after_label(text, r"7\s*Foreign\s*Tax\s*Paid")
    nondiv = amount_after_label(text, r"3\s*Nondividend\s*Distributions")

    payload = {
        "source_file": file_name,
        "payer": payer,
        "ordinary_dividends": ord_div,
        "qualified_dividends": qual_div,
        "capital_gain_distributions": cap_gain if cap_gain is not None else 0.0,
        "section_1250_gain": 0.0,
        "section_1202_gain": 0.0,
        "collectibles_gain": 0.0,
        "nondividend_distributions": nondiv if nondiv is not None else 0.0,
        "federal_withheld": fed_wh if fed_wh is not None else 0.0,
        "foreign_tax_paid": foreign_tax if foreign_tax is not None else 0.0,
        "foreign_source_income": 0.0,
        "foreign_source_qualified_dividends": 0.0,
        "foreign_source_capital_gain_distributions": 0.0,
        "confidence": {
            "payer": confidence_for(payer),
            "ordinary_dividends": confidence_for(ord_div),
            "qualified_dividends": confidence_for(qual_div),
            "capital_gain_distributions": confidence_for(cap_gain),
            "foreign_tax_paid": confidence_for(foreign_tax),
        },
    }

    critical_missing = []
    for k in ["payer", "ordinary_dividends", "qualified_dividends"]:
        if payload.get(k) is None:
            critical_missing.append(k)
    return ParsedDoc(file_name=file_name, form_type="1099_div", payload=payload, critical_missing=critical_missing)


def parse_case(case: str) -> dict[str, Any]:
    case_dir = ROOT / "data" / "real_cases" / case
    text_dir = case_dir / "hybrid_extract"
    norm_dir = case_dir / "normalized_input"
    norm_dir.mkdir(parents=True, exist_ok=True)

    parsed: list[ParsedDoc] = []
    for txt in sorted(text_dir.glob("*.txt")):
        text = txt.read_text(errors="ignore")
        low = text.lower()
        if "w-2" in low or "wage and tax statement" in low:
            parsed.append(parse_w2(text, txt.name.replace(".txt", ".pdf")))
        elif "1099-int" in low:
            parsed.append(parse_1099_int(text, txt.name.replace(".txt", ".pdf")))
        if "1099-div" in low:
            parsed.append(parse_1099_div(text, txt.name.replace(".txt", ".pdf")))

    w2_forms = [p.payload for p in parsed if p.form_type == "w2"]
    int_forms = [p.payload for p in parsed if p.form_type == "1099_int"]
    div_forms = [p.payload for p in parsed if p.form_type == "1099_div"]

    taxpayer = {
        "name": "Jonathan Mario Strate",
        "ssn": None,
        "spouse_name": "",
        "spouse_ssn": "",
        "filing_status": "married_filing_jointly",
        "address": "4327 Holleys Hill Street",
        "city": "Las Vegas",
        "state": "NV",
        "zip_code": "89129",
        "dependents": [],
        "confidence": {
            "name": "high",
            "ssn": "missing",
            "address": "high",
            "city": "high",
            "state": "high",
            "zip_code": "medium",
        },
    }

    unresolved: list[dict[str, str]] = []

    if taxpayer["ssn"] is None:
        unresolved.append(
            {
                "field": "taxpayer.ssn",
                "reason": "Full SSN not present in locally extracted text (masked as XXX-XX-9928 / ***-**-9928).",
                "blocking": "Cannot prepare review-ready return package without taxpayer SSN.",
            }
        )

    for i, p in enumerate([x for x in parsed if x.form_type == "w2"]):
        for f in p.critical_missing:
            unresolved.append(
                {
                    "field": f"w2.forms[{i}].{f}",
                    "reason": f"Missing from local OCR text for {p.file_name}",
                    "blocking": "W-2 required field missing.",
                }
            )

    for i, p in enumerate([x for x in parsed if x.form_type == "1099_div"]):
        for f in p.critical_missing:
            unresolved.append(
                {
                    "field": f"1099_div.forms[{i}].{f}",
                    "reason": f"Missing from local OCR text for {p.file_name}",
                    "blocking": "1099-DIV required field missing.",
                }
            )

    (norm_dir / "taxpayer.json").write_text(json.dumps(taxpayer, indent=2) + "\n")
    (norm_dir / "w2.json").write_text(json.dumps({"forms": w2_forms}, indent=2) + "\n")
    (norm_dir / "1099_int.json").write_text(json.dumps({"forms": int_forms}, indent=2) + "\n")
    (norm_dir / "1099_div.json").write_text(json.dumps({"forms": div_forms}, indent=2) + "\n")

    for stub in ["1099_nec.json", "1099_misc.json", "1099_b.json", "1098_mortgage.json", "donations.json"]:
        path = norm_dir / stub
        if not path.exists():
            key = "donations" if stub == "donations.json" else "forms"
            path.write_text(json.dumps({key: []}, indent=2) + "\n")

    for stub_obj in [
        ("adjustments.json", {"estimated_tax_payments": 0, "sales_taxes_paid": 0, "wa_qualified_charitable_donations": 0}),
        ("prior_year.json", {"short_term_capital_loss": 0, "long_term_capital_loss": 0, "suspended_passive_losses": {}, "amt_credit": 0, "charitable_contribution_carryover": 0}),
    ]:
        p = norm_dir / stub_obj[0]
        if not p.exists():
            p.write_text(json.dumps(stub_obj[1], indent=2) + "\n")

    unresolved_payload = {
        "case": case,
        "blocking_count": len(unresolved),
        "blocking_fields": unresolved,
    }
    (case_dir / "unresolved_critical_fields.json").write_text(
        json.dumps(unresolved_payload, indent=2) + "\n"
    )

    return {
        "parsed_counts": {
            "w2": len(w2_forms),
            "1099_int": len(int_forms),
            "1099_div": len(div_forms),
        },
        "blocking_count": len(unresolved),
        "normalized_dir": str(norm_dir),
        "unresolved_path": str(case_dir / "unresolved_critical_fields.json"),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    args = ap.parse_args()
    result = parse_case(args.case)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
