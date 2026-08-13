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
- 拖标题栏移动,拖边缘缩放;右上角菜单可折叠 / 紧凑 / 回原位
- 托盘图标常驻:切换模块、改开机自启、彻底退出
- 数据存在 `%APPDATA%\DeskFlow`

## 修复记录

- 2026-08-13:修复手动尺寸模式下嵌入窗口内三个页面全部堆叠渲染(CSS 优先级 bug,`.widget:not(.module-off)`)

## 许可

MIT
