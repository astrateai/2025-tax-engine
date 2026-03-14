#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
REAL_CASES = ROOT / "data" / "real_cases"


def extract_text(pdf_path: Path) -> str:
    reader = PdfReader(str(pdf_path))
    chunks = []
    for p in reader.pages:
        chunks.append(p.extract_text() or "")
    return "\n".join(chunks)


def first_money(text: str, pattern: str) -> float | None:
    m = re.search(pattern, text, re.IGNORECASE)
    if not m:
        return None
    raw = m.group(1).replace(",", "")
    try:
        return float(raw)
    except Exception:
        return None


def map_candidates(text: str, file_name: str) -> dict:
    low = text.lower()
    out: dict = {"file": file_name, "type": "unknown", "confidence": "low", "fields": {}}

    if "form w-2" in low or "wage and tax statement" in low:
        out["type"] = "w2"
        out["confidence"] = "medium"
        out["fields"] = {
            "wages_box1": first_money(text, r"(?:box\s*1|wages[, ]+tips[, ]+other compensation)\D+([0-9][0-9,]*\.?[0-9]{0,2})"),
            "federal_withheld_box2": first_money(text, r"(?:box\s*2|federal income tax withheld)\D+([0-9][0-9,]*\.?[0-9]{0,2})"),
        }
        return out

    if "1099-int" in low:
        out["type"] = "1099_int"
        out["confidence"] = "medium"
        out["fields"] = {
            "interest_income_box1": first_money(text, r"(?:box\s*1|interest income)\D+([0-9][0-9,]*\.?[0-9]{0,2})"),
            "federal_withheld_box4": first_money(text, r"(?:box\s*4|federal income tax withheld)\D+([0-9][0-9,]*\.?[0-9]{0,2})"),
        }
        return out

    if "1099-div" in low:
        out["type"] = "1099_div"
        out["confidence"] = "medium"
        out["fields"] = {
            "ordinary_dividends_box1a": first_money(text, r"(?:box\s*1a|total ordinary dividends)\D+([0-9][0-9,]*\.?[0-9]{0,2})"),
            "qualified_dividends_box1b": first_money(text, r"(?:box\s*1b|qualified dividends)\D+([0-9][0-9,]*\.?[0-9]{0,2})"),
        }
        return out

    if "1099-b" in low or "proceeds from broker" in low:
        out["type"] = "1099_b"
        out["confidence"] = "low"
        out["fields"] = {"note": "Requires transaction-level extraction/manual normalization in v1."}
        return out

    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True, help="Case folder name under data/real_cases")
    args = ap.parse_args()

    case_dir = REAL_CASES / args.case
    src = case_dir / "source_docs"
    txt_out = case_dir / "extracted_text"
    norm_out = case_dir / "normalized_input"
    txt_out.mkdir(parents=True, exist_ok=True)
    norm_out.mkdir(parents=True, exist_ok=True)

    candidates = []
    for pdf in sorted(src.glob("*.pdf")):
        text = extract_text(pdf)
        (txt_out / f"{pdf.stem}.txt").write_text(text)
        candidates.append(map_candidates(text, pdf.name))

    (case_dir / "mapped_candidates.json").write_text(json.dumps(candidates, indent=2) + "\n")

    # Seed normalized JSON skeletons
    taxpayer = {
        "name": "REQUIRED",
        "ssn": "REQUIRED",
        "spouse_name": "",
        "spouse_ssn": "",
        "filing_status": "married_filing_jointly",
        "address": "REQUIRED",
        "city": "REQUIRED",
        "state": "REQUIRED",
        "zip_code": "REQUIRED",
        "dependents": []
    }
    (norm_out / "taxpayer.json").write_text(json.dumps(taxpayer, indent=2) + "\n")

    (norm_out / "normalization_notice.md").write_text(
        "# Normalization Notice\n\n"
        "Auto-extracted candidates were generated. Human confirmation is required before prep run.\n"
        "Complete REQUIRED fields in normalized_input and map verified form values into engine JSON files.\n"
    )

    print(f"case prepared: {case_dir}")


if __name__ == "__main__":
    main()
