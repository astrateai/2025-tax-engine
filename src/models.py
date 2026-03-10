"""Data models for tax documents and calculations."""

from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# =============================================================================
# Enums
# =============================================================================


class FilingStatus(str, Enum):
    SINGLE = "single"
    MFJ = "married_filing_jointly"
    MFS = "married_filing_separately"
    HOH = "head_of_household"
    QSS = "qualifying_surviving_spouse"


class CapitalGainTerm(str, Enum):
    SHORT = "short"
    LONG = "long"


# =============================================================================
# Input Documents
# =============================================================================


class W2(BaseModel):
    """Form W-2: Wage and Tax Statement."""

    employer: str
    ein: str
    wages: Decimal = Field(description="Box 1: Wages, tips, other compensation")
    federal_withheld: Decimal = Field(description="Box 2: Federal income tax withheld")
    social_security_wages: Decimal = Field(description="Box 3")
    social_security_withheld: Decimal = Field(description="Box 4")
    medicare_wages: Decimal = Field(description="Box 5")
    medicare_withheld: Decimal = Field(description="Box 6")
    state: Optional[str] = Field(default=None, description="Box 15: State")
    state_wages: Optional[Decimal] = Field(default=None, description="Box 16")
    state_withheld: Optional[Decimal] = Field(default=None, description="Box 17")


class Form1099INT(BaseModel):
    """Form 1099-INT: Interest Income."""

    payer: str
    interest_income: Decimal = Field(description="Box 1: Interest income")
    early_withdrawal_penalty: Decimal = Field(default=Decimal("0"), description="Box 2")
    us_savings_bond_interest: Decimal = Field(default=Decimal("0"), description="Box 3")
    federal_withheld: Decimal = Field(default=Decimal("0"), description="Box 4")
    investment_expenses: Decimal = Field(default=Decimal("0"), description="Box 5")
    foreign_tax_paid: Decimal = Field(default=Decimal("0"), description="Box 6")
    tax_exempt_interest: Decimal = Field(default=Decimal("0"), description="Box 8")


class Form1099DIV(BaseModel):
    """Form 1099-DIV: Dividends and Distributions."""

    payer: str
    ordinary_dividends: Decimal = Field(description="Box 1a: Total ordinary dividends")
    qualified_dividends: Decimal = Field(description="Box 1b: Qualified dividends")
    capital_gain_distributions: Decimal = Field(
        default=Decimal("0"), description="Box 2a"
    )
    section_1250_gain: Decimal = Field(default=Decimal("0"), description="Box 2b")
    section_1202_gain: Decimal = Field(default=Decimal("0"), description="Box 2c")
    collectibles_gain: Decimal = Field(default=Decimal("0"), description="Box 2d")
    nondividend_distributions: Decimal = Field(
        default=Decimal("0"), description="Box 3"
    )
    federal_withheld: Decimal = Field(default=Decimal("0"), description="Box 4")
    foreign_tax_paid: Decimal = Field(default=Decimal("0"), description="Box 7")
    foreign_source_income: Decimal = Field(
        default=Decimal("0"),
        description="Supplemental: foreign-source income for Form 1116 limitation",
    )
    foreign_source_qualified_dividends: Decimal = Field(
        default=Decimal("0"),
        description="Supplemental: foreign-source qualified dividends (subset of foreign-source income)",
    )
    foreign_source_capital_gain_distributions: Decimal = Field(
        default=Decimal("0"),
        description="Supplemental: foreign-source capital gain distributions (subset of foreign-source income)",
    )


class Form1099NEC(BaseModel):
    """Form 1099-NEC: Nonemployee Compensation."""

    payer: str
    nonemployee_comp: Decimal = Field(description="Box 1: Nonemployee compensation")
    federal_withheld: Decimal = Field(default=Decimal("0"), description="Box 4")
    state: Optional[str] = Field(default=None, description="Box 6")
    state_income: Decimal = Field(default=Decimal("0"), description="Box 7")


class Form1099MISC(BaseModel):
    """Form 1099-MISC: Miscellaneous Information (e.g., other income)."""

    payer: str
    other_income: Decimal = Field(description="Box 3: Other income")
    federal_withheld: Decimal = Field(default=Decimal("0"), description="Box 4")
    state: Optional[str] = Field(default=None, description="Box 16")
    state_income: Decimal = Field(default=Decimal("0"), description="Box 17")


class CapitalTransaction(BaseModel):
    """A single capital asset sale (for Form 8949)."""

    description: str
    date_acquired: date
    date_sold: date
    proceeds: Decimal
    cost_basis: Decimal
    adjustment_code: Optional[str] = None
    adjustment_amount: Decimal = Field(default=Decimal("0"))
    reported_to_irs: bool = Field(
        default=True,
        description=(
            "Was this transaction reported to IRS on Form 1099-B "
            "(this flag is about reporting presence, not basis coverage)"
        ),
    )

    @property
    def gain_loss(self) -> Decimal:
        return self.proceeds - self.cost_basis + self.adjustment_amount

    @property
    def term(self) -> CapitalGainTerm:
        days_held = (self.date_sold - self.date_acquired).days
        return CapitalGainTerm.LONG if days_held > 365 else CapitalGainTerm.SHORT


class Form1099B(BaseModel):
    """Form 1099-B: Proceeds from Broker and Barter Exchange Transactions."""

    broker: str
    transactions: list[CapitalTransaction]


class Form1095ACoverage(BaseModel):
    """Form 1095-A: Marketplace coverage summary (aggregated)."""

    months: str
    premium_total: Decimal = Field(description="Total annual premiums")
    slcsp_total: Decimal = Field(description="Second lowest cost silver plan total")
    advance_ptc_total: Decimal = Field(description="Advance premium tax credit total")


class Form1095A(BaseModel):
    """Form 1095-A: Health Insurance Marketplace Statement."""

    coverages: list[Form1095ACoverage]


class K1Boxes(BaseModel):
    """Schedule K-1 (Form 1065) box values."""

    # Ordinary income
    box_1: Decimal = Field(default=Decimal("0"), description="Ordinary business income (loss)")
    box_2: Decimal = Field(default=Decimal("0"), description="Net rental real estate income (loss)")
    box_3: Decimal = Field(default=Decimal("0"), description="Other net rental income (loss)")

    # Guaranteed payments
    box_4a: Decimal = Field(default=Decimal("0"), description="Guaranteed payments for services")
    box_4b: Decimal = Field(default=Decimal("0"), description="Guaranteed payments for capital")
    box_4c: Decimal = Field(default=Decimal("0"), description="Total guaranteed payments")

    # Interest and dividends
    box_5: Decimal = Field(default=Decimal("0"), description="Interest income")
    box_6a: Decimal = Field(default=Decimal("0"), description="Ordinary dividends")
    box_6b: Decimal = Field(default=Decimal("0"), description="Qualified dividends")
    box_6c: Decimal = Field(default=Decimal("0"), description="Dividend equivalents")

    # Royalties
    box_7: Decimal = Field(default=Decimal("0"), description="Royalties")

    # Capital gains
    box_8: Decimal = Field(default=Decimal("0"), description="Net short-term capital gain (loss)")
    box_9a: Decimal = Field(default=Decimal("0"), description="Net long-term capital gain (loss)")
    box_9b: Decimal = Field(default=Decimal("0"), description="Collectibles (28%) gain (loss)")
    box_9c: Decimal = Field(default=Decimal("0"), description="Unrecaptured section 1250 gain")

    # Section 1231 and other
    box_10: Decimal = Field(default=Decimal("0"), description="Net section 1231 gain (loss)")
    box_11: Decimal = Field(default=Decimal("0"), description="Other income (loss)")

    # Section 179 and other deductions
    box_12: Decimal = Field(default=Decimal("0"), description="Section 179 deduction")
    box_13: dict = Field(default_factory=dict, description="Other deductions (codes)")

    # Self-employment
    box_14: dict = Field(default_factory=dict, description="Self-employment earnings")

    # Credits
    box_15: dict = Field(default_factory=dict, description="Credits")

    # Foreign transactions
    box_16: dict = Field(default_factory=dict, description="Foreign transactions")

    # AMT items
    box_17: dict = Field(default_factory=dict, description="Alternative minimum tax (AMT) items")

    # Tax-exempt income
    box_18: dict = Field(default_factory=dict, description="Tax-exempt income and nondeductible expenses")

    # Distributions
    box_19: dict = Field(default_factory=dict, description="Distributions")

    # Other information
    box_20: dict = Field(default_factory=dict, description="Other information")


class ScheduleK1(BaseModel):
    """Schedule K-1 (Form 1065): Partner's Share of Income, Deductions, Credits."""

    entity_name: str
    ein: str
    tax_year: int
    partner_share_profit: Decimal = Field(description="Partner's share of profit %")
    partner_share_loss: Decimal = Field(description="Partner's share of loss %")
    partner_share_capital: Decimal = Field(description="Partner's share of capital %")
    boxes: K1Boxes
    passive_activity: bool = Field(
        description="Is this a passive activity for this partner?"
    )
    at_risk: bool = Field(default=True, description="Is partner at risk?")


class Form1098(BaseModel):
    """Form 1098: Mortgage Interest Statement."""

    lender: str
    mortgage_interest: Decimal = Field(description="Box 1: Mortgage interest received")
    points_paid: Decimal = Field(default=Decimal("0"), description="Box 6: Points paid")
    property_taxes: Decimal = Field(default=Decimal("0"), description="Box 10: Real estate taxes")
    property_address: str
    outstanding_principal: Optional[Decimal] = Field(
        default=None, description="Box 2: Outstanding mortgage principal"
    )


class CharitableDonation(BaseModel):
    """A charitable contribution."""

    recipient: str
    date: date
    cash_amount: Decimal = Field(default=Decimal("0"))
    property_description: Optional[str] = None
    property_fmv: Decimal = Field(default=Decimal("0"), description="Fair market value")
    property_cost_basis: Decimal = Field(default=Decimal("0"))
    property_acquired_date: Optional[date] = None

    @property
    def is_cash(self) -> bool:
        return self.cash_amount > 0

    @property
    def is_appreciated_property(self) -> bool:
        return self.property_fmv > self.property_cost_basis


class PriorYearCarryforward(BaseModel):
    """Carryforward items from prior tax year."""

    short_term_capital_loss: Decimal = Field(default=Decimal("0"))
    long_term_capital_loss: Decimal = Field(default=Decimal("0"))
    suspended_passive_losses: dict[str, Decimal] = Field(
        default_factory=dict, description="Entity name -> suspended loss amount"
    )
    amt_credit: Decimal = Field(default=Decimal("0"))
    charitable_contribution_carryover: Decimal = Field(default=Decimal("0"))


class Dependent(BaseModel):
    """A dependent for tax purposes."""

    name: str
    ssn: str
    relationship: str
    date_of_birth: date
    months_lived_with_taxpayer: int = 12
    qualifies_for_ctc: bool = Field(
        description="Qualifies for Child Tax Credit (under 17 at end of year)"
    )


# =============================================================================
# Taxpayer Info
# =============================================================================


class TaxpayerInfo(BaseModel):
    """Primary taxpayer and spouse information."""

    name: str
    ssn: str
    spouse_name: Optional[str] = None
    spouse_ssn: Optional[str] = None
    filing_status: FilingStatus
    address: str
    city: str
    state: str
    zip_code: str
    dependents: list[Dependent] = Field(default_factory=list)


# =============================================================================
# Aggregated Tax Data
# =============================================================================


class TaxYear2025Data(BaseModel):
    """All input data for 2025 tax year."""

    taxpayer: TaxpayerInfo
    w2s: list[W2] = Field(default_factory=list)
    form_1099_int: list[Form1099INT] = Field(default_factory=list)
    form_1099_div: list[Form1099DIV] = Field(default_factory=list)
    form_1099_nec: list[Form1099NEC] = Field(default_factory=list)
    form_1099_misc: list[Form1099MISC] = Field(default_factory=list)
    form_1099_b: list[Form1099B] = Field(default_factory=list)
    form_1095_a: Optional[Form1095A] = None
    k1s: list[ScheduleK1] = Field(default_factory=list)
    form_1098: list[Form1098] = Field(default_factory=list)
    charitable_donations: list[CharitableDonation] = Field(default_factory=list)
    property_taxes_paid: Decimal = Field(default=Decimal("0"))
    sales_taxes_paid: Decimal = Field(default=Decimal("0"))
    estimated_tax_payments: Decimal = Field(default=Decimal("0"))
    wa_qualified_charitable_donations: Decimal = Field(default=Decimal("0"))
    prior_year: PriorYearCarryforward = Field(default_factory=PriorYearCarryforward)


# =============================================================================
# Calculation Results
# =============================================================================


class CalculationLine(BaseModel):
    """A single line item calculation with audit trail."""

    line: str
    description: str
    value: Decimal
    formula: Optional[str] = None
    inputs: dict = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class FormResult(BaseModel):
    """Result of calculating a form/schedule."""

    form_name: str
    lines: dict[str, CalculationLine] = Field(default_factory=dict)

    def get_line(self, line: str) -> Decimal:
        if line in self.lines:
            return self.lines[line].value
        return Decimal("0")

    def add_line(
        self,
        line: str,
        description: str,
        value: Decimal,
        formula: Optional[str] = None,
        inputs: Optional[dict] = None,
        notes: Optional[list[str]] = None,
    ) -> None:
        self.lines[line] = CalculationLine(
            line=line,
            description=description,
            value=value,
            formula=formula,
            inputs=inputs or {},
            notes=notes or [],
        )


class TaxCalculationResult(BaseModel):
    """Complete tax calculation results."""

    # Calculated forms
    schedule_c: Optional[FormResult] = None
    schedule_e: Optional[FormResult] = None
    schedule_se: Optional[FormResult] = None
    schedule_1: Optional[FormResult] = None
    schedule_b: Optional[FormResult] = None
    schedule_d: Optional[FormResult] = None
    schedule_a: Optional[FormResult] = None
    schedule_3: Optional[FormResult] = None
    form_8949: Optional[FormResult] = None
    form_1116: Optional[FormResult] = None
    form_8582: Optional[FormResult] = None
    form_8959: Optional[FormResult] = None
    form_8960: Optional[FormResult] = None
    form_8962: Optional[FormResult] = None
    form_2210: Optional[FormResult] = None
    form_6251: Optional[FormResult] = None
    form_8283: Optional[FormResult] = None
    form_8812: Optional[FormResult] = None
    form_1040: Optional[FormResult] = None

    # Summary values
    total_income: Decimal = Field(default=Decimal("0"))
    agi: Decimal = Field(default=Decimal("0"))
    taxable_income: Decimal = Field(default=Decimal("0"))
    total_tax: Decimal = Field(default=Decimal("0"))
    total_payments: Decimal = Field(default=Decimal("0"))
    refund_or_owed: Decimal = Field(default=Decimal("0"))

    # State taxes
    wa_capital_gains_tax: Decimal = Field(default=Decimal("0"))

    # Carryforwards to next year
    next_year_carryforward: PriorYearCarryforward = Field(
        default_factory=PriorYearCarryforward
    )

    # Non-fatal caveats that need manual review before filing
    warnings: list[str] = Field(default_factory=list)
