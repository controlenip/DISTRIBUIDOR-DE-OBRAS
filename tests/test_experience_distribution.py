import pandas as pd

from src.distribution_engine import suggest_assignments
from src.models import StatusConfig, Targets


def _snapshots():
    base = {
        "Postes realizados": 0,
        "Projetos realizados": 0,
        "Postes em carteira": 0,
        "Projetos em carteira": 0,
        "Carteira sem PLN": 0,
        "Potencial postes": 0,
        "Potencial projetos": 0,
        "Sem cobertura postes": 30,
        "Sem cobertura projetos": 5,
        "Tempo útil restante (min)": 300,
    }
    return pd.DataFrame([
        {**base, "Projetista": "Junior"},
        {**base, "Projetista": "Senior"},
    ])


def _projects():
    return pd.DataFrame([
        {
            "item_id": "easy", "note": "1", "sgo": "1001", "status": "Em projeto",
            "assignee": "", "posts": 5, "posts_valid": True, "project_type": "UNI",
        },
        {
            "item_id": "hard", "note": "2", "sgo": "1002", "status": "Em projeto",
            "assignee": "", "posts": 5, "posts_valid": True, "project_type": "MTP",
        },
    ])


def test_preferential_matching_sends_easy_to_less_experienced_and_hard_to_experienced():
    suggestions, _ = suggest_assignments(
        _projects(), _snapshots(), Targets(), StatusConfig(),
        max_new_projects_per_designer=1,
        experience_enabled=True,
        designer_experience={"Junior": "Menos experiente", "Senior": "Experiente"},
        project_difficulty={"UNI": "Fácil", "MTP": "Difícil"},
        experience_mode="Preferencial",
        respect_time=False,
    )
    mapping = dict(zip(suggestions["item_id"], suggestions["Projetista"]))
    assert mapping["easy"] == "Junior"
    assert mapping["hard"] == "Senior"
    assert "Postes Alterados/Novos" in suggestions.columns
    assert "PI (Tipo Projeto)" in suggestions.columns


def test_strict_mode_never_gives_hard_project_to_less_experienced():
    projects = _projects().query("item_id == 'hard'").copy()
    snaps = _snapshots().query("Projetista == 'Junior'").copy()
    suggestions, summary = suggest_assignments(
        projects, snaps, Targets(), StatusConfig(),
        experience_enabled=True,
        designer_experience={"Junior": "Menos experiente"},
        project_difficulty={"MTP": "Difícil"},
        experience_mode="Estrito",
        respect_time=False,
    )
    assert suggestions.empty
    assert "experiência" in summary.iloc[0]["Motivo"]
