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
    resizeWindow: function (w, h) { return call('resizeWindow', w, h); },
    resetPosition: function () { return call('resetPosition'); },
    hideWindow: function () { return call('hideWindow'); },
    openSwitcher: function () { return call('openSwitcher'); }
  };
})();";
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
        bool ready;
        WebView2 web;

        public WidgetForm(string widgetName)
        {
            name = widgetName;
            FormBorderStyle = FormBorderStyle.None;
            StartPosition = FormStartPosition.Manual;
            BackColor = Color.Black;
            TopMost = true;
            ShowInTaskbar = false;
            Text = Settings.AppName + " · " + Controller.ModuleTitle(widgetName);

            double s = DpiScale();
            manualSize = "true" == Settings.Get("widgetManualSize/" + widgetName);
            int w, h;
            string[] storedSize = Settings.GetList("widgetSize/" + widgetName);
            if (manualSize && storedSize != null && storedSize.Length == 2)
            {
                int.TryParse(storedSize[0], out w);
                int.TryParse(storedSize[1], out h);
                if (w < 100) w = Controller.InitialSize(widgetName, 0);
                if (h < 50) h = Controller.InitialSize(widgetName, 1);
            }
            else { w = Controller.InitialSize(widgetName, 0); h = Controller.InitialSize(widgetName, 1); }
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
            if (name == "todo") return new Point(right - w - 24, area.Top + 28);
            if (name == "countdown")
            {
                int stacked = area.Top + 520;
                if (stacked + h <= bottom - 20) return new Point(right - w - 30, stacked);
                return new Point(right - w - 430, area.Top + 40);
            }
            return new Point(Math.Max(area.Left + 24, right - w - 470), Math.Max(area.Top + 30, bottom - h - 36));
        }

        void OnShown(object sender, EventArgs e)
        {
            IntPtr hwnd = Handle;
            const int GWL_EXSTYLE = -20;
            const int WS_EX_NOREDIRECTIONBITMAP = 0x00200000;
            int style = GetWindowLong(hwnd, GWL_EXSTYLE);
            SetWindowLong(hwnd, GWL_EXSTYLE, style | WS_EX_NOREDIRECTIONBITMAP);
            ready = true;
            try { web.EnsureCoreWebView2Async(null); }
            catch { }
        }
        [DllImport("user32.dll")] static extern int GetWindowLong(IntPtr h, int idx);
        [DllImport("user32.dll")] static extern int SetWindowLong(IntPtr h, int idx, int val);

        void OnWv2Init(object sender, CoreWebView2InitializationCompletedEventArgs e)
        {
            if (web.CoreWebView2 == null) return;
            CoreWebView2 cv = web.CoreWebView2;
            cv.Settings.AreDefaultContextMenusEnabled = false;
            cv.Settings.AreDevToolsEnabled = false;
            // AllowExternalDrop defaults to true on the WinForms control
            cv.AddScriptToExecuteOnDocumentCreatedAsync(Bridge.Shim);
            cv.SetVirtualHostNameToFolderMapping("app.deskflow.local", Controller.ConceptsPath(), CoreWebView2HostResourceAccessKind.Allow);
            cv.Navigate("https://app.deskflow.local/index.html?widget=" + name + (manualSize ? "&manual=1" : ""));
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
            object[] args = data.TryGetValue("args", out argsObj) && argsObj is object[] ? (object[])argsObj : new object[0];
            object result = Dispatch(method, args);
            if (id != 0)
                web.CoreWebView2.PostWebMessageAsJson("{\"id\":" + id + ",\"result\":" + (result is bool ? (bool)result ? "true" : "false" : "true") + "}");
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
                        if (args.Length > 0 && args[0] is object[])
                            foreach (object o in (object[])args[0]) paths.Add(o.ToString());
                        return c.CopyFiles(paths.ToArray());
                    }
                case "chooseFiles": return c.ChooseFiles(this);
                case "notify":
                    c.Notify(args.Length > 0 ? args[0].ToString() : "", args.Length > 1 ? args[1].ToString() : "");
                    return true;
                case "setEnabledModules":
                    {
                        List<string> m = new List<string>();
                        if (args.Length > 0 && args[0] is object[])
                            foreach (object o in (object[])args[0]) m.Add(o.ToString());
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
                case "resizeWindow":
                    ResizeToContent(args.Length > 0 ? int.Parse(args[0].ToString()) : 0, args.Length > 1 ? int.Parse(args[1].ToString()) : 0);
                    return true;
                case "resetPosition": Location = DefaultPosition(); return true;
                case "hideWindow":
                    Hide();
                    c.OnWidgetHidden(name);
                    return true;
                case "openSwitcher": c.ShowSwitcher(); return true;
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
            int w = Math.Max(220, Math.Min((int)(width * s), area.Width - 20));
            int h = Math.Max(70, Math.Min((int)(height * s), area.Height - 20));
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

    public class StartupDialog : Form
    {
        readonly Dictionary<string, CheckBox> checks = new Dictionary<string, CheckBox>();
        CheckBox autoBox;

        public StartupDialog(string[] selected, bool autoStart)
        {
            double s = WidgetForm_Helper.Scale();
            Text = "序 · 桌面组件选择";
            FormBorderStyle = FormBorderStyle.FixedDialog;
            StartPosition = FormStartPosition.CenterScreen;
            MaximizeBox = false;
            MinimizeBox = false;
            ClientSize = new Size((int)(360 * s), (int)(330 * s));
            Font ui = new Font("Microsoft YaHei UI", 10);

            Label label = new Label();
            label.Text = "今天在桌面上放哪些组件?";
            label.Font = new Font("Microsoft YaHei UI", 12, FontStyle.Bold);
            label.AutoSize = true;
            label.Location = new Point((int)(24 * s), (int)(20 * s));
            Controls.Add(label);

            int y = (int)(62 * s);
            foreach (KeyValuePair<string, string[]> kv in Controller.Modules())
            {
                CheckBox cb = new CheckBox();
                cb.Text = kv.Value[0] + " — " + kv.Value[1];
                cb.Checked = Array.IndexOf(selected, kv.Key) >= 0;
                cb.AutoSize = true;
                cb.Location = new Point((int)(26 * s), y);
                cb.Font = ui;
                checks[kv.Key] = cb;
                Controls.Add(cb);
                y += (int)(36 * s);
            }
            autoBox = new CheckBox();
            autoBox.Text = "开机自动启动";
            autoBox.Checked = autoStart;
            autoBox.AutoSize = true;
            autoBox.Location = new Point((int)(26 * s), y + (int)(4 * s));
            autoBox.Font = ui;
            Controls.Add(autoBox);

            Button cancel = new Button();
            cancel.Text = "取消";
            cancel.Location = new Point((int)(150 * s), y + (int)(48 * s));
            cancel.Size = new Size((int)(88 * s), (int)(34 * s));
            cancel.Font = ui;
            cancel.Click += delegate { DialogResult = DialogResult.Cancel; };
            Controls.Add(cancel);
            Button ok = new Button();
            ok.Text = "放到桌面上 →";
            ok.Location = new Point((int)(244 * s), y + (int)(48 * s));
            ok.Size = new Size((int)(96 * s), (int)(34 * s));
            ok.Font = ui;
            ok.Click += delegate { DialogResult = DialogResult.OK; };
            Controls.Add(ok);
            AcceptButton = ok;
            CancelButton = cancel;
        }
        public List<string> Selection()
        {
            List<string> list = new List<string>();
            foreach (KeyValuePair<string, CheckBox> kv in checks)
                if (kv.Value.Checked) list.Add(kv.Key);
            return list;
        }
        public bool AutoStart { get { return autoBox.Checked; } }
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
            flags.Add("--disable-gpu");
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
            ToolStripMenuItem sw = new ToolStripMenuItem("选择桌面组件…");
            sw.Click += delegate { ShowSwitcher(); };
            menu.Items.Add(sw);
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
            tray.Icon = SystemIcons.Application;
            tray.Text = Settings.AppName;
            tray.ContextMenuStrip = menu;
            tray.Visible = true;
            tray.MouseDoubleClick += delegate { ShowSwitcher(); };
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
            string[] current = SelectedModules();
            ShowSwitcher();
            bool anyVisible = false;
            foreach (WidgetForm w in Windows.Values) if (w.Visible) anyVisible = true;
            if (!anyVisible)
            {
                string[] now = SelectedModules();
                ApplySelection(now.Length == current.Length ? current : now);
            }
        }

        public void ShowSwitcher()
        {
            StartupDialog dlg = new StartupDialog(SelectedModules(), "true" == Settings.Get("autoStart"));
            if (dlg.ShowDialog() == DialogResult.OK)
            {
                ApplySelection(dlg.Selection().ToArray());
                SetAutoStart(dlg.AutoStart);
            }
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
            WidgetForm window = null;
            if (visible && !Windows.TryGetValue(name, out window))
            {
                window = new WidgetForm(name);
                Windows[name] = window;
            }
            if (visible && window != null) window.Show();
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
