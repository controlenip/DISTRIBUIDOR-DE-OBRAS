from datetime import datetime
from zoneinfo import ZoneInfo

from src.work_schedule import productive_minutes_elapsed, productive_minutes_remaining

TZ = ZoneInfo("America/Fortaleza")


def dt(hour, minute=0):
    return datetime(2026, 9, 30, hour, minute, tzinfo=TZ)


def test_start_of_day():
    assert productive_minutes_elapsed(dt(8)) == 0
    assert productive_minutes_remaining(dt(8)) == 528


def test_noon():
    assert productive_minutes_elapsed(dt(12)) == 240
    assert productive_minutes_remaining(dt(12)) == 288


def test_interval_does_not_count():
    assert productive_minutes_elapsed(dt(12, 45)) == 240


def test_end_of_day():
    assert productive_minutes_elapsed(dt(18)) == 528
    assert productive_minutes_remaining(dt(18)) == 0
