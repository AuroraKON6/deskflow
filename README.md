# DeskFlow · 序 · 桌面效率工具

> 三个住在你桌面上的小卡片。
> 一个钉住拖延,一个盯着 Deadline,一个把杂物码得整整齐齐。

**序** 是一套 Windows 桌面悬浮组件,长得像从纸里剪出来的三张卡片,但它们是真的会干活:

- **今日待办** — 你的每日任务清单。勾掉一项会蹦粒子庆祝;没做完?它比你更着急。
- **倒计时** — 给重要日子上发条。24 / 16 / 8 小时三档紧急提醒,越接近 Deadline 它越红。
- **文件收纳** — 把文件拖到卡片上,它就记住位置。下次想找,点一下,文件自己打开。

每个模块都是一个独立的透明悬浮小窗口:可以拖、可以缩放、可以折叠成三层书页塞到角落。关掉不是退出,它们会缩回系统托盘继续替你盯着时间。

## 为什么是这个样子

界面是一份单文件 HTML(`desktop-organizer-concepts/index.html`),带完整的设计系统:纸质感配色、硬阴影、折页动画、粒子特效。Python 外壳(PySide6 + QtWebEngine)只负责把每个模块变成一个真正的 Windows 窗口 —— 拖动、缩放、托盘、开机自启,都是原生能力。

## 目录

- `desktop-organizer-app/` — Python 外壳源码、构建脚本
- `desktop-organizer-concepts/` — 界面层(HTML + 概念渲染脚本)
- 构建产物在 Releases,不在仓库里

## 构建

```powershell
cd desktop-organizer-app
.\build.ps1
```

产物在 `desktop-organizer-dist\DeskFlow\DeskFlow.exe`。构建脚本排除了 33 个用不到的 PySide6 模块,构建后再清掉 QtPdf / 软件渲染回退 / 49 种语言包,dist 从 408MB 瘦到 250MB,zip 约 110MB。

## 使用

- 双击 exe,首次启动弹「桌面组件选择」,勾哪个,哪个就上桌
- 组件默认**钉在桌面上**:位于壁纸和图标之上、所有程序窗口之下,开程序/拖文件都会盖在它上面(Win+D 显示桌面时也一直在)
- 拖标题栏移动,拖边缘缩放;位置和尺寸自动记忆,下次启动原位恢复
- 标题栏图钉按钮 = 桌面固定开关(默认开);关掉后是普通浮动窗口
- 右上角菜单可折叠 / 紧凑 / 回原位 / 打开设置
- 托盘图标常驻:「设置…」开关模块和开机自启,「彻底退出」
- 数据存在 `%APPDATA%\DeskFlow`

## 修复记录

- 2026-08-13:修复手动尺寸模式下嵌入窗口内三个页面全部堆叠渲染(CSS 优先级 bug,`.widget:not(.module-off)`)
- 2026-09-04:v3 设置窗口上线 —— 用 HTML 启动器面板(总开关 + 三模块开关 + 开机自启)替换 WinForms 启动对话框,托盘「设置…」/ 组件菜单「窗口总开关…」/ 双击托盘均可打开
- 2026-09-04:修复 v3 桥接参数丢失(JavaScriptSerializer 把嵌套数组反序列化为 `Collection<object>`,`is object[]` 判断失败导致 resizeWindow / setEnabledModules / copyFiles 全部按空参数执行)
- 2026-09-04:修复 v3 从设置/托盘关闭模块时窗口不隐藏(`TryGetValue` 只在 visible 分支执行,移植自 v2 时引入)
- 2026-09-04:启动黑框与三页面黑边的根因是 v2 —— python.exe 控制台宿主 + `WS_EX_NOREDIRECTIONBITMAP` 在窗口显示后才设置且未生效;v3(CreateParams 提前设置 + GUI 子系统)两者皆无,v2 自启命令也已改用 pythonw.exe 兜底
- 2026-09-04:**桌面钉住模式** —— 组件窗口 SetParent 到桌面层(Progman,失败时发 0x052C 生成 WorkerW,每进程只试一次),默认开启、状态持久化;原「置顶窗口」图钉按钮语义改为「桌面固定」;explorer 重启后自动重挂
- 2026-09-05:桌面钉住改用 z 序方案(SetParent 会让 WebView2 走子窗口渲染路径、alpha 失效发黑),并修复 `GetWindowW` 入口点崩溃
- 2026-09-05:程序图标 —— 「序」纸片卡片(墨色圆角底 + 珊瑚橙硬阴影),嵌入 exe 并用于托盘/Alt-Tab

## 许可

MIT
