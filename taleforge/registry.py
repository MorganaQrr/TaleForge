"""Registro de diretivas de marcação e hooks (pontos de extensão da engine).

Plugins e hooks de projeto usam os decoradores `@directive` e `@hook`.
Durante o carregamento de um módulo por uma Engine, os decoradores
registram *nessa* engine; fora disso, registram nos padrões globais.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Callable, Iterator

# handler(ctx, value, closing) -> None
DirectiveFn = Callable[..., None]


@dataclass
class DirectiveSpec:
    name: str
    fn: DirectiveFn
    kind: str = "event"  # "state" (persiste até [/nome]) ou "event" (acontece uma vez)
    doc: str = ""


_DEFAULT_DIRECTIVES: dict[str, DirectiveSpec] = {}
_DEFAULT_HOOKS: dict[str, Callable] = {}
_active: list[tuple[dict, dict]] = []


@contextmanager
def collecting(specs: dict, hooks: dict) -> Iterator[None]:
    _active.append((specs, hooks))
    try:
        yield
    finally:
        _active.pop()


def directive(name: str | None = None, kind: str = "event") -> Callable[[DirectiveFn], DirectiveFn]:
    """Registra uma diretiva `[nome:valor]`. O handler recebe (ctx, value, closing)."""

    def deco(fn: DirectiveFn) -> DirectiveFn:
        target = _active[-1][0] if _active else _DEFAULT_DIRECTIVES
        key = (name or fn.__name__).lower()
        target[key] = DirectiveSpec(key, fn, kind, (fn.__doc__ or "").strip())
        return fn

    return deco


def hook(name: str | None = None) -> Callable[[Callable], Callable]:
    """Registra um hook chamável por `[[!nome arg|Rótulo]]` ou `[hook:nome arg]`.

    O hook recebe `(engine, *args)`. Se devolver uma string, a engine navega
    para a nota com esse nome; se devolver None, o menu continua na tela.
    """

    def deco(fn: Callable) -> Callable:
        target = _active[-1][1] if _active else _DEFAULT_HOOKS
        target[(name or fn.__name__).lower()] = fn
        return fn

    return deco


class Registry:
    """Conjunto de diretivas disponíveis em uma engine (já com aliases/desativadas)."""

    def __init__(self, aliases: dict[str, str] | None = None, disabled=()):
        self.disabled = {d.lower() for d in disabled}
        self.specs: dict[str, DirectiveSpec] = {
            k: v for k, v in _DEFAULT_DIRECTIVES.items() if k not in self.disabled
        }
        self.aliases = {a.lower(): c.lower() for a, c in (aliases or {}).items()}

    def resolve(self, name: str) -> DirectiveSpec | None:
        n = name.lower()
        n = self.aliases.get(n, n)
        return self.specs.get(n)

    def knows(self, name: str) -> bool:
        return self.resolve(name) is not None
