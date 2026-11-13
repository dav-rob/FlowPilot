import { useMemo, useState } from "react";
import { ArrowLeft, Download, Activity } from "lucide-react";
import type { Run } from "./types";
import { dateTime, download, duration, isActive } from "./api";
import {
  useResource,
  Loading,
  ErrorNotice,
  ModeBadge,
  Status,
  Json,
  Metrics,
} from "./shared";
import { EventCard } from "./RunView";
import { referenceNames } from "./presentation";
import "./routes.css";
export default function TraceView({
  id,
  onBack,
}: {
  id: string;
  onBack: () => void;
}) {
  const resource = useResource<Run>(
    "/runs/" + encodeURIComponent(id),
    (r) => isActive(r.status) || r.status === "awaiting_approval",
    2000,
  );
  const [filter, setFilter] = useState("all");
  const run = resource.data;
  const names = useMemo(
    () => (run ? referenceNames(run) : new Map<string, string>()),
    [run],
  );
  if (!run)
    return resource.error ? (
      <ErrorNotice message={resource.error} retry={resource.reload} />
    ) : (
      <Loading text="Opening execution trace…" />
    );
  const events = [...(run.events ?? [])].sort(
    (a, b) => a.sequence - b.sequence,
  );
  const shown = events.filter(
    (e) =>
      filter === "all" ||
      (filter === "tools" && ["tool_call", "tool_result"].includes(e.kind)) ||
      (filter === "controls" &&
        [
          "validation",
          "approval",
          "manual_decision",
          "handoff",
          "error",
        ].includes(e.kind)) ||
      (filter === "models" &&
        ["model", "classification", "escalation", "decision"].includes(e.kind)),
  );
  return (
    <div className="trace-page">
      <button className="text-button back-link" onClick={onBack}>
        <ArrowLeft size={15} /> Findings, next steps
      </button>
      <div className="page-heading">
        <div>
          <div className="eyebrow">OBSERVABILITY / CASE RECORD</div>
          <h1>Execution trace</h1>
          <p>{run.title}</p>
        </div>
        <div className="trace-heading-actions">
          <ModeBadge mode={run.mode} />
          <Status status={run.status} />
          <button
            className="button secondary"
            onClick={() => download(`flowpilot-trace-${id}.json`, run)}
          >
            <Download size={15} />
            Download trace
          </button>
        </div>
      </div>
      <p>
        The recorded model calls, evidence checks, controls and human decisions
        behind this case. Operational rationales are shown; private model
        reasoning is not recorded.
      </p>
      {resource.error && (
        <ErrorNotice message={resource.error} retry={resource.reload} />
      )}
      <div className="trace-summary">
        {[
          ["Review duration", duration(run.duration_ms)],
          ["Model calls", run.metrics.model_calls ?? "Not recorded"],
          ["Business tool calls", run.metrics.tool_calls ?? "Not recorded"],
          [
            "Unsafe actions blocked",
            run.metrics.unsafe_actions_blocked ?? "Not recorded",
          ],
        ].map(([k, v]) => (
          <article className="panel" key={k}>
            <small>{k}</small>
            <strong>{v}</strong>
          </article>
        ))}
      </div>
      <div className="trace-provenance">
        <span>Started {dateTime(run.created_at)}</span>
        <span>
          Rules: {run.ruleset_version ?? "Not recorded for this earlier review"}
        </span>
        <span>
          Application:{" "}
          {run.application_revision ?? "Not recorded for this earlier review"}
        </span>
        <span>Execution ID: {run.id}</span>
      </div>
      {run.mode === "replay" && (
        <p className="mode-explanation">
          Recorded replay: timings and usage describe the original execution.
          This view makes no new AI or business-tool calls.
        </p>
      )}
      <section className="panel trace-models">
        <h2>Models and resource usage</h2>
        <p>{run.metrics.providers?.join(" · ") || "No model usage recorded"}</p>
        <p>
          Usage is shown only where reported by the provider. Missing token or
          cost data is unknown, not zero.
        </p>
        <Metrics value={(run.metrics.usage ?? {}) as Record<string, unknown>} />
        <table>
          <caption>Recorded model response timings</caption>
          <thead>
            <tr>
              <th>Step</th>
              <th>Provider / model</th>
              <th>Duration</th>
            </tr>
          </thead>
          <tbody>
            {events
              .filter(
                (e) =>
                  (e.provider || e.model) && e.duration_ms != null && !e.tool,
              )
              .map((e) => (
                <tr key={e.id}>
                  <td>{e.sequence}</td>
                  <td>
                    {e.provider} / {e.model}
                  </td>
                  <td>{duration(e.duration_ms)}</td>
                </tr>
              ))}
          </tbody>
        </table>
      </section>
      <div className="trace-filters" aria-label="Trace filters">
        {[
          ["all", "All events"],
          ["models", "AI decisions"],
          ["tools", "Tool calls"],
          ["controls", "Controls & human decisions"],
        ].map(([v, label]) => (
          <button
            className={"button " + (filter === v ? "primary" : "secondary")}
            key={v}
            aria-pressed={filter === v}
            onClick={() => setFilter(v)}
          >
            {v === "all" && <Activity size={14} />} {label}
          </button>
        ))}
      </div>
      <section className="panel trace-timeline" aria-label="Execution events">
        {shown.map((event) => (
          <EventCard key={event.id} event={event} names={names} />
        ))}
        {!shown.length && <p>No matching events recorded.</p>}
      </section>
      <details className="panel">
        <summary>Classification and routing data</summary>
        <Json value={run.classification} />
      </details>
      <details className="panel">
        <summary>Complete recorded data</summary>
        <Json value={run} />
      </details>
    </div>
  );
}
