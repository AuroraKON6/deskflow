# DeskFlow 50MB 瘦身计划(WebView2 路线)

目标:整体架构不变、功能不变、设计不变,zip 压缩包 < 50MB(当前 109.6MB)。
路线:渲染引擎从 QtWebEngine 换成 WebView2(系统 Chromium),外壳从 PySide6 换成轻量宿主。

## 大小账

- 移除:QtWebEngine 全家(147MB Core + icudtl 10MB + 资源 15MB + Process)≈ 180MB
- 移除:PySide6 全部(Qt6Gui/Widgets/Core 21MB + 绑定 10MB + 平台插件)≈ 40MB
- 新增:pywebview/pythonnet + WebView2 loader ≈ 8-10MB
- 保留:Python 运行时(python311.dll 5.5MB + base_library 1.4MB + ucrt 3MB)≈ 10MB
- 预估:dist ~30MB,zip ~12-18MB。目标达成,余量充足。

## 不变的部分

- `desktop-organizer-concepts/index.html` 原样复用,零 UI 改动
- 全部前端 JS 逻辑(待办/倒计时/文件收纳/粒子/折叠/紧凑)原样运行
- 窗口外观:透明无边框、硬阴影、折页动画 —— 由同一个 CSS 渲染
- 后端行为:托盘、启动器对话框、开机自启、位置记忆、拖拽缩放,行为逐条对齐

## 变的部分

- 桥接层:`qwebchannel.js`(60 行)换成 WebView2 WebMessage shim(~40 行),暴露同样的 `window.desktopBridge` API,前端代码无感
- 外壳:`main.py`(~740 行)重写为 `DeskFlow.py`(~500 行),PySide6 → pywebview/win32,原生对话框 + 托盘不变
- 数据:localStorage 换存储位置(WebView2 user data folder → `%APPDATA%\DeskFlow`)

## 实测资源占用(v1.0.0,2026-08-13)

| 指标 | 数值 |
|---|---|
| 进程 | 3 个(DeskFlow + 2 个 QtWebEngineProcess) |
| 空闲 RAM | ~436MB(295 + 73 + 68) |
| CPU | 空闲累计 2.8s,基本闲置 |

RAM 大头是 Chromium 内核;WebView2 路线后,宿主 DLL 全部走系统(不计入 app 内存),预估 app 内存 ~30-50MB,约降 10 倍,这是比体积更实在的收益。

## 阶段计划

### Phase 0 — 技术验证(约 2h,~60K tokens)
先证伪最大风险:WebView2 透明窗口渲染 HTML 是否正常。
- 最小原型(~200 行):一个透明无边框窗口渲染 todo widget,验证拖拽
- 验证项:透明背景、圆角、文件拖放、WebMessage 通道、无渲染黑底
- 产出:可运行的 spike;若透明有怪癖,评估降级方案(1px 实色底/回退 QML)

### Phase 1 — 外壳重写(约 3.5h,~200K tokens)
- `DeskFlow.py`:WidgetWindow(透明/无边框/拖拽/缩放)+ StartupDialog + 托盘菜单 + 注册表持久化 + 开机自启,行为对齐现版
- 桥接 API 逐条对齐:openPath / copyFiles / chooseFiles / notify / setEnabledModules / setAutoStart / beginMove / beginResize / setManualSize / setAlwaysOnTop / resizeWindow / resetPosition / hideWindow / openSwitcher
- 前端仅加 ~40 行 shim(条件编译:有 qt 走 QWebChannel,无 qt 走 WebView2 消息),同仓库双栈共存

### Phase 2 — 功能验收(约 1.5h,~100K tokens)
复用本会话的验证工具链(窗口枚举/拖拽模拟/像素采样/MiMo 截图):
- 三个 widget 独立渲染、可拖分、缩放、折叠、紧凑
- 托盘开关模块、提醒触发、文件拖放收纳、开机自启
- 与 v1.0.0 并排对比截图(MiMo + 像素 diff)

### Phase 3 — 打包发布(约 1h,~30K tokens)
- `build.ps1` v2(PyInstaller,无 PySide6,无需 Qt 清理)
- zip → GitHub Release v2.0.0(保留 v1.0.0)
- README 更新:体积对比、WebView2 依赖说明(Win11 自带)

合计:~8 小时 / ~390K tokens,建议分 2-3 次会话(每阶段末尾需要你看效果)。

## 风险与对策

| 风险 | 对策 |
|---|---|
| WebView2 透明窗口渲染有已知怪癖 | Phase 0 先证伪;降级方案:1px 实色底 / 回退 QML 路线 |
| 目标机器缺 WebView2 Runtime | Win11 预装(Edge 内核);Win10 老版本走 Evergreen 自动安装,README 注明 |
| 旧数据(localStorage)迁移 | 待用户选:手动重建 / 老版本加"导出数据"按钮(v1.0.1) |
| WebMessage 拖拽交互差异 | 沿用现有 header 区域 beginMove 模式,Phase 0 验证 |

## 待拍板

1. 旧数据要不要迁(要 → 老版本出 v1.0.1 加导出按钮;不要 → 直接开工)
2. 确认开工时机(可随时)

## Phase 0-3 实测结果(2026-08-13)

### 目标达成
- **zip 17.0MB**(v1 109.6MB → 降 84%),目标 <50MB 大幅达成
- dist 30.3MB(v1 250MB → 降 88%)
- 设计/功能/架构不变:同一份 index.html,WebView2 渲染

### 验证项
- WebView2 渲染 index.html:MiMo 视觉确认纸色卡片/圆角/列表内容正确
- 透明无边框窗口:WS_EX_NOREDIRECTIONBITMAP + DefaultBackgroundColor
- 桥接 14 方法:注入 shim → chrome.webview.postMessage → host 分发(实测 resize/drag/resize 全通)
- 拖拽/边缘缩放:WM_NCLBUTTONDOWN + HT* 码(实测通过)
- 数据迁移:读旧版注册表键,位置/尺寸精确还原
- 启动器对话框 + 托盘 + 单实例互斥锁
- DPI:--force-device-scale-factor + CSS↔物理换算

### 内存实测(诚实记录)
- v1 QtWebEngine:~436MB(DeskFlow 295 + WebView 141)
- v2 WebView2:~594MB(DeskFlow 122 + WebView2 7 进程 471)
- 结论:体积大幅缩小,但内存没有降 —— WebView2 同是 Chromium,进程模型更分散。
  计划中"内存降 10 倍"预估错误。若内存是硬需求,需 C#(.NET Framework)壳,
  但那是另一次重写,且 zip 仍需 ~20-30MB。

### 关键技术踩坑
1. pythonnet `Application.Run(form)` 重载解析错误 → 先 form.Show() 再 Run()
2. UI 线程 CreateAsync().Result 阻塞 → WebView2 不初始化 → 改用环境变量
   (WEBVIEW2_USER_DATA_FOLDER + WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS)
3. WinForms DPI-aware 下坐标是物理像素,必须乘/除 dpi_scale()
4. `.venv\Scripts\python.exe` 是启动器,会派生子进程(正常行为,勿误判双实例)
5. PyInstaller 打包:--add-data 放 webview2lib DLL + WebView2Loader.dll
