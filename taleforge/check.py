"""`taleforge check`: valida um projeto sem executá-lo (links, assets, diretivas, hooks)."""
from __future__ import annotations

from dataclasses import dataclass, field

from .directives import split_args
from .engine import Engine
from .loader import normalize
from .markup import Embed, Option, Tag, parse_note
from .paths import resolve_asset


@dataclass
class Report:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    notes: int = 0

    @property
    def ok(self) -> bool:
        return not self.errors


def check_project(engine: Engine) -> Report:
    rep = Report()
    cfg, loader = engine.config, engine.loader
    names = loader.names()
    rep.notes = len(names)
    start = str(cfg.get("project.start", "inicio"))
    if loader.find(start) is None:
        rep.errors.append(f"nota inicial '{start}' não existe em {cfg.path('content')}")
    linked: set[str] = {normalize(start)}
    asset_dirs = {"ascii": "ascii", "sound": "audio", "music": "audio"}

    for name in names:
        note = loader.get(name)
        unknown: list[str] = []
        tokens = parse_note(note.body, engine._known,
                            markdown=bool(cfg.get("text.markdown", True)),
                            ascii_exts=engine._ascii_exts(), unknown=unknown)
        where = f"{name}"
        for u in sorted(set(unknown)):
            rep.warnings.append(f"{where}: diretiva desconhecida [{u}:...] (ficará como texto)")
        for tok in tokens:
            if isinstance(tok, Option):
                if tok.is_hook:
                    hook_name = tok.target[1:].split()[0].lower() if tok.target[1:].split() else ""
                    if hook_name not in engine.hooks:
                        rep.errors.append(f"{where}: hook '{hook_name}' não existe ({tok.raw})")
                    if hook_name == "goto" and len(tok.target.split()) > 1:
                        linked.add(normalize(tok.target.split()[1]))
                elif loader.find(tok.target) is None:
                    rep.errors.append(f"{where}: link para nota inexistente '{tok.target}'")
                else:
                    linked.add(normalize(tok.target))
            elif isinstance(tok, Embed):
                if resolve_asset(cfg, tok.path, "ascii") is None:
                    rep.errors.append(f"{where}: arte ASCII não encontrada '{tok.path}'")
            elif isinstance(tok, Tag) and not tok.closing:
                if tok.name in asset_dirs and tok.value:
                    path, _ = split_args(tok.value)
                    if tok.name == "music" and path.lower() in ("stop", "none", "parar"):
                        continue
                    if resolve_asset(cfg, path, asset_dirs[tok.name]) is None:
                        rep.errors.append(f"{where}: arquivo não encontrado em {tok.raw}")
                elif tok.name == "goto" and tok.value:
                    if loader.find(tok.value) is None:
                        rep.errors.append(f"{where}: [goto] para nota inexistente '{tok.value}'")
                    else:
                        linked.add(normalize(tok.value))
                elif tok.name in ("layer", "stop_layer") and tok.value:
                    if tok.value not in engine.audio.layers:
                        rep.warnings.append(f"{where}: camada '{tok.value}' não está em [layers] (será criada vazia)")
                elif tok.name == "hook" and tok.value:
                    hn = tok.value.split()[0].lower()
                    if hn not in engine.hooks:
                        rep.errors.append(f"{where}: hook '{hn}' não existe")
        meta = note.meta
        if meta.get("music") and str(meta["music"]).lower() not in ("none", "stop", "parar"):
            if resolve_asset(cfg, str(meta["music"]), "audio") is None:
                rep.errors.append(f"{where}: música '{meta['music']}' não encontrada")
        if meta.get("sound") and resolve_asset(cfg, str(meta["sound"]), "audio") is None:
            rep.errors.append(f"{where}: som '{meta['sound']}' não encontrado")
        raw = meta.get("layers")
        for ln in (raw if isinstance(raw, list) else str(raw or "").split(",")):
            ln = str(ln).strip()
            if ln and ln not in engine.audio.layers:
                rep.warnings.append(f"{where}: camada '{ln}' (frontmatter) não está em [layers]")

    for name in names:
        if loader.get(name).meta.get("entry"):  # alcançada por hook/código
            continue
        if normalize(name) not in linked and normalize(name.split("/")[-1]) not in linked:
            rep.warnings.append(f"{name}: nenhuma nota aponta para ela (órfã)")
    for lname, layer in engine.audio.layers.items():
        for item in (layer.spec.get("sounds") or []):
            files = item if isinstance(item, str) else (item.get("files") or item.get("file") or [])
            for f in ([files] if isinstance(files, str) else files):
                if resolve_asset(cfg, f, "audio") is None:
                    rep.errors.append(f"[layers.{lname}]: som não encontrado '{f}'")
    rep.warnings.extend(engine.warnings)
    return rep
