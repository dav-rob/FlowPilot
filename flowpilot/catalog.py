"""Public inbox access. No evaluation fixtures or ground truth are loaded here."""

from __future__ import annotations
import json
import re
from pathlib import Path
from flowpilot_data.util import read_jsonl

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = [
    {
        "id": "supplier_fraud",
        "name": "Supplier fraud",
        "description": "Verify invoices, bank changes and payment requests.",
        "icon": "ShieldCheck",
        "color": "violet",
    },
    {
        "id": "regulatory_compliance",
        "name": "Policy & compliance",
        "description": "Turn new obligations into evidenced system audits.",
        "icon": "Scale",
        "color": "blue",
    },
    {
        "id": "gdpr_data",
        "name": "Personal data requests",
        "description": "Find customer data, identity checks and legal holds.",
        "icon": "Fingerprint",
        "color": "teal",
    },
    {
        "id": "it_asset",
        "name": "IT asset investigation",
        "description": "Resolve inventory anomalies and security concerns.",
        "icon": "Server",
        "color": "orange",
    },
    {
        "id": "contract_risk",
        "name": "Contract risk",
        "description": "Assess amendments across finance, legal and privacy.",
        "icon": "FileCheck2",
        "color": "pink",
    },
]
# Only public presenter selection metadata; never investigation paths or expected results.
SHOWCASE = {
    "IN-B148DF6144": "supplier_fraud",
    "IN-4988DE6162": "regulatory_compliance",
    "IN-D687B92A2F": "gdpr_data",
    "IN-F8352D982B": "it_asset",
    "IN-8649D7CEB6": "contract_risk",
}


def case_list(partition="train", root=ROOT):
    if partition not in ("train", "validation", "test"):
        raise ValueError("Invalid partition")
    base = Path(root) / "data" / "partitions" / partition
    cases = []
    for c in read_jsonl(base / "cases.jsonl"):
        path = (base / c["document"]["path"]).resolve()
        if not path.is_relative_to(base.resolve()):
            raise ValueError("Document path outside partition")
        document = path.read_text(encoding="utf-8")
        attachments = []
        for a in c.get("attachments", []):
            ap = (base / a["path"]).resolve()
            if not ap.is_relative_to(base.resolve()):
                raise ValueError("Attachment path outside partition")
            attachments.append(
                f"\n\n--- Attachment: {ap.name} ---\n{ap.read_text(encoding='utf-8')}"
            )
        full = document + "".join(attachments)
        json_title = None
        try:
            parsed = json.loads(document)
            if isinstance(parsed, dict):
                json_title = parsed.get("subject") or parsed.get("title")
        except (ValueError, TypeError):
            try:
                parsed = json.loads(document.splitlines()[0])
                if isinstance(parsed, dict):
                    json_title = parsed.get("subject") or parsed.get("title")
            except (ValueError, TypeError, IndexError):
                pass
        subject = re.search(r"^Subject:\s*(.+)", document, re.M | re.I)
        heading = re.search(r"^#{1,3}\s+(.+)", document, re.M)
        title = json_title or (
            (subject or heading).group(1)
            if subject or heading
            else next(
                (
                    s.strip()
                    for s in document.splitlines()
                    if s.strip() and not s.lstrip().startswith(("{", "["))
                ),
                c["case_id"],
            )
        )
        cases.append(
            {
                "case_id": c["case_id"],
                "partition": partition,
                "title": title[:140],
                "preview": re.sub(r"\s+", " ", document)[:220],
                "document": full,
                "media_type": c["document"]["media_type"],
                "received_at": c["received_at"],
                "showcase": c["case_id"] in SHOWCASE,
                "workflow": SHOWCASE.get(c["case_id"]),
            }
        )
    return sorted(cases, key=lambda c: (not c["showcase"], c["case_id"]))


def get_case(case_id, partition="train", root=ROOT):
    return next(
        (c for c in case_list(partition, root) if c["case_id"] == case_id), None
    )
