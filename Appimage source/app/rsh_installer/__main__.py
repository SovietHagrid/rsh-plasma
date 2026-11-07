"""Point d'entrée : assistant graphique par défaut, ligne de commande sur demande."""
import sys


def main() -> int:
    argv = sys.argv[1:]
    from . import cli
    if argv and (argv[0] in cli.COMMANDS or argv[0] in ("-h", "--help", "--version")):
        return cli.run(argv)
    from . import gui
    if "--selftest" in argv:
        return gui.selftest()
    return gui.main()


if __name__ == "__main__":
    sys.exit(main())
