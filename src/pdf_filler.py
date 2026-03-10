"""Generate fillable IRS packet PDFs from Taxinator output.

Design constraints:
- Fillable-fields only (no overlay rendering).
- Deterministic packet output under forms/filled/2025.
- Verification pass that re-reads filled fields and checks mapped values.
"""

from __future__ import annotations

import argparse
import json
import re
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Callable

from pypdf import PdfReader, PdfWriter
from pypdf.generic import BooleanObject, NameObject

from .engine import calculate_2025
from .ingest import load_2025_data
from .models import FormResult, TaxCalculationResult, TaxYear2025Data
from .utils import NIIT_THRESHOLD

BASE_DIR = Path(__file__).resolve().parent.parent
FORMS_BLANK_DIR = BASE_DIR / "forms" / "blank"
FORMS_FILLED_DIR = BASE_DIR / "forms" / "filled" / "2025" / "federal"
WA_FILLED_DIR = BASE_DIR / "forms" / "filled" / "2025" / "wa"
OUTPUT_DIR = BASE_DIR / "data" / "output"

IRS_PDF_BASE = "https://www.irs.gov/pub/irs-pdf"


def _to_mm(value: str | None) -> float | None:
    if not value:
        return None
    match = re.match(r"([-0-9.]+)(mm|pt|in)$", value)
    if not match:
        return None
    number = float(match.group(1))
    unit = match.group(2)
    if unit == "mm":
        return number
    if unit == "pt":
        return number * 25.4 / 72.0
    if unit == "in":
        return number * 25.4
    return None


def _full_name(path_name: str) -> str:
    if "." in path_name:
        return path_name.split(".")[-1]
    return path_name


def _format_irs_dollar(value: Decimal) -> str:
    rounded = value.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    if rounded == Decimal("-0"):
        rounded = Decimal("0")
    return str(int(rounded))


def _digits_only(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\D", "", value)


def _split_name(full_name: str | None) -> tuple[str, str]:
    if not full_name:
        return "", ""
    parts = full_name.strip().split()
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return " ".join(parts[:-1]), parts[-1]


def _ensure_pdf(filename: str) -> Path:
    FORMS_BLANK_DIR.mkdir(parents=True, exist_ok=True)
    path = FORMS_BLANK_DIR / filename
    if path.exists() and path.stat().st_size > 0:
        return path

    url = f"{IRS_PDF_BASE}/{filename}"
    with urllib.request.urlopen(url, timeout=30) as response:  # nosec B310
        payload = response.read()
    path.write_bytes(payload)
    return path


def _extract_xfa_template_root(reader: PdfReader) -> ET.Element | None:
    acroform = reader.trailer["/Root"].get("/AcroForm")
    if not acroform or "/XFA" not in acroform:
        return None
    xfa = acroform["/XFA"]
    for idx in range(0, len(xfa), 2):
        if str(xfa[idx]) == "template":
            xml_payload = xfa[idx + 1].get_object().get_data()
            return ET.fromstring(xml_payload)
    return None


def _is_text_field(element: ET.Element) -> bool:
    for child in element.iter():
        tag = child.tag.split("}")[-1]
        if tag == "checkButton":
            return False
        if tag == "choiceList":
            return False
        if tag == "textEdit":
            return True
    return False


def _assist_text(element: ET.Element) -> str:
    chunks: list[str] = []
    for child in element:
        if child.tag.split("}")[-1] != "assist":
            continue
        for node in child.iter():
            if node.text:
                value = node.text.strip()
                if value:
                    chunks.append(value)
    return " ".join(chunks)


def _extract_assist_line_field_map(reader: PdfReader) -> dict[str, str]:
    """Fallback mapping: parse line ids from field assist text."""
    root = _extract_xfa_template_root(reader)
    if root is None:
        return {}

    candidates_by_line: dict[str, list[tuple[float, float, str]]] = {}
    for element in root.iter():
        if element.tag.split("}")[-1] != "field":
            continue
        if not _is_text_field(element):
            continue
        name = element.attrib.get("name")
        x = _to_mm(element.attrib.get("x"))
        y = _to_mm(element.attrib.get("y"))
        if not name or x is None or y is None:
            continue

        assist = _assist_text(element)
        if not assist:
            continue

        match = re.match(r"^\\s*(\\d+[a-z]?)\\b", assist, re.IGNORECASE)
        if not match:
            continue
        line_id = match.group(1).lower()
        label = f"Ln{line_id}"
        candidates_by_line.setdefault(label, []).append((x, y, name))

    mapping: dict[str, str] = {}
    for label, candidates in candidates_by_line.items():
        # Prefer right-most field for numeric entry (avoids descriptive columns).
        candidates.sort(key=lambda item: (item[0], -item[1]))
        chosen_name = candidates[-1][2]
        mapping[label] = f"{chosen_name}[0]"
    return mapping


def _extract_line_field_map(reader: PdfReader) -> dict[str, str]:
    """Map XFA draw labels like Ln24 -> short field name like f2_16[0]."""
    root = _extract_xfa_template_root(reader)
    if root is None:
        return {}

    fields: list[tuple[str, float, float]] = []
    labels: list[tuple[str, float, float]] = []

    for element in root.iter():
        tag = element.tag.split("}")[-1]
        name = element.attrib.get("name")
        x = _to_mm(element.attrib.get("x"))
        y = _to_mm(element.attrib.get("y"))

        if tag == "field" and name and x is not None and y is not None and _is_text_field(element):
            fields.append((name, x, y))
        elif tag == "draw" and name and name.startswith("Ln") and x is not None and y is not None:
            labels.append((name, x, y))

    mapping: dict[str, str] = {}
    for label_name, label_x, label_y in labels:
        candidates_right: list[tuple[float, float, str]] = []
        for field_name, field_x, field_y in fields:
            if abs(field_y - label_y) > 3.6:
                continue
            if field_x + 0.1 < label_x:
                continue
            candidates_right.append((field_x - label_x, abs(field_y - label_y), field_name))

        candidates: list[tuple[float, float, str]]
        if candidates_right:
            candidates = candidates_right
        else:
            # Fallback for layouts where the entry box is not strictly to the right
            # of the line label (some schedules place labels above/left of boxes).
            candidates_any_side: list[tuple[float, float, str]] = []
            for field_name, field_x, field_y in fields:
                if abs(field_y - label_y) > 3.6:
                    continue
                candidates_any_side.append((abs(field_x - label_x), abs(field_y - label_y), field_name))
            if not candidates_any_side:
                continue
            candidates = candidates_any_side

        candidates.sort(key=lambda item: (item[1], item[0]))
        chosen = candidates[0][2]
        mapping[label_name] = f"{chosen}[0]"

    # Fallback: augment with assist-text-derived line mappings.
    for label, field_name in _extract_assist_line_field_map(reader).items():
        mapping.setdefault(label, field_name)

    return mapping


def _set_checkbox_by_name(writer: PdfWriter, short_name: str, checked: bool, on_state: str = "/1") -> None:
    for page in writer.pages:
        for annotation_ref in page.get("/Annots", []):
            annotation = annotation_ref.get_object()
            if annotation.get("/T") != short_name:
                continue

            ap = annotation.get("/AP")
            available = list(ap["/N"].keys()) if ap and "/N" in ap else []
            state = NameObject(on_state) if checked and NameObject(on_state) in available else NameObject("/Off")
            annotation[NameObject("/AS")] = state
            annotation[NameObject("/V")] = state


def _set_filing_status_checkbox(writer: PdfWriter, filing_status: str) -> None:
    """Set Form 1040 filing status checkbox set c1_8 by AP state code."""
    desired_state = {
        "single": "/1",
        "married_filing_jointly": "/2",
        "married_filing_separately": "/3",
        "head_of_household": "/4",
        "qualifying_surviving_spouse": "/5",
    }.get(filing_status)
    if desired_state is None:
        return

    for page in writer.pages:
        for annotation_ref in page.get("/Annots", []):
            annotation = annotation_ref.get_object()
            field_name = annotation.get("/T", "")
            if not isinstance(field_name, str) or not field_name.startswith("c1_8"):
                continue

            ap = annotation.get("/AP")
            available = list(ap["/N"].keys()) if ap and "/N" in ap else []
            desired_obj = NameObject(desired_state)
            if desired_obj in available:
                annotation[NameObject("/AS")] = desired_obj
                annotation[NameObject("/V")] = desired_obj
            else:
                annotation[NameObject("/AS")] = NameObject("/Off")
                annotation[NameObject("/V")] = NameObject("/Off")


def _derive_niit(result: TaxCalculationResult) -> Decimal:
    se_tax = result.schedule_se.get_line("12") if result.schedule_se else Decimal("0")
    medicare_tax = result.form_8959.get_line("18") if result.form_8959 else Decimal("0")
    additional_taxes = result.form_1040.get_line("17") if result.form_1040 else Decimal("0")
    return max(Decimal("0"), additional_taxes - se_tax - medicare_tax)


def _derive_form_8960(result: TaxCalculationResult, data: TaxYear2025Data) -> FormResult:
    """Build a minimal 8960 line set that ties to engine NIIT totals."""
    form = FormResult(form_name="Form 8960")

    interest_income = result.schedule_b.get_line("1") if result.schedule_b else Decimal("0")
    ordinary_dividends = result.schedule_b.get_line("5") if result.schedule_b else Decimal("0")
    schedule_e_net_passive = result.schedule_e.get_line("NetPassive") if result.schedule_e else Decimal("0")
    passive_for_niit = max(Decimal("0"), schedule_e_net_passive)
    misc_income = result.schedule_1.get_line("8z") if result.schedule_1 else Decimal("0")
    net_capital_for_niit = Decimal("0")
    if result.form_8949:
        net_capital_for_niit = max(
            Decimal("0"),
            result.form_8949.get_line("ShortTerm") + result.form_8949.get_line("LongTerm"),
        )

    line1 = interest_income
    line2 = ordinary_dividends
    line5 = net_capital_for_niit + passive_for_niit + misc_income
    line7 = line1 + line2 + line5
    line13 = result.agi
    threshold = NIIT_THRESHOLD[data.taxpayer.filing_status]
    line14 = threshold
    line15 = max(Decimal("0"), line13 - line14)
    line16 = min(line7, line15)
    line17 = _derive_niit(result)

    form.add_line("1", "Taxable interest", line1)
    form.add_line("2", "Ordinary dividends", line2)
    form.add_line("5", "Net gains/other investment income", line5)
    form.add_line("7", "Net investment income", line7)
    form.add_line("13", "Modified AGI", line13)
    form.add_line("14", "Threshold", line14)
    form.add_line("15", "Excess MAGI", line15)
    form.add_line("16", "NIIT base", line16)
    form.add_line("17", "NIIT", line17)
    return form


def _derive_schedule_2(result: TaxCalculationResult) -> FormResult:
    """Build minimal Schedule 2 values that tie to 1040 additional taxes."""
    form = FormResult(form_name="Schedule 2")
    se_tax = result.schedule_se.get_line("12") if result.schedule_se else Decimal("0")
    medicare_tax = result.form_8959.get_line("18") if result.form_8959 else Decimal("0")
    niit = _derive_niit(result)

    line21 = se_tax + medicare_tax + niit

    form.add_line("4", "Self-employment tax", se_tax)
    form.add_line("11", "Additional Medicare tax", medicare_tax)
    form.add_line("12", "Net investment income tax", niit)
    form.add_line("21", "Total other taxes", line21)
    return form


def _fill_1040_identity_and_dependents(
    field_values: dict[str, str],
    checkbox_ops: list[tuple[str, bool, str]],
    data: TaxYear2025Data,
) -> None:
    taxpayer = data.taxpayer
    self_first, self_last = _split_name(taxpayer.name)
    spouse_first, spouse_last = _split_name(taxpayer.spouse_name)

    field_values["f1_14[0]"] = self_first
    field_values["f1_15[0]"] = self_last
    field_values["f1_16[0]"] = _digits_only(taxpayer.ssn)
    field_values["f1_17[0]"] = spouse_first
    field_values["f1_18[0]"] = spouse_last
    field_values["f1_19[0]"] = _digits_only(taxpayer.spouse_ssn)

    field_values["f1_20[0]"] = taxpayer.address
    field_values["f1_21[0]"] = ""
    field_values["f1_22[0]"] = taxpayer.city
    field_values["f1_23[0]"] = taxpayer.state
    field_values["f1_24[0]"] = taxpayer.zip_code

    dep_rows = [
        ("f1_31[0]", "f1_32[0]", "f1_33[0]", "c1_12[0]", "c1_13[0]"),
        ("f1_35[0]", "f1_36[0]", "f1_37[0]", "c1_14[0]", "c1_15[0]"),
        ("f1_39[0]", "f1_40[0]", "f1_41[0]", "c1_16[0]", "c1_17[0]"),
        ("f1_43[0]", "f1_44[0]", "f1_45[0]", "c1_18[0]", "c1_19[0]"),
    ]
    for dependent, row in zip(taxpayer.dependents, dep_rows):
        name_field, ssn_field, relation_field, ctc_checkbox, odc_checkbox = row
        field_values[name_field] = dependent.name
        field_values[ssn_field] = _digits_only(dependent.ssn)
        field_values[relation_field] = dependent.relationship
        if dependent.qualifies_for_ctc:
            checkbox_ops.append((ctc_checkbox, True, "/1"))
            checkbox_ops.append((odc_checkbox, False, "/1"))
        else:
            checkbox_ops.append((ctc_checkbox, False, "/1"))
            checkbox_ops.append((odc_checkbox, True, "/1"))


def _fill_schedule_e_totals(field_values: dict[str, str], schedule_e: FormResult) -> None:
    passive_income = schedule_e.get_line("PassiveIncome")
    allowed_passive_loss = abs(schedule_e.get_line("AllowedPassiveLoss"))
    nonpassive = schedule_e.get_line("NonPassive")
    net_passive = schedule_e.get_line("NetPassive")

    field_values["f2_40[0]"] = _format_irs_dollar(allowed_passive_loss)
    field_values["f2_41[0]"] = _format_irs_dollar(passive_income)

    if nonpassive < 0:
        field_values["f2_42[0]"] = _format_irs_dollar(abs(nonpassive))
        field_values["f2_44[0]"] = "0"
    else:
        field_values["f2_42[0]"] = "0"
        field_values["f2_44[0]"] = _format_irs_dollar(nonpassive)

    field_values["f2_67[0]"] = _format_irs_dollar(net_passive + nonpassive)


def _fill_form_8949_totals(field_values: dict[str, str], form_8949: FormResult) -> None:
    short_term = form_8949.get_line("ShortTerm")
    long_term = form_8949.get_line("LongTerm")
    field_values["f1_95[0]"] = _format_irs_dollar(short_term)
    field_values["f2_95[0]"] = _format_irs_dollar(long_term)


def _fill_form_8283_summary(field_values: dict[str, str], result: TaxCalculationResult, data: TaxYear2025Data) -> None:
    value = result.form_8283.get_line("SectionA") if result.form_8283 else Decimal("0")
    _, last_name = _split_name(data.taxpayer.name)
    field_values["f1_1[0]"] = data.taxpayer.name
    field_values["f1_8[0]"] = "Various donee organizations (see statements)"
    field_values["f1_7[0]"] = "Publicly traded securities (aggregated summary)"
    field_values["f1_21[0]"] = _format_irs_dollar(value)
    field_values["f1_22[0]"] = "Broker statement FMV"
    field_values["f2_1[0]"] = f"{data.taxpayer.name} ({last_name})"


def _add_manual_write(
    field_values: dict[str, str],
    expected_writes: list[dict[str, str]],
    field_name: str,
    value: str,
    *,
    line: str = "custom",
    label: str = "custom",
) -> None:
    field_values[field_name] = value
    expected_writes.append(
        {
            "line": line,
            "label": label,
            "field": field_name,
            "value": value,
        }
    )


@dataclass
class FormSpec:
    key: str
    pdf_filename: str
    result_attr: str | None
    line_aliases: dict[str, str] = field(default_factory=dict)
    ignore_lines: set[str] = field(default_factory=set)
    include_if: Callable[[TaxCalculationResult], bool] | None = None


FORM_SPECS: list[FormSpec] = [
    FormSpec(
        key="form_1040",
        pdf_filename="f1040.pdf",
        result_attr="form_1040",
        line_aliases={
            "1": "1a",
            "7": "7a",
            "11": "11a",
            "12": "12e",
            "37": "37",
        },
    ),
    FormSpec(
        key="schedule_1",
        pdf_filename="f1040s1.pdf",
        result_attr="schedule_1",
        ignore_lines={"8z"},
    ),
    FormSpec(
        key="schedule_2",
        pdf_filename="f1040s2.pdf",
        result_attr="derived_schedule_2",
    ),
    FormSpec(
        key="schedule_3",
        pdf_filename="f1040s3.pdf",
        result_attr="schedule_3",
        include_if=lambda r: r.schedule_3 is not None,
    ),
    FormSpec(
        key="schedule_a",
        pdf_filename="f1040sa.pdf",
        result_attr="schedule_a",
        line_aliases={"Total": "17"},
    ),
    FormSpec(
        key="schedule_b",
        pdf_filename="f1040sb.pdf",
        result_attr="schedule_b",
        ignore_lines={"1", "Qualified", "2a", "7", "5"},
    ),
    FormSpec(
        key="schedule_c",
        pdf_filename="f1040sc.pdf",
        result_attr="schedule_c",
        ignore_lines={"31"},
    ),
    FormSpec(
        key="schedule_d",
        pdf_filename="f1040sd.pdf",
        result_attr="schedule_d",
        line_aliases={"21": "16", "21a": "21"},
        ignore_lines={"1a", "15", "21", "21a"},
    ),
    FormSpec(
        key="schedule_e",
        pdf_filename="f1040se.pdf",
        result_attr="schedule_e",
        ignore_lines={"PassiveIncome", "PassiveLoss", "AllowedPassiveLoss", "NetPassive", "NonPassive"},
    ),
    FormSpec(
        key="schedule_se",
        pdf_filename="f1040sse.pdf",
        result_attr="schedule_se",
        line_aliases={"4": "4c"},
        ignore_lines={"2", "4", "12", "13"},
    ),
    FormSpec(
        key="form_8949",
        pdf_filename="f8949.pdf",
        result_attr="form_8949",
        ignore_lines={"ShortTerm", "LongTerm"},
    ),
    FormSpec(
        key="form_8283",
        pdf_filename="f8283.pdf",
        result_attr="form_8283",
        ignore_lines={"SectionA"},
        include_if=lambda r: (r.form_8283 is not None and r.form_8283.get_line("SectionA") > 0),
    ),
    FormSpec(
        key="form_8582",
        pdf_filename="f8582.pdf",
        result_attr="form_8582",
        line_aliases={"1": "1d", "2": "2d"},
        ignore_lines={"1", "2", "3", "5"},
    ),
    FormSpec(
        key="form_8959",
        pdf_filename="f8959.pdf",
        result_attr="form_8959",
        ignore_lines={"6", "13", "18"},
    ),
    FormSpec(
        key="form_8960",
        pdf_filename="f8960.pdf",
        result_attr="derived_form_8960",
        ignore_lines={"1", "2", "5", "7", "13", "14", "15", "16", "17"},
    ),
    FormSpec(
        key="form_8962",
        pdf_filename="f8962.pdf",
        result_attr="form_8962",
        ignore_lines={"11", "12", "26", "29"},
    ),
    FormSpec(
        key="form_1116",
        pdf_filename="f1116.pdf",
        result_attr="form_1116",
        ignore_lines={"1a", "7", "8", "15", "18", "20", "21", "22"},
        include_if=lambda r: r.form_1116 is not None,
    ),
]


def _line_to_label(form_key: str, line_id: str, aliases: dict[str, str]) -> str | None:
    if line_id in aliases:
        mapped = aliases[line_id]
    else:
        normalized = line_id.strip()
        if re.fullmatch(r"\d+[A-Za-z]?", normalized):
            mapped = normalized.lower()
        else:
            return None
    if mapped.startswith("Ln"):
        return mapped
    return f"Ln{mapped}"


def _build_form_values(
    spec: FormSpec,
    form_result: FormResult | None,
    line_map: dict[str, str],
) -> tuple[dict[str, str], list[dict[str, str]], list[str]]:
    field_values: dict[str, str] = {}
    expected_writes: list[dict[str, str]] = []
    unmapped: list[str] = []

    if form_result is None:
        return field_values, expected_writes, unmapped

    for line_id, line in form_result.lines.items():
        if line_id in spec.ignore_lines:
            continue
        label = _line_to_label(spec.key, line_id, spec.line_aliases)
        if label is None:
            unmapped.append(f"{line_id}: non-standard line id")
            continue
        field_name = line_map.get(label)
        if not field_name:
            unmapped.append(f"{line_id}: no {label} field found")
            continue

        value = _format_irs_dollar(line.value)
        field_values[field_name] = value
        expected_writes.append(
            {
                "line": line_id,
                "label": label,
                "field": field_name,
                "value": value,
            }
        )

    return field_values, expected_writes, unmapped


def _apply_text_fields(writer: PdfWriter, field_values: dict[str, str]) -> None:
    if not field_values:
        return
    for page in writer.pages:
        writer.update_page_form_field_values(page, field_values, auto_regenerate=False)


def _verify_field_values(pdf_path: Path, expected_writes: list[dict[str, str]]) -> list[dict[str, str]]:
    reader = PdfReader(str(pdf_path))
    fields = reader.get_fields() or {}
    mismatches: list[dict[str, str]] = []

    for write in expected_writes:
        field = write["field"]
        expected = write["value"]

        match_value: str | None = None
        for full_name, field_info in fields.items():
            if _full_name(full_name) == field:
                raw = field_info.get("/V")
                match_value = "" if raw is None else str(raw)
                break

        if match_value is None:
            mismatches.append({"field": field, "expected": expected, "actual": "<missing>"})
            continue

        if match_value != expected:
            mismatches.append({"field": field, "expected": expected, "actual": match_value})

    return mismatches


def _merge_pdfs(paths: list[Path], output_path: Path) -> None:
    writer = PdfWriter()
    for path in paths:
        writer.append(str(path))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("wb") as handle:
        writer.write(handle)


def _write_mail_instructions(paths: list[Path], result: TaxCalculationResult) -> Path:
    instruction_path = FORMS_FILLED_DIR / "print_and_mail.md"
    lines = [
        "# Federal Packet: Print, Sign, and Mail",
        "",
        "## Print Order",
    ]
    for idx, path in enumerate(paths, start=1):
        lines.append(f"{idx}. {path.name}")

    lines.extend(
        [
            "",
            "## Signature Requirements",
            "1. Sign and date Form 1040 (both spouses for MFJ).",
            "2. Keep copy of full packet and proof of mailing.",
            "",
            "## Payment / Balance Due",
            f"- Federal balance due (engine): ${abs(result.refund_or_owed):,.2f} (if owed).",
            "- Confirm IRS mailing address by payment/no-payment status before sending:",
            "  https://www.irs.gov/filing/where-to-file-paper-tax-returns-with-or-without-a-payment",
        ]
    )
    instruction_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return instruction_path


def _write_wa_packet(result: TaxCalculationResult) -> Path:
    WA_FILLED_DIR.mkdir(parents=True, exist_ok=True)
    packet = {
        "wa_capital_gains_tax": str(result.wa_capital_gains_tax),
        "notes": [
            "WA capital gains tax is filed through My DOR (electronic filing path).",
            "Attach/retain a copy of federal return and supporting transaction docs per WA DOR guidance.",
        ],
        "my_dor_help": "https://dor.wa.gov/manage-business/my-dor-help/capital-gains-my-dor-help",
    }
    path = WA_FILLED_DIR / "wa_capgains_packet.json"
    path.write_text(json.dumps(packet, indent=2) + "\n", encoding="utf-8")
    return path


def generate_packet() -> dict:
    FORMS_FILLED_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    result, _ = calculate_2025()
    data = load_2025_data()

    derived_form_8960 = _derive_form_8960(result, data)
    derived_schedule_2 = _derive_schedule_2(result)

    form_by_attr: dict[str, FormResult | None] = {
        "form_1040": result.form_1040,
        "schedule_1": result.schedule_1,
        "derived_schedule_2": derived_schedule_2,
        "schedule_3": result.schedule_3,
        "schedule_a": result.schedule_a,
        "schedule_b": result.schedule_b,
        "schedule_c": result.schedule_c,
        "schedule_d": result.schedule_d,
        "schedule_e": result.schedule_e,
        "schedule_se": result.schedule_se,
        "form_8949": result.form_8949,
        "form_8283": result.form_8283,
        "form_8582": result.form_8582,
        "form_8959": result.form_8959,
        "derived_form_8960": derived_form_8960,
        "form_8962": result.form_8962,
        "form_1116": result.form_1116,
    }

    report: dict = {
        "forms": {},
        "warnings": [],
        "packet": {},
    }

    filled_paths: list[Path] = []

    for spec in FORM_SPECS:
        if spec.include_if and not spec.include_if(result):
            continue

        source_form = form_by_attr.get(spec.result_attr) if spec.result_attr else None
        if source_form is None and spec.result_attr is not None:
            continue

        blank_path = _ensure_pdf(spec.pdf_filename)
        reader = PdfReader(str(blank_path))
        writer = PdfWriter()
        writer.clone_document_from_reader(reader)

        line_map = _extract_line_field_map(reader)
        field_values, expected_writes, unmapped = _build_form_values(spec, source_form, line_map)

        checkbox_ops: list[tuple[str, bool, str]] = []

        if spec.key == "form_1040":
            _fill_1040_identity_and_dependents(field_values, checkbox_ops, data)
            _set_filing_status_checkbox(writer, data.taxpayer.filing_status.value)
            if result.schedule_b is not None and "Ln3a" in line_map:
                qd_field = line_map["Ln3a"]
                qd_value = _format_irs_dollar(result.schedule_b.get_line("Qualified"))
                _add_manual_write(
                    field_values,
                    expected_writes,
                    qd_field,
                    qd_value,
                    line="3a",
                    label="Ln3a",
                )

        if spec.key == "schedule_1" and result.schedule_1 is not None:
            _add_manual_write(
                field_values,
                expected_writes,
                "f1_36[0]",
                _format_irs_dollar(result.schedule_1.get_line("8z")),
                line="8z",
                label="manual",
            )

        if spec.key == "schedule_b" and result.schedule_b is not None:
            _add_manual_write(
                field_values,
                expected_writes,
                "f1_31[0]",
                _format_irs_dollar(result.schedule_b.get_line("1")),
                line="1",
                label="manual",
            )
            _add_manual_write(
                field_values,
                expected_writes,
                "f1_64[0]",
                _format_irs_dollar(result.schedule_b.get_line("5")),
                line="5",
                label="manual",
            )

        if spec.key == "schedule_c" and result.schedule_c is not None:
            _add_manual_write(
                field_values,
                expected_writes,
                "f1_46[0]",
                _format_irs_dollar(result.schedule_c.get_line("31")),
                line="31",
                label="manual",
            )

        if spec.key == "schedule_d" and result.schedule_d is not None:
            _add_manual_write(
                field_values,
                expected_writes,
                "f1_6[0]",
                _format_irs_dollar(result.schedule_d.get_line("1a")),
                line="1a",
                label="manual",
            )
            _add_manual_write(
                field_values,
                expected_writes,
                "f1_43[0]",
                _format_irs_dollar(result.schedule_d.get_line("15")),
                line="15",
                label="manual",
            )
            _add_manual_write(
                field_values,
                expected_writes,
                "f2_1[0]",
                _format_irs_dollar(result.schedule_d.get_line("21")),
                line="21",
                label="manual",
            )
            _add_manual_write(
                field_values,
                expected_writes,
                "f2_4[0]",
                _format_irs_dollar(abs(result.schedule_d.get_line("21a"))),
                line="21a",
                label="manual",
            )

        if spec.key == "schedule_e" and result.schedule_e is not None:
            _fill_schedule_e_totals(field_values, result.schedule_e)
            for special_field in ("f2_40[0]", "f2_41[0]", "f2_42[0]", "f2_44[0]", "f2_67[0]"):
                _add_manual_write(
                    field_values,
                    expected_writes,
                    special_field,
                    field_values[special_field],
                )

        if spec.key == "schedule_se" and result.schedule_se is not None:
            _add_manual_write(
                field_values,
                expected_writes,
                "f1_5[0]",
                _format_irs_dollar(result.schedule_se.get_line("2")),
                line="2",
                label="manual",
            )
            _add_manual_write(
                field_values,
                expected_writes,
                "f1_9[0]",
                _format_irs_dollar(result.schedule_se.get_line("4")),
                line="4",
                label="manual",
            )
            _add_manual_write(
                field_values,
                expected_writes,
                "f1_21[0]",
                _format_irs_dollar(result.schedule_se.get_line("12")),
                line="12",
                label="manual",
            )
            _add_manual_write(
                field_values,
                expected_writes,
                "f1_22[0]",
                _format_irs_dollar(result.schedule_se.get_line("13")),
                line="13",
                label="manual",
            )

        if spec.key == "form_8949" and result.form_8949 is not None:
            _fill_form_8949_totals(field_values, result.form_8949)
            for special_field in ("f1_95[0]", "f2_95[0]"):
                _add_manual_write(
                    field_values,
                    expected_writes,
                    special_field,
                    field_values[special_field],
                )

        if spec.key == "form_8283":
            _fill_form_8283_summary(field_values, result, data)
            for special_field in ("f1_1[0]", "f1_8[0]", "f1_7[0]", "f1_21[0]", "f1_22[0]", "f2_1[0]"):
                _add_manual_write(
                    field_values,
                    expected_writes,
                    special_field,
                    field_values[special_field],
                )

        if spec.key == "form_8582" and result.form_8582 is not None:
            _add_manual_write(
                field_values,
                expected_writes,
                "f1_06[0]",
                _format_irs_dollar(result.form_8582.get_line("1")),
                line="1",
                label="manual",
            )
            _add_manual_write(
                field_values,
                expected_writes,
                "f1_10[0]",
                _format_irs_dollar(result.form_8582.get_line("2")),
                line="2",
                label="manual",
            )
            _add_manual_write(
                field_values,
                expected_writes,
                "f1_11[0]",
                _format_irs_dollar(result.form_8582.get_line("3")),
                line="3",
                label="manual",
            )
            _add_manual_write(
                field_values,
                expected_writes,
                "f1_13[0]",
                _format_irs_dollar(result.form_8582.get_line("5")),
                line="5",
                label="manual",
            )

        if spec.key == "form_8959" and result.form_8959 is not None:
            _add_manual_write(
                field_values,
                expected_writes,
                "f1_8[0]",
                _format_irs_dollar(result.form_8959.get_line("6")),
                line="6",
                label="manual",
            )
            _add_manual_write(
                field_values,
                expected_writes,
                "f1_15[0]",
                _format_irs_dollar(result.form_8959.get_line("13")),
                line="13",
                label="manual",
            )
            _add_manual_write(
                field_values,
                expected_writes,
                "f1_20[0]",
                _format_irs_dollar(result.form_8959.get_line("18")),
                line="18",
                label="manual",
            )

        if spec.key == "form_8960":
            _add_manual_write(
                field_values,
                expected_writes,
                "f1_3[0]",
                _format_irs_dollar(derived_form_8960.get_line("1")),
                line="1",
                label="manual",
            )
            _add_manual_write(
                field_values,
                expected_writes,
                "f1_4[0]",
                _format_irs_dollar(derived_form_8960.get_line("2")),
                line="2",
                label="manual",
            )
            _add_manual_write(
                field_values,
                expected_writes,
                "f1_10[0]",
                _format_irs_dollar(derived_form_8960.get_line("5")),
                line="5",
                label="manual",
            )
            _add_manual_write(
                field_values,
                expected_writes,
                "f1_15[0]",
                _format_irs_dollar(derived_form_8960.get_line("7")),
                line="7",
                label="manual",
            )
            _add_manual_write(
                field_values,
                expected_writes,
                "f1_22[0]",
                _format_irs_dollar(derived_form_8960.get_line("7")),
                line="12",
                label="manual",
            )
            _add_manual_write(
                field_values,
                expected_writes,
                "f1_23[0]",
                _format_irs_dollar(derived_form_8960.get_line("13")),
                line="13",
                label="manual",
            )
            _add_manual_write(
                field_values,
                expected_writes,
                "f1_24[0]",
                _format_irs_dollar(derived_form_8960.get_line("14")),
                line="14",
                label="manual",
            )
            _add_manual_write(
                field_values,
                expected_writes,
                "f1_25[0]",
                _format_irs_dollar(derived_form_8960.get_line("15")),
                line="15",
                label="manual",
            )
            _add_manual_write(
                field_values,
                expected_writes,
                "f1_26[0]",
                _format_irs_dollar(derived_form_8960.get_line("16")),
                line="16",
                label="manual",
            )
            _add_manual_write(
                field_values,
                expected_writes,
                "f1_27[0]",
                _format_irs_dollar(derived_form_8960.get_line("17")),
                line="17",
                label="manual",
            )

        if spec.key == "form_8962" and result.form_8962 is not None:
            _add_manual_write(
                field_values,
                expected_writes,
                "f1_13[0]",
                _format_irs_dollar(result.form_8962.get_line("11")),
                line="11",
                label="manual",
            )
            _add_manual_write(
                field_values,
                expected_writes,
                "f1_14[0]",
                _format_irs_dollar(result.form_8962.get_line("12")),
                line="12",
                label="manual",
            )
            _add_manual_write(
                field_values,
                expected_writes,
                "f1_92[0]",
                _format_irs_dollar(result.form_8962.get_line("26")),
                line="26",
                label="manual",
            )
            _add_manual_write(
                field_values,
                expected_writes,
                "f1_93[0]",
                _format_irs_dollar(result.form_8962.get_line("29")),
                line="29",
                label="manual",
            )

        if spec.key == "form_1116" and result.form_1116 is not None:
            manual_map = {
                "1a": "f1_13[0]",
                "7": "f1_51[0]",
                "8": "f1_82[0]",
                "15": "f2_07[0]",
                "18": "f2_10[0]",
                "20": "f2_12[0]",
                "21": "f2_13[0]",
                "22": "f2_27[0]",
            }
            for line_id, field_name in manual_map.items():
                _add_manual_write(
                    field_values,
                    expected_writes,
                    field_name,
                    _format_irs_dollar(result.form_1116.get_line(line_id)),
                    line=line_id,
                    label="manual",
                )

        _apply_text_fields(writer, field_values)

        for checkbox_name, checked, state in checkbox_ops:
            _set_checkbox_by_name(writer, checkbox_name, checked, on_state=state)

        if "/AcroForm" in writer._root_object:
            writer._root_object["/AcroForm"][NameObject("/NeedAppearances")] = BooleanObject(True)

        output_name = f"{spec.key}.pdf"
        output_path = FORMS_FILLED_DIR / output_name
        with output_path.open("wb") as handle:
            writer.write(handle)

        mismatches = _verify_field_values(output_path, expected_writes)

        report["forms"][spec.key] = {
            "source": spec.result_attr,
            "blank_pdf": spec.pdf_filename,
            "filled_pdf": output_name,
            "mapped_writes": len(expected_writes),
            "writes": expected_writes,
            "unmapped_lines": unmapped,
            "verification_mismatches": mismatches,
        }

        if unmapped:
            report["warnings"].append(f"{spec.key}: {len(unmapped)} lines were not mapped to fillable fields")
        if mismatches:
            report["warnings"].append(f"{spec.key}: {len(mismatches)} field verification mismatches")

        filled_paths.append(output_path)

    packet_path = FORMS_FILLED_DIR / "00_full_packet.pdf"
    _merge_pdfs(filled_paths, packet_path)
    mail_path = _write_mail_instructions(filled_paths, result)
    wa_path = _write_wa_packet(result)

    report["packet"] = {
        "forms_included": [path.name for path in filled_paths],
        "merged_pdf": str(packet_path.relative_to(BASE_DIR)),
        "mail_instructions": str(mail_path.relative_to(BASE_DIR)),
        "wa_packet": str(wa_path.relative_to(BASE_DIR)),
        "federal_total_tax": str(result.total_tax),
        "federal_total_payments": str(result.total_payments),
        "federal_refund_or_owed": str(result.refund_or_owed),
    }

    report_path = FORMS_FILLED_DIR / "packet_report.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate fillable IRS packet PDFs from Taxinator output")
    _ = parser.parse_args()

    report = generate_packet()
    print("Generated federal packet:", report["packet"]["merged_pdf"])
    print("Forms included:")
    for name in report["packet"]["forms_included"]:
        print(" -", name)
    if report["warnings"]:
        print("Warnings:")
        for warning in report["warnings"]:
            print(" -", warning)


if __name__ == "__main__":
    main()
