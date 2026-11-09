"""Document specification and multi-format rendering (email, plain text, markdown, structured events)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from .noise import apply_noise
from .util import Rng, ts
from . import vocab

FORMATS = [("eml", 0.30), ("txt", 0.22), ("md", 0.16), ("event.json", 0.16), ("events.jsonl", 0.16)]
VOICES = ["formal", "terse", "chatty", "forwarded"]


@dataclass
class Attachment:
    title: str
    lines: list[tuple[str, str]]
    body: str = ""
    kind: str = "scan"  # scan -> OCR style, csv -> tabular, md


@dataclass
class DocSpec:
    sender: str = ""
    to: str = ""
    subject: str = ""
    message_id: str | None = None
    sent_at: str = ""
    paragraphs: list[str] = field(default_factory=list)
    fields: list[tuple[str, str]] = field(default_factory=list)
    attachments: list[Attachment] = field(default_factory=list)
    signature: str = ""
    inject: str | None = None  # adversarial embedded instruction text (placed inside body)
    protect: set = field(default_factory=set)  # words (entity names) exempt from noise so evidence entry points stay readable


@dataclass
class Rendered:
    ext: str
    text: str
    media_type: str
    role: str  # primary | attachment


MEDIA = {"eml": "message/rfc822", "txt": "text/plain", "md": "text/markdown", "event.json": "application/json",
         "events.jsonl": "application/x-ndjson", "csv": "text/csv"}

_GREET = {"formal": ["Dear Team,", "Dear colleagues,", "Good morning,"], "terse": ["Hi,", "Hello -", ""],
          "chatty": ["Hi all,", "Morning!", "Hey there,"], "forwarded": ["Hi,", "FYI - please see below.", "Can someone look at this?"]}
_CLOSE = {"formal": ["Kind regards,", "Yours sincerely,", "With thanks,"], "terse": ["Thanks", "Regards", "Cheers"],
          "chatty": ["Thanks so much!", "Many thanks,", "Speak soon,"], "forwarded": ["Thanks,", "Regards,", "Ta,"]}


def _fields_block(fields, md=False):
    if not fields:
        return ""
    if md:
        return "\n".join(f"| {a} | {b} |" for a, b in [("Field", "Value"), ("---", "---")] + list(fields))
    return "\n".join(f"{a}: {b}" for a, b in fields)


def _signoff(spec: DocSpec, voice: str, rng: Rng) -> str:
    return f"{rng.pick(_CLOSE[voice])}\n{spec.signature}".strip()


def _body(spec: DocSpec, voice: str, rng: Rng, md: bool = False) -> str:
    parts = [rng.pick(_GREET[voice])] + list(spec.paragraphs)
    if spec.inject:
        parts.insert(rng.randrange(1, len(parts) + 1), spec.inject)
    if spec.fields:
        parts.append(_fields_block(spec.fields, md))
    parts.append(_signoff(spec, voice, rng))
    return "\n\n".join(p for p in parts if p)


def render_attachment(att: Attachment, rng: Rng, level: int, protect: frozenset = frozenset()) -> Rendered:
    if att.kind == "csv":
        heads = ",".join(a for a, _ in att.lines)
        vals = ",".join('"%s"' % b.replace('"', "'") for _, b in att.lines)
        return Rendered("csv", f"{heads}\n{vals}\n", MEDIA["csv"], "attachment")
    body = "\n".join([att.title.upper(), "-" * 24] + [f"{a}: {b}" for a, b in att.lines] + ([att.body] if att.body else []))
    if att.kind == "scan":
        body = apply_noise(body, rng, max(level, 1), mode="ocr", protect=protect)
        return Rendered("txt", "[scanned document - OCR text]\n" + body + "\n", MEDIA["txt"], "attachment")
    return Rendered("md", f"# {att.title}\n\n" + _fields_block(att.lines, md=True) + "\n\n" + att.body + "\n", MEDIA["md"], "attachment")


def render_primary(spec: DocSpec, rng: Rng, fmt: str, voice: str, level: int, event_id: str) -> Rendered:
    mode = "typo"
    P = frozenset(w.lower() for w in spec.protect)
    if fmt == "eml":
        hdr = [f"From: {spec.sender}", f"To: {spec.to}", f"Date: {spec.sent_at}", f"Subject: {spec.subject}"]
        if spec.message_id:
            hdr.append(f"Message-ID: <{spec.message_id}>")
        hdr += ["MIME-Version: 1.0", "Content-Type: text/plain; charset=utf-8"]
        body = _body(spec, voice, rng)
        if voice == "forwarded":
            inner = _body(spec, "terse", rng)
            if inner.startswith(("Hi,\n\n", "Hello -\n\n")):
                inner = inner.split("\n\n", 1)[-1]
            body = (f"{rng.pick(_GREET['forwarded'])}\n\n---------- Forwarded message ----------\nFrom: {spec.sender}\n"
                    f"Subject: {spec.subject}\n\n" + inner)
        text = "\n".join(hdr) + "\n\n" + apply_noise(body, rng, level, mode, P)
    elif fmt == "txt":
        head = f"{spec.subject}\nReceived {spec.sent_at} from {spec.sender}\n" + (f"Reference: {spec.message_id}\n" if spec.message_id else "")
        text = head + "\n" + apply_noise(_body(spec, voice, rng), rng, level, mode, P)
    elif fmt == "md":
        head = f"# {spec.subject}\n\n*From:* {spec.sender}  \n*Received:* {spec.sent_at}\n" + (f"*Message reference:* `{spec.message_id}`\n" if spec.message_id else "")
        text = head + "\n" + apply_noise(_body(spec, voice, rng, md=True), rng, level, mode, P)
    elif fmt == "event.json":
        text = json.dumps({"event_id": event_id, "received_at": spec.sent_at, "source": "intake-gateway",
                           "sender": spec.sender, "subject": spec.subject, "message_reference": spec.message_id,
                           "body": apply_noise("\n\n".join(spec.paragraphs + ([spec.inject] if spec.inject else [])), rng, level, mode, P),
                           "attributes": dict(spec.fields), "signature": spec.signature}, indent=2, sort_keys=True) + "\n"
    else:  # events.jsonl
        lines = [{"seq": 1, "event_id": event_id, "ts": spec.sent_at, "kind": "intake", "sender": spec.sender, "subject": spec.subject,
                  "message_reference": spec.message_id}]
        for i, p in enumerate(spec.paragraphs + ([spec.inject] if spec.inject else []), 2):
            lines.append({"seq": i, "kind": "narrative", "text": apply_noise(p, rng, level, mode, P)})
        for a, b in spec.fields:
            lines.append({"seq": len(lines) + 1, "kind": "attribute", "name": a, "value": b})
        text = "\n".join(json.dumps(l, sort_keys=True) for l in lines) + "\n"
    return Rendered(fmt, text, MEDIA[fmt], "primary")


def choose_format(rng: Rng) -> str:
    return rng.weighted(FORMATS)


def choose_voice(rng: Rng) -> str:
    return rng.pick(VOICES)


def fluff(rng: Rng, n: int) -> list[str]:
    """Neutral business filler used to vary document length (not label-bearing)."""
    return rng.sample(FLUFF_BANK, min(n, len(FLUFF_BANK)))


FLUFF_BANK = ["I'm out of office from Thursday so please copy in the shared mailbox.",
            "Apologies for the short notice - this has been sitting in my inbox.",
            "The previous thread is below if useful, though I think most of it is superseded.",
            "Let me know if you need anything else from our side.",
            "This was raised at the weekly operations catch-up but without a clear owner.",
            "Sorry for the formatting, sent from my phone.",
            "Our reference for this is in the subject line; ignore the older one.",
              "We are mid-way through quarter-end so response times may be slower than usual."]
