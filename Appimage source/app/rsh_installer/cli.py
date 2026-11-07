"""Mode ligne de commande : mêmes opérations que l'assistant graphique."""
from __future__ import annotations

import argparse
import sys

from . import core
from .version import INSTALLER_VERSION, THEME_RELEASE

COMMANDS = {"install", "uninstall", "status", "list"}


def _reporter() -> core.Reporter:
    marks = {"info": "▸", "warn": "!", "error": "✗"}

    def log(msg: str, level: str = "info") -> None:
        stream = sys.stderr if level != "info" else sys.stdout
        print(f"{marks.get(level, '▸') if not msg.startswith(('▸', '   ')) else ''} {msg}".strip(), file=stream)

    return core.Reporter(log=log)


def _parse_components(value: str) -> list[str]:
    ids = [v.strip() for v in value.split(",") if v.strip()]
    unknown = [i for i in ids if i not in core.BY_ID]
    if unknown:
        raise SystemExit(f"Composant(s) inconnu(s) : {', '.join(unknown)}  (voir : list)")
    return ids


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="installeur-republique-hagridienne",
        description=f"Installeur du thème KDE Plasma « {core.THEME_NAME} » ({THEME_RELEASE}). "
                    "Sans commande, l’assistant graphique est lancé.",
    )
    p.add_argument("--version", action="version", version=f"installeur {INSTALLER_VERSION} (thème {THEME_RELEASE})")
    sub = p.add_subparsers(dest="command")

    sub.add_parser("list", help="liste les composants")
    sub.add_parser("status", help="affiche ce qui est installé et l’état du système")

    i = sub.add_parser("install", help="installe le thème")
    g = i.add_mutually_exclusive_group()
    g.add_argument("--full", action="store_true", help="installation complète (par défaut)")
    g.add_argument("--components", metavar="a,b,c", help="installation personnalisée (voir : list)")
    i.add_argument("--apply", action="store_true", help="applique le thème à la fin")
    i.add_argument("--star-cursor", action="store_true", help="avec --apply : active le curseur étoile")
    i.add_argument("--sddm-enable", action="store_true", help="active l’écran de connexion SDDM (après l’avoir installé)")

    u = sub.add_parser("uninstall", help="désinstalle")
    g2 = u.add_mutually_exclusive_group()
    g2.add_argument("--all", action="store_true", help="tout désinstaller, sauf les polices (par défaut)")
    g2.add_argument("--components", metavar="a,b,c", help="composants à retirer")
    u.add_argument("--revert", action="store_true", help="revient d’abord à Breeze Sombre")
    return p


def cmd_list() -> int:
    print(f"{'identifiant':<13} {'taille':>8}  composant")
    for c in core.COMPONENTS:
        size = core.component_size(c)[0]
        flag = " (requis)" if c.required else ""
        print(f"{c.id:<13} {core.format_size(size) if size else '—':>8}  {c.label}{flag}")
    return 0


def cmd_status() -> int:
    env = core.inspect_environment()
    print(f"Plasma : {env.plasma or 'non détecté'}")
    print(f"plasma-apply-lookandfeel : {'oui' if env.can_apply else 'non'}   pkexec : {'oui' if env.has_pkexec else 'non'}")
    inst = core.detect_installed()
    for c in core.COMPONENTS:
        if c.kind == "toggle":
            continue
        print(f"  [{'x' if inst.get(c.id) else ' '}] {c.id:<12} {c.label}")
    if inst.get("sddm"):
        print(f"      écran de connexion activé : {'oui' if core.sddm_enabled() else 'non'}")
    marks = core.applied_markers()
    print("Actuellement appliqué : " + (", ".join(marks) if marks else "rien"))
    return 0


def cmd_install(args) -> int:
    ids = core.ALL_IDS if (args.full or not args.components) else _parse_components(args.components)
    ids = core.normalize_selection(ids)
    rep = _reporter()
    res = core.install(ids, rep)
    if not res.ok:
        return 1
    print(f"Installé : {', '.join(res.installed)}")
    if args.sddm_enable:
        if res.sddm_installed or core.detect_installed().get("sddm"):
            core.sddm_enable(rep)
        else:
            print("! --sddm-enable ignoré : l’écran de connexion n’est pas installé.", file=sys.stderr)
    if args.apply:
        ap = core.apply_theme(args.star_cursor, rep)
        if not ap.ok:
            return 2
    else:
        print("Thème non appliqué. Pour l’appliquer : Paramètres système → Apparence et style → Thème global "
              f"→ « {core.THEME_NAME} » (ou relancez avec --apply).")
    return 0


def cmd_uninstall(args) -> int:
    if args.components:
        ids = _parse_components(args.components)
    else:
        ids = [i for i, there in core.detect_installed().items() if there and i != "fonts"]
    rep = _reporter()
    res = core.uninstall(ids, args.revert, rep)
    if not res.ok:
        return 1
    print(f"Retiré : {', '.join(res.removed) or 'rien'}")
    return 0


def run(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "list":
        return cmd_list()
    if args.command == "status":
        return cmd_status()
    if args.command == "install":
        return cmd_install(args)
    if args.command == "uninstall":
        return cmd_uninstall(args)
    return 0
