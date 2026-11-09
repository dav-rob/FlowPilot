# Recorded live showcases

These five JSON files contain actual completed FlowPilot CLI investigations against the supplied synthetic dataset, recorded on 9 November 2026. Classification used Antigravity Flash low and investigation used Flash medium. They contain public run exports, not ground truth or scripted presenter paths.

They are curated demonstrations chosen after integration fixes. They are **not** a held-out benchmark and do not represent the success rate of all development attempts. Earlier failed attempts remain in local development history. Tool errors and corrective actions within each recording are preserved.

Load the recordings as read-only replays, without making model or tool calls:

```sh
.venv/bin/python -m flowpilot --import-recordings
```

Open Run history. Imported entries are labelled Recorded replay, retain the source mode/status and original metrics, and cannot execute pending approvals. Start a new Live AI investigation to run a case again.

All businesses, people, bank details, records and policy content are synthetic. No CLI authentication data, raw provider transcripts or approval tokens are included.
