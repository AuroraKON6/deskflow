# -*- coding: utf-8 -*-
"""Phase 0 spike v2: transparent frameless WebView2 window hosting index.html?widget=todo."""
import ctypes
import datetime
import json
import os
import sys
import threading
from pathlib import Path

V2 = Path(__file__).resolve().parent
CONCEPTS = V2.parent / "desktop-organizer-concepts"
WV2LIB = V2 / ".venv" / "Lib" / "site-packages" / "webview" / "lib"
NATIVE = WV2LIB / "runtimes" / "win-x64" / "native"
LOG = V2 / "spike1.log"

os.environ["PATH"] = str(NATIVE) + os.pathsep + os.environ.get("PATH", "")

# STA COM for WinForms/WebView2 UI thread
ctypes.windll.ole32.CoInitializeEx(None, 0x2)  # COINIT_APARTMENTTHREADED
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    ctypes.windll.user32.SetProcessDPIAware()

import clr  # noqa: E402

clr.AddReference(str(WV2LIB / "Microsoft.Web.WebView2.Core.dll"))
clr.AddReference(str(WV2LIB / "Microsoft.Web.WebView2.WinForms.dll"))
clr.AddReference("System.Drawing")
clr.AddReference("System.Windows.Forms")

from Microsoft.Web.WebView2.WinForms import WebView2  # noqa: E402
from Microsoft.Web.WebView2.Core import (  # noqa: E402
    CoreWebView2Environment,
    CoreWebView2HostResourceAccessKind,
)
from System.Windows.Forms import (  # noqa: E402
    Application,
    DockStyle,
    Form,
    FormBorderStyle,
    FormStartPosition,
    Screen,
)
from System import Enum as SysEnum  # noqa: E402
from System.Drawing import Color, Point, Size  # noqa: E402

user32 = ctypes.windll.user32

NONE_BORDER = SysEnum.Parse(FormBorderStyle, "None")
NONE_DOCK = SysEnum.Parse(DockStyle, "None")

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
  window.addEventListener('DOMContentLoaded', function () {
    window.chrome.webview.postMessage({ __dom: document.documentElement.dataset.desktopWidget });
  });
})();
"""


def log(msg):
    line = "[{}] {}".format(datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3], msg)
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def hwnd_int(handle):
    try:
        return int(handle.ToInt64())
    except Exception:
        return int(handle)


class MainForm(Form):
    def __init__(self):
        super().__init__()
        self._inited = False
        self.FormBorderStyle = NONE_BORDER
        self.StartPosition = FormStartPosition.Manual
        self.Location = Point(140, 120)
        self.Size = Size(420, 540)
        self.BackColor = Color.Black
        self.TopMost = True
        self.ShowInTaskbar = False
        self.Text = "DeskFlow spike"
        self.Shown += self._on_shown

        self.web = WebView2()
        self.web.Dock = NONE_DOCK  # will be set Fill in _on_shown via layout
        self.web.Dock = SysEnum.Parse(DockStyle, "Fill")
        self.web.DefaultBackgroundColor = Color.FromArgb(0, 0, 0, 0)
        self.Controls.Add(self.web)
        self.web.CoreWebView2InitializationCompleted += self._on_wv2_init
        self.web.WebMessageReceived += self._on_message

        self._poll = threading.Timer(2.0, self._poll_loop)
        self._poll.start()

    def _poll_loop(self):
        try:
            self._poll_state()
        except Exception as exc:
            log("poll_loop error: {!r}".format(exc))
        if not self._inited:
            self._poll = threading.Timer(2.0, self._poll_loop)
            self._poll.start()

    def _on_shown(self, sender, e):
        hwnd = hwnd_int(self.Handle)
        GWL_EXSTYLE = -20
        WS_EX_NOREDIRECTIONBITMAP = 0x00200000
        style = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, style | WS_EX_NOREDIRECTIONBITMAP)
        log("Shown event: applied WS_EX_NOREDIRECTIONBITMAP hwnd=0x{:x}".format(hwnd))
        try:
            self.web.EnsureCoreWebView2Async(None)
            log("EnsureCoreWebView2Async called")
        except Exception as exc:
            log("EnsureCoreWebView2Async error: {!r}".format(exc))

    def _on_wv2_init(self, sender, args):
        log("CoreWebView2InitializationCompleted fired; exc={}".format(args.InitializationException))
        self._setup_webview()

    def _poll_state(self):
        try:
            cv = self.web.CoreWebView2
            if cv is not None:
                self._setup_webview()
            else:
                log("poll: CoreWebView2 is None (not initialized)")
        except Exception as exc:
            log("poll CoreWebView2 error: {!r}".format(exc))

    def _setup_webview(self):
        if self._inited:
            return
        self._inited = True
        try:
            cv = self.web.CoreWebView2
            log("CoreWebView2 ready; browser={}".format(cv.Environment.BrowserVersionString))
            cv.Settings.AreDefaultContextMenusEnabled = False
            cv.Settings.AreDevToolsEnabled = False
            cv.AddScriptToExecuteOnDocumentCreatedAsync(SHIM_JS)
            cv.SetVirtualHostNameToFolderMapping(
                "app.deskflow.local",
                str(CONCEPTS),
                CoreWebView2HostResourceAccessKind.Allow,
            )
            cv.Navigate("https://app.deskflow.local/index.html?widget=todo")
            log("navigate sent to todo widget")
        except Exception as exc:
            log("setup_webview exception: {!r}".format(exc))

    def _on_message(self, sender, args):
        try:
            raw = args.WebMessageAsJson
            data = json.loads(raw)
        except Exception as exc:
            try:
                raw = args.TryGetWebMessageAsString()
                data = json.loads(raw)
            except Exception as exc2:
                log("message parse error: {!r} / {!r}".format(exc, exc2))
                return
        if data.get("__ready"):
            log("SHIM READY from page")
            return
        if data.get("__dom"):
            log("page DOM ready, data-desktop-widget=" + str(data.get("__dom")))
            return
        method = data.get("method")
        args_ = data.get("args") or []
        if method == "resizeWindow":
            self.resize_to_content(int(args_[0]), int(args_[1]))
            self.post(method, data.get("id"), True)
        elif method == "beginMove":
            self.begin_system_move()
            self.post(method, data.get("id"), True)
        elif method == "notify":
            log("notify: {} / {}".format(args_[0], args_[1]))
            self.post(method, data.get("id"), True)
        else:
            log("bridge call: {} {}".format(method, args_))
            self.post(method, data.get("id"), True)

    def post(self, method, msg_id, result):
        self.web.CoreWebView2.PostWebMessageAsJson(
            json.dumps({"id": msg_id, "result": result, "method": method})
        )

    def resize_to_content(self, width, height):
        screen = Screen.PrimaryScreen.WorkingArea
        w = max(220, min(int(width), screen.Width - 20))
        h = max(70, min(int(height), screen.Height - 20))
        if self.ClientSize.Width != w or self.ClientSize.Height != h:
            self.ClientSize = Size(w, h)
            log("resized to {}x{}".format(w, h))
        x = max(screen.X, min(self.Location.X, screen.X + screen.Width - w))
        y = max(screen.Y, min(self.Location.Y, screen.Y + screen.Height - h))
        if self.Location.X != x or self.Location.Y != y:
            self.Location = Point(x, y)

    def begin_system_move(self):
        hwnd = hwnd_int(self.Handle)
        WM_NCLBUTTONDOWN = 0x00A1
        HTCAPTION = 2
        user32.ReleaseCapture()
        user32.SendMessageW(hwnd, WM_NCLBUTTONDOWN, HTCAPTION, 0)
        log("begin_system_move sent")


def main():
    with open(LOG, "w", encoding="utf-8") as fh:
        fh.write("")
    log("spike1 v2 start, concepts exists={}".format(CONCEPTS.exists()))
    Application.EnableVisualStyles()
    global form
    form = MainForm()
    log("MainForm constructed")
    form.Show()
    log("form.Show() done")
    threading.Timer(150.0, Application.Exit).start()
    Application.Run()
    log("spike1 exit")


if __name__ == "__main__":
    main()
