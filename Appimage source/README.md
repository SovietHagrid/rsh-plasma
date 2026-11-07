# Installeur République Hagridienne

Assistant d'installation (AppImage) du thème KDE Plasma 6 « République Hagridienne ».

- Installation **complète** ou **personnalisée** (choix des composants, aperçus, tailles)
- À la fin : **appliquer le thème maintenant ou non**, curseur étoile en option
- Écran de connexion SDDM : copié sans être activé ; test et activation séparés
- Désinstallation totale ou partielle

## Utilisation
    chmod +x Installeur-Republique-Hagridienne-*.AppImage && ./Installeur-Republique-Hagridienne-*.AppImage
Si FUSE n'est pas installé : `./…AppImage --appimage-extract-and-run`

Ligne de commande : `… list | status | install [--full | --components icons,colors] [--apply] [--star-cursor] | uninstall [--revert]`

## Reconstruire
    packaging/build.sh /chemin/rsh_plasma_a1_9_tar.gz      # → dist/
Prérequis : curl, tar, binutils, accès à github.com, pypi.org et archive.ubuntu.com.

## Tests
    RSH_PAYLOAD=/chemin/theme_extrait python3 -m unittest tests.test_core -v
    RSH_PAYLOAD=/chemin/theme_extrait QT_QPA_PLATFORM=offscreen python3 tests/gui_drive.py /tmp/captures
