#!/usr/bin/env python3
"""
MiniMax M3 OCR client via Anthropic-compatible Token Plan API.
Endpoint: https://api.minimax.io/anthropic
Auth:     MINIMAX_API_KEY (Token Plan subscription key)

Thinking blocks are automatically separated from text blocks
using the standard Anthropic SDK content block types.
"""
import base64
import os
from pathlib import Path

try:
    import anthropic as _anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

MODEL = "MiniMax-M3"
BASE_URL = "https://api.minimax.io/anthropic"

OCR_PROMPT = (
    "Transcribe el texto de esta imagen exactamente como aparece, "
    "preservando saltos de línea, puntuación y acentos. "
    "No añadas explicaciones ni comentarios. Solo el texto."
)


def _get_client() -> "_anthropic.Anthropic":
    key = os.environ.get("MINIMAX_API_KEY") or _load_env_key()
    if not key:
        raise RuntimeError("MINIMAX_API_KEY no encontrada en entorno ni en .env")
    return _anthropic.Anthropic(api_key=key, base_url=BASE_URL)


def _load_env_key() -> str | None:
    env_path = Path(__file__).parent.parent / ".env"
    if not env_path.exists():
        return None
    for line in env_path.read_text().splitlines():
        if line.startswith("MINIMAX_API_KEY"):
            return line.split("=", 1)[1].strip()
    return None


def ocr_image_bytes(
    image_bytes: bytes,
    prompt: str = OCR_PROMPT,
    budget_tokens: int = 512,
) -> dict:
    """
    OCR via MiniMax M3 (Anthropic-compatible endpoint).

    Args:
        image_bytes: Raw PNG/JPEG bytes.
        prompt:      OCR instruction.
        budget_tokens: Max thinking tokens (keep low for OCR — thinking rarely helps).

    Returns {"text": str, "thinking": str, "model": str, "error": None|str,
             "input_tokens": int, "output_tokens": int, "thinking_tokens": int}.
    """
    if not HAS_ANTHROPIC:
        return {"text": "", "thinking": "", "model": None,
                "error": "anthropic package not installed",
                "input_tokens": 0, "output_tokens": 0, "thinking_tokens": 0}

    img_b64 = base64.b64encode(image_bytes).decode()

    try:
        client = _get_client()
        response = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            thinking={"type": "enabled", "budget_tokens": budget_tokens},
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": img_b64,
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }],
        )

        text = ""
        thinking = ""
        for block in response.content:
            if block.type == "thinking":
                thinking = block.thinking
            elif block.type == "text":
                text = block.text

        usage = response.usage
        return {
            "text": text,
            "thinking": thinking,
            "model": MODEL,
            "error": None,
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "thinking_tokens": getattr(usage, "thinking_tokens", 0),
        }

    except Exception as exc:
        return {"text": "", "thinking": "", "model": MODEL,
                "error": str(exc),
                "input_tokens": 0, "output_tokens": 0, "thinking_tokens": 0}


def ocr_image_file(path: "Path | str", prompt: str = OCR_PROMPT) -> dict:
    """OCR a single image file. Returns same dict as ocr_image_bytes."""
    return ocr_image_bytes(Path(path).read_bytes(), prompt=prompt)
