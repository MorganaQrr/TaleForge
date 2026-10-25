"""Camada de áudio sobre pygame.mixer: soundFX(), music() e camadas aninhadas.

Modelo
------
* `Layer` é um nó de uma árvore de mixagem. O volume efetivo de um som é o
  produto dos volumes de todas as camadas ancestrais (a raiz é "master").
* `layer.soundFX(arquivo)` toca um efeito pontual; `layer.music(arquivo)` toca
  uma trilha contínua. Na camada raiz a trilha usa `pygame.mixer.music`
  (streaming); nas demais, um `Sound` em loop num canal próprio, o que permite
  várias trilhas simultâneas (mixagem em camadas).
* Camadas podem ser declaradas no config (`[layers.nome]`, com `parent`,
  `volume` e `sounds`) e ativadas por `[layer:nome]`, pelo frontmatter
  `layers:` da nota ou por código: `audio.layer("criaturas")`.
* Sem pygame, sem dispositivo de som ou com `audio.enabled = false`, tudo
  continua funcionando em silêncio (backend nulo).
"""
from __future__ import annotations

import logging
import os
import random
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .paths import resolve_asset

if TYPE_CHECKING:  # pragma: no cover
    from .engine import Engine

log = logging.getLogger("taleforge.audio")


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


# ------------------------------------------------------------------ backends


class NullBackend:
    available = False

    def load(self, path: Path) -> None:
        return None

    def music_play(self, path: Path, loops: int, fade_ms: int, volume: float) -> bool:
        return False

    def music_stop(self, fade_ms: int = 0) -> None: ...

    def music_volume(self, v: float) -> None: ...

    def shutdown(self) -> None: ...


class PygameBackend:
    available = True

    def __init__(self, cfg: dict):
        os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
        if cfg.get("driver"):
            os.environ["SDL_AUDIODRIVER"] = str(cfg["driver"])
        import pygame  # import tardio: só quando o áudio está habilitado

        self.pg = pygame
        pygame.mixer.init(frequency=int(cfg.get("frequency", 44100)), size=-16,
                          channels=2, buffer=int(cfg.get("buffer", 512)))
        pygame.mixer.set_num_channels(int(cfg.get("channels", 32)))
        self._cache: dict[Path, Any] = {}

    def load(self, path: Path):
        snd = self._cache.get(path)
        if snd is None:
            snd = self.pg.mixer.Sound(str(path))
            self._cache[path] = snd
        return snd

    def music_play(self, path: Path, loops: int, fade_ms: int, volume: float) -> bool:
        m = self.pg.mixer.music
        m.load(str(path))
        m.set_volume(volume)
        m.play(loops=loops, fade_ms=fade_ms)
        return True

    def music_stop(self, fade_ms: int = 0) -> None:
        # mixer.music.fadeout() bloqueia; sem fade, parar é imediato
        self.pg.mixer.music.stop()

    def music_volume(self, v: float) -> None:
        self.pg.mixer.music.set_volume(v)

    def shutdown(self) -> None:
        try:
            self.pg.mixer.quit()
        except Exception:  # pragma: no cover
            pass


# ------------------------------------------------------------------- handles


class Handle:
    """Referência a um som em reprodução (efeito, loop ou trilha)."""

    def __init__(self, layer: "Layer", base: float, category: float, *,
                 channel=None, sound=None, stream: bool = False, source: str = ""):
        self.layer, self.base, self.category = layer, base, category
        self.channel, self.sound, self.stream, self.source = channel, sound, stream, source

    @property
    def volume(self) -> float:
        return _clamp(self.base * self.category * self.layer.effective_volume)

    def apply_volume(self) -> None:
        try:
            if self.stream:
                self.layer.manager.backend.music_volume(self.volume)
            elif self.channel is not None:
                self.channel.set_volume(self.volume)
        except Exception:  # canal já liberado
            pass

    def alive(self) -> bool:
        try:
            if self.stream:
                return bool(self.layer.manager.backend.pg.mixer.music.get_busy())
            return bool(self.channel and self.channel.get_busy() and self.channel.get_sound() is self.sound)
        except Exception:
            return False

    def stop(self, fade_ms: int = 0) -> None:
        try:
            if self.stream:
                self.layer.manager.backend.music_stop(fade_ms)
            elif self.channel is not None:
                self.channel.fadeout(fade_ms) if fade_ms > 0 else self.channel.stop()
        except Exception:
            pass


@dataclass
class _Scheduled:
    files: list[str]
    lo: float
    hi: float
    volume: float
    fade_ms: int
    next_at: float = 0.0

    def reset(self, now: float) -> None:
        self.next_at = now + random.uniform(self.lo, self.hi)


# --------------------------------------------------------------------- layer


class Layer:
    def __init__(self, manager: "AudioManager", name: str, parent: "Layer | None" = None,
                 volume: float = 1.0, spec: dict | None = None):
        self.manager, self.name, self.parent = manager, name, parent
        self.volume = volume
        self.spec = spec or {}
        self.persist = bool(self.spec.get("persist", False))
        self.children: dict[str, Layer] = {}
        self.active = parent is None  # a raiz está sempre ativa
        self._handles: list[Handle] = []
        self._scheduled: list[_Scheduled] = []
        self._music: Handle | None = None
        self._music_file: str | None = None
        if parent:
            parent.children[name] = self

    # -- volume
    @property
    def effective_volume(self) -> float:
        return self.volume * (self.parent.effective_volume if self.parent else 1.0)

    def set_volume(self, v: float) -> None:
        self.volume = _clamp(float(v), 0.0, 2.0)
        self._refresh()

    def _refresh(self) -> None:
        for h in self._handles:
            h.apply_volume()
        if self._music:
            self._music.apply_volume()
        for c in self.children.values():
            c._refresh()

    # -- composição
    def layer(self, name: str, volume: float = 1.0, **spec: Any) -> "Layer":
        """Devolve (criando se preciso) uma subcamada. Ex.: `fx.layer("criaturas")`."""
        return self.manager.layer(name, parent=self, volume=volume, **spec)

    # -- reprodução
    def soundFX(self, file: str, volume: float = 1.0, loop: bool = False,
                fade_ms: int = 0) -> Handle | None:
        """Toca um efeito pontual (ou em loop) nesta camada."""
        path = self.manager.locate(file)
        if path is None:
            return None
        sound = self.manager.backend.load(path)
        if sound is None:
            return None
        try:
            channel = sound.play(loops=-1 if loop else 0, fade_ms=int(fade_ms))
        except Exception as exc:
            self.manager.warn(f"falha ao tocar {file}: {exc}")
            return None
        if channel is None:  # sem canais livres
            return None
        h = Handle(self, volume, self.manager.sfx_volume, channel=channel, sound=sound, source=file)
        h.apply_volume()
        self._handles.append(h)
        return h

    def music(self, file: str, volume: float = 1.0, loop: bool = True,
              fade_ms: int | None = None) -> Handle | None:
        """Toca uma trilha contínua; trocar de trilha substitui a anterior da camada."""
        if self._music_file == file and self._music and self._music.alive():
            self._music.base = volume
            self._music.apply_volume()
            return self._music
        fade = self.manager.fade_ms if fade_ms is None else int(fade_ms)
        self.music_stop(fade)
        path = self.manager.locate(file)
        if path is None:
            return None
        handle: Handle | None = None
        if self.parent is None:  # raiz → streaming
            h = Handle(self, volume, self.manager.music_volume, stream=True, source=file)
            try:
                ok = self.manager.backend.music_play(path, -1 if loop else 0, fade, h.volume)
            except Exception as exc:
                self.manager.warn(f"falha ao tocar música {file}: {exc}")
                ok = False
            handle = h if ok else None
        else:
            sound = self.manager.backend.load(path)
            if sound is not None:
                try:
                    ch = sound.play(loops=-1 if loop else 0, fade_ms=fade)
                except Exception as exc:
                    self.manager.warn(f"falha ao tocar música {file}: {exc}")
                    ch = None
                if ch is not None:
                    handle = Handle(self, volume, self.manager.music_volume,
                                    channel=ch, sound=sound, source=file)
                    handle.apply_volume()
        self._music, self._music_file = handle, file if handle else None
        return handle

    def music_stop(self, fade_ms: int = 0) -> None:
        if self._music:
            self._music.stop(fade_ms)
        self._music, self._music_file = None, None

    def every(self, files: str | list[str], min_s: float, max_s: float,
              volume: float = 1.0, fade_ms: int = 0) -> None:
        """Agenda um som aleatório a cada `min_s`–`max_s` segundos enquanto ativa."""
        item = _Scheduled([files] if isinstance(files, str) else list(files),
                          float(min_s), float(max_s), volume, fade_ms)
        item.reset(time.monotonic())
        self._scheduled.append(item)

    # -- ciclo de vida
    def activate(self) -> None:
        if self.parent and not self.parent.active:
            self.parent.activate()
        if self.active:
            return
        self.active = True
        self._play_spec()

    def _play_spec(self) -> None:
        for item in self.spec.get("sounds", []) or []:
            if isinstance(item, str):
                item = {"file": item}
            files = item.get("files") or item.get("file")
            if not files:
                continue
            vol = float(item.get("volume", 1.0))
            fade = int(item.get("fade_ms", 0))
            every = item.get("every")
            if every:
                lo, hi = (every if isinstance(every, (list, tuple)) else (every, every))
                self.every(files, lo, hi, vol, fade)
            else:
                f = random.choice(files) if isinstance(files, list) else files
                self.soundFX(f, vol, loop=bool(item.get("loop", False)), fade_ms=fade)

    def stop(self, fade_ms: int = 0) -> None:
        for c in self.children.values():
            c.stop(fade_ms)
        if self.parent is None:
            return
        for h in self._handles:
            h.stop(fade_ms)
        self._handles.clear()
        self._scheduled.clear()
        self.music_stop(fade_ms)
        self.active = False

    def _tick(self, now: float) -> None:
        self._handles = [h for h in self._handles if h.alive()]
        for item in self._scheduled:
            if now >= item.next_at:
                self.soundFX(random.choice(item.files), item.volume, fade_ms=item.fade_ms)
                item.reset(now)


# ------------------------------------------------------------------- manager


class AudioManager:
    def __init__(self, engine: "Engine"):
        self.engine = engine
        self.config = engine.config
        cfg = self.config.section("audio")
        self.enabled_flag = bool(cfg.get("enabled", True))
        self.sfx_volume = float(cfg.get("sfx_volume", 1.0))
        self.music_volume = float(cfg.get("music_volume", 1.0))
        self.fade_ms = int(cfg.get("fade_ms", 600))
        self.backend: NullBackend | PygameBackend = NullBackend()
        if self.enabled_flag:
            try:
                self.backend = PygameBackend(cfg)
            except Exception as exc:  # pygame ausente ou sem dispositivo de áudio
                self.warn(f"áudio desativado ({exc})")
        self._lock = threading.RLock()
        self.master = Layer(self, "master", None, float(cfg.get("master_volume", 1.0)))
        self.layers: dict[str, Layer] = {"master": self.master}
        self.stack: list[Layer] = []
        self._build_layers()
        self._stop_evt = threading.Event()
        self._thread: threading.Thread | None = None
        if self.backend.available:
            self._thread = threading.Thread(target=self._loop, name="taleforge-audio", daemon=True)
            self._thread.start()

    # -- utilidades
    @property
    def available(self) -> bool:
        return self.backend.available

    def warn(self, msg: str) -> None:
        self.engine.warn(msg)

    def locate(self, file: str) -> Path | None:
        path = resolve_asset(self.config, file, "audio")
        if path is None:
            self.warn(f"arquivo de áudio não encontrado: {file}")
        return path

    # -- camadas
    def _build_layers(self) -> None:
        specs: dict[str, dict] = {k: v for k, v in self.config.section("layers").items()
                                  if isinstance(v, dict)}

        def build(name: str, trail: tuple[str, ...] = ()) -> Layer:
            if name in self.layers:
                return self.layers[name]
            spec = specs.get(name, {})
            parent_name = spec.get("parent", "master")
            if name in trail or parent_name == name:
                self.warn(f"camada '{name}': parent cíclico, usando master")
                parent_name = "master"
            parent = build(parent_name, trail + (name,)) if parent_name in specs or parent_name in self.layers else self.master
            return self._make(name, parent, spec)

        for n in specs:
            build(n)

    def _make(self, name: str, parent: Layer, spec: dict) -> Layer:
        layer = Layer(self, name, parent, float(spec.get("volume", 1.0)), spec)
        self.layers[name] = layer
        return layer

    def layer(self, name: str, parent: Layer | None = None, volume: float | None = None,
              **spec: Any) -> Layer:
        with self._lock:
            existing = self.layers.get(name)
            if existing:
                if volume is not None:
                    existing.set_volume(volume)
                return existing
            return self._make(name, parent or self.master, {"volume": volume or 1.0, **spec})

    @property
    def current(self) -> Layer:
        return self.stack[-1] if self.stack else self.master

    # -- API pública (camada corrente)
    def soundFX(self, file: str, volume: float = 1.0, loop: bool = False, fade_ms: int = 0):
        with self._lock:
            return self.current.soundFX(file, volume, loop, fade_ms)

    def music(self, file: str, volume: float = 1.0, loop: bool = True, fade_ms: int | None = None):
        with self._lock:
            return self.current.music(file, volume, loop, fade_ms)

    def music_stop(self, fade_ms: int | None = None) -> None:
        with self._lock:
            self.current.music_stop(self.fade_ms if fade_ms is None else fade_ms)

    # -- controle de cenas
    def enter_layer(self, name: str) -> Layer:
        with self._lock:
            layer = self.layer(name)
            layer.activate()
            self.stack.append(layer)
            return layer

    def exit_layer(self) -> None:
        with self._lock:
            if self.stack:
                self.stack.pop()

    def stop_layer(self, name: str, fade_ms: int | None = None) -> None:
        with self._lock:
            layer = self.layers.get(name)
            if layer and layer is not self.master:
                layer.stop(self.fade_ms if fade_ms is None else fade_ms)
            self.stack = [l for l in self.stack if l.active]

    def set_volume(self, name: str, value: float) -> None:
        with self._lock:
            self.layer(name).set_volume(value)

    def sync_layers(self, names: list[str]) -> None:
        """Deixa ativas exatamente as camadas de `names` (mais as marcadas persist)."""
        with self._lock:
            wanted: set[str] = set()
            for n in names:
                layer = self.layer(n)
                wanted.add(n)
                while layer.parent is not None:  # ancestrais contam como desejados
                    wanted.add(layer.name)
                    layer = layer.parent
            for name, layer in list(self.layers.items()):
                if layer.parent is not None and layer.active and name not in wanted and not layer.persist:
                    layer.stop(self.fade_ms)
            for n in names:
                self.layers[n].activate()

    def stop_all(self, fade_ms: int = 0) -> None:
        with self._lock:
            self.master.stop(fade_ms)
            self.master.music_stop(fade_ms)
            self.stack.clear()

    # -- thread de agendamento
    def _loop(self) -> None:
        while not self._stop_evt.wait(0.1):
            with self._lock:
                now = time.monotonic()
                for layer in list(self.layers.values()):
                    if layer.active:
                        layer._tick(now)

    def shutdown(self) -> None:
        self._stop_evt.set()
        if self._thread:
            self._thread.join(timeout=1)
        with self._lock:
            try:
                self.stop_all(0)
            finally:
                self.backend.shutdown()
