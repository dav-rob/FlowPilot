import { useEffect, useRef, useState } from "react";
import {
  AlertCircle,
  ArrowUpRight,
  Check,
  ChevronRight,
  Circle,
  FlaskConical,
  LoaderCircle,
  Radio,
  RefreshCw,
  Sparkles,
} from "lucide-react";
import type { Mode } from "./types";
import { api, errorMessage, readable } from "./api";
export function useResource<T>(
  path: string | null,
  poll?: (data: T) => boolean,
  interval = 1000,
) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [version, setVersion] = useState(0);
  const pollRef = useRef(poll);
  pollRef.current = poll;
  useEffect(() => {
    setData(null);
    setError("");
    setLoading(!!path);
    if (!path) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function refresh() {
      try {
        const value = await api<T>(path!, undefined, controller.signal);
        if (controller.signal.aborted) return;
        setData(value);
        setError("");
        if (pollRef.current?.(value)) timer = setTimeout(refresh, interval);
      } catch (e) {
        if (!controller.signal.aborted) {
          setError(errorMessage(e));
          if (pollRef.current) timer = setTimeout(refresh, 3000);
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
  }, [path, version, interval]);
  return { data, loading, error, reload: () => setVersion((v) => v + 1) };
}
export function ErrorNotice({
  message,
  retry,
}: {
  message: string;
  retry?: () => void;
}) {
  return (
    <div className="error-notice" role="alert">
      <AlertCircle size={18} />
      <span>{message}</span>
      {retry && (
        <button className="text-button" onClick={retry}>
          <RefreshCw size={14} /> Retry
        </button>
      )}
    </div>
  );
}
export function Loading({ text = "Loading workspace…" }: { text?: string }) {
  return (
    <div className="empty-state" role="status">
      <LoaderCircle className="spin" size={24} />
      <p>{text}</p>
    </div>
  );
}
export function Empty({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="empty-state">
      <div className="empty-icon">
        <Sparkles size={24} />
      </div>
      <h3>{title}</h3>
      <p>{detail}</p>
    </div>
  );
}
export function ModeBadge({ mode }: { mode: Mode | "replay" }) {
  return (
    <span className={`badge mode-${mode}`}>
      {mode === "live" ? (
        <Radio size={12} />
      ) : mode === "replay" ? (
        <RefreshCw size={12} />
      ) : (
        <FlaskConical size={12} />
      )}{" "}
      {mode === "live"
        ? "Live AI"
        : mode === "replay"
          ? "Recorded replay"
          : "Simulation"}
    </span>
  );
}
export function Status({ status }: { status: string }) {
  return (
    <span className={`badge status-${status}`}>
      {status === "running" || status === "queued" ? (
        <LoaderCircle size={12} className="spin" />
      ) : status === "completed" ||
        status === "executed" ||
        status === "approved" ? (
        <Check size={12} />
      ) : (
        <Circle size={8} />
      )}{" "}
      {readable(status)}
    </span>
  );
}
export function Json({ value }: { value: unknown }) {
  return (
    <pre tabIndex={0} className="json-block">
      {JSON.stringify(value, null, 2) ?? "Unknown"}
    </pre>
  );
}
export function ModePicker({
  value,
  onChange,
  disabled,
}: {
  value: Mode;
  onChange: (mode: Mode) => void;
  disabled?: boolean;
}) {
  return (
    <fieldset className="mode-picker" disabled={disabled}>
      <legend>Execution mode</legend>
      {(["live", "simulation"] as Mode[]).map((mode) => (
        <label
          className={`mode-option ${value === mode ? "selected" : ""}`}
          key={mode}
        >
          <input
            type="radio"
            name="execution-mode"
            value={mode}
            checked={value === mode}
            onChange={() => onChange(mode)}
          />
          <span className="mode-icon">
            {mode === "live" ? (
              <Sparkles size={18} />
            ) : (
              <FlaskConical size={18} />
            )}
          </span>
          <span>
            <strong>{mode === "live" ? "Live AI" : "Simulation"}</strong>
            <small>
              {mode === "live"
                ? "Your local AI subscriptions"
                : "Deterministic · no model calls"}
            </small>
          </span>
          <span className="radio-dot" />
        </label>
      ))}
    </fieldset>
  );
}
export function WorkflowPath({ stage = 0 }: { stage?: number }) {
  return (
    <div
      className="workflow-path"
      aria-label={`Workflow: ${["Intake", "Classify", "Investigate", "Review"][stage] ?? "Intake"}`}
    >
      {["Intake", "Classify", "Investigate", "Review"].map((label, i) => (
        <div
          className={`path-stage ${i <= stage ? "reached" : ""} ${i === stage ? "current" : ""}`}
          key={label}
        >
          <span>
            {i < stage ? <Check size={12} /> : String(i + 1).padStart(2, "0")}
          </span>
          <b>{label}</b>
          {i < 3 && <ChevronRight size={15} />}
        </div>
      ))}
    </div>
  );
}
export function SectionHeading({
  eyebrow,
  title,
  children,
}: {
  eyebrow?: string;
  title: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="section-heading">
      <div>
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        <h2>{title}</h2>
      </div>
      {children}
    </div>
  );
}
export function OpenArrow() {
  return <ArrowUpRight size={16} />;
}
export function Metrics({
  value,
  prefix = "",
}: {
  value: Record<string, unknown>;
  prefix?: string;
}) {
  const entries = Object.entries(value ?? {});
  if (!entries.length)
    return <p className="muted small">No metrics reported yet.</p>;
  return (
    <div className="metric-tree">
      {entries.map(([key, item]) => (
        <div
          key={key}
          className={
            typeof item === "object" && item !== null && !Array.isArray(item)
              ? "metric-nested"
              : "metric-row"
          }
        >
          {typeof item === "object" && item !== null && !Array.isArray(item) ? (
            <>
              <h4>{readable(key)}</h4>
              <Metrics
                value={item as Record<string, unknown>}
                prefix={`${prefix}${key}.`}
              />
            </>
          ) : (
            <>
              <span>{readable(key)}</span>
              <strong>
                {item == null
                  ? "Unknown"
                  : Array.isArray(item)
                    ? item.length
                      ? item
                          .map((v) =>
                            typeof v === "object"
                              ? JSON.stringify(v)
                              : String(v),
                          )
                          .join(", ")
                      : "None reported"
                    : typeof item === "number"
                      ? item.toLocaleString(undefined, {
                          maximumFractionDigits: 4,
                        })
                      : String(item)}
              </strong>
            </>
          )}
        </div>
      ))}
    </div>
  );
}
