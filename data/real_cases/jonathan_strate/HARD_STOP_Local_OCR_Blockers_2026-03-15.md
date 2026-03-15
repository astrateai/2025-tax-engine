# HARD STOP — Jonathan Strate (Local OCR-only Ingestion)

Date: 2026-03-15 UTC
Mode: local OCR/Tesseract only (cloud extractor disabled)

## Result
Preparation run is blocked. `unresolved_critical_fields.json` contains blocking fields.

## Blocking fields
- taxpayer.ssn
  - Reason: Full SSN not present in local extraction (masked as XXX-XX-9928 / ***-**-9928).
- w2.forms[2].wages
  - Source: 2025 W-2 SV1 Hospitality LLC - Jonathan Mario Strate.pdf
  - Reason: OCR did not reliably capture Box 1.
- w2.forms[2].social_security_wages
  - Source: 2025 W-2 SV1 Hospitality LLC - Jonathan Mario Strate.pdf
  - Reason: OCR did not reliably capture Box 3.
- w2.forms[2].social_security_withheld
  - Source: 2025 W-2 SV1 Hospitality LLC - Jonathan Mario Strate.pdf
  - Reason: OCR did not reliably capture Box 4.
- w2.forms[2].medicare_wages
  - Source: 2025 W-2 SV1 Hospitality LLC - Jonathan Mario Strate.pdf
  - Reason: OCR did not reliably capture Box 5.
- w2.forms[2].medicare_withheld
  - Source: 2025 W-2 SV1 Hospitality LLC - Jonathan Mario Strate.pdf
  - Reason: OCR did not reliably capture Box 6.
- 1099_div.forms[0].ordinary_dividends
  - Source: 2025-Individual-4343-Consolidated-Form-1099.pdf
  - Reason: OCR did not reliably capture Box 1a.
- 1099_div.forms[0].qualified_dividends
  - Source: 2025-Individual-4343-Consolidated-Form-1099.pdf
  - Reason: OCR did not reliably capture Box 1b.

## Artifacts generated
- `data/real_cases/jonathan_strate/hybrid_extract/*` (local OCR text)
- `data/real_cases/jonathan_strate/normalized_input/*.json` (best-effort normalized output + confidence)
- `data/real_cases/jonathan_strate/unresolved_critical_fields.json`

## Safety
No e-file, no submission performed.
