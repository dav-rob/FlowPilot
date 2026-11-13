# Guardrails and their evolution

The rule catalogue distinguishes the business rule, how it is checked, the
response to failure, and whether approval can authorise an exception. The
catalogue is descriptive: the registry, approval authority and runtime remain
the enforcement boundaries. Changing catalogue text alone does not change an
enforced rule.

`flowpilot.assurance.run_guardrail_suite(store)` runs actual controls against
isolated synthetic state and a temporary database. It records expected versus
actual behaviour, permitted controls as well as unsafe attempts, per-rule
coverage, duration, a ruleset version, suite version, application revision, implementation digest and
the rule definitions used. Results are appended with new identifiers and never
replace an older measurement. No model provider is called. A scripted responder
exercises the iteration limit and is explicitly labelled as a test double.

The history is a first cut based on repository commits and documented development
observations. It describes unsupported citations, structured-action failures,
approval scope, and the separation of business cases from development attempts.
It does not invent old pass rates, claim unrecorded pre-fix comparisons, or
retroactively attach current rule versions to old executions.

The prompt-injection rule remains explicitly unmeasured by this suite. Runtime
boundary checks and an adversarial reference regression test do not establish
that a model recognises every hostile document or subtle policy issue. Add live
adversarial cases and evaluation comparisons as measured evidence becomes
available; retain both missed unsafe attempts and incorrectly blocked legitimate
work. A high number of blocked actions alone is not evidence of better quality.

Departmental handoff checks also verify that an explicit Privacy outcome opens
only its required review, that a departmental decision makes no business change,
that undecided or declined reviews cannot authorise consequential actions, and
that the standard route does not create unrelated approval workflows.

All approvals here concern synthetic state in a single-operator demo. There is
no claim of production banking compliance, multiuser separation of duties or
universal resistance to prompt injection.
