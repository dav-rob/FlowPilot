export type Mode = "live" | "simulation";
export type Partition = "train" | "validation" | "test";
export type Page = "investigations" | "history" | "evaluation" | "registry";
export interface Workflow {
  id: string;
  name: string;
  description: string;
  icon: string;
  color: string;
}
export interface Config {
  workflows: Workflow[];
  modes: { id: string; name: string; description: string }[];
  classifier: { mode: string; configured: boolean };
  models: Record<string, unknown>;
  limits: Record<string, unknown>;
}
export interface InboxCase {
  case_id: string;
  partition: Partition;
  title: string;
  preview: string;
  document: string;
  media_type: string;
  received_at: string;
  showcase: boolean;
  workflow: string | null;
}
export interface Classification {
  categories: string[];
  primary: string;
  confidence: number | null;
  uncertainty: number;
  risk: string;
  urgency: number | string;
  escalate: boolean;
  escalation_reason: string;
  provider: string;
  model: string;
  mode: string;
  rationale: string;
  usage?: object;
}
export interface TraceEvent {
  id: string;
  sequence: number;
  kind: string;
  title: string;
  detail: string;
  timestamp: string;
  status: string;
  tool?: string;
  arguments?: object;
  result?: object;
  provider?: string;
  model?: string;
  duration_ms?: number;
  batch_id?: string;
  evidence_ids?: string[];
  [key: string]: unknown;
}
export interface Outcome {
  summary: string;
  conclusion: string;
  risk: string;
  outcome_code: string;
  evidence: { record_id: string; note: string }[];
  unresolved: string[];
  recommendations: string[];
  requires_approval: boolean;
  actions: object[];
  departments?: string[];
  by_workflow?: Record<string, string>;
}
export interface Approval {
  request_id: string;
  tool: string;
  args: object;
  justification: string;
  status: string;
  result?: object;
}
export interface Run {
  id: string;
  case_id?: string;
  partition?: string;
  title: string;
  input?: string;
  mode: Mode | "replay";
  status: string;
  created_at: string;
  updated_at: string;
  duration_ms: number | null;
  classification: Classification | null;
  outcome: Outcome | null;
  events?: TraceEvent[];
  approvals?: Approval[];
  metrics: {
    tool_calls?: number;
    iterations?: number;
    model_calls?: number;
    unsafe_actions_blocked?: number;
    usage?: object;
    providers?: string[];
  };
  error?: string;
  source_run_id?: string;
  source_status?: string;
  source_mode?: string;
  replay_note?: string;
}
export interface Evaluation {
  id: string;
  status: string;
  mode: Mode;
  partition: Partition;
  created_at: string;
  completed: number;
  total: number;
  metrics: Record<string, unknown>;
  results: Record<string, unknown>[];
  error?: string;
  warning?: string;
}
export interface Tool {
  name: string;
  description: string;
  domain: string;
  parameters: Record<string, unknown>;
  permission: string;
  system: string;
}
