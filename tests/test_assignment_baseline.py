import pandas as pd

from src.metrics import build_assignment_baseline
from src.models import StatusConfig, Targets


def _project(item_id, posts, assignee="", status="Em projeto", sgo="4301", posts_valid=True):
    return {
        "item_id": item_id,
        "note": f"N-{item_id}",
        "sgo": sgo,
        "status": status,
        "regional": "NORTE",
        "municipality": "SAO LUIS",
        "posts": posts,
        "posts_valid": posts_valid,
        "assignee": assignee,
        "completed_at": None,
        "actual_posts": None,
        "priority": "Normal",
        "deadline": None,
        "etag": None,
    }


def test_baseline_subtracts_existing_assigned_load():
    projects = pd.DataFrame([
        _project("1", 10, assignee="PROJETISTA A"),
        _project("2", 8, assignee="PROJETISTA A"),
        _project("3", 5, assignee=""),
    ])
    result = build_assignment_baseline(projects, ["PROJETISTA A"], Targets(), StatusConfig())
    row = result.iloc[0]
    assert row["Projetos já atribuídos"] == 2
    assert row["PLN já atribuído"] == 18
    assert row["Meta restante postes"] == 12
    assert row["Meta restante projetos"] == 3
    assert row["Situação da carga"] == "Meta parcialmente coberta"


def test_baseline_full_target_when_designer_has_no_assignment():
    projects = pd.DataFrame([_project("1", 10, assignee="OUTRA PESSOA")])
    result = build_assignment_baseline(projects, ["PROJETISTA B"], Targets(), StatusConfig())
    row = result.iloc[0]
    assert row["Projetos já atribuídos"] == 0
    assert row["PLN já atribuído"] == 0
    assert row["Meta restante postes"] == 30
    assert row["Meta restante projetos"] == 5
    assert row["Situação da carga"] == "Sem projeto atribuído - meta inteira"


def test_baseline_flags_assigned_project_without_pln():
    projects = pd.DataFrame([
        _project("1", 0, assignee="PROJETISTA A", posts_valid=False),
        _project("2", 7, assignee="PROJETISTA A", posts_valid=True),
    ])
    result = build_assignment_baseline(projects, ["PROJETISTA A"], Targets(), StatusConfig())
    row = result.iloc[0]
    assert row["Projetos já atribuídos"] == 2
    assert row["Projetos sem PLN"] == 1
    assert row["PLN já atribuído"] == 7
    assert bool(row["Cálculo de postes confiável"]) is False
    assert row["Situação da carga"] == "PLN pendente - carga parcial"
