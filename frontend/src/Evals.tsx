import { useEffect, useState } from "react";
import {
  Activity,
  ArrowRight,
  BookOpen,
  CheckCircle2,
  Clock3,
  Code2,
  FlaskConical,
  GitBranch,
  History,
  Layers,
  LoaderCircle,
  Play,
  ShieldCheck,
  TriangleAlert,
  Wrench,
} from "lucide-react";
import type { Config, Evaluation, InboxCase, Run } from "./types";
import { api, dateTime, duration, errorMessage } from "./api";
import { Empty, ErrorNotice, Loading, useResource } from "./shared";
import { Evaluations, Registry, RunHistory } from "./Screens";
import Investigation from "./Investigation";
import { documentKey } from "./business";
import "./evals.css";

type Tab =
  | "overview"
  | "quality"
  | "guardrails"
  | "evolution"
  | "workbench"
  | "history"
  | "registry";
type Rule = {
  id: string;
  version: string;
  name: string;
  rule: string;
  check: string;
  response: string;
  exception_policy: string;
  implementation: unknown;
  coverage: unknown;
};
type TestResult = {
  id: string;
  rule_id: string;
  title: string;
  expected: string;
  actual: string;
  passed: boolean;
  details?: unknown;
};
type Suite = {
  id: string;
  status: string;
  mode: string;
  created_at: string;
  passed: number;
  failed: number;
  total: number;
  results: TestResult[];
  ruleset_version?: string;
  suite_version?: string;
  implementation_digest?: string;
  negative_tests?: number;
  positive_controls?: number;
  coverage?: Record<
    string,
    { tested: boolean; passed: number; failed: number }
  >;
};
type Change = {
  id: string;
  date: string;
  title: string;
  source: string;
  description: string;
  rule_ids: string[];
  before: string;
  after: string;
  evidence: { label: string; path: string }[];
  verification: unknown;
};
type Assurance = {
  ruleset_version?: string;
  rules: Rule[];
  history: Change[];
  suite: Suite | null;
  suites?: Suite[];
};
const tabs: { id: Tab; label: string; icon: typeof Activity }[] = [
  { id: "overview", label: "Overview", icon: Activity },
  { id: "quality", label: "Quality", icon: FlaskConical },
  { id: "guardrails", label: "Guardrails", icon: ShieldCheck },
  { id: "evolution", label: "Evolution", icon: GitBranch },
  { id: "workbench", label: "Test workbench", icon: Code2 },
  { id: "history", label: "Execution history", icon: History },
  { id: "registry", label: "Tool registry", icon: Wrench },
];
function tabFromUrl(fallback?: string): Tab {
  const value =
    fallback || new URLSearchParams(window.location.search).get("evals");
  return tabs.some((t) => t.id === value) ? (value as Tab) : "overview";
}
function description(value: unknown): string {
  if (typeof value === "string") return value;
  if (Array.isArray(value))
    return value.map(description).filter(Boolean).join(" · ");
  if (value && typeof value === "object")
    return Object.entries(value)
      .map(([k, v]) => `${k.replaceAll("_", " ")}: ${description(v)}`)
      .join(" · ");
  return value == null ? "Not recorded" : String(value);
}
function repositoryLink(path: string) {
  if (/^[\w./-]+$/.test(path) && !path.includes(".."))
    return "https://github.com/dav-rob/FlowPilot/blob/main/" + path;
  return undefined;
}

export default function Evals({
  runs,
  config,
  starting,
  onLaunch,
  onOpen,
  initialTab,
}: {
  runs: Run[];
  config: Config | null;
  starting: boolean;
  initialTab?: string;
  onLaunch: (body: object) => void;
  onOpen: (run: Run) => void;
}) {
  const [tab, setTab] = useState<Tab>(() => tabFromUrl(initialTab));
  useEffect(() => {
    setTab(tabFromUrl(initialTab));
  }, [initialTab]);
  const [cases, setCases] = useState<InboxCase[]>([]);
  const [loadingCases, setLoadingCases] = useState(true);
  const [caseError, setCaseError] = useState("");
  const [caseVersion, setCaseVersion] = useState(0);
  const assurance = useResource<Assurance>("/assurance");
  const [testing, setTesting] = useState(false);
  const [testError, setTestError] = useState("");
  const [newSuite, setNewSuite] = useState<Suite | null>(null);
  const [selectedSuite, setSelectedSuite] = useState("");
  const [ruleFilter, setRuleFilter] = useState("all");
  useEffect(() => {
    const controller = new AbortController();
    setLoadingCases(true);
    setCaseError("");
    void Promise.allSettled(
      (["train", "validation", "test"] as const).map((partition) =>
        api<{ cases: InboxCase[] }>(
          "/cases?partition=" + partition,
          undefined,
          controller.signal,
        ),
      ),
    ).then((results) => {
      if (controller.signal.aborted) return;
      setCases(
        results.flatMap((r) => (r.status === "fulfilled" ? r.value.cases : [])),
      );
      if (results.some((r) => r.status === "rejected"))
        setCaseError("Some example documents could not be loaded.");
      setLoadingCases(false);
    });
    return () => controller.abort();
  }, [caseVersion]);
  function selectTab(value: Tab) {
    setTab(value);
    window.location.hash = "evals/" + value;
  }
  async function testGuardrails() {
    if (testing) return;
    setTesting(true);
    setTestError("");
    try {
      const recorded = await api<Suite>("/assurance/run", {});
      setNewSuite(recorded);
      setSelectedSuite(recorded.id);
      assurance.reload();
    } catch (error) {
      setTestError(errorMessage(error));
    } finally {
      setTesting(false);
    }
  }
  const live = runs.filter((r) => r.mode === "live");
  const replays = runs.filter((r) => r.mode === "replay");
  const simulated = runs.filter((r) => r.mode === "simulation");
  const documents = new Set(live.map(documentKey)).size;
  const failed = live.filter((r) => r.status === "failed").length;
  const durations = live
    .map((r) => r.duration_ms)
    .filter((n): n is number => typeof n === "number")
    .sort((a, b) => a - b);
  const median = durations.length
    ? durations.length % 2
      ? durations[Math.floor(durations.length / 2)]
      : (durations[durations.length / 2 - 1] +
          durations[durations.length / 2]) /
        2
    : null;
  const models = [...new Set(live.flatMap((r) => r.metrics.providers ?? []))];
  const recordedSuites =
    assurance.data?.suites ??
    (assurance.data?.suite ? [assurance.data.suite] : []);
  const suites =
    newSuite && !recordedSuites.some((item) => item.id === newSuite.id)
      ? [newSuite, ...recordedSuites]
      : recordedSuites;
  const suite = suites.find((item) => item.id === selectedSuite) ?? suites[0];
  const rules = assurance.data?.rules ?? [];
  const changes = assurance.data?.history ?? [];
  const workbench = (
    <div className="evals-workbench" aria-busy={starting}>
      {starting && (
        <p role="status" className="evals-notice">
          <LoaderCircle size={16} className="spin" /> Starting review…
        </p>
      )}
      <Investigation
        cases={cases}
        loading={loadingCases}
        error={caseError}
        retry={() => setCaseVersion((v) => v + 1)}
        config={config}
        onLaunch={(body) => {
          if (!starting) onLaunch({ ...body, purpose: "test" });
        }}
      />
    </div>
  );
  return (
    <div className="evals-page">
      <header className="evals-heading">
        <div>
          <div className="eyebrow">
            QUALITY, CONTROLS & CONTINUOUS IMPROVEMENT
          </div>
          <h1>Evals</h1>
          <p>
            How well documents are handled, whether the rules hold, and what
            improves over time.
          </p>
        </div>
        <span className="evals-environment">
          <FlaskConical size={16} /> Synthetic enterprise environment
        </span>
      </header>
      <nav className="evals-tabs" aria-label="Evals sections">
        {tabs.map(({ id, label, icon: Icon }) => (
          <button
            type="button"
            key={id}
            className={tab === id ? "selected" : ""}
            aria-current={tab === id ? "page" : undefined}
            onClick={() => selectTab(id)}
          >
            <Icon size={16} />
            {label}
          </button>
        ))}
      </nav>
      {tab === "overview" && (
        <>
          <section
            className="panel evals-history-explainer"
            aria-labelledby="evals-records-title"
          >
            <div className="evals-section-heading">
              <div>
                <div className="eyebrow">WHAT IS IN THE RECORD</div>
                <h2 id="evals-records-title">Reviews, recordings and tests</h2>
              </div>
              <Layers size={21} />
            </div>
            <p>
              These records explain the activity behind the demo. A document may
              appear more than once because it was reviewed again, tested, or
              saved as a replay. They are execution attempts—not a count of
              distinct business cases.
            </p>
            <div className="evals-record-grid">
              <article>
                <span className="evals-record-number">{live.length}</span>
                <h3>AI reviews</h3>
                <p>
                  Real model calls on example documents. {documents} distinct
                  document{documents === 1 ? "" : "s"};{" "}
                  {Math.max(0, live.length - documents)} additional attempt
                  {live.length - documents === 1 ? "" : "s"}.
                </p>
                <small>
                  {failed} failed attempt{failed === 1 ? "" : "s"} remain
                  visible rather than being removed.
                </small>
              </article>
              <article>
                <span className="evals-record-number">{replays.length}</span>
                <h3>Saved replays</h3>
                <p>
                  Recorded executions that can be viewed again without another
                  AI call.
                </p>
                <small>
                  Read-only. Replaying does not perform new business actions.
                </small>
              </article>
              <article>
                <span className="evals-record-number">{simulated.length}</span>
                <h3>Simulated reviews</h3>
                <p>
                  Offline tests using deterministic decisions and synthetic
                  enterprise tools.
                </p>
                <small>
                  Useful for exercising the application; not evidence of model
                  performance.
                </small>
              </article>
            </div>
            <div className="evals-notice">
              <BookOpen size={17} />
              <p>
                Execution history includes development attempts. Only scored
                evaluation batches compare results with hidden expected answers.
                “Completed” means an execution finished; it does not establish
                that its findings were correct.
              </p>
            </div>
            <button
              className="text-button"
              onClick={() => selectTab("history")}
            >
              Inspect execution history <ArrowRight size={15} />
            </button>
          </section>
          <div className="evals-purpose-grid">
            <button onClick={() => selectTab("quality")}>
              <FlaskConical size={23} />
              <h3>Did it reach the right result?</h3>
              <p>
                Classification, findings, evidence, tool choices and efficiency
                against expected answers.
              </p>
              <span>
                Quality evaluations <ArrowRight size={15} />
              </span>
            </button>
            <button onClick={() => selectTab("guardrails")}>
              <ShieldCheck size={23} />
              <h3>Did it stay within the rules?</h3>
              <p>
                Approval requirements, prohibited actions, evidence restrictions
                and boundary cases.
              </p>
              <span>
                Guardrail tests <ArrowRight size={15} />
              </span>
            </button>
            <button onClick={() => selectTab("evolution")}>
              <GitBranch size={23} />
              <h3>What changed as we learned?</h3>
              <p>
                The edge case, the change to a control, and the evidence that
                supports it.
              </p>
              <span>
                Evolution history <ArrowRight size={15} />
              </span>
            </button>
          </div>
          <section className="panel evals-runtime-summary">
            <div>
              <Clock3 size={18} />
              <h2>Recorded execution characteristics</h2>
            </div>
            <dl>
              <div>
                <dt>Median AI review duration</dt>
                <dd>{duration(median)}</dd>
              </div>
              <div>
                <dt>Model/provider combinations reported</dt>
                <dd>{models.length}</dd>
              </div>
              <div>
                <dt>AI tool calls recorded</dt>
                <dd>
                  {live.reduce(
                    (total, run) => total + (run.metrics.tool_calls ?? 0),
                    0,
                  )}
                </dd>
              </div>
            </dl>
            <p>
              Includes failed and repeated AI reviews. Detailed model usage and
              reported resource consumption are available in each case’s Open
              trace view; missing cost or token data is not estimated.
            </p>
          </section>
          <div className="evals-workbench-intro">
            <h2>Test workbench</h2>
            <p>
              Choose an example or supply a document. Test activity is kept
              separate from the business dashboard.
            </p>
          </div>
          {workbench}
        </>
      )}
      {tab === "workbench" && workbench}
      {tab === "quality" && (
        <>
          <div className="evals-notice">
            <FlaskConical size={18} />
            <p>
              Quality evaluations compare each document with its hidden expected
              result. Use AI Review to measure model behaviour; simulation
              checks the offline application path. Per-case results link to the
              same execution trace used by the business workspace.
            </p>
          </div>
          <QualityComparison />
          <Evaluations config={config} onOpenRun={onOpen} />
        </>
      )}
      {tab === "history" && <RunHistory onOpen={onOpen} />}
      {tab === "registry" && <Registry />}
      {tab === "guardrails" && (
        <>
          <section className="panel evals-guardrail-intro">
            <div className="evals-section-heading">
              <div>
                <div className="eyebrow">RULE → CHECK → RESPONSE</div>
                <h2>Guardrails</h2>
              </div>
              <button
                className="button primary"
                disabled={testing}
                onClick={() => void testGuardrails()}
              >
                {testing ? (
                  <LoaderCircle size={16} className="spin" />
                ) : (
                  <Play size={15} />
                )}
                {testing ? "Testing controls…" : "Run guardrail tests"}
              </button>
            </div>
            <p>
              Each guardrail defines what is allowed, how it is checked, and
              what happens when the check fails. Some responses require a human
              decision; others prohibit an action even with approval.
            </p>
            <div className="evals-notice">
              <ShieldCheck size={17} />
              <p>
                These tests exercise real application controls in an isolated
                synthetic session. They make no AI calls and do not establish
                how reliably a model recognises every risky document or
                prompt-injection attempt.
              </p>
            </div>
          </section>
          {(testError || assurance.error) && (
            <ErrorNotice
              message={testError || assurance.error}
              retry={assurance.reload}
            />
          )}
          {assurance.loading && !assurance.data && !newSuite ? (
            <Loading text="Loading guardrail rules…" />
          ) : (
            <>
              {suite ? (
                <section className="panel evals-suite">
                  <div className="evals-section-heading">
                    <div>
                      <h2>Recorded control tests</h2>
                      <p>
                        {dateTime(suite.created_at)} · Deterministic tests ·{" "}
                        {suite.total} checks · Rules{" "}
                        {suite.ruleset_version ?? "not recorded"}
                      </p>
                    </div>
                    <span
                      className={
                        "evals-test-badge " +
                        (suite.failed ? "failed" : "passed")
                      }
                    >
                      {suite.failed ? (
                        <TriangleAlert size={15} />
                      ) : (
                        <CheckCircle2 size={15} />
                      )}
                      {suite.passed} passed · {suite.failed} failed
                    </span>
                  </div>
                  <label className="evals-suite-selector">
                    Recorded test run
                    <select
                      value={suite.id}
                      onChange={(event) => setSelectedSuite(event.target.value)}
                    >
                      {suites.map((item) => (
                        <option key={item.id} value={item.id}>
                          {dateTime(item.created_at)} · {item.passed}/
                          {item.total} passed ·{" "}
                          {item.ruleset_version ?? "Version not recorded"}
                        </option>
                      ))}
                    </select>
                  </label>
                  <p className="evals-suite-coverage">
                    {suite.negative_tests ?? "Not recorded"} boundary tests ·{" "}
                    {suite.positive_controls ?? "Not recorded"} permitted-action
                    checks
                    {suite.coverage
                      ? ` · ${Object.values(suite.coverage).filter((item) => item.tested).length}/${Object.keys(suite.coverage).length} rules exercised by this suite`
                      : ""}
                    . Untested rules are not counted as passing.
                  </p>
                  <div className="evals-test-results">
                    {suite.results.map((test) => (
                      <details
                        key={test.id}
                        className={test.passed ? "passed" : "failed"}
                      >
                        <summary>
                          <span className="evals-test-indicator">
                            {test.passed ? (
                              <CheckCircle2 size={17} />
                            ) : (
                              <TriangleAlert size={17} />
                            )}
                          </span>
                          <span>
                            <strong>{test.title}</strong>
                            <small>{test.rule_id}</small>
                          </span>
                          <span className="evals-result-word">
                            {test.passed ? "Pass" : "Fail"}
                          </span>
                        </summary>
                        <div className="evals-test-comparison">
                          <div>
                            <span>Expected</span>
                            <p>{description(test.expected)}</p>
                          </div>
                          <div>
                            <span>Actual</span>
                            <p>{description(test.actual)}</p>
                          </div>
                          {test.details != null && (
                            <p className="evals-test-details">
                              {description(test.details)}
                            </p>
                          )}
                        </div>
                      </details>
                    ))}
                  </div>
                </section>
              ) : (
                <section className="panel">
                  <Empty
                    title="No guardrail suite recorded yet"
                    detail="Run the isolated tests to record expected and actual behaviour. No paid model calls or business changes are made."
                  />
                </section>
              )}
              <section className="evals-rules">
                <div className="evals-section-heading">
                  <div>
                    <h2>Rules and responses</h2>
                    <p>
                      {rules.length} rules · Revision{" "}
                      {assurance.data?.ruleset_version ??
                        rules[0]?.version ??
                        "not recorded"}
                    </p>
                  </div>
                </div>
                <div className="evals-rule-grid">
                  {rules.map((rule) => (
                    <article className="panel evals-rule" key={rule.id}>
                      <div className="evals-rule-title">
                        <ShieldCheck size={18} />
                        <h3>{rule.name}</h3>
                      </div>
                      <small className="evals-rule-id">
                        {rule.id} · {rule.version}
                      </small>
                      <dl>
                        <div>
                          <dt>Rule</dt>
                          <dd>{rule.rule}</dd>
                        </div>
                        <div>
                          <dt>Check</dt>
                          <dd>{rule.check}</dd>
                        </div>
                        <div>
                          <dt>Response</dt>
                          <dd>{rule.response}</dd>
                        </div>
                        <div>
                          <dt>Approval or exception</dt>
                          <dd>{rule.exception_policy}</dd>
                        </div>
                      </dl>
                      <details>
                        <summary>Implementation and test coverage</summary>
                        <p>{description(rule.implementation)}</p>
                        <p>{description(rule.coverage)}</p>
                      </details>
                    </article>
                  ))}
                </div>
              </section>
              <div className="evals-notice evals-gap">
                <TriangleAlert size={19} />
                <p>
                  <strong>Coverage still matters.</strong> A passing
                  deterministic suite does not certify the whole application.
                  Model-based risk recognition and resistance to malicious
                  document instructions need separate, labelled AI evaluations.
                  A high number of blocked actions alone is not a success
                  metric: legitimate work blocked unnecessarily must also be
                  tested.
                </p>
              </div>
            </>
          )}
        </>
      )}
      {tab === "evolution" && (
        <>
          <section className="panel evals-evolution-intro">
            <div className="evals-section-heading">
              <div>
                <div className="eyebrow">
                  EDGE CASE → CHANGE → REGRESSION CHECK
                </div>
                <h2>How the controls evolve</h2>
              </div>
              <GitBranch size={24} />
            </div>
            <p>
              A readable record of what was learned and what changed. Existing
              entries describe documented development fixes and current
              regression coverage. Historical scores are not reconstructed where
              a before-and-after measurement was never recorded.
            </p>
            <p className="evals-evolution-note">
              Changes are reviewed and versioned; the AI does not silently
              rewrite its own rules. An old result stays an old result.
              Rechecking a document creates a new execution.
            </p>
          </section>
          {assurance.error && (
            <ErrorNotice message={assurance.error} retry={assurance.reload} />
          )}
          {assurance.loading && !assurance.data ? (
            <Loading text="Loading evolution history…" />
          ) : (
            <>
              {suites.length > 0 && (
                <section className="panel evals-measured-history">
                  <div className="evals-section-heading">
                    <div>
                      <h2>Recorded guardrail runs</h2>
                      <p>
                        Actual saved results, kept with the rules and
                        implementation they exercised.
                      </p>
                    </div>
                  </div>
                  <div className="evals-measured-runs">
                    {suites.map((item, index) => {
                      const previous = suites[index + 1];
                      const changed = previous
                        ? item.results.filter((result) => {
                            const old = previous.results.find(
                              (r) => r.id === result.id,
                            );
                            return old && old.passed !== result.passed;
                          })
                        : [];
                      return (
                        <article key={item.id}>
                          <div>
                            <strong>{dateTime(item.created_at)}</strong>
                            <small>
                              Rules {item.ruleset_version ?? "not recorded"} ·
                              Test suite {item.suite_version ?? "not recorded"}
                            </small>
                            <small>
                              Implementation{" "}
                              {item.implementation_digest?.slice(0, 12) ??
                                "not recorded"}
                            </small>
                          </div>
                          <div>
                            <span
                              className={
                                item.failed ? "evals-mismatch" : "evals-match"
                              }
                            >
                              {item.passed} passed · {item.failed} failed
                            </span>
                            <small>
                              {previous
                                ? changed.length
                                  ? `${changed.length} shared test result${changed.length === 1 ? "" : "s"} changed since the preceding run`
                                  : "No pass/fail changes among shared tests since the preceding run"
                                : "First recorded run; no earlier measured baseline"}
                            </small>
                          </div>
                          <button
                            className="text-button"
                            onClick={() => {
                              setSelectedSuite(item.id);
                              selectTab("guardrails");
                            }}
                          >
                            View checks <ArrowRight size={13} />
                          </button>
                        </article>
                      );
                    })}
                  </div>
                </section>
              )}
              <label className="evals-history-filter">
                Filter by rule
                <select
                  value={ruleFilter}
                  onChange={(e) => setRuleFilter(e.target.value)}
                >
                  <option value="all">All rules</option>
                  {rules.map((rule) => (
                    <option key={rule.id} value={rule.id}>
                      {rule.name}
                    </option>
                  ))}
                </select>
              </label>
              <div className="evals-evolution-list">
                {changes
                  .filter(
                    (c) =>
                      ruleFilter === "all" || c.rule_ids.includes(ruleFilter),
                  )
                  .map((change) => (
                    <article className="panel evals-change" key={change.id}>
                      <div className="evals-change-marker">
                        <GitBranch size={18} />
                      </div>
                      <div className="evals-change-heading">
                        <span>{change.date}</span>
                        <small>{change.source}</small>
                      </div>
                      <h3>{change.title}</h3>
                      <p>{change.description}</p>
                      <div className="evals-change-comparison">
                        <div>
                          <span>Before</span>
                          <p>{change.before}</p>
                        </div>
                        <div>
                          <span>Change</span>
                          <p>{change.after}</p>
                        </div>
                      </div>
                      <div className="evals-verification">
                        <CheckCircle2 size={16} />
                        <p>{description(change.verification)}</p>
                      </div>
                      <div className="evals-evidence-links">
                        {change.evidence.map((e, i) =>
                          repositoryLink(e.path) ? (
                            <a
                              key={i}
                              href={repositoryLink(e.path)}
                              target="_blank"
                              rel="noreferrer"
                            >
                              <BookOpen size={13} />
                              {e.label}
                            </a>
                          ) : (
                            <span key={i}>
                              {e.label}: {e.path}
                            </span>
                          ),
                        )}
                      </div>
                      <div className="evals-change-rules">
                        {change.rule_ids.map((id) => (
                          <span className="tag" key={id}>
                            {rules.find((r) => r.id === id)?.name ?? id}
                          </span>
                        ))}
                      </div>
                    </article>
                  ))}
              </div>
              {!changes.length && (
                <Empty
                  title="No evolution entries recorded"
                  detail="Document a discovered edge case, the reviewed change and its regression evidence to start the history."
                />
              )}
            </>
          )}
        </>
      )}
    </div>
  );
}

function QualityComparison() {
  const resource = useResource<{ evaluations: Evaluation[] }>(
    "/evaluations",
    () => true,
    5000,
  );
  const [selected, setSelected] = useState("");
  const [scoring, setScoring] = useState(false);
  const [scoreError, setScoreError] = useState("");
  async function scoreSaved() {
    if (scoring) return;
    setScoring(true);
    setScoreError("");
    try {
      const result = await api<Evaluation>("/evaluations/recorded", {});
      setSelected(result.id);
      resource.reload();
    } catch (error) {
      setScoreError(errorMessage(error));
    } finally {
      setScoring(false);
    }
  }
  const evaluations = resource.data?.evaluations ?? [];
  const id = selected || evaluations[0]?.id;
  const detail = useResource<Evaluation>(
    id ? "/evaluations/" + encodeURIComponent(id) : null,
    (evaluation) => ["queued", "running"].includes(evaluation.status),
    1500,
  );
  const resultLabel = (value: unknown) =>
    typeof value === "boolean" ? (value ? "Match" : "Mismatch") : "Not scored";
  const words = (value: unknown) =>
    typeof value === "string" ? value.replaceAll("_", " ") : "Not recorded";
  return (
    <section className="panel evals-quality-comparison">
      <div className="evals-section-heading">
        <div>
          <h2>Expected versus actual</h2>
          <p>
            Individual document results, including the model and time taken.
          </p>
        </div>
        {evaluations.length > 0 && (
          <select
            aria-label="Evaluation to compare"
            value={id ?? ""}
            onChange={(event) => setSelected(event.target.value)}
          >
            {evaluations.map((evaluation) => (
              <option key={evaluation.id} value={evaluation.id}>
                {dateTime(evaluation.created_at)} ·{" "}
                {evaluation.mode === "live" ? "AI Review" : "Simulation"} ·{" "}
                {evaluation.partition} · {evaluation.completed}/
                {evaluation.total} cases
              </option>
            ))}
          </select>
        )}
      </div>
      <button
        className="button secondary"
        disabled={scoring}
        onClick={() => void scoreSaved()}
      >
        <FlaskConical size={15} />
        {scoring ? "Scoring saved reviews…" : "Score saved AI reviews"}
      </button>
      <p>
        Compare the latest saved AI attempt per labelled document with expected
        answers. No new AI or business actions.
      </p>
      {scoreError && <ErrorNotice message={scoreError} />}
      {(resource.error || detail.error) && (
        <ErrorNotice
          message={resource.error || detail.error}
          retry={resource.reload}
        />
      )}
      {resource.loading || (id && detail.loading) ? (
        <Loading text="Loading scored comparisons…" />
      ) : !detail.data?.results.length ? (
        <Empty
          title="No scored document results yet"
          detail="Use the evaluation controls below. Completed document comparisons will appear here; historical executions without scores remain in Execution history."
        />
      ) : (
        <>
          <p className="evals-quality-mode">
            {detail.data.mode === "simulation"
              ? "Simulation: these scores exercise deterministic behaviour and do not measure an AI model."
              : "AI Review: measured against hidden expected answers on synthetic documents."}{" "}
            Missing fields in older evaluations are shown as not recorded.
          </p>
          {detail.data.warning && (
            <p className="evals-notice">{detail.data.warning}</p>
          )}
          <div className="evals-quality-table-wrap">
            <table className="evals-quality-table">
              <thead>
                <tr>
                  <th>Document</th>
                  <th>Expected finding</th>
                  <th>Actual finding</th>
                  <th>Quality checks</th>
                  <th>Time / model</th>
                  <th>
                    <span className="sr-only">Execution details</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {detail.data.results.map((result, i) => (
                  <tr key={String(result.run_id ?? i)}>
                    <td>
                      <strong>
                        {String(
                          result.title ?? result.case_id ?? "Untitled document",
                        )}
                      </strong>
                      <small>{String(result.case_id ?? "")}</small>
                    </td>
                    <td>
                      {words(result.expected_outcome)}
                      <small>
                        Categories:{" "}
                        {Array.isArray(result.expected_categories)
                          ? result.expected_categories.map(words).join(", ")
                          : "Not recorded"}
                      </small>
                    </td>
                    <td>
                      {words(result.actual_outcome ?? result.outcome_code)}
                      <small>
                        Categories:{" "}
                        {Array.isArray(result.actual_categories)
                          ? result.actual_categories.map(words).join(", ")
                          : "Not recorded"}
                      </small>
                      {typeof result.requires_approval === "boolean" && (
                        <small>
                          {result.requires_approval
                            ? "Human approval required"
                            : "No pending action approval"}
                        </small>
                      )}
                    </td>
                    <td>
                      <span
                        className={
                          result.outcome_correct === true
                            ? "evals-match"
                            : result.outcome_correct === false
                              ? "evals-mismatch"
                              : ""
                        }
                      >
                        Finding: {resultLabel(result.outcome_correct)}
                      </span>
                      <small>
                        Routing: {resultLabel(result.primary_correct)}
                      </small>
                      <small>
                        Evidence-grounded result:{" "}
                        {resultLabel(result.grounded_correct)}
                      </small>
                    </td>
                    <td>
                      {duration(
                        typeof result.duration_ms === "number"
                          ? result.duration_ms
                          : null,
                      )}
                      <small>
                        {Array.isArray(result.models) && result.models.length
                          ? result.models.join(" · ")
                          : "Model not recorded"}
                      </small>
                      {typeof result.ruleset_version === "string" && (
                        <small>Rules: {result.ruleset_version}</small>
                      )}
                      {typeof result.application_revision === "string" && (
                        <small>
                          Application: {result.application_revision}
                        </small>
                      )}
                    </td>
                    <td>
                      {typeof result.run_id === "string" && (
                        <a
                          className="text-button"
                          href={"#trace/" + encodeURIComponent(result.run_id)}
                        >
                          Open trace
                          <ArrowRight size={13} />
                        </a>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}
