import { useEffect, useMemo, useState } from "react";
import {
  ArrowRight,
  ArrowUpRight,
  Boxes,
  Check,
  ChevronDown,
  Clock3,
  Code2,
  Download,
  FlaskConical,
  History,
  Layers,
  LoaderCircle,
  Play,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  Wrench,
  X,
} from "lucide-react";
import type { Config, Evaluation, Mode, Partition, Run, Tool } from "./types";
import {
  api,
  dateTime,
  download,
  duration,
  errorMessage,
  isActive,
  readable,
} from "./api";
import {
  Empty,
  ErrorNotice,
  Json,
  Loading,
  Metrics,
  ModeBadge,
  ModePicker,
  Status,
  useResource,
} from "./shared";
export function RunHistory({ onOpen }: { onOpen: (run: Run) => void }) {
  const resource = useResource<{ runs: Run[] }>("/runs", (data) =>
    data.runs.some(
      (run) => isActive(run.status) || run.status === "awaiting_approval",
    ),
  );
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState("all");
  const [status, setStatus] = useState("all");
  const runs = resource.data?.runs ?? [];
  const filtered = runs.filter(
    (r) =>
      (mode === "all" || r.mode === mode) &&
      (status === "all" || r.status === status) &&
      `${r.title} ${r.id} ${r.case_id ?? ""}`
        .toLowerCase()
        .includes(query.toLowerCase()),
  );
  return (
    <div>
      <div className="page-heading">
        <div>
          <div className="eyebrow">THE RECORD OF EVERY DECISION</div>
          <h1>Execution history</h1>
          <p>
            Revisit outcomes, inspect evidence, and replay recorded execution.
          </p>
        </div>
        <button className="button secondary" onClick={resource.reload}>
          <History size={15} /> Refresh history
        </button>
      </div>
      <div className="history-summary">
        <div>
          <span className="summary-icon violet">
            <Layers size={19} />
          </span>
          <span>
            <strong>{resource.data ? runs.length : "—"}</strong>
            <small>Recorded runs</small>
          </span>
        </div>
        <div>
          <span className="summary-icon green">
            <Check size={19} />
          </span>
          <span>
            <strong>
              {resource.data
                ? runs.filter((r) => r.status === "completed").length
                : "—"}
            </strong>
            <small>Completed</small>
          </span>
        </div>
        <div>
          <span className="summary-icon amber">
            <Clock3 size={19} />
          </span>
          <span>
            <strong>
              {resource.data
                ? runs.filter((r) => r.status === "awaiting_approval").length
                : "—"}
            </strong>
            <small>Awaiting approval</small>
          </span>
        </div>
      </div>
      {resource.error && (
        <ErrorNotice message={resource.error} retry={resource.reload} />
      )}
      <section className="panel">
        <div className="filter-bar">
          <label className="search-field">
            <Search size={16} />
            <input
              aria-label="Search run history"
              placeholder="Search investigations or run IDs…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </label>
          <select
            aria-label="Filter run mode"
            value={mode}
            onChange={(e) => setMode(e.target.value)}
          >
            <option value="all">All modes</option>
            <option value="live">Live AI</option>
            <option value="simulation">Simulation</option>
          </select>
          <select
            aria-label="Filter run status"
            value={status}
            onChange={(e) => setStatus(e.target.value)}
          >
            <option value="all">All statuses</option>
            {[
              "queued",
              "running",
              "completed",
              "awaiting_approval",
              "failed",
              "cancelled",
            ].map((s) => (
              <option key={s} value={s}>
                {readable(s)}
              </option>
            ))}
          </select>
        </div>
        {resource.loading ? (
          <Loading text="Loading recorded runs…" />
        ) : !filtered.length ? (
          <Empty
            title={
              runs.length
                ? "No matching investigations"
                : "Your investigation history starts here"
            }
            detail={
              runs.length
                ? "Try a different search or filter."
                : "Start an investigation to build a durable record of decisions and evidence."
            }
          />
        ) : (
          <div className="table-scroll">
            <table className="data-table history-table">
              <thead>
                <tr>
                  <th scope="col">Investigation</th>
                  <th scope="col">Mode</th>
                  <th scope="col">Status</th>
                  <th scope="col">Created</th>
                  <th scope="col">Duration</th>
                  <th scope="col">
                    <span className="sr-only">Open run</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((run) => (
                  <tr key={run.id}>
                    <td>
                      <button
                        className="table-title"
                        onClick={() => onOpen(run)}
                      >
                        {run.title || "Untitled investigation"}
                      </button>
                      <span className="table-subtitle mono">
                        {run.case_id || run.id}
                        {run.source_run_id ? " · Recorded replay" : ""}
                      </span>
                    </td>
                    <td>
                      <ModeBadge mode={run.mode} />
                    </td>
                    <td>
                      <Status status={run.status} />
                    </td>
                    <td className="nowrap muted">{dateTime(run.created_at)}</td>
                    <td className="nowrap muted">
                      {duration(run.duration_ms)}
                    </td>
                    <td>
                      <button
                        className="icon-button"
                        aria-label={`Open ${run.title || run.id}`}
                        onClick={() => onOpen(run)}
                      >
                        <ArrowUpRight size={17} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
export function Registry() {
  const resource = useResource<{ tools: Tool[] }>("/registry");
  const [query, setQuery] = useState("");
  const [domain, setDomain] = useState("all");
  const [permission, setPermission] = useState("all");
  const tools = resource.data?.tools ?? [];
  const domains = [...new Set(tools.map((t) => t.domain))].sort();
  const permissions = [...new Set(tools.map((t) => t.permission))].sort();
  const filtered = useMemo(
    () =>
      tools.filter(
        (t) =>
          (domain === "all" || t.domain === domain) &&
          (permission === "all" || t.permission === permission) &&
          `${t.name} ${t.description} ${t.system}`
            .toLowerCase()
            .includes(query.toLowerCase()),
      ),
    [tools, domain, permission, query],
  );
  return (
    <div>
      <div className="page-heading">
        <div>
          <div className="eyebrow">CAPABILITIES WITH GUARDRAILS</div>
          <h1>Tool registry</h1>
          <p>
            The enterprise tools available to agents, with explicit permissions
            and validated schemas.
          </p>
        </div>
        <span className="heading-chip">
          <Boxes size={16} />
          {resource.data
            ? `${tools.length} registered tools`
            : "Loading registry"}
        </span>
      </div>
      {resource.error && (
        <ErrorNotice message={resource.error} retry={resource.reload} />
      )}
      <div className="registry-layout">
        <aside className="panel domain-sidebar">
          <div className="panel-header">
            <div className="panel-title">
              <SlidersHorizontal size={16} />
              <h2>Domains</h2>
            </div>
          </div>
          <button
            className={domain === "all" ? "active" : ""}
            onClick={() => setDomain("all")}
            aria-pressed={domain === "all"}
          >
            <Layers size={15} />
            <span>All domains</span>
            <small>{tools.length}</small>
          </button>
          {domains.map((d) => (
            <button
              key={d}
              className={domain === d ? "active" : ""}
              onClick={() => setDomain(d)}
              aria-pressed={domain === d}
            >
              <Wrench size={14} />
              <span>{readable(d)}</span>
              <small>{tools.filter((t) => t.domain === d).length}</small>
            </button>
          ))}
          <div className="registry-guardrail">
            <ShieldCheck size={20} />
            <p>
              Permissions and argument validation are enforced by the backend
              registry.
            </p>
          </div>
        </aside>
        <section className="registry-tools">
          <div className="filter-bar registry-filter">
            <label className="search-field">
              <Search size={16} />
              <input
                placeholder="Find a tool or capability…"
                aria-label="Search tools"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
              {query && (
                <button
                  className="icon-button"
                  aria-label="Clear tool search"
                  onClick={() => setQuery("")}
                >
                  <X size={14} />
                </button>
              )}
            </label>
            <select
              value={permission}
              aria-label="Filter tool permission"
              onChange={(e) => setPermission(e.target.value)}
            >
              <option value="all">All permissions</option>
              {permissions.map((p) => (
                <option key={p} value={p}>
                  {readable(p)}
                </option>
              ))}
            </select>
          </div>
          {resource.loading ? (
            <Loading text="Loading enterprise tool registry…" />
          ) : !filtered.length ? (
            <div className="panel">
              <Empty
                title="No tools found"
                detail="Try another search or domain filter."
              />
            </div>
          ) : (
            <>
              <div className="registry-result-count">
                {filtered.length} capabilities <span>·</span>{" "}
                {domain === "all" ? "All domains" : readable(domain)}
              </div>
              <div className="tool-grid">
                {filtered.map((tool) => (
                  <article className="panel tool-card" key={tool.name}>
                    <div className="tool-card-head">
                      <span className="tool-card-icon">
                        <Wrench size={18} />
                      </span>
                      <span className={`badge permission-${tool.permission}`}>
                        {readable(tool.permission)}
                      </span>
                    </div>
                    <h3>{tool.name}</h3>
                    <p>{tool.description}</p>
                    <div className="tool-meta">
                      <span className="tag">{readable(tool.domain)}</span>
                      <span>{tool.system || "Unknown system"}</span>
                    </div>
                    <details>
                      <summary>
                        <Code2 size={14} /> Argument schema{" "}
                        <ChevronDown size={13} />
                      </summary>
                      <Json value={tool.parameters} />
                    </details>
                  </article>
                ))}
              </div>
            </>
          )}
        </section>
      </div>
    </div>
  );
}
export function Evaluations({
  config,
  onOpenRun,
}: {
  config: Config | null;
  onOpenRun?: (run: Run) => void;
}) {
  const resource = useResource<{ evaluations: Evaluation[] }>(
    "/evaluations",
    (data) => data.evaluations.some((e) => isActive(e.status)),
  );
  const [partition, setPartition] = useState<Partition>("test");
  const [mode, setMode] = useState<Mode>("simulation");
  const [limit, setLimit] = useState("5");
  const [selected, setSelected] = useState("");
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState("");
  const detail = useResource<Evaluation>(
    selected ? `/evaluations/${encodeURIComponent(selected)}` : null,
    (e) => isActive(e.status),
  );
  const [opening, setOpening] = useState("");
  const evaluation = detail.data;
  const evaluationLimit =
    typeof config?.limits?.max_evaluation_cases === "number"
      ? Math.min(25, config.limits.max_evaluation_cases)
      : 25;
  const validLimit =
    Number.isInteger(Number(limit)) &&
    Number(limit) >= 1 &&
    Number(limit) <= evaluationLimit;
  const running =
    resource.data?.evaluations.some((e) => isActive(e.status)) ||
    (evaluation && isActive(evaluation.status));
  useEffect(() => {
    if (!selected && resource.data?.evaluations.length)
      setSelected(resource.data.evaluations[0].id);
  }, [resource.data, selected]);
  async function start(e: React.FormEvent) {
    e.preventDefault();
    if (!validLimit || starting || running) return;
    setStarting(true);
    setStartError("");
    try {
      const value = await api<Evaluation>("/evaluations", {
        partition,
        mode,
        limit: Number(limit),
      });
      setSelected(value.id);
      resource.reload();
    } catch (err) {
      setStartError(errorMessage(err));
    } finally {
      setStarting(false);
    }
  }
  async function openRun(id: string) {
    setOpening(id);
    setStartError("");
    try {
      onOpenRun?.(await api<Run>(`/runs/${encodeURIComponent(id)}`));
    } catch (e) {
      setStartError(errorMessage(e));
    } finally {
      setOpening("");
    }
  }
  return (
    <div>
      <div className="page-heading">
        <div>
          <div className="eyebrow">MEASURE WHAT ACTUALLY HAPPENED</div>
          <h1>Evaluation lab</h1>
          <p>
            Run a bounded evaluation against a selected partition and inspect
            every result.
          </p>
        </div>
        <span className="heading-chip">
          <FlaskConical size={16} /> Measured, never estimated
        </span>
      </div>
      {(startError || resource.error) && (
        <ErrorNotice
          message={startError || resource.error}
          retry={resource.error ? resource.reload : undefined}
        />
      )}
      <div className="evaluation-grid">
        <form className="panel evaluation-controls" onSubmit={start}>
          <div className="panel-header">
            <div className="panel-title">
              <SlidersHorizontal size={17} />
              <h2>Configure evaluation</h2>
            </div>
          </div>
          <div className="evaluation-config">
            <label className="field-label" htmlFor="eval-partition">
              Dataset partition
            </label>
            <select
              id="eval-partition"
              value={partition}
              onChange={(e) => setPartition(e.target.value as Partition)}
              disabled={starting}
            >
              <option value="train">Train</option>
              <option value="validation">Validation</option>
              <option value="test">Test</option>
            </select>
            <label className="field-label" htmlFor="eval-limit">
              Case limit <span className="muted">(1–{evaluationLimit})</span>
            </label>
            <input
              id="eval-limit"
              type="number"
              min={1}
              max={evaluationLimit}
              step={1}
              value={limit}
              onChange={(e) => setLimit(e.target.value)}
              required
              disabled={starting}
            />
            <p className="field-hint">
              Sequential, bounded execution. Each case produces an inspectable
              investigation.
            </p>
            <ModePicker value={mode} onChange={setMode} disabled={starting} />
            <div className="eval-notice">
              <ShieldCheck size={16} />
              <p>
                {mode === "simulation"
                  ? "Simulation scores measure deterministic policy behavior. They do not measure live model performance."
                  : "Live evaluations use real configured models on synthetic enterprise cases. Ground truth is isolated from the agent."}
              </p>
            </div>
            <button
              className="button primary"
              type="submit"
              disabled={starting || !!running || !validLimit}
            >
              {starting ? (
                <LoaderCircle className="spin" size={16} />
              ) : (
                <Play size={15} />
              )}{" "}
              {starting
                ? "Starting evaluation…"
                : running
                  ? "Evaluation in progress"
                  : "Start evaluation"}
              {!running && !starting && <ArrowRight size={16} />}
            </button>
          </div>
          <div className="evaluation-history">
            <h3>Recent evaluations</h3>
            {resource.loading ? (
              <Loading text="Loading evaluations…" />
            ) : resource.data?.evaluations.length ? (
              resource.data.evaluations.map((e) => (
                <button
                  key={e.id}
                  type="button"
                  className={`evaluation-history-item ${selected === e.id ? "selected" : ""}`}
                  onClick={() => setSelected(e.id)}
                >
                  <span>
                    <strong>
                      {readable(e.partition)} · {e.total} cases
                    </strong>
                    <small>
                      {dateTime(e.created_at)} ·{" "}
                      {e.mode === "live" ? "Live AI" : "Simulation"}
                    </small>
                  </span>
                  <Status status={e.status} />
                </button>
              ))
            ) : (
              <p className="small muted">No evaluations recorded yet.</p>
            )}
          </div>
        </form>
        <div className="evaluation-results">
          {detail.error && (
            <ErrorNotice message={detail.error} retry={detail.reload} />
          )}
          <section className="panel evaluation-report">
            {detail.loading && selected ? (
              <Loading text="Loading evaluation results…" />
            ) : evaluation ? (
              <>
                <div className="panel-header">
                  <div className="panel-title">
                    <FlaskConical size={18} />
                    <h2>Evaluation results</h2>
                  </div>
                  <button
                    className="icon-button"
                    onClick={() =>
                      download(
                        `flowpilot-evaluation-${evaluation.id}.json`,
                        evaluation,
                      )
                    }
                    aria-label="Download evaluation JSON"
                  >
                    <Download size={17} />
                  </button>
                </div>
                <div className="evaluation-report-body">
                  <div className="eval-report-heading">
                    <div>
                      <h3>{readable(evaluation.partition)} partition</h3>
                      <span className="small muted">
                        {dateTime(evaluation.created_at)}
                      </span>
                    </div>
                    <div>
                      <ModeBadge mode={evaluation.mode} />
                      <Status status={evaluation.status} />
                    </div>
                  </div>
                  <div className="evaluation-progress">
                    <div>
                      <strong>
                        {evaluation.completed}{" "}
                        <span>/ {evaluation.total} cases</span>
                      </strong>
                      <span className="small muted">
                        {isActive(evaluation.status)
                          ? "Polling every second"
                          : readable(evaluation.status)}
                      </span>
                    </div>
                    <progress
                      max={evaluation.total || 1}
                      value={evaluation.completed}
                      aria-label={`${evaluation.completed} of ${evaluation.total} cases completed`}
                    />
                  </div>
                  {evaluation.error && (
                    <ErrorNotice message={evaluation.error} />
                  )}
                  <div className={`mode-explainer ${evaluation.mode}`}>
                    <p>
                      {evaluation.warning ||
                        (evaluation.mode === "simulation"
                          ? "Deterministic simulation results. These metrics do not establish live AI performance."
                          : "Live model evaluation on synthetic cases. Metrics below are returned by the evaluator.")}
                    </p>
                  </div>
                  <h4 className="report-subheading">Reported metrics</h4>
                  <p className="small muted">
                    Primary routing accuracy includes expected abstention.
                    Multilabel match scores the selected categories separately.
                  </p>
                  <Metrics value={evaluation.metrics} />
                  <details className="full-eval-json">
                    <summary>
                      <Code2 size={14} /> Full evaluation JSON
                    </summary>
                    <Json value={evaluation} />
                  </details>
                </div>
              </>
            ) : (
              <Empty
                title="A clear view of performance"
                detail="Start an evaluation or select a previous one. Results and reported metrics will appear here as cases complete."
              />
            )}
          </section>
          {evaluation && (
            <section className="panel per-case-results">
              <div className="panel-header">
                <div className="panel-title">
                  <Layers size={17} />
                  <h2>Per-case results</h2>
                  <span className="counter">
                    {evaluation.results?.length ?? 0}
                  </span>
                </div>
              </div>
              {!evaluation.results?.length ? (
                <Empty
                  title="No case results yet"
                  detail={
                    isActive(evaluation.status)
                      ? "The first completed case will appear here automatically."
                      : "No per-case results were reported."
                  }
                />
              ) : (
                <div className="evaluation-case-list">
                  {evaluation.results.map((result, i) => (
                    <details
                      className="evaluation-case"
                      key={String(result.case_id ?? i)}
                    >
                      <summary>
                        <span>
                          <strong>
                            {String(
                              result.title ??
                                result.case_id ??
                                `Result ${i + 1}`,
                            )}
                          </strong>
                          <small className="mono">
                            {String(result.case_id ?? "Unknown case")}
                          </small>
                        </span>
                        <span>
                          {typeof result.status === "string" && (
                            <Status status={result.status} />
                          )}
                          <ChevronDown size={15} />
                        </span>
                      </summary>
                      <div className="case-result-body">
                        {result.error ? (
                          <ErrorNotice message={String(result.error)} />
                        ) : null}
                        <div className="case-score-grid">
                          {[
                            "primary_correct",
                            "outcome_correct",
                            "grounded_correct",
                          ]
                            .filter((k) => k in result)
                            .map((key) => (
                              <div key={key}>
                                <span>{readable(key)}</span>
                                <strong
                                  className={
                                    result[key] === true
                                      ? "text-green"
                                      : result[key] === false
                                        ? "text-red"
                                        : ""
                                  }
                                >
                                  {typeof result[key] === "boolean"
                                    ? result[key]
                                      ? "Yes"
                                      : "No"
                                    : String(result[key] ?? "Unknown")}
                                </strong>
                              </div>
                            ))}
                        </div>
                        <Json value={result} />
                        {typeof result.run_id === "string" && onOpenRun && (
                          <button
                            className="button secondary"
                            disabled={!!opening}
                            onClick={() =>
                              void openRun(result.run_id as string)
                            }
                          >
                            {opening === result.run_id ? (
                              <LoaderCircle className="spin" size={14} />
                            ) : (
                              <ArrowUpRight size={14} />
                            )}{" "}
                            Open investigation trace
                          </button>
                        )}
                      </div>
                    </details>
                  ))}
                </div>
              )}
            </section>
          )}
        </div>
      </div>
    </div>
  );
}
