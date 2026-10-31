"""Diretivas de marcação embutidas. Todas usam o mesmo mecanismo dos plugins."""
from __future__ import annotations

import shlex
from typing import TYPE_CHECKING

from .colors import parse_color
from .registry import directive

if TYPE_CHECKING:  # pragma: no cover
    from .renderer import RenderContext

_FALSE = {"0", "false", "no", "off", "nao", "não"}


def truthy(value: str | None) -> bool:
    return True if value is None else value.strip().lower() not in _FALSE


def split_args(value: str | None) -> tuple[str, dict[str, str]]:
    """`arquivo.ogg, volume=0.5, loop=true` → ("arquivo.ogg", {...})."""
    if not value:
        return "", {}
    head, *rest = [p.strip() for p in value.split(",")]
    kw: dict[str, str] = {}
    for part in rest:
        if "=" in part:
            k, v = part.split("=", 1)
            kw[k.strip().lower()] = v.strip()
    return head, kw


def _bg(ctx: "RenderContext") -> str:
    return str(ctx.engine.config.get("theme.background", "#000000"))


# ------------------------------------------------------------ estados (state)


@directive("color", kind="state")
def color(ctx, value, closing):
    """[color:#0fff] / [color:red] — cor do texto. [/color] volta ao padrão."""
    ctx.state.color = None if closing or not value else parse_color(value, _bg(ctx))


@directive("bg", kind="state")
def bg(ctx, value, closing):
    """[bg:#222] — cor de fundo do texto."""
    ctx.state.bg = None if closing or not value else parse_color(value, _bg(ctx))


def _flag(attr: str):
    def handler(ctx, value, closing):
        setattr(ctx.state, attr, False if closing else truthy(value))

    handler.__doc__ = f"[{attr}] … [/{attr}]"
    return handler


for _name in ("bold", "italic", "underline", "dim", "strike"):
    directive(_name, kind="state")(_flag(_name))


@directive("type_speed", kind="state")
def type_speed(ctx, value, closing):
    """[type_speed:0.5] — multiplicador da velocidade (0.5 = metade; 0 = instantâneo).
    Também aceita [type_speed:80cps] para caracteres por segundo."""
    if closing or not value:
        ctx.state.speed = 1.0
        return
    v = value.strip().lower()
    if v.endswith("cps"):
        ctx.state.speed = max(float(v[:-3]), 0.0) / ctx.renderer.base_cps
    else:
        ctx.state.speed = max(float(v), 0.0)


@directive("shake", kind="state")
def shake(ctx, value, closing):
    """[shake:3] — o texto seguinte treme (amplitude em colunas). [/shake] encerra."""
    ctx.state.shake = 0 if closing else int(float(value)) if value else 2


@directive("style", kind="state")
def style(ctx, value, closing):
    """[style:perigo] — aplica um preset de [styles.perigo] do config. [/style] limpa tudo."""
    if closing:
        ctx.state.reset()
        return
    preset = ctx.engine.config.get(f"styles.{value}")
    if not isinstance(preset, dict):
        ctx.engine.warn(f"estilo não definido em [styles]: {value}")
        return
    for key, val in preset.items():
        if val is True:
            ctx.apply(key, None)
        elif val is False:
            ctx.apply(key, None, closing=True)
        else:
            ctx.apply(key, str(val))


@directive("reset")
def reset(ctx, value, closing):
    """[reset] — limpa todos os estilos."""
    ctx.state.reset()


# --------------------------------------------------------- eventos (event)


@directive("pause")
def pause(ctx, value, closing):
    """[pause:1.5] — pausa em segundos (pulável).
    [pause:1.5, force=true] — pausa obrigatória, o Enter não pula."""
    if not value:
        ctx.renderer.sleep(0.5)
        return
    head, kw = split_args(value)
    secs = float(head) if head else 0.5
    force = truthy(kw.get("force", kw.get("obrigatorio", kw.get("r", "false"))))
    ctx.renderer.sleep(secs, force=force)
    
@directive("wait")
def wait(ctx, value, closing):
    """[wait] — espera uma tecla (texto opcional no lugar do ▼)."""
    ctx.renderer.wait_key(value)


@directive("clear")
def clear(ctx, value, closing):
    """[clear] — limpa a tela."""
    ctx.renderer.clear()


@directive("rule")
def rule(ctx, value, closing):
    """[rule] ou `---` — linha horizontal."""
    ctx.renderer.rule()


@directive("jolt")
def jolt(ctx, value, closing):
    """[jolt:3] — treme a linha atual uma vez, agora."""
    ctx.renderer.jitter(int(float(value)) if value else 2)


@directive("ascii")
def ascii_art(ctx, value, closing):
    """[ascii:caminho.txt, color=red, align=center, mode=instant] — carrega arte ASCII."""
    path, kw = split_args(value)
    color_ = parse_color(kw["color"], _bg(ctx)) if "color" in kw else None
    ctx.renderer.print_ascii(path, ctx.state, color_, kw.get("align", "left"), kw.get("mode"))


@directive("sound")
def sound(ctx, value, closing):
    """[sound:passos.ogg, volume=0.8, loop=true, fade=500] — efeito pontual."""
    path, kw = split_args(value)
    ctx.engine.audio.soundFX(path, float(kw.get("volume", kw.get("vol", 1.0))),
                             truthy(kw.get("loop", "false")), int(kw.get("fade", 0)))


@directive("music")
def music(ctx, value, closing):
    """[music:tema.ogg, volume=0.6, fade=1500] — trilha contínua.
    [music:stop] para. [music:pause] pausa (mantém posição).
    [music:play] retoma. [music:play -r] recomeça do início.
    [music:pause -r] pausa e marca para recomeçar ao retomar."""
    if not value:
        return
    path, kw = split_args(value)

    # Flag "-r" / "--restart" no final do path (aceita "[music:play -r]")
    restart = False
    if path:
        for flag in (" -r", " --restart", " -restart"):
            if path.lower().endswith(flag):
                path = path[: -len(flag)].rstrip()
                restart = True
                break

    cmd = (path or "").strip().lower()
    audio = ctx.engine.audio

    if cmd in ("stop", "none", "parar"):
        audio.music_stop(int(kw["fade"]) if "fade" in kw else None)
        return
    if cmd in ("pause", "pausar"):
        restart = restart or truthy(kw.get("r", kw.get("restart", "false")))
        audio.music_pause(restart)
        return
    if cmd in ("play", "resume", "retomar", "continuar", "tocar"):
        restart = restart or truthy(kw.get("r", kw.get("restart", "false")))
        audio.music_resume(restart)
        return
    if not path:
        return
    audio.music(path, float(kw.get("volume", kw.get("vol", 1.0))),
                truthy(kw.get("loop", "true")),
                int(kw["fade"]) if "fade" in kw else None)

@directive("music_stop")
def music_stop(ctx, value, closing):
    """[music_stop] — para a trilha da camada corrente."""
    ctx.engine.audio.music_stop(int(float(value)) if value else None)


@directive("layer")
def layer(ctx, value, closing):
    """[layer:criaturas] … [/layer] — ativa a camada e a torna corrente até [/layer]."""
    if closing:
        ctx.engine.audio.exit_layer()
    elif value:
        ctx.engine.audio.enter_layer(value)


@directive("stop_layer")
def stop_layer(ctx, value, closing):
    """[stop_layer:criaturas] — para a camada (e suas subcamadas)."""
    if value:
        ctx.engine.audio.stop_layer(value)


@directive("volume")
def volume(ctx, value, closing):
    """[volume:0.5] (camada corrente) ou [volume:criaturas=0.3]."""
    if not value:
        return
    name, _, num = value.rpartition("=")
    ctx.engine.audio.set_volume(name.strip() or ctx.engine.audio.current.name, float(num))


@directive("hook")
def hook_call(ctx, value, closing):
    """[hook:nome arg1 arg2] — chama um hook do projeto no meio do texto."""
    if value:
        ctx.engine.run_hook_line(value)


@directive("goto")
def goto(ctx, value, closing):
    """[goto:nota] — ao fim do texto, salta para a nota (sem menu)."""
    if value:
        ctx.engine.goto(value)


@directive("end")
def end(ctx, value, closing):
    """[end] — encerra o jogo ao fim do texto."""
    ctx.engine.quit()


def parse_hook_line(line: str) -> tuple[str, list[str]]:
    try:
        parts = shlex.split(line)
    except ValueError:
        parts = line.split()
    return (parts[0].lower(), parts[1:]) if parts else ("", [])

@directive("voice", kind="state")
def voice(ctx, value, closing):
    ctx.state.voice = None if closing or not value else     value.strip().lower()

@directive("som_menu")
def _dir_som_menu(ctx, value, closing):
    if closing:
        return
    value = (value or "").strip()
    if not value or value.lower() in ("off", "none", "mudo", "disable"):
        ctx.engine.audio.set_ui_sound("off", None)
        return
    for pair in value.split():
        if "=" in pair:
            k, v = pair.split("=", 1)
            ctx.engine.audio.set_ui_sound(k.strip().lower(), v.strip())
        else:
            # "som_menu: click.wav" sem chave → só troca o "move"
            ctx.engine.audio.set_ui_sound("move", pair)
            
def _coerce(raw: str):
    """Converte 'valor' para o tipo óbvio: bool, None, int, float, string.
    Use aspas para forçar string: [set:senha=\"1234\"]"""
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in ('"', "'"):
        return raw[1:-1]                      # sempre string
    low = raw.lower()
    if low in ("true", "sim", "yes", "on"):
        return True
    if low in ("false", "nao", "não", "no", "off"):
        return False
    if low in ("none", "null", "vazio"):
        return None
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        pass
    return raw


@directive("set")
def set_state(ctx, value, closing):
    """[set:nome_jogador=Demiurgo]              → string
    [set:hp=100]                          → int
    [set:pi=3.14]                         → float
    [set:flag=true]                       → True
    [set:tmp=none]                        → None
    [set:senha=\"1234\"]                    → string forçada
    [set:chars.colosso.nome=Colosso]      → navega dict (cria se faltar)
    [set:party.0.hp=50]                   → navega lista (índice existe)"""
    if closing or not value or "=" not in value:
        return
    path, _, raw = value.partition("=")
    path, raw = path.strip(), raw.strip()
    if not path:
        return

    val = _coerce(raw)
    parts = path.split(".")
    node = ctx.engine.state

    for p in parts[:-1]:
        if isinstance(node, dict):
            node = node.setdefault(p, {})
        elif isinstance(node, list):
            try:
                node = node[int(p)]
            except (ValueError, IndexError):
                ctx.engine.warn(f"[set] índice inválido: {p}")
                return
        else:
            ctx.engine.warn(f"[set] caminho impossível: {path}")
            return

    last = parts[-1]
    if isinstance(node, dict):
        node[last] = val
    elif isinstance(node, list):
        try:
            node[int(last)] = val
        except (ValueError, IndexError):
            ctx.engine.warn(f"[set] índice inválido: {last}")
