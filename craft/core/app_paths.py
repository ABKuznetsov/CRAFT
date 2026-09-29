from __future__ import annotations

from pathlib import Path

from platformdirs import user_data_dir


def craft_data_dir(*, base: str | Path | None = None) -> Path:
    """Return the portable per-user Sci data directory for CRAFT."""
    sci_root = Path(base) / "Sci" if base is not None else Path(user_data_dir("Sci", appauthor=False))
    return sci_root / "craft"


def craft_presets_dir(*, base: str | Path | None = None) -> Path:
    """User-authored knowledge lives outside disposable computed caches."""
    return craft_data_dir(base=base) / "presets"


def craft_knowledge_index(*, base: str | Path | None = None) -> Path:
    """Return the rebuildable index of user-authored structural knowledge."""
    return craft_data_dir(base=base) / "knowledge-index.json"


__all__ = [
    "craft_data_dir",
    "craft_knowledge_index",
    "craft_presets_dir",
]
