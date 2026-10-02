from __future__ import annotations

import pandas as pd

from .experience_rules import (
    match_penalty,
    normalize_difficulty_label,
    normalize_experience_label,
)
from .metrics import prepare_projects
from .name_utils import normalize_person_name, normalize_text
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
    current_active_projects: int,
    max_portfolio_posts: int | None,
    max_portfolio_projects: int | None,
    priority_enabled: bool,
    experience_enabled: bool = False,
    designer_experience: str = "Intermediário",
    experience_mode: str = "Preferencial",
    oversize_lock_enabled: bool = True,
    target_posts: int = 30,
) -> pd.Series | None:
    """Pick one project that advances targets without breaching portfolio limits.

    When experience matching is enabled, exact experience/difficulty matches are
    preferred. In strict mode, a project harder than the designer's experience
    is excluded. In preferential mode it is kept only as fallback.
    """
    if candidates.empty:
        return None

    work = candidates.copy()
    if max_portfolio_posts is not None:
        work = work[(current_posts + work["posts"].astype(int)) <= int(max_portfolio_posts)]
    if max_portfolio_projects is not None and current_projects + 1 > int(max_portfolio_projects):
        return None
    # Projetos individuais acima da meta diária são tratados como carga especial.
    # Para garantir a trava de forma determinística a partir da BASE, a automação
    # só entrega esse tipo de obra para quem está sem projetos Em projeto.
    if oversize_lock_enabled and current_active_projects > 0:
        work = work[work["posts"].astype(int) <= int(target_posts)]
    if work.empty:
        return None

    if experience_enabled:
        penalties: dict[int, tuple[int, int] | None] = {}
        for idx, row in work.iterrows():
            penalties[idx] = match_penalty(designer_experience, row.get("_difficulty", "Médio"), experience_mode)
        if str(experience_mode or "").strip().casefold() == "estrito":
            allowed = [idx for idx, penalty in penalties.items() if penalty is not None]
            work = work.loc[allowed]
            if work.empty:
                return None
    else:
        penalties = {idx: (0, 0) for idx in work.index}

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
        exp_penalty = penalties.get(row.name) or (0, 0)
        # Experience matching comes before queue fit so hard/easy work tends to the
        # appropriate profile. Priority/deadline still break ties inside the match.
        return (exp_penalty[0], exp_penalty[1], priority_rank, deadline_ord, fit, posts, str(row.get("item_id", "")))

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
    experience_enabled: bool = False,
    designer_experience: dict[str, str] | None = None,
    project_difficulty: dict[str, str] | None = None,
    experience_mode: str = "Preferencial",
    oversize_lock_enabled: bool = True,
):
    """Suggest a fair, non-destructive distribution.

    Rules:
    - only Status=Em projeto, empty assignee, valid SGO and Postes Alterados/Novos are eligible;
    - existing assignments are never moved;
    - lowest target coverage receives the next project (round-robin/water filling);
    - priority/deadline can influence which project is selected;
    - optional experience matching uses PI (Tipo Projeto) as project difficulty;
    - portfolio caps prevent overload;
    - when oversize lock is enabled, a project with posts > daily target blocks
      that designer from receiving another project while it remains Em projeto.
    """
    df = prepare_projects(projects, "America/Fortaleza")
    df["_priority"] = df["priority"].map(_priority)
    df["_deadline_sort"] = pd.to_datetime(df["deadline"], errors="coerce").fillna(pd.Timestamp.max)

    difficulty_map_norm = {
        normalize_text(k): normalize_difficulty_label(v)
        for k, v in (project_difficulty or {}).items()
        if str(k or "").strip()
    }
    df["_difficulty"] = df["project_type"].map(
        lambda value: difficulty_map_norm.get(normalize_text(value), "Médio")
    )

    experience_map_norm = {
        normalize_person_name(k): normalize_experience_label(v)
        for k, v in (designer_experience or {}).items()
    }

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
    if "Projetos em carteira" in virtual.columns:
        virtual["_active_projects_for_oversize"] = virtual["Projetos em carteira"].fillna(0).astype(int)
    else:
        virtual["_active_projects_for_oversize"] = 0
    if "Bloqueio projeto acima da meta" in virtual.columns:
        virtual["_oversize_lock"] = virtual["Bloqueio projeto acima da meta"].fillna(False).astype(bool)
    else:
        virtual["_oversize_lock"] = False

    remaining_projects = available.copy()
    suggestion_rows: list[dict] = []

    while not remaining_projects.empty:
        eligible_indices: list[int] = []
        for idx, snap in virtual.iterrows():
            if respect_time and int(snap["Tempo útil restante (min)"]) <= 0:
                continue
            if int(snap.get("Carteira sem PLN", 0) or 0) > 0:
                continue
            if oversize_lock_enabled and bool(snap.get("_oversize_lock", False)):
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

        chosen_designer_idx = None
        chosen_project = None
        chosen_experience = "Intermediário"
        for designer_idx in sorted(eligible_indices, key=designer_key):
            snap = virtual.loc[designer_idx]
            need_posts = max(0, targets.target_posts - int(snap["_virtual_posts"]))
            need_projects = max(0, targets.target_projects - int(snap["_virtual_projects"]))
            designer = str(snap["Projetista"])
            exp_level = experience_map_norm.get(normalize_person_name(designer), "Intermediário")
            candidate = _pick_project(
                remaining_projects,
                need_posts,
                need_projects,
                int(snap["_virtual_posts"]),
                int(snap["_virtual_projects"]),
                int(snap.get("_active_projects_for_oversize", 0)),
                max_portfolio_posts,
                max_portfolio_projects,
                priority_enabled,
                experience_enabled=experience_enabled,
                designer_experience=exp_level,
                experience_mode=experience_mode,
                oversize_lock_enabled=oversize_lock_enabled,
                target_posts=targets.target_posts,
            )
            if candidate is not None:
                chosen_designer_idx = designer_idx
                chosen_project = candidate
                chosen_experience = exp_level
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
        project_type_value = str(chosen_project.get("project_type") or "").strip()
        difficulty_value = normalize_difficulty_label(chosen_project.get("_difficulty", "Médio"))
        is_oversized_project = posts > int(targets.target_posts)

        reason_parts = [f"menor cobertura da equipe ({before_posts} postes / {before_projects} projetos)"]
        if experience_enabled:
            reason_parts.append(
                f"perfil {chosen_experience} compatível com dificuldade {difficulty_value}"
                + (f" do PI {project_type_value}" if project_type_value else "")
            )
        if priority_enabled and _priority(priority_value) <= 1:
            reason_parts.append(f"prioridade {priority_value}")
        if need_posts > 0 or need_projects > 0:
            reason_parts.append(f"faltavam {need_posts} postes e {need_projects} projetos")
        if oversize_lock_enabled and is_oversized_project:
            reason_parts.append(
                f"projeto acima da meta diária ({posts}>{targets.target_posts}); projetista bloqueado até a carteira voltar a zero"
            )

        suggestion_rows.append(
            {
                "Projetista": designer,
                "item_id": item_id,
                "Nº da nota": chosen_project.get("note"),
                "Nota SGO": chosen_project.get("sgo"),
                "Postes Alterados/Novos": posts,
                # Backward-compatible alias for workers/tests created before V13.
                "PLN": posts,
                "PI (Tipo Projeto)": project_type_value,
                "Dificuldade": difficulty_value,
                "Experiência projetista": chosen_experience,
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
        virtual.at[chosen_designer_idx, "_active_projects_for_oversize"] = int(snap.get("_active_projects_for_oversize", 0)) + 1
        if oversize_lock_enabled and is_oversized_project:
            virtual.at[chosen_designer_idx, "_oversize_lock"] = True
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

        if oversize_lock_enabled and bool(snap.get("_oversize_lock", False)) and suggested_projects == 0:
            reason = "Bloqueado: projeto acima da meta diária ainda está Em projeto"
        elif int(snap.get("Carteira sem PLN", 0) or 0) > 0:
            reason = "Distribuição bloqueada: existe projeto atribuído sem Postes Alterados/Novos"
        elif oversize_lock_enabled and bool(snap.get("_oversize_lock", False)) and suggested_projects > 0:
            reason = "Recebeu projeto acima da meta diária e ficou bloqueado para novas atribuições"
        elif covered_posts and covered_projects:
            reason = "Carteira cobre a meta diária"
        elif suggested_projects:
            reason = "Recebeu carga, mas a fila/limite não permitiu cobertura total"
        elif int(snap["_base_potential_posts"]) >= targets.target_posts and int(snap["_base_potential_projects"]) >= targets.target_projects:
            reason = "Carteira já cobria a meta antes do ciclo"
        elif experience_enabled and str(experience_mode or "").strip().casefold() == "estrito":
            reason = "Sem obra compatível com o nível de experiência ou limite de carteira atingido"
        else:
            reason = "Sem obra compatível disponível ou limite de carteira atingido"

        designer_rows.append(
            {
                "Projetista": designer,
                "Experiência": experience_map_norm.get(normalize_person_name(designer), "Intermediário"),
                "Bloqueado por projeto acima da meta": bool(snap.get("_oversize_lock", False)) if oversize_lock_enabled else False,
                "Novos projetos sugeridos": suggested_projects,
                "Novos postes sugeridos": suggested_posts,
                "Potencial postes após distribuição": int(snap["_virtual_posts"]),
                "Potencial projetos após distribuição": int(snap["_virtual_projects"]),
                "Risco de tempo": bool(time_risk),
                "Motivo": reason,
            }
        )

    return pd.DataFrame(suggestion_rows), pd.DataFrame(designer_rows)
