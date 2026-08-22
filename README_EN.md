English | [简体中文](./README.md)

# Process Watchdog

A lightweight Windows process watchdog: it stays in the system tray, monitors the running state of a specified program (Program A), and when it exits — whether closed normally or crashed — it **automatically and concurrently** launches a pre-configured list of programs (Program B list), with full logging.

## Notes

- This program has no uninstaller. To remove it, simply delete all files in the installation directory(C:\Users\yourusername\AppData\Local\Programs\ProcessWatchdog).
- **Watch your system tray!!!** Multiple instances of this program can be run at the same time, with no warning when more than one is open.

## Features

- **Tray-resident**: hides to the system tray on launch; double-click the tray icon to open the main window; closing the window only minimizes it back to the tray
- **500 ms high-frequency polling**: checks every 500 ms whether Program A has exited
- **Program B list**: supports any number of programs to launch, all started **concurrently via multiple threads** when triggered (in real tests, multiple programs were launched within the same millisecond)
- **Safe trigger logic**: only triggers when Program A "was running and then exited", avoiding false launches at boot when A hasn't started yet
- **Quick config in the GUI**: edit paths directly in the window, browse for files, and click "Save Config" to apply instantly — no manual INI editing needed
- **Dual logging**: built-in real-time log panel + `Log.txt` file (with millisecond timestamps)
- **No dependencies**: the EXE in Releases bundles the entire runtime — just download and run, no Python or any other environment required

## Quick Start

1. Download `ProcessWatchdog-install` from [Releases](../../releases) and run it
2. Create `config.ini` in the installation directory (a template is auto-generated on first run) and edit it as needed:

```ini
[Config]
; Program A: full path of the monitored program
MonitorApp=C:\path\to\ProgramA.exe
; Program B list: launched concurrently when Program A exits, any number of lines
LaunchApp1=C:\path\to\ProgramB1.exe
LaunchApp2=C:\path\to\ProgramB2.exe
```

3. Double-click the EXE; it hides to the tray and starts monitoring (you can also edit the config in the window and click "Save Config")

> Tip: the legacy single-entry `LaunchApp=...` format is still supported when reading; the GUI rewrites it as `LaunchApp1..N` when saving.

## How It Works

```
Start → read config.ini → hide to tray
  ↓ poll every 500 ms
Is Program A running? ──No (never ran)──> keep waiting
  ↓ Yes
Program A exits detected ──> concurrently launch all programs in the B list ──> log "Triggered, X programs launched"
```

## UI Overview

- **Program A path**: directly editable or selectable via file browser
- **Program B list**: Add… (multi-select supported) / Remove selected / Clear
- **Action buttons**: start/stop monitoring, save config, reload config, open log file, exit
- **Log panel**: scrolls in real time showing runtime events

## Building from Source (Python, primary version)

```bash
pip install PySide6-Essentials psutil pyinstaller
pyinstaller --onefile --noconsole --name ProcessWatchdog watchdog_qt.py
```

The build output is `dist/ProcessWatchdog.exe`.

## C# Version (early simplified edition)

`ProcessWatchdog.cs` in this repository is an earlier version written in C# WinForms. It only supports a **single** Program B (no list / concurrent launch / log panel); the Python version is the authoritative one. Its advantage is a single-file source that can be compiled directly with the .NET Framework compiler bundled with Windows into a very small EXE:

```
C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe /target:winexe /out:ProcessWatchdog.exe ProcessWatchdog.cs
```

## Configuration Reference

| Key | Description |
|---|---|
| `MonitorApp` | Full path of Program A, the monitored program |
| `LaunchApp1..N` | Program B list, launched concurrently when Program A exits |

Files generated at runtime (all in the same directory as the EXE):

- `config.ini` — configuration file (a template is auto-generated if missing)
- `Log.txt` — runtime log

## Acknowledgements

The code of this project was generated with AI assistance and verified by real-world manual testing (process exit detection, concurrent launching, and logging all passed live tests).

## License

[MIT](./LICENSE)
