from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from src.distribution_engine import suggest_assignments
from src.metrics import build_daily_snapshots
from src.models import StatusConfig, Targets


def test_active_project_above_daily_target_marks_designer_as_locked():
    projects = pd.DataFrame([
        {
            "item_id": "1", "note": "N1", "sgo": "S1", "posts": 32, "posts_valid": True,
            "assignee": "A", "status": "Em projeto",
        }
    ])
    now = datetime(2026, 10, 2, 10, 0, tzinfo=ZoneInfo("America/Fortaleza"))
    snap = build_daily_snapshots(projects, ["A"], now, Targets(), StatusConfig())
    row = snap.iloc[0]
    assert bool(row["Bloqueio projeto acima da meta"]) is True
    assert int(row["Projetos acima da meta na carteira"]) == 1
    assert int(row["Maior projeto em carteira"]) == 32
    assert row["Situação"] == "Bloqueado - projeto acima da meta diária"


def test_locked_designer_does_not_receive_more_projects():
    projects = pd.DataFrame([
        {"item_id": "new", "note": "N2", "sgo": "S2", "posts": 5, "posts_valid": True, "assignee": "", "status": "Em projeto"},
    ])
    snapshots = pd.DataFrame([{
        "Projetista": "A",
        "Postes realizados": 0,
        "Projetos realizados": 0,
        "Postes em carteira": 32,
        "Projetos em carteira": 1,
        "Carteira sem PLN": 0,
        "Potencial postes": 32,
        "Potencial projetos": 1,
        "Bloqueio projeto acima da meta": True,
        "Tempo útil restante (min)": 300,
    }])
    suggestions, summary = suggest_assignments(
        projects, snapshots, Targets(), StatusConfig(), max_portfolio_posts=60, max_portfolio_projects=6
    )
    assert suggestions.empty
    assert "Bloqueado" in summary.iloc[0]["Motivo"]


def test_oversized_project_is_not_given_to_designer_with_active_portfolio():
    projects = pd.DataFrame([
        {"item_id": "big", "note": "N3", "sgo": "S3", "posts": 31, "posts_valid": True, "assignee": "", "status": "Em projeto", "priority": "Urgente"},
    ])
    snapshots = pd.DataFrame([{
        "Projetista": "A",
        "Postes realizados": 0,
        "Projetos realizados": 0,
        "Postes em carteira": 5,
        "Projetos em carteira": 1,
        "Carteira sem PLN": 0,
        "Potencial postes": 5,
        "Potencial projetos": 1,
        "Bloqueio projeto acima da meta": False,
        "Tempo útil restante (min)": 300,
    }])
    suggestions, _ = suggest_assignments(
        projects, snapshots, Targets(), StatusConfig(), max_portfolio_posts=60, max_portfolio_projects=6
    )
    assert suggestions.empty


def test_receiving_oversized_project_blocks_additional_assignment_same_cycle():
    projects = pd.DataFrame([
        {"item_id": "big", "note": "N4", "sgo": "S4", "posts": 31, "posts_valid": True, "assignee": "", "status": "Em projeto", "priority": "Urgente"},
        {"item_id": "small", "note": "N5", "sgo": "S5", "posts": 2, "posts_valid": True, "assignee": "", "status": "Em projeto", "priority": "Baixa"},
    ])
    snapshots = pd.DataFrame([{
        "Projetista": "A",
        "Postes realizados": 0,
        "Projetos realizados": 0,
        "Postes em carteira": 0,
        "Projetos em carteira": 0,
        "Carteira sem PLN": 0,
        "Potencial postes": 0,
        "Potencial projetos": 0,
        "Bloqueio projeto acima da meta": False,
        "Tempo útil restante (min)": 300,
    }])
    suggestions, summary = suggest_assignments(
        projects, snapshots, Targets(), StatusConfig(), max_portfolio_posts=60, max_portfolio_projects=6
    )
    assert suggestions["item_id"].tolist() == ["big"]
    assert bool(summary.iloc[0]["Bloqueado por projeto acima da meta"]) is True
    assert "acima da meta diária" in suggestions.iloc[0]["Motivo"]
