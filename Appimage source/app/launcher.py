"""Lanceur utilisé par l'AppRun : le dossier de ce fichier est ajouté à sys.path."""
import sys

from rsh_installer.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
