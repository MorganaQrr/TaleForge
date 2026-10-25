"""Interface de linha de comando: run, new, check."""
from __future__ import annotations

import argparse
import logging
import shutil
import sys
from pathlib import Path

from rich.console import Console

from . import __version__

TEMPLATE = Path(__file__).parent / "templates" / "project"


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="taleforge", description="Engine de RPG textual para terminal.")
    p.add_argument("--version", action="version", version=f"TaleForge {__version__}")
    sub = p.add_subparsers(dest="cmd")

    run = sub.add_parser("run", help="executa um projeto")
    run.add_argument("project", nargs="?", default=".", help="pasta do projeto (ou arquivo de config)")
    run.add_argument("--start", help="nota inicial (sobrepõe project.start)")
    run.add_argument("--instant", action="store_true", help="sem efeitos de digitação/pausas")
    run.add_argument("--no-audio", action="store_true", help="desliga o áudio")
    run.add_argument("--watch", action="store_true", help="hot-reload ao editar notas/config")
    run.add_argument("--debug", action="store_true", help="grava taleforge.log no projeto")

    new = sub.add_parser("new", help="cria um projeto novo a partir do modelo")
    new.add_argument("dest", help="pasta a criar")

    chk = sub.add_parser("check", help="valida links, assets, diretivas e hooks")
    chk.add_argument("project", nargs="?", default=".")
    return p


def cmd_run(args) -> int:
    from .config import ConfigError
    from .engine import Engine

    try:
        engine = Engine(args.project, instant=True if args.instant else None,
                        audio=False if args.no_audio else None,
                        hot_reload=True if args.watch else None)
    except ConfigError as exc:
        print(f"Erro de configuração: {exc}", file=sys.stderr)
        return 2
    if args.debug:
        logging.basicConfig(filename=engine.project_dir / "taleforge.log", level=logging.DEBUG,
                            format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    engine.run(args.start)
    return 0


def cmd_new(args) -> int:
    dest = Path(args.dest)
    if dest.exists() and any(dest.iterdir()):
        print(f"'{dest}' já existe e não está vazia.", file=sys.stderr)
        return 1
    shutil.copytree(TEMPLATE, dest, dirs_exist_ok=True)
    (dest / "assets" / "audio").mkdir(parents=True, exist_ok=True)
    print(f"Projeto criado em {dest}/\n  taleforge run {dest}\n  taleforge check {dest}")
    return 0


def cmd_check(args) -> int:
    from .check import check_project
    from .config import ConfigError
    from .engine import Engine

    console = Console()
    try:
        engine = Engine(args.project, audio=False)
    except ConfigError as exc:
        console.print(f"[red]Erro de configuração:[/red] {exc}")
        return 2
    try:
        rep = check_project(engine)
    finally:
        engine.audio.shutdown()
    for e in rep.errors:
        console.print(f"[red]erro[/red]   {e}", highlight=False)
    for w in rep.warnings:
        console.print(f"[yellow]aviso[/yellow]  {w}", highlight=False)
    status = "[green]OK[/green]" if rep.ok else "[red]FALHOU[/red]"
    console.print(f"{status} — {rep.notes} nota(s), {len(rep.errors)} erro(s), {len(rep.warnings)} aviso(s)")
    return 0 if rep.ok else 1


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] not in ("run", "new", "check", "-h", "--help", "--version"):
        argv.insert(0, "run")  # `taleforge meu_rpg` equivale a `taleforge run meu_rpg`
    args = _build_parser().parse_args(argv)
    if args.cmd is None:
        args = _build_parser().parse_args(["run"])
    return {"run": cmd_run, "new": cmd_new, "check": cmd_check}[args.cmd](args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
