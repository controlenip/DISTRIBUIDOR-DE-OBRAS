from __future__ import annotations

import pandas as pd

from .metrics import prepare_projects
from .work_schedule import nominal_minutes_for_workload


PRIORITY_RANK = {
    "urgente": 0,
    "crítica": 0,
    "critica": 0,
    "alta": 1,
    "normal": 2,
    "média": 2,
    "media": 2,
    "baixa": 3,
}


def _priority(value: object) -> int:
    return PRIORITY_RANK.get(str(value or "").strip().casefold(), 2)


def _coverage_score(potential_posts: float, potential_projects: float, target_posts: int, target_projects: int) -> float:
    post_cov = min(1.0, max(0.0, float(potential_posts)) / max(1, target_posts))
    project_cov = min(1.0, max(0.0, float(potential_projects)) / max(1, target_projects))
    return (post_cov + project_cov) / 2.0


def _pick_project(
    candidates: pd.DataFrame,
    need_posts: int,
    need_projects: int,
    current_posts: int,
    current_projects: int,
    max_portfolio_posts: int | None,
    max_portfolio_projects: int | None,
    priority_enabled: bool,
) -> pd.Series | None:
    """Pick one project that advances both targets without breaching portfolio limits."""
    if candidates.empty:
        return None

    work = candidates.copy()
    if max_portfolio_posts is not None:
        work = work[(current_posts + work["posts"].astype(int)) <= int(max_portfolio_posts)]
    if max_portfolio_projects is not None and current_projects + 1 > int(max_portfolio_projects):
        return None
    if work.empty:
        return None

    ideal_posts = (need_posts / max(1, need_projects)) if need_posts > 0 else 0.0

    def score(row: pd.Series) -> tuple:
        posts = int(row["posts"])
        if need_posts <= 0 and need_projects > 0:
            fit = posts
        else:
            under = max(0, need_posts - posts)
            over = max(0, posts - need_posts)
            closeness = abs(posts - ideal_posts)
            fit = closeness + over * 3 + (under / max(1, need_projects)) * 0.05

        deadline = row.get("_deadline_sort")
        deadline_ord = deadline.value if isinstance(deadline, pd.Timestamp) and deadline is not pd.NaT else pd.Timestamp.max.value
        priority_rank = int(row.get("_priority", 2)) if priority_enabled else 2
        return (priority_rank, deadline_ord, fit, posts, str(row.get("item_id", "")))

    best_idx = min(work.index, key=lambda idx: score(work.loc[idx]))
    return work.loc[best_idx]


def suggest_assignments(
    projects,
    snapshots,
    targets,
    statuses,
    max_new_projects_per_designer=6,
    max_portfolio_posts: int | None = None,
    max_portfolio_projects: int | None = None,
    priority_enabled: bool = True,
    respect_time: bool = True,
):
    """Suggest a fair, non-destructive distribution.

    Rules:
    - only Status=Em projeto, empty assignee, valid SGO and PLN are eligible;
    - existing assignments are never moved;
    - lowest target coverage receives the next project (round-robin/water filling);
    - priority/deadline can influence which project is selected;
    - portfolio caps prevent overload.
    """
    df = prepare_projects(projects, "America/Fortaleza")
    df["_priority"] = df["priority"].map(_priority)
    df["_deadline_sort"] = pd.to_datetime(df["deadline"], errors="coerce").fillna(pd.Timestamp.max)

    available = df[
        df["status_norm"].isin(statuses.project_pool_set)
        & (df["assignee_norm"] == "")
        & df["posts_valid"]
        & df["sgo_present"]
    ].copy()

    if snapshots.empty:
        return pd.DataFrame(), pd.DataFrame()

    virtual = snapshots.copy().reset_index(drop=True)
    virtual["_new_projects"] = 0
    virtual["_new_posts"] = 0
    if "Potencial postes" in virtual.columns:
        base_potential_posts = virtual["Potencial postes"].fillna(0).astype(int)
    else:
        base_potential_posts = (targets.target_posts - virtual.get("Sem cobertura postes", 0)).clip(lower=0).astype(int)
    if "Potencial projetos" in virtual.columns:
        base_potential_projects = virtual["Potencial projetos"].fillna(0).astype(int)
    else:
        base_potential_projects = (targets.target_projects - virtual.get("Sem cobertura projetos", 0)).clip(lower=0).astype(int)
    virtual["_base_potential_posts"] = base_potential_posts
    virtual["_base_potential_projects"] = base_potential_projects
    virtual["_virtual_posts"] = base_potential_posts
    virtual["_virtual_projects"] = base_potential_projects

    remaining_projects = available.copy()
    suggestion_rows: list[dict] = []

    while not remaining_projects.empty:
        eligible_indices: list[int] = []
        for idx, snap in virtual.iterrows():
            if respect_time and int(snap["Tempo útil restante (min)"]) <= 0:
                continue
            if int(snap.get("Carteira sem PLN", 0) or 0) > 0:
                continue
            if int(snap["_new_projects"]) >= int(max_new_projects_per_designer):
                continue
            if max_portfolio_projects is not None and int(snap["_virtual_projects"]) >= int(max_portfolio_projects):
                continue
            if max_portfolio_posts is not None and int(snap["_virtual_posts"]) >= int(max_portfolio_posts):
                continue
            needs_posts = int(snap["_virtual_posts"]) < targets.target_posts
            needs_projects = int(snap["_virtual_projects"]) < targets.target_projects
            if needs_posts or needs_projects:
                eligible_indices.append(idx)

        if not eligible_indices:
            break

        def designer_key(idx: int) -> tuple:
            snap = virtual.loc[idx]
            coverage = _coverage_score(
                snap["_virtual_posts"], snap["_virtual_projects"], targets.target_posts, targets.target_projects
            )
            return (
                coverage,
                int(snap["_new_projects"]),
                int(snap["Postes realizados"]),
                int(snap["Projetos realizados"]),
                str(snap["Projetista"]),
            )

        # Try designers from lowest coverage upward. If the lowest one cannot take
        # any available project because of the cap, move to the next designer.
        chosen_designer_idx = None
        chosen_project = None
        for designer_idx in sorted(eligible_indices, key=designer_key):
            snap = virtual.loc[designer_idx]
            need_posts = max(0, targets.target_posts - int(snap["_virtual_posts"]))
            need_projects = max(0, targets.target_projects - int(snap["_virtual_projects"]))
            candidate = _pick_project(
                remaining_projects,
                need_posts,
                need_projects,
                int(snap["_virtual_posts"]),
                int(snap["_virtual_projects"]),
                max_portfolio_posts,
                max_portfolio_projects,
                priority_enabled,
            )
            if candidate is not None:
                chosen_designer_idx = designer_idx
                chosen_project = candidate
                break

        if chosen_designer_idx is None or chosen_project is None:
            break

        snap = virtual.loc[chosen_designer_idx]
        need_posts = max(0, targets.target_posts - int(snap["_virtual_posts"]))
        need_projects = max(0, targets.target_projects - int(snap["_virtual_projects"]))
        item_id = str(chosen_project["item_id"])
        posts = int(chosen_project["posts"])
        designer = str(snap["Projetista"])
        before_posts = int(snap["_virtual_posts"])
        before_projects = int(snap["_virtual_projects"])
        after_posts = before_posts + posts
        after_projects = before_projects + 1
        priority_value = str(chosen_project.get("priority") or "Normal").strip() or "Normal"

        reason_parts = [f"menor cobertura da equipe ({before_posts} postes / {before_projects} projetos)"]
        if priority_enabled and _priority(priority_value) <= 1:
            reason_parts.append(f"prioridade {priority_value}")
        if need_posts > 0 or need_projects > 0:
            reason_parts.append(f"faltavam {need_posts} postes e {need_projects} projetos")

        suggestion_rows.append(
            {
                "Projetista": designer,
                "item_id": item_id,
                "Nº da nota": chosen_project.get("note"),
                "Nota SGO": chosen_project.get("sgo"),
                "PLN": posts,
                "Regional": chosen_project.get("regional"),
                "Município": chosen_project.get("municipality"),
                "Prioridade": priority_value,
                "Prazo": chosen_project.get("deadline"),
                "Carga antes (postes)": before_posts,
                "Carga antes (projetos)": before_projects,
                "Carga depois (postes)": after_posts,
                "Carga depois (projetos)": after_projects,
                "etag": chosen_project.get("etag"),
                "Motivo": "; ".join(reason_parts),
            }
        )

        virtual.at[chosen_designer_idx, "_new_projects"] = int(snap["_new_projects"]) + 1
        virtual.at[chosen_designer_idx, "_new_posts"] = int(snap["_new_posts"]) + posts
        virtual.at[chosen_designer_idx, "_virtual_posts"] = after_posts
        virtual.at[chosen_designer_idx, "_virtual_projects"] = after_projects
        remaining_projects = remaining_projects[remaining_projects["item_id"].astype(str) != item_id]

    designer_rows: list[dict] = []
    for _, snap in virtual.iterrows():
        designer = str(snap["Projetista"])
        suggested_projects = int(snap["_new_projects"])
        suggested_posts = int(snap["_new_posts"])
        remaining_minutes = int(snap["Tempo útil restante (min)"])
        remaining_work_posts = max(0, targets.target_posts - int(snap["Postes realizados"]))
        remaining_work_projects = max(0, targets.target_projects - int(snap["Projetos realizados"]))
        nominal_needed_minutes = nominal_minutes_for_workload(
            remaining_work_posts,
            remaining_work_projects,
            targets.target_posts,
            targets.target_projects,
        )
        time_risk = nominal_needed_minutes > remaining_minutes
        covered_posts = int(snap["_virtual_posts"]) >= targets.target_posts
        covered_projects = int(snap["_virtual_projects"]) >= targets.target_projects

        if int(snap.get("Carteira sem PLN", 0) or 0) > 0:
            reason = "Distribuição bloqueada: existe projeto atribuído sem PLN"
        elif covered_posts and covered_projects:
            reason = "Carteira cobre a meta diária"
        elif suggested_projects:
            reason = "Recebeu carga, mas a fila/limite não permitiu cobertura total"
        elif int(snap["_base_potential_posts"]) >= targets.target_posts and int(snap["_base_potential_projects"]) >= targets.target_projects:
            reason = "Carteira já cobria a meta antes do ciclo"
        else:
            reason = "Sem obra compatível disponível ou limite de carteira atingido"

        designer_rows.append(
            {
                "Projetista": designer,
                "Novos projetos sugeridos": suggested_projects,
                "Novos postes sugeridos": suggested_posts,
                "Potencial postes após distribuição": int(snap["_virtual_posts"]),
                "Potencial projetos após distribuição": int(snap["_virtual_projects"]),
                "Risco de tempo": bool(time_risk),
                "Motivo": reason,
            }
        )

    return pd.DataFrame(suggestion_rows), pd.DataFrame(designer_rows)
