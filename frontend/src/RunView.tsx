import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  Activity,
  ArrowLeft,
  ArrowUpRight,
  CheckCircle2,
  ChevronDown,
  Clock3,
  Code2,
  Download,
  FileText,
  Fingerprint,
  GitBranch,
  LoaderCircle,
  LockKeyhole,
  MessageSquare,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Square,
  Wrench,
} from "lucide-react";
import type { Mode, Run, TraceEvent, Workflow } from "./types";
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
} from "./shared";
import {
  businessText,
  completedWork,
  describeFailure,
  eventTitle,
  failureSummary,
  outcomeTitle,
  priorityLabel,
  referenceNames,
  resultSummary,
  sanitizeErrorText,
  suppressProvenanceProse,
  workflowDescription,
  type ReferenceNames,
} from "./presentation";
import { CaseRoute } from "./CaseRoute";
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
  const workflowName = (value: string) =>
    workflows.find((w) => w.id === value)?.name ?? readable(value);
  if (starting && !id)
    return (
      <section className="panel starting-panel">
        <div className="starting-orb">
          <Sparkles size={31} />
        </div>
        <div className="eyebrow">CASE REVIEW</div>
        <h1>Starting review</h1>
        <ModeBadge mode={startingMode} />
        <p>
          Submitting document for review. Progress will appear here shortly.
        </p>
        <Loading text="Starting your review…" />
      </section>
    );
  if (!run)
    return (
      <>
        <button className="text-button back-link" onClick={onBack}>
          <ArrowLeft size={16} /> Back to processed
        </button>
        {error && (
          <ErrorNotice message={error} retry={() => setVersion((v) => v + 1)} />
        )}
        <section className="panel">
          {loading ? (
            <Loading text="Opening recorded review…" />
          ) : (
            <Empty
              title="Review unavailable"
              detail="The run could not be loaded. Retry the request or return to cases."
            />
          )}
        </section>
      </>
    );
  const names = referenceNames(run);
  const text = (value?: string) => businessText(value, names);
  const businessProse = (value?: string) =>
    suppressProvenanceProse(businessText(value, names));
  const outcome = run.outcome;
  const classification = run.classification;
  const finalStatus =
    run.mode === "replay" ? (run.source_status ?? run.status) : run.status;
  const work = completedWork(run);
  const failure = finalStatus === "failed" ? describeFailure(run) : null;
  const sanitizedRunError = sanitizeErrorText(run.error);
  const hasErrorEvents = !!run.events?.some(
    (e) => e.kind === "error" && typeof e.detail === "string",
  );
  const sanitizedTrace =
    run.error || (hasErrorEvents && run.events)
      ? {
          ...run,
          ...(run.error ? { error: sanitizedRunError } : {}),
          ...(hasErrorEvents && run.events
            ? {
                events: run.events.map((e) =>
                  e.kind === "error" && typeof e.detail === "string"
                    ? { ...e, detail: sanitizeErrorText(e.detail) }
                    : e,
                ),
              }
            : {}),
        }
      : run;
  const pendingApprovals =
    run.approvals?.filter((a) => a.status === "pending").length ?? 0;
  const latestCheck = [...events]
    .reverse()
    .find((e) => e.kind === "tool_call" || e.kind === "decision");
  return (
    <div className="run-page result-page">
      <button className="text-button back-link" onClick={onBack}>
        <ArrowLeft size={15} /> Processed
      </button>
      <div className="page-heading run-heading">
        <div>
          <div className="eyebrow">CASE FINDINGS</div>
          <h1>{run.title || "Untitled review"}</h1>
          <div className="heading-meta">
            <ModeBadge mode={run.mode} />
            <Status status={finalStatus} />
            <span>
              <Clock3 size={13} />
              {dateTime(run.created_at)}
            </span>
          </div>
        </div>
        {(active || run.status === "awaiting_approval") &&
          run.mode !== "replay" && (
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
              <Square size={13} /> Stop review
            </button>
          )}
      </div>
      {error && (
        <ErrorNotice message={error} retry={() => setVersion((v) => v + 1)} />
      )}
      {actionError && <ErrorNotice message={actionError} />}
      <CaseRoute run={run} />
      {(run.purpose === "test" || run.purpose === "evaluation") && (
        <div className="result-mode-note">
          <Code2 size={16} />
          {run.purpose === "test" ? "Workbench test" : "Evaluation run"} ·
          Excluded from operational totals.
        </div>
      )}
      {run.mode === "simulation" && (
        <div className="result-mode-note">
          <Sparkles size={16} />
          Simulation: these results follow deterministic rules rather than a
          Live API review. Actions are simulated.
        </div>
      )}
      {run.mode === "replay" && (
        <div className="result-mode-note">
          <FileText size={16} />
          Saved review ·{" "}
          {run.source_mode === "live"
            ? "Originally a Live API review."
            : run.source_mode === "simulation"
              ? "Originally a simulation."
              : "Original mode is recorded in the technical details."}{" "}
          Nothing is running or being changed.
        </div>
      )}

      {failure && (
        <section
          className="panel failure-panel"
          aria-labelledby="failure-panel-title"
          aria-live="polite"
        >
          <div className="failure-panel-header">
            <div className="failure-panel-label">
              <ShieldAlert size={18} />
              <span>Failure summary</span>
            </div>
            <div className="failure-panel-badges">
              <span className="badge failure-category-badge">
                {failure.categoryLabel}
              </span>
              <span className="badge failure-provenance-badge">
                {failure.provenanceLabel}
              </span>
            </div>
          </div>
          <h2 id="failure-panel-title">{failure.title}</h2>
          <p className="failure-outcome-status">
            No verified outcome available
          </p>
          <p className="result-lede failure-explanation">
            {failure.explanation}
          </p>
          {failure.recordIds.length > 0 && (
            <div className="failure-record-ids">
              <span>
                Unconfirmed record reference
                {failure.recordIds.length === 1 ? "" : "s"}:
              </span>
              {failure.recordIds.map((recordId) => (
                <code key={recordId}>{recordId}</code>
              ))}
            </div>
          )}
          <div className="failure-meta-grid">
            <div>
              <h3>How this review ran</h3>
              <p>{failure.provenanceDetail}</p>
            </div>
            <div>
              <h3>Next step</h3>
              <p>{failure.nextStep}</p>
            </div>
          </div>
          {(work.reviews > 0 || work.tasks > 0 || pendingApprovals > 0) && (
            <div className="failure-activity-note">
              {(work.reviews > 0 || work.tasks > 0) && (
                <p>
                  Earlier checks recorded:{" "}
                  {[
                    work.reviews > 0
                      ? `${work.reviews} review case${work.reviews === 1 ? "" : "s"} opened`
                      : "",
                    work.tasks > 0
                      ? `${work.tasks} follow-up task${work.tasks === 1 ? "" : "s"} created`
                      : "",
                  ]
                    .filter(Boolean)
                    .join(" · ")}
                  .
                </p>
              )}
              {pendingApprovals > 0 && (
                <p>
                  {pendingApprovals} proposed change
                  {pendingApprovals === 1 ? "" : "s"} cannot be approved because
                  this run failed without an accepted finding.
                </p>
              )}
            </div>
          )}
          <details className="failure-technical-details">
            <summary>Raw technical error</summary>
            {failure.rawError ? (
              <pre className="failure-raw-error" tabIndex={0}>
                {failure.rawError}
              </pre>
            ) : (
              <p className="failure-raw-empty">
                No raw technical error message was recorded for this run.
              </p>
            )}
          </details>
        </section>
      )}

      {(outcome || finalStatus !== "failed") && (
        <div className={`result-overview ${outcome ? "has-result" : ""}`}>
          <section
            className={`panel result-hero ${!outcome ? "result-incomplete" : ""}`}
            aria-labelledby="business-outcome-title"
            aria-live="polite"
          >
            <div className="result-section-label">
              <ShieldCheck size={18} /> Findings, next steps
            </div>
            {outcome ? (
              <>
                <div className="result-headline">
                  <h2 id="business-outcome-title">{outcomeTitle(run)}</h2>
                  <span className={`badge risk-${outcome.risk}`}>
                    {readable(outcome.risk)} risk
                  </span>
                </div>
                <p className="result-lede">
                  {businessProse(outcome.conclusion || outcome.summary)}
                </p>
                {outcome.summary && outcome.summary !== outcome.conclusion && (
                  <details className="result-summary-note">
                    <summary>More about this finding</summary>
                    <p>{businessProse(outcome.summary)}</p>
                  </details>
                )}
                {!!outcome.departments?.length && (
                  <div className="result-owner">
                    <span>Teams to involve</span>
                    {outcome.departments.map((d) => (
                      <span className="tag" key={d}>
                        {readable(d)}
                      </span>
                    ))}
                  </div>
                )}
                {(work.reviews > 0 || work.tasks > 0 || work.applied > 0) && (
                  <div className="result-done">
                    <CheckCircle2 size={16} />
                    <span>
                      {[
                        work.reviews > 0
                          ? `${work.reviews} review case${work.reviews === 1 ? "" : "s"} opened`
                          : "",
                        work.tasks > 0
                          ? `${work.tasks} follow-up task${work.tasks === 1 ? "" : "s"} created`
                          : "",
                        work.applied > 0
                          ? `${work.applied} approved simulated change${work.applied === 1 ? "" : "s"} applied`
                          : "",
                      ]
                        .filter(Boolean)
                        .join(" · ")}
                    </span>
                  </div>
                )}
                {finalStatus !== "failed" &&
                  (pendingApprovals > 0 ||
                    (outcome.requires_approval && !work.applied)) && (
                    <div className="result-approval-note">
                      <LockKeyhole size={16} />
                      {pendingApprovals > 0
                        ? `${pendingApprovals} proposed change${pendingApprovals === 1 ? " needs" : "s need"} your approval below.`
                        : "Approval is required before the proposed changes can be made."}
                    </div>
                  )}
              </>
            ) : (
              <>
                <h2 id="business-outcome-title">
                  {active
                    ? "In progress"
                    : finalStatus === "cancelled"
                      ? "Review stopped"
                      : "No verified outcome available"}
                </h2>
                <p className="result-lede">
                  {active
                    ? "The relevant records are being checked. Findings and recommended next steps will appear here when the review is complete."
                    : finalStatus === "cancelled"
                      ? "This review was stopped. The checks completed so far are saved below."
                      : failureSummary(run.error)}
                </p>
                {active && (
                  <div className="result-progress">
                    <LoaderCircle className="spin" size={16} />
                    {latestCheck
                      ? text(latestCheck.detail) || eventTitle(latestCheck)
                      : "Reading the request and deciding which records to check…"}
                  </div>
                )}
              </>
            )}
          </section>

          {outcome && (
            <section
              className="panel result-next"
              aria-labelledby="recommendations-title"
            >
              <div className="result-section-label">
                <ArrowUpRight size={18} /> Recommendations
              </div>
              <h2 id="recommendations-title">What to do next</h2>
              {outcome.recommendations?.length ? (
                <ol className="result-steps">
                  {outcome.recommendations.map((item, i) => (
                    <li key={i}>
                      <span className="result-step-number" aria-hidden="true">
                        {i + 1}
                      </span>
                      <p>{businessProse(item)}</p>
                    </li>
                  ))}
                </ol>
              ) : (
                <p className="result-no-next">
                  No further steps were recommended in this review.
                </p>
              )}
              {!!outcome.unresolved?.length && (
                <div className="result-questions">
                  <h3>
                    <MessageSquare size={17} /> Questions still to resolve
                  </h3>
                  <ul>
                    {outcome.unresolved.map((item, i) => (
                      <li key={i}>{businessProse(item)}</li>
                    ))}
                  </ul>
                </div>
              )}
            </section>
          )}
        </div>
      )}

      <div className="result-explanation-label">Explore the details</div>
      <a
        className="button secondary"
        href={"#trace/" + encodeURIComponent(run.id)}
      >
        <Activity size={16} /> Open trace <ArrowUpRight size={14} />
      </a>
      {outcome && (
        <Disclosure
          title="Supporting evidence"
          description={`${outcome.evidence?.length ?? 0} supporting record${outcome.evidence?.length === 1 ? "" : "s"}`}
          icon={<Fingerprint size={18} />}
        >
          <p className="result-detail-intro">
            The records behind this conclusion. Reference numbers identify the
            exact sources used.
          </p>
          {outcome.evidence?.length ? (
            <ul className="result-evidence">
              {outcome.evidence.map((e, i) => (
                <li key={`${e.record_id}-${i}`}>
                  <p>{text(e.note)}</p>
                  <code>{e.record_id}</code>
                </li>
              ))}
            </ul>
          ) : (
            <p>No supporting record references were reported.</p>
          )}
        </Disclosure>
      )}

      <Disclosure
        title="About this request"
        description="Request type and initial assessment"
        icon={<FileText size={18} />}
      >
        {classification ? (
          <>
            <div className="result-request-types">
              {classification.categories.map((category) => (
                <div key={category}>
                  <h3>{workflowName(category)}</h3>
                  <p>{workflowDescription(category)}</p>
                </div>
              ))}
            </div>
            <dl className="result-assessment">
              <div>
                <dt>Initial risk</dt>
                <dd>{readable(classification.risk)}</dd>
              </div>
              <div>
                <dt>Priority</dt>
                <dd>{priorityLabel(classification.urgency)}</dd>
              </div>
              <div>
                <dt>Review depth</dt>
                <dd>
                  {classification.escalate ||
                  events.some((e) => e.kind === "escalation")
                    ? "A more detailed review was requested"
                    : "Standard review"}
                </dd>
              </div>
            </dl>
            <p className="result-detail-intro">
              This is the initial assessment of the request. The business
              outcome above reflects what the review found.
            </p>
          </>
        ) : (
          <p>
            {active
              ? "The request is still being assessed."
              : "No initial assessment was recorded."}
          </p>
        )}
      </Disclosure>

      <Disclosure
        title="Checks performed"
        description={`${run.metrics?.tool_calls ?? 0} business check${run.metrics?.tool_calls === 1 ? " or action" : "s and actions"} · ${duration(run.duration_ms)}`}
        icon={<Activity size={18} />}
      >
        <p className="result-detail-intro">
          Follow the checks, the evidence returned and the decisions that
          followed. AI decisions and automatic safeguards are labelled
          separately.
        </p>
        <div
          className="result-event-filters"
          aria-label="Filter checks performed"
        >
          {[
            ["all", "All steps"],
            ["tools", "Record checks"],
            ["models", "AI decisions"],
            ["orchestration", "Automatic steps"],
            ["issues", "Issues"],
          ].map(([value, label]) => (
            <button
              key={value}
              className={filter === value ? "selected" : ""}
              aria-pressed={filter === value}
              onClick={() => setFilter(value)}
            >
              {label}
            </button>
          ))}
        </div>
        <div className="timeline-list">
          {groups.length ? (
            groups.map((group) => (
              <div
                key={group.key}
                className={group.batch ? "result-batch" : "event-single"}
              >
                {group.batch && (
                  <p className="result-batch-label">
                    <GitBranch size={13} /> Checks started together
                  </p>
                )}
                {group.events.map((event) => (
                  <EventCard key={event.id} event={event} names={names} />
                ))}
              </div>
            ))
          ) : (
            <Empty
              title="No steps to show yet"
              detail={
                active
                  ? "This section updates as the review progresses."
                  : "No recorded steps match this filter."
              }
            />
          )}
        </div>
      </Disclosure>

      <Disclosure
        title="Original document"
        description="The information that started this review"
        icon={<FileText size={18} />}
      >
        <pre tabIndex={0} className="input-document expanded">
          {run.input ??
            "The original document is not available in this saved record."}
        </pre>
      </Disclosure>
      <Disclosure
        title="Technical record"
        description="Models, original findings and full execution data"
        icon={<Code2 size={18} />}
      >
        <div className="result-technical-actions">
          <button
            className="button secondary"
            onClick={() => download(`flowpilot-${run.id}.json`, run)}
          >
            <Download size={15} /> Download full record
          </button>
          {!active && run.mode !== "replay" && (
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
              <FileText size={15} /> Open read-only recording
            </button>
          )}
        </div>
        {sanitizedRunError && (
          <div className="error-notice">
            <ShieldAlert size={17} />
            <span>{sanitizedRunError}</span>
          </div>
        )}
        <h3>Execution details</h3>
        <dl className="result-assessment">
          <div>
            <dt>Run ID</dt>
            <dd className="mono">{run.id}</dd>
          </div>
          <div>
            <dt>Data partition</dt>
            <dd>{run.partition ?? "Not recorded"}</dd>
          </div>
          <div>
            <dt>Models used</dt>
            <dd>{run.metrics.providers?.join(", ") || "None recorded"}</dd>
          </div>
        </dl>
        <Metrics value={run.metrics as Record<string, unknown>} />
        <details>
          <summary>Original input classification</summary>
          <Json value={classification} />
        </details>
        <details>
          <summary>Original business report and action records</summary>
          <Json value={outcome} />
        </details>
        <details>
          <summary>Complete execution trace (JSON)</summary>
          <Json value={sanitizedTrace} />
        </details>
      </Disclosure>
    </div>
  );
}

function Disclosure({
  title,
  description,
  icon,
  children,
}: {
  title: string;
  description: string;
  icon: ReactNode;
  children: ReactNode;
}) {
  return (
    <details className="panel result-disclosure">
      <summary>
        <span className="result-disclosure-icon">{icon}</span>
        <span className="result-disclosure-heading">
          <strong>{title}</strong>
          <span>{description}</span>
        </span>
        <ChevronDown className="result-chevron" size={18} />
      </summary>
      <div className="result-disclosure-body">{children}</div>
    </details>
  );
}

export function EventCard({
  event,
  names,
}: {
  event: TraceEvent;
  names: ReferenceNames;
}) {
  const automatic = ["orchestration", "validation", "handoff"].includes(
    event.kind,
  );
  const detail =
    event.kind === "tool_result"
      ? resultSummary(event)
      : event.kind === "classification"
        ? "The request was assessed to identify the relevant business process and priority."
        : event.kind === "escalation"
          ? "The case was referred for more detailed reasoning. The recorded reason is available in the technical details."
          : event.kind === "model"
            ? "The AI reviewed the available information before selecting its next action."
            : event.kind === "orchestration"
              ? "The application prepared this step and enforced the review’s limits and permissions."
              : event.kind === "error"
                ? failureSummary(event.detail)
                : businessText(event.detail, names);
  return (
    <article
      className={`trace-event event-${event.kind} event-status-${event.status} ${automatic ? "is-orchestration" : ""}`}
    >
      <div className="event-marker">
        {event.status === "running" ? (
          <LoaderCircle className="spin" size={16} />
        ) : automatic ? (
          <ShieldCheck size={16} />
        ) : event.tool ? (
          <Wrench size={16} />
        ) : (
          <Sparkles size={16} />
        )}
      </div>
      <div className="event-body">
        <div className="event-topline">
          <span className="event-kind">
            {event.kind === "manual_decision"
              ? "Human decision"
              : event.kind === "approval"
                ? "Approval workflow"
                : automatic
                  ? "Automatic step"
                  : event.tool
                    ? "Business record check"
                    : "Review decision"}
          </span>
          <span className="event-time">
            Step {event.sequence}
            {event.duration_ms != null && ` · ${duration(event.duration_ms)}`}
          </span>
        </div>
        <div className="event-title">
          <h3>{eventTitle(event)}</h3>
          <Status status={event.status} />
        </div>
        {detail && <p className="event-detail">{detail}</p>}
        <details className="result-event-technical">
          <summary>Technical details</summary>
          {event.kind === "error" && event.detail && (
            <p>
              Recorded error: <code>{sanitizeErrorText(event.detail)}</code>
            </p>
          )}
          {event.tool && (
            <p>
              Tool: <code>{event.tool}</code>
            </p>
          )}
          {(event.provider || event.model) && (
            <p>
              Model: {event.provider} / {event.model}
            </p>
          )}
          {event.duration_ms != null && (
            <p>Total step time: {duration(event.duration_ms)}</p>
          )}
          {event.timing && (
            <>
              <h4>Call timing and measurement sources</h4>
              <Json value={event.timing} />
            </>
          )}
          {event.arguments !== undefined && (
            <>
              <h4>Submitted arguments</h4>
              <Json value={event.arguments} />
            </>
          )}
          {event.result !== undefined && (
            <>
              <h4>Returned data</h4>
              <Json value={event.result} />
            </>
          )}
          <details>
            <summary>Full event record</summary>
            <Json
              value={
                event.kind === "error" && typeof event.detail === "string"
                  ? { ...event, detail: sanitizeErrorText(event.detail) }
                  : event
              }
            />
          </details>
        </details>
      </div>
    </article>
  );
}
