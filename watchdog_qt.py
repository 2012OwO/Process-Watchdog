# -*- coding: utf-8 -*-
r"""
进程看门狗 - Process Watchdog
读取同目录 config.ini，启动后隐藏至系统托盘，每 500ms 轮询检测程序A是否退出，
程序A退出（正常关闭或崩溃）后自动、并发地启动配置列表中的所有程序B，
并将事件记录到 Log.txt 与界面日志区。

config.ini 格式：
    [Config]
    MonitorApp=C:\path\to\ProgramA.exe
    LaunchApp1=C:\path\to\ProgramB1.exe
    LaunchApp2=C:\path\to\ProgramB2.exe
    （LaunchApp 旧单程序写法仍兼容；GUI 保存时统一写为 LaunchApp1..N）
"""
import os
import re
import sys
import datetime
import threading
import configparser
import subprocess

import psutil
from PySide6.QtCore import Qt, QTimer, QPointF, QObject, Signal
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QPen, QPolygonF
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QLineEdit, QPushButton,
    QVBoxLayout, QHBoxLayout, QGridLayout, QMessageBox,
    QSystemTrayIcon, QMenu, QFileDialog,
    QListWidget, QListWidgetItem, QPlainTextEdit, QAbstractItemView,
)

APP_TITLE = "进程看门狗 - Process Watchdog"

CONFIG_TEMPLATE = (
    "[Config]\r\n"
    "; 程序A：被监控程序的完整路径\r\n"
    "MonitorApp=C:\\path\\to\\ProgramA.exe\r\n"
    "; 程序B列表：被启动程序，可写多行 LaunchApp1、LaunchApp2 …\r\n"
    "LaunchApp1=C:\\path\\to\\ProgramB1.exe\r\n"
    "LaunchApp2=C:\\path\\to\\ProgramB2.exe\r\n"
)


def get_base_dir():
    """打包成 EXE 后，取 EXE 所在目录；开发时取脚本所在目录。"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


BASE_DIR = get_base_dir()
CONFIG_FILE = os.path.join(BASE_DIR, 'config.ini')
LOG_FILE = os.path.join(BASE_DIR, 'Log.txt')

_log_lock = threading.Lock()


# ---------- 日志：文件 + 界面日志区（线程安全，跨线程走 Qt 信号队列） ----------
class LogHub(QObject):
    send = Signal(str)


_hub = None  # main() 中创建并连接


def log(msg):
    try:
        with _log_lock:
            stamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
            with open(LOG_FILE, 'a', encoding='utf-8') as f:
                f.write("%s  %s\r\n" % (stamp, msg))
    except Exception:
        pass
    if _hub is not None:
        try:
            _hub.send.emit(msg)
        except Exception:
            pass


def read_ini(path):
    """读取 ini，兼容 UTF-8 / GBK 编码。"""
    for enc in ('utf-8-sig', 'gbk'):
        try:
            with open(path, 'r', encoding=enc) as f:
                cp = configparser.ConfigParser()
                cp.read_file(f)
            return cp
        except (UnicodeDecodeError, configparser.Error):
            continue
    cp = configparser.ConfigParser()
    cp.read(path, encoding='utf-8', errors='ignore')
    return cp


def load_launch_list_from_cp(cp):
    """按 LaunchApp（旧单程序）+ LaunchApp1..N 收集被启动程序列表，保持顺序。"""
    items = []
    if cp.has_option('Config', 'LaunchApp'):
        v = cp.get('Config', 'LaunchApp').strip().strip('"')
        if v:
            items.append(v)
    numbered = []
    if cp.has_section('Config'):
        for key in cp.options('Config'):
            m = re.match(r'^LaunchApp(\d+)$', key, re.IGNORECASE)
            if m:
                v = cp.get('Config', key).strip().strip('"')
                if v:
                    numbered.append((int(m.group(1)), v))
    numbered.sort(key=lambda t: t[0])
    items.extend(v for _, v in numbered)
    return items


def make_icon():
    """生成托盘图标：蓝底白色 W。"""
    pm = QPixmap(64, 64)
    pm.fill(QColor(30, 120, 215))
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor(255, 255, 255), 7))
    p.drawPolyline(QPolygonF([
        QPointF(14, 18), QPointF(24, 46), QPointF(32, 28),
        QPointF(40, 46), QPointF(50, 18),
    ]))
    p.end()
    return QIcon(pm)


class WatchdogWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(660, 600)
        self.setWindowIcon(make_icon())

        # 状态
        self.monitor_path = ''
        self.monitor_proc = ''
        self.launch_paths = []
        self.monitoring = False
        self.was_running = False
        self.first_check = True
        self.quitting = False

        self._build_ui()
        self._build_tray()

        # 500ms 轮询定时器
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.check_process)

        self.load_config()
        self.start_monitoring()

    # ---------- 界面 ----------
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(18, 14, 18, 14)
        outer.setSpacing(6)

        # 程序A
        row_a = QHBoxLayout()
        row_a.addWidget(QLabel("程序A（被监控）："))
        self.ed_monitor = QLineEdit()
        self.ed_monitor.setPlaceholderText("可在此直接填写路径，或点击“浏览…”选择")
        row_a.addWidget(self.ed_monitor, 1)
        btn_browse_m = QPushButton("浏览…")
        btn_browse_m.clicked.connect(self.browse_monitor)
        row_a.addWidget(btn_browse_m)
        outer.addLayout(row_a)

        # 程序B列表
        outer.addWidget(QLabel("程序B列表（退出时并发启动全部）："))

        row_b = QHBoxLayout()
        self.lst_launch = QListWidget()
        self.lst_launch.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.lst_launch.setMinimumHeight(110)
        self.lst_launch.setToolTip("选中后可删除；程序A退出时将同时启动列表中的所有程序")
        row_b.addWidget(self.lst_launch, 1)

        col_btns = QVBoxLayout()
        btn_add = QPushButton("添加…")
        btn_add.clicked.connect(self.add_launch)
        col_btns.addWidget(btn_add)
        btn_del = QPushButton("删除选中")
        btn_del.clicked.connect(self.del_launch)
        col_btns.addWidget(btn_del)
        btn_clear = QPushButton("清空")
        btn_clear.clicked.connect(self.clear_launch)
        col_btns.addWidget(btn_clear)
        col_btns.addStretch(1)
        row_b.addLayout(col_btns)
        outer.addLayout(row_b)

        # 状态
        self.lbl_status = QLabel("状态：已停止")
        self.lbl_proc = QLabel("程序A：未知")
        outer.addWidget(self.lbl_status)
        outer.addWidget(self.lbl_proc)

        # 操作按钮
        btns = QHBoxLayout()
        self.btn_toggle = QPushButton("停止监控")
        self.btn_toggle.clicked.connect(self.on_toggle)
        btns.addWidget(self.btn_toggle)
        btn_save = QPushButton("保存配置")
        btn_save.clicked.connect(self.save_config)
        btns.addWidget(btn_save)
        btn_reload = QPushButton("重读配置")
        btn_reload.clicked.connect(self.load_config)
        btns.addWidget(btn_reload)
        btn_log = QPushButton("打开日志文件")
        btn_log.clicked.connect(self.open_log)
        btns.addWidget(btn_log)
        btn_quit = QPushButton("退出")
        btn_quit.clicked.connect(self.quit_app)
        btns.addWidget(btn_quit)
        btns.addStretch(1)
        outer.addLayout(btns)

        # 界面日志区
        outer.addWidget(QLabel("日志："))
        self.txt_log = QPlainTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setMaximumBlockCount(1000)
        self.txt_log.setMinimumHeight(140)
        outer.addWidget(self.txt_log, 1)

    def _build_tray(self):
        menu = QMenu()
        act_show = menu.addAction("显示主界面")
        act_show.triggered.connect(self.show_and_raise)
        act_log = menu.addAction("打开日志文件")
        act_log.triggered.connect(self.open_log)
        menu.addSeparator()
        act_quit = menu.addAction("退出")
        act_quit.triggered.connect(self.quit_app)

        self.tray = QSystemTrayIcon(make_icon(), self)
        self.tray.setToolTip(APP_TITLE)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self.on_tray_activated)
        self.tray.show()

    def on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_and_raise()

    def show_and_raise(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    # ---------- 界面日志区 ----------
    def append_log_view(self, msg):
        stamp = datetime.datetime.now().strftime('%H:%M:%S')
        self.txt_log.appendPlainText("[%s] %s" % (stamp, msg))

    # ---------- 配置 ----------
    def browse_monitor(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择程序A（被监控程序）", "", "程序 (*.exe *.bat *.cmd);;所有文件 (*.*)")
        if path:
            self.ed_monitor.setText(path)

    def add_launch(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "选择程序B（可多选）", "", "程序 (*.exe *.bat *.cmd);;所有文件 (*.*)")
        for p in paths:
            if p:
                self.lst_launch.addItem(p)

    def del_launch(self):
        for item in reversed(self.lst_launch.selectedItems()):
            self.lst_launch.takeItem(self.lst_launch.row(item))

    def clear_launch(self):
        self.lst_launch.clear()

    def load_config(self):
        if not os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'w', encoding='utf-8-sig') as f:
                    f.write(CONFIG_TEMPLATE)
                log('未找到 config.ini，已生成模板配置文件')
            except Exception as e:
                log('生成模板配置失败：%s' % e)
            QTimer.singleShot(0, lambda: QMessageBox.information(
                self, "提示",
                "未找到 config.ini，已在程序目录生成模板配置文件，\n请编辑后点击“重读配置”。"))

        monitor, launch_list = '', []
        try:
            cp = read_ini(CONFIG_FILE)
            if cp.has_option('Config', 'MonitorApp'):
                monitor = cp.get('Config', 'MonitorApp').strip().strip('"')
            launch_list = load_launch_list_from_cp(cp)
        except Exception as e:
            log('读取 config.ini 失败：%s' % e)
            QTimer.singleShot(0, lambda: QMessageBox.critical(
                self, "错误", "读取 config.ini 失败：%s" % e))

        self.monitor_path = monitor
        self.launch_paths = list(launch_list)
        self.monitor_proc = os.path.splitext(os.path.basename(monitor))[0].lower() if monitor else ''

        self.ed_monitor.setText(monitor or "（未配置）")
        self.lst_launch.clear()
        for p in self.launch_paths:
            self.lst_launch.addItem(p)

        self.was_running = False
        self.first_check = True

        if not monitor or not launch_list:
            QTimer.singleShot(0, lambda: QMessageBox.warning(
                self, "配置错误", "config.ini 中 MonitorApp / LaunchApp 未正确配置。"))

        log('加载配置：MonitorApp=%s，程序B列表=%d个' % (monitor, len(launch_list)))

    def save_config(self):
        """把界面上的配置写回 config.ini，保存后立即生效。"""
        monitor = self.ed_monitor.text().strip().strip('"')
        if monitor in ('', '（未配置）', '(未配置)'):
            QMessageBox.warning(self, "提示", "请先填写程序A的完整路径。")
            return
        launches = [self.lst_launch.item(i).text().strip().strip('"')
                    for i in range(self.lst_launch.count())]
        launches = [p for p in launches if p]
        if not launches:
            QMessageBox.warning(self, "提示", "程序B列表为空，请至少添加一个被启动程序。")
            return
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8-sig') as f:
                f.write("[Config]\r\nMonitorApp=%s\r\n" % monitor)
                for i, p in enumerate(launches, 1):
                    f.write("LaunchApp%d=%s\r\n" % (i, p))
            log('保存配置：MonitorApp=%s，程序B列表=%d个' % (monitor, len(launches)))
            QMessageBox.information(self, "成功", "配置已保存到 config.ini，监控立即生效。")
            self.load_config()
        except Exception as e:
            QMessageBox.critical(self, "错误", "保存配置失败：%s" % e)

    # ---------- 监控 ----------
    def on_toggle(self):
        if self.monitoring:
            self.stop_monitoring()
        else:
            self.start_monitoring()

    def start_monitoring(self):
        self.monitoring = True
        self.was_running = False
        self.first_check = True
        self.btn_toggle.setText("停止监控")
        self.lbl_status.setText("状态：监控中（每 500ms 轮询）")
        self.tray.setToolTip(APP_TITLE + " - 监控中")
        log('开始监控')
        self.timer.start(500)

    def stop_monitoring(self):
        self.monitoring = False
        self.timer.stop()
        self.btn_toggle.setText("开始监控")
        self.lbl_status.setText("状态：已停止")
        self.lbl_proc.setText("程序A：未知")
        self.tray.setToolTip(APP_TITLE + " - 已停止")
        log('停止监控')

    def check_process(self):
        try:
            running = False
            if self.monitor_proc:
                for p in psutil.process_iter(['name']):
                    try:
                        n = (p.info['name'] or '').lower()
                        if n == self.monitor_proc + '.exe' or n == self.monitor_proc:
                            running = True
                            break
                    except Exception:
                        continue

            if self.first_check:
                self.first_check = False
                self.was_running = running
                if running:
                    log('程序A 正在运行：%s，等待其退出' % self.monitor_path)
                else:
                    log('程序A 当前未运行，等待其启动')
            elif running and not self.was_running:
                self.was_running = True
                log('检测到 程序A 启动：%s' % self.monitor_path)
            elif not running and self.was_running:
                self.was_running = False
                log('检测到 程序A 退出：%s，立即并发启动 程序B 列表' % self.monitor_path)
                self.launch_all_programs_b()

            self.lbl_proc.setText("程序A：" + ("运行中" if running else "未运行"))
        except Exception as e:
            log('轮询出错：%s' % e)

    # ---------- 并发启动程序B列表 ----------
    def _start_one(self, path, counter):
        """在独立线程中启动一个程序B，成功则计数 +1。"""
        if not path or not os.path.exists(path):
            log('启动失败，程序不存在：%s' % path)
            return
        try:
            subprocess.Popen(
                [path],
                cwd=os.path.dirname(path) or None,
                creationflags=getattr(subprocess, 'DETACHED_PROCESS', 0)
                | getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0),
                close_fds=True,
            )
            log('程序B 启动成功：%s' % path)
            counter.append(path)
        except Exception as e:
            log('启动 程序B 出错：%s（%s）' % (path, e))

    def launch_all_programs_b(self):
        """并发（同时）启动列表中的所有程序B，并记录汇总。"""
        paths = list(self.launch_paths)
        if not paths:
            log('程序B列表为空，无程序可启动')
            return
        counter = []
        threads = [threading.Thread(target=self._start_one, args=(p, counter))
                   for p in paths]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        log('已触发启动，共启动%d个程序' % len(counter))

    # ---------- 其他 ----------
    def open_log(self):
        try:
            if os.path.exists(LOG_FILE):
                os.startfile(LOG_FILE)
            else:
                QMessageBox.information(self, "提示", "日志文件尚未生成。")
        except Exception as e:
            QMessageBox.critical(self, "错误", "无法打开日志：%s" % e)

    def quit_app(self):
        self.quitting = True
        log('程序退出')
        self.tray.hide()
        QApplication.quit()

    def closeEvent(self, event):
        """点关闭 = 隐藏到托盘，不退出。"""
        if not self.quitting:
            event.ignore()
            self.hide()
        else:
            event.accept()


def main():
    global _hub
    log('程序启动')
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    _hub = LogHub()
    win = WatchdogWindow()
    _hub.send.connect(win.append_log_view)   # 跨线程自动走队列连接
    win.hide()          # 启动时隐藏，仅在系统托盘
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
