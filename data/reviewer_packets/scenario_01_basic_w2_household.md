# Reviewer Packet — scenario_01_basic_w2_household

## Return Type and Tax Year
- Type: 1040-family pilot return
- Tax year: 2025

## Taxpayer Summary
- Taxpayer: Example Taxpayer
- Filing status: married_filing_jointly
- State (taxpayer): TX
- W-2 count: 2
- 1099 counts: 1099-INT=2, 1099-DIV=1, 1099-NEC=0, 1099-MISC=0, 1099-B=0

## Key Form 1040 Totals
- Taxable income (L15): $3,255.00
- Total tax (L24): $-1,895.00
- Total payments (L33): $3,984.00
- Refund (L35a): $0.00
- Amount owed (L37): $-5,879.00

## Reviewer Attention Flags
- Taxpayer state 'TX' differs from W-2 state set ['WA'].
- TX state handling requires mandatory reviewer validation in pilot.

## Engine Warnings / Assumptions
- Foreign tax paid ($7.00) detected but Form 1116 credit computed as $0; verify foreign-source income inputs and limitation math.
- Form 2210 underpayment penalty is not implemented; validate separately if required.
- Form 6251 AMT computation is not implemented; validate separately if required.
- WA-qualified charitable donation input is $0 while federal noncash donations exist. This is intentional for non-WA-qualified donees; confirm if any donation qualifies under WA rules.

## Audit Trail (tail)
- NIIT net investment income inputs:
  Interest: $120.00
  Dividends: $300.00
  Net capital gain (LT+ST, floor 0): $0.00
  1099-MISC other income: $0.00
  Passive income included for NIIT: $0.00
  Net investment income total: $420.00
- MAGI $38,255 <= threshold $250,000, no NIIT
- Additional Medicare tax:
  Total wages: $39,835.00
  SE income: $0.00
  Threshold: $250,000.00
  Excess: $0.00
  Tax due (0.9%): $0.00
  Estimated withheld: $0.00
- Full credit: 1 × $2,200 = $2,200
- Foreign tax credit (Form 1116) summary:
  Foreign tax paid (total): $7.00
  Foreign-source income (input): $90.00
  Foreign-source qualified dividends (input): $70.00
  Adjustment exception: YES
  Adjustment factor used: 0
  Foreign income adjusted (line 1a): $90.00
  Foreign taxable income (line 15 est.): $7.66
  Worldwide taxable income (line 18 adj.): $3,255.00
  US tax for credit (line 20): $305.50
  Limitation ratio (line 19): 0.002353
  Limitation (line 21): $0.72
  Allowed FTC (Schedule 3 line 1): $0.00
- Excess Social Security withholding:
  SS wage base: $176,100.00
  Max SS tax (6.2%): $10,918.20
  Withheld: $2,469.77
  Excess credit: $0.00
- Payments summary:
  Federal withholding: $3,984.00
  Excess SS credit: $0.00
  Estimated tax payments: $0.00
  Total payments: $3,984.00
- WARNING: Foreign tax paid ($7.00) detected but Form 1116 credit computed as $0; verify foreign-source income inputs and limitation math.
- WARNING: Form 2210 underpayment penalty is not implemented; validate separately if required.
- WARNING: Form 6251 AMT computation is not implemented; validate separately if required.
- No WA capital gains tax (gains $-1,500 - deduction $278,000 <= 0)
- WARNING: WA-qualified charitable donation input is $0 while federal noncash donations exist. This is intentional for non-WA-qualified donees; confirm if any donation qualifies under WA rules.

## Not Submitted Confirmation
- Return not submitted. Not e-filed.
