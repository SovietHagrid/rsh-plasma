"""Tests du cœur, dans un HOME temporaire avec de fausses commandes Plasma.

    RSH_PAYLOAD=/chemin/du/theme python3 -m unittest tests.test_core -v
"""
import os
import shutil
import stat
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
from rsh_installer import core  # noqa: E402

FAKE_TOOLS = {
    "plasmashell": 'echo "plasmashell 6.5.2"',
    "plasma-apply-lookandfeel": 'echo "plasma-apply-lookandfeel $*" >> "$FAKE_LOG"; echo "Thème appliqué"',
    "plasma-apply-wallpaperimage": 'echo "plasma-apply-wallpaperimage $*" >> "$FAKE_LOG"',
    "plasma-apply-cursortheme": 'echo "plasma-apply-cursortheme $*" >> "$FAKE_LOG"',
    "qdbus6": 'echo "qdbus6 $*" >> "$FAKE_LOG"',
    "kbuildsycoca6": 'echo "kbuildsycoca6" >> "$FAKE_LOG"',
    "fc-cache": 'echo "fc-cache $*" >> "$FAKE_LOG"',
    "fc-list": 'echo "VT323 Orbitron Press Start 2P"',
    "pkexec": 'echo "pkexec" >> "$FAKE_LOG"; exec "$@"',
}


class Base(unittest.TestCase):
    aurorae_plugin = "org.kde.kdecoration3/org.kde.kwin.aurorae.v2.so"

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="rsh-test-"))
        self.home = self.tmp / "home"
        self.bin = self.tmp / "bin"
        self.sddm = self.tmp / "sddm-themes"
        self.conf = self.tmp / "sddm.conf.d" / "10-republique-hagridienne.conf"
        self.plugins = self.tmp / "qtplugins"
        self.log = self.tmp / "calls.log"
        for d in (self.home, self.bin):
            d.mkdir(parents=True)
        for name, body in FAKE_TOOLS.items():
            f = self.bin / name
            f.write_text(f"#!/bin/sh\n{body}\n")
            f.chmod(f.stat().st_mode | stat.S_IEXEC)
        q = self.bin / "qtpaths6"
        q.write_text(f'#!/bin/sh\necho "{self.plugins}"\n')
        q.chmod(0o755)
        plug = self.plugins / self.aurorae_plugin
        plug.parent.mkdir(parents=True)
        plug.write_text("")
        self._env = dict(os.environ)
        os.environ.update(
            HOME=str(self.home), XDG_DATA_HOME=str(self.home / "share"), XDG_CONFIG_HOME=str(self.home / "cfg"),
            XDG_CACHE_HOME=str(self.home / "cache"), PATH=f"{self.bin}:/usr/bin:/bin", FAKE_LOG=str(self.log),
            RSH_SDDM_DIR=str(self.sddm), RSH_SDDM_CONF=str(self.conf),
        )
        core._size_cache.clear()
        self.data = core.data_home()
        self.rep = core.Reporter()

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def calls(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def defaults(self):
        return (self.data / core._LF / "contents" / "defaults").read_text(encoding="utf-8")


class TestFullInstall(Base):
    def test_full_install_copies_everything_like_cp_a(self):
        res = core.install(core.ALL_IDS, self.rep)
        self.assertTrue(res.ok, res.error)
        share = core.payload_dir() / "share"
        for c in core.FILE_COMPONENTS:
            for src, dst in c.items:
                s, d = share / src, self.data / dst
                self.assertTrue(os.path.lexists(d), f"manquant : {dst}")
                if s.is_dir():
                    n_src = sum(len(f) for _r, _d, f in os.walk(s))
                    # gtk-update-icon-cache (s'il existe) ajoute légitimement icon-theme.cache
                    n_dst = sum(len([x for x in f if x != "icon-theme.cache"]) for _r, _d, f in os.walk(d))
                    self.assertEqual(n_src, n_dst, f"nombre de fichiers différent pour {dst}")
        # liens symboliques conservés (alias d'icônes) et relatifs
        links = [p for p in (self.data / "icons/hagridienne-neon").rglob("*") if p.is_symlink()]
        self.assertGreater(len(links), 7000)
        self.assertFalse(os.path.isabs(os.readlink(links[0])))
        self.assertFalse(any(self.data.rglob("*.rsh-tmp")))

    def test_full_defaults_equal_original_except_aurorae_library(self):
        core.install(core.ALL_IDS, self.rep)
        orig = (core.payload_dir() / "share" / core._LF / "contents" / "defaults").read_text(encoding="utf-8")
        got = self.defaults()
        norm = lambda t: [l for l in t.splitlines() if l.strip()]
        self.assertEqual(norm(orig), norm(got))  # plugin v2 présent -> identique

    def test_sddm_copied_not_enabled_and_owned_sanely(self):
        res = core.install(core.ALL_IDS, self.rep)
        self.assertTrue(res.sddm_installed)
        self.assertTrue((self.sddm / core.SDDM_ID / "Main.qml").is_file())
        self.assertTrue((self.sddm / core.SDDM_ID / "fonts" / "Orbitron-VF.ttf").is_file())
        self.assertFalse(self.conf.exists(), "SDDM ne doit pas être activé à l'installation")
        mode = (self.sddm / core.SDDM_ID).stat().st_mode & 0o777
        self.assertEqual(mode & 0o022, 0, "pas d'écriture pour groupe/autres")

    def test_reinstall_is_idempotent(self):
        core.install(core.ALL_IDS, self.rep)
        res = core.install(core.ALL_IDS, self.rep)
        self.assertTrue(res.ok)
        self.assertFalse(any(self.data.rglob("*.rsh-tmp")))


class TestCustomInstall(Base):
    def test_core_always_installed_and_defaults_trimmed(self):
        res = core.install(["icons", "colors"], self.rep)
        self.assertTrue(res.ok, res.error)
        self.assertTrue(core.detect_installed()["core"])
        d = self.defaults()
        self.assertIn("ColorScheme=RepubliqueHagridienne", d)
        self.assertIn("widgetStyle=Breeze", d)
        self.assertIn("Theme=hagridienne-neon", d)
        for absent in ("font=", "activeFont", "plasmarc", "Wallpaper", "kcminputrc", "kdecoration2", "ksplashrc"):
            self.assertNotIn(absent, d, f"{absent} ne devrait pas être présent")
        self.assertFalse((self.data / "fonts").exists())
        self.assertFalse((self.data / "wallpapers").exists())

    def test_splash_toggle(self):
        core.install(["splash"], self.rep)
        self.assertIn("[ksplashrc][KSplash]", self.defaults())
        core.install(["colors"], self.rep)  # n'enlève pas un réglage déjà actif
        self.assertIn("[ksplashrc][KSplash]", self.defaults())
        self.assertIn("ColorScheme", self.defaults())

    def test_union_over_successive_installs(self):
        core.install(["icons"], self.rep)
        core.install(["fonts"], self.rep)
        d = self.defaults()
        self.assertIn("Theme=hagridienne-neon", d)
        self.assertIn("font=VT323", d)

    def test_cursor_key_only_when_cursor_installed(self):
        core.install(["icons"], self.rep)
        self.assertNotIn("cursorTheme", self.defaults())
        core.install(["cursor"], self.rep)
        self.assertIn("cursorTheme=breeze_cursors", self.defaults())

    def test_unknown_ids_ignored_and_order_canonical(self):
        self.assertEqual(core.normalize_selection(["sddm", "bogus", "icons"]), ["core", "icons", "sddm"])

    def test_no_sddm_when_not_selected(self):
        core.install(["icons"], self.rep)
        self.assertFalse((self.sddm / core.SDDM_ID).exists())
        self.assertNotIn("pkexec", self.calls())


class TestAuroraeV1(Base):
    aurorae_plugin = "org.kde.kdecoration2/org.kde.kwin.aurorae.so"

    def test_falls_back_to_v1_plugin(self):
        core.install(["aurorae"], self.rep)
        self.assertIn("library=org.kde.kwin.aurorae\n", self.defaults())
        self.assertNotIn("aurorae.v2", self.defaults())


class TestAuroraeDetection(Base):
    def test_v2_wins_when_both_present(self):
        extra = self.plugins / "org.kde.kdecoration2" / "org.kde.kwin.aurorae.so"
        extra.parent.mkdir(parents=True)
        extra.write_text("")
        self.assertEqual(core.detect_aurorae(), "org.kde.kwin.aurorae.v2")

    def test_default_is_v2_when_nothing_found(self):
        shutil.rmtree(self.plugins)
        self.assertEqual(core.detect_aurorae(), "org.kde.kwin.aurorae.v2")


class TestApply(Base):
    def test_apply_full_with_cursor(self):
        core.install(core.ALL_IDS, self.rep)
        res = core.apply_theme(True, self.rep)
        self.assertTrue(res.ok, res.error)
        calls = self.calls()
        self.assertIn(f"plasma-apply-lookandfeel -a {core.THEME_ID}", calls)
        self.assertTrue(any(c.startswith("plasma-apply-wallpaperimage") and c.endswith("RepubliqueHagridienne") for c in calls))
        self.assertIn("plasma-apply-cursortheme EtoileHagridienne", calls)
        self.assertTrue(any(c.startswith("qdbus6 org.kde.KWin /KWin reconfigure") for c in calls))

    def test_apply_without_cursor_choice(self):
        core.install(core.ALL_IDS, self.rep)
        core.apply_theme(False, self.rep)
        self.assertFalse(any("cursortheme" in c for c in self.calls()))

    def test_apply_custom_does_not_touch_wallpaper(self):
        core.install(["icons"], self.rep)
        res = core.apply_theme(False, self.rep)
        self.assertTrue(res.ok)
        self.assertFalse(any("wallpaperimage" in c for c in self.calls()))
        self.assertEqual(res.applied, ["icons"])

    def test_apply_without_core_fails_cleanly(self):
        res = core.apply_theme(False, self.rep)
        self.assertFalse(res.ok)

    def test_apply_without_plasma_tools(self):
        core.install(["icons"], self.rep)
        (self.bin / "plasma-apply-lookandfeel").unlink()
        res = core.apply_theme(False, self.rep)
        self.assertFalse(res.ok)
        self.assertIn("Paramètres système", res.error)


class TestUninstall(Base):
    def test_partial_uninstall_updates_defaults(self):
        core.install(core.ALL_IDS, self.rep)
        res = core.uninstall(["icons", "cursor"], False, self.rep)
        self.assertTrue(res.ok)
        self.assertFalse((self.data / "icons").joinpath("hagridienne-neon").exists())
        self.assertFalse((self.data / "icons").joinpath("EtoileHagridienne").exists())
        d = self.defaults()
        self.assertNotIn("hagridienne-neon", d)
        self.assertNotIn("cursorTheme", d)
        self.assertIn("ColorScheme", d)
        self.assertIn("[ksplashrc][KSplash]", d)

    def test_full_uninstall_matches_uninstall_sh_and_keeps_fonts_by_default(self):
        core.install(core.ALL_IDS, self.rep)
        ids = [i for i, there in core.detect_installed().items() if there and i != "fonts"]
        res = core.uninstall(ids, True, self.rep)
        self.assertTrue(res.ok, res.error)
        inst = core.detect_installed()
        self.assertEqual([i for i, v in inst.items() if v], ["fonts"])
        self.assertFalse(self.sddm.joinpath(core.SDDM_ID).exists())
        self.assertIn(f"plasma-apply-lookandfeel -a {core.BREEZE_DARK_ID}", self.calls())

    def test_uninstall_removes_sddm_conf_first(self):
        core.install(core.ALL_IDS, self.rep)
        core.sddm_enable(self.rep)
        self.assertTrue(core.sddm_enabled())
        core.uninstall(["sddm"], False, self.rep)
        self.assertFalse(self.conf.exists())
        self.assertFalse(core.sddm_enabled())

    def test_never_deletes_outside_data_dir(self):
        core.install(["icons"], self.rep)
        outside = self.tmp / "outside"
        outside.mkdir()
        (outside / "keep.txt").write_text("x")
        # un lien symbolique à la place du dossier d'icônes ne doit pas faire supprimer la cible
        shutil.rmtree(self.data / "icons" / "hagridienne-neon")
        os.symlink(outside, self.data / "icons" / "hagridienne-neon")
        core.uninstall(["icons"], False, self.rep)
        self.assertTrue((outside / "keep.txt").exists())


class TestSddmEnable(Base):
    def test_enable_writes_expected_conf(self):
        core.install(["sddm"], self.rep)
        self.assertTrue(core.sddm_enable(self.rep))
        self.assertEqual(self.conf.read_text(), "[Theme]\nCurrent=republique-hagridienne\n")

    def test_pkexec_refused_is_a_warning_not_a_crash(self):
        (self.bin / "pkexec").write_text("#!/bin/sh\nexit 126\n")
        res = core.install(["sddm"], self.rep)
        self.assertTrue(res.ok)
        self.assertFalse(res.sddm_installed)
        self.assertTrue(any("refusée" in w for w in res.warnings))
        self.assertFalse((self.sddm / core.SDDM_ID).exists())

    def test_no_pkexec_gives_manual_command(self):
        (self.bin / "pkexec").unlink()
        res = core.install(["sddm"], self.rep)
        self.assertTrue(res.ok)
        self.assertFalse(res.sddm_installed)
        self.assertTrue(any("Commande manuelle" in w for w in res.warnings))


class TestEnvironment(Base):
    def test_host_env_restores_apprun_changes(self):
        os.environ["LD_LIBRARY_PATH"] = "/tmp/bundled"
        os.environ["RSH_ORIG_LD_LIBRARY_PATH"] = "/usr/lib/real"
        os.environ["PYTHONHOME"] = "/tmp/bundled-py"
        os.environ["RSH_ORIG_PYTHONHOME"] = "__RSH_UNSET__"
        os.environ["APPDIR"] = "/tmp/.mount_x"
        env = core.host_env()
        self.assertEqual(env["LD_LIBRARY_PATH"], "/usr/lib/real")
        self.assertNotIn("PYTHONHOME", env)
        self.assertNotIn("APPDIR", env)
        self.assertFalse(any(k.startswith("RSH_ORIG_") for k in env))

    def test_environment_inspection(self):
        env = core.inspect_environment()
        self.assertEqual(env.plasma, "6.5.2")
        self.assertEqual(env.plasma_major, 6)
        self.assertTrue(env.can_apply and env.has_pkexec)

    def test_applied_markers(self):
        cfg = core.config_home()
        cfg.mkdir(parents=True)
        (cfg / "kdeglobals").write_text("[General]\nColorScheme=RepubliqueHagridienne\n[Icons]\nTheme=breeze\n")
        self.assertEqual(core.applied_markers(), ["schéma de couleurs"])

    def test_component_sizes(self):
        self.assertGreater(core.component_size(core.BY_ID["icons"])[0], 2_000_000)
        self.assertEqual(core.format_size(4_900_000), "4,7 Mo")


if __name__ == "__main__":
    unittest.main()
