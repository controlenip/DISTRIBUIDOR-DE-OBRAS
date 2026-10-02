from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from src.metrics import build_daily_snapshots, monthly_metrics, data_quality_summary
from src.models import StatusConfig, Targets


def _base_rows(today="2026-10-02"):
    return pd.DataFrame([
        {
            "item_id": "1", "note": "N1", "sgo": "S1", "posts": 8, "actual_posts": 8,
            "assignee": "A", "status": "Concluído", "completed_at": today,
        },
        {
            "item_id": "2", "note": "N2", "sgo": "S2", "posts": 7, "actual_posts": 7,
            "assignee": "A", "status": "Em projeto", "completed_at": today,
        },
        {
            "item_id": "3", "note": "N3", "sgo": "S3", "posts": 6, "actual_posts": 6,
            "assignee": "A", "status": "Concluído", "completed_at": None,
        },
    ])


def test_daily_productivity_requires_completed_status_and_delivery_date():
    projects = _base_rows()
    now = datetime(2026, 10, 2, 15, 0, tzinfo=ZoneInfo("America/Fortaleza"))
    snap = build_daily_snapshots(projects, ["A"], now, Targets(), StatusConfig())
    row = snap.iloc[0]
    assert int(row["Postes realizados"]) == 8
    assert int(row["Projetos realizados"]) == 1
    # The Em projeto row remains portfolio only, even though it has a date populated.
    assert int(row["Postes em carteira"]) == 7
    assert int(row["Projetos em carteira"]) == 1


def test_monthly_productivity_uses_same_completed_plus_date_rule():
    projects = _base_rows()
    now = datetime(2026, 10, 2, 15, 0, tzinfo=ZoneInfo("America/Fortaleza"))
    out = monthly_metrics(projects, ["A"], now, Targets(), StatusConfig())
    row = out.iloc[0]
    assert int(row["Postes"]) == 8
    assert int(row["Projetos"]) == 1


def test_completed_without_delivery_date_is_flagged_for_quality():
    quality = data_quality_summary(_base_rows(), StatusConfig())
    assert quality["concluidos_sem_data_entrega"] == 1
    assert quality["concluidos_com_data_entrega"] == 1
