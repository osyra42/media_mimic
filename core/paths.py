"""Path resolution anchored to the project root, so assets (posters, icons,
cache) resolve correctly no matter what the process's working directory is.

This module lives in core/, so the project root is its parent's parent.
"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def project_path(relative):
    """Absolute Path for something under the project root. Absolute inputs
    pass through unchanged."""
    p = Path(relative)
    return p if p.is_absolute() else PROJECT_ROOT / p
