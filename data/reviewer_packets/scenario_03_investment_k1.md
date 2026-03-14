# Reviewer Packet — scenario_03_investment_k1

## Return Type and Tax Year
- Type: 1040-family pilot return
- Tax year: 2025

## Taxpayer Summary
- Taxpayer: Example Taxpayer
- Filing status: married_filing_jointly
- State (taxpayer): VA
- W-2 count: 2
- 1099 counts: 1099-INT=2, 1099-DIV=1, 1099-NEC=1, 1099-MISC=1, 1099-B=1

## Key Form 1040 Totals
- Taxable income (L15): $12,222.00
- Total tax (L24): $-2,943.00
- Total payments (L33): $6,984.00
- Refund (L35a): $0.00
- Amount owed (L37): $-9,927.00

## Reviewer Attention Flags
- Taxpayer state 'VA' differs from W-2 state set ['WA'].
- VA state handling requires mandatory reviewer validation in pilot.

## Engine Warnings / Assumptions
- Form 8962 is simplified; Net PTC is set to $0 as a placeholder.
- Foreign tax paid ($7.00) detected but Form 1116 credit computed as $0; verify foreign-source income inputs and limitation math.
- Form 2210 underpayment penalty is not implemented; validate separately if required.
- Form 6251 AMT computation is not implemented; validate separately if required.
- WA-qualified charitable donation input is $0 while federal noncash donations exist. This is intentional for non-WA-qualified donees; confirm if any donation qualifies under WA rules.

## Audit Trail (tail)
- MAGI $47,222 <= threshold $250,000, no NIIT
- Additional Medicare tax:
  Total wages: $39,835.00
  SE income: $3,694.00
  Threshold: $250,000.00
  Excess: $0.00
  Tax due (0.9%): $0.00
  Estimated withheld: $0.00
- Full credit: 2 × $2,200 = $4,400
- Foreign tax credit (Form 1116) summary:
  Foreign tax paid (total): $7.00
  Foreign-source income (input): $90.00
  Foreign-source qualified dividends (input): $70.00
  Adjustment exception: YES
  Adjustment factor used: 0
  Foreign income adjusted (line 1a): $90.00
  Foreign taxable income (line 15 est.): $23.16
  Worldwide taxable income (line 18 adj.): $12,222.41
  US tax for credit (line 20): $892.24
  Limitation ratio (line 19): 0.001895
  Limitation (line 21): $1.69
  Allowed FTC (Schedule 3 line 1): $0.00
- Excess Social Security withholding:
  SS wage base: $176,100.00
  Max SS tax (6.2%): $10,918.20
  Withheld: $2,469.77
  Excess credit: $0.00
- Payments summary:
  Federal withholding: $3,984.00
  Excess SS credit: $0.00
  Estimated tax payments: $3,000.00
  Total payments: $6,984.00
- WARNING: Form 8962 is simplified; Net PTC is set to $0 as a placeholder.
- WARNING: Foreign tax paid ($7.00) detected but Form 1116 credit computed as $0; verify foreign-source income inputs and limitation math.
- WARNING: Form 2210 underpayment penalty is not implemented; validate separately if required.
- WARNING: Form 6251 AMT computation is not implemented; validate separately if required.
- No WA capital gains tax (gains $5,000 - deduction $278,000 <= 0)
- WARNING: WA-qualified charitable donation input is $0 while federal noncash donations exist. This is intentional for non-WA-qualified donees; confirm if any donation qualifies under WA rules.

## Not Submitted Confirmation
- Return not submitted. Not e-filed.
