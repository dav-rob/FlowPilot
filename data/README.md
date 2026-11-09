# Agent-visible data

`partitions/<name>/` holds one self-contained synthetic enterprise environment:

* `cases.jsonl` - incoming cases (opaque ids, received time, document references). No labels.
* `inbox/` - incoming documents and attachments (email, text, markdown, JSON events, JSONL event streams, OCR text, CSV).
* `enterprise/*.jsonl` - business system records queried by the mock tools (`flowpilot_data.tools`).

Everything is fictional. Ground truth is kept outside this directory in `evaluation/`.
