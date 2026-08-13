# DeskFlow Windows 桌面版

这是当前桌面待办、倒计时和文件收纳效果稿的原生 Windows 外壳。

## 已接入的原生能力

- 双击 EXE 直接启动，不需要浏览器。
- Windows 系统托盘与后台运行。
- 使用系统默认程序打开文件。
- 将真实文件路径写入 Windows 文件剪贴板，可在资源管理器中粘贴。
- 原生文件选择器。
- Windows 系统托盘提醒。
- 关闭主窗口后继续在后台执行提醒。
- 可在启动控制台开启或关闭 Windows 当前用户的开机自动启动。

## 构建

在 PowerShell 中运行：

```powershell
.\build.ps1
```

生成结果位于 `desktop-organizer-dist\DeskFlow\DeskFlow.exe`。

PoggetCore 使用 Apache-2.0 许可，后续接入其收纳存储层时需保留原 LICENSE 与修改说明。
