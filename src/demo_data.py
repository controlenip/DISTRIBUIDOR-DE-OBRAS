from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd


def sample_designers() -> list[str]:
    return ["Projetista A", "Projetista B", "Projetista C", "Projetista D"]


def sample_designers_df() -> pd.DataFrame:
    return pd.DataFrame({
        "name": sample_designers(),
        "email": ["a@empresa.com", "b@empresa.com", "c@empresa.com", "d@empresa.com"],
        "sharepoint_lookup_id": [None, None, None, None],
    })


def sample_projects(timezone: str = "America/Fortaleza") -> pd.DataFrame:
    now = datetime.now(ZoneInfo(timezone))
    today = now.replace(hour=10, minute=0, second=0, microsecond=0)
    yesterday = today - timedelta(days=1)

    rows = [
        # item_id, note, sgo, municipality, regional, PLN, assignee, status, priority, deadline, completed_at
        ("1", "111000001", "430100001", "São Luís", "Norte", 8, "Projetista A", "Concluído", "Normal", None, today),
        ("2", "111000002", "430100002", "São Luís", "Norte", 7, "Projetista A", "Concluído", "Normal", None, today),
        ("3", "111000003", "430100003", "Bacabal", "Centro", 9, "Projetista B", "Concluído", "Alta", None, today),
        ("4", "111000004", "430100004", "Timon", "Leste", 5, "Projetista C", "Concluído", "Normal", None, today),
        # Carteira já atribuída: status continua Em projeto
        ("5", "111000005", "430100005", "Rosário", "Norte", 8, "Projetista A", "Em projeto", "Normal", None, None),
        ("6", "111000006", "430100006", "Codó", "Leste", 6, "Projetista B", "Em projeto", "Normal", None, None),
        ("7", "111000007", "430100007", "Caxias", "Leste", 7, "Projetista C", "Em projeto", "Normal", None, None),
        ("8", "111000008", "430100008", "Santa Inês", "Noroeste", 12, "Projetista D", "Em projeto", "Alta", None, None),
        # Disponíveis: Em projeto + assignee vazio
        ("9", "111000009", "430100009", "Pinheiro", "Norte", 3, "", "Em projeto", "Alta", now + timedelta(days=1), None),
        ("10", "111000010", "430100010", "Viana", "Norte", 5, "", "Em projeto", "Normal", now + timedelta(days=2), None),
        ("11", "111000011", "430100011", "Pedreiras", "Centro", 6, "", "Em projeto", "Normal", now + timedelta(days=3), None),
        ("12", "111000012", "430100012", "Imperatriz", "Sul", 9, "", "Em projeto", "Alta", now + timedelta(days=1), None),
        ("13", "111000013", "430100013", "Açailândia", "Sul", 4, "", "Em projeto", "Normal", now + timedelta(days=4), None),
        ("14", "111000014", "430100014", "Chapadinha", "Leste", 7, "", "Em projeto", "Normal", now + timedelta(days=2), None),
        ("15", "111000015", "430100015", "Itapecuru Mirim", "Norte", 10, "", "Em projeto", "Alta", now + timedelta(days=1), None),
        ("16", "111000016", "430100016", "Grajaú", "Centro", 2, "", "Em projeto", "Baixa", now + timedelta(days=5), None),
        ("17", "111000017", "430100017", "Barra do Corda", "Centro", 5, "", "Em projeto", "Normal", now + timedelta(days=3), None),
        ("18", "111000018", "430100018", "Presidente Dutra", "Centro", 8, "", "Em projeto", "Normal", now + timedelta(days=2), None),
        # Histórico
        ("19", "110999901", "430099901", "São Luís", "Norte", 31, "Projetista A", "Concluído", "Normal", None, yesterday),
        ("20", "110999902", "430099902", "Bacabal", "Centro", 27, "Projetista B", "Concluído", "Normal", None, yesterday),
        ("21", "110999903", "430099903", "Timon", "Leste", 25, "Projetista C", "Concluído", "Normal", None, yesterday),
        ("22", "110999904", "430099904", "Imperatriz", "Sul", 33, "Projetista D", "Concluído", "Normal", None, yesterday),
    ]
    df = pd.DataFrame(rows, columns=[
        "item_id", "note", "sgo", "municipality", "regional", "posts", "assignee", "status", "priority", "deadline", "completed_at"
    ])
    df["posts_valid"] = df["posts"].notna() & (df["posts"] > 0)
    df["actual_posts"] = None
    df["assigned_at"] = None
    df["complexity"] = None
    df["modified_at"] = now
    df["etag"] = [f'W/"{i}"' for i in range(1, len(df) + 1)]
    df["assignee_lookup_id"] = None
    return df
