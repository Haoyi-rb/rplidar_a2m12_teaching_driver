# A2M12 教学级 ROS 2 驱动

![ROS2 Humble](https://img.shields.io/badge/ROS2-Humble-blue)
![Platform](https://img.shields.io/badge/Platform-Ubuntu%2022.04-orange)
![Status](https://img.shields.io/badge/Status-Stable-green)
![LiDAR](https://img.shields.io/badge/LiDAR-RPLIDAR%20A2M12-blueviolet)

> ⚠️ **本仓库是基于原版高性能驱动的二次开发版，专为思岚 A2M12 与新手教学定制。**
> 原版驱动的默认配置是给 S 系列用的（串口波特率 **1000000**），A2M12 用它**一个数据点都收不到**。
> 在 A2M12 上，**启动只认「🚀 唯一正确的启动方式」那一节**里的命令。

---

## 🔍 A2M12 vs C1M1：两代硬件差在哪（真机实测）

| 项目 | **A2M12（本包）** | C1M1（上一代教学包） |
|---|---|---|
| 型号 ID | 44（0x2C），日志 `Type: RPLIDAR A2M12` | 65（0x41） |
| 协议 | A 系三角测距，**老协议** | 新协议（TOF） |
| 波特率 | **256000** | 460800 |
| 量程 | 12 m | 12 m |
| `frame_id` | `laser_a2m12` | `laser` |
| 默认扫描频率 | **11.9 Hz**（设定 600 时实测） | 约 10.0 Hz |
| 调速（`rpm`） | **有效**，但参数是 **PWM 占空比**，不是转/分 | **有效**（RPM 闭环，≈ rpm÷60，实测 600 → 10.02 Hz；旧驱动因内置 SDK 误判型号而无效，已修复） |
| 掉线检测 | `max_retries: 3` → 拔线后约 9.5 s 判定（A2M12 未单独测） | 约 9.5 s（实测） |

结论：**同一个 `rpm` 参数在两代硬件上语义完全不同**——A2M12 是 PWM 占空比（频率会变），C1M1 是 rpm 指令（固件不理）。
换雷达要改的只有 `param/*.yaml` 里的 `serial_baudrate` 与 `frame_id`，代码不用动。

---

## 📚 文档导航

| 你的处境 | 该看哪份 |
|---|---|
| 第一次装 ROS 2、第一次编译、串口没权限 | **[零基础安装与配置指南](README_INSTALL.md)** |
| 想加功能、想改参数、不知道动哪个文件 | **[新手参数调优与代码导航](README_NEWBIE.md)** |
| 想了解真机拔插实测、踩过的坑、和上游的差异 | **[详细的真实拔插实测与填坑记录](README_CN.md)** |
| 想搞懂某个参数改了 RViz 会变成什么样 | [参数手册 doc/PARAM_GUIDE_A2M12.md](doc/PARAM_GUIDE_A2M12.md) |
| 想读核心函数为什么这么写 | [代码精读 doc/CODE_NOTES_CN.md](doc/CODE_NOTES_CN.md) |

推荐顺序：**安装 → 新手导航 → 中文说明**。这三份读完，你就能独立改这个驱动了。

---

## ⚠️ 硬件限制清单（调参之前先看）

下面这些是 **A2M12 的物理 / 固件限制，不是配置没生效**，别在它们身上耗时间：

| 限制 | 实测表现 | 怎么验证 |
|---|---|---|
| **`rpm` 是 PWM 占空比，不是转速**（A2M12 实测） | 5 档扫频：设 480/600/720/900 → 9.23 / 11.89 / 14.67 / 18.82 Hz，**会变，但不是 rpm÷60** | `ros2 topic hz /scan`，见参数手册第 6 节 |
| **C1M1 旧驱动下调速无效**（已修复） | 内置 SDK 按 Model ID 高 4 位选调速通道，C1（65 = 0x41，高 4 位是 4）落进 A2/A3 的 PWM 探测分支，不发 `HQ_MOTOR_SPEED_CTRL`，`param set` 却返回成功。补丁后实测 480/600/720/900 → 8.01/10.02/12.01/15.01 Hz | 启动日志 `motorCtrlSupport = 2 (RPM)` + `examples/scan_probe.py` |
| RPM 取值范围 0~1200 | 超出（如 9999）被参数回调拒绝：`RPM must be between 0 and 1200` | `ros2 param set /rplidar_node rpm 9999` |
| 串口波特率固定 256000 | 用 1000000（上游默认）一个点都收不到，SDK 报数据可能损坏 | `ros2 param get /rplidar_node serial_baudrate` |
| 在线开 `publish_point_cloud` 不生效 | 只翻标志位、打印日志，`/cloud` 不会出现，需 deactivate → activate | `ros2 topic list \| grep cloud` |

> ✅ **A2M12 调速有效（2026-11-06 实测）**：`rpm` 从 480 到 900，`/scan` 从 9.23 Hz 变到 18.82 Hz。
> ⚠️ 但 A 系这个参数是 **PWM 占空比**（`SL_LIDAR_CMD_SET_MOTOR_PWM`），不是转/分：设 600 实测约 713 rpm。
> ✅ C1M1 打补丁后调速同样有效，而且走 RPM 闭环，频率 ≈ rpm÷60（480/600/720/900 → 8.01/10.02/12.01/15.01 Hz）；A2M12 是开环 PWM，数值不等于转速。

完整实测数据（两代对照）见 [README_CN.md 第 5 节](README_CN.md)。

---

## ⚙️ 进阶操作：改转速（A2M12 真的会变，但单位不是 rpm）

```bash
ros2 param set /rplidar_node rpm 480      # 频率会变，但 480 不是"480 转/分"
ros2 param set /rplidar_node rpm 0        # 恢复默认（驱动按 600 下发）
```

**A2M12 实测（FW 1.32 / HW 6，2026-11-06，脚本 `ros2 run rplidar_a2m12_teaching_driver rpm_sweep.sh`，每档稳定 8 s、测 6 s）**：

| 设定 `rpm` | `/scan` 实测 | 折算转速 ≈Hz×60 | 相对 600 档 |
|---|---|---|---|
| 0（驱动按 600 下发） | 11.932 Hz | 716 rpm | — |
| 480 | 9.231 Hz | 554 rpm | −22.6% |
| 600 | 11.892 Hz | 713 rpm | −0.3% |
| 720 | 14.673 Hz | 880 rpm | +23.0% |
| 900 | 18.821 Hz | 1129 rpm | +57.7% |

**结论两条**：

1. **A2M12 的调速是有效的**——频率确实跟着设定值单调变化（极差 103.9%）。2026-11-07 复测趋势一致（480/600/720/900 → 8.89/11.26/14.15/18.13 Hz）。
2. **但 `rpm` 这个参数在 A 系上不是转速**：SDK 把它判为 `MotorCtrlSupportPwm`，走
   `SL_LIDAR_CMD_SET_MOTOR_PWM`，参数值被原样填进 `pwm_value` 字段——你填的是 **PWM 占空比**。
   所以 `600` 换来的不是 600 转/分，本机实测约 713 转/分；近似关系是
   `实际转速 ≈ 1.37 × 设定值 − 104`。想按真实转速标定，只能自己跑脚本记表
   （[doc/PARAM_GUIDE_A2M12.md 第 6 节](doc/PARAM_GUIDE_A2M12.md)）。

**用法建议**：默认留 `0`（=600，本机约 11.9 Hz）；要提帧率最多试到 `720`（约 14.7 Hz）；
`900`（约 18.8 Hz）已超出 A2M12 额定转速，且每圈点数从 347 掉到 224（见下表），只适合实验，别写进产品配置。
在线改转速不会自动改 `computed_ray_count`，参数回调只打一句警告。

**顺带量到的角分辨率**（同一次实验，`ros2 topic echo /scan --once --field angle_increment`，每圈点数 = 2π ÷ angle_increment）：

| 档位 | 每圈点数 | 角增量 | 点率 ≈点数×Hz |
|---|---|---|---|
| 600（默认） | **347** | 0.018107 rad | 4.13 k 点/s |
| 900 | **224** | 0.028050 rad | 4.22 k 点/s |

2026-11-07 复测同样设置：600 → 545 点/帧、900 → 343 点/帧，点率约 6.1–6.4 k 点/s。
**两次的绝对值不同是正常的**：驱动会丢掉距离为 0 的点（`interpolated_rays` 关闭时），每帧点数取决于现场有多少有效回波。
上面的数字只是当场的实测值，不是硬件常数。不变的规律是：同一场景下，转速越高，**每圈点数越少**，而点率基本恒定，
说明瓶颈是硬件采样率：**提帧率不会让你多拿数据，只会把同样的点摊到更多圈上，角分辨率变粗**。
想同时要高帧率和高角分辨率，只能开 `interpolated_rays`，但那部分点是插值算出来的，不是测出来的。

> **C1M1 对比**：旧驱动下参数同样被接受、日志同样打印 `Updating RPM to ...`，但 `/scan` 恒在 10 Hz（360~900 全部 ≈10.00 Hz）。
> 原因是内置 SDK 的 `checkMotorCtrlSupport()` 只有 Model ID 高 4 位 ≥ 6 才选 RPM 通道，C1（0x41）高 4 位是 4，
> 被当成 A2/A3 去探测 PWM 板，`setMotorSpeed()` 因此从不发 `HQ_MOTOR_SPEED_CTRL`。
> 本包已在 `src/sdk/src/sl_lidar_driver.cpp` 让 C1 强制走 RPM 通道，实测 480/600/720/900 → 8.01/10.02/12.01/15.01 Hz。
> 同一个参数名在两代硬件上语义完全不同，别互相对抄。

## ✅ 怎么确认真的跑起来了

```bash
ros2 node list                    # 应看到 /rplidar_node
ros2 lifecycle get /rplidar_node  # 应显示 active
ros2 topic hz /scan               # 本机 A2M12 实测约 11.9 Hz；C1M1 实测约 10 Hz
```

RViz 里应看到一圈激光点，Fixed Frame 用 `laser_a2m12`（`a2m12.launch.py` 默认帮你打开这份 RViz 配置）。

---

## 🚫 不要用这些命令（它们来自上游，对 A2M12 无效）

```bash
ros2 launch rplidar_a2m12_teaching_driver rplidar.launch.py             # ✗ 加载 param/rplidar.yaml，波特率 1000000
ros2 launch rplidar_a2m12_teaching_driver rplidar_with_args.launch.py   # ✗ 同上
ros2 launch rplidar_a2m12_teaching_driver composition.launch.py         # ✗ 上游组件化示例，未配 A2M12 参数
ros2 run rplidar_a2m12_teaching_driver rplidar_node                     # ✗ 不带参数档，全用上游默认值
```

**典型症状**：命令不报错、节点也起来了，但 `ros2 topic hz /scan` 一直没输出——
因为 A2M12 是以 256000 会话的，听不懂按 1000000 波特率发出的指令。

上游原始英文 README 已存档到 [doc/UPSTREAM_README_EN.md](doc/UPSTREAM_README_EN.md)，仅供对照，其中的命令同样不适用于 A2M12。

---

## 📄 许可与来源

本仓库基于 [frozenreboot/rplidar_driver](https://github.com/frozenreboot/rplidar_driver) v1.4.2 修改，
沿用上游同样的许可证（见 [LICENSE](LICENSE)）。

本包由 C1M1 教学包 [`rplidar_c1m1_teaching_driver`](https://github.com/Haoyi-rb/rplidar_c1m1_ros_teaching_driver) 完整复制后派生：包名重命名 + 新增 A2M12 参数档与启动文件，底层驱动代码和 3 个 bug 修复保持原样；相对 C1M1 包唯一新增的 C++ 改动是 5 行型号名识别（`model == 0x2C` → `RPLIDAR A2M12`），见 [README_CN.md 第 12.2 节](README_CN.md#122-改了逻辑的地方重点看这里)。
上游作者与贡献者名单见 [README_CN.md](README_CN.md) 开头；GitHub Contributors 面板里为何会出现一个 AI 条目：见 [README_CN.md 第 9.4 节](README_CN.md#94-关于-contributors-列表里的-claude)。
