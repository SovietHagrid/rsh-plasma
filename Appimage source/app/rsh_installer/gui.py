"""Assistant graphique (PySide6) aux couleurs du thème."""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QFont, QFontDatabase, QPixmap
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QDialog, QFrame, QGraphicsDropShadowEffect, QHBoxLayout,
    QLabel, QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton,
    QRadioButton, QStackedWidget, QTextBrowser, QVBoxLayout, QWidget,
)
from PySide6.QtGui import QColor

from . import core
from .version import INSTALLER_VERSION, THEME_RELEASE

NIGHT, PANEL, TEXT = "#020818", "#0a1628", "#cce0ff"
CYAN, PINK, GOLD, LIME, SEL = "#00f5ff", "#ff00cc", "#ffd700", "#00ff88", "#d400a8"
MUTED = "#8aa0c8"

QSS = f"""
* {{ color: {TEXT}; font-size: 11pt; }}
QWidget#root, QStackedWidget, QWidget#page {{ background: {PANEL}; }}
QFrame#sidebar {{ background: {NIGHT}; border-right: 2px solid {CYAN}; }}
QLabel {{ background: transparent; }}
QLabel#h1 {{ color: {CYAN}; font-family: Orbitron; font-size: 19pt; font-weight: bold; }}
QLabel#h2 {{ color: {GOLD}; font-family: Orbitron; font-size: 12pt; font-weight: bold; }}
QLabel#brand {{ color: {CYAN}; font-family: Orbitron; font-size: 12pt; font-weight: bold; }}
QLabel#muted {{ color: {MUTED}; }}
QLabel#step {{ color: {MUTED}; padding: 5px 8px; }}
QLabel#stepOn {{ color: {NIGHT}; background: {CYAN}; padding: 5px 8px; font-weight: bold; }}
QLabel#stepDone {{ color: {LIME}; padding: 5px 8px; }}
QPushButton {{ background: {PANEL}; border: 2px solid {CYAN}; color: {CYAN}; padding: 7px 20px; }}
QPushButton:hover {{ border-color: {PINK}; color: {PINK}; }}
QPushButton:disabled {{ border-color: #2a3b5c; color: #4d5f80; }}
QPushButton#primary {{ background: {CYAN}; color: {NIGHT}; font-weight: bold; }}
QPushButton#primary:hover {{ background: {PINK}; border-color: {PINK}; color: white; }}
QPushButton#primary:disabled {{ background: #1b2c48; border-color: #2a3b5c; color: #4d5f80; }}
QPushButton#link {{ border: none; color: {MUTED}; padding: 2px 4px; text-decoration: underline; }}
QPushButton#link:hover {{ color: {PINK}; }}
QFrame#card {{ background: {NIGHT}; border: 2px solid #2a3b5c; }}
QFrame#card[sel="true"] {{ border-color: {PINK}; }}
QFrame#card QLabel, QFrame#card QRadioButton {{ background: transparent; }}
QListWidget {{ background: {NIGHT}; border: 2px solid {CYAN}; outline: none; }}
QListWidget::item {{ padding: 6px 4px; border-bottom: 1px solid #14233f; }}
QListWidget::item:selected {{ background: {SEL}; color: white; }}
QCheckBox, QRadioButton {{ spacing: 9px; background: transparent; }}
QListWidget::indicator {{ width: 14px; height: 14px; border: 2px solid {CYAN}; background: {NIGHT}; margin-left: 4px; }}
QListWidget::indicator:checked {{ background: {CYAN}; }}
QListWidget::indicator:disabled {{ border-color: {GOLD}; background: {GOLD}; }}
QCheckBox::indicator, QRadioButton::indicator {{ width: 14px; height: 14px; border: 2px solid {CYAN}; background: {NIGHT}; }}
QRadioButton::indicator {{ border-radius: 9px; }}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{ background: {CYAN}; border-color: {CYAN}; }}
QCheckBox::indicator:disabled, QRadioButton::indicator:disabled {{ border-color: #2a3b5c; }}
QProgressBar {{ border: 2px solid {CYAN}; background: {NIGHT}; height: 16px; text-align: center; color: {TEXT}; }}
QProgressBar::chunk {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 {CYAN}, stop:1 {PINK}); }}
QPlainTextEdit, QTextBrowser {{ background: {NIGHT}; border: 2px solid #2a3b5c; font-family: VT323, monospace; font-size: 13pt; }}
QTextBrowser#plain {{ border: none; background: transparent; font-family: inherit; font-size: 11pt; }}
QScrollBar:vertical {{ background: {NIGHT}; width: 12px; }}
QScrollBar::handle:vertical {{ background: #2a3b5c; min-height: 24px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
"""


# --------------------------------------------------------------------------------------
# Tâches en arrière-plan
# --------------------------------------------------------------------------------------


class Worker(QObject):
    log = Signal(str, str)
    progress = Signal(float, str)
    done = Signal(object)

    def __init__(self, fn):
        super().__init__()
        self.fn = fn

    def run(self):
        rep = core.Reporter(log=lambda m, lv="info": self.log.emit(m, lv),
                            progress=lambda f, t="": self.progress.emit(f, t))
        try:
            res = self.fn(rep)
        except Exception as exc:  # noqa: BLE001
            rep.log(f"Erreur inattendue : {exc}", "error")
            res = exc
        self.done.emit(res)


class Relay(QObject):
    """Vit dans le thread principal : les signaux du worker y arrivent en file d'attente,
    de sorte que l'interface n'est jamais touchée depuis un autre thread."""

    def __init__(self, parent, on_log, on_progress, on_done):
        super().__init__(parent)
        self._l, self._p, self._d = on_log, on_progress, on_done

    @Slot(str, str)
    def log(self, msg, level):
        if self._l:
            self._l(msg, level)

    @Slot(float, str)
    def progress(self, frac, text):
        if self._p:
            self._p(frac, text)

    @Slot(object)
    def done(self, res):
        if self._d:
            self._d(res)


class Card(QFrame):
    """Carte cliquable contenant un bouton radio, un titre et un texte."""

    def __init__(self, title: str, text: str, badge: str = ""):
        super().__init__()
        self.setObjectName("card")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.radio = QRadioButton(title)
        self.radio.setStyleSheet(f"font-family: Orbitron; font-weight: bold; font-size: 12pt; color: {CYAN};")
        body = QLabel(text)
        body.setWordWrap(True)
        body.setStyleSheet(f"color: {TEXT}; padding-left: 26px;")
        top = QHBoxLayout()
        top.addWidget(self.radio, 1)
        if badge:
            b = QLabel(badge)
            b.setStyleSheet(f"background: {GOLD}; color: {NIGHT}; font-weight: bold; padding: 2px 8px;")
            top.addWidget(b)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 14)
        lay.setSpacing(6)
        lay.addLayout(top)
        lay.addWidget(body)
        fx = QGraphicsDropShadowEffect(self)
        fx.setBlurRadius(0)
        fx.setOffset(5, 5)
        fx.setColor(QColor(PINK))
        fx.setEnabled(False)
        self.setGraphicsEffect(fx)
        self.radio.toggled.connect(self._sync)

    def _sync(self, on: bool):
        self.setProperty("sel", "true" if on else "false")
        self.style().unpolish(self)
        self.style().polish(self)
        self.graphicsEffect().setEnabled(on)

    def mousePressEvent(self, _e):
        self.radio.setChecked(True)


def _label(text="", name="", wrap=True) -> QLabel:
    lb = QLabel(text)
    if name:
        lb.setObjectName(name)
    lb.setWordWrap(wrap)
    lb.setTextFormat(Qt.TextFormat.RichText)
    return lb


def _page() -> tuple[QWidget, QVBoxLayout]:
    w = QWidget()
    w.setObjectName("page")
    lay = QVBoxLayout(w)
    lay.setContentsMargins(32, 28, 32, 12)
    lay.setSpacing(12)
    return w, lay


def _dot(ok: bool | None) -> str:
    color = LIME if ok else (GOLD if ok is None else PINK)
    return f'<span style="color:{color}">●</span>'


# --------------------------------------------------------------------------------------
# Fenêtre principale
# --------------------------------------------------------------------------------------


class Wizard(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("root")
        self.setWindowTitle(f"Installeur — {core.THEME_NAME}")
        self.resize(980, 660)
        self.setMinimumSize(900, 620)
        self.env: core.Environment | None = None
        self.flow = "install"
        self.mode = "full"
        self.selection: list[str] = list(core.ALL_IDS)
        self.install_result: core.InstallResult | None = None
        self.task_ok = False
        self._busy = False
        self._threads: list[QThread] = []
        self._finish_phase = 0
        self.key = "welcome"
        self.fatal = False

        self._build_sidebar()
        self.stack = QStackedWidget()
        self.pages: dict[str, QWidget] = {}
        for key, builder in (("welcome", self._p_welcome), ("mode", self._p_mode),
                             ("components", self._p_components), ("summary", self._p_summary),
                             ("progress", self._p_progress), ("finish", self._p_finish),
                             ("uninst", self._p_uninst), ("uninst_done", self._p_uninst_done)):
            self.pages[key] = builder()
            self.stack.addWidget(self.pages[key])

        self.btn_back = QPushButton("Retour")
        self.btn_next = QPushButton("Suivant")
        self.btn_next.setObjectName("primary")
        self.btn_quit = QPushButton("Quitter")
        self.btn_back.clicked.connect(self.go_back)
        self.btn_next.clicked.connect(self.go_next)
        self.btn_quit.clicked.connect(self.close)
        bar = QHBoxLayout()
        bar.setContentsMargins(32, 6, 32, 18)
        bar.setSpacing(12)
        bar.addWidget(self.btn_quit)
        bar.addStretch(1)
        bar.addWidget(self.btn_back)
        bar.addWidget(self.btn_next)

        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(0)
        right.addWidget(self.stack, 1)
        right.addLayout(bar)
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self.sidebar)
        root.addLayout(right, 1)

        self.go("welcome")
        QTimer.singleShot(0, self._probe_env)

    # ---- barre latérale -------------------------------------------------------------
    def _build_sidebar(self):
        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(250)
        lay = QVBoxLayout(self.sidebar)
        lay.setContentsMargins(18, 26, 18, 18)
        lay.setSpacing(4)
        star = payload_star()
        if star:
            sv = QSvgWidget(str(star))
            sv.setFixedSize(84, 84)
            sv.setStyleSheet("background: transparent;")
            lay.addWidget(sv, 0, Qt.AlignmentFlag.AlignHCenter)
        brand = _label("RÉPUBLIQUE<br>HAGRIDIENNE", "brand")
        brand.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(brand)
        sub = _label(f"Thème Plasma 6 · {THEME_RELEASE}", "muted")
        sub.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(sub)
        lay.addSpacing(22)
        self.step_box = QVBoxLayout()
        self.step_box.setSpacing(2)
        lay.addLayout(self.step_box)
        lay.addStretch(1)
        lay.addWidget(_label(f"Installeur {INSTALLER_VERSION}", "muted"))

    LABELS = {"welcome": "Bienvenue", "mode": "Type d’installation", "components": "Composants",
              "summary": "Récapitulatif", "progress": "Progression", "finish": "Terminé",
              "uninst": "Désinstallation", "uninst_done": "Terminé"}

    def steps(self) -> list[str]:
        if self.flow == "uninstall":
            return ["uninst", "progress", "uninst_done"]
        s = ["welcome", "mode"]
        if self.mode == "custom":
            s.append("components")
        return s + ["summary", "progress", "finish"]

    def _refresh_steps(self):
        while self.step_box.count():
            w = self.step_box.takeAt(0).widget()
            if w:
                w.hide()
                w.setParent(None)
                w.deleteLater()
        order = self.steps()
        cur = order.index(self.key) if self.key in order else 0
        for i, k in enumerate(order):
            lb = QLabel(("✓  " if i < cur else "") + self.LABELS[k])
            lb.setObjectName("stepOn" if i == cur else "stepDone" if i < cur else "step")
            self.step_box.addWidget(lb)

    # ---- navigation -----------------------------------------------------------------
    def go(self, key: str):
        self.key = key
        self.stack.setCurrentWidget(self.pages[key])
        self._refresh_steps()
        self.btn_back.setVisible(key in ("mode", "components", "summary"))
        self.btn_back.setEnabled(True)
        self.btn_next.setEnabled(True)
        self.btn_next.setVisible(True)
        self.btn_quit.setEnabled(not self._busy)
        getattr(self, f"_enter_{key}", lambda: None)()

    def go_next(self):
        if self.fatal:
            return self.close()
        if self.key == "finish":
            return self._finish_clicked()
        if self.key == "uninst":
            return self._start_uninstall()
        if self.key == "uninst_done":
            return self.close()
        order = self.steps()
        self.go(order[order.index(self.key) + 1])

    def go_back(self):
        if self.key == "mode" or self.key == "uninst":
            return self.go("welcome")
        order = self.steps()
        self.go(order[order.index(self.key) - 1])

    def set_busy(self, busy: bool):
        self._busy = busy
        for b in (self.btn_back, self.btn_next, self.btn_quit):
            b.setEnabled(not busy)

    def run_async(self, fn, on_log=None, on_progress=None, on_done=None):
        th, wk = QThread(self), Worker(fn)
        wk.moveToThread(th)

        def finished(res):
            th.quit()
            th.wait()
            self._threads.remove(th)
            if on_done:
                on_done(res)

        relay = Relay(self, on_log, on_progress, finished)
        th.started.connect(wk.run)
        wk.log.connect(relay.log, Qt.ConnectionType.QueuedConnection)
        wk.progress.connect(relay.progress, Qt.ConnectionType.QueuedConnection)
        wk.done.connect(relay.done, Qt.ConnectionType.QueuedConnection)
        th._keep = (wk, relay)  # références
        self._threads.append(th)
        th.start()

    def closeEvent(self, e):
        if self._busy:
            QMessageBox.information(self, "Opération en cours", "Patientez : l’opération n’est pas terminée.")
            e.ignore()
        else:
            e.accept()

    # ---- page : bienvenue -----------------------------------------------------------
    def _p_welcome(self):
        w, lay = _page()
        lay.addWidget(_label("Bienvenue dans le futur !", "h1"))
        lay.addWidget(_label(
            f"Cet assistant installe le thème global KDE Plasma 6 « {core.THEME_NAME} » : couleurs, style "
            "Plasma, décorations de fenêtres, icônes, polices, fond d’écran, curseur, écrans de démarrage "
            "et de connexion. Vous choisirez une installation complète ou personnalisée, puis, à la fin, "
            "d’appliquer le thème tout de suite ou non."))
        lay.addSpacing(6)
        lay.addWidget(_label("Votre système", "h2"))
        self.env_label = _label("Analyse en cours…")
        lay.addWidget(self.env_label)
        self.installed_label = _label("")
        lay.addWidget(self.installed_label)
        row = QHBoxLayout()
        self.btn_uninstall = QPushButton("Désinstaller…")
        self.btn_uninstall.clicked.connect(lambda: self.start_flow("uninstall"))
        self.btn_uninstall.hide()
        row.addWidget(self.btn_uninstall)
        row.addStretch(1)
        lic = QPushButton("Licence")
        lic.setObjectName("link")
        lic.clicked.connect(self._show_license)
        row.addWidget(lic)
        lay.addLayout(row)
        lay.addStretch(1)
        return w

    def _probe_env(self):
        self.run_async(lambda rep: core.inspect_environment(), on_done=self._env_ready)

    def _env_ready(self, env):
        if isinstance(env, Exception):
            return
        self.env = env
        rows = []
        if env.plasma:
            rows.append(f"{_dot(env.plasma_major is not None and env.plasma_major >= 6)} KDE Plasma <b>{env.plasma}</b>"
                        + ("" if (env.plasma_major or 0) >= 6 else " — ce thème est conçu pour Plasma 6"))
        else:
            rows.append(f"{_dot(None)} KDE Plasma introuvable — les fichiers pourront être installés, mais pas appliqués")
        rows.append(f"{_dot(env.can_apply)} Application automatique du thème : "
                    + ("disponible" if env.can_apply else "indisponible (à faire depuis Paramètres système)"))
        self.env_label.setText("<br>".join(rows))
        self._refresh_installed()

    def _refresh_installed(self):
        inst = core.detect_installed()
        names = [core.BY_ID[i].label for i, v in inst.items() if v]
        if names:
            self.installed_label.setText(f"{_dot(True)} Déjà installé : {len(names)} composant(s). "
                                         "Continuer réinstalle (met à jour) ; vous pouvez aussi désinstaller.")
            self.btn_uninstall.show()
        else:
            self.installed_label.setText(f"{_dot(None)} Le thème n’est pas encore installé.")
            self.btn_uninstall.hide()

    def _enter_welcome(self):
        self.btn_next.setText("Commencer")
        self._refresh_installed()

    def _show_license(self):
        d = QDialog(self)
        d.setWindowTitle("Licence")
        d.resize(720, 520)
        d.setStyleSheet(f"QDialog {{ background: {PANEL}; }}")
        tb = QTextBrowser()
        f = core.payload_dir() / "LICENSE.md"
        tb.setMarkdown(f.read_text(encoding="utf-8") if f.exists() else "Licence introuvable.")
        lay = QVBoxLayout(d)
        lay.addWidget(tb)
        ok = QPushButton("Fermer")
        ok.clicked.connect(d.accept)
        lay.addWidget(ok, 0, Qt.AlignmentFlag.AlignRight)
        d.exec()

    def start_flow(self, flow: str):
        self.flow = flow
        self.go("uninst" if flow == "uninstall" else "mode")

    # ---- page : type d'installation -------------------------------------------------
    def _p_mode(self):
        w, lay = _page()
        lay.addWidget(_label("Type d’installation", "h1"))
        total = sum(core.component_size(c)[0] for c in core.COMPONENTS)
        self.card_full = Card(
            "Installation complète",
            "Installe tous les composants : thème global et écran de démarrage, couleurs, style Plasma, "
            "décorations de fenêtres, icônes, polices, fond d’écran, Konsole, curseur étoile et écran de "
            "connexion SDDM (copié sans être activé ; le mot de passe administrateur sera demandé).<br>"
            f"<span style='color:{MUTED}'>Espace nécessaire : environ {core.format_size(total)}.</span>",
            "Recommandée")
        self.card_custom = Card(
            "Installation personnalisée",
            "Choisissez vous-même les composants à installer : par exemple seulement les icônes et les "
            "couleurs. Le thème global est toujours installé ; seuls les composants cochés seront appliqués.")
        grp = QButtonGroup(self)
        grp.addButton(self.card_full.radio)
        grp.addButton(self.card_custom.radio)
        self.card_full.radio.setChecked(True)
        self.card_full.radio.toggled.connect(lambda on: self._set_mode("full" if on else "custom"))
        lay.addWidget(self.card_full)
        lay.addSpacing(6)
        lay.addWidget(self.card_custom)
        lay.addStretch(1)
        return w

    def _set_mode(self, mode):
        self.mode = mode
        self._refresh_steps()

    def _enter_mode(self):
        self.btn_next.setText("Suivant")

    # ---- page : composants ----------------------------------------------------------
    def _p_components(self):
        w, lay = _page()
        lay.addWidget(_label("Composants à installer", "h1"))
        row = QHBoxLayout()
        row.setSpacing(16)
        self.comp_list = QListWidget()
        self.comp_list.setMinimumWidth(330)
        for c in core.COMPONENTS:
            size = core.component_size(c)[0]
            bits = [core.format_size(size)] if size and c.kind != "toggle" else []
            if c.note:
                bits.append(c.note)
            it = QListWidgetItem(f"{c.label}\n{' · '.join(bits)}")
            it.setData(Qt.ItemDataRole.UserRole, c.id)
            if c.required:
                it.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                it.setCheckState(Qt.CheckState.Checked)
            else:
                it.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsUserCheckable)
                it.setCheckState(Qt.CheckState.Checked if c.in_custom_default else Qt.CheckState.Unchecked)
            self.comp_list.addItem(it)
        row.addWidget(self.comp_list, 1)
        side_w = QWidget()
        side_w.setFixedWidth(300)
        side = QVBoxLayout(side_w)
        side.setContentsMargins(0, 0, 0, 0)
        self.preview = QLabel()
        self.preview.setFixedSize(300, 176)
        self.preview.setScaledContents(False)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setStyleSheet(f"background: {NIGHT}; border: 2px solid #2a3b5c;")
        self.comp_desc = _label("")
        side.addWidget(self.preview)
        side.addWidget(self.comp_desc)
        side.addStretch(1)
        row.addWidget(side_w)
        lay.addLayout(row, 1)
        foot = QHBoxLayout()
        self.total_label = _label("", "muted", wrap=False)
        b_all = QPushButton("Tout cocher")
        b_opt = QPushButton("Sélection par défaut")
        b_all.clicked.connect(lambda: self._set_all(True))
        b_opt.clicked.connect(lambda: self._set_all(False))
        foot.addWidget(self.total_label, 1)
        foot.addWidget(b_opt)
        foot.addWidget(b_all)
        lay.addLayout(foot)
        self.comp_list.itemChanged.connect(lambda _i: self._update_total())
        self.comp_list.currentItemChanged.connect(lambda cur, _p: cur and self._show_comp(cur.data(Qt.ItemDataRole.UserRole)))
        self.comp_list.setCurrentRow(0)
        self._update_total()
        return w

    def _set_all(self, on: bool):
        for i in range(self.comp_list.count()):
            it = self.comp_list.item(i)
            c = core.BY_ID[it.data(Qt.ItemDataRole.UserRole)]
            if c.required:
                continue
            keep = on or c.in_custom_default      # sélection par défaut : tout sauf curseur et SDDM
            it.setCheckState(Qt.CheckState.Checked if keep else Qt.CheckState.Unchecked)
        self._update_total()

    def _checked_ids(self) -> list[str]:
        ids = []
        for i in range(self.comp_list.count()):
            it = self.comp_list.item(i)
            if it.checkState() == Qt.CheckState.Checked:
                ids.append(it.data(Qt.ItemDataRole.UserRole))
        return core.normalize_selection(ids)

    def _update_total(self):
        ids = self._checked_ids()
        total = sum(core.component_size(core.BY_ID[i])[0] for i in ids)
        self.total_label.setText(f"{len(ids)} composant(s) · {core.format_size(total)}")

    def _show_comp(self, cid: str):
        c = core.BY_ID[cid]
        self.comp_desc.setText(f"<b style='color:{CYAN}'>{c.label}</b><br>{c.desc}")
        pm = QPixmap(str(core.payload_dir() / c.preview)) if c.preview else QPixmap()
        if pm.isNull():
            self.preview.clear()
        else:
            self.preview.setPixmap(pm.scaled(292, 168, Qt.AspectRatioMode.KeepAspectRatio,
                                             Qt.TransformationMode.SmoothTransformation))

    def _enter_components(self):
        self.btn_next.setText("Suivant")

    # ---- page : récapitulatif -------------------------------------------------------
    def _p_summary(self):
        w, lay = _page()
        lay.addWidget(_label("Récapitulatif", "h1"))
        self.summary = QTextBrowser()
        self.summary.setObjectName("plain")
        lay.addWidget(self.summary, 1)
        return w

    def _enter_summary(self):
        self.selection = core.normalize_selection(core.ALL_IDS if self.mode == "full" else self._checked_ids())
        data = core.data_home()
        rows, total = [], 0
        for i in self.selection:
            c = core.BY_ID[i]
            if c.kind == "toggle":
                where = "activé avec le thème global"
            elif c.kind == "system":
                where = str(core.sddm_themes_dir() / core.SDDM_ID)
            else:
                where = str(data / c.items[0][1])
            size = core.component_size(c)[0]
            total += size if c.kind != "toggle" else 0
            rows.append(f"<tr><td style='padding:3px 14px 3px 0'><b>{c.label}</b></td>"
                        f"<td style='color:{MUTED}'>{where}</td></tr>")
        notes = []
        if "sddm" in self.selection:
            notes.append(f"{_dot(None)} Le mot de passe administrateur sera demandé pour l’écran de connexion. "
                         "Il sera copié <b>sans être activé</b>.")
        if any(core.detect_installed().get(i) for i in self.selection if core.BY_ID[i].kind == "files"):
            notes.append(f"{_dot(None)} Les composants déjà présents seront remplacés.")
        label = "complète" if self.mode == "full" else "personnalisée"
        self.summary.setHtml(
            f"<p>Installation <b>{label}</b> — {len(self.selection)} composant(s), {core.format_size(total)}.</p>"
            f"<table>{''.join(rows)}</table><p>{'<br>'.join(notes)}</p>"
            f"<p style='color:{MUTED}'>L’application du thème vous sera proposée à la fin.</p>")
        self.btn_next.setText("Installer")

    # ---- page : progression ---------------------------------------------------------
    def _p_progress(self):
        w, lay = _page()
        self.prog_title = _label("Installation…", "h1")
        lay.addWidget(self.prog_title)
        self.prog_step = _label("")
        lay.addWidget(self.prog_step)
        self.prog_bar = QProgressBar()
        self.prog_bar.setRange(0, 1000)
        lay.addWidget(self.prog_bar)
        self.prog_log = QPlainTextEdit()
        self.prog_log.setReadOnly(True)
        lay.addWidget(self.prog_log, 1)
        return w

    def _append_log(self, log: QPlainTextEdit, msg: str, level: str):
        prefix = {"warn": "! ", "error": "✗ "}.get(level, "")
        log.appendPlainText(prefix + msg)

    def _enter_progress(self):
        self.btn_back.hide()
        self.btn_next.setEnabled(False)
        self.btn_next.setText("Suivant")
        self.prog_log.clear()
        self.prog_bar.setValue(0)
        self.set_busy(True)
        if self.flow == "uninstall":
            return
        self.prog_title.setText("Installation en cours…")
        sel = list(self.selection)
        self.run_async(lambda rep: core.install(sel, rep),
                       on_log=lambda m, lv: self._append_log(self.prog_log, m, lv),
                       on_progress=self._on_progress, on_done=self._install_done)

    def _on_progress(self, frac: float, text: str):
        self.prog_bar.setValue(int(frac * 1000))
        if text:
            self.prog_step.setText(text)

    def _install_done(self, res):
        self.set_busy(False)
        self.btn_back.hide()
        if isinstance(res, Exception) or not res.ok:
            self.prog_title.setText("L’installation a échoué")
            self.prog_step.setText(f"Détails dans {core.log_file()}")
            self.btn_next.setText("Quitter")
            self.btn_next.setEnabled(True)
            self.fatal = True
            return
        self.install_result = res
        self.prog_bar.setValue(1000)
        self.prog_title.setText("Installation terminée")
        self.prog_step.setText("Avertissements — lisez le journal ci-dessous." if res.warnings else "Tout s’est bien passé.")
        self.btn_next.setEnabled(True)
        self.btn_next.setText("Suivant")
        if not res.warnings:
            QTimer.singleShot(900, lambda: self.key == "progress" and self.go("finish"))

    # ---- page : fin / application ---------------------------------------------------
    def _p_finish(self):
        w, lay = _page()
        self.fin_title = _label("Installation terminée ⭐", "h1")
        lay.addWidget(self.fin_title)
        self.fin_info = _label("")
        lay.addWidget(self.fin_info)
        self.fin_choices = QWidget()
        cl = QVBoxLayout(self.fin_choices)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(8)
        cl.addWidget(_label("Appliquer le thème maintenant ?", "h2"))
        self.rb_yes = QRadioButton("Oui, appliquer le thème maintenant")
        self.rb_no = QRadioButton("Non, je l’appliquerai plus tard")
        self.yes_detail = _label("", "muted")
        self.yes_detail.setContentsMargins(26, 0, 0, 0)
        self.no_detail = _label("", "muted")
        self.no_detail.setContentsMargins(26, 0, 0, 0)
        self.cb_cursor = QCheckBox("Utiliser le curseur étoile ⭐")
        self.cb_cursor.setContentsMargins(26, 0, 0, 0)
        self.rb_yes.toggled.connect(lambda on: self.cb_cursor.setEnabled(on and self._can_apply()))
        cl.addWidget(self.rb_yes)
        cl.addWidget(self.yes_detail)
        cl.addWidget(self.cb_cursor)
        cl.addWidget(self.rb_no)
        cl.addWidget(self.no_detail)
        self.sddm_box = QFrame()
        self.sddm_box.setObjectName("card")
        sl = QVBoxLayout(self.sddm_box)
        sl.addWidget(_label("Écran de connexion (SDDM)", "h2"))
        sl.addWidget(_label("Un thème de connexion défectueux peut donner un écran noir au démarrage : "
                            "testez-le d’abord, puis activez-le seulement si le test est concluant.", "muted"))
        r = QHBoxLayout()
        self.cb_sddm = QCheckBox("Activer l’écran de connexion")
        self.btn_sddm_test = QPushButton("Tester dans une fenêtre")
        self.btn_sddm_test.clicked.connect(self._sddm_test)
        r.addWidget(self.cb_sddm, 1)
        r.addWidget(self.btn_sddm_test)
        sl.addLayout(r)
        cl.addWidget(self.sddm_box)
        lay.addWidget(self.fin_choices)
        self.fin_bar = QProgressBar()
        self.fin_bar.setRange(0, 1000)
        self.fin_bar.hide()
        lay.addWidget(self.fin_bar)
        self.fin_log = QPlainTextEdit()
        self.fin_log.setReadOnly(True)
        self.fin_log.hide()
        lay.addWidget(self.fin_log, 1)
        lay.addStretch(1)
        return w

    def _enter_finish(self):
        self._finish_phase = 0
        self.fin_log.hide()
        self.fin_bar.hide()
        self.fin_choices.show()
        inst = core.detect_installed()
        can = bool(self.env and self.env.can_apply)
        res = self.install_result
        warn = f" {_dot(None)} {len(res.warnings)} avertissement(s) : voir le journal." if res and res.warnings else ""
        self.fin_info.setText(f"{_dot(True)} Les composants sont installés.{warn}")
        names = [core.BY_ID[i].label for i in core.applicable_components()]
        self.yes_detail.setText("Appliqué : " + (", ".join(names) if names else "réglages du thème global") + ".")
        self.no_detail.setText(f"Plus tard : Paramètres système → Apparence et style → Thème global → « {core.THEME_NAME} ».")
        self.rb_yes.setEnabled(can)
        (self.rb_yes if can else self.rb_no).setChecked(True)
        if not can:
            self.yes_detail.setText("Indisponible : plasma-apply-lookandfeel est introuvable sur ce système.")
        self.cb_cursor.setVisible(bool(inst.get("cursor")))
        self.cb_cursor.setChecked(self.mode == "full" or "cursor" in self.selection)
        self.cb_cursor.setEnabled(can)
        show_sddm = bool(inst.get("sddm"))
        self.sddm_box.setVisible(show_sddm)
        if show_sddm:
            enabled = core.sddm_enabled()
            self.cb_sddm.setChecked(False)
            self.cb_sddm.setEnabled(not enabled)
            self.cb_sddm.setText("Écran de connexion déjà activé" if enabled else "Activer l’écran de connexion")
            self.btn_sddm_test.setEnabled(core.sddm_test_command() is not None)
            if not self.btn_sddm_test.isEnabled():
                self.btn_sddm_test.setToolTip("sddm-greeter-qt6 est introuvable")
        self.btn_back.hide()
        self.btn_next.setText("Terminer")

    def _can_apply(self) -> bool:
        return bool(self.env and self.env.can_apply)

    def _sddm_test(self):
        if not core.sddm_test():
            QMessageBox.warning(self, "Test impossible", "sddm-greeter-qt6 est introuvable ou le thème n’est pas installé.")

    def _finish_clicked(self):
        if self._finish_phase == 1:
            return self.close()
        do_apply = self.rb_yes.isChecked() and self.rb_yes.isEnabled()
        do_sddm = self.sddm_box.isVisible() and self.cb_sddm.isChecked() and self.cb_sddm.isEnabled()
        if not do_apply and not do_sddm:
            return self.close()
        cursor = self.cb_cursor.isChecked() and self.cb_cursor.isVisible()

        def job(rep: core.Reporter):
            out = {"apply": None, "sddm": None}
            if do_apply:
                out["apply"] = core.apply_theme(cursor, rep)
            if do_sddm:
                out["sddm"] = core.sddm_enable(rep)
            return out

        self.fin_choices.hide()
        self.fin_info.setText("Application en cours…")
        self.fin_bar.show()
        self.fin_log.show()
        self.fin_log.clear()
        self.set_busy(True)
        self.run_async(job, on_log=lambda m, lv: self._append_log(self.fin_log, m, lv),
                       on_progress=lambda f, t: (self.fin_bar.setValue(int(f * 1000)), t and self.fin_info.setText(t)),
                       on_done=self._apply_done)

    def _apply_done(self, out):
        self.set_busy(False)
        self._finish_phase = 1
        self.fin_bar.setValue(1000)
        problems = []
        if isinstance(out, Exception):
            problems.append(str(out))
        else:
            if out["apply"] is not None and not out["apply"].ok:
                problems.append(out["apply"].error)
            if out["sddm"] is False:
                problems.append("l’écran de connexion n’a pas été activé")
        if problems:
            self.fin_title.setText("Terminé, avec un souci")
            self.fin_info.setText(f"{_dot(False)} " + " ; ".join(problems))
        else:
            self.fin_title.setText("C’est fait ⭐")
            tip = ("Déconnectez-vous puis reconnectez-vous pour que polices, curseur et écran de démarrage "
                   "soient pris en compte partout." if out["apply"] is not None else "")
            self.fin_info.setText(f"{_dot(True)} Réglages appliqués. {tip}")
        self.btn_next.setText("Fermer")

    # ---- désinstallation ------------------------------------------------------------
    def _p_uninst(self):
        w, lay = _page()
        lay.addWidget(_label("Désinstallation", "h1"))
        lay.addWidget(_label("Cochez les composants à retirer."))
        self.un_list = QListWidget()
        lay.addWidget(self.un_list, 1)
        self.cb_revert = QCheckBox("Revenir d’abord au thème Breeze Sombre (recommandé si le thème est appliqué)")
        lay.addWidget(self.cb_revert)
        self.un_note = _label("", "muted")
        lay.addWidget(self.un_note)
        return w

    def _enter_uninst(self):
        self.btn_back.show()
        self.btn_next.setText("Désinstaller")
        self.un_list.clear()
        inst = core.detect_installed()
        for c in core.COMPONENTS:
            if not inst.get(c.id):
                continue
            it = QListWidgetItem(c.label + ("\nconservées par défaut : d’autres applications peuvent les utiliser"
                                            if c.id == "fonts" else ""))
            it.setData(Qt.ItemDataRole.UserRole, c.id)
            it.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Unchecked if c.id == "fonts" else Qt.CheckState.Checked)
            self.un_list.addItem(it)
        marks = core.applied_markers()
        self.cb_revert.setChecked(bool(marks))
        self.un_note.setText("Actuellement appliqué : " + ", ".join(marks) + "." if marks else
                             "Le thème ne semble pas appliqué dans la session actuelle.")
        self.btn_next.setEnabled(self.un_list.count() > 0)
        if not self.un_list.count():
            self.un_note.setText("Rien à désinstaller.")

    def _start_uninstall(self):
        ids = [self.un_list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.un_list.count())
               if self.un_list.item(i).checkState() == Qt.CheckState.Checked]
        if not ids:
            return
        revert = self.cb_revert.isChecked()
        self.go("progress")
        self.prog_title.setText("Désinstallation en cours…")
        self.run_async(lambda rep: core.uninstall(ids, revert, rep),
                       on_log=lambda m, lv: self._append_log(self.prog_log, m, lv),
                       on_progress=self._on_progress, on_done=self._uninstall_done)

    def _uninstall_done(self, res):
        self.set_busy(False)
        ok = not isinstance(res, Exception) and res.ok
        self.prog_bar.setValue(1000 if ok else self.prog_bar.value())
        self.prog_title.setText("Désinstallation terminée" if ok else "La désinstallation a échoué")
        self.prog_step.setText("" if ok else f"Détails dans {core.log_file()}")
        self.btn_next.setEnabled(True)
        self.btn_next.setText("Fermer")
        self.flow = "uninstall"
        self.key = "uninst_done"
        self._refresh_steps()
        self.btn_back.hide()

    def _p_uninst_done(self):
        w, _lay = _page()
        return w


def payload_star() -> Path | None:
    p = core.payload_dir() / "share" / "plasma" / "look-and-feel" / core.THEME_ID / "contents" / "splash" / "images" / "star.svg"
    return p if p.exists() else None


def _load_fonts():
    d = core.payload_dir() / "share" / "fonts" / "republique-hagridienne"
    for f in d.glob("*.ttf"):
        QFontDatabase.addApplicationFont(str(f))


def make_app() -> QApplication:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Installeur République Hagridienne")
    app.setDesktopFileName("rsh-installer")   # associe la fenêtre à l'icône sous Wayland
    _load_fonts()
    app.setStyleSheet(QSS)
    return app


def main() -> int:
    app = make_app()
    w = Wizard()
    w.show()
    return app.exec()


def selftest() -> int:
    """Construit la fenêtre et quitte : sert à vérifier un AppImage sans écran."""
    app = make_app()
    w = Wizard()
    w.show()
    QTimer.singleShot(400, app.quit)
    app.exec()
    print("selftest OK")
    return 0
