from __future__ import annotations

import pandas as pd

from .experience_rules import normalize_experience_label
from .name_utils import normalize_column_label


BASE_ALIASES = {
    "note": ["N° da nota", "Nº da nota", "N da nota"],
    "sgo": ["Nota SGO"],
    "status": ["Status do projeto", "Status do projeto "],
    "project_type": ["PI (Tipo Projeto)", "PI Tipo Projeto", "Tipo Projeto"],
    "regional": ["Regional"],
    "municipality": ["Município", "Municipio"],
    "deadline": ["Prazo"],
    # Coluna R. Na interface o nome exibido é "Postes Alterados/Novos".
    "posts": ["P L N", "P L N ", "PLN", "Postes Alterados/Novos", "Postes Alterados / Novos"],
    "assignee": ["Projetistas", "Projetista"],
    "completed_at": ["Data de entrega do projeto"],
    "actual_posts": ["Qtd. de poste", "Qtd de poste"],
    "priority": ["Prioridade"],
    "reanalyzed_at": ["Data da reanálise", "Data da reanalise"],
}

DESIGNER_ALIASES = {
    "name": ["Nome", "Projetista", "Colaborador"],
    "email": ["E-mail", "Email", "E mail"],
    "sharepoint_lookup_id": ["SharePointLookupId", "LookupId", "SharePoint ID"],
    "experience": [
        "Experiência", "Experiencia", "Nível", "Nivel", "Nível de experiência",
        "Nivel de experiencia", "Perfil", "Senioridade",
    ],
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
    """Load an exported Microsoft Lists workbook into the app's canonical schema.

    Column R is the planned workload used for portfolio/distribution and is shown
    to users as "Postes Alterados/Novos". Column F (PI - Tipo Projeto) can be used
    to classify project difficulty for experience-aware distribution.
    """
    raw = _read_excel(source)
    optional = {
        "actual_posts", "priority", "deadline", "completed_at", "reanalyzed_at", "project_type",
    }
    cols = {
        key: _find_column(raw, aliases, required=key not in optional)
        for key, aliases in BASE_ALIASES.items()
    }

    out = pd.DataFrame(index=raw.index)
    out["item_id"] = [f"excel-{i + 2}" for i in range(len(raw))]
    out["source_row"] = raw.index + 2
    ordered = [
        "note", "sgo", "status", "project_type", "regional", "municipality", "deadline", "posts",
        "assignee", "completed_at", "actual_posts", "priority", "reanalyzed_at",
    ]
    for key in ordered:
        col = cols.get(key)
        out[key] = raw[col] if col else None

    posts_numeric = pd.to_numeric(out["posts"], errors="coerce")
    out["posts_valid"] = posts_numeric.notna() & (posts_numeric > 0)
    out["posts"] = posts_numeric.fillna(0).astype(int)

    out["assignee"] = out["assignee"].fillna("").astype(str).str.strip()
    out["status"] = out["status"].fillna("").astype(str).str.strip()
    out["project_type"] = out["project_type"].fillna("").astype(str).str.strip()
    out["note"] = out["note"].where(out["note"].notna(), None)
    out["sgo"] = out["sgo"].where(out["sgo"].notna(), None)
    out["assigned_at"] = None
    out["complexity"] = None
    out["modified_at"] = None
    out["etag"] = None
    out["assignee_lookup_id"] = None
    return out



def load_vu_excel(source) -> pd.DataFrame:
    """Load BASE LIST VU using only columns A (project number) and C (status).

    The VU source intentionally has no workload/post count or assignee fields.
    Each valid row therefore contributes one project to the distribution pool,
    while post coverage remains unknown until a richer source provides it.
    """
    raw = _read_excel(source)
    if raw.shape[1] < 3:
        raise ValueError("A BASE LIST VU precisa possuir pelo menos as colunas A e C.")

    project_col = raw.columns[0]  # A
    status_col = raw.columns[2]   # C

    out = pd.DataFrame(index=raw.index)
    out["item_id"] = [f"excel-vu-{i + 2}" for i in range(len(raw))]
    out["source_row"] = raw.index + 2
    out["note"] = None
    def _project_number(value):
        if pd.isna(value):
            return None
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        if isinstance(value, int):
            return str(value)
        text = str(value).strip()
        return text or None
    out["sgo"] = raw[project_col].map(_project_number)
    out["status"] = raw[status_col].fillna("").astype(str).str.strip()
    out["project_type"] = ""
    out["regional"] = ""
    out["municipality"] = ""
    out["deadline"] = None
    out["posts"] = 0
    out["posts_valid"] = False
    out["assignee"] = ""
    out["completed_at"] = None
    out["actual_posts"] = None
    out["priority"] = "Normal"
    out["reanalyzed_at"] = None
    out["assigned_at"] = None
    out["complexity"] = None
    out["modified_at"] = None
    out["etag"] = None
    out["assignee_lookup_id"] = None
    out["workload_known"] = False
    return out

def load_designers_excel(source) -> pd.DataFrame:
    raw = _read_excel(source)
    name_col = _find_column(raw, DESIGNER_ALIASES["name"])
    email_col = _find_column(raw, DESIGNER_ALIASES["email"], required=False)
    lookup_col = _find_column(raw, DESIGNER_ALIASES["sharepoint_lookup_id"], required=False)
    experience_col = _find_column(raw, DESIGNER_ALIASES["experience"], required=False)

    out = pd.DataFrame()
    out["name"] = raw[name_col].fillna("").astype(str).str.strip()
    out = out[out["name"] != ""].copy()
    out["email"] = raw.loc[out.index, email_col].fillna("").astype(str).str.strip() if email_col else ""
    out["sharepoint_lookup_id"] = raw.loc[out.index, lookup_col] if lookup_col else None
    if experience_col:
        out["experience"] = raw.loc[out.index, experience_col].map(normalize_experience_label)
    else:
        out["experience"] = "Intermediário"
    out = out.drop_duplicates(subset=["name"], keep="first").reset_index(drop=True)
    return out
