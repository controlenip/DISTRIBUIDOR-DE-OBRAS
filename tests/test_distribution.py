import pandas as pd

from src.distribution_engine import suggest_assignments
from src.models import StatusConfig, Targets


def test_distribution_uses_real_em_projeto_rule():
    projects = pd.DataFrame([
        {"item_id": "1", "note": "111", "sgo": "4301", "posts": 4, "posts_valid": True, "assignee": "", "status": "Em projeto", "priority": "Normal", "deadline": None, "etag": None},
        {"item_id": "2", "note": "112", "sgo": "4302", "posts": 6, "posts_valid": True, "assignee": "", "status": "Em projeto", "priority": "Normal", "deadline": None, "etag": None},
        {"item_id": "3", "note": "113", "sgo": "4303", "posts": 12, "posts_valid": True, "assignee": "", "status": "Em projeto", "priority": "Baixa", "deadline": None, "etag": None},
    ])
    snapshots = pd.DataFrame([{
        "Projetista": "Projetista A",
        "Postes realizados": 20,
        "Projetos realizados": 3,
        "Sem cobertura postes": 10,
        "Sem cobertura projetos": 2,
        "Tempo útil restante (min)": 240,
    }])
    suggestions, summary = suggest_assignments(projects, snapshots, Targets(), StatusConfig())
    assert set(suggestions["item_id"]) == {"1", "2"}
    assert int(suggestions["PLN"].sum()) == 10
    assert int(summary.iloc[0]["Novos projetos sugeridos"]) == 2


def test_distribution_blocks_missing_pln_or_sgo():
    projects = pd.DataFrame([
        {"item_id": "1", "note": "111", "sgo": "4301", "posts": 0, "posts_valid": False, "assignee": "", "status": "Em projeto"},
        {"item_id": "2", "note": "112", "sgo": None, "posts": 8, "posts_valid": True, "assignee": "", "status": "Em projeto"},
        {"item_id": "3", "note": "113", "sgo": "4303", "posts": 8, "posts_valid": True, "assignee": "", "status": "Em projeto"},
    ])
    snapshots = pd.DataFrame([{
        "Projetista": "Projetista A",
        "Postes realizados": 22,
        "Projetos realizados": 4,
        "Sem cobertura postes": 8,
        "Sem cobertura projetos": 1,
        "Tempo útil restante (min)": 180,
    }])
    suggestions, _ = suggest_assignments(projects, snapshots, Targets(), StatusConfig())
    assert suggestions["item_id"].tolist() == ["3"]


def test_distribution_holds_designer_with_assigned_project_without_pln():
    projects = pd.DataFrame([
        {"item_id": "1", "note": "111", "sgo": "4301", "posts": 0, "posts_valid": False, "assignee": "Projetista A", "status": "Em projeto"},
        {"item_id": "2", "note": "112", "sgo": "4302", "posts": 8, "posts_valid": True, "assignee": "", "status": "Em projeto"},
    ])
    snapshots = pd.DataFrame([{
        "Projetista": "Projetista A",
        "Postes realizados": 0,
        "Projetos realizados": 0,
        "Postes em carteira": 0,
        "Projetos em carteira": 1,
        "Carteira sem PLN": 1,
        "Potencial postes": 0,
        "Potencial projetos": 1,
        "Sem cobertura postes": 30,
        "Sem cobertura projetos": 4,
        "Tempo útil restante (min)": 300,
    }])
    suggestions, summary = suggest_assignments(projects, snapshots, Targets(), StatusConfig())
    assert suggestions.empty
    assert summary.iloc[0]["Motivo"] == "Distribuição bloqueada: existe projeto atribuído sem PLN"
