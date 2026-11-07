"""Pilote l'assistant hors écran, enregistre des captures et vérifie les parcours."""
import os, shutil, stat, sys, tempfile, time
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app")); sys.path.insert(0, str(ROOT))
from tests.test_core import FAKE_TOOLS

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/shots")
OUT.mkdir(exist_ok=True, parents=True)

def setup():
    tmp = Path(tempfile.mkdtemp(prefix="rsh-gui-"))
    (tmp/"bin").mkdir(); (tmp/"home").mkdir()
    for n, b in FAKE_TOOLS.items():
        f = tmp/"bin"/n; f.write_text(f"#!/bin/sh\n{b}\n"); f.chmod(0o755)
    os.environ.update(HOME=str(tmp/"home"), XDG_DATA_HOME=str(tmp/"home/share"), XDG_CONFIG_HOME=str(tmp/"home/cfg"),
        XDG_CACHE_HOME=str(tmp/"home/cache"), PATH=f"{tmp/'bin'}:/usr/bin:/bin", FAKE_LOG=str(tmp/"calls.log"),
        RSH_SDDM_DIR=str(tmp/"sddm"), RSH_SDDM_CONF=str(tmp/"sddm.conf"))
    return tmp

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtWidgets import QApplication
from rsh_installer import core, gui

def spin(cond, timeout=60):
    t = time.time()
    while not cond():
        QCoreApplication.processEvents()
        time.sleep(0.02)
        assert time.time() - t < timeout, "délai dépassé"
    for _ in range(5): QCoreApplication.processEvents()

def shot(w, name):
    for _ in range(5): QCoreApplication.processEvents()
    w.grab().save(str(OUT/f"{name}.png"))

def scenario_full():
    tmp = setup(); core._size_cache.clear()
    w = gui.Wizard(); w.show()
    spin(lambda: w.env is not None)
    shot(w, "01_welcome")
    w.go_next(); shot(w, "02_mode_full")
    w.card_custom.radio.setChecked(True); w.card_full.radio.setChecked(True)
    w.go_next(); assert w.key == "summary", w.key; shot(w, "05_summary_full")
    w.go_next(); assert w.key == "progress"
    spin(lambda: w.install_result is not None); shot(w, "06_progress_done")
    spin(lambda: w.key == "finish", 10); shot(w, "07_finish_full")
    assert w.rb_yes.isChecked() and w.cb_cursor.isVisible() and w.sddm_box.isVisible()
    w.go_next()                       # Terminer -> applique
    spin(lambda: w._finish_phase == 1); shot(w, "08_applied")
    calls = (tmp/"calls.log").read_text()
    assert f"plasma-apply-lookandfeel -a {core.THEME_ID}" in calls and "cursortheme EtoileHagridienne" in calls, calls
    assert not Path(tmp/"sddm.conf").exists()
    print("full: OK")
    w._busy = False; w.close()

def scenario_custom_no_apply():
    tmp = setup(); core._size_cache.clear()
    w = gui.Wizard(); w.show(); spin(lambda: w.env is not None)
    w.go_next(); w.card_custom.radio.setChecked(True)
    w.go_next(); assert w.key == "components"; shot(w, "03_components")
    for i in range(w.comp_list.count()):       # sélectionne le curseur pour la capture
        if w.comp_list.item(i).data(Qt.ItemDataRole.UserRole) == "sddm": w.comp_list.setCurrentRow(i)
    shot(w, "04_components_sddm")
    # ne garder que icônes + couleurs
    for i in range(w.comp_list.count()):
        it = w.comp_list.item(i); cid = it.data(Qt.ItemDataRole.UserRole)
        if not core.BY_ID[cid].required:
            it.setCheckState(Qt.CheckState.Checked if cid in ("icons","colors") else Qt.CheckState.Unchecked)
    w.go_next(); assert w.key == "summary"; shot(w, "05b_summary_custom")
    w.go_next(); spin(lambda: w.install_result is not None); spin(lambda: w.key == "finish", 10)
    assert not w.cb_cursor.isVisible() and not w.sddm_box.isVisible()
    w.rb_no.setChecked(True); shot(w, "07b_finish_custom")
    w.go_next()                       # Terminer sans appliquer -> ferme
    assert not w.isVisible()
    calls = (tmp/"calls.log").read_text() if (tmp/"calls.log").exists() else ""
    assert "apply-lookandfeel" not in calls
    assert core.detect_installed()["icons"] and not core.detect_installed()["fonts"]
    print("custom/no-apply: OK")

def scenario_uninstall():
    tmp = setup(); core._size_cache.clear()
    core.install(core.ALL_IDS, core.Reporter())
    w = gui.Wizard(); w.show(); spin(lambda: w.env is not None)
    assert w.btn_uninstall.isVisible() or not w.btn_uninstall.isHidden()
    shot(w, "09_welcome_installed")
    w.start_flow("uninstall"); shot(w, "10_uninstall")
    w.go_next(); spin(lambda: w.key == "uninst_done"); shot(w, "11_uninstall_done")
    left = [k for k, v in core.detect_installed().items() if v]
    assert left == ["fonts"], left
    print("uninstall: OK")

if __name__ == "__main__":
    app = gui.make_app()
    for f in (scenario_full, scenario_custom_no_apply, scenario_uninstall):
        f()
