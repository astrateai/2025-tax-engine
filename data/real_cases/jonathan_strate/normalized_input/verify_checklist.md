# Jonathan Strate — Field Verification Checklist (before Kevin prep run)

Please confirm/fill these REQUIRED fields in `normalized_input/*.json`.

## 1) taxpayer.json
- [ ] name
- [ ] ssn
- [ ] spouse_name / spouse_ssn (if MFJ)
- [ ] address / city / state / zip
- [ ] dependents list (if any)

## 2) w2.json (all 3 W-2s)
For each W-2, confirm:
- [ ] EIN
- [ ] Box 1 wages
- [ ] Box 2 federal withheld
- [ ] Box 3 / Box 4
- [ ] Box 5 / Box 6
- [ ] State / Box 16 / Box 17

## 3) 1099_int.json
- [ ] payer names
- [ ] box 1 interest amounts
- [ ] box 4 withholding (if any)

## 4) 1099_div.json
- [ ] ordinary dividends (1a)
- [ ] qualified dividends (1b)
- [ ] cap gain distributions (2a) if present

## 5) 1099_b.json
- [ ] transaction list entered (or confirm no reportable sales)
- [ ] proceeds, basis, dates for each transaction

## 6) Prior / adjustments
- [ ] prior-year carryovers (if any)
- [ ] estimated payments (if any)

After checklist is complete, I will run Kevin end-to-end and post:
- reviewer packet
- filled federal packet PDF
- Drive upload link
