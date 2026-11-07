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
