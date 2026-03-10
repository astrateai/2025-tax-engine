"""Main calculation orchestrator for the 2025 tax engine snapshot."""

from __future__ import annotations

import json
import re
from decimal import Decimal
from pathlib import Path

from .ingest import load_2025_data
from .models import FormResult, PriorYearCarryforward, TaxCalculationResult
from .utils import (
    CAPITAL_LOSS_DEDUCTION_LIMIT,
    STANDARD_DEDUCTION,
    TAX_BRACKETS_MFJ,
    CAPITAL_GAINS_BRACKETS_MFJ,
    calculate_additional_medicare_tax,
    calculate_capital_gains_tax,
    calculate_child_tax_credit,
    calculate_deductible_mortgage_interest,
    calculate_excess_social_security_credit,
    calculate_niit,
    calculate_salt_deduction,
    calculate_self_employment_tax,
    calculate_tax_from_brackets,
    calculate_wa_capital_gains_tax,
    format_currency,
    round_to_dollar,
)


OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data" / "output"


def _sum_decimals(values) -> Decimal:
    total = Decimal("0")
    for value in values:
        total += value
    return total


def _safe_decimal(value: Decimal | None) -> Decimal:
    return value if value is not None else Decimal("0")


def _normalize_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _names_match(left: str, right: str) -> bool:
    a = _normalize_name(left)
    b = _normalize_name(right)
    return a == b or a in b or b in a


def _add_warning(result: TaxCalculationResult, audit_lines: list[str], message: str) -> None:
    warning = f"WARNING: {message}"
    result.warnings.append(message)
    audit_lines.append(warning)


def _round_form_results(result: TaxCalculationResult) -> None:
    """
    IRS returns generally use whole-dollar amounts on form lines.
    Keep internal math precision during computation, then round display lines.
    """
    form_attrs = (
        "schedule_c",
        "schedule_e",
        "schedule_se",
        "schedule_1",
        "schedule_b",
        "schedule_d",
        "schedule_a",
        "schedule_3",
        "form_8949",
        "form_1116",
        "form_8582",
        "form_8959",
        "form_8960",
        "form_8962",
        "form_2210",
        "form_6251",
        "form_8283",
        "form_8812",
        "form_1040",
    )
    for attr in form_attrs:
        form = getattr(result, attr)
        if form is None:
            continue
        for line in form.lines.values():
            line.value = round_to_dollar(line.value)


def calculate_2025() -> tuple[TaxCalculationResult, list[str]]:
    data = load_2025_data()
    audit_lines: list[str] = []

    result = TaxCalculationResult()
    foreign_tax_credit = Decimal("0")

    # ---------------------------------------------------------------------
    # W-2 totals
    # ---------------------------------------------------------------------
    w2_wages = _sum_decimals(w.wages for w in data.w2s)
    w2_withholding = _sum_decimals(w.federal_withheld for w in data.w2s)
    w2_ss_wages = _sum_decimals(w.social_security_wages for w in data.w2s)
    w2_ss_withheld = _sum_decimals(w.social_security_withheld for w in data.w2s)
    w2_medicare_wages = [w.medicare_wages for w in data.w2s]

    audit_lines.append(f"W-2 wages: {format_currency(w2_wages)}")
    audit_lines.append(f"Federal withholding (W-2): {format_currency(w2_withholding)}")

    # ---------------------------------------------------------------------
    # Schedule C (1099-NEC)
    # ---------------------------------------------------------------------
    schedule_c = FormResult(form_name="Schedule C")
    nec_income = _sum_decimals(form.nonemployee_comp for form in data.form_1099_nec)
    nec_expenses = Decimal("0")
    nec_net = nec_income - nec_expenses
    schedule_c.add_line("1", "Gross receipts (1099-NEC)", nec_income)
    schedule_c.add_line("28", "Total expenses", nec_expenses)
    schedule_c.add_line("31", "Net profit", nec_net)
    result.schedule_c = schedule_c

    # ---------------------------------------------------------------------
    # Schedule 1 (Other income from 1099-MISC)
    # ---------------------------------------------------------------------
    schedule_1 = FormResult(form_name="Schedule 1")
    misc_income = _sum_decimals(form.other_income for form in data.form_1099_misc)
    schedule_1.add_line("8z", "Other income (1099-MISC)", misc_income)
    result.schedule_1 = schedule_1

    # ---------------------------------------------------------------------
    # Schedule SE (Self-Employment Tax)
    # ---------------------------------------------------------------------
    se_tax, se_deduction, se_audit = calculate_self_employment_tax(nec_net, w2_ss_wages)
    schedule_se = FormResult(form_name="Schedule SE")
    schedule_se.add_line("2", "Net profit from Schedule C", nec_net)
    se_earnings = nec_net * Decimal("0.9235") if nec_net > 0 else Decimal("0")
    schedule_se.add_line("4", "SE earnings (92.35%)", se_earnings)
    schedule_se.add_line("12", "Self-employment tax", se_tax)
    schedule_se.add_line("13", "Deduction (50% SE tax)", se_deduction)
    result.schedule_se = schedule_se
    audit_lines.append(se_audit)

    # ---------------------------------------------------------------------
    # Schedule B (Interest + Dividends)
    # ---------------------------------------------------------------------
    schedule_b = FormResult(form_name="Schedule B")
    interest_from_1099 = _sum_decimals(f.interest_income for f in data.form_1099_int)
    ordinary_dividends_from_1099 = _sum_decimals(f.ordinary_dividends for f in data.form_1099_div)
    qualified_dividends_from_1099 = _sum_decimals(f.qualified_dividends for f in data.form_1099_div)
    capital_gain_distributions_from_1099 = _sum_decimals(
        f.capital_gain_distributions for f in data.form_1099_div
    )
    foreign_tax_paid_div = _sum_decimals(f.foreign_tax_paid for f in data.form_1099_div)
    foreign_tax_paid_int = _sum_decimals(f.foreign_tax_paid for f in data.form_1099_int)
    foreign_tax_paid = foreign_tax_paid_div + foreign_tax_paid_int
    foreign_source_income = _sum_decimals(f.foreign_source_income for f in data.form_1099_div)
    foreign_source_qualified_dividends = _sum_decimals(
        f.foreign_source_qualified_dividends for f in data.form_1099_div
    )
    foreign_source_capital_gain_distributions = _sum_decimals(
        f.foreign_source_capital_gain_distributions for f in data.form_1099_div
    )

    # K-1 portfolio items
    k1_interest = _sum_decimals(k1.boxes.box_5 for k1 in data.k1s)
    k1_dividends = _sum_decimals(k1.boxes.box_6a for k1 in data.k1s)
    k1_qualified_dividends = _sum_decimals(k1.boxes.box_6b for k1 in data.k1s)

    # Guardrail for accidental double-entry of partnership portfolio items in both
    # 1099s and K-1 data.
    for k1 in data.k1s:
        if (
            _safe_decimal(k1.boxes.box_5) <= 0
            and _safe_decimal(k1.boxes.box_6a) <= 0
            and _safe_decimal(k1.boxes.box_6b) <= 0
        ):
            continue
        int_match = any(
            _names_match(f.payer, k1.entity_name) and f.interest_income != 0
            for f in data.form_1099_int
        )
        div_match = any(
            _names_match(f.payer, k1.entity_name)
            and (f.ordinary_dividends != 0 or f.qualified_dividends != 0)
            for f in data.form_1099_div
        )
        if int_match or div_match:
            _add_warning(
                result,
                audit_lines,
                (
                    f"Potential duplicate portfolio income for '{k1.entity_name}' "
                    "across 1099 and K-1 inputs; verify only one source is kept."
                ),
            )

    interest_income = interest_from_1099 + k1_interest
    ordinary_dividends = ordinary_dividends_from_1099 + k1_dividends
    qualified_dividends = qualified_dividends_from_1099 + k1_qualified_dividends

    schedule_b.add_line("1", "Taxable interest", interest_income)
    schedule_b.add_line("5", "Ordinary dividends", ordinary_dividends)
    schedule_b.add_line("Qualified", "Qualified dividends (for worksheet)", qualified_dividends)
    schedule_b.add_line("2a", "Capital gain distributions (1099-DIV)", capital_gain_distributions_from_1099)
    schedule_b.add_line("7", "Foreign tax paid (1099-DIV)", foreign_tax_paid_div)
    result.schedule_b = schedule_b

    if misc_income:
        audit_lines.append(f"1099-MISC other income: {format_currency(misc_income)}")

    # ---------------------------------------------------------------------
    # K-1 ordinary income and passive losses (Schedule E + Form 8582)
    # ---------------------------------------------------------------------
    schedule_e = FormResult(form_name="Schedule E")
    passive_income = Decimal("0")
    passive_loss = Decimal("0")
    passive_loss_by_entity: dict[str, Decimal] = {}
    nonpassive_income = Decimal("0")
    section_1231_total = Decimal("0")

    for k1 in data.k1s:
        section_1231_amount = _safe_decimal(k1.boxes.box_10)
        section_1231_total += section_1231_amount
        ordinary_total = (
            _safe_decimal(k1.boxes.box_1)
            + _safe_decimal(k1.boxes.box_2)
            + _safe_decimal(k1.boxes.box_3)
            + _safe_decimal(k1.boxes.box_4a)
            + _safe_decimal(k1.boxes.box_4b)
            + _safe_decimal(k1.boxes.box_4c)
            + _safe_decimal(k1.boxes.box_7)
            + _safe_decimal(k1.boxes.box_11)
        )
        if k1.passive_activity:
            if ordinary_total >= 0:
                passive_income += ordinary_total
            else:
                loss_amount = abs(ordinary_total)
                passive_loss += loss_amount
                passive_loss_by_entity[k1.entity_name] = passive_loss_by_entity.get(k1.entity_name, Decimal("0")) + loss_amount
        else:
            nonpassive_income += ordinary_total

    if section_1231_total != 0:
        _add_warning(
            result,
            audit_lines,
            (
                "K-1 box 10 (Section 1231) is non-zero. "
                "This engine does not fully model Form 4797/1231 netting; "
                "manual review required."
            ),
        )

    allowed_passive_loss = min(passive_loss, passive_income)
    net_passive = passive_income - allowed_passive_loss
    suspended_passive = passive_loss - allowed_passive_loss

    schedule_e.add_line("PassiveIncome", "Passive income (K-1)", passive_income)
    schedule_e.add_line("PassiveLoss", "Passive losses (K-1)", -passive_loss)
    schedule_e.add_line("AllowedPassiveLoss", "Allowed passive loss", -allowed_passive_loss)
    schedule_e.add_line("NetPassive", "Net passive income", net_passive)
    schedule_e.add_line("NonPassive", "Non-passive K-1 income", nonpassive_income)
    result.schedule_e = schedule_e

    form_8582 = FormResult(form_name="Form 8582")
    form_8582.add_line("1", "Passive income", passive_income)
    form_8582.add_line("2", "Passive losses", -passive_loss)
    form_8582.add_line("3", "Allowed losses", -allowed_passive_loss)
    form_8582.add_line("5", "Suspended losses", -suspended_passive)
    result.form_8582 = form_8582

    # Update suspended passive loss carryforward
    next_year = PriorYearCarryforward.model_validate(data.prior_year.model_dump())
    if passive_loss > 0:
        allowed_ratio = allowed_passive_loss / passive_loss if passive_loss > 0 else Decimal("0")
        for k1 in data.k1s:
            if k1.passive_activity:
                prior = next_year.suspended_passive_losses.get(k1.entity_name, Decimal("0"))
                entity_loss = passive_loss_by_entity.get(k1.entity_name, Decimal("0"))
                # Reduce entity loss by allowed_ratio; remainder is suspended
                entity_suspended = entity_loss - (entity_loss * allowed_ratio)
                next_year.suspended_passive_losses[k1.entity_name] = prior + entity_suspended
    result.next_year_carryforward = next_year

    # ---------------------------------------------------------------------
    # Form 8949 + Schedule D (Capital gains)
    # ---------------------------------------------------------------------
    form_8949 = FormResult(form_name="Form 8949")
    short_term = Decimal("0")
    long_term = Decimal("0")

    for form in data.form_1099_b:
        for tx in form.transactions:
            gain = tx.gain_loss
            if tx.term.value == "short":
                short_term += gain
            else:
                long_term += gain

    # K-1 capital gains
    k1_short = _sum_decimals(k1.boxes.box_8 for k1 in data.k1s)
    k1_long = _sum_decimals(k1.boxes.box_9a for k1 in data.k1s)
    short_term += k1_short
    long_term += k1_long

    # 1099-DIV box 2a capital gain distributions flow to Schedule D line 13.
    long_term += capital_gain_distributions_from_1099

    # Apply prior-year capital loss carryforward
    short_term += data.prior_year.short_term_capital_loss
    long_term += data.prior_year.long_term_capital_loss

    form_8949.add_line("ShortTerm", "Short-term total (incl. carryforward)", short_term)
    form_8949.add_line("LongTerm", "Long-term total (incl. carryforward)", long_term)
    result.form_8949 = form_8949

    schedule_d = FormResult(form_name="Schedule D")
    schedule_d.add_line("1a", "Short-term capital gain (loss)", short_term)
    schedule_d.add_line("15", "Long-term capital gain (loss)", long_term)

    net_capital = short_term + long_term
    if net_capital >= 0:
        capital_loss_deduction = Decimal("0")
        carryforward_short = Decimal("0")
        carryforward_long = Decimal("0")
    else:
        capital_loss_deduction = min(abs(net_capital), CAPITAL_LOSS_DEDUCTION_LIMIT)
        remaining = abs(net_capital) - capital_loss_deduction
        st_loss = max(Decimal("0"), -short_term)
        lt_loss = max(Decimal("0"), -long_term)
        total_loss = st_loss + lt_loss
        if total_loss > 0:
            carryforward_short = remaining * (st_loss / total_loss)
            carryforward_long = remaining * (lt_loss / total_loss)
        else:
            carryforward_short = Decimal("0")
            carryforward_long = Decimal("0")

    schedule_d.add_line("21", "Net capital gain (loss)", net_capital)
    schedule_d.add_line("21a", "Capital loss deduction", -capital_loss_deduction)
    result.schedule_d = schedule_d

    # Update next-year capital loss carryforward
    result.next_year_carryforward.short_term_capital_loss = carryforward_short
    result.next_year_carryforward.long_term_capital_loss = carryforward_long

    # ---------------------------------------------------------------------
    # Mortgage + Donation inputs (used for Schedule A after AGI)
    # ---------------------------------------------------------------------
    mortgage_interest = _sum_decimals(f.mortgage_interest for f in data.form_1098)
    principal = None
    if data.form_1098:
        principal = data.form_1098[0].outstanding_principal
    deductible_interest, mortgage_audit = calculate_deductible_mortgage_interest(
        mortgage_interest, principal
    )

    cash_donations = _sum_decimals(d.cash_amount for d in data.charitable_donations)
    property_donations = _sum_decimals(d.property_fmv for d in data.charitable_donations)
    audit_lines.append(mortgage_audit)

    # ---------------------------------------------------------------------
    # Income + AGI
    # ---------------------------------------------------------------------
    capital_income_for_agi = net_capital if net_capital >= 0 else -capital_loss_deduction
    other_income = nec_net + net_passive + nonpassive_income + misc_income
    total_income = (
        w2_wages
        + other_income
        + interest_income
        + ordinary_dividends
        + capital_income_for_agi
    )
    agi = total_income - se_deduction

    result.total_income = total_income
    result.agi = agi

    # ---------------------------------------------------------------------
    # Schedule A (Itemized Deductions) after AGI
    # ---------------------------------------------------------------------
    from .utils import CHARITABLE_APPRECIATED_PROPERTY_LIMIT_PERCENT, CHARITABLE_CASH_LIMIT_PERCENT

    total_salt_paid = data.property_taxes_paid + data.sales_taxes_paid
    salt, salt_audit = calculate_salt_deduction(agi, total_salt_paid)
    audit_lines.append(salt_audit)
    audit_lines.append(
        "SALT input details:\n"
        f"  Property taxes: ${data.property_taxes_paid:,.2f}\n"
        f"  Sales taxes elected: ${data.sales_taxes_paid:,.2f}\n"
        f"  Total state/local taxes paid: ${total_salt_paid:,.2f}"
    )

    cash_limit = agi * CHARITABLE_CASH_LIMIT_PERCENT
    property_limit = agi * CHARITABLE_APPRECIATED_PROPERTY_LIMIT_PERCENT
    allowed_cash = min(cash_donations, cash_limit)
    allowed_property = min(property_donations, property_limit)
    total_charity_allowed = allowed_cash + allowed_property
    charity_carryover = (cash_donations - allowed_cash) + (property_donations - allowed_property)

    schedule_a = FormResult(form_name="Schedule A")
    schedule_a.add_line("5e", "State and local taxes (capped)", salt)
    schedule_a.add_line("8a", "Mortgage interest (capped)", deductible_interest)
    schedule_a.add_line("11", "Charitable contributions (allowed)", total_charity_allowed)
    schedule_a.add_line("Total", "Total itemized deductions", salt + deductible_interest + total_charity_allowed)
    result.schedule_a = schedule_a

    # Carryover to next year
    result.next_year_carryforward.charitable_contribution_carryover = charity_carryover

    # ---------------------------------------------------------------------
    # Deductions: Standard vs Itemized
    # ---------------------------------------------------------------------
    standard_deduction = STANDARD_DEDUCTION[data.taxpayer.filing_status]
    itemized = schedule_a.get_line("Total")
    deduction_taken = max(standard_deduction, itemized)
    taxable_income = max(Decimal("0"), agi - deduction_taken)
    result.taxable_income = taxable_income

    # ---------------------------------------------------------------------
    # Tax calculations
    # ---------------------------------------------------------------------
    # Qualified Dividends and Capital Gain Tax Worksheet logic requires:
    # - preferential income cannot exceed taxable income
    # - net short-term losses reduce long-term capital gains taxed at pref rates
    # Source: 2025 Schedule D instructions worksheet
    # https://www.irs.gov/instructions/i1040sd
    long_term_after_st_offset = max(Decimal("0"), long_term + min(Decimal("0"), short_term))
    preferential_income = min(
        taxable_income,
        long_term_after_st_offset + qualified_dividends,
    )
    ordinary_income = max(Decimal("0"), taxable_income - preferential_income)

    audit_lines.append(
        "Preferential-rate income calculation:\n"
        f"  Taxable income: ${taxable_income:,.2f}\n"
        f"  Long-term gains before ST offset: ${long_term:,.2f}\n"
        f"  Short-term amount: ${short_term:,.2f}\n"
        f"  Long-term gains after ST loss offset: ${long_term_after_st_offset:,.2f}\n"
        f"  Qualified dividends: ${qualified_dividends:,.2f}\n"
        f"  Preferential income (capped): ${preferential_income:,.2f}\n"
        f"  Ordinary income: ${ordinary_income:,.2f}"
    )

    if data.taxpayer.filing_status.value != "married_filing_jointly":
        raise NotImplementedError("Only MFJ filing status is supported in this engine version.")
    ordinary_tax = calculate_tax_from_brackets(ordinary_income, TAX_BRACKETS_MFJ)
    capital_gains_tax, cap_audit = calculate_capital_gains_tax(
        ordinary_income=ordinary_income,
        long_term_gains=long_term_after_st_offset,
        qualified_dividends=qualified_dividends,
        filing_status=data.taxpayer.filing_status,
    )
    audit_lines.append(cap_audit)

    net_capital_for_niit = max(Decimal("0"), long_term + short_term)
    passive_for_niit = max(Decimal("0"), net_passive)
    net_investment_income = max(
        Decimal("0"),
        interest_income
        + ordinary_dividends
        + net_capital_for_niit
        + misc_income
        + passive_for_niit,
    )
    audit_lines.append(
        "NIIT net investment income inputs:\n"
        f"  Interest: ${interest_income:,.2f}\n"
        f"  Dividends: ${ordinary_dividends:,.2f}\n"
        f"  Net capital gain (LT+ST, floor 0): ${net_capital_for_niit:,.2f}\n"
        f"  1099-MISC other income: ${misc_income:,.2f}\n"
        f"  Passive income included for NIIT: ${passive_for_niit:,.2f}\n"
        f"  Net investment income total: ${net_investment_income:,.2f}"
    )
    niit, niit_audit = calculate_niit(agi, net_investment_income, data.taxpayer.filing_status)
    audit_lines.append(niit_audit)

    additional_medicare_tax, additional_withheld, medicare_audit = calculate_additional_medicare_tax(
        w2_medicare_wages=w2_medicare_wages,
        se_income=se_earnings,
        filing_status=data.taxpayer.filing_status,
    )
    audit_lines.append(medicare_audit)
    net_additional_medicare_tax = max(Decimal("0"), additional_medicare_tax - additional_withheld)

    ctc, ctc_audit = calculate_child_tax_credit(
        num_qualifying_children=sum(1 for d in data.taxpayer.dependents if d.qualifies_for_ctc),
        agi=agi,
        filing_status=data.taxpayer.filing_status,
    )
    audit_lines.append(ctc_audit)

    # ---------------------------------------------------------------------
    # Form 1116 (Foreign Tax Credit) - Passive category (RIC/1099-DIV)
    # ---------------------------------------------------------------------
    form_1116 = FormResult(form_name="Form 1116")
    schedule_3 = FormResult(form_name="Schedule 3")

    if foreign_tax_paid > 0:
        if foreign_source_income <= 0:
            _add_warning(
                result,
                audit_lines,
                (
                    f"Foreign tax paid (${foreign_tax_paid:,.2f}) detected but foreign-source income "
                    "is $0; populate 1099-DIV supplemental fields (foreign_source_income / "
                    "foreign_source_qualified_dividends) to compute Form 1116."
                ),
            )
        elif foreign_source_qualified_dividends > foreign_source_income:
            _add_warning(
                result,
                audit_lines,
                (
                    "foreign_source_qualified_dividends exceeds foreign_source_income; "
                    "Form 1116 inputs appear inconsistent."
                ),
            )
        else:
            # Determine whether qualified dividends/capital gains are taxed at 0% / 15% / 20%
            # for the purpose of the Form 1116 adjustment factors (0.4054 / 0.5405).
            pref_income_exists = (qualified_dividends + long_term_after_st_offset) > 0
            cap_gain_rate = Decimal("0")
            if pref_income_exists:
                if taxable_income > CAPITAL_GAINS_BRACKETS_MFJ[1][0]:
                    cap_gain_rate = Decimal("0.20")
                elif taxable_income > CAPITAL_GAINS_BRACKETS_MFJ[0][0]:
                    cap_gain_rate = Decimal("0.15")
                else:
                    cap_gain_rate = Decimal("0.00")

            if cap_gain_rate == Decimal("0.20"):
                adjustment_factor = Decimal("0.5405")
            elif cap_gain_rate == Decimal("0.15"):
                adjustment_factor = Decimal("0.4054")
            else:
                adjustment_factor = Decimal("0")

            # Form 1116 adjustment exception (Instructions for Form 1116):
            # If QD/CG worksheet line 5 does not exceed threshold AND foreign-source
            # (capital gain distributions + qualified dividends) < $20,000, no adjustment needed.
            # For MFJ, threshold is $394,600.
            adjustment_exception_threshold = Decimal("394600")
            foreign_pref_income = (
                foreign_source_qualified_dividends + foreign_source_capital_gain_distributions
            )
            qualifies_for_adjustment_exception = (
                taxable_income <= adjustment_exception_threshold
                and foreign_pref_income < Decimal("20000")
            )

            # Part I line 1a (gross income), with qualified-dividend adjustment if required.
            foreign_nonpref_income = (
                foreign_source_income
                - foreign_source_qualified_dividends
                - foreign_source_capital_gain_distributions
            )
            if foreign_nonpref_income < 0:
                foreign_nonpref_income = Decimal("0")

            if qualifies_for_adjustment_exception:
                foreign_income_adjusted = foreign_source_income
                foreign_qd_adjusted = foreign_source_qualified_dividends
                foreign_cg_dist_adjusted = foreign_source_capital_gain_distributions
            else:
                foreign_qd_adjusted = foreign_source_qualified_dividends * adjustment_factor
                foreign_cg_dist_adjusted = (
                    foreign_source_capital_gain_distributions * adjustment_factor
                )
                foreign_income_adjusted = (
                    foreign_nonpref_income + foreign_qd_adjusted + foreign_cg_dist_adjusted
                )

            # Approximate allocation of overall deductions/adjustments ratably to foreign income.
            # This is intentionally simplified (no detailed expense apportionment model).
            if result.total_income > 0:
                foreign_taxable_income = foreign_income_adjusted * (
                    taxable_income / result.total_income
                )
            else:
                foreign_taxable_income = Decimal("0")

            # Worksheet for Line 18 (Individuals): adjust worldwide taxable income (line 18)
            # when QD/CG are present and adjustment is required.
            def _adjusted_worldwide_taxable_income() -> Decimal:
                if qualifies_for_adjustment_exception or adjustment_factor == 0:
                    return taxable_income

                line1 = qualified_dividends
                line2 = capital_gain_distributions_from_1099
                line3 = max(Decimal("0"), long_term)  # Schedule D line 15 if positive
                line4 = line1 + line2 + line3
                line5 = taxable_income  # QD/CG worksheet line 5 (Form 1040 line 15)

                if line5 == line4:
                    return line5

                line6 = max(Decimal("0"), line5 - line4)
                line7 = min(line2, line6)
                line8 = line2 - line7

                line9 = line8 * adjustment_factor
                line10 = line3 * adjustment_factor
                line11 = line1 * adjustment_factor
                line12 = line9 + line10 + line11

                line13 = line1 + line2 + line3
                line14 = line13 - line12
                line15 = max(Decimal("0"), line5 - line4)
                line16 = line14 + line15
                return line16

            worldwide_taxable_income_adj = _adjusted_worldwide_taxable_income()

            # Form 1116 credit limitation.
            us_tax_for_credit = ordinary_tax + capital_gains_tax  # Form 1040 line 16
            numerator = max(Decimal("0"), foreign_taxable_income)
            denominator = max(Decimal("0"), worldwide_taxable_income_adj)
            limitation_ratio = (numerator / denominator) if denominator > 0 else Decimal("0")
            limitation = us_tax_for_credit * limitation_ratio

            foreign_tax_credit = min(foreign_tax_paid, limitation)
            # Nonrefundable: cannot exceed total tax after CTC (engine only models CTC here).
            total_tax_before_schedule3 = (
                us_tax_for_credit + niit + se_tax + net_additional_medicare_tax - ctc
            )
            foreign_tax_credit = min(foreign_tax_credit, max(Decimal("0"), total_tax_before_schedule3))

            audit_lines.append(
                "Foreign tax credit (Form 1116) summary:\n"
                f"  Foreign tax paid (total): ${foreign_tax_paid:,.2f}\n"
                f"  Foreign-source income (input): ${foreign_source_income:,.2f}\n"
                f"  Foreign-source qualified dividends (input): ${foreign_source_qualified_dividends:,.2f}\n"
                f"  Adjustment exception: {'YES' if qualifies_for_adjustment_exception else 'NO'}\n"
                f"  Adjustment factor used: {adjustment_factor}\n"
                f"  Foreign income adjusted (line 1a): ${foreign_income_adjusted:,.2f}\n"
                f"  Foreign taxable income (line 15 est.): ${foreign_taxable_income:,.2f}\n"
                f"  Worldwide taxable income (line 18 adj.): ${worldwide_taxable_income_adj:,.2f}\n"
                f"  US tax for credit (line 20): ${us_tax_for_credit:,.2f}\n"
                f"  Limitation ratio (line 19): {limitation_ratio:.6f}\n"
                f"  Limitation (line 21): ${limitation:,.2f}\n"
                f"  Allowed FTC (Schedule 3 line 1): ${foreign_tax_credit:,.2f}"
            )

            form_1116.add_line("1a", "Gross income from sources outside U.S. (adjusted)", foreign_income_adjusted)
            form_1116.add_line("7", "Net foreign source taxable income (est.)", foreign_taxable_income)
            form_1116.add_line("8", "Foreign taxes paid/accrued", foreign_tax_paid)
            form_1116.add_line("15", "Taxable income from sources outside U.S.", numerator)
            form_1116.add_line("18", "Taxable income from all sources (adjusted)", denominator)
            form_1116.add_line("20", "Tax against which credit is taken", us_tax_for_credit)
            form_1116.add_line("21", "FTC limitation (20×19)", limitation)
            form_1116.add_line("22", "Foreign tax credit allowed", foreign_tax_credit)

            schedule_3.add_line("1", "Foreign tax credit (Form 1116)", foreign_tax_credit)
            schedule_3.add_line("8", "Total other credits", foreign_tax_credit)

    if foreign_tax_paid > 0 and (foreign_source_income > 0 or foreign_tax_credit > 0):
        result.form_1116 = form_1116
        result.schedule_3 = schedule_3

    total_tax = (
        ordinary_tax
        + capital_gains_tax
        + niit
        + se_tax
        + net_additional_medicare_tax
        - ctc
        - foreign_tax_credit
    )
    result.total_tax = total_tax

    # ---------------------------------------------------------------------
    # Payments / Credits
    # ---------------------------------------------------------------------
    excess_ss_credit, ss_audit = calculate_excess_social_security_credit(w2_ss_withheld)
    audit_lines.append(ss_audit)

    other_withholding = _sum_decimals(f.federal_withheld for f in data.form_1099_int)
    other_withholding += _sum_decimals(f.federal_withheld for f in data.form_1099_div)
    other_withholding += _sum_decimals(f.federal_withheld for f in data.form_1099_nec)
    other_withholding += _sum_decimals(f.federal_withheld for f in data.form_1099_misc)
    federal_withholding_total = w2_withholding + other_withholding

    total_payments = federal_withholding_total + excess_ss_credit + data.estimated_tax_payments
    result.total_payments = total_payments
    result.refund_or_owed = total_payments - total_tax
    audit_lines.append(
        "Payments summary:\n"
        f"  Federal withholding: ${federal_withholding_total:,.2f}\n"
        f"  Excess SS credit: ${excess_ss_credit:,.2f}\n"
        f"  Estimated tax payments: ${data.estimated_tax_payments:,.2f}\n"
        f"  Total payments: ${total_payments:,.2f}"
    )

    # ---------------------------------------------------------------------
    # Form 8959 / 8962 placeholders
    # ---------------------------------------------------------------------
    form_8959 = FormResult(form_name="Form 8959")
    form_8959.add_line("6", "Additional Medicare tax", additional_medicare_tax)
    form_8959.add_line("13", "Additional Medicare tax withheld (est.)", additional_withheld)
    form_8959.add_line("18", "Net Additional Medicare tax", net_additional_medicare_tax)
    result.form_8959 = form_8959

    form_8962 = FormResult(form_name="Form 8962")
    if data.form_1095_a:
        total_premiums = _sum_decimals(c.premium_total for c in data.form_1095_a.coverages)
        total_slcsp = _sum_decimals(c.slcsp_total for c in data.form_1095_a.coverages)
        total_advance = _sum_decimals(c.advance_ptc_total for c in data.form_1095_a.coverages)
        form_8962.add_line("11", "Total premiums", total_premiums)
        form_8962.add_line("12", "Total SLCSP", total_slcsp)
        form_8962.add_line("26", "Advance PTC", total_advance)
        form_8962.add_line(
            "29",
            "Net PTC (placeholder - full Form 8962 not implemented)",
            Decimal("0"),
            notes=[
                "Engine does not run full Form 8962 household/FPL computation.",
                "Placeholder only; verify Form 8962 separately before filing any real return.",
            ],
        )
        if total_slcsp == 0 and total_premiums > 0:
            _add_warning(
                result,
                audit_lines,
                "1095-A SLCSP total is zero while premiums are non-zero; verify input data.",
            )
        if total_advance > 0:
            _add_warning(
                result,
                audit_lines,
                "Advance PTC exists but full Form 8962 reconciliation is not implemented.",
            )
        else:
            _add_warning(
                result,
                audit_lines,
                "Form 8962 is simplified; Net PTC is set to $0 as a placeholder.",
            )
    result.form_8962 = form_8962

    if foreign_tax_paid > 0 and foreign_tax_credit == 0:
        _add_warning(
            result,
            audit_lines,
            (
                f"Foreign tax paid (${foreign_tax_paid:,.2f}) detected but Form 1116 credit "
                "computed as $0; verify foreign-source income inputs and limitation math."
            ),
        )

    # Form 2210/6251 are intentionally out of scope in this estimator.
    # - 2210 safe harbor + annualized/waiver filing cases:
    #   https://www.irs.gov/instructions/i2210
    # - 6251 filing triggers and AMT worksheet rules:
    #   https://www.irs.gov/instructions/i6251
    _add_warning(
        result,
        audit_lines,
        "Form 2210 underpayment penalty is not implemented; validate separately if required.",
    )
    _add_warning(
        result,
        audit_lines,
        "Form 6251 AMT computation is not implemented; validate separately if required.",
    )

    # ---------------------------------------------------------------------
    # Form 8283 (noncash donations summary)
    # ---------------------------------------------------------------------
    form_8283 = FormResult(form_name="Form 8283")
    form_8283.add_line("SectionA", "Noncash contributions (FMV)", property_donations)
    result.form_8283 = form_8283

    # ---------------------------------------------------------------------
    # Form 1040 summary (high level)
    # ---------------------------------------------------------------------
    form_1040 = FormResult(form_name="Form 1040")
    form_1040.add_line("1", "Wages", w2_wages)
    form_1040.add_line("2b", "Taxable interest", interest_income)
    form_1040.add_line("3b", "Ordinary dividends", ordinary_dividends)
    form_1040.add_line("7", "Capital gain (loss)", capital_income_for_agi)
    form_1040.add_line("8", "Other income (Schedule 1)", other_income)
    form_1040.add_line("11", "Adjusted gross income", agi)
    form_1040.add_line("12", "Deductions (std/itemized)", deduction_taken)
    form_1040.add_line("15", "Taxable income", taxable_income)
    form_1040.add_line("16", "Tax", ordinary_tax + capital_gains_tax)
    form_1040.add_line("17", "Additional taxes (SE + NIIT + Medicare)", se_tax + niit + net_additional_medicare_tax)
    form_1040.add_line("19", "Credits (CTC)", ctc)
    if foreign_tax_credit:
        form_1040.add_line("20", "Credits (Schedule 3 - foreign tax credit)", foreign_tax_credit)
        form_1040.add_line("21", "Total credits", ctc + foreign_tax_credit)
    form_1040.add_line("24", "Total tax", total_tax)
    form_1040.add_line("25d", "Federal withholding", federal_withholding_total)
    form_1040.add_line("26", "Estimated tax payments", data.estimated_tax_payments)
    form_1040.add_line("31", "Excess SS credit", excess_ss_credit)
    form_1040.add_line("34", "Total payments", total_payments)
    form_1040.add_line("37", "Amount owed (negative = refund)", -result.refund_or_owed)
    result.form_1040 = form_1040

    # ---------------------------------------------------------------------
    # WA Capital Gains Tax
    # ---------------------------------------------------------------------
    wa_tax, wa_audit = calculate_wa_capital_gains_tax(
        long_term_capital_gains=long_term,
        wa_qualified_charitable_donations=data.wa_qualified_charitable_donations,
    )
    result.wa_capital_gains_tax = wa_tax
    audit_lines.append(wa_audit)

    if data.wa_qualified_charitable_donations == 0 and property_donations > 0:
        _add_warning(
            result,
            audit_lines,
            (
                "WA-qualified charitable donation input is $0 while federal noncash "
                "donations exist. This is intentional for non-WA-qualified donees; "
                "confirm if any donation qualifies under WA rules."
            ),
        )

    # Keep summary values human-readable.
    result.total_income = result.total_income.quantize(Decimal("0.01"))
    result.agi = result.agi.quantize(Decimal("0.01"))
    result.taxable_income = result.taxable_income.quantize(Decimal("0.01"))
    result.total_tax = result.total_tax.quantize(Decimal("0.01"))
    result.total_payments = result.total_payments.quantize(Decimal("0.01"))
    result.refund_or_owed = result.refund_or_owed.quantize(Decimal("0.01"))
    result.wa_capital_gains_tax = result.wa_capital_gains_tax.quantize(Decimal("0.01"))

    # Round output form lines to IRS-style whole dollars after all computations.
    _round_form_results(result)

    return result, audit_lines


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    result, audit_lines = calculate_2025()

    calculations_path = OUTPUT_DIR / "calculations.json"
    audit_path = OUTPUT_DIR / "audit_trail.txt"

    with calculations_path.open("w", encoding="utf-8") as f:
        json.dump(result.model_dump(mode="json"), f, indent=2)

    # Write a human-readable audit trail
    with audit_path.open("w", encoding="utf-8") as f:
        f.write("2025 TAX ENGINE AUDIT TRAIL\n")
        f.write("=" * 72 + "\n\n")
        for line in audit_lines:
            detail = line
            f.write(detail)
            f.write("\n\n")


if __name__ == "__main__":
    main()
