import { useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  ArrowLeft,
  ArrowUpRight,
  Ban,
  BrainCircuit,
  Check,
  CheckCircle2,
  ChevronDown,
  CircleAlert,
  Clock3,
  Code2,
  Download,
  FileText,
  Fingerprint,
  Flag,
  GitBranch,
  Layers,
  LoaderCircle,
  LockKeyhole,
  MessageSquare,
  Play,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Square,
  Wrench,
  X,
} from "lucide-react";
import type { Approval, Mode, Run, TraceEvent, Workflow } from "./types";
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
  Status,
  WorkflowPath,
} from "./shared";
export default function RunView({
  id,
  initial,
  starting,
  startingMode,
  workflows,
  onOpen,
  onBack,
}: {
  id: string;
  initial: Run | null;
  starting: boolean;
  startingMode: Mode;
  workflows: Workflow[];
  onOpen: (run: Run) => void;
  onBack: () => void;
}) {
  const [run, setRun] = useState<Run | null>(initial);
  const [loading, setLoading] = useState(!initial);
  const [error, setError] = useState("");
  const [action, setAction] = useState("");
  const [actionError, setActionError] = useState("");
  const [version, setVersion] = useState(0);
  const [filter, setFilter] = useState("all");
  const [showJson, setShowJson] = useState(false);
  const revision = useRef(0);
  const currentStatus = run?.status;
  useEffect(() => {
    if (!id) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function refresh() {
      const observedRevision = revision.current;
      try {
        const value = await api<Run>(
          `/runs/${encodeURIComponent(id)}`,
          undefined,
          controller.signal,
        );
        if (controller.signal.aborted) return;
        if (revision.current === observedRevision) {
          setRun(value);
          setError("");
        }
        if (isActive(value.status) || value.status === "awaiting_approval")
          timer = setTimeout(refresh, 1000);
      } catch (e) {
        if (!controller.signal.aborted) {
          setError(errorMessage(e));
          timer = setTimeout(refresh, 3000);
        }
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }
    void refresh();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [id, currentStatus, version]);
  async function mutate(path: string, body: object, name: string) {
    if (action) return;
    setAction(name);
    setActionError("");
    revision.current++;
    try {
      const value = await api<Run>(path, body);
      if (name === "replay") onOpen(value);
      else setRun(value);
    } catch (e) {
      setActionError(errorMessage(e));
    } finally {
      setAction("");
      setVersion((v) => v + 1);
    }
  }
  const events = useMemo(
    () => [...(run?.events ?? [])].sort((a, b) => a.sequence - b.sequence),
    [run?.events],
  );
  const visibleEvents = events.filter(
    (e) =>
      filter === "all" ||
      (filter === "tools"
        ? ["tool_call", "tool_result", "validation"].includes(e.kind)
        : filter === "models"
          ? ["model", "classification", "escalation", "decision"].includes(
              e.kind,
            )
          : filter === "issues"
            ? e.status === "failed" ||
              e.status === "blocked" ||
              e.kind === "error"
            : e.kind === "orchestration"),
  );
  const groups: { key: string; batch?: string; events: TraceEvent[] }[] = [];
  for (const event of visibleEvents) {
    const last = groups[groups.length - 1];
    if (event.batch_id && last?.batch === event.batch_id)
      last.events.push(event);
    else groups.push({ key: event.id, batch: event.batch_id, events: [event] });
  }
  const active = isActive(run?.status);
  const escalation = [...events]
    .reverse()
    .find((event) => event.kind === "escalation");
  const workflowName = (value: string) =>
    workflows.find((w) => w.id === value)?.name ?? readable(value);
  if (starting && !id)
    return (
      <section className="panel starting-panel">
        <div className="starting-orb">
          <Sparkles size={31} />
        </div>
        <div className="eyebrow">INVESTIGATION WORKSPACE</div>
        <h1>Opening your investigation</h1>
        <ModeBadge mode={startingMode} />
        <p>
          The backend is accepting your input. Execution will appear here as
          soon as the run is created.
        </p>
        <Loading text="Submitting to local backend…" />
      </section>
    );
  if (!run)
    return (
      <>
        <button className="text-button back-link" onClick={onBack}>
          <ArrowLeft size={16} /> Back to investigations
        </button>
        {error && (
          <ErrorNotice message={error} retry={() => setVersion((v) => v + 1)} />
        )}
        <section className="panel">
          {loading ? (
            <Loading text="Opening recorded investigation…" />
          ) : (
            <Empty
              title="Investigation unavailable"
              detail="The run could not be loaded. Retry the request or return to investigations."
            />
          )}
        </section>
      </>
    );
  const stage =
    run.outcome || ["completed", "awaiting_approval"].includes(run.status)
      ? 3
      : run.classification
        ? 2
        : active
          ? 1
          : 0;
  return (
    <div className="run-page">
      <div className="run-topline">
        <button className="text-button back-link" onClick={onBack}>
          <ArrowLeft size={15} /> Investigations
        </button>
        <span className="mono small muted">{run.id}</span>
      </div>
      <div className="page-heading run-heading">
        <div>
          <div className="eyebrow">
            {run.source_run_id
              ? "RECORDED REPLAY · NO NEW CALLS"
              : "INVESTIGATION WORKSPACE"}
          </div>
          <h1>{run.title || "Untitled investigation"}</h1>
          <div className="heading-meta">
            <ModeBadge mode={run.mode} />
            <Status status={run.status} />
            <span>
              <Clock3 size={13} />
              {dateTime(run.created_at)}
            </span>
            {run.partition && <span>{readable(run.partition)} partition</span>}
          </div>
        </div>
        <div className="heading-actions">
          <button
            className="button secondary"
            onClick={() => download(`flowpilot-${run.id}.json`, run)}
          >
            <Download size={15} />
            <span>Download trace</span>
          </button>
          {active || run.status === "awaiting_approval" ? (
            <button
              className="button danger-outline"
              disabled={!!action}
              onClick={() =>
                void mutate(
                  `/runs/${encodeURIComponent(id)}/cancel`,
                  {},
                  "cancel",
                )
              }
            >
              {action === "cancel" ? (
                <LoaderCircle className="spin" size={15} />
              ) : (
                <Square size={13} />
              )}{" "}
              Cancel run
            </button>
          ) : (
            <button
              className="button secondary"
              disabled={!!action}
              onClick={() =>
                void mutate(
                  `/runs/${encodeURIComponent(id)}/replay`,
                  {},
                  "replay",
                )
              }
            >
              {action === "replay" ? (
                <LoaderCircle className="spin" size={15} />
              ) : (
                <Play size={14} />
              )}{" "}
              Replay trace
            </button>
          )}
        </div>
      </div>
      {error && (
        <ErrorNotice
          message={`Trace update failed. ${error}`}
          retry={() => setVersion((v) => v + 1)}
        />
      )}
      {actionError && <ErrorNotice message={actionError} />}
      {run.error && <ErrorNotice message={run.error} />}
      {run.mode === "simulation" && (
        <div className="simulation-banner">
          <Flag size={14} />
          <span>
            <strong>Simulation mode</strong> · Deterministic execution. No live
            AI model calls. Consequential actions are simulated.
          </span>
        </div>
      )}
      {run.source_run_id && (
        <div className="replay-banner">
          <RefreshCw size={14} />
          <span>
            Recorded replay of <code>{run.source_run_id}</code>. Source
            investigation:{" "}
            <strong>{readable(run.source_status ?? "unknown")}</strong> ·{" "}
            {readable(run.source_mode ?? "unknown")} mode. Events and metrics
            reflect that execution.
          </span>
        </div>
      )}
      <WorkflowPath stage={stage} />
      <section className="panel classification-panel">
        <div className="classification-icon">
          <BrainCircuit size={24} />
        </div>
        {run.classification ? (
          <>
            <div className="classification-main">
              <div className="eyebrow">INPUT CLASSIFICATION</div>
              <h2>{workflowName(run.classification.primary)}</h2>
              <p>
                {run.classification.rationale ||
                  "No classification rationale reported."}
              </p>
              <div className="classification-tags">
                {run.classification.categories?.map((category) => (
                  <span className="tag" key={category}>
                    {workflowName(category)}
                  </span>
                ))}
                <span className={`badge risk-${run.classification.risk}`}>
                  {readable(run.classification.risk)} risk
                </span>
                <span className="tag">
                  Urgency {run.classification.urgency ?? "Unknown"}
                </span>
              </div>
              <div className="model-line">
                <span className="provider-badge">
                  <Sparkles size={11} />
                  {run.classification.provider || "Unknown provider"}
                </span>
                <span className="mono">
                  {run.classification.model || "Unknown model"}
                </span>
                <span>
                  Confidence{" "}
                  {run.classification.confidence == null
                    ? "Unknown"
                    : `${(run.classification.confidence * 100).toFixed(1)}%`}
                </span>
                <span>
                  Uncertainty{" "}
                  {run.classification.uncertainty == null
                    ? "Unknown"
                    : `${(run.classification.uncertainty * 100).toFixed(1)}%`}
                </span>
              </div>
            </div>
            <div
              className={`escalation-card ${run.classification.escalate || escalation ? "escalated" : ""}`}
            >
              <div>
                <GitBranch size={17} />
                <strong>
                  {escalation
                    ? run.mode === "simulation"
                      ? "Simulated escalation signal"
                      : "Model escalation recorded"
                    : run.classification.escalate
                      ? "Model escalation requested"
                      : "Standard model route"}
                </strong>
              </div>
              <p>
                {escalation?.detail ||
                  run.classification.escalation_reason ||
                  (run.classification.escalate
                    ? "No escalation reason reported."
                    : "Classifier did not request escalation.")}
              </p>
              <span className="small muted">
                {escalation
                  ? "Escalation recorded in the execution trace"
                  : "Routing decision recorded by the classifier"}
              </span>
            </div>
          </>
        ) : (
          <div className="classification-main">
            <div className="eyebrow">INPUT CLASSIFICATION</div>
            <h2>
              {active
                ? "Classifying incoming document"
                : "No classification recorded"}
            </h2>
            <p>
              {active
                ? "Waiting for the backend to return categories, risk, and model routing."
                : "This trace does not contain a classification result."}
            </p>
          </div>
        )}
      </section>
      <div className={`execution-grid ${run.outcome ? "has-outcome" : ""}`}>
        <div className="execution-main">
          <section className="panel timeline-panel">
            <div className="panel-header">
              <div className="panel-title">
                <Activity size={18} />
                <h2>Execution timeline</h2>
                <span className="counter">{events.length}</span>
              </div>
              {active ? (
                <span className="live-update">
                  <span className="live-dot" /> Updating live
                </span>
              ) : (
                <span className="subtle-label">RECORDED EVENTS</span>
              )}
            </div>
            <div
              className="timeline-filters"
              role="group"
              aria-label="Filter trace events"
            >
              {[
                { id: "all", label: "All events" },
                { id: "tools", label: "Tools" },
                { id: "models", label: "Agent & models" },
                { id: "orchestration", label: "Orchestration" },
                { id: "issues", label: "Issues" },
              ].map((item) => (
                <button
                  key={item.id}
                  className={filter === item.id ? "active" : ""}
                  aria-pressed={filter === item.id}
                  onClick={() => setFilter(item.id)}
                >
                  {item.label}
                </button>
              ))}
            </div>
            <div className="timeline">
              {groups.length ? (
                groups.map((group) =>
                  group.batch ? (
                    <details key={group.key} className="event-batch" open>
                      <summary className="batch-heading">
                        <Layers size={13} />
                        <strong>Tool batch</strong>
                        <code>{group.batch}</code>
                        <span>{group.events.length} recorded events</span>
                        <ChevronDown size={12} />
                      </summary>
                      {group.events.map((event) => (
                        <EventCard key={event.id} event={event} />
                      ))}
                    </details>
                  ) : (
                    <div key={group.key} className="event-single">
                      {group.events.map((event) => (
                        <EventCard key={event.id} event={event} />
                      ))}
                    </div>
                  ),
                )
              ) : (
                <Empty
                  title={
                    active && filter === "all"
                      ? "Waiting for the first event"
                      : "No events to show"
                  }
                  detail={
                    active && filter === "all"
                      ? "The timeline updates every second as the backend records execution."
                      : "Events matching this filter will appear here when recorded."
                  }
                />
              )}
            </div>
            {active && events.length > 0 && (
              <div className="timeline-listening">
                <LoaderCircle className="spin" size={14} /> Listening for the
                next recorded event…
              </div>
            )}
          </section>
          <details className="panel document-details">
            <summary>
              <span>
                <FileText size={17} /> Input document{" "}
                <span className="muted small">
                  {run.input?.length.toLocaleString() ?? "Unknown"} characters
                </span>
              </span>
              <ChevronDown size={16} />
            </summary>
            <pre tabIndex={0} className="input-document expanded">
              {run.input ?? "Input document is not available in this trace."}
            </pre>
          </details>
          <section className="panel technical-panel">
            <button
              className="technical-toggle"
              onClick={() => setShowJson((v) => !v)}
              aria-expanded={showJson}
            >
              <span>
                <Code2 size={17} /> Technical trace
              </span>
              <ChevronDown className={showJson ? "rotate" : ""} size={16} />
            </button>
            {showJson && <Json value={run} />}
          </section>
        </div>
        <aside className="outcome-column">
          <section className="panel outcome-panel">
            <div className="panel-header">
              <div className="panel-title">
                <ShieldCheck size={18} />
                <h2>Business outcome</h2>
              </div>
              {run.outcome && (
                <span className={`badge risk-${run.outcome.risk}`}>
                  {readable(run.outcome.risk)}
                </span>
              )}
            </div>
            {run.outcome ? (
              <div className="outcome-content">
                <div className="outcome-code">
                  <CheckCircle2 size={16} />
                  {readable(run.outcome.outcome_code)}
                </div>
                <h3>{run.outcome.summary}</h3>
                <p>{run.outcome.conclusion}</p>
                {run.outcome.departments?.length ? (
                  <div className="classification-tags">
                    {run.outcome.departments.map((d) => (
                      <span className="tag" key={d}>
                        {readable(d)}
                      </span>
                    ))}
                  </div>
                ) : null}
                {run.outcome.requires_approval && (
                  <div className="approval-required">
                    <LockKeyhole size={14} /> Human approval required
                  </div>
                )}
                <div className="outcome-section">
                  <h4>
                    <Fingerprint size={15} /> Supporting evidence{" "}
                    <span>{run.outcome.evidence?.length ?? 0}</span>
                  </h4>
                  {run.outcome.evidence?.length ? (
                    <ul className="evidence-list">
                      {run.outcome.evidence.map((e, i) => (
                        <li key={`${e.record_id}-${i}`}>
                          <code>{e.record_id}</code>
                          <p>{e.note}</p>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="muted small">
                      No evidence references reported.
                    </p>
                  )}
                </div>
                <OutcomeList
                  title="Recommendations"
                  icon={ArrowUpRight}
                  items={run.outcome.recommendations}
                />
                <OutcomeList
                  title="Unresolved questions"
                  icon={MessageSquare}
                  items={run.outcome.unresolved}
                />
                {run.outcome.actions?.length ? (
                  <details className="action-records">
                    <summary>
                      Proposed action details ({run.outcome.actions.length})
                    </summary>
                    <Json value={run.outcome.actions} />
                  </details>
                ) : null}
              </div>
            ) : (
              <div className="outcome-waiting">
                <div className="empty-icon">
                  {active ? (
                    <LoaderCircle size={23} className="spin" />
                  ) : (
                    <ShieldAlert size={23} />
                  )}
                </div>
                <h3>
                  {active ? "Building the evidence" : "No outcome recorded"}
                </h3>
                <p>
                  {active
                    ? "The business summary, evidence, and recommendations will appear when reported by the investigation."
                    : "Review the recorded events and any errors for more detail."}
                </p>
              </div>
            )}
          </section>
          {!!run.approvals?.length && (
            <section className="panel approval-panel">
              <div className="panel-header">
                <div className="panel-title">
                  <LockKeyhole size={17} />
                  <h2>Simulated approvals</h2>
                </div>
              </div>
              <p className="approval-disclaimer">
                Review simulated business actions. These controls do not
                authorize production changes.
              </p>
              {run.approvals.map((approval) => (
                <ApprovalCard
                  key={approval.request_id}
                  approval={approval}
                  busy={!!action}
                  readOnly={
                    run.mode === "replay" ||
                    active ||
                    run.status === "cancelled" ||
                    run.status === "failed"
                  }
                  onDecide={(approve) =>
                    void mutate(
                      `/runs/${encodeURIComponent(id)}/approvals/${encodeURIComponent(approval.request_id)}`,
                      { approve },
                      approval.request_id,
                    )
                  }
                />
              ))}
            </section>
          )}
          <section className="panel run-metrics">
            <div className="panel-header">
              <div className="panel-title">
                <Clock3 size={17} />
                <h2>Run metrics</h2>
              </div>
            </div>
            <div className="metric-stats">
              <div>
                <span>Tool calls</span>
                <strong>{run.metrics?.tool_calls ?? "Unknown"}</strong>
              </div>
              <div>
                <span>Model calls</span>
                <strong>{run.metrics?.model_calls ?? "Unknown"}</strong>
              </div>
              <div>
                <span>Iterations</span>
                <strong>{run.metrics?.iterations ?? "Unknown"}</strong>
              </div>
              <div>
                <span>Duration</span>
                <strong>{duration(run.duration_ms)}</strong>
              </div>
            </div>
            <div className="metrics-bottom">
              <div className="metric-row">
                <span>
                  <ShieldCheck size={13} /> Unsafe actions blocked
                </span>
                <strong>
                  {run.metrics?.unsafe_actions_blocked ?? "Unknown"}
                </strong>
              </div>
              <div className="metric-row">
                <span>Providers</span>
                <strong>
                  {run.metrics?.providers?.length
                    ? run.metrics.providers.join(", ")
                    : "None reported"}
                </strong>
              </div>
              <details>
                <summary>Reported model usage</summary>
                {run.metrics?.usage && Object.keys(run.metrics.usage).length ? (
                  <Metrics
                    value={run.metrics.usage as Record<string, unknown>}
                  />
                ) : (
                  <p className="muted small">No model usage reported.</p>
                )}
              </details>
              <p className="metric-caption">
                Values are reported by the backend. Missing metrics are shown as
                unknown.
              </p>
            </div>
          </section>
        </aside>
      </div>
    </div>
  );
}
function OutcomeList({
  title,
  icon: Icon,
  items,
}: {
  title: string;
  icon: typeof ArrowUpRight;
  items?: string[];
}) {
  return (
    <div className="outcome-section">
      <h4>
        <Icon size={15} />
        {title}
      </h4>
      {items?.length ? (
        <ul className="outcome-list">
          {items.map((item, i) => (
            <li key={i}>{item}</li>
          ))}
        </ul>
      ) : (
        <p className="muted small">None reported.</p>
      )}
    </div>
  );
}
function ApprovalCard({
  approval,
  busy,
  readOnly,
  onDecide,
}: {
  approval: Approval;
  busy: boolean;
  readOnly: boolean;
  onDecide: (approve: boolean) => void;
}) {
  return (
    <div className="approval-card">
      <div className="approval-card-head">
        <code>{approval.tool}</code>
        <Status status={approval.status} />
      </div>
      <p>{approval.justification || "No justification reported."}</p>
      <details>
        <summary>Requested arguments</summary>
        <Json value={approval.args} />
      </details>
      {approval.result !== undefined && (
        <details>
          <summary>Recorded result</summary>
          <Json value={approval.result} />
        </details>
      )}
      {approval.status === "pending" && !readOnly && (
        <div className="approval-actions">
          <button
            disabled={busy}
            className="button approve"
            onClick={() => onDecide(true)}
          >
            <Check size={14} /> Approve simulation
          </button>
          <button
            disabled={busy}
            className="button danger-outline"
            onClick={() => onDecide(false)}
          >
            <X size={14} /> Deny
          </button>
        </div>
      )}
    </div>
  );
}
function EventCard({ event }: { event: TraceEvent }) {
  const orchestration = event.kind === "orchestration";
  const icons: Record<string, typeof Activity> = {
    orchestration: GitBranch,
    classification: BrainCircuit,
    escalation: Sparkles,
    decision: BrainCircuit,
    tool_call: Wrench,
    tool_result: CheckCircle2,
    validation: ShieldCheck,
    outcome: Flag,
    error: CircleAlert,
    approval: LockKeyhole,
    model: Sparkles,
  };
  const Icon =
    event.status === "failed"
      ? CircleAlert
      : event.status === "blocked"
        ? Ban
        : (icons[event.kind] ?? Activity);
  const hasData = event.arguments !== undefined || event.result !== undefined;
  const extraFields = Object.fromEntries(
    Object.entries(event).filter(
      ([key]) =>
        ![
          "id",
          "sequence",
          "kind",
          "title",
          "detail",
          "timestamp",
          "status",
          "tool",
          "arguments",
          "result",
          "provider",
          "model",
          "duration_ms",
          "batch_id",
          "evidence_ids",
        ].includes(key),
    ),
  );
  return (
    <article
      className={`trace-event event-${event.kind} event-status-${event.status} ${orchestration ? "is-orchestration" : ""}`}
    >
      <div className="event-marker">
        {event.status === "running" ? (
          <LoaderCircle className="spin" size={16} />
        ) : (
          <Icon size={16} />
        )}
      </div>
      <div className="event-body">
        <div className="event-topline">
          <span
            className={`event-kind ${orchestration ? "orchestration-label" : ""}`}
          >
            {orchestration
              ? "Orchestration"
              : ["tool_call", "tool_result", "decision", "model"].includes(
                    event.kind,
                  )
                ? `Agent · ${readable(event.kind)}`
                : readable(event.kind)}
          </span>
          <span className="event-time">
            #{event.sequence} <span>·</span>{" "}
            {new Date(event.timestamp).toLocaleTimeString(undefined, {
              hour: "2-digit",
              minute: "2-digit",
              second: "2-digit",
            })}
            {event.duration_ms != null && ` · ${duration(event.duration_ms)}`}
          </span>
        </div>
        <div className="event-title">
          <h3>{event.title}</h3>
          <Status status={event.status} />
        </div>
        {event.tool && <code className="tool-name">{event.tool}</code>}
        {event.detail && <p className="event-detail">{event.detail}</p>}
        {(event.provider || event.model) && (
          <div className="model-line">
            <span className="provider-badge">
              <Sparkles size={10} />
              {event.provider || "Unknown provider"}
            </span>
            <span className="mono">{event.model || "Unknown model"}</span>
          </div>
        )}
        {!!event.evidence_ids?.length && (
          <div className="event-evidence">
            {event.evidence_ids.map((id, i) => (
              <code key={`${id}-${i}`}>
                <Fingerprint size={10} />
                {id}
              </code>
            ))}
          </div>
        )}
        {hasData && (
          <div className="event-data">
            {event.arguments !== undefined && (
              <details>
                <summary>
                  <Code2 size={13} /> Tool arguments <ChevronDown size={12} />
                </summary>
                <Json value={event.arguments} />
              </details>
            )}
            {event.result !== undefined && (
              <details
                open={event.status === "failed" || event.status === "blocked"}
              >
                <summary>
                  <FileText size={13} /> Actual result <ChevronDown size={12} />
                </summary>
                <Json value={event.result} />
              </details>
            )}
          </div>
        )}
        {Object.keys(extraFields).length > 0 && (
          <details className="additional-fields">
            <summary>Additional recorded fields</summary>
            <Json value={extraFields} />
          </details>
        )}
      </div>
    </article>
  );
}
