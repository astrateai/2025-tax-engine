"""Tax constants, tables, and utility functions for 2025 tax year."""

from decimal import Decimal
from decimal import ROUND_HALF_UP
from typing import Optional

from .models import FilingStatus


# =============================================================================
# 2025 Tax Year Constants
# =============================================================================

TAX_YEAR = 2025

# Standard deductions (2025, updated for OBBBA)
#
# Source:
# IRS Internal Revenue Bulletin 2025-45 (2025 adjusted items under OBBBA)
# https://www.irs.gov/irb/2025-45_IRB
STANDARD_DEDUCTION = {
    FilingStatus.SINGLE: Decimal("15750"),
    FilingStatus.MFJ: Decimal("31500"),
    FilingStatus.MFS: Decimal("15750"),
    FilingStatus.HOH: Decimal("23625"),
    FilingStatus.QSS: Decimal("31500"),
}

# Federal income tax brackets (ordinary income) - MFJ
# Format: (upper_bound, rate, tax_on_lower_brackets)
TAX_BRACKETS_MFJ = [
    (Decimal("23850"), Decimal("0.10"), Decimal("0")),
    (Decimal("96950"), Decimal("0.12"), Decimal("2385")),
    (Decimal("206700"), Decimal("0.22"), Decimal("11157")),
    (Decimal("394600"), Decimal("0.24"), Decimal("35302")),
    (Decimal("501050"), Decimal("0.32"), Decimal("80398")),
    (Decimal("751600"), Decimal("0.35"), Decimal("114462")),
    (None, Decimal("0.37"), Decimal("202154")),  # None = no upper bound
]

# Capital gains tax brackets - MFJ (2025)
#
# Source (2025 thresholds):
# IRS Rev. Proc. 2024-40, section 3.03
# https://www.irs.gov/pub/irs-drop/rp-24-40.pdf
CAPITAL_GAINS_BRACKETS_MFJ = [
    (Decimal("96700"), Decimal("0.00")),   # 0% rate
    (Decimal("600050"), Decimal("0.15")),  # 15% rate
    (None, Decimal("0.20")),               # 20% rate
]

# Net Investment Income Tax (NIIT)
NIIT_THRESHOLD = {
    FilingStatus.SINGLE: Decimal("200000"),
    FilingStatus.MFJ: Decimal("250000"),
    FilingStatus.MFS: Decimal("125000"),
    FilingStatus.HOH: Decimal("200000"),
    FilingStatus.QSS: Decimal("250000"),
}
NIIT_RATE = Decimal("0.038")

# Child Tax Credit (2025)
#
# Source:
# IRS Internal Revenue Bulletin 2025-45 (2025 Child Tax Credit updates)
# https://www.irs.gov/irb/2025-45_IRB
CTC_AMOUNT_PER_CHILD = Decimal("2200")
CTC_REFUNDABLE_MAX = Decimal("1700")  # Additional child tax credit max per child
CTC_PHASE_OUT_THRESHOLD = {
    FilingStatus.SINGLE: Decimal("200000"),
    FilingStatus.MFJ: Decimal("400000"),
    FilingStatus.MFS: Decimal("200000"),
    FilingStatus.HOH: Decimal("200000"),
    FilingStatus.QSS: Decimal("400000"),
}
CTC_PHASE_OUT_RATE = Decimal("50")  # $50 reduction per $1,000 over threshold

# SALT deduction cap (2025 law)
#
# Source:
# IRS 2025 Schedule A instructions + Tax Computation Worksheet
# https://www.irs.gov/instructions/i1040sca
SALT_CAP_STANDARD = Decimal("40000")
SALT_CAP_FLOOR = Decimal("10000")
SALT_PHASEOUT_START = Decimal("500000")  # MFJ

# Payroll tax constants
SOCIAL_SECURITY_RATE = Decimal("0.062")
MEDICARE_RATE = Decimal("0.0145")
ADDITIONAL_MEDICARE_RATE = Decimal("0.009")
ADDITIONAL_MEDICARE_THRESHOLD = {
    FilingStatus.SINGLE: Decimal("200000"),
    FilingStatus.MFJ: Decimal("250000"),
    FilingStatus.MFS: Decimal("125000"),
    FilingStatus.HOH: Decimal("200000"),
    FilingStatus.QSS: Decimal("250000"),
}
# 2025 wage base (update if IRS releases a different figure)
SOCIAL_SECURITY_WAGE_BASE = Decimal("176100")

# AMT exemption amounts - MFJ
AMT_EXEMPTION_MFJ = Decimal("137000")  # Estimated for 2025
AMT_PHASE_OUT_THRESHOLD_MFJ = Decimal("1252700")
AMT_RATES = [
    (Decimal("232600"), Decimal("0.26")),  # 26% up to this amount
    (None, Decimal("0.28")),               # 28% above
]

# Charitable contribution limits (as % of AGI)
CHARITABLE_CASH_LIMIT_PERCENT = Decimal("0.60")
CHARITABLE_APPRECIATED_PROPERTY_LIMIT_PERCENT = Decimal("0.30")

# Capital loss deduction limit
CAPITAL_LOSS_DEDUCTION_LIMIT = Decimal("3000")

# Mortgage interest limit (acquisition debt)
MORTGAGE_INTEREST_DEBT_LIMIT = Decimal("750000")


# =============================================================================
# Washington State Capital Gains Tax (2025)
# =============================================================================

WA_CG_STANDARD_DEDUCTION = Decimal("278000")
# WA charitable deduction only applies to qualifying donations above this threshold,
# then is capped.
# Source:
# RCW 82.87.080 and WA DOR guidance
# https://app.leg.wa.gov/RCW/default.aspx?cite=82.87.080
# https://dor.wa.gov/taxes-rates/other-taxes/capital-gains-tax/deductions-and-exemptions
WA_CG_CHARITABLE_DONATION_THRESHOLD = Decimal("278000")
WA_CG_BRACKETS = [
    (Decimal("1000000"), Decimal("0.07")),  # 7% on first $1M after deduction
    (None, Decimal("0.099")),               # 9.9% on amounts over $1M
]
WA_CG_CHARITABLE_DEDUCTION_LIMIT = Decimal("111000")


# =============================================================================
# Utility Functions
# =============================================================================


def calculate_tax_from_brackets(
    taxable_income: Decimal,
    brackets: list[tuple[Optional[Decimal], Decimal, Decimal]],
) -> Decimal:
    """
    Calculate tax using bracket system.

    Brackets format: [(upper_bound, rate, cumulative_tax_at_lower), ...]
    """
    if taxable_income <= 0:
        return Decimal("0")

    for i, (upper, rate, cumulative) in enumerate(brackets):
        if upper is None or taxable_income <= upper:
            if i == 0:
                lower = Decimal("0")
            else:
                lower = brackets[i - 1][0]
            return cumulative + (taxable_income - lower) * rate

    # Should not reach here
    return Decimal("0")


def calculate_capital_gains_tax(
    ordinary_income: Decimal,
    long_term_gains: Decimal,
    qualified_dividends: Decimal,
    filing_status: FilingStatus,
) -> tuple[Decimal, str]:
    """
    Calculate tax on long-term capital gains and qualified dividends.

    Returns (tax_amount, audit_trail_description).

    The capital gains "stack" on top of ordinary income, filling brackets
    from where ordinary income left off.
    """
    if filing_status != FilingStatus.MFJ:
        raise NotImplementedError(f"Capital gains calculation not implemented for {filing_status}")

    brackets = CAPITAL_GAINS_BRACKETS_MFJ
    total_gains = long_term_gains + qualified_dividends

    if total_gains <= 0:
        return Decimal("0"), "No capital gains to tax"

    audit_lines = []
    tax = Decimal("0")
    gains_remaining = total_gains
    current_income = ordinary_income

    for i, (threshold, rate) in enumerate(brackets):
        if threshold is None:
            # Top bracket - tax all remaining at this rate
            bracket_tax = gains_remaining * rate
            tax += bracket_tax
            audit_lines.append(f"  ${gains_remaining:,.0f} at {rate*100:.1f}% = ${bracket_tax:,.0f}")
            break

        if current_income >= threshold:
            # Already past this bracket with ordinary income
            continue

        # How much room in this bracket?
        room_in_bracket = threshold - current_income
        gains_in_bracket = min(room_in_bracket, gains_remaining)

        if gains_in_bracket > 0:
            bracket_tax = gains_in_bracket * rate
            tax += bracket_tax
            audit_lines.append(f"  ${gains_in_bracket:,.0f} at {rate*100:.1f}% = ${bracket_tax:,.0f}")

            gains_remaining -= gains_in_bracket
            current_income += gains_in_bracket

        if gains_remaining <= 0:
            break

    audit = "Capital gains tax calculation:\n" + "\n".join(audit_lines)
    return tax, audit


def calculate_niit(
    magi: Decimal,
    net_investment_income: Decimal,
    filing_status: FilingStatus,
) -> tuple[Decimal, str]:
    """
    Calculate Net Investment Income Tax (Form 8960).

    Returns (tax_amount, audit_trail_description).
    """
    threshold = NIIT_THRESHOLD[filing_status]

    if magi <= threshold:
        return Decimal("0"), f"MAGI ${magi:,.0f} <= threshold ${threshold:,.0f}, no NIIT"

    excess_magi = magi - threshold
    taxable_amount = min(net_investment_income, excess_magi)
    niit = taxable_amount * NIIT_RATE

    audit = (
        f"NIIT calculation:\n"
        f"  MAGI: ${magi:,.0f}\n"
        f"  Threshold: ${threshold:,.0f}\n"
        f"  Excess MAGI: ${excess_magi:,.0f}\n"
        f"  Net investment income: ${net_investment_income:,.0f}\n"
        f"  Taxable amount (lesser): ${taxable_amount:,.0f}\n"
        f"  NIIT (3.8%): ${niit:,.0f}"
    )
    return niit, audit


def calculate_child_tax_credit(
    num_qualifying_children: int,
    agi: Decimal,
    filing_status: FilingStatus,
) -> tuple[Decimal, str]:
    """
    Calculate Child Tax Credit with phase-out.

    Returns (credit_amount, audit_trail_description).
    """
    if num_qualifying_children == 0:
        return Decimal("0"), "No qualifying children"

    base_credit = CTC_AMOUNT_PER_CHILD * num_qualifying_children
    threshold = CTC_PHASE_OUT_THRESHOLD[filing_status]

    if agi <= threshold:
        return base_credit, f"Full credit: {num_qualifying_children} × ${CTC_AMOUNT_PER_CHILD:,.0f} = ${base_credit:,.0f}"

    # Phase-out: $50 per $1,000 over threshold (rounded up)
    excess = agi - threshold
    reduction_units = (excess + 999) // 1000  # Round up to nearest $1,000
    reduction = reduction_units * CTC_PHASE_OUT_RATE

    credit = max(Decimal("0"), base_credit - reduction)

    audit = (
        f"Child Tax Credit calculation:\n"
        f"  Qualifying children: {num_qualifying_children}\n"
        f"  Base credit: ${base_credit:,.0f}\n"
        f"  AGI: ${agi:,.0f}\n"
        f"  Phase-out threshold: ${threshold:,.0f}\n"
        f"  Excess: ${excess:,.0f}\n"
        f"  Reduction (${CTC_PHASE_OUT_RATE} per $1,000): ${reduction:,.0f}\n"
        f"  Final credit: ${credit:,.0f}"
    )
    return credit, audit


def calculate_wa_capital_gains_tax(
    long_term_capital_gains: Decimal,
    wa_qualified_charitable_donations: Decimal = Decimal("0"),
) -> tuple[Decimal, str]:
    """
    Calculate Washington State capital gains tax.

    Returns (tax_amount, audit_trail_description).
    """
    # Apply standard deduction
    taxable = long_term_capital_gains - WA_CG_STANDARD_DEDUCTION

    # Charitable deduction applies only to the amount above the annual threshold.
    charitable_base = max(
        Decimal("0"),
        wa_qualified_charitable_donations - WA_CG_CHARITABLE_DONATION_THRESHOLD,
    )
    charitable_deduction = min(charitable_base, WA_CG_CHARITABLE_DEDUCTION_LIMIT)
    taxable = taxable - charitable_deduction

    if taxable <= 0:
        return Decimal("0"), f"No WA capital gains tax (gains ${long_term_capital_gains:,.0f} - deduction ${WA_CG_STANDARD_DEDUCTION:,.0f} <= 0)"

    tax = Decimal("0")
    audit_lines = []
    remaining = taxable

    for threshold, rate in WA_CG_BRACKETS:
        if threshold is None:
            # Top bracket
            bracket_tax = remaining * rate
            tax += bracket_tax
            audit_lines.append(f"  ${remaining:,.0f} at {rate*100:.1f}% = ${bracket_tax:,.0f}")
            break

        amount_in_bracket = min(remaining, threshold)
        bracket_tax = amount_in_bracket * rate
        tax += bracket_tax
        audit_lines.append(f"  ${amount_in_bracket:,.0f} at {rate*100:.1f}% = ${bracket_tax:,.0f}")

        remaining -= amount_in_bracket
        if remaining <= 0:
            break

    audit = (
        f"WA Capital Gains Tax calculation:\n"
        f"  Long-term capital gains: ${long_term_capital_gains:,.0f}\n"
        f"  Standard deduction: ${WA_CG_STANDARD_DEDUCTION:,.0f}\n"
        f"  WA-qualified charitable donations: ${wa_qualified_charitable_donations:,.0f}\n"
        f"  Charitable deduction base above threshold: ${charitable_base:,.0f}\n"
        f"  Charitable deduction after cap: ${charitable_deduction:,.0f}\n"
        f"  Taxable amount: ${taxable:,.0f}\n"
        + "\n".join(audit_lines) +
        f"\n  Total WA tax: ${tax:,.0f}"
    )
    return tax, audit


def format_currency(amount: Decimal) -> str:
    """Format a decimal as currency."""
    if amount < 0:
        return f"-${abs(amount):,.2f}"
    return f"${amount:,.2f}"


def round_to_dollar(amount: Decimal) -> Decimal:
    """Round to nearest whole dollar using IRS-style half-up rounding."""
    return amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def calculate_deductible_mortgage_interest(
    mortgage_interest: Decimal,
    outstanding_principal: Optional[Decimal],
) -> tuple[Decimal, str]:
    """
    Apply the $750k acquisition debt limit (pro-rata) to mortgage interest.
    """
    if outstanding_principal is None or outstanding_principal <= 0:
        return mortgage_interest, "No principal provided; using full mortgage interest"

    if outstanding_principal <= MORTGAGE_INTEREST_DEBT_LIMIT:
        return mortgage_interest, "Principal <= $750k; full mortgage interest deductible"

    ratio = MORTGAGE_INTEREST_DEBT_LIMIT / outstanding_principal
    deductible = mortgage_interest * ratio
    audit = (
        f"Mortgage interest cap applied:\n"
        f"  Outstanding principal: ${outstanding_principal:,.2f}\n"
        f"  Cap: ${MORTGAGE_INTEREST_DEBT_LIMIT:,.0f}\n"
        f"  Ratio: {ratio:.6f}\n"
        f"  Deductible interest: ${deductible:,.2f}"
    )
    return deductible, audit


def calculate_salt_deduction(
    agi: Decimal,
    state_local_taxes_paid: Decimal,
) -> tuple[Decimal, str]:
    """
    Calculate SALT deduction cap for 2025 (simplified for MFJ).

    The 2025 law increases the cap to $40k with a phase-down above $500k MAGI,
    not falling below $10k. For this engine (MFJ-only), we assume AGI as a
    proxy for MAGI and apply the floor when AGI > $500k.
    """
    if agi <= SALT_PHASEOUT_START:
        cap = SALT_CAP_STANDARD
        audit = (
            f"SALT cap applied:\n"
            f"  AGI: ${agi:,.2f}\n"
            f"  Cap: ${cap:,.0f}"
        )
    else:
        reduction = (agi - SALT_PHASEOUT_START) * Decimal("0.30")
        cap = max(SALT_CAP_FLOOR, SALT_CAP_STANDARD - reduction)
        audit = (
            f"SALT cap applied (phase-down):\n"
            f"  AGI: ${agi:,.2f}\n"
            f"  Base cap: ${SALT_CAP_STANDARD:,.0f}\n"
            f"  Reduction (30% of excess): ${reduction:,.2f}\n"
            f"  Cap after phase-down: ${cap:,.0f}"
        )

    deductible = min(state_local_taxes_paid, cap)
    return deductible, audit


def calculate_self_employment_tax(
    net_profit: Decimal,
    w2_social_security_wages: Decimal,
) -> tuple[Decimal, Decimal, str]:
    """
    Calculate Schedule SE tax and the above-the-line deduction (half).
    """
    if net_profit <= 0:
        return Decimal("0"), Decimal("0"), "No self-employment income"

    se_earnings = net_profit * Decimal("0.9235")
    remaining_ss_base = max(Decimal("0"), SOCIAL_SECURITY_WAGE_BASE - w2_social_security_wages)
    ss_taxable = min(se_earnings, remaining_ss_base)
    ss_tax = ss_taxable * Decimal("0.124")
    medicare_tax = se_earnings * Decimal("0.029")
    total_tax = ss_tax + medicare_tax
    deduction = total_tax / 2

    audit = (
        f"Self-employment tax:\n"
        f"  Net profit: ${net_profit:,.2f}\n"
        f"  SE earnings (92.35%): ${se_earnings:,.2f}\n"
        f"  SS taxable (remaining base): ${ss_taxable:,.2f}\n"
        f"  SS tax (12.4%): ${ss_tax:,.2f}\n"
        f"  Medicare tax (2.9%): ${medicare_tax:,.2f}\n"
        f"  Total SE tax: ${total_tax:,.2f}\n"
        f"  Deduction (50%): ${deduction:,.2f}"
    )
    return total_tax, deduction, audit


def calculate_additional_medicare_tax(
    w2_medicare_wages: list[Decimal],
    se_income: Decimal,
    filing_status: FilingStatus,
) -> tuple[Decimal, Decimal, str]:
    """
    Calculate Additional Medicare Tax (Form 8959).

    Returns (tax_due, tax_withheld_estimate, audit).
    """
    threshold = ADDITIONAL_MEDICARE_THRESHOLD[filing_status]
    total_wages = sum(w2_medicare_wages)
    total_income = total_wages + se_income
    taxable_excess = max(Decimal("0"), total_income - threshold)
    tax_due = taxable_excess * ADDITIONAL_MEDICARE_RATE

    # Estimate additional Medicare withheld by each employer (above $200k per employer)
    withheld_estimate = Decimal("0")
    for wage in w2_medicare_wages:
        withheld_estimate += max(Decimal("0"), wage - Decimal("200000")) * ADDITIONAL_MEDICARE_RATE

    audit = (
        f"Additional Medicare tax:\n"
        f"  Total wages: ${total_wages:,.2f}\n"
        f"  SE income: ${se_income:,.2f}\n"
        f"  Threshold: ${threshold:,.2f}\n"
        f"  Excess: ${taxable_excess:,.2f}\n"
        f"  Tax due (0.9%): ${tax_due:,.2f}\n"
        f"  Estimated withheld: ${withheld_estimate:,.2f}"
    )
    return tax_due, withheld_estimate, audit


def calculate_excess_social_security_credit(
    total_ss_withheld: Decimal,
) -> tuple[Decimal, str]:
    """
    Calculate excess Social Security withholding credit.
    """
    max_ss_tax = SOCIAL_SECURITY_WAGE_BASE * SOCIAL_SECURITY_RATE
    excess = max(Decimal("0"), total_ss_withheld - max_ss_tax)
    audit = (
        f"Excess Social Security withholding:\n"
        f"  SS wage base: ${SOCIAL_SECURITY_WAGE_BASE:,.2f}\n"
        f"  Max SS tax (6.2%): ${max_ss_tax:,.2f}\n"
        f"  Withheld: ${total_ss_withheld:,.2f}\n"
        f"  Excess credit: ${excess:,.2f}"
    )
    return excess, audit
