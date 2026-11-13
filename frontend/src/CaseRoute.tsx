import { ArrowRight, CheckCircle2, LockKeyhole, Users } from "lucide-react";
import type { Run } from "./types";
import "./routes.css";
export function CaseRoute({ run }: { run: Run }) {
  const route = run.business_route;
  const requests = [...(run.approvals ?? []), ...(run.manual_reviews ?? [])];
  const waiting = requests.filter((r) => r.status === "pending");
  const human =
    ["human_review", "human_complete", "declined", "blocked"].includes(
      route?.path ?? "",
    ) || waiting.length > 0;
  const label =
    route?.label ??
    (waiting.length
      ? "Held for human review"
      : run.outcome
        ? "Review complete"
        : "In progress");
  return (
    <section
      className={
        "case-route panel " + (human ? "route-human" : "route-standard")
      }
      aria-label="Business process route"
    >
      <div className="case-route-heading">
        {human ? <Users size={21} /> : <CheckCircle2 size={21} />}
        <div>
          <span>BUSINESS PROCESS</span>
          <h2>{label}</h2>
        </div>
      </div>
      <div className="route-steps">
        <span>Document</span>
        <ArrowRight size={14} />
        <span>AI Review</span>
        <ArrowRight size={14} />
        <strong>{human ? "Human decision" : "Findings, next steps"}</strong>
        {human && (
          <>
            <ArrowRight size={14} />
            <span>Recorded outcome</span>
          </>
        )}
      </div>
      <p>
        {route?.detail ??
          (waiting.length
            ? "The proposed next step is paused until a person records a decision."
            : "See the findings and recommended next steps below.")}
      </p>
      {run.mode !== "replay" && requests.length > 0 && (
        <a
          className="button secondary"
          href={
            "#approvals/" +
            encodeURIComponent(waiting[0]?.request_id ?? requests[0].request_id)
          }
        >
          <LockKeyhole size={15} />
          {waiting.length
            ? `Open approvals · ${waiting.length} waiting`
            : "View approval decisions"}
          <ArrowRight size={15} />
        </a>
      )}
    </section>
  );
}
export function ProcessingRoutes({
  standard,
  human,
  active,
}: {
  standard: number;
  human: number;
  active: number;
}) {
  return (
    <section
      className="processing-routes panel"
      aria-label="Document processing routes"
    >
      <div className="workspace-section-heading">
        <div>
          <h2>From document to decision</h2>
          <p>
            Routine reviews finish with findings. Exceptions take a separate
            human review route.
          </p>
        </div>
      </div>
      <div className="processing-route-grid">
        <article>
          <CheckCircle2 size={20} />
          <h3>
            Standard route <span>{standard}</span>
          </h3>
          <p>Document → AI Review → Findings, next steps</p>
          <small>
            Checks completed without an approval handoff. Consequential changes
            are never applied automatically.
          </small>
        </article>
        <article className="human-path">
          <Users size={20} />
          <h3>
            Human review route <span>{human}</span>
          </h3>
          <p>Document → AI Review → Hold → Human decision</p>
          <small>
            The proposed step stays paused until the required decisions are
            recorded.
          </small>
          <a href="#approvals">
            Open approval workflows <ArrowRight size={14} />
          </a>
        </article>
      </div>
      {active > 0 && (
        <p>
          {active} review{active === 1 ? " is" : "s are"} still in progress.
        </p>
      )}
    </section>
  );
}
