from __future__ import annotations

import re
import unicodedata


def normalize_text(value: object) -> str:
    """Normalize text for operational comparisons without changing displayed values."""
    text = str(value or "").strip().casefold()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text)


def normalize_person_name(value: object) -> str:
    return normalize_text(value)


def normalize_column_label(value: object) -> str:
    text = normalize_text(value)
    text = text.replace("º", "o").replace("°", "o")
    return re.sub(r"[^a-z0-9]+", "", text)
