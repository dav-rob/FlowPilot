"""Load explicitly labelled recordings without invoking classifiers, models or tools."""

import copy
import json
from pathlib import Path
from .store import now


def import_recordings(store, directory):
    imported = 0
    for path in sorted(Path(directory).glob("*.json")):
        source = json.loads(path.read_text(encoding="utf-8"))
        if source.get("mode") not in ("live", "simulation") or source.get(
            "status"
        ) not in ("completed", "awaiting_approval", "failed", "cancelled"):
            raise ValueError(f"{path.name}: not a terminal live/simulation recording")
        if not isinstance(source.get("events"), list) or not source.get("id"):
            raise ValueError(f"{path.name}: invalid recording")
        rid = "recording-" + source["id"]
        if store.get("run", rid):
            continue
        run = copy.deepcopy(source)
        run.update(
            id=rid,
            mode="replay",
            status="completed",
            source_run_id=source["id"],
            source_mode=source["mode"],
            source_status=source["status"],
            recording_file=path.name,
            imported_at=now(),
        )
        run["replay_note"] = (
            f"Recorded {source['mode']} execution from {source['created_at']}; source status: {source['status']}. No model or tool calls were made during import. Approvals are read-only and metrics belong to the original run."
        )
        for proposal in run.get("approvals", []):
            proposal["read_only"] = True
        store.put("run", run)
        imported += 1
    return imported
