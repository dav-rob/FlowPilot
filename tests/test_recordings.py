import json
import pytest
from flowpilot.catalog import ROOT
from flowpilot.engine import Engine
from flowpilot.recordings import import_recordings
from flowpilot.store import Store


@pytest.mark.asyncio
async def test_bundled_recordings_are_actual_live_exports_and_import_read_only(
    tmp_path,
):
    store = Store(tmp_path / "recordings.sqlite3")
    try:
        directory = ROOT / "examples" / "traces"
        for path in directory.glob("*.json"):
            source = json.loads(path.read_text())
            assert source["mode"] == "live"
            assert source["metrics"]["model_calls"] > 0
            assert source["outcome"]["evidence"]
            assert not any(k.startswith("_") for k in source)
        assert import_recordings(store, directory) == 5
        assert import_recordings(store, directory) == 0
        runs = store.list("run")
        assert all(r["mode"] == "replay" and r["source_mode"] == "live" for r in runs)
        assert all(
            r["source_status"] in ("completed", "awaiting_approval") for r in runs
        )
        pending = next(r for r in runs if r["approvals"])
        engine = Engine(store)
        with pytest.raises(ValueError, match="read-only"):
            await engine.approve(
                pending["id"], pending["approvals"][0]["request_id"], True
            )
    finally:
        store.close()
