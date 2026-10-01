from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import BinaryIO

import pandas as pd

from .name_utils import normalize_column_label


BASE_ALIASES = {
    "note": ["N° da nota", "Nº da nota", "N da nota"],
    "sgo": ["Nota SGO"],
    "status": ["Status do projeto", "Status do projeto "],
    "regional": ["Regional"],
    "municipality": ["Município", "Municipio"],
    "deadline": ["Prazo"],
    "posts": ["P L N", "P L N ", "PLN"],
    "assignee": ["Projetistas", "Projetista"],
    "completed_at": ["Data de entrega do projeto"],
    "actual_posts": ["Qtd. de poste", "Qtd de poste"],
    "priority": ["Prioridade"],
}

DESIGNER_ALIASES = {
    "name": ["Nome", "Projetista", "Colaborador"],
    "email": ["E-mail", "Email", "E mail"],
    "sharepoint_lookup_id": ["SharePointLookupId", "LookupId", "SharePoint ID"],
}


def _read_excel(source, sheet_name=0) -> pd.DataFrame:
    return pd.read_excel(source, sheet_name=sheet_name, engine="openpyxl")


def _column_lookup(df: pd.DataFrame) -> dict[str, str]:
    return {normalize_column_label(c): c for c in df.columns}


def _find_column(df: pd.DataFrame, aliases: list[str], required: bool = True) -> str | None:
    lookup = _column_lookup(df)
    for alias in aliases:
        key = normalize_column_label(alias)
        if key in lookup:
            return lookup[key]
    if required:
        raise ValueError(f"Coluna obrigatória não encontrada. Esperado um de: {aliases}")
    return None


def load_base_excel(source) -> pd.DataFrame:
    """Load an exported Microsoft Lists workbook into the app's canonical schema."""
    raw = _read_excel(source)
    cols = {
        key: _find_column(raw, aliases, required=key not in {"actual_posts", "priority", "deadline", "completed_at"})
        for key, aliases in BASE_ALIASES.items()
    }

    out = pd.DataFrame(index=raw.index)
    out["item_id"] = [f"excel-{i + 2}" for i in range(len(raw))]
    out["source_row"] = raw.index + 2
    for key in ["note", "sgo", "status", "regional", "municipality", "deadline", "posts", "assignee", "completed_at", "actual_posts", "priority"]:
        col = cols.get(key)
        out[key] = raw[col] if col else None

    posts_numeric = pd.to_numeric(out["posts"], errors="coerce")
    out["posts_valid"] = posts_numeric.notna() & (posts_numeric > 0)
    out["posts"] = posts_numeric.fillna(0).astype(int)
    out["assignee"] = out["assignee"].fillna("").astype(str).str.strip()
    out["status"] = out["status"].fillna("").astype(str).str.strip()
    out["note"] = out["note"].where(out["note"].notna(), None)
    out["sgo"] = out["sgo"].where(out["sgo"].notna(), None)
    out["assigned_at"] = None
    out["complexity"] = None
    out["modified_at"] = None
    out["etag"] = None
    out["assignee_lookup_id"] = None
    return out


def load_designers_excel(source) -> pd.DataFrame:
    raw = _read_excel(source)
    name_col = _find_column(raw, DESIGNER_ALIASES["name"])
    email_col = _find_column(raw, DESIGNER_ALIASES["email"], required=False)
    lookup_col = _find_column(raw, DESIGNER_ALIASES["sharepoint_lookup_id"], required=False)

    out = pd.DataFrame()
    out["name"] = raw[name_col].fillna("").astype(str).str.strip()
    out = out[out["name"] != ""].copy()
    out["email"] = raw.loc[out.index, email_col].fillna("").astype(str).str.strip() if email_col else ""
    out["sharepoint_lookup_id"] = raw.loc[out.index, lookup_col] if lookup_col else None
    out = out.drop_duplicates(subset=["name"], keep="first").reset_index(drop=True)
    return out
