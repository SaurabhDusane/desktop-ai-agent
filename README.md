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
