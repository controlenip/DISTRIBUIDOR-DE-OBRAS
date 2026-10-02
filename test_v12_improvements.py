from datetime import date

import pandas as pd

from src.distribution_engine import suggest_assignments
from src.models import StatusConfig, Targets
from src.performance_analytics import designer_daily_history, portfolio_balance_metrics


def _snap(name="A", potential_posts=0, potential_projects=0):
    return {
        "Projetista": name,
        "Postes realizados": 0,
        "Projetos realizados": 0,
        "Carteira sem PLN": 0,
        "Potencial postes": potential_posts,
        "Potencial projetos": potential_projects,
        "Tempo útil restante (min)": 300,
    }


def test_portfolio_cap_blocks_overload():
    projects = pd.DataFrame([
        {"item_id":"1","note":"1","sgo":"4301","posts":8,"posts_valid":True,"assignee":"","status":"Em projeto","priority":"Normal"},
    ])
    snapshots = pd.DataFrame([_snap("A", potential_posts=30, potential_projects=4)])
    suggestions, _ = suggest_assignments(
        projects, snapshots, Targets(), StatusConfig(),
        max_portfolio_posts=36, max_portfolio_projects=6, respect_time=False,
    )
    assert suggestions.empty


def test_priority_is_respected_when_enabled():
    projects = pd.DataFrame([
        {"item_id":"1","note":"1","sgo":"4301","posts":5,"posts_valid":True,"assignee":"","status":"Em projeto","priority":"Normal"},
        {"item_id":"2","note":"2","sgo":"4302","posts":5,"posts_valid":True,"assignee":"","status":"Em projeto","priority":"Urgente"},
    ])
    snapshots = pd.DataFrame([_snap("A", potential_posts=25, potential_projects=4)])
    suggestions, _ = suggest_assignments(
        projects, snapshots, Targets(), StatusConfig(),
        max_portfolio_posts=36, max_portfolio_projects=6, priority_enabled=True, respect_time=False,
    )
    assert not suggestions.empty
    assert suggestions.iloc[0]["Nota SGO"] == "4302"


def test_balance_metrics_are_bounded():
    baseline = pd.DataFrame([
        {"Projetista":"A","PLN já atribuído":30,"Projetos já atribuídos":5},
        {"Projetista":"B","PLN já atribuído":0,"Projetos já atribuídos":0},
    ])
    result = portfolio_balance_metrics(baseline, 30, 5)
    assert 0 <= result["score"] <= 100
    assert result["spread_posts"] == 30
    assert result["avg_coverage"] == 50


def test_designer_daily_history_has_business_days():
    projects = pd.DataFrame([
        {"item_id":"1","note":"1","sgo":"4301","posts":5,"posts_valid":True,"actual_posts":5,"assignee":"A","status":"Concluído","completed_at":"2026-10-01"},
    ])
    history = designer_daily_history(projects, "A", date(2026,10,1), Targets(), days=5)
    assert len(history) == 5
    assert history.iloc[-1]["Postes"] == 5
