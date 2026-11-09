# Application contract
All JSON. Same origin /api. Dates ISO UTC, durations milliseconds.

GET /api/health -> {status, name}
GET /api/config -> {workflows:[{id,name,description,icon,color}], modes:[{id,name,description}], classifier:{mode,configured}, models:object, limits:object}
GET /api/cases?partition=train -> {cases:[{case_id,partition,title,preview,document,media_type,received_at,showcase:bool,workflow:string|null}], total}
GET /api/cases/{case_id}?partition=train -> above case
GET /api/runs -> {runs:[Run]} (newest first, no events or input on list)
POST /api/runs body {case_id?:string,partition?:string,document?:string,mode:"simulation"|"live",title?:string} -> Run, starts asynchronously
GET /api/runs/{id} -> Run
POST /api/runs/{id}/cancel -> Run
POST /api/runs/{id}/replay -> Run (recorded replay, no calls)
POST /api/runs/{id}/approvals/{request_id} body {approve:boolean} -> Run
GET /api/evaluations -> {evaluations:[Evaluation]}
POST /api/evaluations body {partition:"train"|"validation"|"test",limit:5,mode:"simulation"|"live"} -> Evaluation, asynchronous
GET /api/evaluations/{id} -> Evaluation
GET /api/registry -> {tools:[{name,description,domain,parameters:JSONSchema,permission,system}]}

Run = {id,case_id,partition,title,input,mode,status:"queued"|"running"|"completed"|"awaiting_approval"|"failed"|"cancelled",created_at,updated_at,duration_ms,classification:Classification|null,outcome:Outcome|null,events:Event[],approvals:Approval[],metrics:{tool_calls,iterations,model_calls,unsafe_actions_blocked,usage:object,providers:string[]},error?:string,source_run_id?:string}
Classification = {categories:string[],primary:string,confidence:number|null,uncertainty:number,risk:string,urgency:"routine"|"priority"|"urgent"|"immediate",escalate:boolean,escalation_reason:string,provider,model,mode,rationale,usage?:object}
Event = {id,sequence,kind:"orchestration"|"classification"|"escalation"|"decision"|"tool_call"|"tool_result"|"validation"|"outcome"|"error"|"approval"|"model",title,detail:string,timestamp,status:"running"|"completed"|"failed"|"blocked",tool?:string,arguments?:object,result?:object,provider?:string,model?:string,duration_ms?:number,batch_id?:string,evidence_ids?:string[],[key:string]:unknown}
Outcome = {summary,conclusion,risk:"low"|"medium"|"high"|"critical",outcome_code,evidence:[{record_id,note}],unresolved:string[],recommendations:string[],requires_approval:boolean,actions:object[],departments?:string[],by_workflow?:Record<string,string>}
Approval = {request_id,tool,args,justification,status:"pending"|"approved"|"denied"|"executed"|"failed",result?:object}
Evaluation = {id,status,mode,partition,created_at,completed:number,total:number,metrics:object,results:object[],error?:string}. Metrics from existing evaluator may be nested.

Browser polling every 1s while active. Never invent events, scores, model usage or outcome data. Display unknown as unknown. Modes labeled at all times; errors visible. Render document and tool text as text, never raw HTML.
