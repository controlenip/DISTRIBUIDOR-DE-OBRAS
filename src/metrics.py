from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from .models import StatusConfig, Targets
from .name_utils import normalize_person_name, normalize_text
from .work_schedule import business_days, nominal_minutes_for_workload, productive_minutes_elapsed, productive_minutes_remaining, workday_progress


def _safe_datetime(series: pd.Series, timezone: str) -> pd.Series:
    parsed = pd.to_datetime(series, errors="coerce")
    if getattr(parsed.dt, "tz", None) is None:
        try:
            parsed = parsed.dt.tz_localize(timezone)
        except Exception:
            pass
    else:
        try:
            parsed = parsed.dt.tz_convert(timezone)
        except Exception:
            pass
    return parsed


def prepare_projects(projects: pd.DataFrame, timezone: str) -> pd.DataFrame:
    df = projects.copy()
    expected = [
        "item_id", "note", "sgo", "municipality", "regional", "posts", "posts_valid",
        "assignee", "status", "priority", "deadline", "complexity", "assigned_at",
        "completed_at", "actual_posts", "modified_at", "etag", "assignee_lookup_id",
    ]
    for col in expected:
        if col not in df.columns:
            df[col] = None

    raw_posts = pd.to_numeric(df["posts"], errors="coerce")
    if "posts_valid" not in projects.columns:
        df["posts_valid"] = raw_posts.notna() & (raw_posts > 0)
    else:
        df["posts_valid"] = df["posts_valid"].fillna(False).astype(bool)
    df["posts"] = raw_posts.fillna(0).astype(int)

    raw_actual = pd.to_numeric(df["actual_posts"], errors="coerce")
    df["actual_posts_valid"] = raw_actual.notna() & (raw_actual >= 0)
    df["actual_posts_numeric"] = raw_actual.fillna(0).astype(int)
    # Planejamento/carteira usa PLN. Produção concluída usa a quantidade final
    # quando existir; se não existir, usa PLN como fallback.
    df["production_posts_valid"] = df["actual_posts_valid"] | df["posts_valid"]
    df["production_posts"] = df["actual_posts_numeric"].where(df["actual_posts_valid"], df["posts"])

    df["assignee"] = df["assignee"].fillna("").astype(str).str.strip()
    df["assignee_norm"] = df["assignee"].map(normalize_person_name)
    df["status"] = df["status"].fillna("").astype(str).str.strip()
    df["status_norm"] = df["status"].map(normalize_text)
    df["sgo_present"] = df["sgo"].notna() & (df["sgo"].astype(str).str.strip() != "")
    df["completed_dt"] = _safe_datetime(df["completed_at"], timezone)
    df["modified_dt"] = _safe_datetime(df["modified_at"], timezone)
    df["completion_reference"] = df["completed_dt"].where(df["completed_dt"].notna(), df["modified_dt"])
    df["deadline_dt"] = pd.to_datetime(df["deadline"], errors="coerce")
    return df


def build_daily_snapshots(
    projects: pd.DataFrame,
    designers: list[str],
    now: datetime,
    targets: Targets,
    statuses: StatusConfig,
    timezone: str = "America/Fortaleza",
) -> pd.DataFrame:
    df = prepare_projects(projects, timezone)
    now_local = now.astimezone(ZoneInfo(timezone)) if now.tzinfo else now.replace(tzinfo=ZoneInfo(timezone))
    today = now_local.date()

    completed_mask = df["status_norm"].isin(statuses.completed_set)
    completed_today_mask = completed_mask & df["completion_reference"].notna() & (df["completion_reference"].dt.date == today)
    active_mask = df["status_norm"].isin(statuses.project_pool_set) & (df["assignee_norm"] != "")

    elapsed_min = productive_minutes_elapsed(now_local, timezone)
    remaining_min = productive_minutes_remaining(now_local, timezone)
    progress = workday_progress(now_local, timezone)
    elapsed_hours = elapsed_min / 60 if elapsed_min else 0
    remaining_hours = remaining_min / 60 if remaining_min else 0

    rows = []
    for designer in designers:
        designer_norm = normalize_person_name(designer)
        d_completed = df[completed_today_mask & (df["assignee_norm"] == designer_norm)]
        d_active = df[active_mask & (df["assignee_norm"] == designer_norm)]

        completed_posts = int(d_completed.loc[d_completed["production_posts_valid"], "production_posts"].sum())
        completed_projects = int(len(d_completed))
        completed_missing_pln = int((~d_completed["posts_valid"]).sum())

        active_posts = int(d_active.loc[d_active["posts_valid"], "posts"].sum())
        active_projects = int(len(d_active))
        active_missing_pln = int((~d_active["posts_valid"]).sum())
        potential_posts = completed_posts + active_posts
        potential_projects = completed_projects + active_projects

        current_rate_posts = completed_posts / elapsed_hours if elapsed_hours else 0.0
        current_rate_projects = completed_projects / elapsed_hours if elapsed_hours else 0.0
        required_rate_posts = max(0, targets.target_posts - completed_posts) / remaining_hours if remaining_hours else 0.0
        required_rate_projects = max(0, targets.target_projects - completed_projects) / remaining_hours if remaining_hours else 0.0

        projected_posts = completed_posts + current_rate_posts * remaining_hours if elapsed_hours else completed_posts
        projected_projects = completed_projects + current_rate_projects * remaining_hours if elapsed_hours else completed_projects
        expected_posts = targets.target_posts * progress
        expected_projects = targets.target_projects * progress
        remaining_work_posts = max(0, targets.target_posts - completed_posts)
        remaining_work_projects = max(0, targets.target_projects - completed_projects)
        estimated_minutes_to_target = nominal_minutes_for_workload(
            remaining_work_posts,
            remaining_work_projects,
            targets.target_posts,
            targets.target_projects,
        )
        time_balance_minutes = remaining_min - estimated_minutes_to_target

        full_hit = completed_posts >= targets.target_posts and completed_projects >= targets.target_projects
        min_hit = completed_posts >= targets.min_posts and completed_projects >= targets.min_projects
        lacks_load = potential_posts < targets.target_posts or potential_projects < targets.target_projects

        if full_hit:
            situation = "Meta atingida"
        elif active_missing_pln > 0:
            situation = "PLN pendente na carteira"
        elif lacks_load:
            situation = "Falta de carga"
        elif remaining_min == 0:
            situation = "Encerrado abaixo da meta" if not min_hit else "Faixa mínima atingida"
        elif elapsed_min >= 120 and (projected_posts < targets.min_posts or projected_projects < targets.min_projects):
            situation = "Risco produtivo"
        elif min_hit:
            situation = "Faixa mínima atingida"
        else:
            situation = "Carteira suficiente"

        rows.append(
            {
                "Projetista": designer,
                "Postes realizados": completed_posts,
                "Projetos realizados": completed_projects,
                "Concluídos sem PLN": completed_missing_pln,
                "Postes em carteira": active_posts,
                "Projetos em carteira": active_projects,
                "Carteira sem PLN": active_missing_pln,
                "Potencial postes": potential_posts,
                "Potencial projetos": potential_projects,
                "Faltam postes": max(0, targets.target_posts - completed_posts),
                "Faltam projetos": max(0, targets.target_projects - completed_projects),
                "Sem cobertura postes": max(0, targets.target_posts - potential_posts),
                "Sem cobertura projetos": max(0, targets.target_projects - potential_projects),
                "Meta postes agora": round(expected_posts, 1),
                "Meta projetos agora": round(expected_projects, 1),
                "Ritmo postes/h": round(current_rate_posts, 2),
                "Ritmo necessário postes/h": round(required_rate_posts, 2),
                "Ritmo projetos/h": round(current_rate_projects, 2),
                "Ritmo necessário projetos/h": round(required_rate_projects, 2),
                "Previsão postes 18h": round(projected_posts, 1),
                "Previsão projetos 18h": round(projected_projects, 1),
                "Tempo útil restante (min)": remaining_min,
                "Tempo estimado p/ meta (min)": estimated_minutes_to_target,
                "Saldo de tempo (min)": time_balance_minutes,
                "Situação": situation,
            }
        )
    return pd.DataFrame(rows)


def build_assignment_baseline(
    projects: pd.DataFrame,
    designers: list[str],
    targets: Targets,
    statuses: StatusConfig,
    timezone: str = "America/Fortaleza",
) -> pd.DataFrame:
    """Summarize the current active portfolio before new distribution.

    Only projects with Status = Em projeto and a filled assignee count as current
    assigned load. The remaining target is calculated from that portfolio. A
    designer with no assigned project therefore starts with the full daily target.
    """
    df = prepare_projects(projects, timezone)
    active = df[df["status_norm"].isin(statuses.project_pool_set) & (df["assignee_norm"] != "")].copy()

    rows: list[dict] = []
    for designer in designers:
        designer_norm = normalize_person_name(designer)
        d = active[active["assignee_norm"] == designer_norm].copy()

        assigned_projects = int(len(d))
        assigned_posts = int(d.loc[d["posts_valid"], "posts"].sum())
        missing_pln = int((~d["posts_valid"]).sum())
        remaining_posts = max(0, targets.target_posts - assigned_posts)
        remaining_projects = max(0, targets.target_projects - assigned_projects)

        sgos = [str(v).strip() for v in d["sgo"].tolist() if pd.notna(v) and str(v).strip()]
        sgo_text = ", ".join(dict.fromkeys(sgos))

        if assigned_projects == 0:
            situation = "Sem projeto atribuído - meta inteira"
        elif missing_pln > 0:
            situation = "PLN pendente - carga parcial"
        elif remaining_posts == 0 and remaining_projects == 0:
            situation = "Meta de carga coberta"
        else:
            situation = "Meta parcialmente coberta"

        rows.append(
            {
                "Projetista": designer,
                "Projetos já atribuídos": assigned_projects,
                "PLN já atribuído": assigned_posts,
                "Projetos sem PLN": missing_pln,
                "Meta diária postes": targets.target_posts,
                "Meta diária projetos": targets.target_projects,
                "Meta restante postes": remaining_posts,
                "Meta restante projetos": remaining_projects,
                "Cobertura postes %": round(min(100.0, assigned_posts / max(1, targets.target_posts) * 100), 1),
                "Cobertura projetos %": round(min(100.0, assigned_projects / max(1, targets.target_projects) * 100), 1),
                "Nota SGO na carteira": sgo_text,
                "Cálculo de postes confiável": missing_pln == 0,
                "Situação da carga": situation,
            }
        )
    return pd.DataFrame(rows)


def _period_metrics(projects, designers, start_date, end_date, targets, statuses, timezone):
    df = prepare_projects(projects, timezone)
    completed = df[df["status_norm"].isin(statuses.completed_set) & df["completion_reference"].notna()].copy()
    completed["work_date"] = completed["completion_reference"].dt.date
    completed = completed[(completed["work_date"] >= start_date) & (completed["work_date"] <= end_date)]

    rows = []
    workdays = business_days(start_date, end_date)
    for designer in designers:
        designer_norm = normalize_person_name(designer)
        d = completed[completed["assignee_norm"] == designer_norm]
        daily = d.groupby("work_date").agg(
            posts=("production_posts", lambda s: int(s[d.loc[s.index, "production_posts_valid"]].sum())),
            projects=("item_id", "count"),
        ).reset_index() if not d.empty else pd.DataFrame(columns=["work_date", "posts", "projects"])
        full_days = int(((daily["posts"] >= targets.target_posts) & (daily["projects"] >= targets.target_projects)).sum()) if not daily.empty else 0
        min_days = int(((daily["posts"] >= targets.min_posts) & (daily["projects"] >= targets.min_projects)).sum()) if not daily.empty else 0
        rows.append(
            {
                "Projetista": designer,
                "Postes": int(d.loc[d["production_posts_valid"], "production_posts"].sum()),
                "Projetos": int(len(d)),
                "Projetos sem PLN": int((~d["posts_valid"]).sum()),
                "Concluídos sem quantidade final": int((~d["actual_posts_valid"]).sum()),
                "Referência postes": workdays * targets.target_posts,
                "Referência projetos": workdays * targets.target_projects,
                "Dias úteis": workdays,
                "Dias meta cheia": full_days,
                "Dias faixa mínima": min_days,
                "Consistência meta cheia %": round((full_days / workdays * 100) if workdays else 0, 1),
            }
        )
    return pd.DataFrame(rows)


def weekly_metrics(projects, designers, now, targets, statuses, timezone="America/Fortaleza"):
    local = now.astimezone(ZoneInfo(timezone)) if now.tzinfo else now.replace(tzinfo=ZoneInfo(timezone))
    start = local.date() - timedelta(days=local.weekday())
    return _period_metrics(projects, designers, start, local.date(), targets, statuses, timezone)


def monthly_metrics(projects, designers, now, targets, statuses, timezone="America/Fortaleza"):
    local = now.astimezone(ZoneInfo(timezone)) if now.tzinfo else now.replace(tzinfo=ZoneInfo(timezone))
    start = local.date().replace(day=1)
    return _period_metrics(projects, designers, start, local.date(), targets, statuses, timezone)


def monthly_prediction(projects, designers, now, targets, statuses, timezone="America/Fortaleza"):
    local = now.astimezone(ZoneInfo(timezone)) if now.tzinfo else now.replace(tzinfo=ZoneInfo(timezone))
    current = monthly_metrics(projects, designers, local, targets, statuses, timezone)
    month_start = local.date().replace(day=1)
    month_end = local.date().replace(day=monthrange(local.year, local.month)[1])
    elapsed = business_days(month_start, local.date())
    total = business_days(month_start, month_end)
    result = current.copy()
    divisor = max(1, elapsed)
    result["Média postes/dia útil"] = (result["Postes"] / divisor).round(2)
    result["Média projetos/dia útil"] = (result["Projetos"] / divisor).round(2)
    result["Projeção postes mês"] = (result["Média postes/dia útil"] * total).round(0).astype(int)
    result["Projeção projetos mês"] = (result["Média projetos/dia útil"] * total).round(0).astype(int)
    result["Meta mensal postes"] = total * targets.target_posts
    result["Meta mensal projetos"] = total * targets.target_projects
    result["Tendência"] = result.apply(
        lambda r: "Dentro/acima da referência" if (
            r["Projeção postes mês"] >= r["Meta mensal postes"] and r["Projeção projetos mês"] >= r["Meta mensal projetos"]
        ) else "Requer acompanhamento",
        axis=1,
    )
    return result


def data_quality_summary(projects: pd.DataFrame, statuses: StatusConfig) -> dict[str, int]:
    df = prepare_projects(projects, "America/Fortaleza")
    pool = df[df["status_norm"].isin(statuses.project_pool_set)].copy()
    available = pool[pool["assignee_norm"] == ""]
    assigned = pool[pool["assignee_norm"] != ""]
    return {
        "em_projeto": int(len(pool)),
        "disponiveis": int(len(available)),
        "atribuidos": int(len(assigned)),
        "disponiveis_sem_pln": int((~available["posts_valid"]).sum()),
        "atribuidos_sem_pln": int((~assigned["posts_valid"]).sum()),
        "disponiveis_sem_sgo": int((~available["sgo_present"]).sum()),
    }
