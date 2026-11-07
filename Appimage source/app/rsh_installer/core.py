"""Cœur de l'installeur : composants, installation, application, désinstallation.

Aucune dépendance à Qt : tout ce module est utilisable en ligne de commande
et testable sans interface graphique.

Les destinations et la logique reprennent celles de ``install.sh`` / ``uninstall.sh``
du thème, de sorte que les deux méthodes d'installation sont interchangeables.
"""
from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

THEME_ID = "com.republiquehagridienne.zephyr"
THEME_NAME = "République Hagridienne"
SDDM_ID = "republique-hagridienne"
BREEZE_DARK_ID = "org.kde.breezedark"
CURSOR_THEME = "EtoileHagridienne"
WALLPAPER_NAME = "RepubliqueHagridienne"
COLOR_SCHEME = "RepubliqueHagridienne"
ICON_THEME = "hagridienne-neon"
PLASMA_STYLE = "republique-hagridienne"

# ----------------------------------------------------------------------------------------
# Chemins
# ----------------------------------------------------------------------------------------


def data_home() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share"))


def config_home() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config"))


def cache_home() -> Path:
    return Path(os.environ.get("XDG_CACHE_HOME") or (Path.home() / ".cache"))


def payload_dir() -> Path:
    """Dossier contenant ``share/`` (le thème), ``apercu/`` et ``LICENSE.md``."""
    env = os.environ.get("RSH_PAYLOAD")
    if env:
        return Path(env)
    return Path(__file__).resolve().parent.parent / "payload"


def sddm_themes_dir() -> Path:
    return Path(os.environ.get("RSH_SDDM_DIR") or "/usr/share/sddm/themes")


def sddm_conf_file() -> Path:
    return Path(os.environ.get("RSH_SDDM_CONF") or "/etc/sddm.conf.d/10-republique-hagridienne.conf")


def log_file() -> Path:
    return cache_home() / "republique-hagridienne-installer" / "installer.log"


# ----------------------------------------------------------------------------------------
# Composants
# ----------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Component:
    id: str
    label: str
    desc: str
    kind: str = "files"            # "files" | "toggle" (réglage du thème global) | "system" (SDDM)
    required: bool = False
    in_custom_default: bool = True  # coché par défaut en mode personnalisé
    # (source relative à payload/share, destination relative au dossier de données XDG)
    items: tuple[tuple[str, str], ...] = ()
    preview: str = ""               # image relative au dossier payload
    note: str = ""                  # mention courte affichée dans la liste


_LF = f"plasma/look-and-feel/{THEME_ID}"

COMPONENTS: tuple[Component, ...] = (
    Component(
        "core", "Thème global « République Hagridienne »",
        "Le thème global apparaît dans Paramètres système → Apparence et style → Thème global. "
        "Il regroupe les réglages par défaut et sert à appliquer les autres composants : il est donc "
        "toujours installé.",
        required=True, items=((_LF, _LF),), preview="apercu/bureau-maquette.jpg", note="requis",
    ),
    Component(
        "splash", "Écran de démarrage animé",
        "L’étoile, le titre et le chargeur pixel de « Bienvenue dans le futur ! ». Les fichiers sont "
        "inclus dans le thème global ; décocher cette case évite seulement de l’activer à l’application.",
        kind="toggle", preview="apercu/demarrage-splash.jpg", note="inclus dans le thème global",
    ),
    Component(
        "colors", "Schéma de couleurs",
        "Palette nuit / cyan / rose. Appliqué avec le style d’applications Breeze, pour lequel les "
        "couleurs ont été conçues.",
        items=(("color-schemes/RepubliqueHagridienne.colors", "color-schemes/RepubliqueHagridienne.colors"),),
        preview="apercu/bureau-maquette.jpg",
    ),
    Component(
        "plasmastyle", "Style Plasma",
        "Panneau, fenêtres contextuelles, info-bulles et widgets (variantes translucide, opaque et solide).",
        items=(("plasma/desktoptheme/republique-hagridienne", "plasma/desktoptheme/republique-hagridienne"),),
        preview="apercu/bureau-maquette.jpg",
    ),
    Component(
        "aurorae", "Décorations de fenêtres",
        "Barre de titre dégradée, trait néon, ombre rose dure et boutons pixel (thème Aurorae).",
        items=(("aurorae/themes/RepubliqueHagridienne", "aurorae/themes/RepubliqueHagridienne"),),
        preview="apercu/fenetres-decoration.jpg",
    ),
    Component(
        "icons", "Pack d’icônes « Hagridienne Néon »",
        "733 icônes et environ 7 400 alias. Les icônes absentes du pack retombent sur Breeze Sombre.",
        items=(("icons/hagridienne-neon", "icons/hagridienne-neon"),),
        preview="apercu/icones-hagridienne-neon.jpg",
    ),
    Component(
        "fonts", "Polices (VT323, Orbitron, Press Start 2P)",
        "Polices libres (licence SIL OFL) utilisées par le thème : VT323 pour l’interface, Orbitron pour "
        "les titres de fenêtres.",
        items=(("fonts/republique-hagridienne", "fonts/republique-hagridienne"),),
        preview="apercu/bureau-maquette.jpg",
    ),
    Component(
        "wallpaper", "Fond d’écran « Nuit hagridienne »",
        "Sept résolutions, dont les formats ultra-larges 21:9.",
        items=(("wallpapers/RepubliqueHagridienne", "wallpapers/RepubliqueHagridienne"),),
        preview="wallpapers/RepubliqueHagridienne/contents/screenshot.png",
    ),
    Component(
        "konsole", "Konsole (couleurs et profil)",
        "Jeu de couleurs et profil « République Hagridienne » pour le terminal Konsole.",
        items=(
            ("konsole/RepubliqueHagridienne.colorscheme", "konsole/RepubliqueHagridienne.colorscheme"),
            ("konsole/RepubliqueHagridienne.profile", "konsole/RepubliqueHagridienne.profile"),
        ),
        preview="apercu/bureau-maquette.jpg",
    ),
    Component(
        "cursor", "Curseur « Étoile Hagridienne »",
        "Le ⭐ du site comme pointeur (le reste vient de Breeze). Facultatif.",
        in_custom_default=False,
        items=(("icons/EtoileHagridienne", "icons/EtoileHagridienne"),),
        preview="apercu/curseurs.png", note="facultatif",
    ),
    Component(
        "sddm", "Écran de connexion SDDM",
        "Installé dans /usr/share/sddm/themes : le mot de passe administrateur sera demandé. Le thème est "
        "copié sans être activé ; vous pourrez le tester puis l’activer à la fin de l’installation.",
        kind="system", in_custom_default=False,
        preview="apercu/connexion-sddm.jpg", note="facultatif · droits administrateur",
    ),
)

BY_ID = {c.id: c for c in COMPONENTS}
ALL_IDS = [c.id for c in COMPONENTS]
CUSTOM_DEFAULT_IDS = [c.id for c in COMPONENTS if c.in_custom_default]
FILE_COMPONENTS = [c for c in COMPONENTS if c.kind == "files"]


def normalize_selection(ids) -> list[str]:
    """Ordre canonique, identifiants inconnus écartés, thème global toujours présent."""
    wanted = set(ids) | {"core"}
    return [c.id for c in COMPONENTS if c.id in wanted]


# ----------------------------------------------------------------------------------------
# Outils : taille, formatage, environnement hôte
# ----------------------------------------------------------------------------------------


def _walk_size(path: Path) -> tuple[int, int]:
    """(octets, nombre de fichiers et liens) sous ``path``, liens non suivis."""
    if path.is_symlink() or path.is_file():
        try:
            return path.lstat().st_size, 1
        except OSError:
            return 0, 1
    total = count = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            count += 1
            try:
                total += os.lstat(os.path.join(root, name)).st_size
            except OSError:
                pass
    return total, count


_size_cache: dict[str, tuple[int, int]] = {}


def component_size(comp: Component) -> tuple[int, int]:
    """(octets, fichiers) d'un composant, d'après le contenu embarqué."""
    if comp.id in _size_cache:
        return _size_cache[comp.id]
    share = payload_dir() / "share"
    total = count = 0
    if comp.kind == "files":
        for src, _dst in comp.items:
            b, n = _walk_size(share / src)
            total += b
            count += n
    elif comp.kind == "system":
        b, n = _walk_size(share / "sddm" / "themes" / SDDM_ID)
        total, count = b, n
    _size_cache[comp.id] = (total, count)
    return total, count


def format_size(n: int) -> str:
    if n < 1024:
        return f"{n} o"
    if n < 1024 ** 2:
        return f"{n / 1024:.0f} Ko"
    return f"{n / 1024 ** 2:.1f} Mo".replace(".", ",")


def host_env() -> dict[str, str]:
    """Environnement à donner aux outils du système (Plasma, fc-cache…).

    Dans un AppImage, l'AppRun peut avoir modifié des variables ; il en sauvegarde alors la valeur
    d'origine dans ``RSH_ORIG_<NOM>`` (``__RSH_UNSET__`` si elle n'existait pas).
    """
    env = dict(os.environ)
    for key in [k for k in env if k.startswith("RSH_ORIG_")]:
        name, val = key[len("RSH_ORIG_"):], env.pop(key)
        if val == "__RSH_UNSET__":
            env.pop(name, None)
        else:
            env[name] = val
    for key in ("APPDIR", "APPIMAGE", "ARGV0", "OWD", "APPIMAGE_COMMAND"):
        env.pop(key, None)
    return env


def which(cmd: str) -> Optional[str]:
    return shutil.which(cmd, path=host_env().get("PATH"))


def run_host(cmd: list[str], timeout: float = 120, stdin=None) -> tuple[int, str]:
    """Exécute une commande du système ; renvoie (code, sortie). 127 si introuvable."""
    exe = which(cmd[0])
    if exe is None:
        return 127, f"{cmd[0]} : commande introuvable"
    try:
        p = subprocess.run(
            [exe, *cmd[1:]], env=host_env(), stdin=stdin, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, timeout=timeout, errors="replace",
        )
        return p.returncode, (p.stdout or "").strip()
    except subprocess.TimeoutExpired:
        return 124, f"{cmd[0]} : délai dépassé ({timeout:.0f} s)"
    except OSError as e:
        return 126, f"{cmd[0]} : {e}"


class Reporter:
    """Reçoit journal et progression ; écrit aussi dans le fichier journal."""

    def __init__(self, log: Optional[Callable[[str, str], None]] = None,
                 progress: Optional[Callable[[float, str], None]] = None):
        self._log, self._progress = log, progress
        self.warnings: list[str] = []
        try:
            log_file().parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass

    def log(self, msg: str, level: str = "info") -> None:
        if level == "warn":
            self.warnings.append(msg)
        try:
            with open(log_file(), "a", encoding="utf-8") as fh:
                fh.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} [{level}] {msg}\n")
        except OSError:
            pass
        if self._log:
            self._log(msg, level)

    def progress(self, frac: float, text: str = "") -> None:
        if self._progress:
            self._progress(max(0.0, min(1.0, frac)), text)


# ----------------------------------------------------------------------------------------
# État du système
# ----------------------------------------------------------------------------------------


def plasma_version() -> Optional[str]:
    rc, out = run_host(["plasmashell", "--version"], timeout=8)
    if rc != 0:
        return None
    m = re.search(r"\d+(?:\.\d+)+", out)
    return m.group(0) if m else None


@dataclass
class Environment:
    plasma: Optional[str]
    can_apply: bool
    has_pkexec: bool
    has_tar: bool
    greeter: Optional[str]

    @property
    def plasma_major(self) -> Optional[int]:
        try:
            return int(self.plasma.split(".")[0]) if self.plasma else None
        except ValueError:
            return None


def inspect_environment() -> Environment:
    return Environment(
        plasma=plasma_version(),
        can_apply=which("plasma-apply-lookandfeel") is not None,
        has_pkexec=which("pkexec") is not None,
        has_tar=which("tar") is not None,
        greeter=which("sddm-greeter-qt6") or which("sddm-greeter"),
    )


def component_paths(comp: Component) -> list[Path]:
    """Chemins installés d'un composant (SDDM : voir ``sddm_paths``)."""
    base = data_home()
    return [base / dst for _src, dst in comp.items]


def sddm_paths() -> list[Path]:
    return [sddm_themes_dir() / SDDM_ID, sddm_conf_file()]


def detect_installed() -> dict[str, bool]:
    """Composants présents sur le disque (compatible avec les installations faites par install.sh)."""
    found: dict[str, bool] = {}
    for c in COMPONENTS:
        if c.kind == "files":
            found[c.id] = any(os.path.lexists(p) for p in component_paths(c))
        elif c.kind == "system":
            found[c.id] = os.path.lexists(sddm_themes_dir() / SDDM_ID)
    return found


def sddm_enabled() -> bool:
    try:
        return SDDM_ID in sddm_conf_file().read_text(encoding="utf-8")
    except OSError:
        return False


def _read_ini_value(path: Path, group: str, key: str) -> Optional[str]:
    try:
        current = None
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if line.startswith("[") and line.endswith("]"):
                current = line[1:-1]
            elif current == group and line.startswith(key + "="):
                return line.split("=", 1)[1]
    except OSError:
        pass
    return None


def applied_markers() -> list[str]:
    """Éléments du thème actuellement actifs dans la session (lecture seule de la configuration)."""
    cfg = config_home()
    marks = []
    if _read_ini_value(cfg / "kdeglobals", "General", "ColorScheme") == COLOR_SCHEME:
        marks.append("schéma de couleurs")
    if _read_ini_value(cfg / "kdeglobals", "Icons", "Theme") == ICON_THEME:
        marks.append("icônes")
    if _read_ini_value(cfg / "plasmarc", "Theme", "name") == PLASMA_STYLE:
        marks.append("style Plasma")
    if _read_ini_value(cfg / "ksplashrc", "KSplash", "Theme") == THEME_ID:
        marks.append("écran de démarrage")
    return marks


# ----------------------------------------------------------------------------------------
# Copie
# ----------------------------------------------------------------------------------------


def _remove(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.exists():
        shutil.rmtree(path)


def copy_tree(src: Path, dst: Path, on_file: Callable[[], None]) -> None:
    """Équivalent de ``cp -a`` : liens symboliques conservés tels quels, modes et dates préservés."""
    dst.mkdir(parents=True, exist_ok=True)
    for entry in os.scandir(src):
        s, d = Path(entry.path), dst / entry.name
        if entry.is_symlink():
            os.symlink(os.readlink(s), d)
            on_file()
        elif entry.is_dir(follow_symlinks=False):
            copy_tree(s, d, on_file)
        else:
            shutil.copy2(s, d)
            on_file()
    shutil.copystat(src, dst, follow_symlinks=False)   # en dernier, comme cp -a


def put(src: Path, dst: Path, on_file: Callable[[], None]) -> None:
    """Copie atomique : on prépare à côté, puis on remplace (jamais d'état à moitié copié)."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(dst.name + ".rsh-tmp")
    _remove(tmp)
    try:
        if src.is_dir() and not src.is_symlink():
            copy_tree(src, tmp, on_file)
        else:
            shutil.copy2(src, tmp)
            on_file()
        _remove(dst)
        os.replace(tmp, dst)
    except BaseException:
        _remove(tmp)
        raise


# ----------------------------------------------------------------------------------------
# Fichier « defaults » du thème global, adapté aux composants installés
# ----------------------------------------------------------------------------------------

# (en-tête, clé) -> composant qui rend la clé pertinente
DEFAULTS_MAP: dict[tuple[str, str], str] = {
    ("[kdeglobals][KDE]", "widgetStyle"): "colors",
    ("[kdeglobals][General]", "ColorScheme"): "colors",
    ("[kdeglobals][General]", "font"): "fonts",
    ("[kdeglobals][General]", "fixed"): "fonts",
    ("[kdeglobals][General]", "smallestReadableFont"): "fonts",
    ("[kdeglobals][General]", "toolBarFont"): "fonts",
    ("[kdeglobals][General]", "menuFont"): "fonts",
    ("[kdeglobals][WM]", "activeFont"): "fonts",
    ("[kdeglobals][Icons]", "Theme"): "icons",
    ("[plasmarc][Theme]", "name"): "plasmastyle",
    ("[Wallpaper]", "Image"): "wallpaper",
    ("[kcminputrc][Mouse]", "cursorTheme"): "cursor",
    ("[kwinrc][org.kde.kdecoration2]", "library"): "aurorae",
    ("[kwinrc][org.kde.kdecoration2]", "theme"): "aurorae",
    ("[kwinrc][org.kde.kdecoration2]", "BorderSize"): "aurorae",
    ("[ksplashrc][KSplash]", "Theme"): "splash",
}


def detect_aurorae() -> str:
    """Même logique que install.sh : plugin Aurorae v2 si présent, sinon v1."""
    dirs: list[str] = []
    rc, out = run_host(["qtpaths6", "--plugin-dir"], timeout=8)
    if rc == 0 and out:
        dirs.append(out.splitlines()[0])
    dirs += ["/usr/lib/qt6/plugins", "/usr/lib64/qt6/plugins",
             "/usr/lib/x86_64-linux-gnu/qt6/plugins", "/usr/lib/aarch64-linux-gnu/qt6/plugins"]
    for lib in ("org.kde.kwin.aurorae.v2", "org.kde.kwin.aurorae"):
        for base in dirs:
            for sub in ("org.kde.kdecoration3", "org.kde.kdecoration2"):
                if os.path.exists(os.path.join(base, sub, lib + ".so")):
                    return lib
    return "org.kde.kwin.aurorae.v2"


def _installed_defaults_path() -> Path:
    return data_home() / _LF / "contents" / "defaults"


def installed_defaults_has_splash() -> bool:
    try:
        return "[ksplashrc][KSplash]" in _installed_defaults_path().read_text(encoding="utf-8")
    except OSError:
        return False


def build_defaults(source_text: str, enabled: set[str], aurorae_lib: str) -> str:
    """Filtre le fichier ``defaults`` d'origine : ne garde que ce qui concerne les composants actifs."""
    out: list[str] = []
    header = None
    block: list[str] = []

    def flush():
        if header is not None and block:
            out.append(header)
            out.extend(block)
            out.append("")

    for raw in source_text.splitlines():
        line = raw.rstrip()
        if line.startswith("["):
            flush()
            header, block = line, []
        elif "=" in line and header is not None:
            key = line.split("=", 1)[0]
            comp = DEFAULTS_MAP.get((header, key))
            if comp is not None and comp not in enabled:
                continue
            if header == "[kwinrc][org.kde.kdecoration2]" and key == "library":
                line = f"library={aurorae_lib}"
            block.append(line)
    flush()
    return "\n".join(out).rstrip() + "\n"


def write_defaults(enabled: set[str], rep: Reporter) -> None:
    src = payload_dir() / "share" / _LF / "contents" / "defaults"
    target = _installed_defaults_path()
    lib = detect_aurorae() if "aurorae" in enabled else "org.kde.kwin.aurorae.v2"
    target.write_text(build_defaults(src.read_text(encoding="utf-8"), enabled, lib), encoding="utf-8")
    if "aurorae" in enabled:
        rep.log(f"Décorations de fenêtres : plugin {lib}")
    names = [BY_ID[i].label for i in ALL_IDS if i in enabled and i != "core"]
    rep.log("Réglages du thème global : " + (", ".join(names) if names else "aucun composant optionnel"))


# ----------------------------------------------------------------------------------------
# SDDM (droits administrateur via pkexec)
# ----------------------------------------------------------------------------------------


def _pkexec_sh(script: str, stdin=None, timeout: float = 300) -> tuple[int, str]:
    """Lance ``sh -c script`` en root. 126/127 : authentification annulée ou refusée."""
    if which("pkexec") is None:
        return 127, "pkexec est introuvable"
    return run_host(["pkexec", "/bin/sh", "-c", script], stdin=stdin, timeout=timeout)


def manual_sddm_command() -> str:
    d = sddm_themes_dir()
    return (f"sudo cp -a <dossier-du-thème>/share/sddm/themes/{SDDM_ID} {d}/")


def sddm_install(rep: Reporter) -> bool:
    """Copie le thème SDDM sans l'activer.

    Les fichiers sont envoyés à root par un flux tar (entrée standard) : le point de montage
    d'un AppImage (FUSE) n'est pas lisible par root, et on évite ainsi tout fichier temporaire.
    """
    src = payload_dir() / "share" / "sddm" / "themes" / SDDM_ID
    if not src.is_dir():
        rep.log("Thème SDDM introuvable dans l’installeur.", "warn")
        return False
    if which("pkexec") is None or which("tar") is None:
        rep.log("pkexec ou tar est introuvable : l’écran de connexion n’a pas été installé. "
                f"Commande manuelle : {manual_sddm_command()}", "warn")
        return False
    dest = sddm_themes_dir()
    q = shlex.quote
    script = (f"set -e; mkdir -p {q(str(dest))}; rm -rf {q(str(dest / SDDM_ID))}; "
              f"tar -C {q(str(dest))} -xf - --no-same-owner; "
              f"chmod -R u=rwX,go=rX {q(str(dest / SDDM_ID))}")
    rep.log("Écran de connexion SDDM : en attente de l’autorisation administrateur…")
    tar = subprocess.Popen([which("tar"), "-C", str(src.parent), "-cf", "-", SDDM_ID],
                           stdout=subprocess.PIPE, env=host_env())
    try:
        rc, out = _pkexec_sh(script, stdin=tar.stdout)
    finally:
        if tar.stdout:
            tar.stdout.close()
        tar.wait()
    if rc == 0:
        rep.log(f"Écran de connexion SDDM copié dans {dest / SDDM_ID} (non activé).")
        return True
    if rc in (126, 127):
        rep.log("Autorisation administrateur refusée ou annulée : l’écran de connexion n’a pas été installé.", "warn")
    else:
        rep.log(f"Échec de l’installation de l’écran de connexion (code {rc}) : {out}", "warn")
    return False


def sddm_enable(rep: Reporter) -> bool:
    q = shlex.quote
    conf = sddm_conf_file()
    script = (f"set -e; mkdir -p {q(str(conf.parent))}; "
              f"printf '[Theme]\\nCurrent={SDDM_ID}\\n' > {q(str(conf))}; chmod 644 {q(str(conf))}")
    rc, out = _pkexec_sh(script)
    if rc == 0:
        rep.log("Écran de connexion SDDM activé.")
        rep.log(f"En cas d’écran noir au démarrage : Ctrl+Alt+F3, connexion, puis « sudo rm {conf} ».")
        return True
    rep.log("Activation de l’écran de connexion impossible ou annulée" + (f" : {out}" if out else "."), "warn")
    return False


def sddm_remove(rep: Reporter) -> bool:
    q = shlex.quote
    script = f"rm -f {q(str(sddm_conf_file()))}; rm -rf {q(str(sddm_themes_dir() / SDDM_ID))}"
    rc, out = _pkexec_sh(script)
    if rc == 0:
        rep.log("Écran de connexion SDDM retiré.")
        return True
    rep.log("Retrait de l’écran de connexion impossible ou annulé" + (f" : {out}" if out else "."), "warn")
    return False


def sddm_test_command() -> Optional[list[str]]:
    greeter = which("sddm-greeter-qt6") or which("sddm-greeter")
    theme = sddm_themes_dir() / SDDM_ID
    if greeter and theme.is_dir():
        return [greeter, "--test-mode", "--theme", str(theme)]
    return None


def sddm_test() -> bool:
    cmd = sddm_test_command()
    if not cmd:
        return False
    try:
        subprocess.Popen(cmd, env=host_env(), stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        return True
    except OSError:
        return False


# ----------------------------------------------------------------------------------------
# Installation
# ----------------------------------------------------------------------------------------


@dataclass
class InstallResult:
    ok: bool = True
    installed: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    sddm_installed: bool = False
    error: str = ""


def _refresh_caches(selected: set[str], rep: Reporter) -> None:
    data = data_home()
    if "icons" in selected and which("gtk-update-icon-cache"):
        run_host(["gtk-update-icon-cache", "-q", "-t", "-f", str(data / "icons" / ICON_THEME)], timeout=60)
    if "fonts" in selected and which("fc-cache"):
        run_host(["fc-cache", "-f", str(data / "fonts")], timeout=120)
        if which("fc-list"):
            _rc, seen = run_host(["fc-list"], timeout=60)
            for fam in ("VT323", "Orbitron", "Press Start 2P"):
                if fam.lower() in seen.lower():
                    rep.log(f"   ✓ police {fam} détectée")
                else:
                    rep.log(f"Police « {fam} » non détectée par fontconfig (une reconnexion peut être nécessaire).", "warn")
    if which("kbuildsycoca6"):
        run_host(["kbuildsycoca6"], timeout=60)


def install(selection, rep: Reporter) -> InstallResult:
    sel = normalize_selection(selection)
    chosen = set(sel)
    res = InstallResult()
    share = payload_dir() / "share"
    data = data_home()
    if not share.is_dir():
        res.ok, res.error = False, "Les fichiers du thème sont introuvables dans l’installeur."
        rep.log(res.error, "error")
        return res

    prev_splash = installed_defaults_has_splash()   # à lire avant que le thème global soit remplacé
    files = [BY_ID[i] for i in sel if BY_ID[i].kind == "files"]
    total = sum(component_size(c)[1] for c in files) + 60 + (200 if "sddm" in chosen else 0)
    done = 0

    def tick():
        nonlocal done
        done += 1
        if done % 25 == 0:
            rep.progress(done / total)

    rep.log(f"Installation dans {data}")
    try:
        for c in files:
            rep.progress(done / total, f"Copie : {c.label}")
            rep.log(f"▸ {c.label}")
            for src, dst in c.items:
                put(share / src, data / dst, tick)
            res.installed.append(c.id)
        done += 10
        rep.progress(done / total, "Réglages du thème global")

        enabled = {c.id for c in FILE_COMPONENTS if any(os.path.lexists(p) for p in component_paths(c))}
        enabled.add("core")
        if "splash" in chosen or prev_splash:
            enabled.add("splash")
        if "splash" in chosen:
            res.installed.append("splash")
        write_defaults(enabled, rep)

        done += 20
        rep.progress(done / total, "Mise à jour des caches")
        _refresh_caches(chosen, rep)
        done += 30

        if "sddm" in chosen:
            rep.progress(done / total, "Écran de connexion SDDM (administrateur)")
            res.sddm_installed = sddm_install(rep)
            if res.sddm_installed:
                res.installed.append("sddm")
        rep.progress(1.0, "Terminé")
    except Exception as exc:  # noqa: BLE001 — on remonte tout au journal
        res.ok, res.error = False, f"{type(exc).__name__} : {exc}"
        rep.log(f"Échec de l’installation : {res.error}", "error")
    res.warnings = list(rep.warnings)
    return res


# ----------------------------------------------------------------------------------------
# Application
# ----------------------------------------------------------------------------------------


@dataclass
class ApplyResult:
    ok: bool = True
    applied: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error: str = ""


def applicable_components() -> list[str]:
    """Composants appliqués avec le thème global : ceux qui sont installés (le fichier defaults les reflète).

    Le curseur étoile n'en fait pas partie : il est appliqué séparément, sur demande.
    """
    inst = detect_installed()
    ids = [c.id for c in FILE_COMPONENTS if inst.get(c.id) and c.id not in ("konsole", "core", "cursor")]
    if installed_defaults_has_splash():
        ids.insert(0, "splash")
    return [i for i in ALL_IDS if i in ids]


def _reconfigure_kwin() -> None:
    for q in ("qdbus6", "qdbus-qt6", "qdbus"):
        if which(q):
            run_host([q, "org.kde.KWin", "/KWin", "reconfigure"], timeout=15)
            return
    if which("dbus-send"):
        run_host(["dbus-send", "--session", "--type=method_call", "--dest=org.kde.KWin", "/KWin",
                  "org.kde.KWin.reconfigure"], timeout=15)


def apply_theme(use_cursor: bool, rep: Reporter) -> ApplyResult:
    res = ApplyResult()
    inst = detect_installed()
    if not inst.get("core"):
        res.ok, res.error = False, "Le thème global n’est pas installé."
        rep.log(res.error, "error")
        return res
    if which("plasma-apply-lookandfeel") is None:
        res.ok = False
        res.error = ("plasma-apply-lookandfeel est introuvable. Appliquez le thème depuis Paramètres système → "
                     "Apparence et style → Thème global → « République Hagridienne ».")
        rep.log(res.error, "error")
        return res

    res.applied = applicable_components()
    rep.progress(0.1, "Application du thème global")
    rep.log("▸ Application du thème global : " +
            (", ".join(BY_ID[i].label for i in res.applied) if res.applied else "aucun composant optionnel"))
    rc, out = run_host(["plasma-apply-lookandfeel", "-a", THEME_ID], timeout=180)
    if out:
        rep.log(out)
    if rc != 0:
        res.ok, res.error = False, f"plasma-apply-lookandfeel a échoué (code {rc})."
        rep.log(res.error, "error")
        return res

    if inst.get("wallpaper") and which("plasma-apply-wallpaperimage"):
        rep.progress(0.5, "Fond d’écran")
        rc, out = run_host(["plasma-apply-wallpaperimage", str(data_home() / "wallpapers" / WALLPAPER_NAME)], timeout=60)
        if rc != 0:
            rep.log(f"Le fond d’écran n’a pas pu être appliqué : {out}", "warn")
    if inst.get("cursor") and use_cursor:
        rep.progress(0.7, "Curseur étoile")
        if which("plasma-apply-cursortheme"):
            rc, out = run_host(["plasma-apply-cursortheme", CURSOR_THEME], timeout=60)
            if rc != 0:
                rep.log(f"Le curseur n’a pas pu être appliqué : {out}", "warn")
            else:
                res.applied.append("cursor")
        else:
            rep.log("plasma-apply-cursortheme est introuvable : choisissez « Étoile Hagridienne » dans "
                    "Paramètres système → Curseurs.", "warn")
    rep.progress(0.9, "Rechargement de KWin")
    _reconfigure_kwin()
    rep.progress(1.0, "Terminé")
    rep.log("Thème appliqué. Reconnectez-vous pour que polices, curseur et écran de démarrage soient pris en compte partout.")
    res.warnings = list(rep.warnings)
    return res


# ----------------------------------------------------------------------------------------
# Désinstallation
# ----------------------------------------------------------------------------------------


@dataclass
class UninstallResult:
    ok: bool = True
    removed: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error: str = ""


def uninstall(selection, revert: bool, rep: Reporter) -> UninstallResult:
    res = UninstallResult()
    chosen = set(selection)
    data = data_home().resolve()
    try:
        if revert:
            if which("plasma-apply-lookandfeel"):
                rep.log("▸ Retour au thème Breeze Sombre")
                rc, out = run_host(["plasma-apply-lookandfeel", "-a", BREEZE_DARK_ID], timeout=180)
                if rc != 0:
                    rep.log(f"Retour à Breeze Sombre impossible : {out}", "warn")
            else:
                rep.log("plasma-apply-lookandfeel est introuvable : le retour à Breeze Sombre est à faire à la main.", "warn")

        todo = [BY_ID[i] for i in ALL_IDS if i in chosen and i in BY_ID and BY_ID[i].kind == "files"]
        for k, c in enumerate(todo):
            rep.progress(k / (len(todo) + 2), f"Suppression : {c.label}")
            rep.log(f"▸ {c.label}")
            for p in component_paths(c):
                # Garde-fou : on ne supprime que sous le dossier de données de l'utilisateur.
                if not str(p.parent.resolve()).startswith(str(data)):
                    raise RuntimeError(f"chemin hors du dossier de données : {p}")
                _remove(p)
            res.removed.append(c.id)

        if "sddm" in chosen:
            rep.progress(0.8, "Écran de connexion SDDM (administrateur)")
            if sddm_remove(rep):
                res.removed.append("sddm")

        # Le fichier defaults du thème global suit les composants qui restent.
        if detect_installed().get("core"):
            keep = {c.id for c in FILE_COMPONENTS if any(os.path.lexists(p) for p in component_paths(c))}
            if installed_defaults_has_splash():
                keep.add("splash")
            write_defaults(keep, rep)

        if "fonts" in res.removed and which("fc-cache"):
            run_host(["fc-cache", "-f", str(data_home() / "fonts")], timeout=120)
        if which("kbuildsycoca6"):
            run_host(["kbuildsycoca6"], timeout=60)
        rep.progress(1.0, "Terminé")
    except Exception as exc:  # noqa: BLE001
        res.ok, res.error = False, f"{type(exc).__name__} : {exc}"
        rep.log(f"Échec de la désinstallation : {res.error}", "error")
    res.warnings = list(rep.warnings)
    return res
