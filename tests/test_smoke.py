from decimal import Decimal

from src.engine import calculate_2025


def test_example_fixtures_produce_a_complete_result() -> None:
    result, audit_lines = calculate_2025()

    assert result.form_1040 is not None
    assert result.schedule_a is not None
    assert result.schedule_b is not None
    assert result.schedule_c is not None
    assert result.schedule_d is not None
    assert result.total_income > Decimal("0")
    assert result.total_payments >= Decimal("0")
    assert result.form_1040.get_line("24") == result.total_tax.quantize(Decimal("1"))
    assert audit_lines
