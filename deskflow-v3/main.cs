// DeskFlow v3 — WebView2 shell in C# (.NET Framework 4.8, WinForms).
// Same architecture / functions / design as v2; tiny bundle (~1 MB), lighter host.
using System;
using System.Collections.Generic;
using System.Collections.Specialized;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using Microsoft.Win32;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

namespace DeskFlow
{
    static class Native
    {
        [DllImport("user32.dll")] public static extern bool ReleaseCapture();
        [DllImport("user32.dll")] public static extern IntPtr SendMessageW(IntPtr hWnd, uint msg, IntPtr wParam, IntPtr lParam);
        [DllImport("user32.dll")] public static extern uint GetDpiForSystem();
        [DllImport("kernel32.dll")] public static extern IntPtr CreateMutexW(IntPtr attrs, bool initialOwner, string name);
        [DllImport("kernel32.dll")] public static extern uint GetLastError();
        [DllImport("shcore.dll")] public static extern int SetProcessDpiAwareness(int value);
        [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern IntPtr FindWindowW(string cls, string title);
        [DllImport("user32.dll", EntryPoint = "GetWindow")] public static extern IntPtr GetWindowW(IntPtr hwnd, uint cmd);
        [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr hwnd, IntPtr after, int x, int y, int w, int h, uint flags);
        [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern uint RegisterWindowMessageW(string name);

        public const uint GW_HWNDNEXT = 2;
        public static readonly IntPtr HwndBottom = new IntPtr(1);
        public const uint SWP_NOSIZE = 0x0001;
        public const uint SWP_NOMOVE = 0x0002;
        public const uint SWP_NOACTIVATE = 0x0010;
    }

    static class Settings
    {
        const string Root = @"Software\DeskFlow\DesktopOrganizer";
        public const string AppName = "序 · 桌面效率工具";

        static string KeyPath(string name)
        {
            int slash = name.IndexOf('/');
            if (slash > 0) return Root + @"\" + name.Substring(0, slash);
            return Root;
        }
        static string ValueName(string name)
        {
            int slash = name.IndexOf('/');
            if (slash > 0) return name.Substring(slash + 1);
            return name;
        }

        public static string Get(string name)
        {
            try
            {
                using (RegistryKey key = Registry.CurrentUser.OpenSubKey(KeyPath(name)))
                {
                    if (key == null) return null;
                    object v = key.GetValue(ValueName(name));
                    return v == null ? null : v.ToString();
                }
            }
            catch { return null; }
        }
        public static string[] GetList(string name)
        {
            try
            {
                using (RegistryKey key = Registry.CurrentUser.OpenSubKey(KeyPath(name)))
                {
                    if (key == null) return null;
                    object v = key.GetValue(ValueName(name));
                    string[] sa = v as string[];
                    if (sa != null) return sa;
                    string s = v as string;
                    if (s != null) return new[] { s };
                    return null;
                }
            }
            catch { return null; }
        }
        public static void Set(string name, string value)
        {
            try
            {
                using (RegistryKey key = Registry.CurrentUser.CreateSubKey(KeyPath(name)))
                    key.SetValue(ValueName(name), value);
            }
            catch { }
        }
        public static void SetList(string name, string[] values)
        {
            try
            {
                using (RegistryKey key = Registry.CurrentUser.CreateSubKey(KeyPath(name)))
                    key.SetValue(ValueName(name), values);
            }
            catch { }
        }
    }

    static class Bridge
    {
        public const string Shim = @"(function () {
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
    setDesktopPin: function (e) { return call('setDesktopPin', e); },
    getWidgetState: function () { return call('getWidgetState'); },
    resizeWindow: function (w, h) { return call('resizeWindow', w, h); },
    resetPosition: function () { return call('resetPosition'); },
    hideWindow: function () { return call('hideWindow'); },
    openSwitcher: function () { return call('openSwitcher'); },
    getSettings: function () { return call('getSettings'); }
  };
})();";
    }

    static class AppIcon
    {
        public static readonly Icon Instance = Load();
        static Icon Load()
        {
            try
            {
                string path = Path.Combine(Path.GetDirectoryName(Application.ExecutablePath), "app.ico");
                if (File.Exists(path)) return new Icon(path); // 多尺寸 ico,按系统 DPI 取最佳帧
            }
            catch { }
            return SystemIcons.Application;
        }
    }

    public class WidgetForm : Form
    {
        const uint WM_NCLBUTTONDOWN = 0x00A1;
        static readonly Dictionary<int, int> HitMaskToCode = new Dictionary<int, int>
        {
            { 1, 10 }, { 2, 12 }, { 4, 11 }, { 8, 15 },
            { 3, 13 }, { 6, 14 }, { 9, 16 }, { 12, 17 }
        };

        readonly string name;
        bool manualSize;
        bool pinned;
        bool ready;
        WebView2 web;

        public WidgetForm(string widgetName)
        {
            name = widgetName;
            bool isSettings = name == "settings";
            FormBorderStyle = FormBorderStyle.None;
            StartPosition = FormStartPosition.Manual;
            BackColor = Color.Black;
            TopMost = isSettings; // 组件默认不置顶;桌面钉住时永远在程序窗口下面
            ShowInTaskbar = false;
            Icon = AppIcon.Instance;
            Text = Settings.AppName + " · " + Controller.ModuleTitle(widgetName);
            pinned = !isSettings && Settings.Get("widgetPinned/" + widgetName) != "false";

            double s = DpiScale();
            manualSize = !isSettings && "true" == Settings.Get("widgetManualSize/" + widgetName);
            int w, h;
            if (isSettings) { w = 552; h = 430; }
            else
            {
                string[] storedSize = Settings.GetList("widgetSize/" + widgetName);
                if (manualSize && storedSize != null && storedSize.Length == 2)
                {
                    int.TryParse(storedSize[0], out w);
                    int.TryParse(storedSize[1], out h);
                    if (w < 100) w = Controller.InitialSize(widgetName, 0);
                    if (h < 50) h = Controller.InitialSize(widgetName, 1);
                }
                else { w = Controller.InitialSize(widgetName, 0); h = Controller.InitialSize(widgetName, 1); }
            }
            Size = new Size((int)(w * s), (int)(h * s));

            string[] pos = Settings.GetList("widgetPosition/" + widgetName);
            if (pos != null && pos.Length == 2)
            {
                int x, y;
                if (int.TryParse(pos[0], out x) && int.TryParse(pos[1], out y))
                    Location = new Point((int)(x * s), (int)(y * s));
                else Location = DefaultPosition();
            }
            else Location = DefaultPosition();

            web = new WebView2();
            web.Dock = DockStyle.Fill;
            web.DefaultBackgroundColor = Color.FromArgb(0, 0, 0, 0);
            web.AllowExternalDrop = true;
            Controls.Add(web);
            web.CoreWebView2InitializationCompleted += OnWv2Init;
            web.WebMessageReceived += OnMessage;

            Shown += OnShown;
            Move += OnMoved;
            Resize += OnResized;
            Deactivate += OnDeactivated;
        }

        static double DpiScale()
        {
            try { return Native.GetDpiForSystem() / 96.0; }
            catch { return 1.0; }
        }

        Point DefaultPosition()
        {
            Rectangle area = Screen.PrimaryScreen.WorkingArea;
            int right = area.Right;
            int bottom = area.Bottom;
            int w = Width, h = Height;
            if (name == "settings")
                return new Point(area.Left + Math.Max(0, (area.Width - w) / 2), area.Top + Math.Max(24, (area.Height - h) / 3));
            if (name == "todo") return new Point(right - w - 24, area.Top + 28);
            if (name == "countdown")
            {
                int stacked = area.Top + 520;
                if (stacked + h <= bottom - 20) return new Point(right - w - 30, stacked);
                return new Point(right - w - 430, area.Top + 40);
            }
            return new Point(Math.Max(area.Left + 24, right - w - 470), Math.Max(area.Top + 30, bottom - h - 36));
        }

        const int WS_EX_NOREDIRECTIONBITMAP = 0x00200000;
        protected override CreateParams CreateParams
        {
            get
            {
                CreateParams cp = base.CreateParams;
                cp.ExStyle |= WS_EX_NOREDIRECTIONBITMAP;
                return cp;
            }
        }

        void OnShown(object sender, EventArgs e)
        {
            ready = true;
            ApplyDesktopPin();
            try { web.EnsureCoreWebView2Async(null); }
            catch { }
        }

        // ---- 桌面钉住 ----
        // 顶层窗口 + z 序压到桌面(Progman)之上、所有程序之下。
        // 不用 SetParent:挂成桌面子窗口后 WebView2 的 alpha 合成会失效,透明处发黑。
        static readonly uint TaskbarCreatedMsg = Native.RegisterWindowMessageW("TaskbarCreated");

        void ApplyDesktopPin()
        {
            if (name == "settings") return;
            if (pinned) PinToDesktop();
        }

        void PinToDesktop()
        {
            if (!IsHandleCreated) return;
            TopMost = false;
            try
            {
                IntPtr progman = Native.FindWindowW("Progman", null);
                if (progman == IntPtr.Zero) return;
                IntPtr above = Native.GetWindowW(progman, Native.GW_HWNDNEXT); // 紧贴 Progman 之上的窗口
                IntPtr after = above != IntPtr.Zero ? above : Native.HwndBottom;
                Native.SetWindowPos(Handle, after, 0, 0, 0, 0,
                    Native.SWP_NOMOVE | Native.SWP_NOSIZE | Native.SWP_NOACTIVATE);
            }
            catch { } // 钉住失败不影响组件本身
        }

        public void SetDesktopPin(bool value)
        {
            if (name == "settings") return;
            pinned = value;
            Settings.Set("widgetPinned/" + name, pinned ? "true" : "false");
            ApplyDesktopPin();
        }

        public Dictionary<string, object> GetWidgetState()
        {
            Dictionary<string, object> state = new Dictionary<string, object>();
            state["pinned"] = pinned;
            return state;
        }

        protected override void WndProc(ref Message m)
        {
            // explorer 重启后桌面重建,重新压回桌面层
            if (TaskbarCreatedMsg != 0 && m.Msg == (int)TaskbarCreatedMsg && pinned && IsHandleCreated)
            {
                try { PinToDesktop(); } catch { }
            }
            base.WndProc(ref m);
        }

        void OnDeactivated(object sender, EventArgs e)
        {
            // 点击组件会临时浮起(便于交互);切去别的窗口就沉回桌面层
            if (pinned && ready) PinToDesktop();
        }

        void OnWv2Init(object sender, CoreWebView2InitializationCompletedEventArgs e)
        {
            if (web.CoreWebView2 == null) return;
            CoreWebView2 cv = web.CoreWebView2;
            cv.Settings.AreDefaultContextMenusEnabled = false;
            cv.Settings.AreDevToolsEnabled = false;
            // AllowExternalDrop defaults to true on the WinForms control
            cv.AddScriptToExecuteOnDocumentCreatedAsync(Bridge.Shim);
            cv.SetVirtualHostNameToFolderMapping("app.deskflow.local", Controller.ConceptsPath(), CoreWebView2HostResourceAccessKind.Allow);
            string query = "?widget=" + name;
            if (manualSize) query += "&manual=1";
            cv.Navigate("https://app.deskflow.local/index.html" + query);
        }

        void OnMessage(object sender, CoreWebView2WebMessageReceivedEventArgs e)
        {
            Dictionary<string, object> data;
            try
            {
                var ser = new JavaScriptSerializer();
                data = ser.Deserialize<Dictionary<string, object>>(e.WebMessageAsJson);
            }
            catch { return; }
            if (data == null) return;
            int id = 0;
            object idObj;
            if (data.TryGetValue("id", out idObj)) int.TryParse(idObj.ToString(), out id);
            object methodObj;
            string method = data.TryGetValue("method", out methodObj) ? methodObj.ToString() : null;
            if (method == null) return;
            object argsObj;
            object[] args = new object[0];
            if (data.TryGetValue("args", out argsObj))
            {
                // JavaScriptSerializer yields Collection<object> (not object[]) for nested JSON arrays
                System.Collections.IEnumerable seq = argsObj as System.Collections.IEnumerable;
                if (seq != null && !(argsObj is string))
                {
                    List<object> list = new List<object>();
                    foreach (object o in seq) list.Add(o);
                    args = list.ToArray();
                }
            }
            object result = Dispatch(method, args);
            if (Environment.GetEnvironmentVariable("DESKFLOW_DEBUG") == "1")
            {
                StringBuilder dbg = new StringBuilder(DateTime.Now.ToString("HH:mm:ss.fff")).Append(' ').Append(name).Append(' ').Append(method).Append(" raw=").Append(e.WebMessageAsJson).Append('\n');
                File.AppendAllText(Path.Combine(Path.GetTempPath(), "deskflow-debug.log"), dbg.ToString());
            }
            if (id != 0)
                web.CoreWebView2.PostWebMessageAsJson("{\"id\":" + id + ",\"result\":" + ToJson(result) + "}");
        }

        // minimal JSON writer: bool / number / string / enumerable / dictionary
        static string ToJson(object value)
        {
            if (value == null) return "null";
            if (value is bool) return (bool)value ? "true" : "false";
            if (value is int || value is long || value is double)
                return Convert.ToString(value, System.Globalization.CultureInfo.InvariantCulture);
            string text = value as string;
            if (text != null)
            {
                StringBuilder sb = new StringBuilder("\"");
                foreach (char ch in text)
                {
                    if (ch == '"' || ch == '\\') { sb.Append('\\'); sb.Append(ch); }
                    else if (ch == '\n') sb.Append("\\n");
                    else if (ch == '\r') sb.Append("\\r");
                    else if (ch == '\t') sb.Append("\\t");
                    else if (ch < ' ') sb.Append("\\u").Append(((int)ch).ToString("x4"));
                    else sb.Append(ch);
                }
                return sb.Append('"').ToString();
            }
            IDictionary<string, object> dict = value as IDictionary<string, object>;
            if (dict != null)
            {
                StringBuilder sb = new StringBuilder("{");
                bool first = true;
                foreach (KeyValuePair<string, object> kv in dict)
                {
                    if (!first) sb.Append(',');
                    first = false;
                    sb.Append(ToJson(kv.Key)).Append(':').Append(ToJson(kv.Value));
                }
                return sb.Append('}').ToString();
            }
            System.Collections.IEnumerable list = value as System.Collections.IEnumerable;
            if (list != null)
            {
                StringBuilder sb = new StringBuilder("[");
                bool first = true;
                foreach (object item in list)
                {
                    if (!first) sb.Append(',');
                    first = false;
                    sb.Append(ToJson(item));
                }
                return sb.Append(']').ToString();
            }
            return ToJson(value.ToString());
        }

        object Dispatch(string method, object[] args)
        {
            Controller c = Controller.Instance;
            switch (method)
            {
                case "openPath": return c.OpenPath(args.Length > 0 ? args[0].ToString() : "");
                case "copyFiles":
                    {
                        List<string> paths = new List<string>();
                        System.Collections.IEnumerable copied = args.Length > 0 ? args[0] as System.Collections.IEnumerable : null;
                        if (copied != null && !(args[0] is string))
                            foreach (object o in copied) paths.Add(o.ToString());
                        return c.CopyFiles(paths.ToArray());
                    }
                case "chooseFiles": return c.ChooseFiles(this);
                case "notify":
                    c.Notify(args.Length > 0 ? args[0].ToString() : "", args.Length > 1 ? args[1].ToString() : "");
                    return true;
                case "setEnabledModules":
                    {
                        List<string> m = new List<string>();
                        System.Collections.IEnumerable enabled = args.Length > 0 ? args[0] as System.Collections.IEnumerable : null;
                        if (enabled != null && !(args[0] is string))
                            foreach (object o in enabled) m.Add(o.ToString());
                        c.ApplySelection(m.ToArray());
                        return true;
                    }
                case "setAutoStart":
                    return c.SetAutoStart(args.Length > 0 && args[0].ToString() == "True");
                case "beginMove": BeginSystemMove(); return true;
                case "beginResize": BeginSystemResize(args.Length > 0 ? int.Parse(args[0].ToString()) : 0); return true;
                case "setManualSize":
                    manualSize = args.Length > 0 && args[0].ToString() == "True";
                    Settings.Set("widgetManualSize/" + name, manualSize ? "true" : "false");
                    return true;
                case "setAlwaysOnTop":
                    TopMost = args.Length > 0 && args[0].ToString() == "True";
                    return true;
                case "setDesktopPin":
                    SetDesktopPin(args.Length > 0 && args[0].ToString() == "True");
                    return true;
                case "getWidgetState":
                    return GetWidgetState();
                case "resizeWindow":
                    ResizeToContent(args.Length > 0 ? int.Parse(args[0].ToString()) : 0, args.Length > 1 ? int.Parse(args[1].ToString()) : 0);
                    return true;
                case "resetPosition": Location = DefaultPosition(); return true;
                case "hideWindow":
                    Hide();
                    if (name != "settings") c.OnWidgetHidden(name);
                    return true;
                case "openSwitcher": c.ShowSettings(); return true;
                case "getSettings": return c.GetSettings();
            }
            return false;
        }

        void BeginSystemMove()
        {
            Native.ReleaseCapture();
            Native.SendMessageW(Handle, WM_NCLBUTTONDOWN, (IntPtr)2, IntPtr.Zero);
        }
        void BeginSystemResize(int mask)
        {
            int code;
            if (!HitMaskToCode.TryGetValue(mask, out code)) return;
            manualSize = true;
            Settings.Set("widgetManualSize/" + name, "true");
            Native.ReleaseCapture();
            Native.SendMessageW(Handle, WM_NCLBUTTONDOWN, (IntPtr)code, IntPtr.Zero);
        }
        void ResizeToContent(int width, int height)
        {
            if (manualSize) return;
            double s = DpiScale();
            Rectangle area = Screen.PrimaryScreen.WorkingArea;
            bool isSettings = name == "settings";
            int minW = isSettings ? 380 : 220;
            int minH = isSettings ? 320 : 70;
            int w = Math.Max(minW, Math.Min((int)(width * s), area.Width - 20));
            int h = Math.Max(minH, Math.Min((int)(height * s), area.Height - 20));
            if (ClientSize.Width != w || ClientSize.Height != h) ClientSize = new Size(w, h);
            int x = Math.Max(area.Left, Math.Min(Location.X, area.Right - w));
            int y = Math.Max(area.Top, Math.Min(Location.Y, area.Bottom - h));
            Location = new Point(x, y);
        }
        void OnMoved(object sender, EventArgs e)
        {
            if (!ready) return;
            double s = DpiScale();
            Settings.SetList("widgetPosition/" + name, new[] { ((int)(Location.X / s)).ToString(), ((int)(Location.Y / s)).ToString() });
        }
        void OnResized(object sender, EventArgs e)
        {
            if (!ready || !manualSize) return;
            double s = DpiScale();
            Settings.SetList("widgetSize/" + name, new[] { ((int)(Width / s)).ToString(), ((int)(Height / s)).ToString() });
        }
    }

    // workaround: expose scale for dialog (WidgetForm.DpiScale is private)
    static class WidgetForm_Helper
    {
        public static double Scale()
        {
            try { return Native.GetDpiForSystem() / 96.0; }
            catch { return 1.0; }
        }
    }

    public class Controller
    {
        public static Controller Instance;
        public readonly Dictionary<string, WidgetForm> Windows = new Dictionary<string, WidgetForm>();
        readonly Dictionary<string, ToolStripMenuItem> moduleItems = new Dictionary<string, ToolStripMenuItem>();
        NotifyIcon tray;
        bool quitting;

        static readonly string[][] moduleDefs = new string[][]
        {
            new[] { "todo", "今日待办", "任务、周期和到点提醒" },
            new[] { "countdown", "倒计时", "截止时间与紧急提醒" },
            new[] { "files", "文件收纳", "本地文件引用与快速打开" }
        };
        static readonly int[][] initialSizes = new int[][]
        {
            new[] { 390, 470 }, new[] { 330, 500 }, new[] { 460, 350 }
        };

        public static IEnumerable<KeyValuePair<string, string[]>> Modules()
        {
            for (int i = 0; i < moduleDefs.Length; i++)
                yield return new KeyValuePair<string, string[]>(moduleDefs[i][0], new[] { moduleDefs[i][1], moduleDefs[i][2] });
        }
        public static string ModuleTitle(string name)
        {
            if (name == "settings") return "设置";
            for (int i = 0; i < moduleDefs.Length; i++)
                if (moduleDefs[i][0] == name) return moduleDefs[i][1];
            return name;
        }
        public static int InitialSize(string name, int idx)
        {
            for (int i = 0; i < moduleDefs.Length; i++)
                if (moduleDefs[i][0] == name) return initialSizes[i][idx];
            return 350;
        }
        public static string ConceptsPath()
        {
            string dir = Path.GetDirectoryName(Application.ExecutablePath);
            string local = Path.Combine(dir, "desktop-organizer-concepts");
            if (Directory.Exists(local)) return local;
            return Path.Combine(Path.GetDirectoryName(dir), "desktop-organizer-concepts");
        }

        public Controller()
        {
            Instance = this;
            string dataDir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "DeskFlow", "WebView2");
            Environment.SetEnvironmentVariable("WEBVIEW2_USER_DATA_FOLDER", dataDir);
            List<string> flags = new List<string>();
            double s = WidgetForm_Helper.Scale();
            if (Math.Abs(s - 1.0) > 0.01) flags.Add("--force-device-scale-factor=" + s.ToString("0.00"));
            // memory: drop GPU process, crashpad, background networking (widget app needs none of them)
            flags.Add("--disable-crashpad");
            flags.Add("--disable-background-networking");
            flags.Add("--disable-sync");
            flags.Add("--disable-component-update");
            flags.Add("--no-first-run");
            flags.Add("--no-default-browser-check");
            flags.Add("--disable-features=msSmartScreenProtection");
            flags.Add("--js-flags=--max-old-space-size=96");
            Environment.SetEnvironmentVariable("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", string.Join(" ", flags.ToArray()));
            BuildTray();
        }

        public string[] SelectedModules()
        {
            string[] v = Settings.GetList("enabledModules");
            if (v == null || v.Length == 0)
            {
                List<string> all = new List<string>();
                foreach (KeyValuePair<string, string[]> kv in Modules()) all.Add(kv.Key);
                return all.ToArray();
            }
            return v;
        }

        void BuildTray()
        {
            ContextMenuStrip menu = new ContextMenuStrip();
            ToolStripMenuItem settings = new ToolStripMenuItem("设置…");
            settings.Font = new Font(menu.Font, FontStyle.Bold);
            settings.Click += delegate { ShowSettings(); };
            menu.Items.Add(settings);
            menu.Items.Add(new ToolStripSeparator());
            string[] selected = SelectedModules();
            foreach (KeyValuePair<string, string[]> kv in Modules())
            {
                ToolStripMenuItem mi = new ToolStripMenuItem(kv.Value[0]);
                mi.CheckOnClick = true;
                mi.Checked = Array.IndexOf(selected, kv.Key) >= 0;
                string moduleName = kv.Key;
                mi.Click += delegate(object sender, EventArgs e) { SetWidgetVisible(moduleName, ((ToolStripMenuItem)sender).Checked, true); };
                moduleItems[kv.Key] = mi;
                menu.Items.Add(mi);
            }
            menu.Items.Add(new ToolStripSeparator());
            ToolStripMenuItem quit = new ToolStripMenuItem("彻底退出");
            quit.Click += delegate { RequestQuit(); };
            menu.Items.Add(quit);

            tray = new NotifyIcon();
            tray.Icon = AppIcon.Instance;
            tray.Text = Settings.AppName;
            tray.ContextMenuStrip = menu;
            tray.Visible = true;
            tray.MouseDoubleClick += delegate { ShowSettings(); };
        }

        public void Startup()
        {
            string test = Environment.GetEnvironmentVariable("DESKFLOW_TEST_MODULES");
            if (!string.IsNullOrEmpty(test))
            {
                List<string> list = new List<string>();
                foreach (string m in test.Split(','))
                    foreach (KeyValuePair<string, string[]> kv in Modules())
                        if (kv.Key == m) list.Add(m);
                ApplySelection(list.ToArray());
                return;
            }
            ApplySelection(SelectedModules());
            ShowSettings();
        }

        public void ShowSettings()
        {
            WidgetForm window;
            if (!Windows.TryGetValue("settings", out window))
            {
                window = new WidgetForm("settings");
                Windows["settings"] = window;
            }
            window.Show();
            window.Activate();
        }

        public Dictionary<string, object> GetSettings()
        {
            Dictionary<string, object> state = new Dictionary<string, object>();
            state["modules"] = SelectedModules();
            state["autoStart"] = Settings.Get("autoStart") != "false";
            return state;
        }

        public void ApplySelection(string[] modules)
        {
            List<string> normalized = new List<string>();
            foreach (KeyValuePair<string, string[]> kv in Modules())
                if (Array.IndexOf(modules, kv.Key) >= 0) normalized.Add(kv.Key);
            Settings.SetList("enabledModules", normalized.ToArray());
            foreach (KeyValuePair<string, string[]> kv in Modules())
                SetWidgetVisible(kv.Key, Array.IndexOf(normalized.ToArray(), kv.Key) >= 0, false);
        }

        public void SetWidgetVisible(string name, bool visible, bool persist)
        {
            WidgetForm window;
            bool exists = Windows.TryGetValue(name, out window);
            if (visible && !exists)
            {
                window = new WidgetForm(name);
                Windows[name] = window;
            }
            if (visible) { if (window != null) window.Show(); }
            else if (window != null) window.Hide();
            ToolStripMenuItem mi;
            if (moduleItems.TryGetValue(name, out mi) && mi.Checked != visible) mi.Checked = visible;
            if (persist) PersistEnabled();
        }

        public void OnWidgetHidden(string name)
        {
            ToolStripMenuItem mi;
            if (moduleItems.TryGetValue(name, out mi) && mi.Checked) mi.Checked = false;
            PersistEnabled();
        }

        void PersistEnabled()
        {
            List<string> list = new List<string>();
            foreach (KeyValuePair<string, ToolStripMenuItem> kv in moduleItems)
                if (kv.Value.Checked) list.Add(kv.Key);
            Settings.SetList("enabledModules", list.ToArray());
        }

        // ---- bridge targets ----
        public bool OpenPath(string path)
        {
            try { Process.Start(path); return true; }
            catch { return false; }
        }
        public bool CopyFiles(string[] paths)
        {
            StringCollection sc = new StringCollection();
            foreach (string p in paths) if (File.Exists(p)) sc.Add(p);
            if (sc.Count == 0) return false;
            try { Clipboard.SetFileDropList(sc); return true; }
            catch { return false; }
        }
        public string[] ChooseFiles(Form owner)
        {
            OpenFileDialog dlg = new OpenFileDialog();
            dlg.Multiselect = true;
            dlg.Title = "选择要收纳的文件";
            if (dlg.ShowDialog(owner) == DialogResult.OK) return dlg.FileNames;
            return new string[0];
        }
        public void Notify(string title, string body)
        {
            tray.ShowBalloonTip(8000, title, body, ToolTipIcon.Info);
        }
        public bool SetAutoStart(bool enabled)
        {
            try
            {
                using (RegistryKey key = Registry.CurrentUser.OpenSubKey(@"Software\Microsoft\Windows\CurrentVersion\Run", true))
                {
                    if (enabled) key.SetValue("DeskFlow", "\"" + Application.ExecutablePath + "\"");
                    else key.DeleteValue("DeskFlow", false);
                }
                Settings.Set("autoStart", enabled ? "true" : "false");
                return true;
            }
            catch { return false; }
        }
        void RequestQuit()
        {
            quitting = true;
            foreach (WidgetForm w in Windows.Values) w.Close();
            tray.Visible = false;
            Application.Exit();
        }
    }

    static class Program
    {
        [STAThread]
        static void Main()
        {
            IntPtr mutex = Native.CreateMutexW(IntPtr.Zero, true, "Local\\DeskFlow_v3");
            if (Native.GetLastError() == 183)
            {
                MessageBox.Show("DeskFlow 已在运行", Settings.AppName);
                return;
            }
            try { Native.SetProcessDpiAwareness(2); } catch { }
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Controller c = new Controller();
            c.Startup();
            Application.Run();
        }
    }
}
