"""Small starter set of desktop-observation tools; no arbitrary command execution."""

import platform
import subprocess

from desktop_agent.agent.models import RiskLevel
from desktop_agent.agent.registry import ToolRegistry, ToolSpec


# Deliberately fixed executable names: model-generated shell strings are never executed.
APP_CATALOG = {
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "file_explorer": "explorer.exe",
}


def launch_registered_app(app_id: str) -> dict[str, str]:
    if platform.system() != "Windows":
        raise RuntimeError("Application launching is currently supported on Windows only.")
    executable = APP_CATALOG.get(app_id)
    if executable is None:
        raise ValueError(f"Application is not in the approved catalog: {app_id}")
    subprocess.Popen([executable], shell=False, close_fds=True)
    return {"launched": app_id}


def register_desktop_tools(registry: ToolRegistry) -> None:
    registry.register(ToolSpec(
        name="launch_application",
        description="Launch a known Windows application by catalog ID (not an arbitrary command).",
        risk=RiskLevel.SYSTEM_CHANGE,
        handler=launch_registered_app,
    ))
