from __future__ import annotations

import pandas as pd


def _project_key(value: object) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    text = str(value).strip()
    if text.endswith(".0") and text[:-2].isdigit():
        return text[:-2]
    return text


def combine_levantamento_vu(levantamento: pd.DataFrame, vu: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Combine the two mandatory project sources into one distribution dataset.

    LEVANTAMENTO remains the rich operational/history source. VU contributes
    additional projects whose status is exactly "Em projeto". When the same
    project number (SGO) is present in both, LEVANTAMENTO wins to avoid sending
    the same work twice.

    Returns (combined_dataframe, vu_overlap_count). If either source is missing,
    returns an empty dataframe because neither source is allowed to operate alone.
    """
    if levantamento is None or vu is None or levantamento.empty or vu.empty:
        return pd.DataFrame(), 0

    lev = levantamento.copy()
    vu_df = vu.copy()

    vu_status = vu_df.get("status", pd.Series("", index=vu_df.index)).fillna("").astype(str).str.strip().str.casefold()
    vu_pool = vu_df[vu_status.eq("em projeto")].copy()

    lev_keys = {
        _project_key(value) for value in lev.get("sgo", pd.Series(dtype=object)).tolist() if _project_key(value)
    }
    vu_key = vu_pool.get("sgo", pd.Series("", index=vu_pool.index)).map(_project_key)
    overlap_mask = vu_key.isin(lev_keys) & (vu_key != "")
    overlap_count = int(overlap_mask.sum())
    vu_unique = vu_pool[~overlap_mask].copy()

    return pd.concat([lev, vu_unique], ignore_index=True), overlap_count
