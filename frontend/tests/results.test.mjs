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

const { api } = await server.ssrLoadModule("/src/api.ts");

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
