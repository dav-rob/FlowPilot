import { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowRight,
  ArrowUpRight,
  Check,
  CheckCircle2,
  ClipboardCheck,
  Clock3,
  FileText,
  LockKeyhole,
  RefreshCw,
  Search,
  ShieldAlert,
  Users,
  X,
} from "lucide-react";
import type { Run } from "./types";
import { api, dateTime, errorMessage, readable } from "./api";
import { Empty, ErrorNotice, Json, Loading, Status } from "./shared";
import { businessText, toolLabel } from "./presentation";
import "./approvals.css";

export interface ManualWorkItem {
  id: string;
  run_id: string;
  request_id: string;
  kind: "action_approval" | "department_review";
  title: string;
  case_title: string;
  department: string;
  reason: string;
  hold_scope: string;
  next_step: string;
  status: "pending" | "approved" | "executed" | "denied" | "failed" | "blocked";
  created_at: string;
  decided_at?: string;
  decision_note?: string;
  mode: "live" | "simulation";
  purpose?: string;
  can_decide: boolean;
  blocked_reason?: string;
  tool?: string;
  args?: object;
  result?: object;
}

const awaitingDecision = (item: ManualWorkItem) =>
  item.status === "pending" || item.status === "blocked";

export default function Approvals({
  onOpen,
  selectedId,
  onChanged,
}: {
  onOpen: (run: Run) => void;
  selectedId?: string;
  onChanged?: () => void;
}) {
  const [items, setItems] = useState<ManualWorkItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [actionError, setActionError] = useState("");
  const [notice, setNotice] = useState("");
  const [version, setVersion] = useState(0);
  const [tab, setTab] = useState<"pending" | "history">("pending");
  const [query, setQuery] = useState("");
  const [department, setDepartment] = useState("all");
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState("");
  const revision = useRef(0);
  const actionInFlight = useRef(false);
  const highlighted = useRef("");
  const cardRefs = useRef(new Map<string, HTMLElement>());

  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function refresh() {
      const observedRevision = revision.current;
      try {
        const value = await api<{ items: ManualWorkItem[] }>(
          "/approvals",
          undefined,
          controller.signal,
        );
        if (controller.signal.aborted) return;
        if (observedRevision === revision.current) {
          setItems(value.items);
          setError("");
        }
      } catch (e) {
        if (!controller.signal.aborted) setError(errorMessage(e));
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false);
          timer = setTimeout(refresh, 5000);
        }
      }
    }
    void refresh();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [version]);

  useEffect(() => {
    if (!selectedId || highlighted.current === selectedId) return;
    const selected = items.find(
      (item) => item.id === selectedId || item.request_id === selectedId,
    );
    if (!selected) return;
    setTab(awaitingDecision(selected) ? "pending" : "history");
    setQuery("");
    setDepartment("all");
    highlighted.current = selectedId;
    const timer = setTimeout(() => {
      cardRefs.current
        .get(selected.id)
        ?.scrollIntoView({ block: "center", behavior: "smooth" });
      cardRefs.current.get(selected.id)?.focus({ preventScroll: true });
    }, 50);
    return () => clearTimeout(timer);
  }, [selectedId, items]);

  const pending = items.filter(awaitingDecision);
  const history = items.filter((item) => !awaitingDecision(item));
  const departments = useMemo(
    () => [...new Set(items.map((item) => item.department))].sort(),
    [items],
  );
  const filtered = (tab === "pending" ? pending : history).filter((item) => {
    const needle = query.trim().toLowerCase();
    return (
      (department === "all" || department === item.department) &&
      (!needle ||
        [item.title, item.case_title, item.department, item.reason]
          .join(" ")
          .toLowerCase()
          .includes(needle))
    );
  });

  async function openCase(item: ManualWorkItem) {
    if (actionInFlight.current) return;
    actionInFlight.current = true;
    setBusy("case:" + item.id);
    setActionError("");
    try {
      onOpen(await api<Run>("/runs/" + encodeURIComponent(item.run_id)));
    } catch (e) {
      setActionError(errorMessage(e));
    } finally {
      actionInFlight.current = false;
      setBusy("");
    }
  }

  async function decide(item: ManualWorkItem, decision: "approve" | "decline") {
    if (actionInFlight.current || !item.can_decide) return;
    const note = (notes[item.id] ?? "").trim();
    if (!note) {
      setActionError(
        "Add a decision note before approving or declining this request.",
      );
      return;
    }
    actionInFlight.current = true;
    revision.current++;
    setBusy(item.id);
    setActionError("");
    setNotice("");
    try {
      const value = await api<{ item: ManualWorkItem; run: Run }>(
        `/approvals/${encodeURIComponent(item.run_id)}/${encodeURIComponent(item.request_id)}`,
        { decision, note },
      );
      revision.current++;
      setItems((current) =>
        current.map((row) => (row.id === item.id ? value.item : row)),
      );
      setNotice(
        value.item.status === "failed" || value.item.status === "blocked"
          ? "The decision was recorded, but the proposed action did not proceed. Open the case for the recorded restriction or error."
          : decision === "decline"
            ? "Declined. The proposed action has not been applied. Your decision is saved in the history."
            : item.kind === "department_review"
              ? "Review approved and recorded. This decision does not execute a business change."
              : "Approved. The simulated action result is saved in the decision history.",
      );
      onChanged?.();
      setVersion((v) => v + 1);
    } catch (e) {
      setActionError(errorMessage(e));
      setVersion((v) => v + 1);
    } finally {
      actionInFlight.current = false;
      setBusy("");
    }
  }

  return (
    <div className="approvals-page">
      <div className="approvals-heading">
        <div>
          <div className="eyebrow">HUMAN DECISIONS</div>
          <h1>Approvals</h1>
          <p>
            Cases that need a person’s decision before the next step can
            proceed.
          </p>
        </div>
        <button
          className="button secondary"
          onClick={() => setVersion((v) => v + 1)}
          disabled={!!busy}
        >
          <RefreshCw size={15} /> Refresh
        </button>
      </div>

      <div className="approval-route-overview panel">
        <div className="approval-route-icon">
          <Users size={24} />
        </div>
        <div>
          <h2>AI checks. People decide.</h2>
          <p>
            When a review needs approval, FlowPilot pauses the proposed step and
            sends the findings to the relevant team. The request and the human
            decision stay linked to the case.
          </p>
        </div>
        <div
          className="approval-route-sequence"
          aria-label="Manual approval route"
        >
          <span>
            <ClipboardCheck size={15} /> Findings
          </span>
          <ArrowRight size={15} />
          <span className="held">
            <LockKeyhole size={15} /> Held for review
          </span>
          <ArrowRight size={15} />
          <span>
            <Users size={15} /> Human decision
          </span>
        </div>
      </div>

      <div className="approval-counts">
        <div className="panel">
          <Clock3 size={19} />
          <strong>
            {pending.filter((item) => item.status === "pending").length}
          </strong>
          <span>Awaiting a decision</span>
        </div>
        <div className="panel">
          <ShieldAlert size={19} />
          <strong>
            {items.filter((item) => item.status === "blocked").length}
          </strong>
          <span>Blocked or incomplete</span>
        </div>
        <div className="panel">
          <CheckCircle2 size={19} />
          <strong>{history.length}</strong>
          <span>Recorded decisions</span>
        </div>
      </div>

      <p className="approval-demo-note">
        Demonstration workflow · All records and changes are fictional.
        Decisions are recorded as the local demo reviewer; no bank identity or
        authority is verified.
      </p>
      {error && (
        <ErrorNotice message={error} retry={() => setVersion((v) => v + 1)} />
      )}
      {actionError && <ErrorNotice message={actionError} />}
      {notice && (
        <div className="approval-saved-notice" role="status">
          <CheckCircle2 size={17} />
          <span>{notice}</span>
        </div>
      )}

      <div className="approvals-toolbar panel">
        <div
          className="approvals-tabs"
          role="tablist"
          aria-label="Approval queue"
        >
          <button
            role="tab"
            aria-selected={tab === "pending"}
            onClick={() => setTab("pending")}
            className={tab === "pending" ? "selected" : ""}
          >
            Waiting & blocked <span>{pending.length}</span>
          </button>
          <button
            role="tab"
            aria-selected={tab === "history"}
            onClick={() => setTab("history")}
            className={tab === "history" ? "selected" : ""}
          >
            Decision history <span>{history.length}</span>
          </button>
        </div>
        <div className="approvals-filters">
          <label className="approval-search">
            <Search size={17} />
            <input
              aria-label="Search approval requests"
              placeholder="Search cases, requests or teams…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </label>
          <select
            aria-label="Filter by reviewing team"
            value={department}
            onChange={(e) => setDepartment(e.target.value)}
          >
            <option value="all">All teams</option>
            {departments.map((name) => (
              <option key={name} value={name}>
                {readable(name)}
              </option>
            ))}
          </select>
        </div>
      </div>

      {loading && !items.length ? (
        <Loading text="Loading approval requests…" />
      ) : filtered.length === 0 ? (
        <div className="panel">
          <Empty
            title={
              query || department !== "all"
                ? "No requests match these filters"
                : tab === "pending"
                  ? "No decisions waiting"
                  : "No decisions recorded yet"
            }
            detail={
              tab === "pending"
                ? "Requests will appear here when a case requires human approval. Routine reviews can finish without entering this queue."
                : "Approved and declined requests remain here with their decision notes and case links."
            }
          />
        </div>
      ) : (
        <div
          className="approval-workflows"
          role="tabpanel"
          aria-label={
            tab === "pending"
              ? "Requests awaiting decisions"
              : "Recorded decisions"
          }
        >
          {filtered.map((item) => {
            const selected =
              item.id === selectedId || item.request_id === selectedId;
            const isDepartment = item.kind === "department_review";
            return (
              <article
                className={
                  "panel approval-workflow-card" +
                  (selected ? " is-selected" : "")
                }
                key={item.id}
                tabIndex={-1}
                ref={(node) => {
                  if (node) cardRefs.current.set(item.id, node);
                  else cardRefs.current.delete(item.id);
                }}
              >
                <div className="approval-workflow-head">
                  <div>
                    <span className="approval-kind">
                      <Users size={14} />{" "}
                      {isDepartment
                        ? "Department review"
                        : "Proposed business change"}
                    </span>
                    <h2>
                      {businessText(
                        isDepartment
                          ? item.title
                          : item.tool
                            ? toolLabel(item.tool)
                            : item.title || "Approval request",
                      )}
                    </h2>
                  </div>
                  <Status status={item.status} />
                </div>
                <button
                  className="approval-case-link"
                  disabled={!!busy}
                  onClick={() => void openCase(item)}
                >
                  <FileText size={14} />
                  {item.case_title}
                  <ArrowUpRight size={14} />
                </button>
                <dl className="approval-workflow-details">
                  <div>
                    <dt>Reviewing team</dt>
                    <dd>{readable(item.department)}</dd>
                  </div>
                  <div>
                    <dt>Requested</dt>
                    <dd>
                      <time dateTime={item.created_at}>
                        {dateTime(item.created_at)}
                      </time>
                    </dd>
                  </div>
                  <div className="full">
                    <dt>Why a decision is needed</dt>
                    <dd>{businessText(item.reason)}</dd>
                  </div>
                </dl>
                <div className="approval-held-step">
                  <LockKeyhole size={17} />
                  <div>
                    <strong>
                      {awaitingDecision(item)
                        ? "What is held"
                        : "Scope of this decision"}
                    </strong>
                    <p>{businessText(item.hold_scope)}</p>
                  </div>
                </div>
                <div className="approval-next-step">
                  <strong>What happens next</strong>
                  <p>{businessText(item.next_step)}</p>
                  <p className="approval-effect">
                    {isDepartment
                      ? "Approval records the team’s decision. It does not apply a business change or override another rule."
                      : "Approval permits this specific simulated action. Other rules are checked again before it can be applied."}
                  </p>
                </div>
                {item.status === "denied" && (
                  <p className="approval-decision-message">
                    <X size={15} /> Declined — the proposed action has not been
                    applied.
                  </p>
                )}
                {item.status === "approved" && isDepartment && (
                  <p className="approval-decision-message">
                    <CheckCircle2 size={15} /> Review decision recorded. No
                    business change was executed by this approval.
                  </p>
                )}
                {(item.status === "failed" ||
                  item.status === "blocked" ||
                  (item.status === "pending" && !item.can_decide)) && (
                  <div className="approval-restriction">
                    <ShieldAlert size={17} />
                    <p>
                      {businessText(
                        item.blocked_reason ||
                          (item.status === "failed"
                            ? "The approved action could not be applied. Open the case to inspect the recorded result before taking another step."
                            : "This request cannot be approved while the case is incomplete or a rule prevents the action."),
                      )}
                    </p>
                  </div>
                )}
                {item.decision_note && (
                  <div className="approval-recorded-note">
                    <strong>Decision note</strong>
                    <p>{item.decision_note}</p>
                    <small>
                      Local demo reviewer
                      {item.decided_at ? " · " + dateTime(item.decided_at) : ""}
                    </small>
                  </div>
                )}
                {item.status === "pending" && item.can_decide && (
                  <div className="approval-decision-form">
                    <label htmlFor={"decision-note-" + item.id}>
                      Your decision note <span>Required</span>
                    </label>
                    <textarea
                      id={"decision-note-" + item.id}
                      rows={3}
                      maxLength={2000}
                      value={notes[item.id] ?? ""}
                      onChange={(e) =>
                        setNotes((current) => ({
                          ...current,
                          [item.id]: e.target.value,
                        }))
                      }
                      placeholder="Record the reason for your decision and any follow-up needed."
                      disabled={!!busy}
                    />
                    <div className="approval-decision-buttons">
                      <button
                        className="button approve"
                        disabled={!!busy || !(notes[item.id] ?? "").trim()}
                        onClick={() => void decide(item, "approve")}
                      >
                        <Check size={15} />
                        {busy === item.id
                          ? "Saving decision…"
                          : isDepartment
                            ? "Approve review"
                            : "Approve simulated change"}
                      </button>
                      <button
                        className="button danger-outline"
                        disabled={!!busy || !(notes[item.id] ?? "").trim()}
                        onClick={() => void decide(item, "decline")}
                      >
                        <X size={15} />
                        Decline
                      </button>
                    </div>
                  </div>
                )}
                {(item.args || item.result) && (
                  <details className="approval-exact-details">
                    <summary>Exact proposal and recorded result</summary>
                    <Json
                      value={{
                        ...(item.tool ? { tool: item.tool } : {}),
                        ...(item.args ? { arguments: item.args } : {}),
                        ...(item.result ? { result: item.result } : {}),
                      }}
                    />
                  </details>
                )}
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
}
