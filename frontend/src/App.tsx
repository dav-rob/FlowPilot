import { useEffect, useState } from "react";
import {
  Activity,
  ArrowRight,
  ChevronDown,
  Code2,
  FileText,
  FlaskConical,
  Inbox,
  LayoutDashboard,
  Menu,
  Radio,
  ShieldCheck,
  Workflow,
  X,
} from "lucide-react";
import type { Config, InboxCase, Mode, Page, Run } from "./types";
import { api, errorMessage } from "./api";
import { ErrorNotice, useResource } from "./shared";
import Evals from "./Evals";
import Approvals from "./Approvals";
import TraceView from "./TraceView";
import RunView from "./RunView";

import { BusinessCasesView, DocumentInbox, FinanceOverview } from "./Workspace";
import { workspaceRoute, type CaseView } from "./business";

const businessNav: { id: Page; label: string; icon: typeof Activity }[] = [
  { id: "overview", label: "Overview", icon: LayoutDashboard },
  { id: "documents", label: "Documents", icon: Inbox },
  { id: "cases", label: "Cases & findings", icon: FileText },
  { id: "approvals", label: "Approvals", icon: ShieldCheck },
  { id: "evals", label: "Evals", icon: FlaskConical },
];

export default function App() {
  const developer =
    new URLSearchParams(window.location.search).get("developer") === "true";
  const [location, setLocation] = useState(() =>
    workspaceRoute(window.location.hash, developer),
  );
  const [mobileNav, setMobileNav] = useState(false);
  const [starting, setStarting] = useState(false);
  const [launchMode, setLaunchMode] = useState<Mode>("live");
  const [initialRun, setInitialRun] = useState<Run | null>(null);
  const [launchError, setLaunchError] = useState("");
  const [caseView, setCaseView] = useState<{ view: CaseView; area: string }>({
    view: "all",
    area: "all",
  });
  const config = useResource<Config>("/config");
  const health = useResource<{ status: string; name: string }>(
    "/health",
    () => true,
    15000,
  );
  const activity = useResource<{ runs: Run[] }>("/runs", () => true, 5000);
  const [cases, setCases] = useState<InboxCase[]>([]);
  const [casesLoading, setCasesLoading] = useState(true);
  const [caseError, setCaseError] = useState("");
  const [caseVersion, setCaseVersion] = useState(0);
  useEffect(() => {
    const update = () => {
      setLocation(workspaceRoute(window.location.hash, developer));
      setMobileNav(false);
      window.scrollTo(0, 0);
    };
    window.addEventListener("hashchange", update);
    return () => window.removeEventListener("hashchange", update);
  }, [developer]);
  useEffect(() => {
    const controller = new AbortController();
    setCasesLoading(true);
    setCaseError("");
    void Promise.allSettled(
      (["train", "validation", "test"] as const).map((partition) =>
        api<{ cases: InboxCase[]; total: number }>(
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
      const failures = results.filter((r) => r.status === "rejected");
      setCaseError(
        failures.length
          ? "Some example documents could not be loaded. Please try again."
          : "",
      );
      setCasesLoading(false);
    });
    return () => controller.abort();
  }, [caseVersion]);
  function navigate(page: Page) {
    window.location.hash = page;
    setMobileNav(false);
  }
  function viewCases(view: CaseView = "all", area = "all") {
    setCaseView({ view, area });
    navigate("cases");
  }
  function openRun(run: Run) {
    setInitialRun(run);
    window.location.hash = "run/" + encodeURIComponent(run.id);
  }
  function selectDocument(item: InboxCase) {
    window.location.hash =
      "document/" + item.partition + "/" + encodeURIComponent(item.case_id);
  }
  async function launch(body: object) {
    setLaunchMode((body as { mode: Mode }).mode);
    setLaunchError("");
    setStarting(true);
    try {
      openRun(await api<Run>("/runs", body));
    } catch (e) {
      setLaunchError(errorMessage(e));
    } finally {
      setStarting(false);
    }
  }
  function exitDeveloper() {
    const url = new URL(window.location.href);
    url.searchParams.delete("developer");
    url.hash = "overview";
    window.location.href = url.href;
  }
  const connected = !!health.data && !health.error;
  const nav = businessNav;
  const activeTitle = location.traceId
    ? "Execution trace"
    : starting || location.runId
      ? "Case findings"
      : (nav.find((n) => n.id === location.page)?.label ?? "Overview");
  useEffect(() => {
    document.title = activeTitle + " · FlowPilot";
  }, [activeTitle]);
  const workspaceProps = {
    runs: activity.data?.runs ?? [],
    cases,
    workflows: config.data?.workflows ?? [],
    onOpen: openRun,
    loading: activity.loading || casesLoading,
    error: [activity.error, caseError].filter(Boolean).join(" "),
    retry: activity.reload,
  };
  const navItem = (item: (typeof businessNav)[number]) => (
    <a
      key={item.id}
      href={"#" + item.id}
      aria-current={location.page === item.id ? "page" : undefined}
      className={"nav-item " + (location.page === item.id ? "active" : "")}
      onClick={() => {
        setMobileNav(false);
        if (item.id === "cases") setCaseView({ view: "all", area: "all" });
      }}
    >
      <item.icon size={18} />
      <span>{item.label}</span>
      {location.page === item.id && <span className="nav-active-dot" />}
    </a>
  );
  return (
    <div
      className={
        "app-shell " +
        (developer ? "developer-workspace" : "business-workspace")
      }
    >
      <a
        href="#main-content"
        className="skip-link"
        onClick={(e) => {
          e.preventDefault();
          document.getElementById("main-content")?.focus();
        }}
      >
        Skip to content
      </a>
      {mobileNav && (
        <button
          className="nav-scrim"
          aria-label="Close navigation"
          onClick={() => setMobileNav(false)}
        />
      )}
      <aside className={"sidebar " + (mobileNav ? "open" : "")}>
        <a href="#overview" className="brand" aria-label="FlowPilot home">
          <span className="brand-symbol">
            <Workflow size={25} />
          </span>
          <span>
            FlowPilot<span className="brand-dot">.</span>
          </span>
        </a>
        <button
          className="workspace-switch"
          onClick={() => navigate("overview")}
        >
          <span className="workspace-avatar">HM</span>
          <span>
            <strong>Harbourline Mutual</strong>
            <small>Finance workspace</small>
          </span>
          <ChevronDown size={14} />
        </button>
        <div className="nav-caption">WORKSPACE</div>
        <nav aria-label="Main navigation">{businessNav.map(navItem)}</nav>
        <div className="sidebar-note business-sidebar-note">
          <span className="sidebar-note-icon">
            <FileText size={19} />
          </span>
          <h3>From document to decision</h3>
          <p>
            FlowPilot checks the records. You review the findings and approve
            changes.
          </p>
          <a href="#documents">
            Open the inbox
            <ArrowRight size={13} />
          </a>
        </div>
        <div className="sidebar-bottom">
          <div className="local-label">
            <span className={"connection-dot " + (connected ? "online" : "")} />
            {connected
              ? "Workspace connected"
              : health.loading
                ? "Connecting…"
                : "Connection unavailable"}
          </div>
          <div className="profile">
            <span className="profile-avatar">
              <ShieldCheck size={18} />
            </span>
            <span>
              <strong>Demonstration workspace</strong>
              <small>Fictional business records</small>
            </span>
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumb">
            <button
              className="icon-button mobile-menu"
              onClick={() => setMobileNav(true)}
              aria-label="Open navigation"
            >
              <Menu size={21} />
            </button>
            <span className="breadcrumb-root">Workspace</span>
            <span className="breadcrumb-slash">/</span>
            <strong>{activeTitle}</strong>
          </div>
          <div className="topbar-right">
            {developer ? (
              <button className="developer-exit" onClick={exitDeveloper}>
                <Code2 size={13} />
                Evals access · Exit
              </button>
            ) : (
              <span className="local-pill">
                <Radio size={12} />
                Interview demonstration
              </span>
            )}
            <div className="topbar-divider" />
            <span className="topbar-avatar">HM</span>
          </div>
        </header>
        <main id="main-content" tabIndex={-1}>
          {config.error && (
            <ErrorNotice
              message={
                "Workspace settings could not be loaded. " + config.error
              }
              retry={config.reload}
            />
          )}
          {launchError && (
            <ErrorNotice
              message={"The document could not be processed. " + launchError}
            />
          )}
          {location.traceId ? (
            <TraceView
              id={location.traceId}
              onBack={() => {
                window.location.hash =
                  "run/" + encodeURIComponent(location.traceId);
              }}
            />
          ) : location.runId || starting ? (
            <RunView
              key={location.runId || "starting"}
              id={location.runId}
              starting={starting}
              startingMode={launchMode}
              initial={initialRun?.id === location.runId ? initialRun : null}
              workflows={config.data?.workflows ?? []}
              onOpen={openRun}
              onBack={() => viewCases()}
            />
          ) : (
            <>
              {location.page === "overview" && (
                <FinanceOverview
                  {...workspaceProps}
                  onViewCases={viewCases}
                  onInbox={() => navigate("documents")}
                />
              )}
              {location.page === "cases" && (
                <BusinessCasesView
                  {...workspaceProps}
                  view={caseView.view}
                  area={caseView.area}
                  onFilter={viewCases}
                  onInbox={() => navigate("documents")}
                />
              )}
              {location.page === "documents" && (
                <DocumentInbox
                  runs={workspaceProps.runs}
                  cases={cases}
                  onOpen={openRun}
                  loading={casesLoading}
                  error={caseError}
                  retry={() => setCaseVersion((v) => v + 1)}
                  documentId={location.documentId}
                  partition={location.partition}
                  onSelect={selectDocument}
                  onProcess={(item) =>
                    void launch({
                      case_id: item.case_id,
                      partition: item.partition,
                      mode: "live",
                      purpose: "business",
                    })
                  }
                />
              )}
              {location.page === "approvals" && (
                <Approvals
                  onOpen={openRun}
                  selectedId={location.approvalId}
                  onChanged={activity.reload}
                />
              )}
              {location.page === "evals" && (
                <Evals
                  runs={workspaceProps.runs}
                  config={config.data}
                  starting={starting}
                  onLaunch={(body) => void launch({ ...body, purpose: "test" })}
                  onOpen={openRun}
                  initialTab={location.evalTab}
                />
              )}
            </>
          )}
          <footer className="page-footer">
            <span>
              <Workflow size={13} />
              FlowPilot <span className="footer-separator">/</span>Intelligent
              Enterprise Automation
            </span>
            <span>
              <ShieldCheck size={13} />
              Fictional records · Simulated business changes
            </span>
          </footer>
        </main>
      </div>
      {mobileNav && (
        <button
          className="mobile-close icon-button"
          aria-label="Close navigation"
          onClick={() => setMobileNav(false)}
        >
          <X />
        </button>
      )}
    </div>
  );
}
