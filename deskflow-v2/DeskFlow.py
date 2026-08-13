# -*- coding: utf-8 -*-
"""DeskFlow v2 — WebView2 shell.

Replaces the QtWebEngine shell (main.py) with a WinForms + WebView2 host.
Same architecture/functions/design; ~10x smaller bundle, ~10x less RAM.

- Three transparent frameless windows (todo / countdown / files), each hosting
  the shared desktop-organizer-concepts/index.html via virtual host mapping.
- Bridge: injected shim exposes window.desktopBridge, messages flow over
  chrome.webview.postMessage (WebMessage).
- Persistence: same registry keys as the v1 shell (HKCU\\Software\\DeskFlow\\DesktopOrganizer),
  so positions / sizes / enabled modules carry over automatically.
"""
from __future__ import annotations

import ctypes
import json
import os
import sys
import winreg
from pathlib import Path

# --- STA COM + DPI (must run before WinForms) ---
ctypes.windll.ole32.CoInitializeEx(None, 0x2)  # COINIT_APARTMENTTHREADED
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    ctypes.windll.user32.SetProcessDPIAware()

import clr  # noqa: E402

if getattr(sys, "frozen", False):
    WV2LIB = Path(getattr(sys, "_MEIPASS")) / "webview2lib"
else:
    WV2LIB = Path(__file__).resolve().parent / ".venv" / "Lib" / "site-packages" / "webview" / "lib"
NATIVE = WV2LIB / "runtimes" / "win-x64" / "native"
os.environ["PATH"] = str(NATIVE) + os.pathsep + os.environ.get("PATH", "")

clr.AddReference(str(WV2LIB / "Microsoft.Web.WebView2.Core.dll"))
clr.AddReference(str(WV2LIB / "Microsoft.Web.WebView2.WinForms.dll"))
clr.AddReference("System.Drawing")
clr.AddReference("System.Windows.Forms")

from System import Enum as SysEnum  # noqa: E402
from System.Collections.Specialized import StringCollection  # noqa: E402
from System.Drawing import Color, Point, Size, SystemIcons, Font, FontStyle  # noqa: E402
from System.Windows.Forms import (  # noqa: E402
    Application,
    CheckBox,
    Clipboard,
    ContextMenuStrip,
    DockStyle,
    DialogResult,
    Form,
    FormBorderStyle,
    FormStartPosition,
    NotifyIcon,
    OpenFileDialog,
    Screen,
    ToolStripMenuItem,
    ToolStripSeparator,
    Button,
    Label,
    HorizontalAlignment,
)
from Microsoft.Web.WebView2.WinForms import WebView2  # noqa: E402
from Microsoft.Web.WebView2.Core import CoreWebView2HostResourceAccessKind  # noqa: E402

user32 = ctypes.windll.user32


def dpi_scale() -> float:
    """Windows DPI scaling factor (1.0 = 100%, 1.5 = 150%)."""
    try:
        return user32.GetDpiForSystem() / 96.0
    except Exception:
        return 1.0

APP_NAME = "序 · 桌面效率工具"
ORGANIZATION = "DeskFlow"
REG_ROOT = r"Software\DeskFlow\DesktopOrganizer"
MODULES = {
    "todo": ("今日待办", "任务、周期和到点提醒"),
    "countdown": ("倒计时", "截止时间与紧急提醒"),
    "files": ("文件收纳", "本地文件引用与快速打开"),
}
INITIAL_SIZES = {"todo": (390, 470), "countdown": (330, 500), "files": (460, 350)}
NONE_BORDER = SysEnum.Parse(FormBorderStyle, "None")
FILL_DOCK = SysEnum.Parse(DockStyle, "Fill")

SHIM_JS = r"""
(function () {
  if (window.desktopBridge || !window.chrome || !window.chrome.webview) return;
  var pending = {}; var seq = 0;
  function call(method) {
    var args = Array.prototype.slice.call(arguments, 1);
    return new Promise(function (resolve) {
      var id = ++seq; pending[id] = resolve;
      window.chrome.webview.postMessage({ id: id, method: method, args: args });
    });
  }
  window.chrome.webview.addEventListener('message', function (e) {
    var m = e.data;
    if (m && m.id && pending[m.id]) { pending[m.id](m.result); delete pending[m.id]; }
  });
  window.desktopBridge = {
    openPath: function (p) { return call('openPath', p); },
    copyFiles: function (ps) { return call('copyFiles', ps); },
    chooseFiles: function () { return call('chooseFiles'); },
    notify: function (t, b) { return call('notify', t, b); },
    setEnabledModules: function (ms) { return call('setEnabledModules', ms); },
    setAutoStart: function (e) { return call('setAutoStart', e); },
    beginMove: function () { return call('beginMove'); },
    beginResize: function (m) { return call('beginResize', m); },
    setManualSize: function (e) { return call('setManualSize', e); },
    setAlwaysOnTop: function (e) { return call('setAlwaysOnTop', e); },
    resizeWindow: function (w, h) { return call('resizeWindow', w, h); },
    resetPosition: function () { return call('resetPosition'); },
    hideWindow: function () { return call('hideWindow'); },
    openSwitcher: function () { return call('openSwitcher'); }
  };
  window.chrome.webview.postMessage({ __ready: true, __agent: 'shim' });
})();
"""


def resource_path(*parts: str) -> Path:
    if getattr(sys, "frozen", False):
        root = Path(getattr(sys, "_MEIPASS"))
    else:
        root = Path(__file__).resolve().parent.parent
    return root.joinpath(*parts)


# ---------------------------------------------------------------- registry --
def _reg_key(name: str):
    """Split 'a/b' into (subkey_path, value_name)."""
    parts = name.split("/")
    if len(parts) > 1:
        return "/".join(parts[:-1]), parts[-1]
    return "", name


def reg_get(name: str, default=None):
    sub, value = _reg_key(name)
    try:
        path = REG_ROOT if not sub else REG_ROOT + "\\" + sub
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
            val, _ = winreg.QueryValueEx(key, value)
        return val
    except OSError:
        return default


def reg_set(name: str, value) -> None:
    sub, key_name = _reg_key(name)
    try:
        path = REG_ROOT if not sub else REG_ROOT + "\\" + sub
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, path) as key:
            if isinstance(value, bool):
                winreg.SetValueEx(key, key_name, 0, winreg.REG_SZ, "true" if value else "false")
            elif isinstance(value, (list, tuple)):
                winreg.SetValueEx(key, key_name, 0, winreg.REG_MULTI_SZ, [str(v) for v in value])
            else:
                winreg.SetValueEx(key, key_name, 0, winreg.REG_SZ, str(value))
    except OSError:
        pass


def reg_list(name: str, default):
    value = reg_get(name, None)
    if value is None:
        return list(default)
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple)):
        return list(default)
    return [str(item) for item in value]


def reg_bool(name: str, default: bool) -> bool:
    value = reg_get(name, None)
    if value is None:
        return default
    return str(value).lower() == "true"


# -------------------------------------------------------------- bridge app --
class WidgetForm(Form):
    WM_NCLBUTTONDOWN = 0x00A1
    HIT_MASK_TO_CODE = {
        1: 10,  # left
        2: 12,  # top
        4: 11,  # right
        8: 15,  # bottom
        3: 13,  # topleft
        6: 14,  # topright
        9: 16,  # bottomleft
        12: 17,  # bottomright
    }

    def __init__(self, controller: "DesktopController", widget_name: str) -> None:
        super().__init__()
        self.controller = controller
        self.widget_name = widget_name
        self._manual_size = reg_bool(f"widgetManualSize/{widget_name}", False)
        self._inited = False
        self._ready = False
        self._web = None

        self.FormBorderStyle = NONE_BORDER
        self.StartPosition = FormStartPosition.Manual
        self.BackColor = Color.Black
        self.TopMost = True
        self.ShowInTaskbar = False
        self.Text = APP_NAME + " · " + MODULES[widget_name][0]
        self.Shown += self._on_shown
        self.Move += self._on_moved
        self.Resize += self._on_resized

        self._web = WebView2()
        self._web.Dock = FILL_DOCK
        self._web.DefaultBackgroundColor = Color.FromArgb(0, 0, 0, 0)
        self.Controls.Add(self._web)
        self._web.CoreWebView2InitializationCompleted += self._on_wv2_init
        self._web.WebMessageReceived += self._on_message

        # geometry restore (registry stores logical coords; WinForms uses physical)
        scale = dpi_scale()
        w, h = INITIAL_SIZES[widget_name]
        stored_size = reg_get(f"widgetSize/{widget_name}", None)
        if self._manual_size and stored_size:
            try:
                w, h = (int(v) for v in stored_size)
            except (TypeError, ValueError, IndexError):
                w, h = INITIAL_SIZES[widget_name]
        self.Size = Size(int(w * scale), int(h * scale))
        stored_pos = reg_get(f"widgetPosition/{widget_name}", None)
        if stored_pos:
            try:
                self.Location = Point(int(int(stored_pos[0]) * scale), int(int(stored_pos[1]) * scale))
            except (TypeError, ValueError, IndexError):
                self.Location = Point(*self.default_position())
        else:
            self.Location = Point(*self.default_position())

    # --- lifecycle ---
    def _on_shown(self, sender, e):
        hwnd = self._hwnd()
        GWL_EXSTYLE = -20
        WS_EX_NOREDIRECTIONBITMAP = 0x00200000
        style = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, style | WS_EX_NOREDIRECTIONBITMAP)
        self._ready = True
        try:
            self._web.EnsureCoreWebView2Async(None)
        except Exception:
            pass

    def _hwnd(self):
        return int(self.Handle.ToInt64())

    def _on_wv2_init(self, sender, args):
        if args.InitializationException is not None:
            return
        cv = self._web.CoreWebView2
        cv.Settings.AreDefaultContextMenusEnabled = False
        cv.Settings.AreDevToolsEnabled = False
        cv.AllowExternalDrop = True
        cv.AddScriptToExecuteOnDocumentCreatedAsync(SHIM_JS)
        cv.SetVirtualHostNameToFolderMapping(
            "app.deskflow.local",
            str(resource_path("desktop-organizer-concepts")),
            CoreWebView2HostResourceAccessKind.Allow,
        )
        query = "?widget=" + self.widget_name + ("&manual=1" if self._manual_size else "")
        cv.Navigate("https://app.deskflow.local/index.html" + query)

    # --- bridge message dispatch (UI thread) ---
    def _on_message(self, sender, args):
        try:
            data = json.loads(args.WebMessageAsJson)
        except Exception:
            return
        if data.get("__ready"):
            return
        msg_id = data.get("id")
        method = data.get("method")
        args_list = data.get("args") or []
        try:
            result = self._dispatch(method, args_list)
        except Exception:
            result = False
        if msg_id is not None:
            self._post(msg_id, result)

    def _post(self, msg_id, result) -> None:
        self._web.CoreWebView2.PostWebMessageAsJson(
            json.dumps({"id": msg_id, "result": result})
        )

    def _dispatch(self, method, args_list):
        c = self.controller
        if method == "openPath":
            return c.open_path(str(args_list[0]))
        if method == "copyFiles":
            return c.copy_files([str(p) for p in args_list[0]])
        if method == "chooseFiles":
            return c.choose_files(self)
        if method == "notify":
            c.notify(str(args_list[0]), str(args_list[1]))
            return True
        if method == "setEnabledModules":
            c.apply_selection([str(m) for m in args_list[0]])
            return True
        if method == "setAutoStart":
            return c.set_auto_start(bool(args_list[0]))
        if method == "beginMove":
            self.begin_system_move()
            return True
        if method == "beginResize":
            self.begin_system_resize(int(args_list[0]))
            return True
        if method == "setManualSize":
            self._manual_size = bool(args_list[0])
            reg_set(f"widgetManualSize/{self.widget_name}", self._manual_size)
            return True
        if method == "setAlwaysOnTop":
            self.TopMost = bool(args_list[0])
            return True
        if method == "resizeWindow":
            self.resize_to_content(int(args_list[0]), int(args_list[1]))
            return True
        if method == "resetPosition":
            self.reset_position()
            return True
        if method == "hideWindow":
            self.Hide()
            c.on_widget_hidden(self.widget_name)
            return True
        if method == "openSwitcher":
            c.show_switcher()
            return True
        return False

    # --- native window ops ---
    def begin_system_move(self) -> None:
        user32.ReleaseCapture()
        user32.SendMessageW(self._hwnd(), self.WM_NCLBUTTONDOWN, 2, 0)  # HTCAPTION

    def begin_system_resize(self, edge_mask: int) -> None:
        code = self.HIT_MASK_TO_CODE.get(edge_mask)
        if code is None:
            return
        self._manual_size = True
        reg_set(f"widgetManualSize/{self.widget_name}", True)
        user32.ReleaseCapture()
        user32.SendMessageW(self._hwnd(), self.WM_NCLBUTTONDOWN, code, 0)

    def resize_to_content(self, width: int, height: int) -> None:
        if self._manual_size:
            return
        scale = dpi_scale()
        screen = Screen.PrimaryScreen.WorkingArea
        w = max(220, min(int(width * scale), screen.Width - 20))
        h = max(70, min(int(height * scale), screen.Height - 20))
        if self.ClientSize.Width != w or self.ClientSize.Height != h:
            self.ClientSize = Size(w, h)
        x = max(screen.X, min(self.Location.X, screen.X + screen.Width - w))
        y = max(screen.Y, min(self.Location.Y, screen.Y + screen.Height - h))
        self.Location = Point(x, y)

    def reset_position(self) -> None:
        self.Location = Point(*self.default_position())

    def default_position(self) -> tuple[int, int]:
        screen = Screen.PrimaryScreen.WorkingArea
        right = screen.X + screen.Width
        bottom = screen.Y + screen.Height
        width, height = self.Width, self.Height
        if self.widget_name == "todo":
            return right - width - 24, screen.Y + 28
        if self.widget_name == "countdown":
            stacked_y = screen.Y + 520
            if stacked_y + height <= bottom - 20:
                return right - width - 30, stacked_y
            return right - width - 430, screen.Y + 40
        return max(screen.X + 24, right - width - 470), max(screen.Y + 30, bottom - height - 36)

    def _on_moved(self, sender, e):
        if not self._ready:
            return
        scale = dpi_scale()
        reg_set(f"widgetPosition/{self.widget_name}",
                [int(self.Location.X / scale), int(self.Location.Y / scale)])

    def _on_resized(self, sender, e):
        if not self._ready or not self._manual_size:
            return
        scale = dpi_scale()
        reg_set(f"widgetSize/{self.widget_name}",
                [int(self.Width / scale), int(self.Height / scale)])


class StartupDialog(Form):
    def __init__(self, selected: list[str], auto_start: bool) -> None:
        super().__init__()
        s = dpi_scale()
        self.Text = "序 · 桌面组件选择"
        self.FormBorderStyle = SysEnum.Parse(FormBorderStyle, "FixedDialog")
        self.StartPosition = FormStartPosition.CenterScreen
        self.MaximizeBox = False
        self.MinimizeBox = False
        self.ClientSize = Size(int(360 * s), int(330 * s))
        self._checks: dict[str, CheckBox] = {}
        font_label = Font("Microsoft YaHei UI", 12, FontStyle.Bold)
        font_ui = Font("Microsoft YaHei UI", 10)

        label = Label()
        label.Text = "今天在桌面上放哪些组件?"
        label.Font = font_label
        label.AutoSize = True
        label.Location = Point(int(24 * s), int(20 * s))
        self.Controls.Add(label)

        y = int(62 * s)
        for name, (label_txt, desc) in MODULES.items():
            check = CheckBox()
            check.Text = f"{label_txt} — {desc}"
            check.Checked = name in selected
            check.AutoSize = True
            check.Location = Point(int(26 * s), y)
            check.Font = font_ui
            self._checks[name] = check
            self.Controls.Add(check)
            y += int(36 * s)

        self._auto = CheckBox()
        self._auto.Text = "开机自动启动"
        self._auto.Checked = auto_start
        self._auto.AutoSize = True
        self._auto.Location = Point(int(26 * s), y + int(4 * s))
        self._auto.Font = font_ui
        self.Controls.Add(self._auto)

        cancel = Button()
        cancel.Text = "取消"
        cancel.Location = Point(int(150 * s), y + int(48 * s))
        cancel.Size = Size(int(88 * s), int(34 * s))
        cancel.Font = font_ui
        cancel.Click += self._on_cancel
        self.Controls.Add(cancel)
        ok = Button()
        ok.Text = "放到桌面上 →"
        ok.Location = Point(int(244 * s), y + int(48 * s))
        ok.Size = Size(int(96 * s), int(34 * s))
        ok.Font = font_ui
        ok.Click += self._on_ok
        self.Controls.Add(ok)
        self.AcceptButton = ok
        self.CancelButton = cancel

    def _on_cancel(self, sender, e):
        self.DialogResult = DialogResult.Cancel

    def _on_ok(self, sender, e):
        self.DialogResult = DialogResult.OK

    def selection(self) -> list[str]:
        return [name for name, check in self._checks.items() if check.Checked]


class DesktopController:
    def __init__(self) -> None:
        self.windows: dict[str, WidgetForm] = {}
        self.tray: NotifyIcon | None = None
        self.quitting = False
        self.module_items: dict[str, ToolStripMenuItem] = {}
        self.webview_data_dir = (
            Path(os.getenv("APPDATA", str(Path.home()))) / "DeskFlow" / "WebView2"
        )
        os.environ["WEBVIEW2_USER_DATA_FOLDER"] = str(self.webview_data_dir)
        scale = dpi_scale()
        if abs(scale - 1.0) > 0.01:
            os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = (
                f"--force-device-scale-factor={scale:.2f}"
            )

        self.build_tray()

    # --- tray ---
    def build_tray(self) -> None:
        menu = ContextMenuStrip()
        item = ToolStripMenuItem("选择桌面组件…")
        item.Click += lambda s, e: self.show_switcher()
        menu.Items.Add(item)
        menu.Items.Add(ToolStripSeparator())
        selected = self.selected_modules()
        for name, (label, _) in MODULES.items():
            mi = ToolStripMenuItem(label)
            mi.CheckOnClick = True
            mi.Checked = name in selected
            mi.Click += lambda s, e, n=name: self.set_widget_visible(n, s.Checked, persist=True)
            self.module_items[name] = mi
            menu.Items.Add(mi)
        menu.Items.Add(ToolStripSeparator())
        quit_item = ToolStripMenuItem("彻底退出")
        quit_item.Click += lambda s, e: self.request_quit()
        menu.Items.Add(quit_item)

        self.tray = NotifyIcon()
        self.tray.Icon = SystemIcons.Application
        self.tray.Text = APP_NAME
        self.tray.ContextMenuStrip = menu
        self.tray.Visible = True
        self.tray.MouseDoubleClick += lambda s, e: self.show_switcher()

    # --- module state ---
    def selected_modules(self) -> list[str]:
        return reg_list("enabledModules", list(MODULES))

    def startup(self) -> None:
        test = os.environ.get("DESKFLOW_TEST_MODULES")
        if test is not None:
            self.apply_selection([name for name in test.split(",") if name in MODULES])
            return
        current = self.selected_modules()
        self.show_switcher()
        if not any(win.Visible for win in self.windows.values()):
            self.apply_selection(self.selected_modules() if self.selected_modules() != current else current)

    def show_switcher(self) -> None:
        dialog = StartupDialog(self.selected_modules(), reg_bool("autoStart", True))
        if dialog.ShowDialog() == DialogResult.OK:
            self.apply_selection(dialog.selection())
            self.set_auto_start(dialog._auto.Checked)

    def apply_selection(self, modules: list[str]) -> None:
        normalized = [name for name in MODULES if name in modules]
        reg_set("enabledModules", normalized)
        for name in MODULES:
            self.set_widget_visible(name, name in normalized, persist=False)

    def set_widget_visible(self, name: str, visible: bool, persist: bool) -> None:
        window = self.windows.get(name)
        if visible and window is None:
            window = WidgetForm(self, name)
            self.windows[name] = window
        if visible:
            if window is not None:
                window.Show()
        elif window is not None:
            window.Hide()
        self.sync_module_actions(name, visible)
        if persist:
            self.persist_enabled()

    def sync_module_actions(self, name: str, visible: bool) -> None:
        item = self.module_items.get(name)
        if item is not None and item.Checked != visible:
            item.Checked = visible

    def on_widget_hidden(self, name: str) -> None:
        self.sync_module_actions(name, False)
        self.persist_enabled()

    def persist_enabled(self) -> None:
        enabled = [name for name, item in self.module_items.items() if item.Checked]
        reg_set("enabledModules", enabled)

    # --- bridge targets ---
    def open_path(self, path: str) -> bool:
        try:
            os.startfile(path)
            return True
        except OSError:
            return False

    def copy_files(self, paths) -> bool:
        existing = [p for p in paths if Path(p).exists()]
        if not existing:
            return False
        try:
            sc = StringCollection()
            for path in existing:
                sc.Add(path)
            Clipboard.SetFileDropList(sc)
            return True
        except Exception:
            return False

    def choose_files(self, owner: Form):
        dialog = OpenFileDialog()
        dialog.Multiselect = True
        dialog.Title = "选择要收纳的文件"
        if dialog.ShowDialog(owner) == DialogResult.OK:
            return list(dialog.FileNames)
        return []

    def notify(self, title: str, body: str) -> None:
        self.tray.ShowBalloonTip(8000, title, body, 1)  # ToolTipIcon.Info

    def set_auto_start(self, enabled: bool) -> bool:
        run_key = r"Software\Microsoft\Windows\CurrentVersion\Run"
        if getattr(sys, "frozen", False):
            command = f'"{Path(sys.executable).resolve()}"'
        else:
            command = f'"{Path(sys.executable).resolve()}" "{Path(__file__).resolve()}"'
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, run_key, 0, winreg.KEY_SET_VALUE) as key:
                if enabled:
                    winreg.SetValueEx(key, "DeskFlow", 0, winreg.REG_SZ, command)
                else:
                    try:
                        winreg.DeleteValue(key, "DeskFlow")
                    except FileNotFoundError:
                        pass
            reg_set("autoStart", enabled)
            return True
        except OSError:
            return False

    def request_quit(self) -> None:
        self.quitting = True
        for window in self.windows.values():
            window.Close()
        self.tray.Visible = False
        Application.Exit()


def main() -> int:
    # single instance guard
    kernel32 = ctypes.windll.kernel32
    mutex = kernel32.CreateMutexW(None, False, "Local\\DeskFlow_v2")
    if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        ctypes.windll.user32.MessageBoxW(0, "DeskFlow 已在运行", APP_NAME, 0x40)
        return 0
    Application.EnableVisualStyles()
    controller = DesktopController()
    controller.startup()
    Application.Run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
