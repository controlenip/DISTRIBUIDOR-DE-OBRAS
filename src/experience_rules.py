from __future__ import annotations

from .name_utils import normalize_text

EXPERIENCE_LEVELS = ["Menos experiente", "Intermediário", "Experiente"]
DIFFICULTY_LEVELS = ["Fácil", "Médio", "Difícil"]
EXPERIENCE_MODES = ["Preferencial", "Estrito"]

_EXPERIENCE_RANK = {
    "menos experiente": 1,
    "junior": 1,
    "júnior": 1,
    "iniciante": 1,
    "intermediario": 2,
    "intermediário": 2,
    "pleno": 2,
    "experiente": 3,
    "senior": 3,
    "sênior": 3,
}

_DIFFICULTY_RANK = {
    "facil": 1,
    "fácil": 1,
    "simples": 1,
    "medio": 2,
    "médio": 2,
    "intermediario": 2,
    "intermediário": 2,
    "dificil": 3,
    "difícil": 3,
    "complexo": 3,
}


def normalize_experience_label(value: object) -> str:
    key = normalize_text(value)
    rank = _EXPERIENCE_RANK.get(key, 2)
    return EXPERIENCE_LEVELS[rank - 1]


def normalize_difficulty_label(value: object) -> str:
    key = normalize_text(value)
    rank = _DIFFICULTY_RANK.get(key, 2)
    return DIFFICULTY_LEVELS[rank - 1]


def experience_rank(value: object) -> int:
    return EXPERIENCE_LEVELS.index(normalize_experience_label(value)) + 1


def difficulty_rank(value: object) -> int:
    return DIFFICULTY_LEVELS.index(normalize_difficulty_label(value)) + 1


def match_penalty(experience: object, difficulty: object, mode: str = "Preferencial") -> tuple[int, int] | None:
    """Return a sortable penalty for designer/project matching.

    Smaller is better. In strict mode, a project harder than the designer's level
    is rejected. In preferential mode it is allowed only as fallback and receives
    a large first-component penalty. Exact level matches are preferred so easy
    work tends toward less-experienced designers and hard work toward experienced
    designers.
    """
    exp_rank = experience_rank(experience)
    diff_rank = difficulty_rank(difficulty)
    normalized_mode = str(mode or "Preferencial").strip().casefold()

    if normalized_mode == "estrito" and diff_rank > exp_rank:
        return None

    too_hard = 1 if diff_rank > exp_rank else 0
    distance = abs(exp_rank - diff_rank)
    return too_hard, distance
