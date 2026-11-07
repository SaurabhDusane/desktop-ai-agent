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
- Inspect a bounded UIA control tree (maximum depth 5 and 200 nodes; does not read edit values).
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

UI Automation availability and control behavior vary by application, integrity level, and Windows session. Elevated applications may not be controllable from a non-elevated agent. No attempt is made to bypass those boundaries.

### Interactive approval dialog

The desktop launcher now creates a central tool registry and an approval broker.
When a registered tool requests approval from a worker thread, the broker presents
a native Qt confirmation dialog on the UI thread. The dialog shows the tool name,
reason, and structured arguments; **No** is the default choice. If the request
times out or the UI cannot complete the confirmation, the action is denied.

On Windows, UIA tools are registered automatically when the optional dependency
and desktop session are available. Failure to initialize UI Automation does not
prevent the chat window from starting. The registry is currently infrastructure:
the Ollama chat loop does not yet ask the model to plan or invoke tools, so this
does not enable model-directed desktop control by itself.

The approval dialog is not a substitute for reviewing the requested action.
In particular, inspect text-entry arguments before approving them because they
may be submitted by the target application.


## Security and safety controls

The application now has centrally enforced safety modes:

- **Emergency stop:** blocks all future tool executions, including read-only tools, and revokes session grants. The UI disables chat input and safety controls for the remainder of that application session. Restarting the app resets this in-memory state.
- **Read-only mode:** permits read-only tools and denies every tool classified above `READ_ONLY`. Enabling it revokes session grants.
- **Fresh approvals:** sensitive operations continue to require an individual approval for every invocation.
- **Filesystem boundary helper:** `SafePathPolicy` resolves candidate paths and checks them against configured allowed and blocked roots. Future file tools must call this helper before every read or write; it does not grant filesystem access by itself.
- **Audit records:** application startup/shutdown, chat prompts and responses, model-list refreshes, errors, safety-mode changes, and tool decisions are recorded locally.

### Local audit files

The application stores its audit database and JSONL activity stream under:

- `~/.local-desktop-agent/audit.sqlite3`
- `~/.local-desktop-agent/audit.jsonl`

The JSONL stream is hash-chained. Each record includes the previous record's hash and its own digest; startup verifies the existing chain and refuses to append if verification fails. This makes accidental edits and simple tampering detectable, but is **not** tamper-proof against an attacker who can replace the entire log and recompute the chain. Keep the directory protected with your Windows account permissions and back it up separately.

The audit log includes chat content so it can contain sensitive personal information. Basic secret-pattern redaction is applied, but it cannot identify every secret. Treat both files as private data. Do not share them without reviewing their contents.

### Current limitations

- Emergency stop blocks new tool invocations; it cannot forcibly interrupt an operation that has already started inside a third-party application.
- Filesystem restrictions are a reusable boundary helper, not yet wired to a general file-management tool (the agent currently has no general file-management tool).
- Read-only mode and emergency stop are in-memory controls, not persistent policy configuration.
- Prompt-injection isolation, Windows ACL hardening, protected audit export, backups/rollback, and a dedicated activity-log viewer remain future work.
- The model chat loop still does not invoke desktop tools.


## Session context and local learning

The chat UI uses a bounded in-memory `SessionContext` rather than sending the entire conversation on every turn.

- Recent turns remain in RAM; when the configured character budget is exceeded, older turns are compressed into a short summary using the selected local Ollama model.
- Only the summary and recent messages are sent with the next request. No cloud summarizer or external memory service is used.
- Raw session conversation is not written to a memory database. The existing security audit log remains separate and may still contain chat content.
- A separate local `RepetitionMemory` component is provided for future tool workflows. It promotes a compact reusable description only after at least three successful observations of the same normalized action signature. It stores no transcript or raw action arguments.
- Repetition is not permission: learned patterns cannot change tool risk classifications, approval requirements, or policy decisions.

The memory database is `~/.local-desktop-agent/memory.sqlite3`. The repetition-learning interface is not yet connected to tool execution because model-directed tool invocation is not yet implemented. It will be connected at that boundary when action workflows are introduced.

Context size is currently a conservative character-based approximation, not an exact model tokenizer budget. The context summary is session-only and is discarded when the app closes. A later enhancement can add explicit user controls to inspect, pin, or delete promoted patterns.
