"""
Simple image safety classifier for Gschools image filtering.

This module is intentionally lightweight and self-contained so it can run
on typical school servers without a GPU. It is NOT a full NSFW model,
but it provides a reasonable starting point that can be swapped out for
a more advanced model later (e.g. ONNX / TensorRT / cloud vision API).

Interface:
    classify_image(image_bytes: bytes, *, src: str = "", page_url: str = "") -> dict

Returns a dict:
    {
        "explicit_nudity": float 0–1,
        "partial_nudity": float 0–1,
        "suggestive": float 0–1,
        "violence": float 0–1,
        "weapon": float 0–1,
        "self_harm": float 0–1,
        "other": float 0–1,
    }
"""

from __future__ import annotations

import base64
import io
import math
from typing import Dict

try:
    from PIL import Image
except Exception:  # Pillow not installed – classifier will fall back to URL heuristics only
    Image = None


LABELS = [
    "explicit_nudity",
    "partial_nudity",
    "suggestive",
    "violence",
    "weapon",
    "self_harm",
    "other",
]


# Basic keyword hints – this complements the skin-tone heuristic and also
# allows detection when we cannot read the actual pixels (e.g. CORS/tainted canvas).
NSFW_KEYWORDS = [
    "porn", "xxx", "sex", "nude", "nudes", "nsfw", "onlyfans", "camgirl",
    "xvideos", "xnxx", "redtube", "youporn", "pornhub", "hentai",
]

VIOLENCE_KEYWORDS = [
    "gore", "blood", "beheading", "murder", "killshot", "execution",
]

WEAPON_KEYWORDS = [
    "gun", "pistol", "rifle", "shotgun", "ak47", "ar15", "knife", "machete",
    "grenade", "rocket launcher", "rpg", "sniper",
]

SELF_HARM_KEYWORDS = [
    "selfharm", "self-harm", "suicide", "killmyself", "kms", "cutting",
]


def _from_data_url(data_url: str) -> bytes | None:
    if not data_url:
        return None
    if "," not in data_url:
        # assume just base64
        try:
            return base64.b64decode(data_url)
        except Exception:
            return None
    try:
        header, b64 = data_url.split(",", 1)
        return base64.b64decode(b64)
    except Exception:
        return None


def _skin_ratio(img: "Image.Image") -> float:
    """
    Very rough skin detector, based on RGB rules-of-thumb.

    This is NOT perfect, but it can help flag images with a very high
    proportion of skin-tone pixels as potentially explicit.
    """
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")
    w, h = img.size
    if w == 0 or h == 0:
        return 0.0
    # Downsample for speed
    max_side = 256
    scale = min(1.0, max_side / float(max(w, h)))
    if scale < 1.0:
        img = img.resize((int(w * scale), int(h * scale)))
        w, h = img.size

    pixels = img.load()
    if pixels is None:
        return 0.0

    total = 0
    skin = 0
    for y in range(h):
        for x in range(w):
            r, g, b = pixels[x, y][:3]
            total += 1
            # Very simple RGB skin detection heuristic
            if (
                r > 95
                and g > 40
                and b > 20
                and max(r, g, b) - min(r, g, b) > 15
                and abs(r - g) > 15
                and r > g
                and r > b
            ):
                skin += 1
    if total == 0:
        return 0.0
    return float(skin) / float(total)


def _keyword_boost(text: str) -> Dict[str, float]:
    text = (text or "").lower()
    scores = {k: 0.0 for k in LABELS}

    if any(k in text for k in NSFW_KEYWORDS):
        scores["explicit_nudity"] = 0.9
        scores["partial_nudity"] = max(scores["partial_nudity"], 0.7)
        scores["suggestive"] = max(scores["suggestive"], 0.6)

    if any(k in text for k in VIOLENCE_KEYWORDS):
        scores["violence"] = 0.9

    if any(k in text for k in WEAPON_KEYWORDS):
        scores["weapon"] = 0.9

    if any(k in text for k in SELF_HARM_KEYWORDS):
        scores["self_harm"] = 0.9

    return scores


def classify_image(
    image_bytes_or_data_url: bytes | str | None,
    *,
    src: str = "",
    page_url: str = "",
) -> Dict[str, float]:
    """
    Classify an image into coarse safety categories.

    This implementation is intentionally conservative: it tends to
    over-block when there is a high skin ratio or strong NSFW keywords
    in the URL. For production you can replace the internals with a
    stronger model while keeping the same interface.
    """
    scores = {k: 0.0 for k in LABELS}

    # URL-based hints first
    kw_scores = _keyword_boost((src or "") + " " + (page_url or ""))
    for k, v in kw_scores.items():
        scores[k] = max(scores[k], v)

    # Pixel-based heuristic (if Pillow available and we have bytes)
    img_bytes: bytes | None
    if isinstance(image_bytes_or_data_url, str):
        img_bytes = _from_data_url(image_bytes_or_data_url)
    else:
        img_bytes = image_bytes_or_data_url

    if Image is not None and img_bytes:
        try:
            img = Image.open(io.BytesIO(img_bytes))
            sr = _skin_ratio(img)
            # Tune thresholds: high skin ratio => likely explicit
            if sr > 0.5:
                scores["explicit_nudity"] = max(scores["explicit_nudity"], 0.9)
                scores["partial_nudity"] = max(scores["partial_nudity"], 0.7)
            elif sr > 0.35:
                scores["partial_nudity"] = max(scores["partial_nudity"], 0.7)
                scores["suggestive"] = max(scores["suggestive"], 0.6)
            elif sr > 0.2:
                scores["suggestive"] = max(scores["suggestive"], 0.5)
        except Exception:
            # If anything goes wrong, we just rely on keyword-based hints
            pass

    # Ensure at least one label has some probability (for logging)
    if all(v <= 0.0 for v in scores.values()):
        scores["other"] = 0.01

    # Clamp to [0,1]
    for k in list(scores.keys()):
        v = scores[k]
        if v < 0:
            v = 0.0
        elif v > 1:
            v = 1.0
        scores[k] = float(v)

    return scores
