#!/usr/bin/env python3
"""
Render PDF pages with PyMuPDF and apply OCR via Ollama.
Falls back to MiniMax M3 (via Anthropic-compatible API) for pages
whose proxy confidence is below --minimax-threshold (default: 0.70).

CLI:
    python ocr_pages.py --input <pdf_path> --output-dir <dir> --dpi 300
    python ocr_pages.py ... --minimax-threshold 0.70   # enable MiniMax fallback
"""
import sys
import json
import argparse
from pathlib import Path

# Make lib importable from any working directory
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import fitz  # PyMuPDF
from lib.ollama_client import ocr_image_bytes
from lib.minimax_client import ocr_image_bytes as minimax_ocr


def _proxy_confidence(text: str) -> float:
    """Ratio of alphanumeric + space chars to total chars."""
    """
    Proxy confidence based on heuristics.
    Ratio of alphanumeric + space chars to total chars.
    Returns 0.0 for empty text.
    """
    if not text:
        return 0.0
    valid = sum(1 for c in text if c.isalnum() or c == " ")
    return valid / len(text)


def ocr_pdf(
    pdf_path: Path,
    output_dir: Path,
    dpi: int = 300,
    primary_model: str | None = None,
    minimax_threshold: float | None = None,
) -> dict:
    """
    minimax_threshold: if set, pages whose Ollama confidence is below this
    value are re-processed with MiniMax M3. The better result is kept.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(str(pdf_path))
    pages_stats = []
    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)

    for page_num in range(len(doc)):
        out_file = output_dir / f"page_{page_num + 1:04d}.txt"

        # Resume support: skip page if already written with enough content.
        # MIN_VALID_CHARS guards against partial writes from interrupted Ollama calls.
        # Pages genuinely short (blank/cover) rarely appear in parliamentary docs;
        # if they do, they will simply be re-OCR-ed (harmless).
        MIN_VALID_CHARS = 80
        if out_file.exists():
            text = out_file.read_text(encoding="utf-8", errors="ignore")
            if len(text) >= MIN_VALID_CHARS:
                conf = _proxy_confidence(text)
                pages_stats.append({
                    "page": page_num + 1,
                    "chars": len(text),
                    "confidence": round(conf, 4),
                    "model": "cached",
                    "suspicious": conf < 0.5,
                    "error": None,
                })
                continue
            # File exists but too short → delete and reprocess
            out_file.unlink()

        page = doc[page_num]
        pix = page.get_pixmap(matrix=mat)
        img_bytes = pix.tobytes("png")

        result = ocr_image_bytes(img_bytes, primary_model=primary_model)
        text = result["text"]
        model = result["model"]
        error = result["error"]

        conf = _proxy_confidence(text)

        # MiniMax M3 fallback for low-confidence pages
        if minimax_threshold is not None and conf < minimax_threshold and not error:
            mm_result = minimax_ocr(img_bytes)
            if not mm_result["error"]:
                mm_conf = _proxy_confidence(mm_result["text"])
                if mm_conf > conf:
                    text = mm_result["text"]
                    model = mm_result["model"] + "+fallback"
                    conf = mm_conf

        # Only write if OCR produced meaningful content.
        # On error or empty response, skip writing so the page is retried on next run.
        if error or len(text) < 10:
            pages_stats.append({
                "page": page_num + 1,
                "chars": 0,
                "confidence": 0.0,
                "model": model,
                "suspicious": True,
                "error": error or "empty_response",
            })
            continue

        out_file.write_text(text, encoding="utf-8")

        pages_stats.append({
            "page": page_num + 1,
            "chars": len(text),
            "confidence": round(conf, 4),
            "model": model,
            "suspicious": conf < 0.5,
            "error": error,
        })

    doc.close()

    confidences = [p["confidence"] for p in pages_stats]
    mean_conf = sum(confidences) / len(confidences) if confidences else 0.0
    min_conf = min(confidences) if confidences else 0.0

    return {
        "pages": pages_stats,
        "mean_confidence": round(mean_conf, 4),
        "min_confidence": round(min_conf, 4),
        "output_dir": str(output_dir),
    }


def main():
    parser = argparse.ArgumentParser(description="OCR PDF pages via Ollama")
    parser.add_argument("--input", required=True, help="Path to input PDF")
    parser.add_argument("--output-dir", required=True, help="Directory for page .txt files")
    parser.add_argument("--dpi", type=int, default=300, help="Render DPI (default: 300)")
    parser.add_argument("--model", default=None,
                        help="Primary Ollama model to use (overrides default). "
                             "Set via country_config ocr.primary_model.")
    parser.add_argument("--minimax-threshold", type=float, default=None,
                        help="Confidence threshold below which MiniMax M3 is used as fallback. "
                             "Disabled by default. Recommended: 0.70.")
    args = parser.parse_args()

    pdf_path = Path(args.input)
    if not pdf_path.exists():
        print(json.dumps({"status": "error", "error": f"File not found: {pdf_path}"}))
        sys.exit(1)

    output_dir = Path(args.output_dir)
    result = ocr_pdf(pdf_path, output_dir, dpi=args.dpi, primary_model=args.model,
                     minimax_threshold=args.minimax_threshold)
    result["status"] = "ok"
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
