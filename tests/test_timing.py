"""Do not substitute CLI duration for provider API latency."""

import pytest
from flowpilot.timing import cli_timing


def test_reported_agy_run_time_is_never_claimed_as_api_time():
    timing = cli_timing(
        "agy", 12.0, {"duration_seconds": 7.25, "duration_api_ms": 1234}
    )
    assert timing["adapter_duration_ms"] == 12000
    assert timing["provider_run_duration_ms"] == 7250
    assert timing["provider_api_duration_ms"] is None
    assert timing["run_timing_source"] == "agy.result.duration_seconds"


def test_claude_keeps_explicit_api_time_separate_from_process_time():
    timing = cli_timing("claude", 12, {"duration_ms": 9500, "duration_api_ms": 8000})
    assert timing["provider_api_duration_ms"] == 8000
    assert timing["provider_run_duration_ms"] == 9500
    assert timing["adapter_duration_ms"] == 12000
    assert timing["api_timing_source"] == "claude.result.duration_api_ms"
    assert "multiple requests" in timing["api_timing_scope"]


@pytest.mark.parametrize("value", [None, -1, True, "123", float("nan"), float("inf")])
def test_invalid_or_missing_api_measurements_stay_unknown(value):
    timing = cli_timing("claude", 12, {"duration_api_ms": value})
    assert timing["provider_api_duration_ms"] is None
    assert timing["api_timing_source"] is None


def test_unreported_api_timing_is_not_estimated_from_wall_time():
    timing = cli_timing("codex", 12)
    assert timing["provider_api_duration_ms"] is None
    assert timing["provider_run_duration_ms"] is None
    assert timing["adapter_duration_ms"] == 12000
