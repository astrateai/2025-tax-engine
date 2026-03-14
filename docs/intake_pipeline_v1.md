# Kevin Intake Pipeline v1

## Goal
Turn client-uploaded PDFs/images into validated JSON inputs Kevin can use for review-ready draft returns.

## v1 Scope
- Input docs: W-2, 1099-INT, 1099-DIV, 1099-B (PDF first)
- Output: normalized JSON stubs + extraction report + confidence/needs-review flags
- No filing/e-file; reviewer-only workflow

## Pipeline Stages
1. **Collect**
   - Pull docs from Drive case folder into `data/real_cases/<case>/source_docs/`
2. **Extract**
   - Run text extraction on each PDF
   - Save raw extracted text under `extracted_text/`
3. **Map (candidate)**
   - Parse candidate fields for supported forms
   - Save candidates to `mapped_candidates.json`
4. **Normalize**
   - Build engine JSON files in `normalized_input/` with unresolved fields marked
5. **Validate**
   - Run schema/contradiction validator and hard-stop checks
6. **Prepare**
   - Only when required fields are complete, run Kevin prep and generate reviewer packet + filled forms

## Hard-Stop Rules
- Missing required fields for supported form classes
- Unsupported form encountered without fallback
- Contradictory values in the same form/document set

## Required Outputs Per Case
- `extracted_text/*.txt`
- `mapped_candidates.json`
- `normalization_notice.md` (what still needs human confirmation)
- `normalized_input/*.json`
- reviewer packet and final packet PDF when complete
