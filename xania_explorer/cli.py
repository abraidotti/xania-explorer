"""Command line: ``python -m xania_explorer [--xania PATH] <command>``."""

from __future__ import annotations

import argparse
import importlib
import os
import subprocess
import sys
from pathlib import Path

from .areafile.world import load_world
from .paths import REPO_ROOT, XaniaPaths, default_xania_dir
from .systems import SYSTEMS

ASSESSMENTS = tuple(s.slug for s in SYSTEMS)
BUILD_DIR = REPO_ROOT / "build"


def _world(args: argparse.Namespace):
    return load_world(XaniaPaths.resolve(args.xania))


def cmd_check(args: argparse.Namespace) -> int:
    world = _world(args)
    print(f"{world.xania.root}: {len(world.areas)} areas, {len(world.rooms)} rooms, {len(world.mobs)} mobs, "
          f"{len(world.objects)} objects")
    for name in world.unlisted_files:
        print(f"[unlisted] {name}")
    for d in world.diagnostics:
        print(f"[warning] {d}")
    for p in world.problems:
        print(p)
    return 1 if any(p.fatal_in_cpp for p in world.problems) else 0


def cmd_docs(args: argparse.Namespace) -> int:
    from .gen.area_catalogue import write_catalogue

    written = write_catalogue(_world(args), args.out)
    print(f"wrote {len(written)} files to {args.out}")
    return 0


def cmd_assess(args: argparse.Namespace) -> int:
    unknown = set(args.only) - set(ASSESSMENTS)
    if unknown:
        print(f"unknown assessment(s): {', '.join(sorted(unknown))}; choose from {', '.join(ASSESSMENTS)}")
        return 2
    world = _world(args)
    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)
    from .systems import by_slug

    for name in args.only or ASSESSMENTS:
        story = by_slug(name).story(world)
        if story.status != "ok":
            print(f"skipped {name}: {story.note}")
            continue
        mod = importlib.import_module(f".assess.{name}", __package__)
        (out / f"{name}.md").write_text(mod.render(world), encoding="utf-8", newline="\n")
        mod.write_csv(world, out / "data" / f"{name}.csv")
        print(f"wrote {out / (name + '.md')} and data/{name}.csv")
    return 0


def _targets_env(args: argparse.Namespace) -> dict[str, str]:
    """Translate --target NAME=PATH (repeatable) or --xania into the XANIA_TARGETS env var
    read by the MkDocs hook (xania_explorer/site/hooks.py)."""
    from .site.targets import format_targets, parse_target

    specs = [parse_target(t) for t in args.target] if args.target else \
        [parse_target(str(Path(args.xania or default_xania_dir())))]
    env = dict(os.environ)
    env["XANIA_TARGETS"] = format_targets(specs)
    return env


def _mkdocs(args: argparse.Namespace, *mkdocs_args: str) -> int:
    try:
        import mkdocs  # noqa: F401
    except ImportError:
        print("MkDocs isn't installed. Run: python -m pip install -e .[site]")
        return 2
    cmd = [sys.executable, "-m", "mkdocs", *mkdocs_args, "-f", str(REPO_ROOT / "mkdocs.yml")]
    return subprocess.call(cmd, env=_targets_env(args), cwd=REPO_ROOT)


def _refresh_runtime() -> None:
    """If the explorer runtime is bundled, rebuild its xania_explorer wheel so it matches the code being built."""
    from .site.bundle import RUNTIME_DIR, build_wheels

    if (RUNTIME_DIR / "wheels" / "index.json").exists():
        build_wheels(RUNTIME_DIR / "wheels", own_only=True)


def cmd_site(args: argparse.Namespace) -> int:
    _refresh_runtime()
    extra = ["--strict"] if args.strict else []
    return _mkdocs(args, "build", "--site-dir", str(args.out), *extra)


def cmd_serve(args: argparse.Namespace) -> int:
    _refresh_runtime()
    return _mkdocs(args, "serve", "--dev-addr", args.addr)


def cmd_bundle(args: argparse.Namespace) -> int:
    from .site.bundle import bundle

    info = bundle(args.out, args.pyodide, skip_pyodide=args.keep_pyodide)
    print(f"wrote the explorer runtime to {info['dir']} ({info['mb']} MB): Pyodide {info['pyodide']}, "
          f"wheels {', '.join(info['wheels'])}")
    return 0


def cmd_custom_build(args: argparse.Namespace) -> int:
    from .site.builds import custom_build

    dest = custom_build(args.checkouts, args.out, site_url=args.site_url, run_url=args.run_url, keep=args.keep)
    print(f"built {dest}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="xania_explorer", description="Xania Explorer: balance reports and data checks for the Xania MUD.")
    parser.add_argument("--xania", type=Path, default=None, metavar="PATH",
                        help="Xania checkout (or its area/ dir). Default: $XANIA_DIR or ../xania "
                             f"(currently {default_xania_dir()})")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("check", help="load the world and print loader warnings/problems")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("docs", help="write the area catalogue as Markdown")
    p.add_argument("--out", type=Path, default=BUILD_DIR / "reference")
    p.set_defaults(func=cmd_docs)

    p = sub.add_parser("assess", help="write level-progression assessments as Markdown + CSV")
    p.add_argument("--out", type=Path, default=BUILD_DIR / "assessments")
    p.add_argument("only", nargs="*", metavar="NAME",
                   help=f"assessments to run (default: all of {', '.join(ASSESSMENTS)})")
    p.set_defaults(func=cmd_assess)

    target_help = ("NAME=PATH of a Xania checkout to include; repeat to compare versions, "
                   "e.g. --target upstream=../xania-upstream --target fork=../xania")
    p = sub.add_parser("site", help="build the static website (MkDocs) into --out")
    p.add_argument("--target", action="append", default=[], help=target_help)
    p.add_argument("--out", type=Path, default=REPO_ROOT / "site")
    p.add_argument("--strict", action="store_true", help="fail on MkDocs warnings (used in CI)")
    p.set_defaults(func=cmd_site)

    p = sub.add_parser("serve", help="build the website and serve it locally with live reload")
    p.add_argument("--target", action="append", default=[], help=target_help)
    p.add_argument("--addr", default="127.0.0.1:8000")
    p.set_defaults(func=cmd_serve)

    from .site.bundle import RUNTIME_DIR

    p = sub.add_parser("bundle", help="write the in-browser explorer's runtime (Pyodide + wheels) into docs/runtime")
    p.add_argument("--out", type=Path, default=RUNTIME_DIR)
    p.add_argument("--pyodide", type=Path, default=None, metavar="DIR",
                   help="copy Pyodide from a local pyodide package dir instead of downloading it")
    p.add_argument("--keep-pyodide", action="store_true", help="reuse an already-downloaded Pyodide; rebuild wheels only")
    p.set_defaults(func=cmd_bundle)

    from .site.builds import KEEP

    p = sub.add_parser("custom-build", help="build one version, or a comparison of two, into OUT/<slug>/ "
                                            "(the Site workflow's 'Build this on GitHub' fallback)")
    p.add_argument("checkouts", nargs="+", type=Path, metavar="CHECKOUT", help="base checkout, then optional head")
    p.add_argument("--out", type=Path, required=True, help="builds folder (the builds branch)")
    p.add_argument("--site-url", default="", help="the main site's URL; the build lives at <url>/builds/<slug>/")
    p.add_argument("--run-url", default="", help="link to the workflow run, recorded in build.json")
    p.add_argument("--keep", type=int, default=KEEP, help=f"how many builds to keep (default {KEEP})")
    p.set_defaults(func=cmd_custom_build)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except FileNotFoundError as e:
        print(e)
        return 2
