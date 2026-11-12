import { useEffect, useMemo, useState } from "react";
import {
  ArrowRight,
  ArrowUpRight,
  Check,
  ChevronDown,
  ChevronRight,
  FileCheck2,
  FileInput,
  FileText,
  Fingerprint,
  FolderOpen,
  Layers,
  Play,
  Scale,
  Search,
  Server,
  ShieldCheck,
  Sparkles,
  X,
} from "lucide-react";
import type { Config, InboxCase, Mode } from "./types";
import { dateTime, readable } from "./api";
import {
  Empty,
  ErrorNotice,
  Loading,
  ModePicker,
  SectionHeading,
  WorkflowPath,
} from "./shared";
const workflowIcons: Record<string, typeof ShieldCheck> = {
  supplier_fraud: ShieldCheck,
  regulatory_compliance: Scale,
  gdpr_data: Fingerprint,
  it_asset: Server,
  contract_risk: FileCheck2,
};
export default function Investigation({
  cases,
  loading,
  error,
  retry,
  config,
  onLaunch,
}: {
  cases: InboxCase[];
  loading: boolean;
  error: string;
  retry: () => void;
  config: Config | null;
  onLaunch: (body: object) => void;
}) {
  const [selectedId, setSelectedId] = useState("");
  const [source, setSource] = useState<"case" | "custom">("case");
  const [mode, setMode] = useState<Mode>("simulation");
  const [custom, setCustom] = useState("");
  const [title, setTitle] = useState("");
  const [browser, setBrowser] = useState(false);
  const [query, setQuery] = useState("");
  const [partition, setPartition] = useState("all");
  const [kind, setKind] = useState("all");
  const [expandedDoc, setExpandedDoc] = useState(false);
  const [visible, setVisible] = useState(20);
  const showcase = cases.filter((c) => c.showcase);
  useEffect(() => {
    if (!selectedId && cases.length)
      setSelectedId(
        (
          cases.find((c) => c.showcase && c.workflow === "supplier_fraud") ??
          cases.find((c) => c.showcase) ??
          cases[0]
        ).case_id,
      );
  }, [cases, selectedId]);
  const selected = cases.find((c) => c.case_id === selectedId);
  const filtered = useMemo(
    () =>
      cases.filter(
        (c) =>
          (partition === "all" || c.partition === partition) &&
          (kind === "all" || c.workflow === kind) &&
          `${c.title} ${c.case_id} ${c.preview}`
            .toLowerCase()
            .includes(query.toLowerCase()),
      ),
    [cases, partition, kind, query],
  );
  useEffect(() => setVisible(20), [query, partition, kind]);
  const canLaunch = source === "custom" ? !!custom.trim() : !!selected;
  function choose(c: InboxCase) {
    setSelectedId(c.case_id);
    setSource("case");
    setExpandedDoc(false);
  }
  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!canLaunch) return;
    onLaunch(
      source === "custom"
        ? {
            document: custom,
            title: title.trim() || "Custom investigation",
            mode,
          }
        : { case_id: selected!.case_id, partition: selected!.partition, mode },
    );
  }
  return (
    <div className="landing-page">
      <section className="hero">
        <div className="hero-copy">
          <div className="eyebrow">DEVELOPER TOOLS / MANUAL TESTING</div>
          <h1>Test workbench</h1>
          <p>
            Test an example or paste a document to inspect routing and tool
            calls. Test activity is kept out of the business dashboard.
          </p>
          <div className="hero-tags">
            <span>
              <Layers size={14} /> Multi-domain investigation
            </span>
            <span>
              <ShieldCheck size={14} /> Human oversight
            </span>
          </div>
        </div>
        <div className="hero-art" aria-hidden="true">
          <div className="art-orbit orbit-one" />
          <div className="art-orbit orbit-two" />
          <div className="art-line line-one" />
          <div className="art-line line-two" />
          <div className="art-node node-input">
            <FileText size={21} />
            <span>Incoming signal</span>
            <span className="art-small-dot" />
          </div>
          <div className="art-center">
            <WorkflowMark />
          </div>
          <div className="art-node node-outcome">
            <ShieldCheck size={21} />
            <span>Informed decision</span>
            <Check size={14} />
          </div>
          <span className="art-caption">CONNECTED INTELLIGENCE</span>
        </div>
      </section>
      <WorkflowPath />
      <section className="showcase-section">
        <SectionHeading
          eyebrow="A STARTING POINT FOR EVERY TEAM"
          title="Choose an investigation"
        >
          <button
            className="text-button"
            onClick={() => {
              setBrowser((v) => !v);
              setSource("case");
            }}
            aria-expanded={browser}
          >
            {browser
              ? "Close case browser"
              : `Browse ${cases.length || "all"} cases`}
            {browser ? <X size={15} /> : <ArrowUpRight size={16} />}
          </button>
        </SectionHeading>
        {error && <ErrorNotice message={error} retry={retry} />}
        <div className="workflow-cards">
          {config?.workflows?.map((workflow, index) => {
            const c = showcase.find((c) => c.workflow === workflow.id);
            const Icon = workflowIcons[workflow.id] ?? FileText;
            const active = source === "case" && selectedId === c?.case_id;
            return (
              <button
                className={`workflow-card tone-${workflow.color} ${active ? "selected" : ""}`}
                key={workflow.id}
                onClick={() => c && choose(c)}
                disabled={!c}
                aria-pressed={active}
              >
                <div className="workflow-card-top">
                  <span className="workflow-icon">
                    <Icon size={21} />
                  </span>
                  <span className={`card-select ${active ? "checked" : ""}`}>
                    {active ? (
                      <Check size={11} />
                    ) : (
                      String(index + 1).padStart(2, "0")
                    )}
                  </span>
                </div>
                <h3>{workflow.name}</h3>
                <p>{workflow.description}</p>
                <div className="workflow-card-foot">
                  <span>
                    {loading
                      ? "Loading case…"
                      : c
                        ? "Explore example"
                        : "No showcase available"}
                  </span>
                  <ArrowRight size={14} />
                </div>
              </button>
            );
          }) ??
            Array.from({ length: 5 }, (_, i) => (
              <div
                key={i}
                className="workflow-card skeleton"
                aria-hidden="true"
              />
            ))}
        </div>
      </section>
      {browser && (
        <section className="panel case-browser" aria-label="Case browser">
          <SectionHeading title="Case library">
            <span className="count-label">
              {filtered.length} of {cases.length} cases
            </span>
          </SectionHeading>
          <div className="filter-bar">
            <label className="search-field">
              <Search size={16} />
              <input
                aria-label="Search cases"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search title, case ID or document…"
              />
              {query && (
                <button
                  className="icon-button"
                  onClick={() => setQuery("")}
                  aria-label="Clear search"
                >
                  <X size={14} />
                </button>
              )}
            </label>
            <select
              aria-label="Filter case partition"
              value={partition}
              onChange={(e) => setPartition(e.target.value)}
            >
              <option value="all">All partitions</option>
              <option value="train">Train</option>
              <option value="validation">Validation</option>
              <option value="test">Test</option>
            </select>
            <select
              aria-label="Filter workflow examples"
              value={kind}
              onChange={(e) => setKind(e.target.value)}
            >
              <option value="all">All cases</option>
              {config?.workflows.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.name} examples
                </option>
              ))}
            </select>
          </div>
          {loading ? (
            <Loading text="Loading case library…" />
          ) : filtered.length ? (
            <>
              <div className="case-list">
                {filtered.slice(0, visible).map((c) => (
                  <button
                    key={`${c.partition}-${c.case_id}`}
                    className={`case-row ${selectedId === c.case_id && source === "case" ? "selected" : ""}`}
                    onClick={() => choose(c)}
                  >
                    <FileText size={18} />
                    <span>
                      <strong>{c.title}</strong>
                      <small>
                        {c.case_id} <span>·</span> {c.partition}{" "}
                        {c.showcase && "· Showcase"}
                      </small>
                    </span>
                    {selectedId === c.case_id && source === "case" ? (
                      <Check size={17} />
                    ) : (
                      <ChevronRight size={16} />
                    )}
                  </button>
                ))}
              </div>
              {filtered.length > visible && (
                <button
                  className="button secondary load-more"
                  onClick={() => setVisible((v) => v + 30)}
                >
                  Show more cases <ChevronDown size={15} />
                </button>
              )}
            </>
          ) : (
            <Empty
              title="No matching cases"
              detail="Try another search or partition."
            />
          )}
        </section>
      )}
      <form onSubmit={submit} className="launch-grid">
        <section className="panel input-panel">
          <div className="panel-header">
            <div className="panel-title">
              <FileInput size={18} />
              <h2>Input inspector</h2>
            </div>
            <span className="subtle-label">01 / INTAKE</span>
          </div>
          <div
            className="input-tabs"
            role="tablist"
            aria-label="Input source"
            onKeyDown={(e) => {
              if (["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) {
                e.preventDefault();
                const next =
                  e.key === "Home"
                    ? "case"
                    : e.key === "End"
                      ? "custom"
                      : source === "case"
                        ? "custom"
                        : "case";
                setSource(next);
                document.getElementById(`${next}-tab`)?.focus();
              }
            }}
          >
            <button
              id="case-tab"
              type="button"
              role="tab"
              tabIndex={source === "case" ? 0 : -1}
              aria-selected={source === "case"}
              aria-controls="input-content"
              className={source === "case" ? "active" : ""}
              onClick={() => setSource("case")}
            >
              <FolderOpen size={14} /> Selected case
            </button>
            <button
              id="custom-tab"
              type="button"
              role="tab"
              tabIndex={source === "custom" ? 0 : -1}
              aria-selected={source === "custom"}
              aria-controls="input-content"
              className={source === "custom" ? "active" : ""}
              onClick={() => setSource("custom")}
            >
              <FileText size={14} /> Paste your own
            </button>
          </div>
          <div
            id="input-content"
            role="tabpanel"
            aria-labelledby={source === "case" ? "case-tab" : "custom-tab"}
            className="input-content"
          >
            {source === "custom" ? (
              <>
                <label className="field-label" htmlFor="custom-title">
                  Investigation title <span className="muted">(optional)</span>
                </label>
                <input
                  className="full-input"
                  id="custom-title"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="Give this investigation a name"
                  maxLength={160}
                />
                <label className="field-label" htmlFor="custom-document">
                  Input document
                </label>
                <textarea
                  id="custom-document"
                  maxLength={50000}
                  className="document-input"
                  placeholder="Paste an email, policy, request, contract, or operational alert…"
                  value={custom}
                  onChange={(e) => setCustom(e.target.value)}
                  required
                />
                <div className="document-meta">
                  <span>Plain text · rendered securely</span>
                  <span>{custom.length.toLocaleString()} characters</span>
                </div>
              </>
            ) : loading ? (
              <Loading text="Opening input documents…" />
            ) : selected ? (
              <>
                <div className="document-heading">
                  <span className="file-type">
                    <FileText size={14} />
                    {selected.media_type
                      .replace("message/rfc822", "Email")
                      .replace("text/", "")}
                  </span>
                  <span className="mono muted small">{selected.case_id}</span>
                </div>
                <h3 className="document-title">{selected.title}</h3>
                <div className="document-subtitle">
                  {readable(selected.partition)} partition <span>·</span>{" "}
                  Received {dateTime(selected.received_at)}
                </div>
                <pre
                  tabIndex={0}
                  className={`input-document ${expandedDoc ? "expanded" : ""}`}
                >
                  {selected.document}
                </pre>
                <div className="document-meta">
                  <button
                    className="text-button"
                    type="button"
                    onClick={() => setExpandedDoc((v) => !v)}
                    aria-expanded={expandedDoc}
                  >
                    {expandedDoc ? "Collapse document" : "Expand full document"}
                    <ChevronDown
                      size={13}
                      className={expandedDoc ? "rotate" : ""}
                    />
                  </button>
                  <span>
                    {selected.document.length.toLocaleString()} characters
                  </span>
                </div>
              </>
            ) : (
              <Empty
                title="No input selected"
                detail="Choose a case from the library or paste your own document."
              />
            )}
          </div>
        </section>
        <section className="panel launch-panel">
          <div className="panel-header">
            <div className="panel-title">
              <Sparkles size={18} />
              <h2>Launch investigation</h2>
            </div>
            <span className="subtle-label">02 / CONFIGURE</span>
          </div>
          <div className="launch-content">
            <p className="launch-description">
              A single input. The right specialists.
              <br />A traceable path to resolution.
            </p>
            <ModePicker value={mode} onChange={setMode} />
            <div className={`mode-explainer ${mode}`}>
              <span className="mode-indicator" />
              <p>
                {mode === "simulation"
                  ? "Deterministic execution on local enterprise records. No AI model calls. All consequential actions are simulated."
                  : "Uses your configured local AI subscriptions. Provider, model, escalation, and usage are recorded in the trace. Consequential actions remain simulated."}
              </p>
            </div>
            <button
              className="button primary launch-button"
              type="submit"
              disabled={!canLaunch}
            >
              <Play size={16} fill="currentColor" /> Start investigation{" "}
              <ArrowRight size={17} />
            </button>
            <div className="launch-footnote">
              <ShieldCheck size={13} /> Sensitive actions require your review
            </div>
          </div>
        </section>
      </form>
      <div className="landing-bottom">
        <span className="tiny-icon">
          <Layers size={17} />
        </span>
        <span>One workspace. Multiple perspectives.</span>
        <p>
          Finance, compliance, privacy, IT, and legal — connected by evidence.
        </p>
      </div>
    </div>
  );
}
function WorkflowMark() {
  return (
    <>
      <span className="flow-square square-one" />
      <span className="flow-square square-two" />
      <span className="flow-square square-three" />
      <Sparkles size={27} />
    </>
  );
}
