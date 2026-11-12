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
      html.indexOf("Business outcome") < html.indexOf("What to do next"),
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
      html.indexOf("Investigation steps"),
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
  assert.match(render(run), /Approve simulated change/);
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

test("normal routes lead to business pages; developer screens require explicit opt-in", () => {
  assert.equal(business.workspaceRoute("", false).page, "overview");
  assert.equal(
    business.workspaceRoute("#investigations", false).page,
    "overview",
  );
  assert.equal(business.workspaceRoute("#history", false).page, "cases");
  for (const page of ["workbench", "evaluation", "registry"]) {
    assert.equal(business.workspaceRoute("#" + page, false).page, "overview");
    assert.equal(business.workspaceRoute("#" + page, true).page, page);
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
  assert.match(html, /Finance overview/);
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
  assert.match(html, /Process document/);
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
