from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

WORK_PERIODS = (
    (time(8, 0), time(12, 0)),
    (time(13, 12), time(18, 0)),
)
TOTAL_WORK_MINUTES = 528  # 8h48min


def ensure_local(dt: datetime, timezone: str = "America/Fortaleza") -> datetime:
    tz = ZoneInfo(timezone)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=tz)
    return dt.astimezone(tz)


def _period_datetimes(day: date, timezone: str):
    tz = ZoneInfo(timezone)
    return [
        (
            datetime.combine(day, start, tzinfo=tz),
            datetime.combine(day, end, tzinfo=tz),
        )
        for start, end in WORK_PERIODS
    ]


def productive_minutes_elapsed(now: datetime, timezone: str = "America/Fortaleza") -> int:
    now = ensure_local(now, timezone)
    total = 0.0
    for start, end in _period_datetimes(now.date(), timezone):
        if now <= start:
            continue
        effective_end = min(now, end)
        if effective_end > start:
            total += (effective_end - start).total_seconds() / 60
    return max(0, min(TOTAL_WORK_MINUTES, int(round(total))))


def productive_minutes_remaining(now: datetime, timezone: str = "America/Fortaleza") -> int:
    return max(0, TOTAL_WORK_MINUTES - productive_minutes_elapsed(now, timezone))


def workday_progress(now: datetime, timezone: str = "America/Fortaleza") -> float:
    return productive_minutes_elapsed(now, timezone) / TOTAL_WORK_MINUTES


def current_work_status(now: datetime, timezone: str = "America/Fortaleza") -> str:
    now = ensure_local(now, timezone)
    t = now.time()
    if t < time(8, 0):
        return "Antes do expediente"
    if time(8, 0) <= t < time(12, 0):
        return "Expediente - manhã"
    if time(12, 0) <= t < time(13, 12):
        return "Intervalo"
    if time(13, 12) <= t < time(18, 0):
        return "Expediente - tarde"
    return "Expediente encerrado"


def format_minutes(minutes: int) -> str:
    minutes = max(0, int(minutes))
    hours, mins = divmod(minutes, 60)
    return f"{hours}h{mins:02d}min"


def nominal_minutes_for_workload(
    posts: float,
    projects: float,
    target_posts: int = 30,
    target_projects: int = 5,
) -> int:
    """Estimate workload time using the larger of posts/projects target proportions.

    This is a planning heuristic, not a measured project duration. Once historical
    execution-time data exists, this function can be replaced by a trained estimator.
    """
    post_fraction = max(0.0, float(posts)) / max(1, target_posts)
    project_fraction = max(0.0, float(projects)) / max(1, target_projects)
    return int(round(max(post_fraction, project_fraction) * TOTAL_WORK_MINUTES))


def business_days(start: date, end: date) -> int:
    if end < start:
        return 0
    days = 0
    current = start
    while current <= end:
        if current.weekday() < 5:
            days += 1
        current += timedelta(days=1)
    return days
