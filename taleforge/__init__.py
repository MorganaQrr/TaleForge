"""TaleForge — engine modular de RPG textual para terminal Linux."""
from __future__ import annotations

__version__ = "0.1.0"

from . import directives as _directives  # noqa: F401  (registra diretivas embutidas)
from .config import Config
from .engine import Engine
from .registry import directive, hook

__all__ = ["Engine", "Config", "directive", "hook", "__version__"]
