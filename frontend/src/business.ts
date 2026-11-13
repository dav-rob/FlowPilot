import type { Approval, InboxCase, ManualReview, Page, Run } from "./types";
import { businessText, outcomeTitle } from "./presentation";

export type CaseView = "all" | "decisions" | "followup" | "active" | "complete";
export interface BusinessCase {
  key: string;
  run: Run;
  attempts: number;
  decisions: { run: Run; approval: Approval | ManualReview }[];
}
export const documentKey = (c: {
  case_id?: string;
  partition?: string;
  id?: string;
  document_fingerprint?: string;
}) =>
  [
    c.partition ?? "train",
    c.case_id?.startsWith("CUSTOM-") && c.document_fingerprint
      ? "document:" + c.document_fingerprint
      : (c.case_id ?? c.id),
  ].join(":");
const businessRecord = (run: Run) => !run.purpose || run.purpose === "business";

// One case per document. Replays never add actionable approvals.
export function businessCases(runs: Run[]): BusinessCase[] {
  const groups = new Map<string, BusinessCase>();
  const originals = runs.filter((r) => r.mode === "live" && businessRecord(r));
  for (const run of [...originals].sort((a, b) =>
    b.created_at.localeCompare(a.created_at),
  )) {
    const key = documentKey(run);
    let entry = groups.get(key);
    if (!entry) {
      entry = { key, run, attempts: 0, decisions: [] };
      groups.set(key, entry);
    }
    entry.attempts++;
    if (run.status === "awaiting_approval") {
      for (const approval of [
        ...(run.approvals ?? []),
        ...(run.manual_reviews ?? []),
      ]) {
        if (approval.status === "pending")
          entry.decisions.push({ run, approval });
      }
    }
  }
  // A fresh installation can show saved examples, labelled and read-only.
  for (const run of [...runs].sort((a, b) =>
    b.created_at.localeCompare(a.created_at),
  )) {
    const key = documentKey(run);
    if (
      run.mode === "replay" &&
      run.source_mode === "live" &&
      businessRecord(run) &&
      !groups.has(key)
    ) {
      groups.set(key, { key, run, attempts: 0, decisions: [] });
    }
  }
  return [...groups.values()].sort((a, b) =>
    b.run.created_at.localeCompare(a.run.created_at),
  );
}
export function caseState(entry: BusinessCase): Exclude<CaseView, "all"> {
  if (entry.decisions.length) return "decisions";
  const status =
    entry.run.mode === "replay" ? entry.run.source_status : entry.run.status;
  if (
    entry.run.mode !== "replay" &&
    (status === "running" || status === "queued")
  )
    return "active";
  if (
    status === "failed" ||
    status === "cancelled" ||
    status === "awaiting_approval"
  )
    return "followup";
  const outcome = entry.run.outcome;
  if (
    outcome &&
    (outcome.unresolved?.length ||
      outcome.requires_approval ||
      (["high", "critical"].includes(outcome.risk) &&
        outcome.recommendations?.length))
  )
    return "followup";
  return "complete";
}
export const caseStateLabel = (entry: BusinessCase) =>
  ({
    decisions: "Your decision needed",
    followup: "Follow-up needed",
    active: "Checking records",
    complete: "Checks complete",
  })[caseState(entry)];
export function findingTitle(run: Run): string {
  if (
    run.status === "failed" ||
    (run.mode === "replay" && run.source_status === "failed")
  )
    return "Checks could not be completed";
  if (run.status === "cancelled") return "Checks were stopped";
  if (!run.outcome) return "Reviewing the document and relevant records";
  return outcomeTitle(run);
}
export function shortFinding(run: Run): string {
  if (!run.outcome)
    return run.status === "failed"
      ? "A person needs to review the checks completed so far."
      : "The findings will appear when the checks are complete.";
  const summary = businessText(run.outcome.summary).split(/(?<=\.)\s+/)[0];
  return summary.length > 250
    ? summary.slice(0, 247).replace(/\s+\S*$/, "") + "…"
    : summary;
}
export function filterCases(
  entries: BusinessCase[],
  view: CaseView,
  area: string,
  query: string,
) {
  const needle = query.toLowerCase().trim();
  return entries.filter(
    (c) =>
      (view === "all" || caseState(c) === view) &&
      (area === "all" || c.run.classification?.categories.includes(area)) &&
      [c.run.title, c.run.outcome?.summary, c.run.outcome?.conclusion]
        .join(" ")
        .toLowerCase()
        .includes(needle),
  );
}
export function readyDocuments(
  cases: InboxCase[],
  entries: BusinessCase[],
): InboxCase[] {
  const checked = new Set(entries.map((c) => c.key));
  return cases.filter((c) => !checked.has(documentKey(c)));
}

export function workspaceRoute(hash: string, developer: boolean) {
  const path = hash.replace(/^#/, "");
  const base = {
    page: "overview" as Page,
    runId: "",
    documentId: "",
    partition: "",
    traceId: "",
    approvalId: "",
    evalTab: "",
  };
  const decode = (s: string) => {
    try {
      return decodeURIComponent(s);
    } catch {
      return s;
    }
  };
  if (path.startsWith("trace/"))
    return { ...base, page: "cases" as Page, traceId: decode(path.slice(6)) };
  if (path.startsWith("approvals/"))
    return {
      ...base,
      page: "approvals" as Page,
      approvalId: decode(path.slice(10)),
    };
  if (path.startsWith("evals/"))
    return { ...base, page: "evals" as Page, evalTab: path.slice(6) };
  if (path.startsWith("run/"))
    return { ...base, page: "cases" as Page, runId: decode(path.slice(4)) };
  if (path.startsWith("document/")) {
    const [, partition, ...id] = path.split("/");
    return {
      ...base,
      page: "documents" as Page,
      documentId: decode(id.join("/")),
      partition,
    };
  }
  if (["overview", "documents", "cases", "approvals", "evals"].includes(path))
    return { ...base, page: path as Page };
  if (path === "history" && !developer)
    return { ...base, page: "cases" as Page };
  if (
    developer &&
    ["workbench", "history", "evaluation", "registry"].includes(path)
  )
    return {
      ...base,
      page: "evals" as Page,
      evalTab: (
        {
          workbench: "workbench",
          history: "history",
          evaluation: "quality",
          registry: "registry",
        } as Record<string, string>
      )[path],
    };
  return base;
}

export interface ReadableDocument {
  subject: string;
  sender: string;
  recipient: string;
  body: string;
  fields: { name: string; value: string }[];
  attachments: { name: string; text: string }[];
}
// Display correspondence; the original input still goes to the agent unchanged.
export function readableDocument(item: InboxCase): ReadableDocument {
  const pieces = item.document.split(/\n\s*--- Attachment: (.+?) ---\s*\n/g);
  const primary = pieces[0].trim();
  const doc: ReadableDocument = {
    subject: item.title,
    sender: "Sender not recorded",
    recipient: "",
    body: primary,
    fields: [],
    attachments: [],
  };
  for (let i = 1; i < pieces.length; i += 2)
    doc.attachments.push({ name: pieces[i], text: pieces[i + 1] ?? "" });
  const scalar = (value: unknown) =>
    typeof value === "string"
      ? value
      : typeof value === "number" || typeof value === "boolean"
        ? String(value)
        : "";
  const addFields = (obj: unknown) => {
    if (obj && typeof obj === "object" && !Array.isArray(obj)) {
      for (const [name, value] of Object.entries(obj)) {
        const text = scalar(value);
        if (text) doc.fields.push({ name, value: text });
      }
    }
  };
  try {
    const obj = JSON.parse(primary);
    if (obj && typeof obj === "object" && !Array.isArray(obj)) {
      doc.subject = scalar(obj.subject ?? obj.title) || item.title;
      doc.sender = scalar(obj.sender ?? obj.from) || doc.sender;
      doc.recipient = scalar(obj.to ?? obj.recipient);
      doc.body =
        scalar(obj.body ?? obj.text ?? obj.message) ||
        "No message text was included.";
      if (scalar(obj.signature)) doc.body += "\n\n" + scalar(obj.signature);
      addFields(obj.attributes);
      return doc;
    }
  } catch {
    /* Try the other supplied document formats. */
  }
  if (primary.startsWith("{")) {
    try {
      const rows = primary
        .split(/\n/)
        .filter((s) => s.trim())
        .map((s) => JSON.parse(s));
      const header = rows.find((r) => r.kind === "intake") ?? rows[0];
      doc.subject = scalar(header.subject) || item.title;
      doc.sender = scalar(header.sender) || doc.sender;
      doc.body =
        rows
          .filter((r) => r.kind === "narrative")
          .map((r) => scalar(r.text))
          .join("\n\n") || "No message text was included.";
      doc.fields = rows
        .filter((r) => r.kind === "attribute")
        .map((r) => ({ name: scalar(r.name), value: scalar(r.value) }));
      return doc;
    } catch {
      doc.body =
        "This document could not be displayed as a message. Its original content remains available in the test workbench.";
      return doc;
    }
  }
  const sender = primary.match(
    /^(?:\*?From:\*?|Received\s+\S+\s+from)\s*(.+)$/im,
  );
  if (sender) doc.sender = sender[1].trim();
  const recipient = primary.match(/^To:\s*(.+)$/im);
  if (recipient) doc.recipient = recipient[1];
  const lines = primary.split(/\n/);
  const firstBlank = lines.findIndex((l) => !l.trim());
  if (/^From:/i.test(primary) && firstBlank >= 0)
    doc.body = lines.slice(firstBlank + 1).join("\n");
  else
    doc.body = lines
      .filter(
        (line, index) =>
          !(index === 0 && line.replace(/^#+\s*/, "").trim() === item.title) &&
          !/^\*?(?:From:|Received:|Received\s)/i.test(line),
      )
      .join("\n")
      .trim();
  doc.body = doc.body
    .replace(
      /\|\s*([^|\n]+)\s*\|\s*([^|\n]+)\s*\|/g,
      (_whole, name: string, value: string) => {
        if (/^[-\s]+$/.test(name) || name.trim().toLowerCase() === "field")
          return "";
        doc.fields.push({ name: name.trim(), value: value.trim() });
        return "";
      },
    )
    .trim();
  doc.body = doc.body.replace(/\n[ \t]*\n(?:[ \t]*\n)+/g, "\n\n");
  return doc;
}
