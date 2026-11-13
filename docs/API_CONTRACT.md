# Application contract
All JSON. Same origin /api. Dates ISO UTC, durations milliseconds.

GET /api/health -> {status, name}
GET /api/config -> {workflows:[{id,name,description,icon,color}], modes:[{id,name,description}], classifier:{mode,configured}, models:object, limits:object}
GET /api/cases?partition=train -> {cases:[{case_id,partition,title,preview,document,media_type,received_at,showcase:bool,workflow:string|null}], total}
GET /api/cases/{case_id}?partition=train -> above case
GET /api/runs -> {runs:[Run]} (complete history, newest first, no events or input on list)
POST /api/runs body {case_id?:string,partition?:string,document?:string,mode:"simulation"|"live",title?:string,purpose?:"business"|"test"} -> Run, starts asynchronously
GET /api/runs/{id} -> Run
POST /api/runs/{id}/cancel -> Run
POST /api/runs/{id}/replay -> Run (recorded replay, no calls)
POST /api/runs/{id}/approvals/{request_id} body {approve:boolean} -> Run
GET /api/evaluations -> {evaluations:[Evaluation]}
POST /api/evaluations body {partition:"train"|"validation"|"test",limit:5,mode:"simulation"|"live"} -> Evaluation, asynchronous
GET /api/evaluations/{id} -> Evaluation
GET /api/registry -> {tools:[{name,description,domain,parameters:JSONSchema,permission,system}]}

Run = {id,case_id,document_fingerprint?:string,purpose?:"business"|"test"|"evaluation",partition,title,input,mode,status:"queued"|"running"|"completed"|"awaiting_approval"|"failed"|"cancelled",created_at,updated_at,duration_ms,classification:Classification|null,outcome:Outcome|null,events:Event[],approvals:Approval[],metrics:{tool_calls,iterations,model_calls,unsafe_actions_blocked,usage:object,providers:string[]},error?:string,source_run_id?:string}
Classification = {categories:string[],primary:string,confidence:number|null,uncertainty:number,risk:string,urgency:"routine"|"priority"|"urgent"|"immediate",escalate:boolean,escalation_reason:string,provider,model,mode,rationale,usage?:object}
Event = {id,sequence,kind:"orchestration"|"classification"|"escalation"|"decision"|"tool_call"|"tool_result"|"validation"|"outcome"|"error"|"approval"|"model",title,detail:string,timestamp,status:"running"|"completed"|"failed"|"blocked",tool?:string,arguments?:object,result?:object,provider?:string,model?:string,duration_ms?:number,batch_id?:string,evidence_ids?:string[],[key:string]:unknown}
Outcome = {summary,conclusion,risk:"low"|"medium"|"high"|"critical",outcome_code,evidence:[{record_id,note}],unresolved:string[],recommendations:string[],requires_approval:boolean,actions:object[],departments?:string[],by_workflow?:Record<string,string>}
Approval = {request_id,tool,args,justification,status:"pending"|"approved"|"denied"|"executed"|"failed",result?:object}
Evaluation = {id,status,mode,partition,created_at,completed:number,total:number,metrics:object,results:object[],error?:string}. Metrics from existing evaluator may be nested.

Browser polling every 1s while active. Never invent events, scores, model usage or outcome data. Display unknown as unknown. Modes labeled at all times; errors visible. Render document and tool text as text, never raw HTML.

## Human workflows, guardrails and versions

GET /api/approvals -> {items:[ManualWorkItem]} (original live business reviews only)
GET /api/approvals?include_tests=true -> includes test/evaluation and simulation originals
POST /api/approvals/{run_id}/{request_id} body {decision:"approve"|"decline",note:string} -> {item,run}
GET /api/assurance -> {ruleset_version,rules,history,suite,suites,limitations}
POST /api/assurance/run body {} -> a new persisted deterministic GuardrailSuite

ManualWorkItem = {id,run_id,request_id,kind:"action_approval"|"department_review",title,case_title,department,reason,hold_scope,next_step,status,created_at,can_decide,blocked_reason,decided_at?,decision_note?,tool?,args?,result?}

Run additionally exposes manual_reviews, business_route:{path,label,detail},
ruleset_version and application_revision (versions only when actually recorded).
Department decisions emit manual_decision; workflow creation emits handoff.
The legacy action approval endpoint also accepts an optional note.
Decision notes are required by the separate workflow endpoint (1–2,000 chars).
Department approval records a decision and executes no business tool. Dependent
consequential actions require their own explicit approval. Failed/replay reviews
cannot approve; runtime restrictions are rechecked on action execution.

New evaluation result rows include expected_outcome, actual_outcome,
expected_categories, actual_categories, models, requires_approval,
ruleset_version and application_revision alongside existing scores and duration.
Ground truth is still evaluator-only; it is never included in an agent payload.
Guardrail results include rule snapshots, suite/rule versions, application
revision, implementation digest, expected/actual, positive/negative test kind,
per-rule coverage and duration. Every invocation creates a new immutable result
identifier; reading the report performs no tests or model calls.

POST /api/evaluations/recorded?partition=train -> a new completed evaluation of
latest saved original AI attempts for labelled documents. No execution is rerun;
source="saved_ai_reviews", new_model_calls=0 and an explicit warning distinguish
this analysis from a fresh live evaluation. Timings/models belong to the saved
reviews, missing historical versions remain unknown, and original runs and
previous evaluations are unchanged. Custom documents without expected answers
are excluded. This selected development sample is not a held-out benchmark.
