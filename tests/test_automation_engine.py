from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from src.automation_engine import AutomationEngine, AutomationPolicy
from src.models import StatusConfig, Targets


TZ = ZoneInfo("America/Fortaleza")
TARGETS = Targets(min_posts=25, target_posts=30, min_projects=4, target_projects=5)
STATUS = StatusConfig(project_pool=("Em projeto",), completed=("Concluído",))


def project(item_id, posts, assignee="", status="Em projeto", sgo="430000001"):
    return {
        "item_id": item_id,
        "note": f"N-{item_id}",
        "sgo": sgo,
        "status": status,
        "regional": "NORTE",
        "municipality": "SAO LUIS",
        "posts": posts,
        "posts_valid": posts > 0,
        "assignee": assignee,
        "completed_at": None,
        "actual_posts": None,
        "priority": "Normal",
        "deadline": None,
        "etag": None,
    }


def test_cycle_assigns_only_uncovered_load():
    projects = pd.DataFrame([
        project("1", 10, assignee="PROJETISTA A"),
        project("2", 8),
        project("3", 7),
        project("4", 5),
    ])
    engine = AutomationEngine(TARGETS, STATUS, AutomationPolicy(require_work_hours=True))
    now = datetime(2026, 10, 1, 9, 0, tzinfo=TZ)
    result = engine.run_cycle(projects, ["PROJETISTA A"], now)
    assert result.status == "success"
    assert not result.suggestions.empty
    assert result.suggestions["item_id"].astype(str).is_unique
    assert result.suggestions["PLN"].sum() >= 20


def test_cycle_skips_during_break():
    projects = pd.DataFrame([project("1", 10)])
    engine = AutomationEngine(TARGETS, STATUS, AutomationPolicy(require_work_hours=True))
    now = datetime(2026, 10, 1, 12, 30, tzinfo=TZ)
    result = engine.run_cycle(projects, ["PROJETISTA A"], now)
    assert result.status == "skipped"
    assert result.suggestions.empty


def test_cycle_does_not_assign_already_assigned_project():
    projects = pd.DataFrame([
        project("1", 15, assignee="OUTRA PESSOA"),
        project("2", 15),
        project("3", 15),
    ])
    engine = AutomationEngine(TARGETS, STATUS, AutomationPolicy(require_work_hours=False))
    now = datetime(2026, 10, 1, 7, 0, tzinfo=TZ)
    result = engine.run_cycle(projects, ["PROJETISTA A"], now)
    assert "1" not in set(result.suggestions["item_id"].astype(str))
