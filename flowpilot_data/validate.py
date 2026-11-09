"""Dataset validation: schema, quotas, references, evidence replay through the public tool API, leakage and split isolation."""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from .docs import FLUFF_BANK, _GREET
from .planning import cell_quotas
from .schema import CATEGORIES, DIFFICULTIES, GROUPS, OUTCOMES, PARTITIONS, PREFIX_TO_TABLE, TABLES
from .tools import EnterpriseEnv, EnterpriseSession
from .util import canonical, read_json, read_jsonl

ID_RE = re.compile(r"\b([A-Z]{1,4})-([0-9A-F]{8})\b")
EXEMPT_ARGS = {"record_types", "limit", "privileged_only", "query_name", "parameters", "from_version", "to_version", "status", "case_type", "priority"}
TRUTH_KEYS = ["case_id", "partition", "family_id", "variant", "difficulty", "scenario_summary", "facts", "routing", "risk_level", "urgency", "investigation_needed",
              "human_review_required", "expected_outcome", "evidence", "discoverability", "tools", "case_records", "document_quality", "knobs"]
_BOILERPLATE_LINES = set(FLUFF_BANK) | {g for gs in _GREET.values() for g in gs if g} | {"---------- Forwarded message ----------"}


def _doc_texts(data: Path, partition: str, case: dict) -> str:
    docs = [case["document"]] + case["attachments"]
    return "\n".join((data / "partitions" / partition / d["path"]).read_text(encoding="utf-8") for d in docs)


def _mask(text: str) -> str:
    t = ID_RE.sub("", text)
    t = re.sub(r"[A-Z]{2}-\d+|\d[\d,\.\-/: ]*\d|\d", "#", t)
    t = re.sub(r"\b[A-Z][a-z]+(?: [A-Z][a-z]+)+\b", "NAME", t)
    return t.lower()


def _shingles(text: str, k: int = 4) -> set:
    w = re.findall(r"[a-z#]+", _mask(text))
    return {" ".join(w[i:i + k]) for i in range(max(0, len(w) - k + 1))}


def _body_only(text: str) -> str:
    """Drop headers, greetings, signatures, labelled field lines and generic filler so boilerplate does not dominate similarity."""
    parts = text.split("\n\n")
    body = "\n\n".join(parts[1:-1]) if len(parts) > 3 else text
    keep = [l for l in body.split("\n") if l.strip() not in _BOILERPLATE_LINES and not re.match(r"^[A-Za-z ]{3,25}: ", l) and not l.startswith("|")]
    return "\n".join(keep)


def replay_path(session: EnterpriseSession, path: dict, visible_text: str, errors: list, label: str, retries: int = 3) -> set[str]:
    seen_text, found = visible_text.lower(), set()
    for step in path["steps"]:
        tool, args = step["tool"], step["args"]
        for k, v in args.items():
            if k in EXEMPT_ARGS:
                continue
            for x in (v if isinstance(v, list) else [v]):
                if isinstance(x, str) and x.lower() not in seen_text:
                    errors.append(f"{label}: argument {k}={x!r} of {tool} is neither in the rendered input nor in earlier tool output")
        res = None
        for _ in range(retries):
            res = session.call(tool, **args)
            if res["ok"] or res["error"]["code"] != "SERVICE_UNAVAILABLE" or not res["error"].get("retryable"):
                break
        exp = step.get("expect_error")
        if exp:
            if res["ok"] or res["error"]["code"] != exp:
                errors.append(f"{label}: step {tool}({args}) expected error {exp}, got {res}")
                return found
            blob = json.dumps(res["error"], sort_keys=True)
        elif not res["ok"]:
            errors.append(f"{label}: step {tool}({args}) failed: {res['error']['code']}")
            return found
        else:
            blob = json.dumps(res["data"], sort_keys=True)
        seen_text += "\n" + blob.lower()
        found |= set(m.group(0) for m in ID_RE.finditer(blob))
    return found


def forbidden_tokens(truths: list[dict]) -> list[str]:
    toks = {t["family_id"] for t in truths} | {t["variant"] for t in truths} | set(OUTCOMES) | {"showcase", "ground_truth", "family_id", "expected_outcome",
                                                                                              "abstain_expected", "required_groups", "should_escalate"}
    toks |= {c for c in CATEGORIES} | {"supplier_fraud", "regulatory_compliance", "gdpr_data", "it_asset", "contract_risk"}
    return sorted(t for t in toks if len(t) > 5)


def validate(root: str | Path = ".", replay_all: bool = True, partial: bool = False) -> dict:
    root = Path(root)
    data, ev = root / "data", root / "evaluation"
    errors: list[str] = []
    warnings: list[str] = []
    manifest = read_json(ev / "manifests" / "dataset_manifest.json")
    truths = {p: read_jsonl(ev / "ground_truth" / f"{p}.jsonl") for p in PARTITIONS}
    cases = {p: read_jsonl(data / "partitions" / p / "cases.jsonl") for p in PARTITIONS}
    alltr = [t for p in PARTITIONS for t in truths[p]]
    # --- schema & quotas
    for t in alltr:
        miss = [k for k in TRUTH_KEYS if k not in t]
        if miss:
            errors.append(f"{t.get('case_id')}: truth missing {miss}")
        if t["difficulty"] not in DIFFICULTIES or t["expected_outcome"]["action"] not in OUTCOMES or t["routing"]["primary_category"] not in CATEGORIES:
            errors.append(f"{t['case_id']}: invalid enum")
    size, seed = manifest["size"], manifest["seed"]
    quotas = cell_quotas(size)
    for (p, g), n in ([] if partial else quotas.items()):
        got = sum(1 for t in truths[p] if t["group"] == g)
        if got != n:
            errors.append(f"quota mismatch {p}/{g}: expected {n} got {got}")
    if len(alltr) != size and not partial:
        errors.append(f"total cases {len(alltr)} != size {size}")
    for p in PARTITIONS:
        tid = {t["case_id"] for t in truths[p]}
        cid = {c["case_id"] for c in cases[p]}
        if tid != cid:
            errors.append(f"{p}: truth and public case ids differ")
        for c in cases[p]:
            for d in [c["document"]] + c["attachments"]:
                if not (data / "partitions" / p / d["path"]).exists():
                    errors.append(f"{c['case_id']}: missing file {d['path']}")
    # --- references and cross-partition id disjointness
    ids_by_part: dict[str, set] = {}
    for p in PARTITIONS:
        env = EnterpriseEnv(data / "partitions" / p)
        ids_by_part[p] = set(env.index)
        for rid, (t, rec) in env.index.items():
            for k, v in rec.items():
                for x in (v if isinstance(v, list) else [v]):
                    if isinstance(x, str):
                        for m in ID_RE.finditer(x):
                            if m.group(1) in PREFIX_TO_TABLE and k != "id" and m.group(0) not in env.index:
                                errors.append(f"{p}: dangling reference {rid}.{k} -> {m.group(0)}")
    for a in PARTITIONS:
        for b in PARTITIONS:
            if a < b and ids_by_part[a] & ids_by_part[b]:
                errors.append(f"entity ids shared between {a} and {b}")
    # --- evidence + path replay
    replayed = 0
    for p in PARTITIONS:
        env = EnterpriseEnv(data / "partitions" / p)
        cmap = {c["case_id"]: c for c in cases[p]}
        for t in truths[p]:
            label = t["case_id"]
            for e in t["evidence"]:
                if e["record_id"] not in env.index:
                    errors.append(f"{label}: evidence {e['record_id']} not in partition {p}")
            for cr in t["case_records"]:
                if cr not in env.index:
                    errors.append(f"{label}: case record {cr} missing")
            text = _doc_texts(data, p, cmap[label])
            decisive = {e["record_id"] for e in t["evidence"] if e["role"] == "decisive"}
            covered = set()
            if not replay_all:
                continue
            for i, path in enumerate(t["discoverability"]["paths"]):
                sess = EnterpriseSession(env, label)
                if path.get("blocked"):
                    first = next((s for s in path["steps"] if s["tool"] in {o["tool"] for o in t["discoverability"]["unavailable_services"]}), None)
                    if first and sess.call(first["tool"], **first["args"])["ok"]:
                        errors.append(f"{label}: blocked path {i} did not hit the declared outage")
                    continue
                found = replay_path(sess, path, text, errors, f"{label} path{i}")
                miss = set(path["finds"]) - found
                if miss:
                    errors.append(f"{label} path{i}: claimed evidence not returned by replay: {sorted(miss)}")
                covered |= set(path["finds"]) & found
                replayed += 1
            for rc in t["discoverability"]["required_calls"]:
                res = EnterpriseSession(env, label).call(rc["tool"], **rc["args"])
                if (rc["expect_error"] and (res["ok"] or res["error"]["code"] != rc["expect_error"])) or (not rc["expect_error"] and not res["ok"]):
                    errors.append(f"{label}: required call {rc['tool']} does not behave as declared: {res}")
                for k, v in rc["args"].items():
                    if k not in EXEMPT_ARGS and isinstance(v, str) and v.lower() not in text.lower():
                        errors.append(f"{label}: required call argument {k}={v!r} not in input")
            if decisive - covered:
                errors.append(f"{label}: decisive evidence never discoverable: {sorted(decisive - covered)}")
            if len(t["routing"]["labels"]) != len(set(t["routing"]["labels"])):
                errors.append(f"{label}: duplicate labels")
    # --- leakage scan over all agent-visible files
    bad = forbidden_tokens(alltr)
    leaks = []
    for f in sorted((data / "partitions").rglob("*")):
        if f.is_file() and f.name != ".DS_Store":
            if not re.fullmatch(r"(DOC-[0-9A-F]{10}\.(eml|txt|md|event\.json|events\.jsonl|csv)|[a-z_]+\.jsonl)", f.name):
                errors.append(f"non-neutral filename {f.name}")
            body = f.read_text(encoding="utf-8", errors="replace").lower()
            for tok in bad:
                if tok.lower() in body:
                    leaks.append((str(f.relative_to(data)), tok))
    for p in PARTITIONS:
        env = EnterpriseEnv(data / "partitions" / p)
        for t in truths[p][:: max(1, len(truths[p]) // 12)]:
            sess = EnterpriseSession(env, t["case_id"])
            for path in t["discoverability"]["paths"][:2]:
                if path.get("blocked"):
                    continue
                for step in path["steps"]:
                    blob = json.dumps(sess.call(step["tool"], **step["args"])).lower()
                    for tok in bad:
                        if tok.lower() in blob:
                            leaks.append((f"tool:{step['tool']}", tok))
    errors += [f"leak: {where} contains {tok!r}" for where, tok in sorted(set(leaks))]
    # --- split isolation
    fam_by_part = {p: {t["family_id"] for t in truths[p]} for p in PARTITIONS}
    for a in PARTITIONS:
        for b in PARTITIONS:
            if a < b and fam_by_part[a] & fam_by_part[b]:
                errors.append(f"scenario family shared by {a} and {b}: {sorted(fam_by_part[a] & fam_by_part[b])}")
    sh = {}
    for p in PARTITIONS:
        for c in cases[p]:
            primary = (data / "partitions" / p / c["document"]["path"]).read_text(encoding="utf-8")
            sh[c["case_id"]] = (p, _shingles(_body_only(primary)))
    max_sim, worst = 0.0, None
    items = list(sh.items())
    for i, (ca, (pa, sa)) in enumerate(items):
        for cb, (pb, sb) in items[i + 1:]:
            if pa != pb and sa and sb:
                sim = len(sa & sb) / len(sa | sb)
                if sim > max_sim:
                    max_sim, worst = sim, (ca, cb)
    if max_sim > 0.6:
        errors.append(f"near-duplicate documents across partitions (max masked 4-gram Jaccard {max_sim:.2f}: {worst})")
    dec_sig: dict[str, set] = {}
    for p in PARTITIONS:
        env = EnterpriseEnv(data / "partitions" / p)
        sig = set()
        for t in truths[p]:
            for e in t["evidence"]:
                if e["role"] == "decisive":
                    rec = env.index[e["record_id"]][1]
                    sig.add(re.sub(r"\d+", "#", ID_RE.sub("ID", canonical({k: v for k, v in rec.items() if k not in ("id", "added_on", "requested_at", "performed_at", "received_at")}))))
        dec_sig[p] = sig
    dup_records = sum(len(dec_sig[a] & dec_sig[b]) for a in PARTITIONS for b in PARTITIONS if a < b)
    if dup_records:
        warnings.append(f"{dup_records} masked decisive-evidence record shapes recur across partitions (boilerplate such as shared benign wording); review if high")
    # --- coverage
    for p in PARTITIONS:
        groups = Counter(t["group"] for t in truths[p])
        for g in ([] if partial else GROUPS):
            if groups[g] == 0:
                errors.append(f"{p} lacks group {g}")
        if size >= 250 and not partial and not any(t["routing"]["abstain_expected"] for t in truths[p]):
            errors.append(f"{p} has no abstention case")
    # --- showcase manifest & presenter walkthrough integrity
    sc_file = ev / "showcase" / "showcase_cases.json"
    if not sc_file.exists():
        errors.append("missing evaluation/showcase/showcase_cases.json")
    elif not partial:
        sc = read_json(sc_file)
        sc_cases = sc.get("cases", [])
        if [c.get("workflow") for c in sc_cases] != [g for g in GROUPS if g in ("supplier_fraud", "regulatory_compliance", "gdpr_data", "it_asset", "contract_risk")]:
            errors.append(f"showcase workflows mismatch: {[c.get('workflow') for c in sc_cases]}")
        train_map = {t["case_id"]: t for t in truths["train"]}
        train_pub = {c["case_id"]: c for c in cases["train"]}
        train_env = EnterpriseEnv(data / "partitions" / "train")
        for sc_entry in sc_cases:
            cid = sc_entry.get("case_id")
            if sc_entry.get("partition") != "train" or cid not in train_map:
                errors.append(f"showcase case {cid} not in train partition")
                continue
            if replay_all:
                t = train_map[cid]
                text = _doc_texts(data, "train", train_pub[cid])
                found = replay_path(EnterpriseSession(train_env, cid), {"steps": sc_entry.get("example_path", [])}, text, errors, f"showcase:{cid}")
                dec = {e["record_id"] for e in t["evidence"] if e["role"] == "decisive"}
                if dec - found:
                    errors.append(f"showcase:{cid} example_path missed decisive evidence {sorted(dec - found)}")
    return {"ok": not errors, "errors": errors, "warnings": warnings, "cases": len(alltr), "paths_replayed": replayed,
            "max_cross_partition_similarity": round(max_sim, 3), "most_similar_pair": worst}
