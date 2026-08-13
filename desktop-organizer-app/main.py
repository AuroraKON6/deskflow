from __future__ import annotations

import json
import os
import shutil
import sys
import winreg
from ctypes import wintypes
from pathlib import Path


def prepare_webengine_cache(qt_root: Path) -> tuple[Path, Path]:
    """Copy Chromium mmap resources to an ASCII-only shared cache."""
    source_resources = qt_root / "resources"
    source_locales = qt_root / "translations" / "qtwebengine_locales"
    icu_source = source_resources / "icudtl.dat"
    if not icu_source.exists():
        return source_resources, source_locales

    public_root = Path(os.environ.get("PUBLIC", r"C:\Users\Public"))
    try:
        str(public_root).encode("ascii")
    except UnicodeEncodeError:
        public_root = Path(os.environ.get("SystemDrive", "C:")) / "Users" / "Public"

    cache_root = public_root / "DeskFlowCache" / f"WebEngine-{icu_source.stat().st_size}"
    cached_resources = cache_root / "resources"
    cached_locales = cache_root / "locales"
    cached_icu = cached_resources / "icudtl.dat"
    locale_probe_source = source_locales / "zh-CN.pak"
    locale_probe_cached = cached_locales / "zh-CN.pak"

    try:
        cache_ready = (
            cached_icu.exists()
            and cached_icu.stat().st_size == icu_source.stat().st_size
            and locale_probe_cached.exists()
            and locale_probe_cached.stat().st_size == locale_probe_source.stat().st_size
        )
        if not cache_ready:
            cache_root.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source_resources, cached_resources, dirs_exist_ok=True)
            shutil.copytree(source_locales, cached_locales, dirs_exist_ok=True)
        return cached_resources, cached_locales
    except OSError:
        return source_resources, source_locales


def configure_qt_paths() -> None:
    """Use only DeskFlow's Qt files and avoid old Qt DLLs from system PATH."""
    if getattr(sys, "frozen", False):
        bundle_root = Path(getattr(sys, "_MEIPASS"))
        qt_root = bundle_root / "PySide6"
    else:
        bundle_root = Path(sys.prefix)
        qt_root = bundle_root / "Lib" / "site-packages" / "PySide6"

    if not qt_root.exists():
        return

    windows_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    os.environ["PATH"] = os.pathsep.join(
        str(path)
        for path in (qt_root, bundle_root, windows_root / "System32", windows_root)
    )
    webengine_resources, webengine_locales = prepare_webengine_cache(qt_root)
    locations = {
        "QT_PLUGIN_PATH": qt_root / "plugins",
        "QT_QPA_PLATFORM_PLUGIN_PATH": qt_root / "plugins" / "platforms",
        "QML2_IMPORT_PATH": qt_root / "qml",
        "QTWEBENGINEPROCESS_PATH": qt_root / "QtWebEngineProcess.exe",
        "QTWEBENGINE_RESOURCES_PATH": webengine_resources,
        "QTWEBENGINE_LOCALES_PATH": webengine_locales,
    }
    for variable, path in locations.items():
        os.environ[variable] = str(path)


configure_qt_paths()

from PySide6.QtCore import QMimeData, QObject, QSettings, QTimer, QUrl, QUrlQuery, Qt, Slot
from PySide6.QtGui import QAction, QCloseEvent, QColor, QCursor, QDesktopServices, QIcon
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEngineProfile
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QStyle,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)


APP_NAME = "序 · 桌面效率工具"
ORGANIZATION = "DeskFlow"
MODULES = {
    "todo": ("今日待办", "任务、周期和到点提醒"),
    "countdown": ("倒计时", "截止时间与紧急提醒"),
    "files": ("文件收纳", "本地文件引用与快速打开"),
}


def resource_path(*parts: str) -> Path:
    if getattr(sys, "frozen", False):
        root = Path(getattr(sys, "_MEIPASS"))
    else:
        root = Path(__file__).resolve().parent.parent
    return root.joinpath(*parts)


class DesktopWebView(QWebEngineView):
    """Accept native Windows file drops and pass their real paths to the page."""

    def __init__(self, parent: QMainWindow | None = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event) -> None:  # type: ignore[override]
        if event.mimeData().hasUrls() and any(url.isLocalFile() for url in event.mimeData().urls()):
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:  # type: ignore[override]
        if event.mimeData().hasUrls() and any(url.isLocalFile() for url in event.mimeData().urls()):
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:  # type: ignore[override]
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        if paths:
            payload = json.dumps(paths, ensure_ascii=False)
            self.page().runJavaScript(f"window.addNativeFiles?.({payload});")
            event.acceptProposedAction()
            return
        super().dropEvent(event)


class DesktopBridge(QObject):
    def __init__(self, window: "WidgetWindow", controller: "DesktopController") -> None:
        super().__init__(window)
        self.window = window
        self.controller = controller
        self.tray = controller.tray
        self.settings = QSettings(ORGANIZATION, "DesktopOrganizer")

    @Slot(str, result=bool)
    def openPath(self, path: str) -> bool:
        target = Path(path)
        if not target.exists():
            self.tray.showMessage(
                APP_NAME,
                f"文件不存在：{target.name}",
                QSystemTrayIcon.MessageIcon.Warning,
                3500,
            )
            return False
        return QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))

    @Slot("QVariantList", result=bool)
    def copyFiles(self, paths) -> bool:
        existing = [Path(str(path)) for path in paths if Path(str(path)).exists()]
        if not existing:
            self.tray.showMessage(
                APP_NAME,
                "没有可复制的真实文件",
                QSystemTrayIcon.MessageIcon.Warning,
                3000,
            )
            return False
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(path)) for path in existing])
        QApplication.clipboard().setMimeData(mime)
        return True

    @Slot(result="QVariantList")
    def chooseFiles(self):
        paths, _ = QFileDialog.getOpenFileNames(self.window, "选择要收纳的文件")
        return paths

    @Slot(str, str)
    def notify(self, title: str, body: str) -> None:
        self.tray.showMessage(title, body, QSystemTrayIcon.MessageIcon.Information, 10000)

    @Slot("QVariantList")
    def setEnabledModules(self, modules) -> None:
        self.controller.apply_selection([str(module) for module in modules])

    @Slot(bool, result=bool)
    def setAutoStart(self, enabled: bool) -> bool:
        return self.controller.set_auto_start(enabled)

    @Slot()
    def beginMove(self) -> None:
        self.window.begin_system_move()

    @Slot(int)
    def beginResize(self, edge_mask: int) -> None:
        self.window.begin_system_resize(edge_mask)

    @Slot(bool)
    def setManualSize(self, enabled: bool) -> None:
        self.window.set_manual_size(enabled)

    @Slot(bool)
    def setAlwaysOnTop(self, enabled: bool) -> None:
        self.window.set_always_on_top(enabled)

    @Slot(int, int)
    def resizeWindow(self, width: int, height: int) -> None:
        self.window.resize_to_content(width, height)

    @Slot()
    def resetPosition(self) -> None:
        self.window.reset_position()

    @Slot()
    def hideWindow(self) -> None:
        self.controller.set_widget_visible(self.window.widget_name, False, persist=True)

    @Slot()
    def openSwitcher(self) -> None:
        self.controller.show_switcher()


class StartupDialog(QDialog):
    def __init__(self, selected: list[str], auto_start: bool, icon: QIcon) -> None:
        super().__init__()
        self.setWindowTitle("序 · 桌面组件选择")
        self.setWindowIcon(icon)
        self.setModal(True)
        self.setMinimumWidth(430)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 22)
        root.setSpacing(13)

        kicker = QLabel("DESKTOP / STARTUP")
        kicker.setObjectName("kicker")
        title = QLabel("今天在桌面上放哪些组件？")
        title.setObjectName("title")
        note = QLabel("确认后选择器会关闭，每个模块都是独立悬浮窗口。")
        note.setObjectName("note")
        note.setWordWrap(True)
        root.addWidget(kicker)
        root.addWidget(title)
        root.addWidget(note)

        self.master = QCheckBox("总开关 · 全部开启 / 关闭")
        self.master.setTristate(True)
        self.master.setObjectName("master")
        root.addWidget(self.master)

        self.module_checks: dict[str, QCheckBox] = {}
        for name, (label, description) in MODULES.items():
            check = QCheckBox(f"{label}\n{description}")
            check.setChecked(name in selected)
            check.setObjectName("module")
            check.toggled.connect(self._sync_master)
            self.module_checks[name] = check
            root.addWidget(check)

        self.auto_start = QCheckBox("开机自动启动")
        self.auto_start.setChecked(auto_start)
        root.addWidget(self.auto_start)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("取消")
        start = QPushButton("放到桌面上 →")
        start.setObjectName("primary")
        cancel.clicked.connect(self.reject)
        start.clicked.connect(self.accept)
        buttons.addWidget(cancel)
        buttons.addWidget(start)
        root.addLayout(buttons)

        self.master.clicked.connect(self._toggle_all)
        self._sync_master()
        self.setStyleSheet(
            """
            QDialog { background: #ebe8df; color: #171713; }
            QLabel#kicker { color: #e75b37; font: 800 10px 'Cascadia Mono'; letter-spacing: 2px; }
            QLabel#title { font: 800 24px 'Microsoft YaHei UI'; }
            QLabel#note { color: #514f46; font-size: 11px; }
            QCheckBox { padding: 10px 12px; border: 1px solid #171713; border-radius: 6px; background: #f6f4ee; font-weight: 700; spacing: 10px; }
            QCheckBox#master { background: #d7d2c6; }
            QCheckBox::indicator { width: 18px; height: 18px; }
            QPushButton { min-height: 36px; padding: 0 15px; border: 1px solid #171713; border-radius: 5px; background: #f6f4ee; font-weight: 700; }
            QPushButton:hover { background: #d7d2c6; }
            QPushButton#primary { color: #f6f4ee; background: #171713; }
            QPushButton#primary:hover { background: #e75b37; border-color: #e75b37; }
            """
        )

    def _sync_master(self) -> None:
        enabled = sum(check.isChecked() for check in self.module_checks.values())
        self.master.blockSignals(True)
        if enabled == len(self.module_checks):
            self.master.setCheckState(Qt.CheckState.Checked)
        elif enabled == 0:
            self.master.setCheckState(Qt.CheckState.Unchecked)
        else:
            self.master.setCheckState(Qt.CheckState.PartiallyChecked)
        self.master.blockSignals(False)

    def _toggle_all(self, _checked: bool = False) -> None:
        turn_on = self.master.checkState() != Qt.CheckState.Unchecked
        for check in self.module_checks.values():
            check.setChecked(turn_on)
        self._sync_master()

    def selection(self) -> list[str]:
        return [name for name, check in self.module_checks.items() if check.isChecked()]


class WidgetWindow(QMainWindow):
    WM_NCHITTEST = 0x0084
    WM_NCLBUTTONDOWN = 0x00A1
    RESIZE_HIT_CODES = {10, 11, 12, 13, 14, 15, 16, 17}
    HIT_CODE_TO_EDGE_MASK = {
        10: 1,
        11: 4,
        12: 2,
        13: 3,
        14: 6,
        15: 8,
        16: 9,
        17: 12,
    }
    INITIAL_SIZES = {
        "todo": (390, 470),
        "countdown": (330, 500),
        "files": (460, 350),
    }

    def __init__(self, controller: "DesktopController", widget_name: str) -> None:
        super().__init__()
        self.controller = controller
        self.widget_name = widget_name
        self.settings = controller.settings
        self._always_on_top = False
        self._manual_size = bool(
            self.settings.value(f"widgetManualSize/{widget_name}", False, type=bool)
        )
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(300)
        self._save_timer.timeout.connect(self.save_position)

        flags = (
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowTitle(MODULES[widget_name][0])
        self.setMinimumSize(220, 80)
        self.setStyleSheet("QMainWindow { background: transparent; }")

        self.web = DesktopWebView(self)
        self.web.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.web.setStyleSheet("background: transparent;")
        self.setCentralWidget(self.web)
        self.web.page().setBackgroundColor(QColor(0, 0, 0, 0))

        self.channel = QWebChannel(self.web.page())
        self.bridge = DesktopBridge(self, controller)
        self.channel.registerObject("desktopBridge", self.bridge)
        self.web.page().setWebChannel(self.channel)

        html_path = resource_path("desktop-organizer-concepts", "index.html")
        if html_path.exists():
            url = QUrl.fromLocalFile(str(html_path))
            query = QUrlQuery()
            query.addQueryItem("widget", widget_name)
            if self._manual_size:
                query.addQueryItem("manual", "1")
            url.setQuery(query)
            self.web.load(url)

        width, height = self.INITIAL_SIZES[widget_name]
        stored_size = self.settings.value(f"widgetSize/{widget_name}")
        if self._manual_size and stored_size is not None:
            try:
                width, height = (int(value) for value in stored_size)
            except (TypeError, ValueError):
                self._manual_size = False
        self.resize(width, height)
        stored_position = self.settings.value(f"widgetPosition/{widget_name}")
        if stored_position is not None:
            try:
                x, y = (int(value) for value in stored_position)
                self.move(x, y)
            except (TypeError, ValueError):
                self.reset_position()
        else:
            self.reset_position()

    def default_position(self) -> tuple[int, int]:
        screen = QApplication.primaryScreen()
        if screen is None:
            return 40, 40
        area = screen.availableGeometry()
        right = area.x() + area.width()
        bottom = area.y() + area.height()
        width, height = self.width(), self.height()
        if self.widget_name == "todo":
            return right - width - 24, area.y() + 28
        if self.widget_name == "countdown":
            stacked_y = area.y() + 520
            if stacked_y + height <= bottom - 20:
                return right - width - 30, stacked_y
            return right - width - 430, area.y() + 40
        return max(area.x() + 24, right - width - 470), max(area.y() + 30, bottom - height - 36)

    def reset_position(self) -> None:
        self.move(*self.default_position())
        self.save_position()

    def save_position(self) -> None:
        self.settings.setValue(f"widgetPosition/{self.widget_name}", [self.x(), self.y()])

    def begin_system_move(self) -> None:
        handle = self.windowHandle()
        if handle is not None:
            handle.startSystemMove()

    def begin_system_resize(self, edge_mask: int) -> None:
        edge_map = (
            (1, Qt.Edge.LeftEdge),
            (2, Qt.Edge.TopEdge),
            (4, Qt.Edge.RightEdge),
            (8, Qt.Edge.BottomEdge),
        )
        edges = Qt.Edge(0)
        for bit, edge in edge_map:
            if edge_mask & bit:
                edges |= edge
        if not edges:
            return
        self.set_manual_size(True)
        handle = self.windowHandle()
        if handle is not None:
            handle.startSystemResize(edges)

    def set_manual_size(self, enabled: bool) -> None:
        self._manual_size = enabled
        self.settings.setValue(f"widgetManualSize/{self.widget_name}", enabled)
        if enabled:
            self.save_size()

    def save_size(self) -> None:
        self.settings.setValue(
            f"widgetSize/{self.widget_name}", [self.width(), self.height()]
        )

    def native_resize_hit(self) -> int:
        point = self.mapFromGlobal(QCursor.pos())
        near_left = point.x() <= 12
        near_right = point.x() >= self.width() - 23
        near_top = point.y() <= 12
        near_bottom = point.y() >= self.height() - 26
        if near_top and near_left:
            return 13  # HTTOPLEFT
        if near_top and near_right:
            return 14  # HTTOPRIGHT
        if near_bottom and near_left:
            return 16  # HTBOTTOMLEFT
        if near_bottom and near_right:
            return 17  # HTBOTTOMRIGHT
        if near_left:
            return 10  # HTLEFT
        if near_right:
            return 11  # HTRIGHT
        if near_top:
            return 12  # HTTOP
        if near_bottom:
            return 15  # HTBOTTOM
        return 0

    def nativeEvent(self, event_type, message):  # type: ignore[override]
        try:
            native_message = wintypes.MSG.from_address(int(message))
            if native_message.message == self.WM_NCHITTEST:
                hit_code = self.native_resize_hit()
                if hit_code:
                    return True, hit_code
            elif (
                native_message.message == self.WM_NCLBUTTONDOWN
                and int(native_message.wParam) in self.RESIZE_HIT_CODES
            ):
                if hasattr(self, "web"):
                    self.web.page().runJavaScript("setEmbeddedManualSize(true)")
                self.begin_system_resize(
                    self.HIT_CODE_TO_EDGE_MASK[int(native_message.wParam)]
                )
                return True, 0
        except (TypeError, ValueError):
            pass
        return super().nativeEvent(event_type, message)

    def set_always_on_top(self, enabled: bool) -> None:
        if self._always_on_top == enabled:
            return
        geometry = self.geometry()
        visible = self.isVisible()
        flags = self.windowFlags()
        if enabled:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        else:
            flags &= ~Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.setGeometry(geometry)
        self._always_on_top = enabled
        if visible:
            self.show()

    def resize_to_content(self, width: int, height: int) -> None:
        if self._manual_size:
            return
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            self.resize(max(220, width), max(70, height))
            return
        area = screen.availableGeometry()
        width = min(max(220, width), area.width() - 20)
        height = min(max(70, height), area.height() - 20)
        self.resize(width, height)
        x = min(max(self.x(), area.x()), area.x() + area.width() - width)
        y = min(max(self.y(), area.y()), area.y() + area.height() - height)
        self.move(x, y)

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        if self._manual_size:
            self.save_size()

    def moveEvent(self, event) -> None:  # type: ignore[override]
        super().moveEvent(event)
        self._save_timer.start()

    def closeEvent(self, event: QCloseEvent) -> None:  # type: ignore[override]
        if self.controller.quitting:
            event.accept()
            return
        event.ignore()
        self.controller.set_widget_visible(self.widget_name, False, persist=True)


class DesktopController(QObject):
    def __init__(self, app: QApplication, tray: QSystemTrayIcon) -> None:
        super().__init__(app)
        self.app = app
        self.tray = tray
        self.settings = QSettings(ORGANIZATION, "DesktopOrganizer")
        self.quitting = False
        self.icon = tray.icon()
        self.windows: dict[str, WidgetWindow] = {}
        self.module_actions: dict[str, QAction] = {}

        data_root = Path(os.getenv("APPDATA", str(Path.home()))) / "DeskFlow"
        data_root.mkdir(parents=True, exist_ok=True)
        profile = QWebEngineProfile.defaultProfile()
        profile.setPersistentStoragePath(str(data_root / "WebStorage"))
        profile.setCachePath(str(data_root / "WebCache"))
        profile.setPersistentCookiesPolicy(
            QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies
        )

        html_path = resource_path("desktop-organizer-concepts", "index.html")
        if not html_path.exists():
            QMessageBox.critical(None, APP_NAME, f"找不到界面文件：\n{html_path}")
            return

        self.build_tray_menu()

    def selected_modules(self) -> list[str]:
        value = self.settings.value("enabledModules", list(MODULES))
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, (list, tuple)):
            return list(MODULES)
        return [name for name in value if name in MODULES]

    def build_tray_menu(self) -> None:
        menu = QMenu()
        switcher = QAction("选择桌面组件…", menu)
        switcher.triggered.connect(self.show_switcher)
        menu.addAction(switcher)
        menu.addSeparator()
        selected = self.selected_modules()
        for name, (label, _) in MODULES.items():
            action = QAction(label, menu)
            action.setCheckable(True)
            action.setChecked(name in selected)
            action.toggled.connect(
                lambda checked, module=name: self.set_widget_visible(module, checked, persist=True)
            )
            self.module_actions[name] = action
            menu.addAction(action)
        menu.addSeparator()
        quit_action = QAction("彻底退出", menu)
        quit_action.triggered.connect(self.request_quit)
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_activated)

    def _tray_activated(self, reason) -> None:
        if reason in {
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        }:
            self.show_switcher()

    def show_switcher(self) -> None:
        dialog = StartupDialog(
            self.selected_modules(),
            bool(self.settings.value("autoStart", True, type=bool)),
            self.icon,
        )
        screen = QApplication.primaryScreen()
        dialog.adjustSize()
        if screen is not None:
            area = screen.availableGeometry()
            dialog.move(area.center() - dialog.rect().center())
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.apply_selection(dialog.selection())
            self.set_auto_start(dialog.auto_start.isChecked())

    def startup(self) -> None:
        test_modules = os.environ.get("DESKFLOW_TEST_MODULES")
        if test_modules is not None:
            self.apply_selection([name for name in test_modules.split(",") if name in MODULES])
            return
        current = self.selected_modules()
        self.show_switcher()
        if not any(window.isVisible() for window in self.windows.values()):
            self.apply_selection(self.selected_modules() if self.selected_modules() != current else current)

    def apply_selection(self, modules: list[str]) -> None:
        normalized = [name for name in MODULES if name in modules]
        self.settings.setValue("enabledModules", normalized)
        for name in MODULES:
            self.set_widget_visible(name, name in normalized, persist=False)

    def set_widget_visible(self, name: str, visible: bool, persist: bool) -> None:
        window = self.windows.get(name)
        if visible and window is None:
            window = WidgetWindow(self, name)
            self.windows[name] = window
        if visible:
            if window is not None:
                window.show()
        elif window is not None:
            window.hide()
        action = self.module_actions.get(name)
        if action is not None and action.isChecked() != visible:
            action.blockSignals(True)
            action.setChecked(visible)
            action.blockSignals(False)
        if persist:
            selected = [
                module
                for module, item in self.module_actions.items()
                if item.isChecked()
            ]
            self.settings.setValue("enabledModules", selected)

    def set_auto_start(self, enabled: bool) -> bool:
        run_key = r"Software\Microsoft\Windows\CurrentVersion\Run"
        value_name = "DeskFlow"
        if getattr(sys, "frozen", False):
            command = f'"{Path(sys.executable).resolve()}"'
        else:
            command = f'"{Path(sys.executable).resolve()}" "{Path(__file__).resolve()}"'
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, run_key, 0, winreg.KEY_SET_VALUE) as key:
                if enabled:
                    winreg.SetValueEx(key, value_name, 0, winreg.REG_SZ, command)
                else:
                    try:
                        winreg.DeleteValue(key, value_name)
                    except FileNotFoundError:
                        pass
            self.settings.setValue("autoStart", enabled)
            return True
        except OSError as error:
            self.tray.showMessage(
                APP_NAME,
                f"开机启动设置失败：{error}",
                QSystemTrayIcon.MessageIcon.Warning,
                4500,
            )
            return False

    def request_quit(self) -> None:
        self.quitting = True
        for window in self.windows.values():
            window.save_position()
            window.close()
        self.app.quit()


def build_tray(app: QApplication) -> QSystemTrayIcon:
    icon = app.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
    tray = QSystemTrayIcon(QIcon(icon), app)
    tray.setToolTip(APP_NAME)
    tray.show()
    return tray


def main() -> int:
    QApplication.setOrganizationName(ORGANIZATION)
    QApplication.setApplicationName(APP_NAME)
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    tray = build_tray(app)
    controller = DesktopController(app, tray)
    QTimer.singleShot(0, controller.startup)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
