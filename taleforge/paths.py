"""Resolução de assets (ASCII, áudio) a partir da raiz do projeto."""
from __future__ import annotations

from pathlib import Path

from .config import Config


def resolve_asset(config: Config, name: str, kind: str = "assets") -> Path | None:
    """Procura `name` em: caminho absoluto, raiz, pasta do tipo ([paths]) e assets/."""
    if not name:
        return None
    raw = Path(name).expanduser()
    if raw.is_absolute():
        return raw if raw.is_file() else None
    candidates = [
        config.project_dir / raw,
        config.path(kind) / raw,
        config.path("assets") / raw,
        config.path("content") / raw,
    ]
    for c in candidates:
        if c.is_file():
            return c
    return None
