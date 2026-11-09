import { useEffect, useState } from "react";
import {
  Activity,
  ArrowUpRight,
  Boxes,
  ChevronDown,
  Command,
  FlaskConical,
  GitBranch,
  History,
  LayoutDashboard,
  Menu,
  PanelLeftClose,
  Plus,
  Radio,
  ShieldCheck,
  Workflow,
  X,
} from "lucide-react";
import type { Config, InboxCase, Mode, Page, Run } from "./types";
import { api, errorMessage } from "./api";
import { ErrorNotice, useResource } from "./shared";
import Investigation from "./Investigation";
import RunView from "./RunView";
import { Evaluations, Registry, RunHistory } from "./Screens";
const nav: { id: Page; label: string; icon: typeof Activity }[] = [
  { id: "investigations", label: "Investigations", icon: LayoutDashboard },
  { id: "history", label: "Run history", icon: History },
  { id: "evaluation", label: "Evaluation", icon: FlaskConical },
  { id: "registry", label: "Tool registry", icon: Boxes },
];
function decodeId(value: string) {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}
function route() {
  const hash = window.location.hash.slice(1);
  if (hash.startsWith("run/"))
    return { page: "investigations" as Page, runId: decodeId(hash.slice(4)) };
  return {
    page: nav.some((n) => n.id === hash)
      ? (hash as Page)
      : ("investigations" as Page),
    runId: "",
  };
}
export default function App() {
  const [location, setLocation] = useState(route);
  const [mobileNav, setMobileNav] = useState(false);
  const [starting, setStarting] = useState(false);
  const [launchMode, setLaunchMode] = useState<Mode>("simulation");
  const [initialRun, setInitialRun] = useState<Run | null>(null);
  const [launchError, setLaunchError] = useState("");
  const config = useResource<Config>("/config");
  const health = useResource<{ status: string; name: string }>(
    "/health",
    () => true,
    15000,
  );
  const [cases, setCases] = useState<InboxCase[]>([]);
  const [casesLoading, setCasesLoading] = useState(true);
  const [caseError, setCaseError] = useState("");
  const [caseVersion, setCaseVersion] = useState(0);
  useEffect(() => {
    const update = () => {
      setLocation(route());
      setMobileNav(false);
      window.scrollTo(0, 0);
    };
    window.addEventListener("hashchange", update);
    return () => window.removeEventListener("hashchange", update);
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    setCasesLoading(true);
    setCaseError("");
    void Promise.allSettled(
      (["train", "validation", "test"] as const).map((partition) =>
        api<{ cases: InboxCase[]; total: number }>(
          `/cases?partition=${partition}`,
          undefined,
          controller.signal,
        ),
      ),
    ).then((results) => {
      if (controller.signal.aborted) return;
      setCases(
        results.flatMap((r) => (r.status === "fulfilled" ? r.value.cases : [])),
      );
      const failures = results.flatMap((r, i) =>
        r.status === "rejected"
          ? [`${["Train", "Validation", "Test"][i]}: ${errorMessage(r.reason)}`]
          : [],
      );
      setCaseError(failures.join(" "));
      setCasesLoading(false);
    });
    return () => controller.abort();
  }, [caseVersion]);
  function navigate(page: Page) {
    window.location.hash = page;
    setMobileNav(false);
  }
  function openRun(run: Run) {
    setInitialRun(run);
    window.location.hash = `run/${encodeURIComponent(run.id)}`;
  }
  async function launch(body: object) {
    setLaunchMode((body as { mode: Mode }).mode);
    setLaunchError("");
    setStarting(true);
    try {
      const run = await api<Run>("/runs", body);
      openRun(run);
    } catch (e) {
      setLaunchError(errorMessage(e));
    } finally {
      setStarting(false);
    }
  }
  const connected = !!health.data && !health.error;
  const activeTitle =
    starting || location.runId
      ? "Investigation workspace"
      : nav.find((n) => n.id === location.page)?.label;
  useEffect(() => {
    document.title = `${activeTitle ?? "Operations console"} · FlowPilot`;
  }, [activeTitle]);
  return (
    <div className="app-shell">
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
      <aside className={`sidebar ${mobileNav ? "open" : ""}`}>
        <a href="#investigations" className="brand" aria-label="FlowPilot home">
          <span className="brand-symbol">
            <Workflow size={25} />
          </span>
          <span>
            FlowPilot<span className="brand-dot">.</span>
          </span>
        </a>
        <button
          className="workspace-switch"
          onClick={() => navigate("investigations")}
        >
          <span className="workspace-avatar">HM</span>
          <span>
            <strong>Harbourline Mutual</strong>
            <small>Finance workspace</small>
          </span>
          <ChevronDown size={14} />
        </button>
        <div className="nav-caption">WORKSPACE</div>
        <nav aria-label="Main navigation">
          {nav.map((item) => (
            <a
              key={item.id}
              href={`#${item.id}`}
              aria-current={location.page === item.id ? "page" : undefined}
              className={`nav-item ${location.page === item.id ? "active" : ""}`}
              onClick={() => setMobileNav(false)}
            >
              <item.icon size={18} />
              <span>{item.label}</span>
              {location.page === item.id && <span className="nav-active-dot" />}
            </a>
          ))}
        </nav>
        <div className="sidebar-note">
          <span className="sidebar-note-icon">
            <GitBranch size={19} />
          </span>
          <h3>Every decision, connected.</h3>
          <p>From incoming signal to evidence-backed outcome.</p>
          <span>
            Built for accountable automation <ArrowUpRight size={12} />
          </span>
        </div>
        <div className="sidebar-bottom">
          <div className="local-label">
            <span className={`connection-dot ${connected ? "online" : ""}`} />
            {connected
              ? "Local backend connected"
              : health.loading
                ? "Connecting to backend"
                : "Backend unavailable"}
          </div>
          <div className="profile">
            <span className="profile-avatar">
              <Command size={17} />
            </span>
            <span>
              <strong>Local workspace</strong>
              <small>Private by design</small>
            </span>
            <PanelLeftClose size={16} />
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
            <span className="local-pill">
              <Radio size={12} /> Local environment
            </span>
            <div className="topbar-divider" />
            <span className="topbar-avatar">HM</span>
          </div>
        </header>
        <main id="main-content" tabIndex={-1}>
          {config.error && (
            <ErrorNotice
              message={`Configuration unavailable. ${config.error}`}
              retry={config.reload}
            />
          )}
          {launchError && (
            <ErrorNotice
              message={`Could not start investigation. ${launchError}`}
            />
          )}
          {location.page === "investigations" && (
            <>
              {!location.runId && (
                <div hidden={starting}>
                  <Investigation
                    cases={cases}
                    loading={casesLoading}
                    error={caseError}
                    retry={() => setCaseVersion((v) => v + 1)}
                    config={config.data}
                    onLaunch={launch}
                  />
                </div>
              )}
              {(location.runId || starting) && (
                <RunView
                  key={location.runId || "starting"}
                  id={location.runId}
                  starting={starting}
                  startingMode={launchMode}
                  initial={
                    initialRun?.id === location.runId ? initialRun : null
                  }
                  workflows={config.data?.workflows ?? []}
                  onOpen={openRun}
                  onBack={() => navigate("investigations")}
                />
              )}
            </>
          )}
          {location.page === "history" && <RunHistory onOpen={openRun} />}
          {location.page === "evaluation" && (
            <Evaluations config={config.data} onOpenRun={openRun} />
          )}
          {location.page === "registry" && <Registry />}
          <footer className="page-footer">
            <span>
              <Workflow size={13} /> FlowPilot{" "}
              <span className="footer-separator">/</span> Intelligent Enterprise
              Automation
            </span>
            <span>
              <ShieldCheck size={13} /> Evidence before action
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
      {location.page !== "investigations" && (
        <button
          className="new-investigation-fab"
          onClick={() => navigate("investigations")}
        >
          <Plus size={18} />
          <span>New investigation</span>
        </button>
      )}
    </div>
  );
}
