"""Explicit timing scopes. Missing provider timing is never estimated from CLI overhead."""

import math


def milliseconds(value, *, seconds=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value) or value < 0:
        return None
    return round(value * (1000 if seconds else 1), 3)


def cli_timing(provider, elapsed_seconds, reported=None):
    reported = reported or {}
    api = (
        milliseconds(reported.get("duration_api_ms")) if provider == "claude" else None
    )
    run = (
        milliseconds(reported.get("duration_seconds"), seconds=True)
        if provider == "agy"
        else milliseconds(reported.get("duration_ms")) if provider == "claude" else None
    )
    return {
        "transport": "cli",
        "adapter_duration_ms": milliseconds(elapsed_seconds, seconds=True),
        "provider_run_duration_ms": run,
        "provider_api_duration_ms": api,
        "api_timing_source": (
            "claude.result.duration_api_ms" if api is not None else None
        ),
        "run_timing_source": (
            (
                "agy.result.duration_seconds"
                if provider == "agy"
                else "claude.result.duration_ms"
            )
            if run is not None
            else None
        ),
        "api_timing_scope": (
            "Provider-reported cumulative API time for this CLI execution; may cover multiple requests or retries."
            if api is not None
            else None
        ),
    }
