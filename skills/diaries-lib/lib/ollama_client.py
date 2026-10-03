#!/usr/bin/env python3
"""Ollama OCR client with automatic fallback."""
import base64
import json
from pathlib import Path

try:
    import ollama as _ollama
    HAS_OLLAMA = True
except ImportError:
    HAS_OLLAMA = False

PRIMARY_MODEL = "glm-ocr"
FALLBACK_MODEL = "Maternion/LightOnOCR-2:1b"

OCR_PROMPT = (
    "Transcribe el texto de esta imagen exactamente como aparece, "
    "preservando saltos de línea, puntuación y acentos. "
    "No añadas explicaciones ni comentarios. Solo el texto."
)


def ocr_image_bytes(
    image_bytes: bytes,
    prompt: str = OCR_PROMPT,
    primary_model: str | None = None,
) -> dict:
    """
    Run OCR on raw image bytes via Ollama.

    Args:
        image_bytes: Raw PNG/JPEG bytes of the page image.
        prompt: OCR instruction prompt.
        primary_model: Override the default PRIMARY_MODEL for this call.
                       Pass the model name from country_config ocr.primary_model.
                       Falls back to FALLBACK_MODEL if the primary fails.

    Returns {"text": str, "model": str, "error": None|str}.
    """
    if not HAS_OLLAMA:
        return {"text": "", "model": None, "error": "ollama package not installed"}

    img_b64 = base64.b64encode(image_bytes).decode("utf-8")
    last_error = None

    first = primary_model if primary_model else PRIMARY_MODEL
    candidates = [first] if first == FALLBACK_MODEL else [first, FALLBACK_MODEL]

    for model in candidates:
        try:
            response = _ollama.chat(
                model=model,
                messages=[{
                    "role": "user",
                    "content": prompt,
                    "images": [img_b64],
                }],
            )
            text = response["message"]["content"]
            return {"text": text, "model": model, "error": None}
        except Exception as exc:
            last_error = str(exc)
            continue

    return {"text": "", "model": None, "error": f"All models failed: {last_error}"}


def ocr_image_file(path: "Path | str", prompt: str = OCR_PROMPT) -> dict:
    """OCR a single image file. Returns same dict as ocr_image_bytes."""
    return ocr_image_bytes(Path(path).read_bytes(), prompt=prompt)
