#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from pdf2image import convert_from_path
import pytesseract


def extract_local(pdf_path: Path) -> str:
    pages = convert_from_path(str(pdf_path), dpi=250)
    chunks = []
    for img in pages:
        chunks.append(pytesseract.image_to_string(img))
    return "\n".join(chunks)


def main() -> None:
    ap = argparse.ArgumentParser(description="Hybrid intake extractor scaffold")
    ap.add_argument("--case", required=True)
    ap.add_argument("--config", default="config/intake_ocr_config.json")
    args = ap.parse_args()

    root = Path(__file__).resolve().parents[1]
    case_dir = root / "data" / "real_cases" / args.case
    src = case_dir / "source_docs"
    out = case_dir / "hybrid_extract"
    out.mkdir(parents=True, exist_ok=True)

    cfg_path = root / args.config
    if not cfg_path.exists():
        example = root / "config" / "intake_ocr_config.example.json"
        raise SystemExit(f"Missing {cfg_path}. Copy {example} to {cfg_path} and fill values.")
    cfg = json.loads(cfg_path.read_text())

    results = []
    for f in sorted(src.iterdir()):
        if f.suffix.lower() not in {".pdf", ".jpg", ".jpeg", ".png"}:
            continue
        text = ""
        method = ""

        # Google Document AI hook (to be fully wired with processor calls)
        if cfg.get("google_document_ai", {}).get("enabled"):
            method = "google_document_ai_stub"
            # TODO: call Document AI processor and capture form fields + confidences.
            text = ""

        if not text and cfg.get("local_ocr", {}).get("enabled", True):
            method = "local_ocr_tesseract"
            if f.suffix.lower() == ".pdf":
                text = extract_local(f)
            else:
                text = pytesseract.image_to_string(str(f))

        (out / f"{f.stem}.txt").write_text(text)
        results.append({"file": f.name, "method": method, "chars": len(text)})

    (out / "extraction_manifest.json").write_text(json.dumps(results, indent=2) + "\n")
    print(json.dumps({"case": args.case, "files": len(results), "out": str(out)}, indent=2))


if __name__ == "__main__":
    main()
