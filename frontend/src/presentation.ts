import type { Run, TraceEvent } from "./types";

// Presentation only: the original report, references and results stay in the saved record.
const recordPattern = /\b[A-Z]{1,4}-[0-9A-F]{6,}(?:-[A-Z0-9]{2,})*\b/g;
export type ReferenceNames = Map<string, string>;

export function referenceNames(run: Run): ReferenceNames {
  const names: ReferenceNames = new Map();
  function visit(value: unknown): void {
    if (Array.isArray(value)) {
      value.forEach(visit);
      return;
    }
    if (!value || typeof value !== "object") return;
    const row = value as Record<string, unknown>;
    if (typeof row.id === "string") {
      for (const key of [
        "name",
        "full_name",
        "hostname",
        "resource_name",
        "invoice_number",
        "contract_number",
        "principal",
        "title",
      ]) {
        const label = row[key];
        if (typeof label === "string" && label.trim() && label.length <= 140) {
          names.set(row.id, label.trim());
          break;
        }
      }
    }
    Object.values(row).forEach(visit);
  }
  for (const event of run.events ?? []) {
    if (event.kind === "tool_result" && (event.result as { ok?: boolean })?.ok)
      visit(event.result);
  }
  return names;
}

export const toolLabels: Record<string, string> = {
  search_records: "Find relevant records",
  get_linked_records: "Follow links between records",
  get_audit_trail: "Check previous activity",
  get_supplier_record: "Check supplier details",
  find_supplier: "Find the supplier",
  get_supplier_change_history: "Check changes to supplier details",
  get_invoice: "Read the invoice",
  search_invoices: "Find the invoice",
  get_purchase_order: "Check the purchase order",
  get_goods_receipts: "Confirm goods or services were received",
  verify_email_origin: "Check who sent the email",
  get_email_headers: "Check email delivery records",
  get_callback_log: "Check independent phone verification",
  get_payment_status: "Check the payment status",
  find_account_usage: "Check earlier use of the bank account",
  get_fraud_cases: "Check previous fraud reports",
  place_payment_hold: "Put the payment on hold",
  release_payment: "Release the payment",
  update_supplier_bank_details: "Change the supplier’s bank details",
  get_policy: "Read the policy",
  discover_affected_systems: "Find systems covered by the policy",
  get_system: "Read system details",
  inspect_security_controls: "Check security safeguards",
  get_control_definition: "Read the security requirement",
  list_system_databases: "Find the system’s databases",
  run_database_query: "Run a read-only data check",
  get_access_grants: "Check who has access",
  get_audit_findings: "Check earlier audit findings",
  get_control_exceptions: "Check approved exceptions",
  revoke_access_grant: "Remove access",
  find_customer: "Find the customer",
  get_customer_record: "Read customer details",
  verify_identity_status: "Check identity verification",
  find_customer_data: "Find where personal information is held",
  get_retention_records: "Check how long records must be kept",
  check_legal_holds: "Check whether records must be preserved",
  get_data_request_history: "Check earlier data requests",
  get_third_party_authority: "Check permission to act for the customer",
  export_customer_data: "Prepare a copy of personal information",
  execute_erasure: "Delete eligible personal information",
  update_customer_record: "Correct customer details",
  lookup_asset_owner: "Find who is responsible for the asset",
  query_cloud_inventory: "Check the cloud inventory",
  get_cmdb_item: "Read the asset register",
  search_assets: "Find the affected asset",
  get_deployment_history: "Check how the asset was set up",
  get_change_record: "Check whether the change was approved",
  get_security_alerts: "Check security alerts",
  get_employee: "Check the staff directory",
  get_ticket: "Read the existing support request",
  isolate_asset: "Disconnect the asset from the network",
  decommission_asset: "Retire the asset",
  create_ticket: "Create a follow-up task",
  create_review_case: "Open a review case",
  request_approval: "Ask for approval",
  get_contract: "Read the contract",
  find_contracts: "Find the contract",
  compare_contract_versions: "Compare the contract versions",
  get_supplier_risk: "Check supplier risks",
  get_financial_controls: "Check spending and approval limits",
  get_privacy_assessment: "Check the privacy assessment",
  get_approval_workflow: "Check contract approvals",
  release_contract_for_signature: "Release the contract for signing",
};
export const toolLabel = (name?: string) =>
  name
    ? (toolLabels[name] ?? "Review business records")
    : "Review business records";

export function businessText(
  value: string | undefined,
  names: ReferenceNames = new Map(),
): string {
  if (!value) return "";
  let text = value.replace(
    /^\[(?:CLI classifier|Simulation heuristic)[\s\S]*?\]\s*/i,
    "",
  );
  // Remove a duplicated account reference only when the observed name matches.
  text = text.replace(
    /on grant ([A-Z]{1,4}-[0-9A-F]{6,}) for principal ([\w.-]+)/g,
    (whole, id: string, account: string) =>
      names.get(id) === account ? `for account ${account}` : whole,
  );
  text = text.replace(
    /\bPolicy ([A-Z]{1,4}-[0-9A-F]{6,})/g,
    (whole, id: string) =>
      names.has(id) ? `The policy “${names.get(id)}”` : whole,
  );
  // A name already followed by its internal ID needs only the name in the summary.
  text = text.replace(
    /\s*\(([A-Z]{1,4}-[0-9A-F]{6,}(?:-[A-Z0-9]{2,})*)\)/g,
    (whole, id: string) => (names.has(id) ? "" : whole),
  );
  text = text.replace(recordPattern, (id) => names.get(id) ?? id);
  for (const [name, label] of Object.entries(toolLabels))
    text = text.replace(new RegExp(`\\b${name}\\b`, "g"), label.toLowerCase());
  const phrases: [RegExp, string][] = [
    [/\bInvestigation into\b/g, "Review of"],
    [/\binvestigation into\b/g, "review of"],
    [/\bBusiness Email Compromise \(BEC\)/gi, "email impersonation fraud"],
    [/\bBEC\b/g, "email impersonation fraud"],
    [/\bMAC address\b/gi, "device hardware address"],
    [/\bARP mismatch\b/gi, "network identity mismatch"],
    [/\bARP spoofing\b/gi, "device impersonation on the network"],

    [/\bprivileged access grants?\b/gi, "administrator access"],
    [/\bhuman privileged account(s?)\b/gi, "staff administrator account$1"],
    [/\bprivileged human account(s?)\b/gi, "staff administrator account$1"],
    [/\bprivileged account(s?)\b/gi, "administrator account$1"],
    [/\baccess grants?\b/gi, "access permission"],
    [/\bfor principal\b/gi, "for account"],
    [/\bMFA\b/g, "multi-factor authentication (an extra sign-in check)"],
    [/\bPII\b/g, "personal information"],
    [/\bCMDB\b/g, "asset register"],
    [/\bIDV\b/g, "identity verification"],
    [/\bin-scope\b/gi, "affected"],
    [/\bcontrol exceptions?\b/gi, "exception to the rule"],
    [/\bcompensating controls\b/gi, "alternative safeguards"],
    [/\bcreating a compliance gap\b/gi, "so the rule is not being met"],
    [/\b(?:compliance|audit) gap\b/gi, "unmet requirement"],
    [
      /\bnon-compliant access grants?\b/gi,
      "access permission that does not meet the requirement",
    ],
    [/\bnon-compliant\b/gi, "not meeting the requirement"],
    [/\bfor remediation\b/gi, "to get the issue fixed"],
    [/\bremediation\b/gi, "corrective action"],
    [/\bepistemic uncertainty\b/gi, "uncertainty in the initial assessment"],
    [/\bdata-subject requests?\b/gi, "personal information request"],
    [/\bdelegated authority\b/gi, "approval authority"],
    [/\bfulfilment\b/gi, "carrying out the request"],
    [/\bprovenance\b/gi, "source of the evidence"],
  ];
  for (const [pattern, replacement] of phrases)
    text = text.replace(pattern, replacement);
  return text.replace(/\b\d{4}-\d{2}-\d{2}\b/g, (date) => {
    const parsed = new Date(`${date}T12:00:00Z`);
    return Number.isNaN(parsed.getTime())
      ? date
      : parsed.toLocaleDateString("en-GB", {
          day: "numeric",
          month: "long",
          year: "numeric",
          timeZone: "UTC",
        });
  });
}

const outcomeLabels: Record<string, string> = {
  approve_and_process: "Invoice checks passed",
  approve_bank_change: "Bank change checks passed",
  hold_payment_and_open_fraud_case:
    "Put the payment on hold for a fraud review",
  reject_change_and_open_fraud_case: "Do not accept the bank change",
  callback_verification_required: "Confirm the request by phone",
  reject_duplicate_invoice: "A duplicate invoice was found",
  query_supplier_discrepancy: "Supplier details need checking",
  no_action_already_applied: "The requested change was already made",
  no_action_required: "No further action is needed",
  open_audit_item_gap_found: "A policy requirement is not being met",
  monitor_approved_exception: "An approved exception needs monitoring",
  request_owner_attestation: "The system owner needs to confirm compliance",
  fulfil_erasure: "Eligible records can be deleted after approval",
  refuse_erasure_legal_hold: "Records must be kept for a legal matter",
  partial_erasure_with_retention_exemption:
    "Only some records are eligible for deletion",
  fulfil_access_request: "A copy of the records can be prepared",
  request_identity_verification: "Verify the requester’s identity first",
  reject_third_party_request: "Do not share records with this requester",
  apply_correction: "Customer details can be corrected after approval",
  request_supporting_evidence: "More information is needed",
  refer_to_security_review: "A security review is needed",
  no_record_found_notify_requester: "No matching records were found",
  register_asset_and_assign_owner: "Register the asset and assign an owner",
  isolate_and_open_incident: "Take the asset off the network for review",
  decommission_stale_asset: "The unused asset can be retired after approval",
  reconcile_inventory_record: "The asset records need updating",
  complete_decommission_with_ticket: "Finish retiring the asset after approval",
  close_as_authorised_activity: "The activity was authorised",
  recover_device_and_open_ticket: "The device needs to be recovered",
  route_for_standard_approval: "The contract needs the usual approvals",
  escalate_to_senior_approval: "The contract needs senior review",
  block_pending_privacy_assessment:
    "A privacy assessment is needed before proceeding",
  request_clause_renegotiation: "The contract terms need further negotiation",
  request_missing_documents: "Required documents are missing",
  no_business_action: "No business action is needed",
  request_clarification: "Clarify the request before proceeding",
  reject_unsupported_request: "This request cannot be processed here",
  manual_review: "A person needs to review this case",
};
export function outcomeTitle(run: Run): string {
  if (
    run.approvals?.some(
      (a) =>
        a.status === "executed" &&
        a.result &&
        (a.result as { ok?: boolean }).ok,
    )
  ) {
    const applied = run.approvals.filter(
      (a) => a.status === "executed" && (a.result as { ok?: boolean })?.ok,
    );
    if (applied.length === 1) {
      const titles: Record<string, string> = {
        place_payment_hold: "Payment hold applied to the example records",
        isolate_asset: "Network isolation was simulated",
        execute_erasure: "Deletion was simulated",
        export_customer_data: "A records export was simulated",
        update_customer_record: "Customer correction was simulated",
      };
      if (titles[applied[0].tool]) return titles[applied[0].tool];
    }
  }
  return (
    outcomeLabels[run.outcome?.outcome_code ?? ""] ?? "Review the findings"
  );
}

const workflowDescriptions: Record<string, string> = {
  supplier_fraud: "Check whether a supplier payment or bank change is genuine.",
  regulatory_compliance:
    "Check whether business systems meet a policy requirement.",
  gdpr_data:
    "Check a request to access, correct or delete personal information.",
  it_asset: "Review an unexpected asset or conflicting inventory records.",
  contract_risk:
    "Check which teams need to review a contract or its changed terms.",
  out_of_scope: "The request does not identify a supported business review.",
};
export const workflowDescription = (name: string) =>
  workflowDescriptions[name] ??
  "Review the request and the relevant business records.";
export function priorityLabel(value?: string | number): string {
  return (
    (
      {
        routine: "Normal",
        priority: "Needs attention",
        urgent: "Urgent",
        immediate: "Immediate attention",
        "0": "Normal",
        "1": "Needs attention",
        "2": "Urgent",
        "3": "Immediate attention",
      } as Record<string, string>
    )[String(value)] ?? "Not recorded"
  );
}
export function failureSummary(error?: string): string {
  if (
    /not present|not.*observed|citation|supporting evidence|INVALID_EVIDENCE/i.test(
      error ?? "",
    )
  )
    return "Some evidence could not be verified, so no final conclusion was accepted. The completed checks are saved below for review.";
  if (/rate.?limit|usage limit|quota/i.test(error ?? ""))
    return "The AI service has reached a usage limit. The completed checks are saved below; try again when access is available.";
  if (/sign.?in|auth|credential|logged in/i.test(error ?? ""))
    return "The AI connection needs attention before the review can continue. The completed checks are saved below.";
  if (/time.*limit|time.*budget|timed out|timeout/i.test(error ?? ""))
    return "The review took longer than the allowed time. The checks completed so far are saved below.";
  return "The review stopped before a verified result was available. Review the completed checks or start a new review.";
}
export function eventTitle(event: TraceEvent): string {
  if (event.tool) return toolLabel(event.tool);
  if (event.kind === "classification") return "Identified the type of request";
  if (event.kind === "escalation") return "Requested a more detailed review";
  if (event.kind === "decision") return "Chose what to check next";
  if (event.kind === "outcome") return "Recorded the business outcome";
  if (event.kind === "handoff") return "Opened a human review workflow";
  if (event.kind === "manual_decision")
    return "Recorded a departmental decision";
  if (event.kind === "approval")
    return /requested/i.test(event.title)
      ? "Opened an approval request"
      : "Recorded an approval decision";
  if (event.kind === "validation")
    return event.status === "blocked" || event.status === "failed"
      ? "A safeguard stopped this step"
      : "Checked the supporting evidence";
  if (event.kind === "error") return "The review stopped";
  if (event.kind === "model")
    return event.status === "running"
      ? "Deciding what to check next"
      : "Recorded a review decision";
  return "Prepared the next checks";
}
export function resultSummary(event: TraceEvent): string {
  const result = event.result as
    | {
        ok?: boolean;
        data?: Record<string, unknown>;
        error?: { code?: string };
      }
    | undefined;
  if (!result?.ok) {
    const code = result?.error?.code;
    if (code === "NOT_FOUND") return "No matching record was found.";
    if (code === "AMBIGUOUS_MATCH")
      return "Several possible matches need a closer look.";
    if (code === "SERVICE_UNAVAILABLE")
      return "This service was unavailable. Later steps show whether another source could be used.";
    if (code === "PERMISSION_DENIED" || code === "APPROVAL_REQUIRED")
      return "This change was not permitted to run.";
    return "This check could not be completed. Its details have been saved.";
  }
  const data = result.data ?? {};
  if (data.request_id && data.status === "pending")
    return "An approval request was saved. The proposed change has not been made.";
  if (data.review_case_id)
    return "A review case was opened with the findings and evidence.";
  if (data.ticket_id) return "A follow-up task was created.";
  if (typeof data.count === "number")
    return `${data.count} matching record${data.count === 1 ? "" : "s"} found.`;
  for (const key of [
    "in_scope",
    "matches",
    "results",
    "grants",
    "verifications",
    "alerts",
    "changes",
    "locations",
    "findings",
    "contracts",
    "resources",
  ]) {
    if (Array.isArray(data[key]))
      return `${data[key].length} relevant record${data[key].length === 1 ? "" : "s"} returned.`;
  }
  return "The findings were saved for this review.";
}

export function completedWork(run: Run): {
  reviews: number;
  tasks: number;
  applied: number;
} {
  const results = (run.events ?? []).filter(
    (e) => e.kind === "tool_result" && (e.result as { ok?: boolean })?.ok,
  );
  return {
    reviews: results.filter(
      (e) =>
        (e.result as { data?: { review_case_id?: string } })?.data
          ?.review_case_id,
    ).length,
    tasks: results.filter(
      (e) => (e.result as { data?: { ticket_id?: string } })?.data?.ticket_id,
    ).length,
    applied: (run.approvals ?? []).filter(
      (a) => a.status === "executed" && (a.result as { ok?: boolean })?.ok,
    ).length,
  };
}
