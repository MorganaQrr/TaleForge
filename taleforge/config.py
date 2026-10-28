"""Carregamento e mesclagem de configuração (TOML ou YAML) com valores padrão.

Todo comportamento da engine que pode variar entre projetos vive aqui:
um projeto sem nenhum arquivo de configuração funciona com os padrões.
"""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10
    try:
        import tomli as tomllib  # type: ignore
    except ModuleNotFoundError:
        tomllib = None  # type: ignore

CONFIG_NAMES = ("config.toml", "settings.toml", "settings.yaml", "settings.yml")

DEFAULTS: dict[str, Any] = {
    "ui_sound": {
        "enabled": True,       # liga/desliga todos os sons de interface
        "move": "",            # arquivo relativo a assets/audio (vazio = silêncio)
        "select": "",
        "volume": 1.0,
    },
    "voice": {
    "enabled": True, 
    "default": "padrao", 
    "volume": 0.5, 
    "every": 2, 
    "min_gap": 0.03},
    
    "project": {"name": "TaleForge", "start": "inicio"},
    "paths": {
        "content": "content",
        "assets": "assets",
        "ascii": "assets/ascii",
        "audio": "assets/audio",
    },
    "text": {
        "type_speed": 45.0,      # caracteres por segundo (velocidade base)
        "jitter": 0.25,          # variação aleatória do ritmo (0 = metronômico)
        "instant": False,        # true = sem atrasos (útil p/ testes e CI)
        "skippable": True,       # qualquer tecla acelera o texto atual
        "markdown": True,        # **negrito**, *itálico*, # título, > citação, ---
        "max_width": 0,          # 0 = largura do terminal
        "wait_prompt": "▼",
        "pauses": {
            ".": 0.30, "!": 0.30, "?": 0.30, "…": 0.35,
            ",": 0.12, ";": 0.15, ":": 0.15, "\n": 0.12,
        },
    },
    "theme": {
        "text": "",
        "option": "underline cyan",
        "menu_item": "",
        "menu_selected": "bold cyan",
        "menu_cursor": "▶",
        "menu_hint": "dim",
        "rule": "dim",
        "error": "bold red",
        "dim": "dim",
        "background": "#000000",  # usado para misturar cores com alfa (#RGBA)
    },
    "effects": {"shake_frames": 14, "shake_interval": 0.03, "max_shake": 3},
    "ascii": {
        "mode": "line",          # instant | line
        "line_delay": 0.04,
        "extensions": [".txt", ".ans", ".asc", ".art",".md"],
    },
    "menu": {
        "show_numbers": True,
        "number_confirms": True,
        "spacing": 1,
        "hint": "↑/↓ ou número · Enter confirma · Backspace volta",
    },
    "audio": {
        "enabled": True,
        "driver": "",            # ex.: "dummy" para rodar sem placa de som
        "frequency": 44100,
        "buffer": 512,
        "channels": 32,
        "master_volume": 1.0,
        "music_volume": 1.0,
        "sfx_volume": 1.0,
        "fade_ms": 600,
    },
    "layers": {},
    "styles": {
        "heading": {"bold": True, "color": "yellow"},
        "quote": {"italic": True, "dim": True},
        "code": {"dim": True},
    },
    "directives": {
        "disabled": [],
        "aliases": {
            "cor": "color", "fundo": "bg", "negrito": "bold", "italico": "italic",
            "sublinhado": "underline", "pausa": "pause", "espera": "wait",
            "velocidade": "type_speed", "tremor": "shake", "tremer": "jolt",
            "som": "sound", "musica": "music", "camada": "layer",
            "arte": "ascii", "limpar": "clear", "estilo": "style", "fim": "end",
        },
    },
    "plugins": {"modules": []},
    "hooks": {"modules": ["hooks"]},
    "behavior": {
        "on_dead_end": "quit",   # quit | back
        "clear_on_scene": True,
        "end_text": "— Fim —",
    },
    "dev": {"hot_reload": False, "poll_interval": 0.5, "instant_reload": True},
}


class ConfigError(Exception):
    """Erro ao ler ou interpretar o arquivo de configuração."""


def deep_merge(base: dict, extra: dict) -> dict:
    """Mescla `extra` sobre `base` recursivamente, sem alterar os originais."""
    out = copy.deepcopy(base)
    for key, value in (extra or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def find_config(project_dir: Path) -> Path | None:
    for name in CONFIG_NAMES:
        candidate = project_dir / name
        if candidate.is_file():
            return candidate
    return None


def read_file(path: Path) -> dict:
    suffix = path.suffix.lower()
    try:
        if suffix == ".toml":
            if tomllib is None:
                raise ConfigError("Python 3.10 precisa do pacote 'tomli' para ler TOML.")
            with path.open("rb") as fh:
                return tomllib.load(fh)
        if suffix in (".yaml", ".yml"):
            try:
                import yaml
            except ModuleNotFoundError as exc:
                raise ConfigError("Instale 'pyyaml' para usar settings.yaml.") from exc
            with path.open("r", encoding="utf-8") as fh:
                return yaml.safe_load(fh) or {}
    except ConfigError:
        raise
    except Exception as exc:  # sintaxe inválida etc.
        raise ConfigError(f"Erro lendo {path.name}: {exc}") from exc
    raise ConfigError(f"Formato de configuração não suportado: {path.name}")


class Config:
    """Acesso por caminho pontilhado: `config.get("text.type_speed")`."""

    def __init__(self, data: dict, project_dir: Path, source: Path | None = None):
        self.data = data
        self.project_dir = project_dir
        self.source = source

    @classmethod
    def load(cls, project: str | Path = ".") -> "Config":
        path = Path(project).expanduser()
        source: Path | None
        if path.is_file():
            source, project_dir = path, path.parent
        else:
            project_dir, source = path, find_config(path)
        project_dir = project_dir.resolve()
        user = read_file(source) if source else {}
        return cls(deep_merge(DEFAULTS, user), project_dir, source)

    def reload(self) -> None:
        user = read_file(self.source) if self.source else {}
        self.data = deep_merge(DEFAULTS, user)

    def get(self, dotted: str, default: Any = None) -> Any:
        node: Any = self.data
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def set(self, dotted: str, value: Any) -> None:
        parts = dotted.split(".")
        node = self.data
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value

    def section(self, name: str) -> dict:
        value = self.get(name, {})
        return value if isinstance(value, dict) else {}

    def path(self, key: str) -> Path:
        """Pasta configurada em [paths], resolvida a partir da raiz do projeto."""
        rel = self.get(f"paths.{key}", key)
        return (self.project_dir / rel).resolve()
