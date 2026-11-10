# Public repository review — 10 November 2026

Repository: [dav-rob/FlowPilot](https://github.com/dav-rob/FlowPilot).

Before publication, the complete reachable Git history and a separate copy of the publishable working tree were scanned using Gitleaks 8.30.1. The official release checksum was verified before running the scanner. The scan used the standard rules plus a repository-specific TypeSafe JEV credential rule. No credential leaks were found.

The custom JEV rule was positively checked against the local credential with fully redacted scanner output. An additional exact-value check found no occurrence of that credential in publishable files or Git history.

The local `.env` is ignored, untracked and readable only by its owner (mode 0600). Runtime databases, development-agent logs, temporary audit reports, frontend QA files, dependencies and build output are excluded from Git. Only an empty `.env.example` is published. JEV credentials are also stripped from investigation CLI child environments.

The repository deliberately includes synthetic enterprise data and public exports of five recorded live investigations. Content checks found no contact email domains outside the fictional `.example` namespace. The normal Git authorship metadata was retained; the same author identity was already present in the owner's public JobGraph history.

Re-run the secret scan before future publication with Gitleaks installed:

```sh
gitleaks git --redact=100 --log-opts=--all .
```

The checked-in `.gitleaks.toml` extends the standard detector rules with the JEV key format. The local key and detailed private audit output are not included in this report or repository.
