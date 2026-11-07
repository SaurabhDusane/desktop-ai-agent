"""On-demand, local-only screen perception with bounded in-memory capture."""
from __future__ import annotations

from io import BytesIO
from typing import Callable, Protocol


MAX_IMAGE_BYTES = 4 * 1024 * 1024
MAX_DESCRIPTION_CHARS = 4000


class CaptureBackend(Protocol):
    def capture_primary_display(self) -> bytes: ...


class PerceptionError(RuntimeError):
    """A screen observation could not be completed safely."""


class PrimaryDisplayCapture:
    """Capture the primary monitor into memory; never writes screenshots to disk."""

    def __init__(self, max_width: int = 1600, max_height: int = 1000) -> None:
        self.max_width = max_width
        self.max_height = max_height

    def capture_primary_display(self) -> bytes:
        try:
            import mss
            from PIL import Image
        except ImportError as exc:
            raise PerceptionError(
                "Install the perception extra: pip install -e '.[perception]'"
            ) from exc

        try:
            with mss.mss() as screen:
                if len(screen.monitors) < 2:
                    raise PerceptionError("No primary display is available.")
                monitor = screen.monitors[1]
                shot = screen.grab(monitor)
                image = Image.frombytes("RGB", shot.size, shot.rgb)
                image.thumbnail((self.max_width, self.max_height))
                output = BytesIO()
                image.save(output, format="PNG", optimize=True)
                data = output.getvalue()
        except PerceptionError:
            raise
        except Exception as exc:
            raise PerceptionError("Could not capture the primary display.") from exc

        if not data or len(data) > MAX_IMAGE_BYTES:
            raise PerceptionError("Captured image is empty or exceeds the 4 MiB limit.")
        return data


class PerceptionBroker:
    """Capture and analyze only when invoked; images are never persisted."""

    def __init__(
        self,
        capture: CaptureBackend,
        analyze: Callable[[bytes], str],
    ) -> None:
        self._capture = capture
        self._analyze = analyze

    def describe_primary_screen(self) -> dict[str, str | int]:
        image = self._capture.capture_primary_display()
        if not isinstance(image, bytes) or not image or len(image) > MAX_IMAGE_BYTES:
            raise PerceptionError("Capture backend returned an invalid or oversized image.")
        description = self._analyze(image)
        if not isinstance(description, str) or not description.strip():
            raise PerceptionError("The local vision model returned no usable description.")
        bounded = description.strip()[:MAX_DESCRIPTION_CHARS]
        return {
            "description": bounded,
            "image_bytes": len(image),
            "retention": "memory_only; screenshot discarded after analysis",
        }
