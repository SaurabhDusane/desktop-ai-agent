# Local Desktop AI Agent

A Windows-first, local-first desktop assistant built with Python, PySide6, and Ollama.

## Initial milestone

- PySide6 desktop chat interface
- Local Ollama model discovery and chat
- Environment-based configuration
- No shell, mouse, keyboard, or arbitrary file execution in this scaffold

## Requirements

- Windows 10/11
- Python 3.11+
- Ollama installed and running locally
- At least one Ollama model

## Setup (PowerShell)

```powershell
git clone https://github.com/SaurabhDusane/desktop-ai-agent.git
cd desktop-ai-agent
git switch feat/local-desktop-agent
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
ollama pull qwen2.5:7b
python -m desktop_agent
```

Choose a model that fits your available VRAM/RAM; `qwen2.5:7b` is an example, not a requirement.

## Safety

The model does not receive unrestricted shell, PowerShell, Python, mouse, keyboard, or filesystem access. Tool calls pass through a central risk policy and audit log. Read-only and routine tools can run automatically; system-changing and sensitive tools require an approval callback; restricted tools are blocked. The current desktop launcher only accepts fixed catalog IDs and never runs model-generated shell strings. Future tools will use narrow permissions and explicit approval for sensitive actions.

See `LICENSE` for licensing information.


## Windows UI Automation (optional)

Install the Windows automation extra on the Windows machine:

```powershell
pip install -e ".[windows,dev]"
```

The UI Automation adapter uses the `pywinauto` UIA backend. It is loaded only when Windows desktop tools are registered, so Linux CI can test the policy and adapter with fakes.

### Current desktop capabilities

- Enumerate visible top-level windows (titles, process IDs, handles, and control type; no document text).
- Inspect a bounded UIA control tree (maximum depth 5 and 200 nodes; suppresses names for text-bearing controls and does not read edit values).
- Focus one exact visible window, optionally disambiguated by process ID.
- Click one uniquely matched control.
- Enter text into one uniquely matched control.

All capabilities must be registered with `register_uia_tools(registry)` and invoked through `ToolRegistry.execute(ToolCall(...))`. There is no direct model-to-pywinauto path.

### Permission behavior

- Window listing and bounded control inspection are read-only.
- Focusing a window is a system-changing action and requires approval unless separately authorized by a session grant.
- Clicking and typing are sensitive actions and always require a fresh approval for each invocation. Session grants cannot bypass this requirement.
- Ambiguous window/control matches fail closed.
- UIA inspection avoids reading edit values or document contents.
- Keyboard and mouse orchestration is not yet exposed as unrestricted global input.

The approval callback must be connected to a real user confirmation UI before enabling these tools in the interactive application. The current chat window does not yet include that approval dialog or register UIA tools automatically.

### Manual verification on Windows

1. Install `.[windows,dev]` and start the app from an interactive desktop session.
2. Register UIA tools with a `ToolRegistry` backed by `PermissionPolicy` and `AuditLog`.
3. List windows and verify no control values or document contents are returned.
4. Inspect a known window with small depth/node limits.
5. Verify focus prompts for approval.
6. Verify every click and text-entry invocation prompts separately, including repeated calls.
7. Verify duplicate window titles and ambiguous controls are rejected.
8. Check the SQLite audit log for allowed, denied, and failed actions.

Live UIA smoke testing is opt-in with `DESKTOP_AGENT_RUN_UIA_SMOKE=1` from an interactive Windows session; hosted CI validates the adapter with fakes. UI Automation availability and control behavior vary by application, integrity level, and Windows session. Elevated applications may not be controllable from a non-elevated agent. No attempt is made to bypass those boundaries.

### Interactive approval dialog

The desktop launcher now creates a central tool registry and an approval broker.
When a registered tool requests approval from a worker thread, the broker presents
a native Qt confirmation dialog on the UI thread. The dialog shows the tool name,
reason, and structured arguments; **No** is the default choice. If the request
times out or the UI cannot complete the confirmation, the action is denied.

On Windows, UIA tools are registered automatically when the optional dependency
and desktop session are available. Failure to initialize UI Automation does not
prevent the chat window from starting. The Ollama chat loop now exposes only registered tools through the bounded agent runtime. Application adapter operations are registered as ordinary typed tools and still pass through the same risk, capability, approval, and audit checks.

The approval dialog is not a substitute for reviewing the requested action.
In particular, inspect text-entry arguments before approving them because they
may be submitted by the target application.


## Security and safety controls

The application now has centrally enforced safety modes:

- **Emergency stop:** blocks all future tool executions, including read-only tools, and revokes session grants. The UI disables chat input and safety controls for the remainder of that application session. Restarting the app resets this in-memory state.
- **Read-only mode:** permits read-only tools and denies every tool classified above `READ_ONLY`. Enabling it revokes session grants.
- **Fresh approvals:** sensitive operations continue to require an individual approval for every invocation.
- **Filesystem boundary helper:** `SafePathPolicy` resolves candidate paths and checks them against configured allowed and blocked roots. Future file tools must call this helper before every read or write; it does not grant filesystem access by itself.
- **Audit records:** application startup/shutdown, message metadata, model-list refreshes, errors, safety-mode changes, tool decisions, and scheduler state transitions are recorded locally.

### Local audit files

The application stores its audit database and JSONL activity stream under:

- `~/.local-desktop-agent/audit.sqlite3`
- `~/.local-desktop-agent/audit.jsonl`

The JSONL stream is hash-chained. Each record includes the previous record's hash and its own digest; startup verifies the existing chain and refuses to append if verification fails. This makes accidental edits and simple tampering detectable, but is **not** tamper-proof against an attacker who can replace the entire log and recompute the chain. Keep the directory protected with your Windows account permissions and back it up separately.

Chat prompt and response bodies are not written to the audit log; only model and character-count metadata are retained. Tool arguments and approval details may still contain sensitive data. Basic secret-pattern redaction is applied, but it cannot identify every secret. Treat both files as private data.

### Current limitations

- Emergency stop blocks new tool invocations; it cannot forcibly interrupt an operation that has already started inside a third-party application.
- Filesystem restrictions are a reusable boundary helper, not yet wired to a general file-management tool (the agent currently has no general file-management tool).
- Read-only mode and emergency stop are in-memory controls, not persistent policy configuration.
- Prompt-injection isolation, Windows ACL hardening, protected audit export, backups/rollback, and a dedicated activity-log viewer remain future work.


## Session context and local learning

The chat UI uses a bounded in-memory `SessionContext` rather than sending the entire conversation on every turn.

- Recent turns remain in RAM; when the configured character budget is exceeded, older turns are compressed into a short summary using the selected local Ollama model.
- Only the summary and recent messages are sent with the next request. No cloud summarizer or external memory service is used.
- Chat prompts and responses are not written to the security audit log; only message metadata such as model and character count is retained.
- A separate local `RepetitionMemory` component is provided for future tool workflows. The first two successful observations remain in RAM only; after at least three successful observations of the same normalized action signature in one app session, a compact reusable description is persisted. It stores no transcript or raw action arguments. Pending observations disappear when the app closes.
- Repetition is not permission: learned patterns cannot change tool risk classifications, approval requirements, or policy decisions.

The memory database is `~/.local-desktop-agent/memory.sqlite3` and contains promoted patterns only. The repetition-learning interface is not yet connected to tool execution because model-directed tool invocation is not yet implemented. It will be connected at that boundary when action workflows are introduced.

Context size is currently a character-based bound, not an exact model tokenizer budget. The newest request is retained (and may be truncated if it alone exceeds the configured budget). The context summary is session-only and is discarded when the app closes. A later enhancement can add explicit user controls to inspect, pin, or delete promoted patterns.


## Secure model-to-tool execution

The chat path now uses Ollama's native tool-call protocol through a bounded
agent runtime. Only registered tools are exposed to the model. Every proposed
call is parsed, checked against a closed argument schema, and passed through
the central registry for policy evaluation, approval, execution, and audit.
Unknown tools and malformed arguments fail closed. Sensitive actions continue
to require fresh approval for each invocation; the model cannot grant itself
permissions or execute arbitrary shell/Python code.

The runtime treats user, tool, file, and UI content as untrusted; limits a turn
to four tool rounds and eight calls; caps serialized tool arguments/results;
and returns explicit error results rather than implying success. A tool-call
limit stops further autonomous execution. This is the first secure execution
milestone, not a claim that the later scheduler, cancellation, capability
scopes, or dashboard are complete.


## Capability-based permissions

Tool risk and capability are separate checks. Risk answers "how consequential is
this action?"; a capability answers "which resource and operation may this tool
access?". Each tool can declare required resource/action/scope tuples. The
registry checks those requirements before the handler and checks again directly
before execution. Missing capabilities require explicit approval for that
invocation; that approval is not silently saved as a session grant.

The capability policy supports explicit in-memory grants, scoped matching,
wildcards, and revocation. Its default baseline is limited to desktop
observation. Application launching and desktop interaction require additional
authorization. Grants are not persisted across restarts. Existing risk controls
remain in force, including read-only mode, emergency stop, and fresh approval
for sensitive actions. Filesystem path containment remains enforced separately
by SafePathPolicy; future file tools must combine path validation with a
filesystem capability and must never trust a model-provided path.


## Application adapter framework

Application integrations use a shared contract in \`desktop_agent.desktop.adapters\`:

- Each adapter declares a stable adapter ID, display name, platform, and description.
- Each adapter publishes a fixed list of named operations with closed input schemas, risk levels, and required capabilities.
- \`AdapterRegistry\` rejects duplicate adapter IDs, duplicate/empty operation names, and non-closed schemas. It dispatches only declared operations and rejects unknown or missing arguments.
- \`register_adapter_tools\` exposes declared operations through the central \`ToolRegistry\`; it does not provide a direct model-to-adapter path.
- The first implementation is \`WindowsDesktopAdapter\`, wrapping the existing conservative UI Automation implementation. Its operations are window listing, bounded control inspection, exact-window focus, unique-control click, and bounded text entry.

The Windows adapter is registered under the \`windows_desktop\` ID. Tool names use the form \`windows_desktop_<operation>\`. Every operation retains its risk and capability requirements: observation is read-only, focus is system-changing, and click/text entry require fresh approval. The one-time approval dialog now combines missing-capability and risk-policy reasons into a single confirmation rather than prompting twice for the same invocation.

Future browser, IDE, Office, and file adapters should implement the same contract, declare narrowly scoped capabilities, and keep their own application-specific validation. The framework does not imply that those integrations are implemented yet. Adapter registration is trusted application code; model output cannot register an adapter or add operations at runtime.


## Environment state graph

The desktop agent now has a bounded, in-memory environment graph for the current application session:

- Nodes represent the current desktop workspace, observed application process IDs, and visible windows.
- Edges describe workspace containment and application-to-window ownership.
- Window metadata is limited to title, process ID, native handle, control type, visibility, source, and observation time. It does not collect document text, form values, screenshots, or keystrokes.
- The graph is refreshed on demand through \`environment_refresh_desktop\`. On Windows, this calls the existing \`windows_desktop_list_windows\` tool through \`ToolRegistry\`, preserving central policy and audit.
- \`environment_snapshot\` returns a bounded view; \`environment_query\` searches the current graph by metadata and optional node kind.
- The graph replaces its previous desktop observation on refresh rather than accumulating stale window records. It reports generation, last-refresh time, and a stale flag (60-second freshness threshold).
- Node, edge, query, and result limits are enforced. State is not written to disk and is discarded when the application exits.

This is an initial desktop slice of the environment graph, not a complete inventory of files, browser tabs, projects, or application-internal state. Refresh is explicit/on-demand; no background screen or window monitoring is enabled. On non-Windows platforms, graph queries remain available but desktop refresh reports that the Windows observer is unavailable.


## Task scheduler and observability (initial implementation)

The scheduler in `desktop_agent.agent.scheduler` accepts a validated `AgentPlan`
and returns a `PlanHandle` with a result future and cooperative cancellation:

- Plan submissions are bounded (default: four active/queued plans); a full queue rejects new work rather than growing without limit.
- Dependency-ready steps are dispatched to a bounded worker pool (default: three workers). Independent read-only tools may overlap.
- State-changing and sensitive tools are serialized with a scheduler lock. Their actual authorization is still performed by `ToolRegistry`; scheduler metadata never grants permission.
- Each plan has a monotonic deadline. Cancellation and deadlines prevent not-yet-started steps from running, and downstream steps are skipped after a failed dependency.
- Structured task events include plan/step IDs, state, timestamp, duration where available, and bounded detail. The desktop shell records these events in the local audit stream.
- Metrics expose submitted/completed/failed/rejected plans, active plan/step counts, and a rolling average step duration.

**Important execution boundary:** cancellation and deadlines are cooperative. Python cannot safely terminate a tool handler that is already running inside another application. A timed-out or cancelled plan must not be interpreted as proof that an in-flight OS action was undone. The scheduler waits for already-running work up to the plan deadline and reports the actual completed step outcomes when available.

The scheduler is an execution service for typed plans, not yet a model-generated multi-step planning UI. The current chat runtime still invokes individual model-requested tools through the same registry; plan preview, live task dashboard, hard process isolation, per-tool interruption, retries, and persistent metrics remain future work.


## Local model routing and adaptive resource management (initial implementation)

The model selector now includes **Auto (local routing)**. The router only considers models already installed in the local Ollama instance; it never downloads models or switches to a cloud provider.

- Ollama `/api/show` metadata is normalized into conservative capability profiles (chat, tools, vision, code/completion, context length, parameter size).
- Ollama `/api/ps` reports currently loaded model memory. GPU name and free/total VRAM are read locally through `nvidia-smi` when available.
- RAM is read through Windows memory APIs or platform system counters. Disk capacity is included in the resource snapshot.
- Automatic routing filters by task capability, requested context, and known model VRAM footprint, then ranks candidates using measured latency and quality where available. Metadata-only rankings are explicitly marked provisional.
- Benchmark measurements (model name, latency, user/evaluator quality score, timestamp) are stored locally in `~/.local-desktop-agent/model-benchmarks.sqlite3`. No benchmark prompt or model response is persisted.
- `ModelRouter.record_benchmark(model, latency_ms, quality)` records a measured result; quality is a caller-supplied score from 0 to 1. `benchmark_model` measures a single local inference latency; quality evaluation remains separate and must not be fabricated.
- The resource budget manager reduces the session character budget under RAM pressure and reports conservative VRAM warnings. Resource decisions and selected model are recorded as metadata in the local audit log.

**Limitations:** VRAM estimation is available only for models currently loaded by Ollama; unloaded models have unknown VRAM requirements. `nvidia-smi` is optional, so GPU details may be unavailable. The budget is a conservative heuristic, not a guarantee against out-of-memory errors. Current resource budgets constrain chat context, but do not yet dynamically resize Ollama's server-side context or scheduler worker pool. Benchmarking is exposed as a local API; a guided benchmark and quality-rating UI is still future work. Manual model selection always overrides automatic routing.


## Live task dashboard (initial implementation)

The desktop shell includes a dockable **Task Dashboard**. Model-requested tool calls are wrapped as bounded one-step plans and submitted through the existing scheduler; they no longer bypass it. Each step still passes through the central tool registry, capability checks, risk policy, approval broker, and audit trail.

The dashboard shows a bounded session view of plan/step IDs, tool description, queued/running/completed/denied/failed/cancelled/timed-out/skipped states, timestamps, and measured durations. It also shows pending approval status and scheduler counters (submitted, completed, failed, rejected, active plans/steps, and average step duration). Scheduler events are marshalled onto the Qt UI thread before updating widgets and are recorded in the local audit stream.

This is a monitoring surface, not yet a full multi-step planning workspace: the model currently proposes individual tool calls, the dashboard does not persist history across restarts, and user-facing plan cancellation/inspection and resource telemetry are still future work. Cancellation remains cooperative; an already-running third-party action cannot be forcibly undone.


## On-demand multimodal screen perception (initial implementation)

Install the optional capture dependencies on Windows:

```powershell
pip install -e ".[windows,perception,dev]"
```

The Windows desktop adapter registers `perception_describe_primary_screen`. When the model requests it, the central registry requires fresh approval for that invocation and the `desktop:capture@primary_display` capability. A session capability grant does not bypass the sensitive-action approval.

- Captures the primary display once, only after approval; no background capture or screen recording is enabled.
- Resizes the screenshot to at most 1600×1000 and rejects images larger than 4 MiB.
- Sends the image only to an installed Ollama model whose local metadata advertises vision capability. If no such model is available, the tool fails closed rather than silently sending the image to a text-only model or a cloud service.
- The screenshot is held in memory and discarded after analysis; it is not written to disk or included in the audit log.
- The vision prompt treats screen text as untrusted instructions and asks the model not to disclose credentials. The bounded textual description is returned through the ordinary tool-result path.
- The tool is unavailable outside the Windows desktop registration path. Read-only mode blocks it because screen capture is classified as sensitive.

This is the first visual-perception slice. It does not yet include OCR-only extraction, per-window capture, image-region selection, camera input, or a user-facing capture preview/retention settings. Vision-model quality and GPU performance must be verified on the target machine.
