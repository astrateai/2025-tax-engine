"""Load input JSON files into typed tax models."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from decimal import Decimal

from .models import (
    CharitableDonation,
    Form1095A,
    Form1098,
    Form1099B,
    Form1099DIV,
    Form1099INT,
    Form1099MISC,
    Form1099NEC,
    PriorYearCarryforward,
    ScheduleK1,
    TaxYear2025Data,
    TaxpayerInfo,
    W2,
)


INPUT_DIR = Path(__file__).resolve().parent.parent / "data" / "input"


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _load_forms_list(path: Path, model_cls):
    if not path.exists():
        return []
    payload = _load_json(path)
    forms = payload.get("forms", [])
    return [model_cls.model_validate(item) for item in forms]


def load_taxpayer(path: Path) -> TaxpayerInfo:
    payload = _load_json(path)
    return TaxpayerInfo.model_validate(payload)


def load_1099_b(path: Path) -> list[Form1099B]:
    if not path.exists():
        return []
    payload = _load_json(path)
    if "forms" in payload:
        forms = payload.get("forms", [])
        return [Form1099B.model_validate(item) for item in forms]
    if "transactions" in payload:
        broker = payload.get("broker", "Unknown broker")
        return [Form1099B.model_validate({"broker": broker, "transactions": payload["transactions"]})]
    return [Form1099B.model_validate(payload)]


def load_k1s(input_dir: Path) -> list[ScheduleK1]:
    k1s = []
    for path in sorted(input_dir.glob("k1_*.json")):
        payload = _load_json(path)
        k1s.append(ScheduleK1.model_validate(payload))
    return k1s


def load_donations(path: Path) -> list[CharitableDonation]:
    if not path.exists():
        return []
    payload = _load_json(path)
    donations = payload.get("donations", [])
    return [CharitableDonation.model_validate(item) for item in donations]


def load_1095_a(path: Path) -> Form1095A | None:
    if not path.exists():
        return None
    payload = _load_json(path)
    return Form1095A.model_validate(payload)


def load_prior_year(path: Path) -> PriorYearCarryforward:
    if not path.exists():
        return PriorYearCarryforward()
    payload = _load_json(path)
    # Support legacy shape from README (capital_loss_carryforward + suspended_passive_losses)
    if "capital_loss_carryforward" in payload:
        cl = payload.get("capital_loss_carryforward", {})
        short_term = Decimal(str(cl.get("short_term", 0)))
        long_term = Decimal(str(cl.get("long_term", 0)))
        # Normalize: treat carryforward losses as negative amounts
        if short_term and short_term > 0:
            short_term = -short_term
        if long_term and long_term > 0:
            long_term = -long_term
        payload = {
            "short_term_capital_loss": short_term,
            "long_term_capital_loss": long_term,
            "suspended_passive_losses": payload.get("suspended_passive_losses", {}),
            "amt_credit": payload.get("amt_credit_carryforward", payload.get("amt_credit", 0)),
            "charitable_contribution_carryover": payload.get("charitable_contribution_carryover", 0),
        }
    return PriorYearCarryforward.model_validate(payload)


def load_adjustments(path: Path) -> dict[str, Decimal]:
    """
    Load optional manual adjustments that are not present on a single IRS form.

    Keys:
    - estimated_tax_payments: federal quarterly estimates already paid
    - sales_taxes_paid: elected sales tax amount for Schedule A SALT
    - wa_qualified_charitable_donations: WA-CG qualified charitable amount
    """
    if not path.exists():
        return {
            "estimated_tax_payments": Decimal("0"),
            "sales_taxes_paid": Decimal("0"),
            "wa_qualified_charitable_donations": Decimal("0"),
        }

    payload = _load_json(path)
    return {
        "estimated_tax_payments": Decimal(str(payload.get("estimated_tax_payments", 0))),
        "sales_taxes_paid": Decimal(str(payload.get("sales_taxes_paid", 0))),
        "wa_qualified_charitable_donations": Decimal(
            str(payload.get("wa_qualified_charitable_donations", 0))
        ),
    }


def load_2025_data() -> TaxYear2025Data:
    taxpayer_path = INPUT_DIR / "taxpayer.json"
    if not taxpayer_path.exists():
        raise FileNotFoundError(f"Missing taxpayer.json in {INPUT_DIR}")

    taxpayer = load_taxpayer(taxpayer_path)
    adjustments = load_adjustments(INPUT_DIR / "adjustments.json")
    mortgage_forms = _load_forms_list(INPUT_DIR / "1098_mortgage.json", Form1098)

    return TaxYear2025Data(
        taxpayer=taxpayer,
        w2s=_load_forms_list(INPUT_DIR / "w2.json", W2),
        form_1099_int=_load_forms_list(INPUT_DIR / "1099_int.json", Form1099INT),
        form_1099_div=_load_forms_list(INPUT_DIR / "1099_div.json", Form1099DIV),
        form_1099_nec=_load_forms_list(INPUT_DIR / "1099_nec.json", Form1099NEC),
        form_1099_misc=_load_forms_list(INPUT_DIR / "1099_misc.json", Form1099MISC),
        form_1099_b=load_1099_b(INPUT_DIR / "1099_b.json"),
        form_1095_a=load_1095_a(INPUT_DIR / "1095_a.json"),
        k1s=load_k1s(INPUT_DIR),
        form_1098=mortgage_forms,
        charitable_donations=load_donations(INPUT_DIR / "donations.json"),
        property_taxes_paid=sum(
            (form.property_taxes for form in mortgage_forms),
            start=Decimal("0"),
        ),
        sales_taxes_paid=adjustments["sales_taxes_paid"],
        estimated_tax_payments=adjustments["estimated_tax_payments"],
        wa_qualified_charitable_donations=adjustments["wa_qualified_charitable_donations"],
        prior_year=load_prior_year(INPUT_DIR / "prior_year.json"),
    )
