import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createServer } from "vite";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

const server = await createServer({
  server: { middlewareMode: true, hmr: false },
  optimizeDeps: { noDiscovery: true, include: [] },
  appType: "custom",
});
const presentation = await server.ssrLoadModule("/src/presentation.ts");
const { default: RunView } = await server.ssrLoadModule("/src/RunView.tsx");
const screens = await server.ssrLoadModule("/src/Screens.tsx");
const { api } = await server.ssrLoadModule("/src/api.ts");
const business = await server.ssrLoadModule("/src/business.ts");
const workspaceUI = await server.ssrLoadModule("/src/Workspace.tsx");
test.after(() => server.close());
const recordings = [
  "supplier_fraud",
  "regulatory_compliance",
  "gdpr_data",
  "it_asset",
  "contract_risk",
];
const traces = recordings.map((name) =>
  JSON.parse(
    readFileSync(
      new URL(`../../examples/traces/${name}.json`, import.meta.url),
      "utf8",
    ),
  ),
);
const render = (run) =>
  renderToStaticMarkup(
    createElement(RunView, {
      id: run.id,
      initial: run,
      starting: false,
      startingMode: "live",
      workflows: [],
      onOpen: () => {},
      onBack: () => {},
    }),
  );

test("all five reports put the business result before collapsible evidence and execution", () => {
  for (const run of traces) {
    const html = render(run);
    assert.ok(
      html.indexOf("Findings, next steps") < html.indexOf("What to do next"),
    );
    assert.ok(
      html.indexOf("What to do next") < html.indexOf("Supporting evidence"),
    );
    assert.equal(
      (html.match(/<details class="panel result-disclosure"/g) ?? []).length,
      5,
    );
    assert.doesNotMatch(
      html,
      /<details[^>]*class="panel result-disclosure"[^>]*open/,
    );
    const requestSection = html.slice(
      html.indexOf("About this request"),
      html.indexOf("Checks performed"),
    );
    assert.doesNotMatch(
      requestSection,
      /JEV|gemini|agy|confidence|uncertainty|uncalibrated/i,
    );
    // Every exact citation is still available on expansion; the unmodified report is preserved.
    for (const evidence of run.outcome.evidence)
      assert.ok(html.includes(evidence.record_id));
    assert.ok(html.includes("Original business report and action records"));
  }
});

test("presentation expands jargon without losing negations, amounts, dates or unmatched references", () => {
  const text = presentation.businessText(
    "MFA is not enabled on SYS-ABC12345; do not delete records under legal hold. Keep £25,000 until 2026-10-08.",
  );
  assert.match(text, /multi-factor authentication/);
  assert.match(text, /not enabled/);
  assert.match(text, /do not delete records under legal hold/);
  assert.match(text, /SYS-ABC12345/);
  assert.match(text, /£25,000/);
  assert.match(text, /8 October 2026/);
});

test("names come only from successful observations and presentation does not modify the saved trace", () => {
  const run = structuredClone(traces[0]);
  run.events = [
    {
      id: "test-failed",
      sequence: 1,
      kind: "tool_result",
      result: { ok: false, data: { id: "SYS-ABC12345", name: "Unverified" } },
    },
    {
      id: "test-success",
      sequence: 2,
      kind: "tool_result",
      result: {
        ok: true,
        data: { id: "SYS-DEF12345", name: "Accounts archive" },
      },
    },
  ];
  const original = JSON.stringify(run);
  const names = presentation.referenceNames(run);
  assert.equal(names.has("SYS-ABC12345"), false);
  assert.equal(
    presentation.businessText("Check SYS-DEF12345", names),
    "Check Accounts archive",
  );
  render(run);
  assert.equal(JSON.stringify(run), original);
});

test("recommended and pending actions never appear as completed changes", () => {
  const run = structuredClone(traces[0]);
  run.events = [];
  run.outcome.actions = [{ action: "place_payment_hold" }];
  run.approvals = [
    {
      request_id: "test",
      tool: "place_payment_hold",
      args: {},
      justification: "Check payment",
      status: "pending",
    },
  ];
  assert.equal(presentation.completedWork(run).applied, 0);
  assert.doesNotMatch(presentation.outcomeTitle(run), /applied/);
  run.approvals[0].status = "executed";
  run.approvals[0].result = { ok: false };
  assert.equal(presentation.completedWork(run).applied, 0);
  run.approvals[0].result = { ok: true };
  assert.equal(presentation.completedWork(run).applied, 1);
  assert.match(
    presentation.outcomeTitle(run),
    /applied to the example records/,
  );
});

test("replayed, running, failed and cancelled investigations keep approval controls unavailable", () => {
  const run = structuredClone(traces[0]);
  run.approvals = [
    {
      request_id: "test",
      tool: "place_payment_hold",
      args: {},
      justification: "Check payment",
      status: "pending",
    },
  ];
  for (const status of ["running", "failed", "cancelled"]) {
    run.status = status;
    assert.doesNotMatch(render(run), />Approve simulated change</);
  }
  run.status = "awaiting_approval";
  assert.doesNotMatch(render(run), />Approve simulated change</);
  assert.match(render(run), /Open approvals/);
  assert.match(render(run), /#approvals\/test/);
  run.mode = "replay";
  run.source_status = "failed";
  const html = render(run);
  assert.doesNotMatch(html, />Approve simulated change</);
  assert.match(html, /Failed/);
  assert.match(html, /Nothing is running or being changed/);
});

test("failed checks are not described as successful evidence collection", () => {
  assert.match(
    presentation.resultSummary({
      result: { ok: false, error: { code: "NOT_FOUND" } },
    }),
    /No matching record/,
  );
  assert.match(
    presentation.resultSummary({
      result: { ok: false, error: { code: "APPROVAL_REQUIRED" } },
    }),
    /not permitted/,
  );
  const run = {
    ...traces[0],
    outcome: null,
    status: "failed",
    error: "INVALID_EVIDENCE: citation not observed",
  };
  const html = render(run);
  assert.match(html, /No verified outcome available/);
  assert.match(html, /no final conclusion was accepted/);
  assert.doesNotMatch(html, /What to do next/);
});

test("API requests stay within the same app when shared under a URL prefix", async () => {
  const original = globalThis.fetch;
  const requests = [];
  globalThis.fetch = async (path, options) => {
    requests.push({ path, options });
    return new Response('{"status":"ok"}', {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };
  try {
    assert.deepEqual(await api("/health"), { status: "ok" });
    await api("/runs", { mode: "simulation" });
    for (const { path } of requests) {
      assert.equal(
        new URL(path, "http://127.0.0.1:8766/").pathname.startsWith("/api/"),
        true,
      );
      assert.equal(
        new URL(
          path,
          "https://console.example.test:8443/flowpilot/",
        ).pathname.startsWith("/flowpilot/api/"),
        true,
      );
    }
    assert.equal(requests[1].options.method, "POST");
    assert.equal(requests[1].options.body, '{"mode":"simulation"}');
  } finally {
    globalThis.fetch = original;
  }
});

const sampleDocuments = [
  {
    case_id: "doc-invoice",
    partition: "train",
    title: "Please pay today",
    preview: "",
    media_type: "application/json",
    received_at: "2026-09-13T00:37:00Z",
    showcase: true,
    workflow: "supplier_fraud",
    document:
      JSON.stringify({
        subject: "Please pay today",
        sender: "Alex <alex@example.test>",
        body: "Please check this invoice.",
        attributes: { "Invoice number": "SI-12345" },
      }) +
      "\n\n--- Attachment: invoice.txt ---\nTotal payable: £36,900.00\n\n--- Attachment: second-copy.txt ---\nTotal payable: £36,900.00",
  },
  {
    case_id: "doc-customer",
    partition: "train",
    title: "Correct my address",
    preview: "",
    media_type: "application/x-ndjson",
    received_at: "2026-09-13T00:37:00Z",
    showcase: false,
    workflow: null,
    document: [
      {
        kind: "intake",
        subject: "Correct my address",
        sender: "Sam <sam@example.test>",
      },
      { kind: "narrative", text: "Please update my address." },
      { kind: "attribute", name: "New address", value: "41 Priory Close" },
    ]
      .map(JSON.stringify)
      .join("\n"),
  },
];

test("business totals exclude tests and repeat replays while preserving older pending decisions", () => {
  const run = structuredClone(traces[0]);
  run.mode = "live";
  run.status = "awaiting_approval";
  run.approvals = [
    {
      request_id: "pending-original",
      tool: "place_payment_hold",
      args: {},
      justification: "Review",
      status: "pending",
    },
  ];
  const newer = {
    ...structuredClone(run),
    id: "newer",
    status: "completed",
    created_at: "2027-01-01T00:00:00Z",
    approvals: [],
  };
  const replay = {
    ...structuredClone(run),
    id: "replay",
    mode: "replay",
    source_mode: "live",
    source_status: "awaiting_approval",
    status: "completed",
  };
  const tests = ["test", "evaluation"].map((purpose) => ({
    ...structuredClone(run),
    id: purpose,
    purpose,
  }));
  const entries = business.businessCases([
    run,
    newer,
    replay,
    ...tests,
    { ...run, id: "offline", mode: "simulation" },
  ]);
  assert.equal(entries.length, 1);
  assert.equal(entries[0].attempts, 2);
  assert.equal(entries[0].run.id, "newer");
  assert.equal(entries[0].decisions.length, 1);
  assert.equal(entries[0].decisions[0].run.id, run.id);
  assert.equal(business.caseState(entries[0]), "decisions");
});

test("saved examples have honest source statuses and never create actionable approvals", () => {
  const replay = {
    ...structuredClone(traces[0]),
    mode: "replay",
    source_mode: "live",
    source_status: "awaiting_approval",
    status: "completed",
  };
  const entries = business.businessCases([replay]);
  assert.equal(entries.length, 1);
  assert.equal(entries[0].decisions.length, 0);
  assert.equal(business.caseState(entries[0]), "followup");
  assert.equal(
    business.businessCases([{ ...replay, purpose: "evaluation" }]).length,
    0,
  );
});

test("document readers preserve business fields and duplicate attachments without exposing transport JSON", () => {
  const original = sampleDocuments[0].document;
  const invoice = business.readableDocument(sampleDocuments[0]);
  assert.equal(invoice.sender, "Alex <alex@example.test>");
  assert.equal(invoice.body, "Please check this invoice.");
  assert.equal(invoice.fields[0].value, "SI-12345");
  assert.equal(invoice.attachments.length, 2);
  assert.match(invoice.attachments[1].text, /£36,900.00/);
  assert.equal(sampleDocuments[0].document, original);
  const customer = business.readableDocument(sampleDocuments[1]);
  assert.equal(customer.body, "Please update my address.");
  assert.equal(customer.fields[0].value, "41 Priory Close");
  const email = business.readableDocument({
    ...sampleDocuments[0],
    document:
      "From: Pat <pat@example.test>\nSubject: Invoice\nMIME-Version: 1.0\n\nPlease check the amount.",
  });
  assert.equal(email.sender, "Pat <pat@example.test>");
  assert.equal(email.body, "Please check the amount.");
});

test("business routes include Evals and retain legacy developer deep links", () => {
  assert.equal(business.workspaceRoute("", false).page, "overview");
  assert.equal(
    business.workspaceRoute("#investigations", false).page,
    "overview",
  );
  assert.equal(business.workspaceRoute("#history", false).page, "cases");
  for (const page of ["workbench", "evaluation", "registry"]) {
    assert.equal(business.workspaceRoute("#" + page, false).page, "overview");
    assert.equal(business.workspaceRoute("#" + page, true).page, "evals");
  }
  assert.equal(business.workspaceRoute("#run/abc", false).runId, "abc");
  assert.equal(
    business.workspaceRoute("#document/train/doc-invoice", false).documentId,
    "doc-invoice",
  );
});

test("the home page presents findings and decisions without launch or JSON controls", () => {
  const html = renderToStaticMarkup(
    createElement(workspaceUI.FinanceOverview, {
      runs: traces,
      cases: sampleDocuments,
      workflows: [],
      loading: false,
      error: "",
      retry: () => {},
      onOpen: () => {},
      onViewCases: () => {},
      onInbox: () => {},
    }),
  );
  assert.match(html, /HARBOURLINE MUTUAL \/ OPERATIONS/);
  assert.match(html, /<h1>Overview<\/h1>/);
  assert.match(html, /Waiting for your decision/);
  assert.match(html, /Latest case findings/);
  assert.match(html, /Review decision/);
  assert.doesNotMatch(
    html,
    /Input inspector|Execution mode|Start investigation|gemini|JEV|&quot;attributes&quot;/,
  );
});

test("the inbox renders correspondence as text and does not ask the reader to choose a workflow", () => {
  const evil = {
    ...sampleDocuments[0],
    document: JSON.stringify({
      sender: "Alex",
      body: '<script>alert("untrusted")</script>',
      attributes: { "Invoice number": "SI-12345" },
    }),
  };
  const html = renderToStaticMarkup(
    createElement(workspaceUI.DocumentInbox, {
      runs: [],
      cases: [evil],
      loading: false,
      error: "",
      retry: () => {},
      documentId: "",
      partition: "",
      onSelect: () => {},
      onProcess: () => {},
      onOpen: () => {},
    }),
  );
  assert.match(html, /Review document/);
  assert.match(html, /SI-12345/);
  assert.match(html, /&lt;script&gt;/);
  assert.doesNotMatch(
    html,
    /<script>|Execution mode|Choose an investigation|&quot;attributes&quot;/,
  );
});

test("identical custom submissions are one case, while different documents remain separate", () => {
  const run = {
    ...structuredClone(traces[0]),
    mode: "live",
    case_id: "CUSTOM-ONE",
    document_fingerprint: "same-content",
  };
  const retry = { ...structuredClone(run), id: "retry", case_id: "CUSTOM-TWO" };
  const different = {
    ...structuredClone(run),
    id: "different",
    case_id: "CUSTOM-THREE",
    document_fingerprint: "other-content",
  };
  const entries = business.businessCases([run, retry, different]);
  assert.equal(entries.length, 2);
  assert.equal(entries.find((c) => c.key.endsWith("same-content")).attempts, 2);
});

test("manual reviews count as business decisions and trace/evals have distinct routes", () => {
  const run = structuredClone(traces[4]);
  run.mode = "live";
  run.status = "awaiting_approval";
  run.approvals = [];
  run.manual_reviews = [
    {
      request_id: "privacy-review",
      title: "Privacy assessment",
      department: "Privacy",
      status: "pending",
      reason: "Overseas hosting",
      hold_scope: "Hosting change",
      next_step: "Record decision",
    },
  ];
  run.business_route = {
    path: "human_review",
    label: "Held for human review",
    detail: "The hosting change is paused.",
  };
  const entry = business.businessCases([run])[0];
  assert.equal(entry.decisions.length, 1);
  assert.equal(business.caseState(entry), "decisions");
  const html = render(run);
  assert.match(html, /Held for human review/);
  assert.match(html, /#approvals\/privacy-review/);
  assert.match(html, /#trace\//);
  assert.doesNotMatch(html, />Approve simulated change</);
  assert.equal(business.workspaceRoute("#trace/abc", false).traceId, "abc");
  assert.equal(
    business.workspaceRoute("#approvals/privacy-review", false).approvalId,
    "privacy-review",
  );
  assert.equal(
    business.workspaceRoute("#evals/guardrails", false).evalTab,
    "guardrails",
  );
  assert.equal(business.workspaceRoute("#evals", false).page, "evals");
});

test("Evals overview explains attempts and keeps the workbench in its own tab", async () => {
  const { default: Evals } = await server.ssrLoadModule("/src/Evals.tsx");
  const runs = [
    structuredClone(traces[0]),
    structuredClone(traces[0]),
    { ...structuredClone(traces[1]), mode: "replay" },
    { ...structuredClone(traces[2]), mode: "simulation" },
  ];
  runs[1].id = "second-attempt";
  runs[1].status = "failed";
  const html = renderToStaticMarkup(
    createElement(Evals, {
      runs,
      config: null,
      starting: false,
      onLaunch: () => {},
      onOpen: () => {},
      initialTab: "overview",
    }),
  );
  assert.match(html, /Reviews, recordings and tests/);
  assert.doesNotMatch(html, /Choose a review|Input inspector|Execution mode/);
  assert.doesNotMatch(html, /<h2>Test workbench<\/h2>/);
  const workbenchHtml = renderToStaticMarkup(
    createElement(Evals, {
      runs,
      config: null,
      starting: false,
      onLaunch: () => {},
      onOpen: () => {},
      initialTab: "workbench",
    }),
  );
  assert.match(workbenchHtml, /Choose a review/);
  assert.match(workbenchHtml, /Input inspector/);
  assert.match(html, /2<\/span><h3>AI reviews/);
  assert.match(
    html.replace(/<[^>]*>/g, " ").replace(/\s+/g, " "),
    /1 distinct document/,
  );
  assert.match(html, /Only scored evaluation batches compare results/);
  assert.match(html, /Guardrail tests/);
  assert.match(html, /Change history/);
  for (const tab of [
    "quality",
    "guardrails",
    "evolution",
    "workbench",
    "history",
    "registry",
  ]) {
    assert.doesNotThrow(() =>
      renderToStaticMarkup(
        createElement(Evals, {
          runs,
          config: null,
          starting: false,
          onLaunch: () => {},
          onOpen: () => {},
          initialTab: tab,
        }),
      ),
    );
  }
});

test("successful reports never render the failure panel", () => {
  for (const run of traces) {
    const html = render(run);
    assert.doesNotMatch(html, /class="panel failure-panel"/);
    assert.doesNotMatch(html, /Failure summary/);
  }
  const completedReplay = {
    ...structuredClone(traces[0]),
    mode: "replay",
    status: "completed",
    source_mode: "live",
    source_status: "completed",
  };
  assert.doesNotMatch(render(completedReplay), /class="panel failure-panel"/);
});

test("exact cited-unconfirmed Live API error is prominent without opening technical JSON and avoids false claims", () => {
  const failedRun = {
    ...structuredClone(traces[0]),
    id: "d04405e9a9ea48ec8ca2ad0b89f59645",
    case_id: "CASE-PROC-01",
    title: "Procurement review · invoice and signed contract",
    mode: "live",
    status: "failed",
    source_run_id: undefined,
    outcome: null,
    error:
      "ValueError: Conclusion cited records not present in observed tool results: SUP-E8E17955",
    approvals: [
      {
        request_id: "APR-123456",
        tool: "place_payment_hold",
        args: {},
        justification: "Hold payment pending verification",
        status: "pending",
      },
    ],
    events: [
      {
        id: "ev-review",
        sequence: 1,
        kind: "tool_result",
        tool: "create_review_case",
        status: "completed",
        title: "create_review_case returned evidence",
        detail: "Business tool response · synthetic enterprise",
        timestamp: "2026-11-09T10:00:00Z",
        result: { ok: true, data: { review_case_id: "REV-001" } },
      },
    ],
  };

  const html = render(failedRun);
  const failureIndex = html.indexOf("failure-panel");
  const detailsIndex = html.indexOf("Explore the details");
  assert.ok(failureIndex > -1);
  assert.ok(detailsIndex > failureIndex);

  assert.match(html, /Review stopped: unconfirmed evidence/);
  assert.match(html, /Unconfirmed evidence/);
  assert.match(html, /SUP-E8E17955/);
  assert.match(html, /Live API failure/);
  assert.match(html, /How this review ran/);
  assert.doesNotMatch(html, />Provenance</);
  assert.match(html, /evidence check rejected the final report/i);
  assert.doesNotMatch(html, /not an AI provider outage/i);
  assert.match(html, /no final conclusion was accepted/i);
  assert.match(html, /No verified outcome available/);
  assert.match(html, /confirming lookup or retry/i);
  assert.match(html, /Raw technical error/);
  assert.match(html, /1 review case opened/);
  assert.match(
    html,
    /1 proposed change cannot be approved because this run failed/,
  );
  assert.doesNotMatch(html, />Approve simulated change</);
  assert.doesNotMatch(
    html,
    /invented|never appeared anywhere|record does not exist|doesn&#x27;t exist/i,
  );
  assert.doesNotMatch(html, /<details[^>]*class="failure-technical-details"[^>]*open/);
});

test("live vs simulation vs failed-source replay provenance is distinct and replays do not claim AI ran", () => {
  const baseFailed = {
    ...structuredClone(traces[0]),
    outcome: null,
    events: [],
    error: "RuntimeError: Tool call budget exhausted; no further actions executed.",
  };

  const liveHtml = render({ ...baseFailed, mode: "live", status: "failed" });
  assert.match(liveHtml, /Live API failure/);
  assert.match(liveHtml, /not a scripted simulation/i);

  const simHtml = render({
    ...baseFailed,
    mode: "simulation",
    status: "failed",
  });
  assert.match(simHtml, /Simulation failure/);
  assert.match(simHtml, /no Live AI calls were made/i);

  const replayLiveHtml = render({
    ...baseFailed,
    mode: "replay",
    status: "completed",
    source_run_id: "orig-1",
    source_mode: "live",
    source_status: "failed",
  });
  assert.match(replayLiveHtml, /Recorded replay of failed Live API run/);
  assert.match(replayLiveHtml, /Replaying did not run AI/);
  assert.match(replayLiveHtml, /Nothing is running or being changed/);

  const replaySimHtml = render({
    ...baseFailed,
    mode: "replay",
    status: "completed",
    source_run_id: "orig-2",
    source_mode: "simulation",
    source_status: "failed",
  });
  assert.match(replaySimHtml, /Recorded replay of failed simulation/);
  assert.match(replaySimHtml, /Replaying did not run AI/);
});

test("execution history displays concise failure reason directly on failed and failed-replay rows", () => {
  const liveFailed = {
    ...structuredClone(traces[0]),
    id: "d04405e9a9ea48ec8ca2ad0b89f59645",
    case_id: "CASE-LIVE-FAIL",
    title: "Procurement review · invoice and signed contract",
    mode: "live",
    status: "failed",
    outcome: null,
    error:
      "ValueError: Conclusion cited records not present in observed tool results: SUP-E8E17955",
  };
  const replayFailed = {
    ...structuredClone(traces[0]),
    id: "replay-failed-1",
    case_id: "CASE-REPLAY-FAIL",
    title: "Procurement replay",
    mode: "replay",
    status: "completed",
    source_run_id: "d04405e9a9ea48ec8ca2ad0b89f59645",
    source_mode: "live",
    source_status: "failed",
    outcome: null,
    error: liveFailed.error,
  };
  const unknownFailed = {
    ...structuredClone(traces[0]),
    id: "unknown-failed-1",
    case_id: "CASE-UNK-FAIL",
    title: "Unknown failure case",
    mode: "simulation",
    status: "failed",
    outcome: null,
    error: "RuntimeError: Upstream ledger lock contention on shard-4",
  };
  const okRun = {
    ...structuredClone(traces[0]),
    id: "ok-run-1",
    case_id: "CASE-OK",
    title: "Successful case",
    mode: "live",
    status: "completed",
  };

  const html = renderToStaticMarkup(
    createElement(screens.RunHistoryTable, {
      runs: [liveFailed, replayFailed, unknownFailed, okRun],
      onOpen: () => {},
    }),
  );

  const livePresentation = presentation.describeFailure(liveFailed);
  const replayPresentation = presentation.describeFailure(replayFailed);
  const unknownPresentation = presentation.describeFailure(unknownFailed);

  assert.ok(html.includes(livePresentation.historySummary));
  assert.match(html, /Unconfirmed evidence reference \(SUP-E8E17955\)/);
  assert.ok(html.includes(replayPresentation.historySummary));
  assert.match(html, /Source Live API run failed \(replay ran no AI\)/);
  assert.ok(html.includes(unknownPresentation.historySummary));
  assert.match(html, /Upstream ledger lock contention on shard-4/);
  // Successful row does not display a failure reason line.
  assert.equal((html.match(/history-failure-reason/g) ?? []).length, 3);
  // Persisted status badges remain intact for both failed and completed replay rows.
  assert.match(html, /status-failed/);
  assert.match(html, /status-completed/);
});

test("failure classification handles all categories, avoids incidental evidence misclassification, redacts secrets, and escapes HTML", () => {
  const schemaWithEvidence = presentation.describeFailure({
    mode: "live",
    error: "ValidationError: 'evidence' is a required property",
  });
  assert.equal(schemaWithEvidence.category, "validation");

  const valueSchemaWithEvidence = presentation.describeFailure({
    mode: "live",
    error:
      "ValueError: agy returned JSON that failed schema validation at outcome.evidence",
  });
  assert.equal(valueSchemaWithEvidence.category, "validation");

  const pydanticSchemaWithEvidence = presentation.describeFailure({
    mode: "live",
    error: "1 validation error for Outcome\nevidence\n  Field required",
  });
  assert.equal(pydanticSchemaWithEvidence.category, "validation");

  const schemaUnobservedMention = presentation.describeFailure({
    mode: "live",
    error: "Schema error at outcome.evidence: cited field not observed in schema",
  });
  assert.equal(schemaUnobservedMention.category, "validation");

  assert.equal(
    presentation.describeFailure({
      mode: "live",
      error: "AIError: agy reported a quota or rate limit (429 RESOURCE_EXHAUSTED)",
    }).category,
    "quota",
  );
  assert.equal(
    presentation.describeFailure({
      mode: "live",
      error: "AIError: agy is not signed in. Sign in and retry.",
    }).category,
    "auth",
  );
  for (const budgetError of [
    "Investigation reached its configured wall-clock limit.",
    "RuntimeError: Iteration budget exhausted.",
    "RuntimeError: Tool call budget exhausted; no further actions executed.",
    "RuntimeError: Model call budget exhausted; no unverified conclusion was generated.",
  ]) {
    assert.equal(
      presentation.describeFailure({ mode: "live", error: budgetError })
        .category,
      "budget",
    );
  }
  assert.equal(
    presentation.describeFailure({
      mode: "live",
      error: "TOOL_FAILURE: KeyError: 'supplier_id'",
    }).category,
    "tool",
  );
  assert.equal(
    presentation.describeFailure({
      mode: "live",
      error: "AIError: Claude's service was overloaded (503).",
    }).category,
    "provider",
  );

  const absent = presentation.describeFailure({
    mode: "live",
    error: undefined,
  });
  assert.equal(absent.category, "missing");
  assert.match(absent.explanation, /no error message was recorded/i);
  assert.match(absent.historySummary, /No failure reason was recorded/i);

  const unknown = presentation.describeFailure({
    mode: "live",
    error: "CustomError: Unexpected store write conflict on partition-9",
  });
  assert.equal(unknown.category, "unknown");
  assert.match(
    unknown.explanation,
    /Unexpected store write conflict on partition-9/,
  );
  assert.match(
    unknown.historySummary,
    /Unexpected store write conflict on partition-9/,
  );

  const unknownNotRequested = presentation.describeFailure({
    mode: "live",
    error: "ValueError: Returned vendor was not the requested entity",
  });
  assert.equal(unknownNotRequested.category, "unknown");
  assert.match(
    unknownNotRequested.explanation,
    /Returned vendor was not the requested entity/,
  );

  // Construct JEV-shaped credential at runtime so no key-shaped literal appears in source.
  const jevKeyPrefix = ["api", "key"].join("");
  const jevKeyShort = [
    jevKeyPrefix,
    "0123456789abcdef",
    "fedcba9876543210".repeat(2),
  ].join("_");
  const jevKeyMid = [
    jevKeyPrefix,
    "a1b2c3d4e5f60718".repeat(2),
    "9988776655443322".repeat(4),
  ].join("_");
  const jevKeyMax = [
    jevKeyPrefix,
    "A1B2C3D4E5F60718".repeat(4),
    "0011223344556677".repeat(8),
  ].join("_");
  const nonSecretToken = `${jevKeyPrefix}_short_nothex`;

  assert.equal(
    presentation.sanitizeErrorText(`Bad token ${jevKeyShort} and ${jevKeyMax}`),
    "Bad token [redacted] and [redacted]",
  );
  assert.equal(
    presentation.sanitizeErrorText(`Kept ${nonSecretToken} in message`),
    `Kept ${nonSecretToken} in message`,
  );

  const unknownWithJevKey = presentation.describeFailure({
    mode: "live",
    error: `CustomError: Upstream webhook rejected ${jevKeyMid} for invoice check`,
  });
  assert.equal(unknownWithJevKey.category, "unknown");
  assert.equal(unknownWithJevKey.rawError.includes(jevKeyMid), false);
  assert.match(
    unknownWithJevKey.explanation,
    /Upstream webhook rejected \[redacted\] for invoice check/,
  );

  const fakeSkToken = ["sk", ["secret", "1234567890"].join("")].join("-");
  const fakeBearerHeader = ["Bearer", ["topSecret", "Token", "999"].join("")].join(" ");
  const fakeApiKeyAssignment = `${["api", "key"].join("_")}="${["myPrivate", "Key", "123"].join("")}"`;

  const untrustedRun = {
    ...structuredClone(traces[0]),
    mode: "live",
    status: "failed",
    outcome: null,
    error: `Error with ${fakeSkToken} ${fakeBearerHeader} ${fakeApiKeyAssignment} ${jevKeyMid} <script>alert("xss")</script>`,
    events: [
      {
        id: "ev-err",
        sequence: 1,
        kind: "error",
        status: "failed",
        title: "Step failed",
        detail: `Worker failed with ${jevKeyShort}`,
        timestamp: "2026-11-09T10:00:00Z",
      },
    ],
  };
  const untrustedHtml = render(untrustedRun);
  assert.doesNotMatch(untrustedHtml, /sk-secret1234567890/);
  assert.doesNotMatch(untrustedHtml, /topSecretToken999/);
  assert.doesNotMatch(untrustedHtml, /myPrivateKey123/);
  assert.equal(untrustedHtml.includes(jevKeyMid), false);
  assert.equal(untrustedHtml.includes(jevKeyShort), false);
  assert.doesNotMatch(untrustedHtml, /apikey_/);
  assert.match(untrustedHtml, /\[redacted\]/);
  assert.doesNotMatch(untrustedHtml, /<script>alert/);
  assert.match(untrustedHtml, /&lt;script&gt;alert/);
});
