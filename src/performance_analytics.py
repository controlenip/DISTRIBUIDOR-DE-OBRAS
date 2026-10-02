from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from .metrics import prepare_projects
from .name_utils import normalize_person_name


def _local_now(now: datetime, timezone: str) -> datetime:
    return now.astimezone(ZoneInfo(timezone)) if now.tzinfo else now.replace(tzinfo=ZoneInfo(timezone))


def _business_dates(start: date, end: date) -> list[date]:
    if end < start:
        return []
    days: list[date] = []
    current = start
    while current <= end:
        if current.weekday() < 5:
            days.append(current)
        current += timedelta(days=1)
    return days


def designer_attention_table(snapshot: pd.DataFrame, target_posts: int, target_projects: int) -> pd.DataFrame:
    """Daily list of designers who need management attention.

    The list combines production pace, end-of-day forecast and missing portfolio
    coverage. It intentionally contains only project designers.
    """
    if snapshot.empty:
        return snapshot.copy()

    df = snapshot.copy()
    df["Déficit postes hoje"] = (target_posts - df["Postes realizados"]).clip(lower=0)
    df["Déficit projetos hoje"] = (target_projects - df["Projetos realizados"]).clip(lower=0)
    risk_status = {"Falta de carga", "Risco produtivo", "Encerrado abaixo da meta", "PLN pendente na carteira"}
    mask = (
        df["Situação"].isin(risk_status)
        | (df["Postes realizados"] < df["Meta postes agora"])
        | (df["Projetos realizados"] < df["Meta projetos agora"])
        | (df["Previsão postes 18h"] < target_posts)
        | (df["Previsão projetos 18h"] < target_projects)
    )
    cols = [
        "Projetista", "Postes realizados", "Projetos realizados", "Meta postes agora",
        "Meta projetos agora", "Déficit postes hoje", "Déficit projetos hoje",
        "Previsão postes 18h", "Previsão projetos 18h", "Sem cobertura postes",
        "Sem cobertura projetos", "Situação",
    ]
    return df.loc[mask, cols].sort_values(
        ["Previsão postes 18h", "Postes realizados", "Projetista"],
        ascending=[True, True, True],
    ).reset_index(drop=True)


def management_insights(
    snapshot: pd.DataFrame,
    baseline: pd.DataFrame,
    designer_prediction: pd.DataFrame,
    available_projects: int,
    available_posts: int,
) -> list[str]:
    """Generate short management insights focused on designers and workload balance."""
    insights: list[str] = []

    if not snapshot.empty:
        hit = int((snapshot["Situação"] == "Meta atingida").sum())
        risks = int(snapshot["Situação"].isin(["Risco produtivo", "Encerrado abaixo da meta"]).sum())
        no_load = int((snapshot["Situação"] == "Falta de carga").sum())
        insights.append(
            f"{hit} projetista(s) já atingiram a meta cheia hoje; {risks} estão em risco produtivo e {no_load} têm falta de carga."
        )

    if not baseline.empty:
        uncovered_posts = int(baseline["Meta restante postes"].sum())
        uncovered_projects = int(baseline["Meta restante projetos"].sum())
        zero_load = int((baseline["Projetos já atribuídos"] == 0).sum())
        insights.append(
            f"A carteira atual ainda precisa cobrir {uncovered_posts} poste(s) e {uncovered_projects} projeto(s); "
            f"{zero_load} projetista(s) estão sem obra atribuída."
        )

        load = pd.to_numeric(baseline["PLN já atribuído"], errors="coerce").fillna(0)
        if len(load) > 1:
            spread = int(load.max() - load.min())
            average = float(load.mean())
            insights.append(
                f"A carga ativa média é {average:.1f} postes por projetista e a diferença entre a maior e a menor carteira é {spread} poste(s)."
            )

    insights.append(
        f"A fila elegível possui {available_projects} obra(s), somando {available_posts} postes de PLN disponíveis para distribuição."
    )

    if not designer_prediction.empty:
        attention = int((designer_prediction["Tendência"] == "Requer acompanhamento").sum())
        stable = int((designer_prediction["Tendência"] == "Dentro/acima da referência").sum())
        insights.append(
            f"Na projeção mensal, {stable} projetista(s) estão dentro/acima da referência e {attention} requerem acompanhamento no ritmo atual."
        )
    return insights


def designer_monthly_prediction_advanced(
    projects: pd.DataFrame,
    designers: list[str],
    now: datetime,
    targets,
    statuses,
    timezone: str = "America/Fortaleza",
    rolling_days: int = 5,
) -> pd.DataFrame:
    """Month-end forecast for project designers using recent business-day pace.

    Completed production is anchored to ``Data de entrega do projeto``. Post
    production uses ``Qtd. de poste`` when available and PLN as fallback. Daily
    surplus is analytical only and never lowers the following day's target.
    """
    df = prepare_projects(projects, timezone)
    now_local = _local_now(now, timezone)
    month_start = now_local.date().replace(day=1)
    month_end = now_local.date().replace(day=monthrange(now_local.year, now_local.month)[1])
    elapsed_dates = _business_dates(month_start, now_local.date())
    remaining_dates = _business_dates(now_local.date() + timedelta(days=1), month_end)
    total_workdays = len(_business_dates(month_start, month_end))

    completed = df[df["completed_dt"].notna()].copy()
    completed["work_date"] = completed["completed_dt"].dt.date
    completed = completed[(completed["work_date"] >= month_start) & (completed["work_date"] <= now_local.date())]

    rows: list[dict] = []
    for designer in designers:
        norm = normalize_person_name(designer)
        d = completed[completed["assignee_norm"] == norm]
        if d.empty:
            daily_posts: dict[date, int] = {}
            daily_projects: dict[date, int] = {}
        else:
            daily_posts = {}
            daily_projects = {}
            for day, group in d.groupby("work_date"):
                daily_posts[day] = int(group.loc[group["production_posts_valid"], "production_posts"].sum())
                daily_projects[day] = int(len(group))

        post_values = [int(daily_posts.get(day, 0)) for day in elapsed_dates]
        project_values = [int(daily_projects.get(day, 0)) for day in elapsed_dates]
        actual_posts = int(sum(post_values))
        actual_projects = int(sum(project_values))
        recent_post_values = post_values[-rolling_days:] if post_values else []
        recent_project_values = project_values[-rolling_days:] if project_values else []
        recent_posts = sum(recent_post_values) / len(recent_post_values) if recent_post_values else 0.0
        recent_projects = sum(recent_project_values) / len(recent_project_values) if recent_project_values else 0.0
        month_avg_posts = actual_posts / max(1, len(elapsed_dates))
        month_avg_projects = actual_projects / max(1, len(elapsed_dates))
        projected_posts = int(round(actual_posts + recent_posts * len(remaining_dates)))
        projected_projects = int(round(actual_projects + recent_projects * len(remaining_dates)))
        target_posts_month = total_workdays * targets.target_posts
        target_projects_month = total_workdays * targets.target_projects
        full_days = sum(
            1 for posts, jobs in zip(post_values, project_values)
            if posts >= targets.target_posts and jobs >= targets.target_projects
        )
        consistency = full_days / max(1, len(elapsed_dates)) * 100
        post_ratio = projected_posts / max(1, target_posts_month)
        project_ratio = projected_projects / max(1, target_projects_month)
        ratio = min(post_ratio, project_ratio)
        if ratio >= 1:
            trend = "Dentro/acima da referência"
        elif ratio >= 0.9:
            trend = "Atenção"
        else:
            trend = "Requer acompanhamento"

        rows.append({
            "Projetista": designer,
            "Postes mês": actual_posts,
            "Projetos mês": actual_projects,
            "Média postes/dia útil": round(month_avg_posts, 2),
            "Média projetos/dia útil": round(month_avg_projects, 2),
            f"Média postes últimos {rolling_days} dias": round(recent_posts, 2),
            f"Média projetos últimos {rolling_days} dias": round(recent_projects, 2),
            "Projeção postes mês": projected_posts,
            "Meta mensal postes": target_posts_month,
            "Desvio postes projetado": projected_posts - target_posts_month,
            "Projeção projetos mês": projected_projects,
            "Meta mensal projetos": target_projects_month,
            "Desvio projetos projetado": projected_projects - target_projects_month,
            "Consistência meta cheia %": round(consistency, 1),
            "Tendência": trend,
        })

    order = {"Requer acompanhamento": 0, "Atenção": 1, "Dentro/acima da referência": 2}
    result = pd.DataFrame(rows)
    if result.empty:
        return result
    result["_trend_order"] = result["Tendência"].map(order).fillna(9)
    result = result.sort_values(
        ["_trend_order", "Projeção postes mês", "Projetista"],
        ascending=[True, True, True],
    ).drop(columns="_trend_order")
    return result.reset_index(drop=True)
