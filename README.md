# Taxinator

Taxinator is a sanitized snapshot of a one-off Python tax engine that OpenAI Codex generated while helping Kyle Corbitt prepare his 2025 taxes.

Context: it comes from the experiment described in the accompanying blog post, ["Codex, File My Taxes. Make No Mistakes."](https://corbt.com/posts/codex-file-my-taxes-make-no-mistakes)

## Read This First

This repository is not tax software.

Do not rely on it to prepare, review, or file a real tax return unless you are independently validating every number, every worksheet, every source document, and every filing requirement yourself.

No warranty is made about:

- correctness
- completeness
- fitness for a particular purpose
- legal compliance
- suitability for any taxpayer, jurisdiction, or tax year

This code was originally built for one unusually specific 2025 return, then cleaned up for publication. It still carries the shape of that one-off origin. Treat it as an artifact, reference implementation, or conversation starter, not as a product.

## What Was Removed

The original private snapshot included real taxpayer data, real generated outputs, and a filled filing packet. Those have been removed here.

This public copy includes:

- the calculation engine
- the PDF-filling code
- blank IRS forms used by the generator
- synthetic example inputs with fake names, fake IDs, and fake numbers

This public copy does not include:

- any real taxpayer identity data
- any real addresses, SSNs, EINs, or account numbers
- any real source documents
- any real generated returns
- any accountant handoff materials

## Repo Layout

```text
taxinator/
├── data/input/          # Synthetic example fixtures only
├── data/output/         # Generated calculation output (gitignored)
├── forms/blank/         # Blank IRS PDFs used by the filler
├── forms/filled/        # Generated filled PDFs and reports (gitignored)
├── src/                 # Engine, models, ingest, PDF filler
└── tests/               # Lightweight smoke tests
```

## Running It

```bash
uv sync
uv run python -m src.engine
uv run python -m src.pdf_filler
uv run pytest
```

`src.engine` reads JSON fixtures from `data/input/` and writes calculation output to `data/output/`.

`src.pdf_filler` takes the engine result and writes filled forms to `forms/filled/2025/`.

## Flows Believed To Be Implemented Correctly

Believed to work here means: implemented in code, exercised on the original one-off return and/or the sanitized example data, and not currently known to be systematically wrong for the narrow cases listed.

- JSON ingest into typed Pydantic models for W-2, 1099-INT, 1099-DIV, 1099-NEC, 1099-MISC, 1099-B, 1095-A, 1098, donations, prior-year carryforwards, and K-1s
- Schedule C gross-receipts-only flow from 1099-NEC when expenses are modeled as zero
- Schedule B aggregation for taxable interest, ordinary dividends, qualified dividends, and passive-category foreign-tax inputs
- Schedule D / Form 8949 aggregation for basic short-term and long-term capital gain and loss transactions
- Capital-gains stacking against ordinary income for the 2025 MFJ federal brackets
- Basic passive-loss suspension flow for current-year K-1 income/losses with no disposition logic
- Schedule A comparison between itemized deductions and the 2025 standard deduction
- SALT cap calculation for the simplified 2025 MFJ path used in this codebase
- Mortgage-interest cap for a single 1098 loan
- Charitable contribution limits for cash and appreciated property, plus carryover tracking
- Self-employment tax for straightforward Schedule C income
- Net Investment Income Tax calculation
- Additional Medicare Tax calculation for the simplified aggregated-wage path used here
- Child Tax Credit phase-out in obvious in-range and fully-phased-out cases
- Simplified passive-category Form 1116 limitation flow when foreign capital-gain distributions are zero and no carryovers or extra baskets are involved
- Washington capital-gains tax calculation for the 2025 rates encoded in the repo
- Filling supported IRS PDF AcroForm/XFA fields from computed outputs

## Flows Known To Be Wrong, Incomplete, Or Too Narrow

- Filing status support is effectively MFJ-only. Other statuses exist in enums/constants but are not implemented end to end.
- Prior-year suspended passive losses are loaded but not applied to current-year passive-loss limitation math.
- Payroll-tax logic uses aggregated MFJ wage totals, so excess Social Security and some wage-limit logic are wrong once both spouses have wages.
- K-1 guaranteed-payment fields can be double-counted if both `box_4a`/`box_4b` and `box_4c` are populated.
- Mortgage-interest limitation uses the first 1098 principal with summed 1098 interest, so multiple-loan cases are wrong.
- Form 1116 worldwide-taxable-income adjustment can be wrong when capital-gain distributions are non-zero.
- Form 1116 is deliberately simplified: no carryback/carryforward, no multiple baskets, no AMT FTC, no detailed expense apportionment.
- Form 8962 is a placeholder only. It does not implement the real PTC household-income/FPL reconciliation.
- Form 2210 is not implemented.
- Form 6251 / AMT is not implemented.
- Form 4797 / Section 1231 netting is not implemented.
- Washington handling is limited to the capital-gains path in this repo; this is not a general state-tax engine.
- There is no e-file support.
- There is no document OCR, extraction pipeline, or brokerage/account login automation in this repo.
- There is no safety layer that prevents filing with incomplete or contradictory inputs.

## Example Inputs

The fixtures in `data/input/` are synthetic and intentionally fake. They exist only so the engine can run in public without shipping a real person's return.

They demonstrate the shape of:

- multiple W-2s
- self-employment income
- investment income
- capital gains
- passive and non-passive K-1s
- mortgage interest
- charitable donations
- ACA coverage input

## Design Notes

This repo intentionally keeps the original "one engine file plus helpers" shape instead of pretending to be a polished tax platform. That is deliberate: the interesting thing here is that an agent could get surprisingly far on a bounded, document-heavy, rules-heavy problem with mostly plain Python.

That is also why the disclaimers above are so aggressive. "Interesting artifact" and "safe production-grade filing engine" are very different categories.
