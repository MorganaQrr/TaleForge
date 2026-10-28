"""Engine: junta configuração, notas, renderização, menu, áudio e hooks."""
from __future__ import annotations

import importlib
import importlib.util
import logging
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from rich.console import Console

from . import directives as _builtin_directives  # noqa: F401  (registra as diretivas)
from . import input as keys
from . import menu
from .audio import AudioManager
from .config import Config
from .directives import parse_hook_line
from .loader import Note, NoteLoader, NoteNotFound
from .markup import Option, options_of, parse_note
from .registry import _DEFAULT_HOOKS, Registry, collecting
from .renderer import Renderer, TextState
from .watch import Watcher

log = logging.getLogger("taleforge")


@dataclass
class _Nav:
    kind: str  # goto | back | restart | reload | quit
    target: str = ""


class Engine:
    """Executa um projeto TaleForge (uma pasta com notas .md/.txt e assets).

        Engine("meu_rpg").run()
    """

    def __init__(self, project: str | Path = ".", *, config: Config | None = None,
                 console: Console | None = None, instant: bool | None = None,
                 audio: bool | None = None, hot_reload: bool | None = None):
        self.config = config or Config.load(project)
        if instant is not None:
            self.config.set("text.instant", instant)
        if audio is not None:
            self.config.set("audio.enabled", audio)
        if hot_reload is not None:
            self.config.set("dev.hot_reload", hot_reload)
        self.project_dir = self.config.project_dir
        self.console = console or Console(highlight=False)
        self.warnings: list[str] = []
        self.state: dict[str, Any] = {}      # estado livre para hooks (inventário, flags…)
        self.history: list[str] = []
        self.current: Note | None = None
        self.stop_rendering = False
        self._nav: _Nav | None = None
        self._changed = threading.Event()
        self._watcher: Watcher | None = None
        self.extra_options: dict[str, str] = {}
        self.global_options: dict[str, str] = {}
        self.ignored_options: set[str] = set()

        self.registry = Registry(self.config.get("directives.aliases"),
                                 self.config.get("directives.disabled", []))
        self.hooks: dict[str, Callable] = dict(_DEFAULT_HOOKS)
        self.loader = NoteLoader(self.config.path("content"))
        self._load_modules()
        self.renderer = Renderer(self)
        self.audio = AudioManager(self)

    # ------------------------------------------------------------ plugins
    def _load_modules(self) -> None:
        """Importa plugins ([plugins].modules) e hooks do projeto ([hooks].modules)."""
        if str(self.project_dir) not in sys.path:
            sys.path.insert(0, str(self.project_dir))
        explicit_plugins = list(self.config.get("plugins.modules", []) or [])
        hook_mods = list(self.config.get("hooks.modules", []) or [])
        with collecting(self.registry.specs, self.hooks):
            for name in explicit_plugins:
                self._import(name, required=True, project_only=False)
            for name in hook_mods:  # hooks vêm sempre da pasta do projeto
                self._import(name, required=name != "hooks", project_only=True)

    def _import(self, name: str, required: bool, project_only: bool) -> None:
        file = self.project_dir / f"{name.replace('.', '/')}.py"
        try:
            if project_only and not file.is_file():
                raise ModuleNotFoundError(f"{file.name} não existe em {self.project_dir}")
            if file.is_file():
                spec = importlib.util.spec_from_file_location(f"_taleforge_{abs(hash(file))}_{name}", file)
                module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
                spec.loader.exec_module(module)  # type: ignore[union-attr]
            elif name in sys.modules:
                importlib.reload(sys.modules[name])
            else:
                importlib.import_module(name)
        except ModuleNotFoundError as exc:
            if required:
                self.warn(f"módulo '{name}' não encontrado: {exc}")
        except Exception as exc:
            self.warn(f"erro ao carregar '{name}': {exc}")

    # ------------------------------------------------------------ utilidades
    def warn(self, msg: str) -> None:
        log.warning(msg)
        self.warnings.append(msg)

    def say(self, markup: str, newline: bool = True) -> None:
        """Renderiza um trecho de marcação a partir de um hook."""
        tokens = parse_note(markup, self._known, markdown=bool(self.config.get("text.markdown", True)),
                            ascii_exts=self._ascii_exts())
        self.renderer.render(tokens)
        if newline:
            self.renderer.ensure_newline()

    def _known(self, name: str) -> str | None:
        spec = self.registry.resolve(name)
        return spec.name if spec else None

    def _ascii_exts(self) -> tuple[str, ...]:
        return tuple(e.lower() for e in self.config.get("ascii.extensions", [".txt"]))

    def poll_changed(self) -> bool:
        if self._changed.is_set():
            self._changed.clear()
            return True
        return False

    # ----------------------------------------------------------------- hooks
    def call_hook(self, name: str, args: list[str] | tuple = ()) -> Any:
        fn = self.hooks.get(name.lower())
        if fn is None:
            self.warn(f"hook não encontrado: {name}")
            self.renderer.error(f"[hook '{name}' não existe]")
            return None
        try:
            return fn(self, *args)
        except Exception as exc:
            self.warn(f"erro no hook {name}: {exc}")
            log.exception("hook %s falhou", name)
            self.renderer.error(f"[erro no hook '{name}': {exc}]")
            return None

    def run_hook_line(self, line: str) -> Any:
        name, args = parse_hook_line(line)
        return self.call_hook(name, args) if name else None

    # ------------------------------------------------------------ navegação
    def goto(self, note: str) -> None:
        self._nav = _Nav("goto", note)

    def back(self) -> None:
        self._nav = _Nav("back")

    def restart(self) -> None:
        self._nav = _Nav("restart")

    def reload_note(self) -> None:
        self._nav = _Nav("reload")

    def quit(self) -> None:
        self._nav = _Nav("quit")

    # ------------------------------------------------------------------ run
    def run(self, start: str | None = None) -> None:
        start = start or str(self.config.get("project.start", "inicio"))
        with keys.terminal_session():
            self._start_watch()
            try:
                self._loop(start)
            except KeyboardInterrupt:
                pass
            finally:
                self.renderer.ensure_newline()
                self._stop_watch()
                self.audio.shutdown()

    def _loop(self, start: str) -> None:
        nav: _Nav | None = _Nav("goto", start)
        first = True
        while nav and nav.kind != "quit":
            push, instant_once = True, False
            if nav.kind == "back":
                if not self.history:
                    nav = _Nav("reload")
                    continue
                target, push = self.history.pop(), False
            elif nav.kind == "restart":
                self.history.clear()
                self.state.clear()
                target, push = start, False
            elif nav.kind == "reload":
                if self.current is None:
                    break
                target, push = self.current.name, False
                instant_once = bool(self.config.get("dev.instant_reload", True))
            else:
                target = nav.target
            try:
                note = self.loader.get(target)
            except NoteNotFound:
                self.renderer.error(f"[nota não encontrada: {target}]")
                self.warn(f"nota não encontrada: {target}")
                if first or self.current is None:
                    break
                nav = _Nav("reload") if nav.kind != "reload" else None
                continue
            first = False
            if push and self.current is not None:
                self.history.append(self.current.name)
            self.current = note
            self._nav = None
            was_instant = self.config.get("text.instant")
            if instant_once:
                self.config.set("text.instant", True)
            try:
                self._play(note, reloading=instant_once)
            finally:
                self.config.set("text.instant", was_instant)
            nav, self._nav = self._nav, None

    def _play(self, note: Note, reloading: bool = False) -> None:
        # Para evitar de ter opções da nota anterior nas próximas, limpamos os dicionários
        self.extra_options = {}
        self.ignored_options = set()
        self.extra_options = {}
        self.ignored_options = set()
        self.audio.reset_ui_sounds()
        self._apply_scene(note)
        self._run_tag_hooks(note)
        self._apply_scene(note)
        self._run_tag_hooks(note)  # <-- Roda os hooks de todas as tags da nota!
        r = self.renderer
        if reloading or self.config.get("behavior.clear_on_scene", True):
            r.clear()
        tokens = parse_note(note.body, self._known,
                            markdown=bool(self.config.get("text.markdown", True)),
                            ascii_exts=self._ascii_exts())
        r.begin_note()
        r.render(tokens, note)
        if self._nav:  # [goto], [end] ou hook durante o texto
            return
        options = options_of(tokens)

        # Opções extras (extra_options{}) =============================
        for name, content in self.extra_options.items():
            options.append(Option(content, name))
        # opções globais (global_options{})
        for name, content in self.global_options.items():
            if content == note.name or name in self.ignored_options or content in self.ignored_options:
                continue
            options.append(Option(content, name))
        # ============================================================
        if not options:
            self._dead_end()
            return
        self._menu_loop(options)

    def _menu_loop(self, options) -> None:
        while True:
            choice = menu.choose(self, options)
            if choice == "quit":
                return self.quit()
            if choice == "back":
                if self.history:
                    return self.back()
                continue
            if choice == "reload":
                return self.reload_note()
            opt = options[choice]  # type: ignore[index]
            if opt.is_hook:
                ret = self.run_hook_line(opt.target[1:])
                if self._nav:
                    return
                if isinstance(ret, str) and ret:
                    return self.goto(ret)
                continue  # hook executado; o menu permanece
            return self.goto(opt.target)

    def _dead_end(self) -> None:
        r = self.renderer
        if self.config.get("behavior.on_dead_end", "quit") == "back" and self.history:
            return self.back()
        end_text = str(self.config.get("behavior.end_text", ""))
        r.ensure_newline()
        if end_text:
            r.write("\n" + r.paint(end_text, r.theme("dim")) + "\n")
        if keys.is_interactive() and not r.instant:
            if keys.read_key(on_idle=self.poll_changed) == "reload":
                return self.reload_note()
        self.quit()

    def _apply_scene(self, note: Note) -> None:
        """Interpreta o frontmatter da nota: music, layers, sound."""
        meta = note.meta
        if "layers" in meta:
            raw = meta["layers"]
            names = [str(x).strip() for x in (raw if isinstance(raw, list) else str(raw or "").split(","))]
            self.audio.sync_layers([n for n in names if n])
        if "music" in meta:
            track = meta["music"]
            if track in (None, "", False) or str(track).lower() in ("none", "stop", "parar"):
                self.audio.music_stop()
            else:
                self.audio.music(str(track))
        if meta.get("sound"):
            self.audio.soundFX(str(meta["sound"]))
        if "ui_sound" in meta:
            ui = meta["ui_sound"]
            if isinstance(ui, dict):
                for kind in ("move", "select"):
                    if kind in ui:
                        self.audio.set_ui_sound(kind, str(ui[kind]) if ui[kind] else None)
            elif ui in (False, "off", "false"):
                self.audio.set_ui_sound("off", None)

    # ------------------------------------------------------------ hot-reload
    def _start_watch(self) -> None:
        if not self.config.get("dev.hot_reload", False):
            return
        paths = [self.config.path("content"), self.config.path("assets")]
        if self.config.source:
            paths.append(self.config.source)
        hooks_file = self.project_dir / "hooks.py"
        if hooks_file.exists():
            paths.append(hooks_file)

        def on_change(path: Path) -> None:
            if self.config.source and path == self.config.source:
                try:
                    self.config.reload()
                except Exception as exc:
                    self.warn(f"config inválido: {exc}")
            self.loader.invalidate()
            self._changed.set()

        self._watcher = Watcher(paths, on_change, float(self.config.get("dev.poll_interval", 0.5)))
        self._watcher.start()

    def _stop_watch(self) -> None:
        if self._watcher:
            self._watcher.stop()
            self._watcher = None

    def add_option(self, name, content, target=None):
        if target is None:
            target = self.extra_options
        target[name] = content

    def remove_option(self, name, target=None):
        if target is None:
            target = self.extra_options
        target.pop(name, None)

    def _run_tag_hooks(self, note: Note) -> None:
        import re
        tags: set[str] = set()

        # 1. Pega tags do frontmatter YAML (se houver: tags: [title, menu])
        meta_tags = note.meta.get("tags", [])
        if isinstance(meta_tags, str):
            meta_tags = [t.strip() for t in meta_tags.split(",")]
        for t in (meta_tags or []):
            tags.add(str(t).lstrip("#").strip().lower())

        # 2. Pega tags de [tag: #title, #outra] escritas no corpo da nota
        for m in re.finditer(r"\[tag:([^\[\]\n]+)\]", note.body, re.I):
            for raw_t in re.split(r"[,\s]+", m.group(1).strip()):
                clean_t = raw_t.lstrip("#").strip().lower()
                if clean_t:
                    tags.add(clean_t)

        # 3. Dispara os hooks correspondentes para cada tag encontrada
        for tag in tags:
            # Se existir um @hook("tag_title"), chama ele!
            hook_name = f"tag_{tag}"
            if hook_name in self.hooks:
                self.call_hook(hook_name)
            # Se existir um @hook("on_tag") genérico, passa o nome da tag como argumento
            if "on_tag" in self.hooks:
                self.call_hook("on_tag", [tag])

    def ask(self, prompt: str = "", state_key: str | None = None, default: str = "") -> str:
        """Renderiza o prompt com self.say e coleta input restaurando o echo do terminal."""
        if prompt:
            self.say(prompt, newline=False)

        try:
            import termios
            fd = sys.stdin.fileno()
            old_settings = termios.tcgetattr(fd)
            new_settings = termios.tcgetattr(fd)
            # Liga de volta o modo canônico (esperar Enter) e o Echo (mostrar letras na tela)
            new_settings[3] = new_settings[3] | termios.ICANON | termios.ECHO
            termios.tcsetattr(fd, termios.TCSADRAIN, new_settings)
            try:
                resposta = input().strip()
            finally:
                # Devolve o terminal exatamente para o estado da engine
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        except Exception:
            # Fallback caso rode fora de um TTY padrão
            resposta = input().strip()

        valor_final = resposta if resposta else default
        if state_key:
            self.state[state_key] = valor_final

        return valor_final


# --------------------------------------------------------- hooks embutidos
def _builtin(name: str):
    def deco(fn):
        _DEFAULT_HOOKS[name] = fn
        return fn
    return deco


@_builtin("quit")
def _hook_quit(engine: Engine, *args) -> None:
    engine.quit()


@_builtin("back")
def _hook_back(engine: Engine, *args) -> None:
    engine.back()


@_builtin("restart")
def _hook_restart(engine: Engine, *args) -> None:
    engine.restart()


@_builtin("reload")
def _hook_reload(engine: Engine, *args) -> None:
    engine.reload_note()


@_builtin("goto")
def _hook_goto(engine: Engine, note: str = "", *args) -> None:
    if note:
        engine.goto(note)


@_builtin("ask")
def _hook_ask(engine: Engine, state_key: str = "resposta", *prompt_parts) -> None:
    prompt = " ".join(prompt_parts) + " " if prompt_parts else "> "
    engine.ask(prompt, state_key=state_key)
