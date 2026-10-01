from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from .name_utils import normalize_text


@dataclass(frozen=True)
class Targets:
    min_posts: int = 25
    target_posts: int = 30
    min_projects: int = 4
    target_projects: int = 5


@dataclass(frozen=True)
class StatusConfig:
    """Operational status rules for the real Microsoft Lists base.

    A project is in the production pool while its Status do projeto is "Em projeto".
    Within that pool, assignee blank = available; assignee filled = already assigned.
    """

    project_pool: Sequence[str] = field(default_factory=lambda: ("Em projeto",))
    completed: Sequence[str] = field(default_factory=lambda: ("Concluído", "Concluido"))

    @staticmethod
    def normalize(value: object) -> str:
        return normalize_text(value)

    def normalized(self, values: Sequence[str]) -> set[str]:
        return {self.normalize(v) for v in values}

    @property
    def project_pool_set(self) -> set[str]:
        return self.normalized(self.project_pool)

    @property
    def completed_set(self) -> set[str]:
        return self.normalized(self.completed)
