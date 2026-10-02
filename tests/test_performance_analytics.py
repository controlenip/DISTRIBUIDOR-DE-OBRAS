from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from src.metrics import build_daily_snapshots, prepare_projects
from src.models import StatusConfig, Targets
from src.performance_analytics import designer_attention_table, management_insights


def _row(**overrides):
    row = {
        "item_id": "1",
        "note": "430000001",
        "sgo": "440000001",
        "status": "Em projeto",
        "regional": "Norte",
        "municipality": "São Luís",
        "deadline": None,
        "posts": 9,
        "posts_valid": True,
        "assignee": "PROJETISTA A",
        "completed_at": None,
        "actual_posts": None,
        "priority": None,
        "assigned_at": None,
        "complexity": None,
        "modified_at": None,
        "etag": None,
        "assignee_lookup_id": None,
    }
    row.update(overrides)
    return row


def test_project_designer_production_uses_delivery_date_even_after_status_advanced():
    projects = pd.DataFrame([
        _row(
            status="Análise de Qualidade",
            completed_at="2026-10-01 14:00:00",
            actual_posts=10,
            posts=9,
        )
    ])
    now = datetime(2026, 10, 1, 15, 0, tzinfo=ZoneInfo("America/Fortaleza"))
    result = build_daily_snapshots(
        projects,
        ["PROJETISTA A"],
        now,
        Targets(),
        StatusConfig(),
    )
    assert int(result.iloc[0]["Projetos realizados"]) == 1
    assert int(result.iloc[0]["Postes realizados"]) == 10


def test_prepare_projects_uses_actual_posts_with_pln_fallback():
    projects = pd.DataFrame([
        _row(item_id="1", actual_posts=12, posts=9),
        _row(item_id="2", actual_posts=None, posts=7),
    ])
    prepared = prepare_projects(projects, "America/Fortaleza")
    assert int(prepared.loc[prepared["item_id"] == "1", "production_posts"].iloc[0]) == 12
    assert int(prepared.loc[prepared["item_id"] == "2", "production_posts"].iloc[0]) == 7


def test_daily_attention_lists_designer_below_target():
    snapshot = pd.DataFrame([{
        "Projetista": "PROJETISTA A",
        "Postes realizados": 10,
        "Projetos realizados": 2,
        "Meta postes agora": 20,
        "Meta projetos agora": 3.5,
        "Previsão postes 18h": 20,
        "Previsão projetos 18h": 4,
        "Sem cobertura postes": 8,
        "Sem cobertura projetos": 1,
        "Situação": "Falta de carga",
    }])
    attention = designer_attention_table(snapshot, 30, 5)
    assert len(attention) == 1
    assert attention.iloc[0]["Projetista"] == "PROJETISTA A"


def test_management_insights_are_designer_focused():
    snapshot = pd.DataFrame([{
        "Projetista": "A", "Situação": "Falta de carga"
    }])
    baseline = pd.DataFrame([{
        "Projetista": "A", "Meta restante postes": 30, "Meta restante projetos": 5,
        "Projetos já atribuídos": 0, "PLN já atribuído": 0,
    }])
    prediction = pd.DataFrame([{"Projetista": "A", "Tendência": "Requer acompanhamento"}])
    insights = management_insights(snapshot, baseline, prediction, 4, 20)
    joined = " ".join(insights).lower()
    assert "projetista" in joined
    assert "levantador" not in joined
