"""Vercel serverless entry point (Root Directory: backend).

Vercel's Python runtime bundles only this project root and imports functions
from ``api/``. The application code imports itself as the ``backend`` package
(e.g. ``backend.app.main``), which resolves when uvicorn runs from the
repository root. Register this directory under that package name so the
existing imports work unchanged inside the Vercel bundle.
"""

import sys
import types
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]

if "backend" not in sys.modules:
    _backend_pkg = types.ModuleType("backend")
    _backend_pkg.__path__ = [str(_BACKEND_ROOT)]
    sys.modules["backend"] = _backend_pkg

from backend.app.main import app  # noqa: E402

__all__ = ["app"]
