"""Tests for JSON-safe serialization helpers."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from app.utils.json_safety import make_json_safe


def test_converts_timedelta_to_hms_string():
    payload = {"start_time": timedelta(hours=10), "end_time": timedelta(hours=18, minutes=30)}
    result = make_json_safe(payload)
    assert result["start_time"] == "10:00:00"
    assert result["end_time"] == "18:30:00"


def test_converts_nested_datetime_decimal_and_time_types():
    payload = {
        "created": datetime(2026, 3, 13, 10, 40, tzinfo=timezone.utc),
        "price": Decimal("19.99"),
        "values": [date(2026, 3, 13), time(8, 15), {"delta": timedelta(seconds=30)}],
    }
    result = make_json_safe(payload)

    assert result["created"] == "2026-03-13T10:40:00+00:00"
    assert result["price"] == "19.99"
    assert result["values"][0] == "2026-03-13"
    assert result["values"][1] == "08:15:00"
    assert result["values"][2]["delta"] == "00:00:30"
