from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable
from uuid import uuid4

import pandas as pd

from .audit_store import AuditStore
from .distribution_engine import suggest_assignments
from .metrics import build_daily_snapshots, prepare_projects
from .models import StatusConfig, Targets
from .work_schedule import current_work_status, productive_minutes_remaining


@dataclass(frozen=True)
class AutomationPolicy:
    timezone: str = "America/Fortaleza"
    max_new_projects_per_designer: int = 6
    assign_during_break: bool = False
    require_work_hours: bool = True
    require_sgo: bool = True
    require_pln: bool = True
    max_portfolio_posts: int | None = 36
    max_portfolio_projects: int | None = 6
    priority_enabled: bool = True
    experience_enabled: bool = False
    experience_mode: str = "Preferencial"
    designer_experience: dict[str, str] | None = None
    project_difficulty: dict[str, str] | None = None


@dataclass
class AutomationResult:
    cycle_id: str
    status: str
    message: str
    snapshot: pd.DataFrame
    suggestions: pd.DataFrame
    distribution_summary: pd.DataFrame
    assignments_applied: int = 0
    errors: list[str] | None = None


class AutomationEngine:
    """Runs a single safe distribution cycle.

    The engine itself is independent from Microsoft Lists. A caller injects an
    apply function when actual writes are desired. This makes local Excel tests
    and future Lists tests use the exact same business rules.
    """

    def __init__(
        self,
        targets: Targets,
        statuses: StatusConfig,
        policy: AutomationPolicy | None = None,
        audit: AuditStore | None = None,
    ):
        self.targets = targets
        self.statuses = statuses
        self.policy = policy or AutomationPolicy()
        self.audit = audit

    def _work_window_allows_distribution(self, now: datetime) -> tuple[bool, str]:
        status = current_work_status(now, self.policy.timezone)
        if not self.policy.require_work_hours:
            return True, status
        if status.startswith("Expediente -"):
            return True, status
        if status == "Intervalo" and self.policy.assign_during_break:
            return True, status
        return False, status

    def run_cycle(
        self,
        projects: pd.DataFrame,
        designers: list[str],
        now: datetime,
        source: str = "excel",
        mode: str = "dry-run",
        apply_assignment: Callable[[pd.Series], None] | None = None,
    ) -> AutomationResult:
        cycle_id = f"{now.strftime('%Y%m%dT%H%M%S')}-{uuid4().hex[:8]}"
        if self.audit:
            self.audit.start_cycle(cycle_id, now, source, mode, len(projects), len(designers))

        snapshot = build_daily_snapshots(
            projects, designers, now, self.targets, self.statuses, self.policy.timezone
        )

        allowed, window_status = self._work_window_allows_distribution(now)
        if not allowed:
            result = AutomationResult(
                cycle_id=cycle_id,
                status="skipped",
                message=f"Distribuição não executada: {window_status}.",
                snapshot=snapshot,
                suggestions=pd.DataFrame(),
                distribution_summary=pd.DataFrame(),
            )
            if self.audit:
                self.audit.finish_cycle(cycle_id, now, "skipped", 0, 0, result.message)
            return result

        if productive_minutes_remaining(now, self.policy.timezone) <= 0:
            result = AutomationResult(
                cycle_id=cycle_id,
                status="skipped",
                message="Distribuição não executada: expediente encerrado.",
                snapshot=snapshot,
                suggestions=pd.DataFrame(),
                distribution_summary=pd.DataFrame(),
            )
            if self.audit:
                self.audit.finish_cycle(cycle_id, now, "skipped", 0, 0, result.message)
            return result

        suggestions, summary = suggest_assignments(
            projects,
            snapshot,
            self.targets,
            self.statuses,
            max_new_projects_per_designer=self.policy.max_new_projects_per_designer,
            max_portfolio_posts=self.policy.max_portfolio_posts,
            max_portfolio_projects=self.policy.max_portfolio_projects,
            priority_enabled=self.policy.priority_enabled,
            respect_time=True,
            experience_enabled=self.policy.experience_enabled,
            designer_experience=self.policy.designer_experience,
            project_difficulty=self.policy.project_difficulty,
            experience_mode=self.policy.experience_mode,
        )

        # Last defensive check: no duplicate item can appear in one cycle.
        if not suggestions.empty and suggestions["item_id"].astype(str).duplicated().any():
            message = "Falha de segurança: a mesma obra apareceu mais de uma vez no ciclo."
            if self.audit:
                self.audit.finish_cycle(cycle_id, now, "error", len(suggestions), 0, message)
            return AutomationResult(cycle_id, "error", message, snapshot, suggestions, summary, errors=[message])

        if suggestions.empty:
            message = "Nenhuma nova atribuição necessária ou nenhuma obra elegível disponível."
            if self.audit:
                self.audit.finish_cycle(cycle_id, now, "success", 0, 0, message)
            return AutomationResult(cycle_id, "success", message, snapshot, suggestions, summary)

        if mode == "dry-run" or apply_assignment is None:
            if self.audit:
                for _, row in suggestions.iterrows():
                    self.audit.log_assignment(cycle_id, now, row.to_dict(), "suggest", "success")
                self.audit.finish_cycle(cycle_id, now, "success", len(suggestions), 0, "Simulação concluída.")
            return AutomationResult(
                cycle_id,
                "success",
                f"Simulação concluída: {len(suggestions)} atribuição(ões) sugerida(s).",
                snapshot,
                suggestions,
                summary,
                assignments_applied=0,
            )

        applied = 0
        errors: list[str] = []
        for _, row in suggestions.iterrows():
            try:
                apply_assignment(row)
                applied += 1
                if self.audit:
                    self.audit.log_assignment(cycle_id, now, row.to_dict(), "assign", "success")
            except Exception as exc:
                err = f"{row.get('item_id')}: {exc}"
                errors.append(err)
                if self.audit:
                    self.audit.log_assignment(cycle_id, now, row.to_dict(), "assign", "error", reason=str(exc))

        status = "success" if not errors else "partial" if applied else "error"
        message = f"{applied} atribuição(ões) aplicada(s)."
        if errors:
            message += f" {len(errors)} erro(s)."
        if self.audit:
            self.audit.finish_cycle(cycle_id, now, status, len(suggestions), applied, message)
        return AutomationResult(
            cycle_id, status, message, snapshot, suggestions, summary, assignments_applied=applied, errors=errors
        )
