import { useEffect, useMemo, useState } from "react";
import {
  ArrowRight,
  ArrowUpRight,
  CheckCircle2,
  ChevronDown,
  Clock3,
  FileCheck2,
  FileText,
  Fingerprint,
  Inbox,
  LoaderCircle,
  Mail,
  RefreshCw,
  Scale,
  Search,
  Server,
  ShieldAlert,
  ShieldCheck,
} from "lucide-react";
import type { InboxCase, Run, Workflow } from "./types";
import { dateTime, isActive } from "./api";
import { Empty, ErrorNotice, Loading } from "./shared";
import { ProcessingRoutes } from "./CaseRoute";
import { toolLabel } from "./presentation";
import {
  businessCases,
  caseState,
  caseStateLabel,
  documentKey,
  filterCases,
  findingTitle,
  readableDocument,
  readyDocuments,
  shortFinding,
  type BusinessCase,
  type CaseView,
} from "./business";

export const areaIcons: Record<string, typeof ShieldCheck> = {
  supplier_fraud: ShieldCheck,
  regulatory_compliance: Scale,
  gdpr_data: Fingerprint,
  it_asset: Server,
  contract_risk: FileCheck2,
};
type Shared = {
  runs: Run[];
  cases: InboxCase[];
  workflows: Workflow[];
  onOpen: (run: Run) => void;
  loading: boolean;
  error: string;
  retry: () => void;
};
type ViewCases = (view?: CaseView, area?: string) => void;

export function CaseState({ entry }: { entry: BusinessCase }) {
  return (
    <span className={"business-state state-" + caseState(entry)}>
      <span />
      {caseStateLabel(entry)}
    </span>
  );
}
function CaseTable({
  entries,
  onOpen,
  workflows,
  limit,
}: {
  entries: BusinessCase[];
  onOpen: (run: Run) => void;
  workflows: Workflow[];
  limit?: number;
}) {
  return (
    <div className="business-table-wrap">
      <table className="business-table">
        <thead>
          <tr>
            <th scope="col">Document / case</th>
            <th scope="col">What FlowPilot found</th>
            <th scope="col">Next step</th>
            <th scope="col">Last checked</th>
          </tr>
        </thead>
        <tbody>
          {entries.slice(0, limit).map((entry) => {
            const { run } = entry;
            return (
              <tr key={entry.key}>
                <td>
                  <button
                    className="business-case-link"
                    onClick={() => onOpen(entry.decisions[0]?.run ?? run)}
                  >
                    {run.title || "Untitled document"}
                    <ArrowUpRight size={14} />
                  </button>
                  <span className="business-case-area">
                    {run.classification?.categories
                      .map(
                        (id) =>
                          workflows.find((w) => w.id === id)?.name ??
                          "Business review",
                      )
                      .join(" · ") || "Request under review"}
                  </span>
                  {run.mode === "replay" && (
                    <span className="saved-example">
                      Saved example · read-only
                    </span>
                  )}
                </td>
                <td>
                  <p>{findingTitle(run)}</p>
                  {run.outcome?.departments?.length ? (
                    <span className="business-case-team">
                      {run.outcome.departments.join(" · ")}
                    </span>
                  ) : null}
                </td>
                <td>
                  <CaseState entry={entry} />
                  {entry.decisions.length > 0 && (
                    <span className="business-case-team">
                      {entry.decisions.length} approval request
                      {entry.decisions.length === 1 ? "" : "s"}
                    </span>
                  )}
                </td>
                <td>
                  <time dateTime={run.created_at}>
                    {dateTime(run.created_at)}
                  </time>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function FinanceOverview({
  runs,
  cases,
  workflows,
  onOpen,
  loading,
  error,
  retry,
  onViewCases,
  onInbox,
}: Shared & { onViewCases: ViewCases; onInbox: () => void }) {
  const entries = useMemo(() => businessCases(runs), [runs]);
  const decisions = entries.flatMap((entry) =>
    entry.decisions.map((decision) => ({ entry, ...decision })),
  );
  const followups = entries.filter((c) => caseState(c) === "followup");
  const active = entries.filter((c) => caseState(c) === "active");
  const ready = readyDocuments(cases, entries);
  const metrics = [
    {
      label: "Waiting for your decision",
      value: decisions.length,
      detail: "Manual approval workflows",
      icon: ShieldCheck,
      tone: "violet",
      action: () => {
        window.location.hash = "approvals";
      },
    },
    {
      label: "Cases needing follow-up",
      value: followups.length,
      detail: "Findings or checks to resolve",
      icon: ShieldAlert,
      tone: "amber",
      action: () => onViewCases("followup"),
    },
    {
      label: "Being checked",
      value: active.length,
      detail: "Documents currently in progress",
      icon: Clock3,
      tone: "blue",
      action: () => onViewCases("active"),
    },
    {
      label: "Ready to process",
      value: ready.length,
      detail: "Available examples · review on demand",
      icon: Inbox,
      tone: "teal",
      action: onInbox,
    },
  ];
  return (
    <div className="finance-workspace">
      <div className="workspace-heading">
        <div>
          <div className="workspace-eyebrow">
            HARBOURLINE MUTUAL / FINANCE OPERATIONS
          </div>
          <h1>Finance overview</h1>
          <p>The decisions, findings and documents that need your attention.</p>
        </div>
        <button className="button primary" onClick={onInbox}>
          <Inbox size={16} />
          Open document inbox
          <ArrowRight size={15} />
        </button>
      </div>
      {error && <ErrorNotice message={error} retry={retry} />}
      <div className="workspace-metrics">
        {metrics.map((m) => (
          <button
            key={m.label}
            className={"workspace-metric metric-" + m.tone}
            onClick={m.action}
          >
            <span className="workspace-metric-top">
              <m.icon size={19} />
              <ArrowUpRight size={14} />
            </span>
            <strong>{loading ? "—" : m.value}</strong>
            <span>{m.label}</span>
            <small>{m.detail}</small>
          </button>
        ))}
      </div>
      <ProcessingRoutes
        standard={
          entries.filter((c) => c.run.business_route?.path === "default").length
        }
        human={
          entries.filter((c) =>
            ["human_review", "human_complete", "declined", "blocked"].includes(
              c.run.business_route?.path ?? "",
            ),
          ).length
        }
        active={active.length}
      />
      <section
        className="workspace-section"
        aria-labelledby="decisions-heading"
      >
        <div className="workspace-section-heading">
          <div>
            <h2 id="decisions-heading">
              Waiting for your decision <span>{decisions.length}</span>
            </h2>
            <p>Review the findings before approving a proposed change.</p>
          </div>
          {!!decisions.length && (
            <button
              className="text-button"
              onClick={() => {
                window.location.hash = "approvals";
              }}
            >
              View all
              <ArrowRight size={14} />
            </button>
          )}
        </div>
        {loading ? (
          <Loading text="Loading decisions…" />
        ) : decisions.length ? (
          <div className="decision-grid">
            {decisions.slice(0, 4).map(({ entry, run, approval }) => (
              <article
                className="decision-card"
                key={run.id + approval.request_id}
              >
                <div className="decision-topline">
                  <span className="decision-label">
                    <ShieldCheck size={14} />
                    Approval required
                  </span>
                  <span className="decision-risk">
                    {run.outcome?.risk === "critical"
                      ? "Critical"
                      : run.outcome?.risk === "high"
                        ? "High risk"
                        : "Review needed"}
                  </span>
                </div>
                <h3>
                  {"tool" in approval
                    ? toolLabel(approval.tool)
                    : approval.title}
                </h3>
                <p className="decision-document">{entry.run.title}</p>
                <p className="decision-finding">{shortFinding(run)}</p>
                <div className="decision-footer">
                  <span>
                    {run.outcome?.departments?.join(" · ") || "Business review"}
                  </span>
                  <button
                    className="button secondary"
                    onClick={() => {
                      window.location.hash =
                        "approvals/" + encodeURIComponent(approval.request_id);
                    }}
                  >
                    Review decision
                    <ArrowRight size={14} />
                  </button>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <div className="workspace-clear">
            <CheckCircle2 size={20} />
            <div>
              <strong>No approvals are waiting</strong>
              <p>Any changes that need your decision will appear here.</p>
            </div>
          </div>
        )}
      </section>
      <section className="workspace-section" aria-labelledby="recent-heading">
        <div className="workspace-section-heading">
          <div>
            <h2 id="recent-heading">Latest case findings</h2>
            <p>
              {entries.length} cases · One entry per document, with repeated
              checks grouped together.
            </p>
          </div>
          <button className="text-button" onClick={() => onViewCases()}>
            All cases
            <ArrowRight size={14} />
          </button>
        </div>
        <div className="panel">
          {loading ? (
            <Loading text="Loading case findings…" />
          ) : entries.length ? (
            <CaseTable
              entries={entries}
              onOpen={onOpen}
              workflows={workflows}
              limit={5}
            />
          ) : (
            <Empty
              title="Your case findings will appear here"
              detail="Open an example document and process it to see its findings and recommended next steps."
            />
          )}
        </div>
      </section>
      <section className="workspace-section">
        <div className="workspace-section-heading">
          <div>
            <h2>Work across the business</h2>
            <p>Open an area to see its cases and findings.</p>
          </div>
        </div>
        <div className="business-areas">
          {workflows.map((w) => {
            const list = entries.filter((c) =>
              c.run.classification?.categories.includes(w.id),
            );
            const Icon = areaIcons[w.id] ?? FileText;
            const waiting = list.reduce((n, c) => n + c.decisions.length, 0);
            return (
              <button
                className={"business-area area-" + w.color}
                key={w.id}
                onClick={() => onViewCases("all", w.id)}
              >
                <span className="business-area-icon">
                  <Icon size={19} />
                </span>
                <h3>{w.name}</h3>
                <strong>
                  {list.length} case{list.length === 1 ? "" : "s"}
                </strong>
                <span>
                  {waiting
                    ? waiting + " awaiting a decision"
                    : list.length
                      ? "View findings"
                      : "No cases checked yet"}
                  <ArrowRight size={13} />
                </span>
              </button>
            );
          })}
        </div>
      </section>
      <details className="workspace-demo-note">
        <summary>
          About this demonstration
          <ChevronDown size={13} />
        </summary>
        <p>
          This workspace uses fictional example documents and recorded reviews.
          Inbox examples are reviewed on demand when you select Review document.
          There is no automatic processing queue or connected mailbox.
          Processing a document uses the AI Review service. Test runs and
          duplicate replays are kept out of the business totals; a saved example
          is shown only when its original review is unavailable.
        </p>
      </details>
    </div>
  );
}

export function BusinessCasesView({
  runs,
  cases: _cases,
  workflows,
  onOpen,
  loading,
  error,
  retry,
  view,
  area,
  onFilter,
  onInbox,
}: Shared & {
  view: CaseView;
  area: string;
  onFilter: ViewCases;
  onInbox: () => void;
}) {
  const [query, setQuery] = useState("");
  const entries = useMemo(() => businessCases(runs), [runs]);
  const filtered = filterCases(entries, view, area, query);
  return (
    <div className="finance-workspace">
      <div className="workspace-heading">
        <div>
          <div className="workspace-eyebrow">CASE MANAGEMENT</div>
          <h1>Cases & findings</h1>
          <p>What was found, what needs a decision and what to do next.</p>
        </div>
        <button className="button secondary" onClick={retry}>
          <RefreshCw size={15} />
          Refresh cases
        </button>
      </div>
      {error && <ErrorNotice message={error} retry={retry} />}
      <div className="case-view-tabs" aria-label="Filter cases">
        {(
          [
            ["all", "All cases"],
            ["decisions", "Your decisions"],
            ["followup", "Follow-up"],
            ["active", "In progress"],
            ["complete", "Checks complete"],
          ] as [CaseView, string][]
        ).map(([id, label]) => (
          <button
            key={id}
            className={view === id ? "selected" : ""}
            aria-pressed={view === id}
            onClick={() => onFilter(id, area)}
          >
            {label}
            <span>
              {id === "all"
                ? entries.length
                : entries.filter((c) => caseState(c) === id).length}
            </span>
          </button>
        ))}
      </div>
      <section className="panel">
        <div className="business-filter-bar">
          <label className="workspace-search">
            <Search size={17} />
            <input
              aria-label="Search cases"
              placeholder="Search documents or findings…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </label>
          <select
            aria-label="Filter business area"
            value={area}
            onChange={(e) => onFilter(view, e.target.value)}
          >
            <option value="all">All business areas</option>
            {workflows.map((w) => (
              <option key={w.id} value={w.id}>
                {w.name}
              </option>
            ))}
          </select>
        </div>
        {loading ? (
          <Loading text="Loading cases…" />
        ) : filtered.length ? (
          <CaseTable entries={filtered} workflows={workflows} onOpen={onOpen} />
        ) : (
          <Empty
            title="No cases in this view"
            detail={
              entries.length
                ? "Choose another filter or search to find a case."
                : "Process a document from the example inbox to create a case."
            }
          />
        )}
      </section>
      <div className="business-list-foot">
        <span>
          {filtered.length} of {entries.length} cases · Repeat checks are
          grouped by document.
        </span>
        <button className="text-button" onClick={onInbox}>
          Open document inbox
          <ArrowRight size={14} />
        </button>
      </div>
    </div>
  );
}

export function DocumentInbox({
  runs,
  cases,
  onOpen,
  loading,
  error,
  retry,
  documentId,
  partition,
  onSelect,
  onProcess,
}: {
  runs: Run[];
  cases: InboxCase[];
  onOpen: (run: Run) => void;
  loading: boolean;
  error: string;
  retry: () => void;
  documentId: string;
  partition: string;
  onSelect: (item: InboxCase) => void;
  onProcess: (item: InboxCase) => void;
}) {
  const entries = useMemo(() => businessCases(runs), [runs]);
  const byDocument = new Map(entries.map((e) => [e.key, e]));
  const [query, setQuery] = useState("");
  const [view, setView] = useState("all");
  const [visible, setVisible] = useState(25);
  const selected = documentId
    ? cases.find((c) => c.case_id === documentId && c.partition === partition)
    : (cases.find((c) => c.showcase) ?? cases[0]);
  const filtered = useMemo(
    () =>
      cases
        .filter(
          (c) =>
            (view === "all" ||
              (view === "ready"
                ? !byDocument.has(documentKey(c))
                : byDocument.has(documentKey(c)))) &&
            (c.title + " " + readableDocument(c).sender)
              .toLowerCase()
              .includes(query.toLowerCase()),
        )
        .sort(
          (a, b) =>
            Number(b.showcase) - Number(a.showcase) ||
            b.received_at.localeCompare(a.received_at),
        ),
    [cases, runs, view, query],
  );
  useEffect(() => setVisible(25), [query, view]);
  const message = selected ? readableDocument(selected) : null;
  const existing = selected ? byDocument.get(documentKey(selected)) : undefined;
  const active =
    existing && existing.run.mode !== "replay" && isActive(existing.run.status);
  return (
    <div className="finance-workspace">
      <div className="workspace-heading">
        <div>
          <div className="workspace-eyebrow">DOCUMENT INBOX</div>
          <h1>Documents</h1>
          <p>
            Open a document. FlowPilot identifies the work and follows the
            evidence.
          </p>
        </div>
        <span className="example-inbox-label">
          <Inbox size={15} />
          Example inbox · {cases.length} documents
        </span>
      </div>
      {error && <ErrorNotice message={error} retry={retry} />}
      <div className="document-inbox-layout">
        <section className="panel inbox-list-panel" aria-label="Document list">
          <div className="inbox-list-tools">
            <label className="workspace-search">
              <Search size={16} />
              <input
                placeholder="Find a document…"
                aria-label="Search documents"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </label>
            <select
              aria-label="Filter document status"
              value={view}
              onChange={(e) => setView(e.target.value)}
            >
              <option value="all">All documents</option>
              <option value="ready">Ready to process</option>
              <option value="checked">Already checked</option>
            </select>
          </div>
          <div className="inbox-document-list">
            {loading ? (
              <Loading text="Loading example documents…" />
            ) : (
              filtered.slice(0, visible).map((item) => {
                const entry = byDocument.get(documentKey(item));
                const doc = readableDocument(item);
                return (
                  <button
                    className={
                      "inbox-document " + (selected === item ? "selected" : "")
                    }
                    key={documentKey(item)}
                    onClick={() => onSelect(item)}
                    aria-pressed={selected === item}
                  >
                    <span className="inbox-document-meta">
                      <Mail size={14} />
                      {item.showcase && <span>Featured example</span>}
                      <time>{dateTime(item.received_at)}</time>
                    </span>
                    <strong>{doc.subject}</strong>
                    <span className="inbox-document-sender">
                      {doc.sender.replace(/\s*<[^>]+>/, "")}
                    </span>
                    <span
                      className={
                        "inbox-document-state " + (entry ? "checked" : "")
                      }
                    >
                      {entry ? caseStateLabel(entry) : "Ready to process"}
                    </span>
                  </button>
                );
              })
            )}
          </div>
          {filtered.length > visible && (
            <button
              className="inbox-show-more"
              onClick={() => setVisible((v) => v + 25)}
            >
              Show more documents ({filtered.length - visible})
              <ChevronDown size={14} />
            </button>
          )}
          {!loading && !filtered.length && (
            <Empty
              title="No matching documents"
              detail="Try another search or status."
            />
          )}
        </section>
        <section
          className="panel readable-document"
          aria-label="Selected document"
        >
          {selected && message ? (
            <>
              <div className="readable-document-head">
                <span className="readable-document-type">
                  <Mail size={15} />
                  Incoming correspondence
                </span>
                <h2>{message.subject}</h2>
                <dl>
                  <div>
                    <dt>From</dt>
                    <dd>{message.sender}</dd>
                  </div>
                  {message.recipient && (
                    <div>
                      <dt>To</dt>
                      <dd>{message.recipient}</dd>
                    </div>
                  )}
                  <div>
                    <dt>Received</dt>
                    <dd>{dateTime(selected.received_at)}</dd>
                  </div>
                </dl>
              </div>
              <div className="readable-document-content">
                <div className="document-message">{message.body}</div>
                {!!message.fields.length && (
                  <dl className="document-business-fields">
                    {message.fields.map((field, i) => (
                      <div key={i}>
                        <dt>{field.name}</dt>
                        <dd>{field.value}</dd>
                      </div>
                    ))}
                  </dl>
                )}
                {!!message.attachments.length && (
                  <div className="document-attachments">
                    <h3>
                      <FileText size={16} />
                      {message.attachments.length} attachment
                      {message.attachments.length === 1 ? "" : "s"}
                    </h3>
                    {message.attachments.map((attachment, i) => (
                      <details key={i}>
                        <summary>
                          <FileText size={15} />
                          Attachment {i + 1}
                          <span>
                            {attachment.name.split(".").at(-1)?.toUpperCase()}
                          </span>
                          <ChevronDown size={14} />
                        </summary>
                        <div className="document-attachment-text">
                          {attachment.text}
                        </div>
                      </details>
                    ))}
                  </div>
                )}
              </div>
              <div className="document-processing">
                {existing && (
                  <div className="document-existing">
                    <CaseState entry={existing} />
                    <p>{findingTitle(existing.run)}</p>
                    <button
                      className="button secondary"
                      onClick={() =>
                        onOpen(existing.decisions[0]?.run ?? existing.run)
                      }
                    >
                      Open findings
                      <ArrowUpRight size={14} />
                    </button>
                  </div>
                )}
                <div className="document-process-action">
                  <div>
                    <strong>
                      {active
                        ? "FlowPilot is checking this document"
                        : existing
                          ? "Need to check this document again?"
                          : "Ready for FlowPilot to check"}
                    </strong>
                    <p>
                      The request determines which records to check. No business
                      area needs to be selected.
                    </p>
                  </div>
                  <button
                    className={"button " + (existing ? "secondary" : "primary")}
                    disabled={!!active}
                    onClick={() => onProcess(selected)}
                  >
                    {active ? (
                      <LoaderCircle className="spin" size={16} />
                    ) : (
                      <ArrowRight size={16} />
                    )}
                    {active
                      ? "Checks in progress"
                      : existing
                        ? "Check again"
                        : "Review document"}
                  </button>
                </div>
                <small>
                  Demonstration records · Proposed changes require your
                  approval.
                </small>
              </div>
            </>
          ) : (
            <Empty
              title="No document selected"
              detail="Choose an example document from the inbox."
            />
          )}
        </section>
      </div>
    </div>
  );
}
