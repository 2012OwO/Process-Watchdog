[English](./README_EN.md) | 简体中文


# Process Watchdog - 进程看门狗

一个 Windows 轻量级进程看门狗工具：常驻系统托盘，监控指定程序（程序A）的运行状态，当它退出（无论是正常关闭还是崩溃）时，**自动、并发地**启动你预先配置的一组程序（程序B列表），并记录完整日志。

## 注意事项

- 此程序没有卸载程序，如需卸载，到安装目录清除所有文件即可
- 请注意你的系统托盘！！！此程序可以多开，且打开多个时无提示

## 功能特性

- **托盘常驻**：启动后隐藏到系统托盘运行，双击托盘图标打开主界面，关闭窗口仅最小化到托盘
- **500ms 高频轮询**：以 500ms 间隔检测程序A是否退出
- **程序B列表**：支持配置任意多个被启动程序，触发时**多线程并发同时启动**（实测多个程序同毫秒拉起）
- **触发逻辑安全**：只在"A 曾经运行过、然后退出"时触发，避免开机时 A 尚未启动就被误拉起
- **GUI 快速改配置**：界面内直接编辑路径、浏览选文件、一键"保存配置"立即生效，无需手动改 ini
- **双份日志**：主界面内置实时日志区 + `Log.txt` 文件（含毫秒级时间戳）
- **无需依赖**：Release 中的 EXE 已打包全部运行时，下载即用，无需安装 Python 或任何环境

## 快速开始

1. 从 [Releases](../../releases) 下载 `ProcessWatchdog install.exe`，运行
2. 安装目录下创建 `config.ini`（首次运行会自动生成模板），按需修改：

```ini
[Config]
; 程序A：被监控程序的完整路径
MonitorApp=C:\path\to\ProgramA.exe
; 程序B列表：程序A退出时并发启动，可写任意多行
LaunchApp1=C:\path\to\ProgramB1.exe
LaunchApp2=C:\path\to\ProgramB2.exe
```

3. 双击运行 EXE，程序进入托盘开始监控（也可以直接在界面里改配置后点"保存配置"）

> 提示：旧版单条 `LaunchApp=...` 写法仍兼容读取，GUI 保存时会统一写成 `LaunchApp1..N`。

## 工作流程

```
启动 → 读取 config.ini → 隐藏到托盘
  ↓ 每 500ms 轮询
程序A 在运行？ ──否(从未运行)──> 继续等待
  ↓ 是
检测到程序A退出 ──> 并发启动列表中所有程序B ──> 记录日志"已触发启动，共启动X个程序"
```

## 界面一览

- **程序A路径**：可直接编辑或浏览选择
- **程序B列表**：添加…（支持多选）/ 删除选中 / 清空
- **操作按钮**：启停监控、保存配置、重读配置、打开日志文件、退出
- **日志区**：实时滚动显示运行事件

## 从源码构建（Python 版，主版本）

```bash
pip install PySide6-Essentials psutil pyinstaller
pyinstaller --onefile --noconsole --name ProcessWatchdog watchdog_qt.py
```

构建产物在 `dist/ProcessWatchdog.exe`。

## C# 版本（早期简化版）

仓库中的 `ProcessWatchdog.cs` 是早期用 C# WinForms 编写的版本，仅支持**单个**程序B（无列表/并发/界面日志区），功能以 Python 版为准。它的优势是单文件源码、可用 Windows 自带的 .NET Framework 编译器直接编译出体积很小的 EXE：

```
C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe /target:winexe /out:ProcessWatchdog.exe ProcessWatchdog.cs
```

## 配置项说明

| 配置项 | 说明 |
|---|---|
| `MonitorApp` | 程序A完整路径，被监控的程序 |
| `LaunchApp1..N` | 程序B列表，程序A退出时并发启动 |

运行时生成的文件（均在与 EXE 同目录）：

- `config.ini` — 配置文件（不存在时自动生成模板）
- `Log.txt` — 运行日志

## 声明

本项目代码由 AI 辅助开发生成，并经人工实测验证（进程退出检测、并发拉起、日志记录均通过真实测试）。

## License

[MIT](./LICENSE)
