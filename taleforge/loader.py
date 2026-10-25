"""Localização e leitura de notas (.md/.txt) com frontmatter opcional."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_FM_RE = re.compile(r"\A---[ \t]*\n(.*?)\n---[ \t]*(?:\n|\Z)", re.S)


class NoteNotFound(Exception):
    pass


@dataclass
class Note:
    name: str
    path: Path
    meta: dict[str, Any] = field(default_factory=dict)
    body: str = ""


def normalize(name: str) -> str:
    """Chave de busca tolerante: ignora caixa, espaços/_/- e extensão."""
    n = name.strip().replace("\\", "/")
    n = re.sub(r"\.(md|txt)$", "", n, flags=re.I)
    return re.sub(r"[\s_\-]+", "_", n.lower())


def _scalar(v: str) -> Any:
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        return v[1:-1]
    low = v.lower()
    if low in ("true", "yes", "on"):
        return True
    if low in ("false", "no", "off"):
        return False
    if low in ("null", "~", ""):
        return None
    try:
        return float(v) if "." in v else int(v)
    except ValueError:
        return v


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    m = _FM_RE.match(text)
    if not m:
        return {}, text
    raw, body = m.group(1), text[m.end():]
    try:
        import yaml

        data = yaml.safe_load(raw)
        return (data if isinstance(data, dict) else {}), body
    except Exception:
        pass
    meta: dict[str, Any] = {}
    key = None
    for line in raw.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.lstrip().startswith("- ") and key:
            meta.setdefault(key, [])
            if isinstance(meta[key], list):
                meta[key].append(_scalar(line.lstrip()[2:]))
            continue
        k, sep, v = line.partition(":")
        if not sep:
            continue
        key = k.strip()
        v = v.strip()
        if v.startswith("[") and v.endswith("]"):
            meta[key] = [_scalar(x) for x in v[1:-1].split(",") if x.strip()]
        elif v == "":
            meta[key] = None
        else:
            meta[key] = _scalar(v)
    return meta, body


class NoteLoader:
    def __init__(self, content_dir: Path, extensions=(".md", ".txt")):
        self.content_dir = content_dir
        self.extensions = tuple(e.lower() for e in extensions)
        self._index: dict[str, Path] | None = None
        self._cache: dict[Path, tuple[float, Note]] = {}

    def invalidate(self) -> None:
        self._index = None
        self._cache.clear()

    def _build_index(self) -> dict[str, Path]:
        index: dict[str, Path] = {}
        if self.content_dir.is_dir():
            for p in sorted(self.content_dir.rglob("*")):
                if p.is_file() and p.suffix.lower() in self.extensions:
                    rel = p.relative_to(self.content_dir).with_suffix("").as_posix()
                    index.setdefault(normalize(rel), p)
                    index.setdefault(normalize(p.stem), p)
        return index

    def names(self) -> list[str]:
        self._index = self._build_index()
        return sorted({p.relative_to(self.content_dir).with_suffix("").as_posix()
                       for p in self._index.values()})

    def find(self, name: str) -> Path | None:
        if self._index is None:
            self._index = self._build_index()
        key = normalize(name)
        path = self._index.get(key)
        if path is None:  # talvez o arquivo tenha sido criado depois
            self._index = self._build_index()
            path = self._index.get(key)
        return path

    def get(self, name: str) -> Note:
        path = self.find(name)
        if path is None:
            raise NoteNotFound(name)
        mtime = path.stat().st_mtime
        cached = self._cache.get(path)
        if cached and cached[0] == mtime:
            return cached[1]
        text = path.read_text(encoding="utf-8", errors="replace")
        meta, body = parse_frontmatter(text)
        note = Note(path.relative_to(self.content_dir).with_suffix("").as_posix(), path, meta, body)
        self._cache[path] = (mtime, note)
        return note
