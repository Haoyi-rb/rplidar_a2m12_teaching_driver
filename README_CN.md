# A2M12 教学版 RPLIDAR ROS 2 驱动

[README.md](README.md) · [安装](README_INSTALL.md) · [新手导航](README_NEWBIE.md) · **中文说明** · [参数手册](doc/PARAM_GUIDE_A2M12.md) · [代码精读](doc/CODE_NOTES_CN.md)

基于 [frozenreboot/rplidar_driver](https://github.com/frozenreboot/rplidar_driver) 的教学分支；本包由 C1M1 教学包 `rplidar_c1m1_teaching_driver` 复制改名派生（A2M12 参数档 + 文档），C++ 驱动逻辑与 bug 修复原样保留。
原驱动的架构和功能都保留，修复了 3 个 bug（详见第 12 节），另外加了 A2M12 配置、RViz 配置、一个看门狗示例和中文文档。
英文原版说明已存档到 [doc/UPSTREAM_README_EN.md](doc/UPSTREAM_README_EN.md)（命令不适用 A2M12，仅供对照）。

**上游作者与贡献者**：本仓库 `main` 上共 67 个提交，其中 **64 个来自上游 v1.4.2**，3 个由本教学分支新增。
上游作者按提交数：**frozenreboot**（51；git 里显示为 `wj` 与 `JWJ | frozenreboot` 两个署名，同一邮箱）、
**cosmicog**（8，`interpolated_rays` 插值算法就是他贡献的）、**Błażej Sowa**（4）、**Filip Szkudlarek**（1）。
上游历史在 C1M1 教学包里原样保留、未改写任何提交；本 A2M12 包是文件级复制（不带 `.git`），要 `git blame` 或追溯上游请去那个仓库。
Contributors 面板里为什么有一个 Claude 头像，见 [9.4 节](#94-关于-contributors-列表里的-claude)。

**建议的阅读顺序**：

| 顺序 | 文档 | 什么时候看 |
|---|---|---|
| 1 | [README_INSTALL.md](README_INSTALL.md) | 第一次在这台电脑上用：装 ROS 2、编译、串口权限 |
| 2 | [README_NEWBIE.md](README_NEWBIE.md) | 想做某件事，不知道该改哪个文件、哪个函数 |
| 3 | 本页 | 真机实测数据、拔插行为、填坑记录、和上游的差异 |
| 4 | [doc/PARAM_GUIDE_A2M12.md](doc/PARAM_GUIDE_A2M12.md) | 调参数：每个参数改了会怎样 |
| 5 | [doc/CODE_NOTES_CN.md](doc/CODE_NOTES_CN.md) | 读源码：核心函数为什么这么写 |

环境：Ubuntu 22.04 + ROS 2 Humble。

---

## 1. 三分钟跑起来

```bash
# 1) 确认雷达插上了（A2M12 是 CP2102N 串口芯片，一般是 /dev/ttyUSB0）
ls /dev/ttyUSB*
groups | grep dialout     # 没有 dialout 就执行：sudo usermod -aG dialout $USER，然后注销重登

# 2) 编译
cd ~/A2M12_ros
source /opt/ros/humble/setup.bash
colcon build --symlink-install
source install/setup.bash

# 3) 启动驱动 + RViz（一行命令，会自动弹出 RViz 窗口，看到绿色的点就成功了）
ros2 launch rplidar_a2m12_teaching_driver a2m12.launch.py

# 4) 另开终端看频率（应约 10 Hz）
ros2 topic hz /scan
```

| 想要 | 命令 |
|---|---|
| 没有雷达也能练习（模拟数据） | `ros2 launch rplidar_a2m12_teaching_driver a2m12.launch.py dummy_mode:=true` |
| 不开 RViz（机器人上没有显示器、SSH 远程） | `ros2 launch rplidar_a2m12_teaching_driver a2m12.launch.py rviz:=false` |
| 用自己保存的 RViz 配置 | `ros2 launch rplidar_a2m12_teaching_driver a2m12.launch.py rviz_config:=/path/to/my.rviz` |

RViz 配置在 `rviz/a2m12.rviz`：俯视图，Fixed Frame 是 `laser_a2m12`（不需要 TF），1 m 网格，
红色轴是雷达正前方（+X），绿色轴是左边（+Y），点云是绿色方块。

> ⚠️ **避坑：自己开 rviz2 看不到点？**
> 驱动用 SensorDataQoS（Best Effort）发布 `/scan`。RViz 里 LaserScan 默认是 Reliable，两边不匹配就一个点都收不到，
> 也不报错。在 LaserScan → Topic → Reliability Policy 里改成 **Best Effort**。`rviz/a2m12.rviz` 已经设好了。

---

## 2. 和思岚官方驱动 `sllidar_ros2` 有什么不同

| | 官方 `sllidar_ros2` | 本驱动 |
|---|---|---|
| 程序结构 | 一个 `while` 循环：读一圈 → 发布 | Lifecycle 节点 + 后台读取线程 + 6 状态内部状态机 |
| 拔 USB | 读取失败，节点退出，要手动重启 | 自动进入 RESETTING，插回后自己重连 |
| 改 RPM | 改 launch 参数后重启节点 | `ros2 param set` 立即生效：A2M12 实测频率 9.2→18.8 Hz（但该值是 PWM 不是转速，见第 5 节） |
| 硬件访问 | 节点里直接调用 SDK | 通过 `LidarDriverInterface` 接口，真/假雷达可切换 |
| A2M12 波特率 | `sllidar_c1_launch.py` 里 256000 | `param/a2m12.yaml` 里 256000（原 `rplidar.yaml` 默认 1000000，不适用 A2M12） |

---

## 3. 两层状态机（最重要的概念）

本驱动有**两层**状态，新手最容易搞混：

```
外层：ROS 2 Lifecycle（"节点要不要干活"，由 launch 或命令控制）

  unconfigured ──configure──> inactive ──activate──> active
       ^                         │  ^                  │
       └──────cleanup────────────┘  └───deactivate─────┘

内层：DriverState（"雷达硬件现在怎么样"，只在 active 时运行，在 scan_loop 线程里）

  CONNECTING ─> CHECK_HEALTH ─> WARMUP ─> RUNNING
      ^                                     │ 连续读失败 > max_retries
      └────────── RESETTING <───────────────┘
                                   STANDBY（电机停转，串口保持连接）
```

- `a2m12.launch.py` 启动后会自动 configure → activate。
- **拔 USB 时外层一直是 active**，恢复是内层状态机自己在做，不需要任何人去 activate。

手动操作外层：

```bash
ros2 lifecycle get /rplidar_node          # 查看当前状态
ros2 lifecycle set /rplidar_node deactivate   # 让雷达回到待机（电机停，串口不关）
ros2 lifecycle set /rplidar_node activate     # 把雷达从待机叫醒
```

---

## 4. 拔插 USB 会怎样（C1M1 实测 + A2M12 单次拔插）

测试条件：RPLIDAR C1M1（FW 1.2，HW 18），`/dev/ttyUSB0`，460800，`max_retries: 3`，拔掉 36 秒后插回。
用的是本分支修复第 9.2、9.3 节之后的代码。
时间以拔掉 USB 的时刻为 0 秒；拔/插时刻用 `date +%s` 记录，精度约 1 秒。

### 4.1 本机 A2M12 真机记录（2026-11-06，FW 1.32 / HW 6）

下列数字来自这台 A2M12 的实机运行，和上面那张 C1M1 的表**不是同一台设备**：

| 项目 | 实测值 |
|---|---|
| 型号识别 | `Model ID: 44 (0x2C)`、`Type: RPLIDAR A2M12` |
| 固件 / 硬件 | `FW: 1.32`、`HW: 6` |
| 串口 | `/dev/ttyUSB0`，`serial_baudrate: 256000` |
| `range_max` | 12.0 m（`[Config] Max Range: 12.00 m`） |
| `frame_id` | `laser_a2m12` |
| `rpm: 0`（驱动按 600 下发）时的 `/scan` | **11.932 Hz**（≈716 rpm），不是标称的 10 Hz |
| 调速（5 档扫频） | **有效**：480/600/720/900 → 9.231 / 11.892 / 14.673 / 18.821 Hz；但 `rpm` 实为 PWM 值，见第 5 节 |
| `rpm` 越界保护 | 设 `1500` 被拒：`RPM must be between 0 and 1200` |
| 手动拔插 USB 实测 | 拔掉后触发 `[FSM] Hardware unresponsive (Over 3 errors). Resetting...` → 重建驱动 → 插回后约 30 s `Connection established`；`ros2 topic hz` 记到 `max: 40.666s` 的空档 |

**坑**：`ros2 topic echo /scan` 默认用 Reliable，而驱动发的是 Best Effort，终端会警告
`requesting incompatible QoS`；读数时加 `--qos-reliability best_effort`。

| 时刻 | 发生了什么 | 终端里会看到 |
|---|---|---|
| 0 s | 拔掉 USB | `/scan` 停止 |
| 约 5 s | 看门狗发现断流（3 秒超时 + 1 秒检查周期） | 看门狗：`已经 3.6s 没收到 /scan 了！` |
| 约 9.5 s | 连续读取失败超过 3 次，RUNNING → RESETTING | `[FSM] Hardware unresponsive (Over 3 errors). Resetting...` |
| 约 9.5 s | 重建驱动对象，2 秒后进入 CONNECTING | `[FSM] Performing hardware reset (recreating driver)...` |
| 约 11.7 s 起 | 约每 1 秒尝试一次重连，一直持续到插回 | 见下方"重连循环" |
| 36 s | 插回 USB | |
| 约 40.5 s（插回后 4.5 s） | 串口连上，识别到 C1 | `[FSM] Connection established.`、`Type: RPLIDAR C1` |
| 约 41.8 s（插回后 5.8 s） | 电机启动完成 | `[FSM] Motor started. Entering RUNNING state.` |
| 约 44 s（插回后 8.1 s） | 第一帧 `/scan` 发出 | 看门狗：`/scan 恢复了，中断约 42.6s。` |

要点：
- **拔掉后大约 10 秒驱动才确认掉线**：每次读取要等 SDK 超时（约 2 秒），超过 `max_retries`=3 次才进入 RESETTING。
  调小 `max_retries` 能更快确认，但偶尔的串口干扰也可能被误判成掉线。
- **插回后大约 8 秒恢复出数据**，分三段：
  1. 约 4.5 秒：插回后驱动每秒都在尝试，但前几次仍然失败，说明雷达自己上电启动要几秒才能应答。
     修复第 9.2 节前后都是约 4.5 秒，所以这段时间是雷达的，不是驱动的。
  2. 约 1.3 秒：电机预热。
  3. 约 2.2 秒：从进入 RUNNING 到第一圈数据（正常开机也一样）。
- `rpm` 等参数在重建驱动后会保留（日志里 `Target RPM` 仍是拔掉前设置的值）。
- 恢复全程节点一直是 `active`，看门狗没有做任何操作，恢复完全是驱动内部状态机完成的。
- 拔着 USB 期间，`ros2 lifecycle get /rplidar_node` 照常在约 0.9 秒内返回（见第 9.3 节）。

**重连循环（拔着的时候）的日志**

修复第 9.2 节之前，每一轮重连约 4 秒，日志会误导人：

```
[Driver] Failed to get device info (data may be corrupted).
[FSM] Connection failed. Retrying...
[Driver] Device Model ID: 0
[Driver] Detected legacy (A-series) device.          <- 并没有 A 系列雷达
[Hardware Detail] N/A (Not connected or permission denied)
[FSM] Health error: 2. Sending device reset...       <- 雷达根本不在，健康检查当然失败
[FSM] Health error: 2 after reset. Disconnecting...
```

修复后（实测），每秒重试一次，日志只有这两种：

```
[Driver] Failed to get device info (data may be corrupted).
[Driver] Failed to get device info (data may be corrupted).
[FSM] Connection failed. Retrying...
```

为什么 `Failed to get device info` 是两行一组？驱动每秒重试一次，每次都打印这一行；
而 `Connection failed. Retrying...` 用的是 `RCLCPP_WARN_THROTTLE(..., 2000, ...)`，最多每 2 秒打印一次。
所以每两次重试才看到一次 `Retrying...`。这是限频，不是重复打印的 bug。

其他注意：
- 插回去后设备名可能变成 `/dev/ttyUSB1`（比如旧的还没释放），这时驱动会一直连不上。解决办法：
  执行 `scripts/create_udev_rules.sh` 生成固定别名 `/dev/rplidar`，再用
  `ros2 launch rplidar_a2m12_teaching_driver a2m12.launch.py serial_port:=/dev/rplidar`。
  本次实测插回后仍是 `/dev/ttyUSB0`。
- 拔插期间看 `/diagnostics` 可以看到当前状态：`ros2 topic echo /diagnostics`。

---

## 5. 在线修改参数（不用重启节点）

| 参数 | 命令示例 | 取值 | 效果 |
|---|---|---|---|
| `rpm` | `ros2 param set /rplidar_node rpm 600` | 0~1200，0 = 型号默认 | 立即改变扫描频率（A2M12 实测 9.2~18.8 Hz）。**它是 PWM 值不是转速**，见下方 |
| `scan_mode` | `ros2 param set /rplidar_node scan_mode Standard` | 设备支持的模式名 | **会停电机再重启**，失败自动回到默认模式 |
| `auto_standby` | `ros2 param set /rplidar_node auto_standby true` | true/false | 没人订阅 `/scan` 时自动停电机 |
| `publish_point_cloud` | `ros2 param set /rplidar_node publish_point_cloud true` | true/false | 额外发布 `/cloud`（PointCloud2）。**注意：在线打开只翻转内部标志并打印日志，并不会立刻产生 `/cloud`** —— `cloud_pub_` 是 lifecycle 发布者，`on_activate()` 只在节点 ACTIVE 且该参数已为 true 时才调用。要真的出点云，先 `ros2 lifecycle set /rplidar_node deactivate` 再 `activate`，或重新 launch |
| 其他参数（`serial_port`、`frame_id` 等） | — | — | 运行中改了不生效，需要改 `param/a2m12.yaml` 后重新 launch |

- 驱动没连上雷达时（比如 USB 拔着），所有在线修改都会被拒绝：`Driver not ready`。
- 查看当前值：`ros2 param get /rplidar_node rpm`。

**A2M12 实测：调速有效，但 `rpm` 其实是 PWM 值**

2026-11-06 在本机 A2M12（FW 1.32 / HW 6）上做的 5 档扫频（`examples/rpm_sweep.sh`，每档稳定 8 s、测量 6 s）：

| 设定 `rpm` | `/scan` 实测 | 折算转速 ≈Hz×60 | 相对 600 档 |
|---|---|---|---|
| 0（驱动按 600 下发） | 11.932 Hz | 716 rpm | — |
| 480 | 9.231 Hz | 554 rpm | −22.6% |
| 600 | 11.892 Hz | 713 rpm | −0.3% |
| 720 | 14.673 Hz | 880 rpm | +23.0% |
| 900 | 18.821 Hz | 1129 rpm | +57.7% |

频率随设定值单调变化（极差 103.9%），所以 **A2M12 支持调速**。2026-11-07 复测趋势一致：480/600/720/900 → 8.89 / 11.26 / 14.15 / 18.13 Hz。
思岚 A2 系列官方资料标称扫描频率可调，典型范围 5–15 Hz（引用前请对照所用手册版本）；900 档的 18 Hz 已超出该范围。

**顺带量到的角分辨率**（`ros2 topic echo /scan --once --field angle_increment`，每圈点数 = 2π ÷ angle_increment）：

| 档位 | 每圈点数 | 角增量 | 点率 ≈点数×Hz |
|---|---|---|---|
| 600（默认） | **347** | 0.018107 rad | 4.13 k 点/s |
| 900 | **224** | 0.028050 rad | 4.22 k 点/s |

2026-11-07 同样设置复测：600 → 545 点/帧、900 → 343 点/帧，点率约 6.1–6.4 k 点/s。
两次绝对值不同是正常的：驱动丢弃距离为 0 的点，每帧点数取决于现场有效回波多少，表中数字是当场实测值，不是硬件常数。
同一场景下的规律不变：转速越高每圈点数越少，点率基本恒定，**瓶颈是硬件采样率**，
提速换来的是「圈数更多」而不是「数据更多」，代价是角分辨率变粗。这也是为什么 `computed_ray_count`
填上游那个 1450 对 A2M12 没有意义（一圈只有 347 点），所以本包把默认值改成了 **320**（见参数手册 3.9 节）。

**但别把 `rpm` 当转速读。** A2M12 是 A 系老协议，SDK 里判定为 `MotorCtrlSupportPwm`，
`setMotorSpeed(x)` 把 `x` 原样写进 `SL_LIDAR_CMD_SET_MOTOR_PWM` 的 `pwm_value` 字段——这个参数在 A 系上是
**PWM 占空比**，不是转/分。本机实测近似满足 `实际转速 ≈ 1.37 × 设定值 − 104 rpm`：

- 设 600 → 实测约 713 rpm（偏快 19%），所以默认配置下 `/scan` 是 11.9 Hz，不是标称的 10 Hz；
- 设 480 → 554 rpm；设 900 → 1129 rpm，已经超出 A2M12 额定转速，且每圈点数从 347 掉到 224（见下），只适合做实验。

想按真实转速标定，跑第 6 节的实验或直接 `ros2 run rplidar_a2m12_teaching_driver rpm_sweep.sh`。

**C1M1（上一代型号）实测：改了也不变**

| 设置的 rpm | `/scan` 实测频率 |
|---|---|
| 600 | 10.009 Hz |
| 480 | 10.004 Hz |
| 720 | 10.010 Hz |
| 360 | 9.997 Hz |
| 900 | 10.007 Hz |

每次 `param set` 都显示 `Set parameter successful`，驱动日志也打印 `Updating RPM to ...`，但雷达始终是 10 Hz（600 RPM）。
超出 0~1200 的值（比如 9999）会被拒绝：`RPM must be between 0 and 1200`。

细节（2026-11-07 读 SDK 源码后更正）：以前这里写"C1M1 走 `MotorCtrlSupportRpm` 分支、固件不执行"，这是错的。
SDK 在 `connect()` 里调用 `checkMotorCtrlSupport()`，按 Model ID 的**高 4 位**选调速通道：
高 4 位 ≥ 6 才走 `MotorCtrlSupportRpm`（发 `SL_LIDAR_CMD_HQ_MOTOR_SPEED_CTRL`），2~5 被当成 A2/A3 去探测 PWM 板。
C1 的 Model ID 是 65（0x41），高 4 位是 4，所以被归入 A 系分支，结果是 `None`（`setMotorSpeed()` 只切串口 DTR）或 `Pwm`（发 A 系的 `SET_MOTOR_PWM`）。
两种情况 C1 都收不到转速命令；而调速命令只发不等回应，SDK 仍返回 `SL_RESULT_OK`，这就是 `param set` "假成功"的来源。
也就是说，上表的 10 Hz 是**旧驱动**的结果，不能说明 C1M1 硬件不支持调速。

本包已在 `src/sdk/src/sl_lidar_driver.cpp` 的 `checkMotorCtrlSupport()` 里让 Model ID 0x41 强制走 `MotorCtrlSupportRpm`，
并在连接后打印 `[Driver] Model ID .. -> motorCtrlSupport = N`（0=None，1=PWM，2=RPM）。
**补丁后 C1M1 实测（2026-11-07）**：日志 `motorCtrlSupport = 2 (RPM)`，480/600/720/900 → 8.006 / 10.015 / 12.014 / 15.011 Hz，频率 ≈ rpm ÷ 60。

> ⚠️ **测频率别用不带 `--window` 的 `ros2 topic hz`。** 它对启动以来最多 10000 条消息求平均，改完 rpm 后
> 显示值要几分钟才慢慢靠近新值，看起来像电机"有很大惯性延迟"。改用 `examples/scan_probe.py`（按消息时间戳、每次重新统计），
> C1 设 480 后 5 秒内就是 8.01 Hz。改 rpm 后请用 `python3 examples/scan_probe.py 5` 或 `ros2 topic hz /scan --window 20`。
A2M12 走的是 `MotorCtrlSupportPwm` 分支，两条路径完全不同，所以换型号必须重做实验。

> ⚠️ **避坑：同一份 yaml 不要跨型号抄。** `rpm` 在 A 系是 PWM 占空比、在新协议是 rpm 指令、在 C1 上旧驱动根本没发出去（本包已修复，现为 rpm 指令）；
> 参数名一样，语义不一样。

**教训**：参数设置成功 ≠ 硬件真的变了。验证要看实际效果，不要只看命令返回值。

电机控制服务（不离开 active 状态，只停/启电机）：

```bash
ros2 service call /stop_motor  std_srvs/srv/Trigger
ros2 service call /start_motor std_srvs/srv/Trigger
```

---

## 6. 看门狗示例 `examples/scan_watchdog.py`

订阅 `/scan`，3 秒没数据就警告，然后查询驱动的 Lifecycle 状态再决定怎么做：

| 驱动状态 | 看门狗的动作 |
|---|---|
| active | 默认不插手：说明内层状态机正在重连，只提示检查 USB |
| active + `force_restart:=true` | 强制 deactivate → activate，演示手动重启生命周期 |
| inactive | 发送 activate |
| unconfigured | 发送 configure → activate（第 9.1 节的坑修好后才能成功） |
| 找不到节点 | 报错：驱动进程不在了 |

```bash
ros2 run rplidar_a2m12_teaching_driver scan_watchdog.py
ros2 run rplidar_a2m12_teaching_driver scan_watchdog.py --ros-args -p force_restart:=true
ros2 run rplidar_a2m12_teaching_driver scan_watchdog.py --ros-args -p timeout_sec:=5.0
```

动手实验：
1. 运行驱动和看门狗，执行 `ros2 lifecycle set /rplidar_node deactivate`，约 3 秒后看门狗会把它重新 activate。
2. 拔 USB：看门狗只会提示，不会动驱动；断流期间每 5 秒提醒一次，插回后打印一次 `/scan 恢复了，中断约 X s`。

看门狗里有一个值得注意的细节：`get_state` 是异步调用，回应可能来得很晚（第 9.3 节修复前实测超过 4 秒）。
如果回应到达时 `/scan` 已经恢复，这个回应就是过时的，代码会直接丢弃（见 `on_state()` 开头）。
写异步代码时要记得问：**回应回来的时候，世界是不是已经变了？**
3. 用 `force_restart:=true` 再执行 `ros2 service call /stop_motor std_srvs/srv/Trigger`：
   看门狗会强制 deactivate → activate，对照驱动终端里的 `[Lifecycle]` 日志看每一步做了什么。

---

## 7. 想改代码去哪儿

更完整的版本（含搜索关键词）见 [README_NEWBIE.md 第 3 节](README_NEWBIE.md)；每个函数为什么这么写见 [doc/CODE_NOTES_CN.md](doc/CODE_NOTES_CN.md)。

| 我想… | 去这里 |
|---|---|
| 理解整体流程 | `include/rplidar_node.hpp` 顶部 `DriverState` 的注释，配合 `doc/CODE_NOTES_CN.md` 第 1、2 节 |
| 改启动/暂停时做的事 | `src/rplidar_node.cpp` 的 `on_configure` / `on_activate` / `on_deactivate` |
| 改掉线重连的逻辑（重试次数、等待时间） | `src/rplidar_node.cpp` 的 `scan_loop()`，`CONNECTING` 和 `RESETTING` 两个 case |
| 改发布出去的 `/scan` 内容（角度、过滤、强度） | `src/rplidar_node.cpp` 的 `publish_scan()` |
| 加一个新参数 | `include/rplidar_node.hpp` 里的 `Parameters` 结构体 → `init_parameters()` → 需要在线改的话再加到 `parameters_callback()` |
| 改 A2M12 的默认配置（串口、frame_id） | `param/a2m12.yaml` |
| 改 RViz 显示（颜色、点大小、视角） | `rviz/a2m12.rviz`；或在 RViz 里调好后 File → Save Config As 另存，再用 `rviz_config:=` 加载 |
| 改 launch 默认值（是否开 RViz、默认串口） | `launch/a2m12.launch.py` 里的 `DeclareLaunchArgument` |
| 改和 SDK 打交道的代码（型号识别、开电机、读数据） | `src/lidar_driver_wrapper.cpp` |
| 改假雷达生成的数据 | `src/lidar_driver_wrapper.cpp` 里的 `DummyLidarDriver` |
| 看串口收数据的底层线程 | `src/sdk/src/sl_async_transceiver.cpp` 的 `_proc_rxThread` / `_proc_decoderThread`（SDK 代码，一般不要改；讲解见 `doc/CODE_NOTES_CN.md` 第 2 节） |

改完记得：`cd ~/A2M12_ros && colcon build --symlink-install && source install/setup.bash`。
Python 示例用了 `--symlink-install`，改完不用重新编译；C++ 改了必须重新编译。

---

## 8. 为什么用多线程（给新手的一段话）

`grab_scan_data()` 读串口是"阻塞"的：调用后要等雷达转完一圈、数据收齐才返回，
USB 被拔时还要等到超时（约 2 秒）。如果在主线程里读，这段时间节点没法处理参数修改、
服务调用和诊断信息，看起来就像卡死了。所以驱动把读取放到单独的 `scan_thread_` 里，
主线程一直保持能响应。

两个线程会同时用到雷达对象 `driver_`（读数据 vs 改转速），所以用 `driver_mutex_` 加锁，
保证同一时间只有一个线程在通过串口和雷达通信；跨线程的标志位用 `std::atomic`。

思岚 SDK 内部还有两个线程：`_rxThread` 从串口收字节放进队列 `_rxQueue`，
`_decoderThread` 从队列取出来解包成测量点。

---

## 9. 填坑记录

9.1 到 9.3 是本教学分支修掉的上游问题（代码位置汇总见第 12.2 节），每一条都写了现象、原因、修法和怎么验证。
9.4 不是 bug，是新同学经常问的一件事。

### 9.1 cleanup 之后无法再 configure

**现象**：执行 `deactivate → cleanup → configure`，configure 失败，驱动日志：

```
Original error: parameter 'serial_port' has already been declared
Callback returned ERROR during the transition: configure
```

**原因**：ROS 2 规定一个参数在节点里只能 `declare_parameter` 一次。上游的 `init_param()` 每次都直接 declare，
而 `on_configure()` 每次 configure 都会调用它。第一次 configure 没问题，第二次就抛异常。

**修法**（`include/rplidar_node.hpp` 的 `init_param()`）：

```cpp
if (this->has_parameter(name)) {
  variable = this->get_parameter(name).template get_value<T>();   // 已声明：只读
} else {
  variable = this->declare_parameter<T>(name, variable);          // 第一次：声明
}
```

顺带的好处：运行中用 `ros2 param set` 改过的值（比如 rpm），重新 configure 后会保留。

**同一个坑的第二处**：`diagnostic_updater_` 是成员变量，cleanup 不清空它，每次 configure 都会再注册一个
`RPLidar Status`，`/diagnostics` 里出现重复条目。修法是在 `on_configure()` 里先 `removeByName()` 再 `add()`。

**教训**：Lifecycle 节点的回调可能被调用很多次，写 `on_configure()` 时要问自己：
"这里做的事第二次再做一遍，会不会出问题？"

**怎么自己验证**：

```bash
ros2 lifecycle set /rplidar_node deactivate
ros2 lifecycle set /rplidar_node cleanup
ros2 lifecycle set /rplidar_node configure
ros2 lifecycle set /rplidar_node activate
ros2 lifecycle get /rplidar_node      # 应该是 active
```

---

### 9.2 拔着 USB 时，日志说雷达是 "A-series"，还报 "Health error"

**现象**（A2M12 真机，USB 拔着）：每轮重连约 4 秒，日志反复出现：

```
[Driver] Failed to get device info (data may be corrupted).
[FSM] Connection failed. Retrying...
[Driver] Device Model ID: 0
[Driver] Detected legacy (A-series) device.
[FSM] Health error: 2. Sending device reset...
[FSM] Health error: 2 after reset. Disconnecting...
```

**原因**（`src/lidar_driver_wrapper.cpp` 的 `RealLidarDriver::connect()`）：
1. `drv_->connect(channel)` 成功，SDK 内部的"已连接"标志 `_isConnected` 变成 true。
2. 接着 `getDeviceInfo()` 失败，函数 `return false`，但**没有断开**，`_isConnected` 还是 true。
3. 下一轮 `scan_loop()` 里 `isConnected()` 返回 true，状态机以为连着，跳过重连，
   拿全零的设备信息去识别型号（Model ID 0 → A 系列），再去做健康检查，最后给不存在的设备发复位命令。

**修法**：失败分支里补一行。

```cpp
  if (SL_IS_FAIL(res)) {
    ...
    drv_->disconnect();   // 连接没完成，就把"已连接"标志清掉
    return false;
  }
```

**教训**：一个函数做了好几步，中间某一步失败时，要把前面已经做成的步骤撤销掉（"回滚"）。
否则对象会处在"一半连上"的状态，后面的代码会被它骗。

**怎么验证**：拔掉 USB，日志里只应出现 `Failed to get device info` 和 `Connection failed. Retrying...`，
不应再出现 `A-series` 和 `Health error`；插回后应看到 `Type: RPLIDAR A2M12`（A2M12 的 Model ID 是 44 / 0x2C，代码里已有对应分支；其它 A 系型号才会打印 `A-Series (Triangulation)`）。

**实测结果**（A2M12，拔掉 36 秒）：

| | 修复前 | 修复后 |
|---|---|---|
| 拔着时每轮重连 | 约 4 秒 | 约 1 秒 |
| `A-series` / `Health error` / 复位命令 | 每轮都有 | 0 次 |
| 插回后到 `Connection established` | 4.6 秒 | 4.5 秒 |

插回后的时间几乎没变：这段时间主要是雷达自己上电启动（见第 4 节），驱动重试得再快也不会更快。
修复的收益是日志不再误导人，也不再对不存在的设备发复位命令。

### 9.3 拔着 USB 时，`ros2 lifecycle get` 要等好几秒

**现象**：拔掉 USB 后，看门狗向驱动发 `get_state` 请求，实测 4.2 秒才收到回应。
同一时间 lifecycle 命令、服务调用也都会卡住。

**原因**：三件事叠在一起。
1. 节点用 `SingleThreadedExecutor`：诊断定时器、`get_state` 服务、参数回调**全在同一个主线程**里排队执行。
2. `update_diagnostics()` 一开头就 `lock_guard(driver_mutex_)`。
3. 拔掉 USB 后，scan 线程拿着 `driver_mutex_` 在 `grab_scan_data()` 里等超时（约 2 秒一次），
   释放锁的时间极短又重新抢回去（见第 10 节）。

于是主线程卡在诊断回调里等锁，排在后面的 `get_state` 也跟着等。
而且 `update_diagnostics()` 根本不碰 `driver_`，它只读 atomic 变量、`params_` 和 `cached_device_info_`，
这把锁是多余的。更糟的是，scan 线程写 `cached_device_info_` 时本来就**没加锁**，所以这把锁也没保护到它。

**修法**：
- 删掉 `update_diagnostics()` 里的 `lock_guard(driver_mutex_)`。
- 新增一把只保护字符串的小锁 `info_mutex_`：scan 线程写 `cached_device_info_` 时加锁，诊断回调读的时候加锁。
  持有时间只有一次字符串拷贝，主线程不会被拖住。
- `params_.rpm` 只在参数回调里写，参数回调和诊断回调都在主线程里，不会同时执行，不需要加锁。

**教训**：第 8 节说"读串口单独开线程，主线程就不会卡"。但只要主线程去抢慢线程手里的锁，它照样会卡。
**锁要尽量小：只保护真正共享的数据，持有时间越短越好。**

**怎么验证**：先在雷达插着的时候执行一次 `time ros2 lifecycle get /rplidar_node`，记下耗时作为基准
（`ros2` 命令自己启动就要约 1 秒）。拔掉 USB 后马上再执行几次，耗时应该和基准差不多，不应再多出 2~4 秒。

**实测结果**（A2M12，用脚本连续执行 `ros2 lifecycle get` 两分钟，共 136 次）：

| 阶段 | 次数 | 平均耗时 | 最慢一次 |
|---|---|---|---|
| 拔掉之前 | 71 | 0.88 s | 1.21 s |
| 拔着 USB（含驱动等串口超时的前 10 秒） | 41 | 0.87 s | 0.89 s |
| 插回之后 | 24 | 0.88 s | 0.89 s |

拔着 USB 时和平时一样快。修复前同样的请求要等约 4.2 秒。
（拔掉之前有两次 1.21 s，是 `ros2` 命令自己偶尔慢一点，和驱动无关。）

### 9.4 关于 Contributors 列表里的 Claude

> 💡 细心的同学会发现，GitHub 贡献者列表里有一个 Claude 的头像。不用惊讶，它来自上游的 Git 历史。
>
> 上游贡献者 **Filip Szkudlarek** 在开发「待机模式」时用了 Claude 辅助，并在提交 `8ff33b0`（feat: Add standby mode）里如实写了出来：
> 提交信息末尾带有 `Co-authored-by: Claude Opus 5 <noreply@anthropic.com>`。GitHub 会把这种共同作者尾注计入贡献者列表，所以 Claude 就出现在了这里。
>
> 本仓库原样保留上游的全部提交，没有改写其中任何一个，因此这条记录也一起保留了下来。
> 如果为了去掉这个头像而改写 `8ff33b0`，它之后的所有提交都会换哈希，本仓库就没法再和上游对照、合并更新了。
>
> 顺带一提：上游的 `e41b573`、`72d9716` 也在正文里写了 `Generated-by: Anthropic Claude ...`，但那只是普通文字，不会产生贡献者条目。
> 这些都是上游作者自己的 AI 使用说明，与本教学分支的改动无关。
>
> 用了 AI 就在提交里写清楚，这也是现在越来越多开源项目的做法。

---

## 10. 已知限制

**`rpm` 在两代硬件上语义不同**：A2M12 调速有效，但参数是 PWM 占空比（设 600 实测约 713 rpm）；C1M1 旧驱动下无效，原因是内置 SDK 把 C1（0x41）误判成 A 系；本包已修复，C1 走 RPM 闭环，实测 480/600/720/900 → 8.01/10.02/12.01/15.01 Hz。见第 5 节。

**拔着 USB 时 `ros2 param set` 仍然要等几秒**
第 9.3 节的修复只让诊断回调不再抢 `driver_mutex_`。参数回调要通过 `driver_` 往串口发命令，必须持有这把锁，
所以拔着 USB 时改参数仍然要等 scan 线程读超时。`get_state`、lifecycle 命令和 `/diagnostics` 不受影响。

**留给你思考：scan 线程为什么"不让锁"**
`scan_loop()` 的 RUNNING 分支里，读取失败后的 `sleep_for(1ms)` 写在加锁的代码块**里面**。
scan 线程释放锁的时间极短，马上又去读串口、再等约 2 秒超时。`std::mutex` 不保证先来先得，
别的线程可能连续几轮都抢不到锁。试试把 sleep 移到锁外面，会有什么变化？会不会引入新问题？

---

## 11. 其他说明

- 本分支代码里有中文注释，上游仓库的 pre-commit 检查禁止非 ASCII 字符，所以这个分支不能直接给上游提 PR。
  如果要把第 9 节的修复贡献给上游，需要单独开一个只含英文的分支。

---

## 12. 本项目与上游原版的差异

对比基准：上游 [frozenreboot/rplidar_driver](https://github.com/frozenreboot/rplidar_driver) 的 `v1.4.2`
（commit `4446f8f`，即本仓库的 `main` 分支）。本节内容来自 `git diff main`。

**一句话**：驱动的核心架构（Lifecycle、scan 线程、状态机、SDK）一点没换；真正改动逻辑的是 3 处 bug 修复，
共新增 25 行、删除 9 行（不含注释）；本 A2M12 包在这之上再加 5 行型号名识别（见 12.2 最后一行）。其余都是新增的教学文件和中文注释。

### 12.1 完全新增的文件

| 文件 | 作用 |
|---|---|
| `README_CN.md` | 本文档 |
| `README_INSTALL.md` | 零基础安装指南：ROS 2 Humble、编译、`ROS_DOMAIN_ID`、串口权限、udev |
| `README_NEWBIE.md` | 新手导航：想做某件事该去哪个文件、哪个函数、搜哪个关键词 |
| `doc/PARAM_GUIDE_A2M12.md` | 参数调优手册：每个参数改了会怎样，含 A2M12 与 C1M1 两代实测数据与调速验证实验 |
| `doc/CODE_NOTES_CN.md` | 核心代码精读：`scan_loop`、`update_diagnostics`、`parameters_callback`、`publish_scan`、wrapper 层为什么这么写 |
| `param/a2m12.yaml` | A2M12 专用参数：波特率 256000、`/dev/ttyUSB0`、`frame_id: laser_a2m12`、`publish_tf: false`。原版 `param/rplidar.yaml` 不动 |
| `launch/a2m12.launch.py` | 一行命令启动驱动 + RViz。只在第一次 configure 后自动 activate 一次，不会撤销你手动的 deactivate/cleanup |
| `rviz/a2m12.rviz` | RViz 配置：俯视图、Fixed Frame `laser_a2m12`、网格、坐标轴、LaserScan（Best Effort） |
| `examples/scan_watchdog.py` | 看门狗示例：订阅 `/scan`，3 秒无数据就按 Lifecycle 状态处理（见第 6 节） |
| `examples/rpm_sweep.sh` | 调速验证脚本：逐档设 `rpm`、等稳定、测 `/scan` 频率并给判定（见参数手册第 6 节） |

### 12.2 改了逻辑的地方（重点看这里）

| 文件 | 函数 | 改了什么 | 为什么 |
|---|---|---|---|
| `include/rplidar_node.hpp` | `init_param()` | `declare_parameter` 前先 `has_parameter`，已声明就 `get_parameter` | 第 9.1 节：cleanup 后无法再 configure |
| `src/rplidar_node.cpp` | `on_configure()` | `diagnostic_updater_.add()` 前加 `removeByName("RPLidar Status")` | 第 9.1 节：重复的诊断条目 |
| `src/lidar_driver_wrapper.cpp` | `RealLidarDriver::connect()` | `getDeviceInfo()` 失败分支加 `drv_->disconnect()` | 第 9.2 节：误报 A-series |
| `include/rplidar_node.hpp` | 成员变量 | 新增 `std::mutex info_mutex_` | 第 9.3 节 |
| `src/rplidar_node.cpp` | `scan_loop()`，CONNECTING 分支 | 先写局部变量 `info`，再加 `info_mutex_` 写入 `cached_device_info_` | 第 9.3 节：原来写入时没加锁 |
| `src/rplidar_node.cpp` | `update_diagnostics()` | 删掉 `lock_guard(driver_mutex_)`；读 `cached_device_info_` 时加 `info_mutex_` | 第 9.3 节：主线程被串口超时堵住 |
| `launch/a2m12.launch.py` | 启动序列 | CONFIGURE 请求改成进程启动后延迟 3 秒再发（`TimerAction`） | 修启动竞态：launch_ros 在进程刚起时就调用 `change_state`，请求会卡在服务发现上，节点停在 `unconfigured`（同环境复现：C1M1 原包 5/5 卡住，延迟后 5/5 正常）。见 README_INSTALL 排错表 |
| `src/lidar_driver_wrapper.cpp` | `detect_and_init_strategy()`（老协议分支） | 加 `if (devinfo_.model == 0x2C) profile_.model_name = "RPLIDAR A2M12";` | 让启动日志与诊断直接显示 A2M12，而不是通用的 `A-Series (Triangulation)`。**这是本包相对 C1M1 教学包唯一新增的 C++ 改动（5 行）** |

关键代码一共就这些：

```cpp
// include/rplidar_node.hpp —— init_param()
if (this->has_parameter(name)) {
  variable = this->get_parameter(name).template get_value<T>();
} else {
  variable = this->declare_parameter<T>(name, variable);
}
std::mutex info_mutex_;                                   // 新成员

// src/rplidar_node.cpp —— on_configure()
diagnostic_updater_.removeByName("RPLidar Status");

// src/rplidar_node.cpp —— update_diagnostics()
- std::lock_guard<std::mutex> lock(driver_mutex_);        // 删掉
+ { std::lock_guard<std::mutex> info_lock(info_mutex_);
+   stat.add("Device Info", cached_device_info_); }

// src/lidar_driver_wrapper.cpp —— connect()
drv_->disconnect();                                       // getDeviceInfo 失败时
```

构建和配置文件（不影响驱动行为）：

| 文件 | 改动 |
|---|---|
| `CMakeLists.txt` | `install(DIRECTORY ...)` 里加 `rviz`；新增 `install(PROGRAMS examples/scan_watchdog.py ...)` |
| `package.xml` | 新增 `exec_depend`：`rclpy`（看门狗）、`rviz2`（launch 里的 RViz） |
| `.gitignore` | 忽略 `*.log`（真机测试日志） |

### 12.3 只加了注释、没动逻辑的地方

源码里**上游的英文注释全部保留**。中文只加在两类地方：状态机的一行简注（`[CN]`），和修过 bug 的位置（`[CN][fix]`，指向第 9 节）。
"为什么这么写"的长解释都放在 [doc/CODE_NOTES_CN.md](doc/CODE_NOTES_CN.md)。

| 文件 | 新增注释行数 | 注释在哪 |
|---|---|---|
| `include/rplidar_node.hpp` | 14 | `DriverState` 状态图和每个状态、4 个 `on_*` 回调各一行、`init_param` 和 `info_mutex_` 的修复说明 |
| `src/rplidar_node.cpp` | 12 | `scan_loop()` 开头一行指向文档、5 个 `case` 分支各一行、`on_configure` 和 `update_diagnostics` 的修复说明 |
| `include/lidar_driver_wrapper.hpp` | 11 | 接口抽象层（"插座和插头"）、Real / Dummy 两个实现 |
| `src/lidar_driver_wrapper.cpp` | 3 | `connect()` 的修复说明 |
| `src/sdk/` | 0 | 思岚 SDK 保持原样 |

> `git diff` 里 `DriverState` 枚举的 6 行显示为"删除 + 新增"，实际只是在每行末尾加了注释，枚举值和顺序都没变。
> 上表的注释行数包含修复位置旁边的英文和 `[CN][fix]` 注释（这些注释本身也不影响逻辑）。
> `param/rplidar.yaml` 保持上游原样；中文参数说明在 `param/a2m12.yaml` 和参数手册里。

### 12.4 自己动手看差异

```bash
cd ~/A2M12_ros/rplidar_a2m12_teaching_driver
git diff main --stat                      # 每个文件改了多少行
git diff main -- src/lidar_driver_wrapper.cpp   # 看某个文件的完整改动

# 只看改了逻辑的行（过滤掉注释和空行）。输出约 46 行，其中 12 行是 DriverState 枚举（只加了行尾注释）
git diff main -U0 -- src include | grep -E '^[+-]' | grep -vE '^(\+\+\+|---)' \
  | grep -vE '^[+-]\s*//' | grep -vE '^[+-]\s*$'
```

改动是**读代码的路线图**：先看 12.2 的 6 处，再对照第 9 节理解每处为什么要改；
其余代码按 12.3 的注释从 `include/rplidar_node.hpp` 的 `DriverState` 开始读。
