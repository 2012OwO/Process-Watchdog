using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Text;
using System.Windows.Forms;

namespace ProcessWatchdog
{
    public class MainForm : Form
    {
        // ===== 配置与状态 =====
        private string baseDir;
        private string configFile;
        private string logFile;

        private string monitorPath = "";   // 程序A：被监控程序
        private string launchPath = "";    // 程序B：被启动程序
        private string monitorProcName = "";

        private bool monitoring = false;   // 监控是否开启
        private bool wasRunning = false;   // 上一轮 程序A 是否在运行
        private bool firstCheck = true;
        private bool allowClose = false;   // 是否真正退出程序
        private bool formCreated = false;

        // ===== 界面控件 =====
        private NotifyIcon trayIcon;
        private System.Windows.Forms.Timer pollTimer;
        private Label lblMonitor;
        private Label lblLaunch;
        private Label lblStatus;
        private Label lblProc;
        private TextBox txtMonitor;
        private TextBox txtLaunch;
        private Button btnToggle;
        private Button btnReload;
        private Button btnLog;
        private Button btnExit;

        public MainForm()
        {
            baseDir = AppDomain.CurrentDomain.BaseDirectory;
            configFile = Path.Combine(baseDir, "config.ini");
            logFile = Path.Combine(baseDir, "Log.txt");

            InitUi();
            LoadConfig();
            StartMonitoring();
        }

        // ===== 界面初始化 =====
        private void InitUi()
        {
            this.Text = "进程看门狗 - Process Watchdog";
            this.Font = new Font("Microsoft YaHei UI", 9F);
            this.Size = new Size(520, 300);
            this.StartPosition = FormStartPosition.CenterScreen;
            this.ShowInTaskbar = false;
            this.FormBorderStyle = FormBorderStyle.FixedSingle;
            this.MaximizeBox = false;
            this.Icon = SystemIcons.Application;

            this.Size = new Size(505, 280);

            Label l1 = new Label { Text = "程序A（被监控）：", Left = 20, Top = 20, AutoSize = true };
            txtMonitor = new TextBox { Left = 20, Top = 42, Width = 380 };

            Label l2 = new Label { Text = "程序B（被启动）：", Left = 20, Top = 76, AutoSize = true };
            txtLaunch = new TextBox { Left = 20, Top = 98, Width = 380 };

            Button btnBrowseM = new Button { Text = "浏览…", Left = 410, Top = 40, Width = 62 };
            btnBrowseM.Click += (s, e) => BrowseFor(txtMonitor, "选择程序A（被监控程序）");
            Button btnBrowseL = new Button { Text = "浏览…", Left = 410, Top = 96, Width = 62 };
            btnBrowseL.Click += (s, e) => BrowseFor(txtLaunch, "选择程序B（被启动程序）");

            lblStatus = new Label { Text = "状态：已停止", Left = 20, Top = 138, AutoSize = true, ForeColor = Color.Gray };
            lblProc = new Label { Text = "程序A：未知", Left = 20, Top = 160, AutoSize = true, ForeColor = Color.Gray };

            btnToggle = new Button { Text = "停止监控", Left = 20, Top = 195, Width = 85 };
            btnToggle.Click += (s, e) => { if (monitoring) StopMonitoring(); else StartMonitoring(); };

            Button btnSave = new Button { Text = "保存配置", Left = 112, Top = 195, Width = 85 };
            btnSave.Click += (s, e) => SaveConfig();

            btnReload = new Button { Text = "重读配置", Left = 204, Top = 195, Width = 85 };
            btnReload.Click += (s, e) => { LoadConfig(); };

            btnLog = new Button { Text = "打开日志", Left = 296, Top = 195, Width = 85 };
            btnLog.Click += (s, e) => { try { if (File.Exists(logFile)) Process.Start(logFile); else MessageBox.Show("日志文件尚未生成。"); } catch { } };

            btnExit = new Button { Text = "退出", Left = 388, Top = 195, Width = 85 };
            btnExit.Click += (s, e) => { allowClose = true; this.Close(); };

            this.Controls.AddRange(new Control[] { l1, txtMonitor, l2, txtLaunch,
                btnBrowseM, btnBrowseL, lblStatus, lblProc,
                btnToggle, btnSave, btnReload, btnLog, btnExit });

            // 托盘图标
            trayIcon = new NotifyIcon
            {
                Icon = SystemIcons.Application,
                Text = "进程看门狗",
                Visible = true,
                ContextMenu = BuildTrayMenu()
            };
            trayIcon.DoubleClick += (s, e) => ShowMainForm();

            // 500ms 轮询定时器
            pollTimer = new System.Windows.Forms.Timer { Interval = 500 };
            pollTimer.Tick += (s, e) => CheckProcess();
        }

        private ContextMenu BuildTrayMenu()
        {
            ContextMenu menu = new ContextMenu();
            menu.MenuItems.Add("显示主界面", (s, e) => ShowMainForm());
            menu.MenuItems.Add("打开日志", (s, e) => { try { if (File.Exists(logFile)) Process.Start(logFile); } catch { } });
            menu.MenuItems.Add("-");
            menu.MenuItems.Add("退出", (s, e) => { allowClose = true; this.Close(); });
            return menu;
        }

        // 启动时隐藏窗口，仅在托盘显示
        protected override void SetVisibleCore(bool value)
        {
            if (!formCreated)
            {
                formCreated = true;
                value = false;
            }
            base.SetVisibleCore(value);
        }

        // 点关闭 = 隐藏到托盘，不退出
        protected override void OnFormClosing(FormClosingEventArgs e)
        {
            if (!allowClose)
            {
                e.Cancel = true;
                Hide();
            }
            base.OnFormClosing(e);
        }

        protected override void OnFormClosed(FormClosedEventArgs e)
        {
            if (trayIcon != null) trayIcon.Visible = false;
            base.OnFormClosed(e);
        }

        private void ShowMainForm()
        {
            this.Show();
            this.WindowState = FormWindowState.Normal;
            this.Activate();
        }

        // ===== 配置读取 =====
        private void LoadConfig()
        {
            try
            {
                if (!File.Exists(configFile))
                {
                    // 生成模板配置
                    File.WriteAllText(configFile,
                        "[Config]\r\n" +
                        "; 程序A：被监控程序的完整路径\r\n" +
                        "MonitorApp=C:\\path\\to\\ProgramA.exe\r\n" +
                        "; 程序B：被启动程序的完整路径\r\n" +
                        "LaunchApp=C:\\path\\to\\ProgramB.exe\r\n",
                        Encoding.Default);
                    MessageBox.Show("未找到 config.ini，已在程序目录生成模板配置文件，请编辑后点击“重读配置”。",
                        "提示", MessageBoxButtons.OK, MessageBoxIcon.Information);
                }

                foreach (string raw in File.ReadAllLines(configFile, Encoding.Default))
                {
                    string line = raw.Trim();
                    if (line.Length == 0 || line.StartsWith(";") || line.StartsWith("[")) continue;
                    int eq = line.IndexOf('=');
                    if (eq < 0) continue;
                    string key = line.Substring(0, eq).Trim().ToLower();
                    string val = line.Substring(eq + 1).Trim().Trim('"');
                    if (key == "monitorapp") monitorPath = val;
                    else if (key == "launchapp") launchPath = val;
                }

                monitorProcName = Path.GetFileNameWithoutExtension(monitorPath);
                txtMonitor.Text = string.IsNullOrEmpty(monitorPath) ? "（未配置）" : monitorPath;
                txtLaunch.Text = string.IsNullOrEmpty(launchPath) ? "（未配置）" : launchPath;

                if (string.IsNullOrEmpty(monitorPath) || string.IsNullOrEmpty(launchPath))
                {
                    MessageBox.Show("config.ini 中 MonitorApp / LaunchApp 未正确配置。", "配置错误",
                        MessageBoxButtons.OK, MessageBoxIcon.Warning);
                }

                wasRunning = false;
                firstCheck = true;
                Log("重新加载配置：MonitorApp=" + monitorPath + "，LaunchApp=" + launchPath);
            }
            catch (Exception ex)
            {
                MessageBox.Show("读取 config.ini 失败：" + ex.Message, "错误",
                    MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
        }

        // ===== 快速修改配置 =====
        private void BrowseFor(TextBox target, string title)
        {
            using (OpenFileDialog dlg = new OpenFileDialog())
            {
                dlg.Title = title;
                dlg.Filter = "程序 (*.exe;*.bat;*.cmd)|*.exe;*.bat;*.cmd|所有文件 (*.*)|*.*";
                if (dlg.ShowDialog(this) == DialogResult.OK)
                    target.Text = dlg.FileName;
            }
        }

        private void SaveConfig()
        {
            string m = txtMonitor.Text.Trim().Trim('"');
            string l = txtLaunch.Text.Trim().Trim('"');
            if (m.Length == 0 || m == "（未配置）" || l.Length == 0 || l == "（未配置）")
            {
                MessageBox.Show("请先填写程序A和程序B的完整路径。", "提示");
                return;
            }
            try
            {
                File.WriteAllText(configFile,
                    "[Config]\r\nMonitorApp=" + m + "\r\nLaunchApp=" + l + "\r\n",
                    Encoding.Default);
                Log("保存配置：MonitorApp=" + m + "，LaunchApp=" + l);
                MessageBox.Show("配置已保存到 config.ini，监控立即生效。", "成功");
                LoadConfig();
            }
            catch (Exception ex)
            {
                MessageBox.Show("保存配置失败：" + ex.Message, "错误");
            }
        }

        // ===== 监控逻辑 =====
        private void StartMonitoring()
        {
            monitoring = true;
            wasRunning = false;
            firstCheck = true;
            pollTimer.Start();
            btnToggle.Text = "停止监控";
            lblStatus.Text = "状态：监控中（每 500ms 轮询）";
            lblStatus.ForeColor = Color.Green;
            trayIcon.Text = "进程看门狗 - 监控中";
            Log("开始监控");
        }

        private void StopMonitoring()
        {
            monitoring = false;
            pollTimer.Stop();
            btnToggle.Text = "开始监控";
            lblStatus.Text = "状态：已停止";
            lblStatus.ForeColor = Color.Gray;
            lblProc.Text = "程序A：未知";
            trayIcon.Text = "进程看门狗 - 已停止";
            Log("停止监控");
        }

        private void CheckProcess()
        {
            try
            {
                if (string.IsNullOrEmpty(monitorProcName)) return;

                bool running = Process.GetProcessesByName(monitorProcName).Length > 0;

                if (firstCheck)
                {
                    firstCheck = false;
                    wasRunning = running;
                    if (running)
                        Log("程序A 正在运行：" + monitorPath + "，等待其退出");
                    else
                        Log("程序A 当前未运行，等待其启动");
                }
                else if (running && !wasRunning)
                {
                    wasRunning = true;
                    Log("检测到 程序A 启动：" + monitorPath);
                }
                else if (!running && wasRunning)
                {
                    wasRunning = false;
                    Log("检测到 程序A 退出：" + monitorPath + "，立即启动 程序B");
                    LaunchProgramB();
                }

                lblProc.Text = "程序A：" + (running ? "运行中" : "未运行");
                lblProc.ForeColor = running ? Color.Green : Color.OrangeRed;
            }
            catch (Exception ex)
            {
                Log("轮询出错：" + ex.Message);
            }
        }

        private void LaunchProgramB()
        {
            try
            {
                if (string.IsNullOrEmpty(launchPath) || !File.Exists(launchPath))
                {
                    Log("启动失败，程序B 不存在：" + launchPath);
                    MessageBox.Show("程序B 路径无效或文件不存在：" + launchPath, "启动失败",
                        MessageBoxButtons.OK, MessageBoxIcon.Error);
                    return;
                }
                Process p = new Process();
                p.StartInfo.FileName = launchPath;
                p.StartInfo.WorkingDirectory = Path.GetDirectoryName(launchPath) ?? "";
                bool ok = p.Start();
                Log(ok ? "程序B 启动成功：" + launchPath : "程序B 启动失败：" + launchPath);
            }
            catch (Exception ex)
            {
                Log("启动 程序B 出错：" + ex.Message);
            }
        }

        // ===== 日志 =====
        private readonly object logLock = new object();
        private void Log(string msg)
        {
            try
            {
                lock (logLock)
                {
                    File.AppendAllText(logFile,
                        DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss.fff") + "  " + msg + "\r\n",
                        Encoding.Default);
                }
            }
            catch { }
        }
    }

    static class Program
    {
        [STAThread]
        static void Main()
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.Run(new MainForm());
        }
    }
}
