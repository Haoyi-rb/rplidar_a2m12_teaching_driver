# A2M12 参数调优手册（写给第一次碰雷达的同学）

[README.md](../README.md) · [安装](../README_INSTALL.md) · [新手导航](../README_NEWBIE.md) · [中文说明](../README_CN.md) · **参数手册** · [代码精读](CODE_NOTES_CN.md)

> 本手册里标【A2M12 实测】的是 A2M12（FW 1.32，HW 6，2026-11-06）的真机数据，标【C1M1 实测】的是上一代 C1M1（FW 1.2，HW 18）的数据；测试过程见 [README_CN 第 4、5 节](../README_CN.md)。

## 0. 三十秒看懂：数据怎么走、参数分几层

数据流（一条线，从左到右）：

    雷达转一圈 --> 串口吐出角度+距离 --> 驱动节点 rplidar_node --> 话题 /scan --> RViz 画点
      ↑ 硬件层                            ↑ 驱动层                        ↑ ROS 层

三层调参（改哪一层，后果就落在哪一层）：

| 层 | 管的是什么 | 包含的参数 | 改错的后果 |
|---|---|---|---|
| 硬件层 | 跟雷达“商量”：说什么语言、转多快、用哪个预设 | `serial_baudrate` `rpm` `scan_mode` | 波特率不对直接连不上；`rpm` 在 A2M12 上是 PWM 占空比（频率会变，但不等于转速），在 C1M1 上旧驱动没把命令发出去，本包已修复，C1 现为 RPM 闭环（见第 6 节） |
| 驱动层 | 怎么整理数据：角度怎么摆、切成多少根光束、多远算有效 | `angle_compensate` `interpolated_rays` `computed_ray_count` `max_distance` `angle_offset` `symmetric_angle_range` `use_intensities` `intensities_as_angles` | 雷达照转，但 `/scan` 里的数字会变样，甚至被悄悄改难 |
| ROS 层 | 怎么把数据发出去：叫什么帧、谁收得到、要不要多发一份点云 | `frame_id` `publish_tf` `qos_policy` `publish_point_cloud` | 雷达和数据都对，RViz 却一片空白（订阅不上） |

记住一件事：**RViz 里看到什么都不算数，只有 `/scan` 里的数字算数**。RViz 只是个显示器。

## 1. 术语速查（后面会反复用到）

| 词 | 人话解释 |
|---|---|
| 节点 node | 后台跑的一个小程序。本仓库里 `rplidar_node` 就是负责跟雷达说话的那个。 |
| 话题 topic | 节点之间传数据的“广播频道”，有名字（比如 `/scan`）。 |
| 发布 / 订阅 | 往频道里喊话叫发布；打开收音机去听叫订阅。 |
| 消息 message | 频道里传的数据包，格式是事先定好的。 |
| LaserScan | ROS 2 定好的一种格式：一圈分成若干“光束”，每根光束记一个角度和一个距离。 |
| 光束 ray / beam | 就是把一圈圆切成多少份。`/scan` 里 `ranges` 数组的长度就是光束数。 |
| PointCloud2 | 另一种格式：一堆三维点 (x, y, z)。本驱动能把同一圈数据换个格式再发一遍。 |
| RViz | 一个可视化窗口程序，订阅话题把点画出来。它不产生数据，也不修数据。 |
| QoS | “这个频道怎么送数据”的约定：丢不丢帧、要不要重发、缓存几条。 |
| TF | 坐标变换，回答“雷达装在车上的哪儿、朝哪个方向”。 |
| 串口 | 电脑和雷达之间那根线（USB 转出来的），在 Linux 里是个叫 `/dev/ttyUSB0` 的文件。 |
| 波特率 baudrate | 串口每秒传输的快慢。两边填的数不一样，收到的就是一串乱码。 |
| RPM | 每分钟转多少圈。雷达转得越快，每秒扫的圈数越多。 |
| scan_mode | 厂商给的几种出厂预设（如 Standard、DenseBoost），决定采样密度等。 |
| 扫描频率 Hz | 每秒出几帧数据。10 Hz 就是每秒 10 帧 `/scan`。 |
| 诊断 diagnostics | ROS 2 的健康报告机制：`/diagnostics` 话题上定期发一段“我好不好”。 |

## 2. 参数总表

### 2.1 `param/a2m12.yaml` 的 19 个参数（一个不漏，也没有多余的）

| 参数名 | 默认值 | 单位 | 一句话作用 | 改“大”以后 RViz 会看到什么 | 改“大”以后物理雷达会怎样 | 风险 |
|---|---|---|---|---|---|---|
| `serial_port` | `/dev/ttyUSB0` | 无（设备文件路径） | 去哪个串口找雷达 | 改成别的端口，画面立刻空白；它没有“大”可言，只有“对不对” | 完全无影响，只是没人跟它说话了 | 高 |
| `serial_baudrate` | 256000 | bit/s | 串口通信速度，必须与型号匹配 | 填错时 RViz 一直空白，终端打出打不开串口或设备信息损坏 | 电机可能照样转，但两边语言不通，驱动收不到数据 | 高 |
| `frame_id` | `laser_a2m12` | 无（坐标系名） | 给这帧数据盖上“我属于哪个坐标系”的戳 | 改成一个 RViz 里不存在的名字，RViz 报错、点全消失 | 无影响 | 中 |
| `angle_compensate` | true | 布尔 | 是否让厂商 SDK 顺手做角度校正/排序 | 关掉后点可能不再均匀铺开，局部出现重影或空洞 | 无影响（纯软件开关） | 低 |
| `scan_mode` | `Standard` | 无（模式名） | 选雷达的一个出厂采样预设 | 换成 DenseBoost 后一圈点数变多、画面更密，但可能多出“编造”的点 | 雷达内部真的切换采样策略，功耗与发热跟着变 | 中 |
| `rpm` | 0 | PWM 占空比（名字叫 rpm） | 电机驱动量；0 表示“用固定默认 600” | 【A2M12 实测】480/600/720/900 → 9.23/11.89/14.67/18.82 Hz（≈554/713/880/1129 rpm） | 【A2M12 实测】会变、但不是 1:1 的转速；【C1M1 实测】旧驱动恒 10 Hz（SDK 未发命令）；补丁后 480/600/720/900 → 8.01/10.02/12.01/15.01 Hz | 中 |
| `auto_standby` | false | 布尔 | 没人订阅 `/scan` 时自动停电机 | 打开后一关 RViz 雷达就停，再开 RViz 后第一秒画面是空的 | 电机在不被需要时真的停下来，省寿命；唤醒要等加速 | 低 |
| `interpolated_rays` | false | 布尔 | 是否用固定间隔的“假想光束”重算每个距离 | 打开后画面变成规整的一圈、墙角更尖锐，但也更“假” | 无影响 | 中 |
| `computed_ray_count` | 320（本包；上游默认 1450） | 根（每圈光束数） | 开插值时，一圈切成多少根光束 | 调大画面更细密、点间距更小；数据量、CPU 也跟着涨 | 无影响 | 高 |
| `use_intensities` | false | 布尔 | 是否填充回波强度数组 | 打开后如果 RViz 按强度上色，颜色会有层次；关掉是单色 | 无影响 | 低 |
| `max_distance` | 12.0（A2M12 量程） | m（米） | 只在消息里声明“最远多少米算有效” | 调大后 RViz 不再自动裁掉远处的点；但不会凭空长出点 | 无影响（它不裁剪真实数据，见坑） | 低 |
| `dummy_mode` | false | 布尔 | 用程序编的假数据代替真雷达 | 打开后照样有点，但是一圈人造圆环，每帧只有 360 个点 | 雷达完全不参与，甚至可以不插线 | 高 |
| `publish_tf` | false | 布尔 | 是否由本节点发一条 `base_link -> laser_a2m12` 的静态坐标变换 | 打开后 RViz 用 `base_link` 当 Fixed Frame 也能显示 | 无影响 | 中 |
| `qos_policy` | `sensor_data` | 无（三选一字符串） | 选 `/scan` 的传输规矩 | 换成可靠传输后不丢帧但延迟变大；填错值会让订阅方根本收不到 | 无影响 | 高 |
| `max_retries` | 3 | 次（连续失败次数） | 连续读失败多少次就判定硬件掉线 | 调大后拔线要等更久才报错，RViz 定格更久。【C1M1 实测，A2M12 未验证】设 3 时约 9.5 秒 | 无影响 | 中 |
| `angle_offset` | 0.0 | rad（弧度） | 给所有角度统一加一个偏移，纠正零位偏差 | 改大后整幅画面绕中心旋转同一个角度，形状不变 | 无影响 | 中 |
| `symmetric_angle_range` | false | 布尔 | 角度区间报成 [0, 2π) 还是 [-π, π) | 打开后 `angle_min` 变成 -3.14，下游角度过滤器才不会砍掉一半 | 无影响 | 中 |
| `publish_point_cloud` | false | 布尔 | 是否额外发一个 `/cloud` 话题 | 打开后 RViz 可以加 PointCloud2 显示，但带宽和 CPU 翻倍 | 无影响 | 中 |
| `intensities_as_angles` | false | 布尔 | 把硬件原始角度塞进 intensities 当调试信息 | 画面不变，但 intensities 里存的不再是强度而是角度，按强度上色会全乱 | 无影响 | 低 |

### 2.2 `launch/a2m12.launch.py` 的 6 个参数

| 参数名 | 默认值 | 单位 | 一句话作用 | 改“大”以后 RViz 会看到什么 | 改“大”以后物理雷达会怎样 | 风险 |
|---|---|---|---|---|---|---|
| `params_file` | 安装目录下 `param/a2m12.yaml` | 路径 | 用哪一份参数文件 | 换一份文件等于换掉上面 19 个值，现象可能全变 | 波特率不同时会直接连不上 | 中 |
| `serial_port` | `/dev/ttyUSB0` | 路径 | 覆盖 yaml 里的串口 | 改错立刻空白 | 无影响 | 高 |
| `dummy_mode` | false | 布尔 | 覆盖 yaml 里的假数据开关 | 见 2.1 对应行 | 雷达不参与 | 高 |
| `publish_tf` | false | 布尔 | 覆盖 yaml 里的 TF 开关 | 见 2.1 对应行 | 无影响 | 中 |
| `rviz` | true | 布尔 | 是否顺手打开 RViz | `false` 时根本没有窗口，只有终端日志 | 雷达照转，数据照发 | 低 |
| `rviz_config` | 安装目录下 `rviz/a2m12.rviz` | 路径 | RViz 用哪份配置 | 换配置可能 Fixed Frame 或 QoS 不匹配，看到空白 | 无影响 | 低 |

### 2.3 两个服务与 `/diagnostics` 的关键字段

| 名字 | 类型 | 一句话作用 | 调用后 RViz 会看到什么 | 物理雷达会怎样 | 风险 |
|---|---|---|---|---|---|
| 服务 `stop_motor` | `std_srvs/Trigger` | 让电机停下，串口保持连接 | 画面定格在最后一帧，不再更新 | 电机停转，激光灯可能还亮但不出数据 | 低 |
| 服务 `start_motor` | `std_srvs/Trigger` | 让电机重新转起来 | 画面恢复更新，头一两帧可能不全 | 电机重新加速，会有短暂启动噪音 | 低 |

`/diagnostics` 上每个周期报一条状态，`HardwareID` 是 `rplidar-<串口路径>`，关键字段：

| 字段 | 可能出现的内容 | 怎么读 |
|---|---|---|
| 状态摘要 + 级别 | `Scanning`(OK) / `Warming Up`(WARN) / `Connecting`(WARN) / `Hardware Error / Resetting`(ERROR) / `Standby (motor off)` / `Standby (auto: no subscribers)` / `Node Inactive` | 这是最快的健康检查：不是 OK 就别去看 RViz |
| `Lifecycle State` | `Inactive` | 只在节点没被 activate 时出现，说明连接收线都没开始 |
| `Connection` | `Connected` / `Connecting...` / `Disconnected / Resetting` / `Connected (Motor Stopped)` | 串口到底打开没有 |
| `Health Code` | `OK (Scanning Active)` / `Warming Up` / `Error` / `OK (Standby)` | 雷达自检的结论 |
| `Standby Trigger` | `auto_standby` 或 `stop_motor` | 待机是谁引起的，排查“为什么不动”时关键 |
| `Serial Port` | 当前使用的串口路径 | 确认 launch 的覆盖真的生效了 |
| `Target RPM` | 例如 `0` 或 `900` | 注意 `0` 表示“交给固定默认 600”，不是“不转” |
| `Device Info` | `S/N: ... \| FW: ... \| HW: ...`，或 `N/A (Not connected or permission denied)` | 出现 N/A 就是串口权限或线的问题 |
| `Auto Standby` | `ON` / `OFF` | 与 `Standby Trigger` 配合看 |

依据: src/rplidar_node.cpp 的 on_configure 函数（搜索关键词 `diagnostic_updater_.removeByName`）与 update_diagnostics 函数（搜索关键词 `Node Inactive`）；src/lidar_driver_wrapper.cpp 的 get_device_info_str 函数（搜索关键词 `S/N:`）

## 3. 逐参数详解

每一节都是四段：**(a) 它控制什么 → (b) 怎么验证真的生效 → (c) 调大/调小的现象与代价 → (d) 坑**。末尾附依据。

### 3.1 `serial_port`

**(a)** 就是告诉节点“去哪个文件跟雷达说话”。插拔 USB 后编号会变（这次是 `ttyUSB0`，下次可能是 `ttyUSB1`），所以这里填死一个值是有风险的。

**(b)** 先看系统里有没有这个设备，再看节点日志里有没有 `Connection established`：

     ls /dev/ttyUSB*
     ros2 launch rplidar_a2m12_teaching_driver a2m12.launch.py serial_port:=/dev/ttyUSB1
     ros2 topic echo /diagnostics --once | grep -A2 'Device Info'

**(c)** 填错端口时：日志反复出现 `Connection failed. Retrying...`，`/diagnostics` 停在 `Connecting`，RViz 空白。填对时：日志出现 `Connection established`，随后 `Max Range: ...`。代价是没有代价，纯粹别填错。

**(d)** 坑一：`dummy_mode:=true` 时这个参数完全不看，所以“dummy 能跑、真机不能跑”说明问题在串口而不在参数文件。坑二：不动 `/dev/ttyUSB0` 的权限会在打开串口时直接失败（源码提示 `sudo chmod 666`）。

关联参数：`serial_baudrate`（同一个串口的另一半）。

依据: src/rplidar_node.cpp 的 on_configure 函数（搜索关键词 `Initial connection failed at`）与 scan_loop 函数（搜索关键词 `[FSM] Connection established`）；src/lidar_driver_wrapper.cpp 的 connect 函数（搜索关键词 `Failed to open serial port`）

### 3.2 `serial_baudrate`

**(a)** 串口的速度。两边（电脑、雷达）必须填同一个数，否则收到的字节全部对不上。A2M12 是 256000，这是型号决定的，不是你随便挑的性能选项。

**(b)** 改完重启节点，看启动日志里有没有设备型号和序列号；没有就是波特率错：

     ros2 topic echo /diagnostics --once
     ros2 param get /rplidar_node serial_baudrate

**(c)** 这个参数只有“对/错”没有“大小”。填错的表现有两种：串口能打开但拿不到设备信息（日志 `Failed to get device info (data may be corrupted).`），或者串口连打开都失败。两者都让 RViz 永久空白。

**(d)** 坑：把 `param/rplidar.yaml` 的 1000000 抄到 A2M12 上是新手最常犯的错——那个 1000000 是 S2/S3 的。型号对照见第 5 章。

关联参数：`serial_port`。

依据: param/rplidar.yaml 中「serial_baudrate」的注释段（搜索关键词 serial_baudrate）；src/lidar_driver_wrapper.cpp 的 connect 函数（搜索关键词 `Failed to bind connection with device`）；src/rplidar_node.cpp 的 on_configure 函数（搜索关键词 `Initial connection failed at`）

### 3.3 `frame_id`

**(a)** 每条 `LaserScan` 消息头上都有个坐标系名字，RViz 靠它决定“这些点该贴在哪儿、怎么跟着车动”。`frame_id` 就是给数据盖章。

**(b)** 直接读消息头，并跟 RViz 的 Fixed Frame 对一下：

     ros2 topic echo /scan --once --field header.frame_id
     ros2 run tf2_tools view_frames      # 看有没有 laser_a2m12 这个坐标系

**(c)** 它不是数字，谈不上调大调小。改错（比如写成 `laser_frame`，但 RViz 的 Fixed Frame 是 `laser_a2m12`）时，RViz 会红字报错，点一个都不显示——这是最容易被误判成“雷达坏了”的情况。

**(d)** 坑：本仓库的 `rviz/a2m12.rviz` 已经把 Fixed Frame 固定成 `laser_a2m12`，两边必须一致。改了 `frame_id` 还要在 RViz 里手动改 Fixed Frame，或者干脆改回 `laser_a2m12`。

关联参数：`publish_tf`。

依据: src/rplidar_node.cpp 的 publish_scan 函数（搜索关键词 `scan_msg.header.frame_id`）；rviz/a2m12.rviz:84-85、78-80

### 3.4 `angle_compensate`

**(a)** 把“要不要做角度校正”这个开关整个交给厂商 SDK。开着时驱动会在读完一圈后调用 SDK 的角度校正函数；关掉就原样使用 SDK 返回的顺序。

**(b)** 看启动报告里那一行：

     ros2 param get /rplidar_node angle_compensate
     # 启动日志里 Geo. Comp. : ON (SDK managed) / OFF (raw data)

**(c)** 关掉后可能出现点排列不均、窄处有重影。代价是画面质量下降，好处是少一次 SDK 处理、稍省 CPU。

**(d)** 坑：别把它当成“角度偏了”的补救手段——角度整体偏了要用 `angle_offset`。这里只是 SDK 的内部处理开关。SDK 内部具体做了什么，源码里只看到一次调用，细节需查 Slamtec SDK 文档（未验证）。

关联参数：`angle_offset`（真正管角度对齐的那个）。

依据: src/lidar_driver_wrapper.cpp 的 connect 函数（搜索关键词 `apply_geometric_correction`）、grab_scan_data 函数（搜索关键词 `ascendScanData`）、print_summary 函数（搜索关键词 `Geo. Comp.`）

### 3.5 `scan_mode`

**(a)** 选雷达的一个出厂预设。雷达自己会上报它支持哪些模式名，驱动拿你填的名字去里面找；找不到就退回自动选择（优先 DenseBoost，其次 Sensitivity）。

**(b)** 启动日志会打印 `Active Mode : ...`，以它为准，不以你的 yaml 为准：

     ros2 param get /rplidar_node scan_mode
     # 启动日志：Active Mode : Standard

> ⚠️ **A2M12（老协议）例外**：上面的模式匹配只在新协议分支里做。老协议分支在 `lidar_driver_wrapper.cpp` 里直接调用
> `startScan(0, 1)`（`useTypicalScan = true`），用的是雷达固件的典型模式；日志里的 `Active Mode : Standard`
> 是代码写死的字符串，不是雷达上报的。所以在 A2M12 上 `scan_mode` 填什么都不影响实际扫描，日志里那一行也不能当作证据。

**(c)** 换成 DenseBoost 这类模式后，一圈点数变多、画面更密，代价是带宽上升，而且可能多出硬件“插值”出来的点，让测距看起来比实际更准。Standard 更保守。

**(d)** 坑一：模式名写错不会报错退出，只会打一行 `Scan mode 'X' not found. Falling back to automatic selection.` 然后偷偷换成别的模式——你以为改了，其实没改。坑二：在线切换模式会让雷达重启一次（停电机、等 0.5 秒、再启动），中间那几秒没有数据。

关联参数：`interpolated_rays`、`computed_ray_count`（开了插值就别再用 DenseBoost，否则等于插两次）。

依据: src/rplidar_node.cpp 的 parameters_callback 函数（搜索关键词 `Switching scan mode to`）；模式匹配与回退 src/lidar_driver_wrapper.cpp 的 start_motor 函数（搜索关键词 `DenseBoost`）；param/rplidar.yaml 中「scan_mode」的注释段（搜索关键词 scan_mode）

### 3.6 `rpm`

**(a)** 电机转速，单位转/分。`0` 不是“不转”，而是“用默认值 600 转/分”（驱动把 0 换成 600 下发）。
理论上扫描频率 = rpm ÷ 60，600 转对应 10 Hz。

**(b)** 怎么看：

     ros2 param get /rplidar_node rpm                          # 参数里的值
     ros2 topic echo /diagnostics --once | grep 'Target RPM'   # 驱动以为的值
     ros2 topic hz /scan                                       # 雷达真实的转速（唯一可信）

前两个只是“驱动记下来的数”，第三个才是雷达真的转了多快。

**(c)** 【A2M12 实测 2026-11-06，FW 1.32 / HW 6】**会变，但变的不是 rpm。** 5 档扫频（`examples/rpm_sweep.sh`）：

| 设定值 | `/scan` 实测 | 折算转速 ≈Hz×60 |
|---|---|---|
| 0（驱动按 600 下发） | 11.932 Hz | 716 rpm |
| 480 | 9.231 Hz | 554 rpm |
| 600 | 11.892 Hz | 713 rpm |
| 720 | 14.673 Hz | 880 rpm |
| 900 | 18.821 Hz | 1129 rpm |

频率随设定值单调上升（极差 103.9%），所以 **A2M12 支持调速**；但折算转速和设定值对不上，
近似 `实际转速 ≈ 1.37 × 设定值 − 104 rpm`。

**(d)** 为什么是 PWM 而不是 rpm：A 系（含 A2M12）在 SDK 里被判为 `MotorCtrlSupportPwm`，
`setMotorSpeed(x)` 把 `x` 原样写进 `SL_LIDAR_CMD_SET_MOTOR_PWM` 的 `pwm_value`——参数值就是占空比。
只有新协议型号（S/C 系）才走 `MotorCtrlSupportRpm`，发的是 `SL_LIDAR_CMD_HQ_MOTOR_SPEED_CTRL`（真正的 rpm）。
"参数名相同、语义不同"，是这份手册里最容易踩的坑。

**(e)** 实践建议：默认 `0`（=600，本机 11.9 Hz）；提帧率最多试到 `720`（约 14.7 Hz）；
`900`（约 18.8 Hz）超出 A2M12 额定转速，而且每圈点数明显变少（11-06 实测 347 → 224，11-07 另一场景 545 → 343；采样率是瓶颈，见 3.9 节），只适合实验。

**(f)** 【C1M1 实测，旧驱动】设 360/480/600/720/900，`/scan` 恒在 10 Hz 左右。
以前这里写"C1M1 走 `MotorCtrlSupportRpm` 分支"，2026-11-07 读 SDK 源码后更正：`checkMotorCtrlSupport()` 按 Model ID 高 4 位选通道，
≥ 6 才走 RPM；C1 是 0x41（高 4 位 4），被当成 A2/A3 探测 PWM 板，转速命令根本没发。
本包已让 0x41 强制走 RPM 通道，启动日志会打印 `motorCtrlSupport = N`。补丁后 C1M1 实测 480/600/720/900 → 8.006/10.015/12.014/15.011 Hz。
换型号或换固件，必须重做第 6 节的实验。

其他坑：代码只做 0~1200 的统一校验（超出会被拒绝：`RPM must be between 0 and 1200`），不分型号。
在线改 rpm 不会自动改 `computed_ray_count`，参数回调只打一句警告。
A 系列启动时会先用 600 转“踹”一下电机，配置值要等第一圈数据成功后才补发。

关联参数：`computed_ray_count`、`interpolated_rays`。

依据: src/rplidar_node.cpp 的 parameters_callback 函数里 rpm 校验那段（搜索关键词 `Rejecting RPM`）与 scan_loop 函数（搜索关键词 `Applying configured motor speed`）；src/lidar_driver_wrapper.cpp 的 start_motor 函数（搜索关键词 `user_rpm_pref > 0`）与 set_motor_speed 函数（搜索关键词 `(rpm > 0) ? rpm : 600`）；param/rplidar.yaml 中「rpm」的注释段（搜索关键词 rpm）

### 3.7 `auto_standby`

**(a)** 打开后，节点每 0.2 秒数一次“现在有几个订阅者在听 `/scan`”。没人听就停电机（串口不关），有人回来就重新加速。关掉时电机一直转，只能靠服务手动停。

**(b)**

     # 终端 A：不启动 RViz，只跑节点
     ros2 launch rplidar_a2m12_teaching_driver a2m12.launch.py rviz:=false
     ros2 topic echo /diagnostics --once     # 等约 1 秒，应看到 Standby (auto: no subscribers)
     ros2 topic echo /scan --once            # 再订阅一下，电机应重新转起来

**(c)** 打开：省电机寿命、安静，代价是每次唤醒要等加速完成，第一帧可能不全。关闭：随开随有数据，代价是电机一直在转。

**(d)** 坑一：打开后 `stop_motor` / `start_motor` 两个服务会被**拒绝**，返回信息明确写“订阅者数量是唯一裁判”。坑二：如果你的程序只是偶尔发一下 `ros2 topic echo`，雷达会不停地停—转—停。

关联参数：`publish_point_cloud`（打开点云后，`/cloud` 的订阅者也计入“有人听”）。

依据: src/rplidar_node.cpp 的 scan_loop 函数（搜索关键词 `No subscribers left`）、count_output_subscribers 函数（搜索关键词 `get_subscription_count`）、standby_request_refused 函数（搜索关键词 `auto_standby' is enabled`）、parameters_callback 函数（搜索关键词 `Auto standby: %s`）；param/rplidar.yaml 中「auto_standby」的注释段（搜索关键词 auto_standby）

### 3.8 `interpolated_rays`

**(a)** 雷达每圈采到的点数是不固定的，也不均匀。关掉时，驱动把这些点“装箱”到均匀格子里，每个格子保留最近的读数（同一格里更近的那个赢）。打开时反过来：先定好一圈有 `computed_ray_count` 根固定光束，再把相邻两个真实测量点连成线段，算光束和线段的交点当作该光束的距离。

**(b)** 看 `angle_increment` 是否变成一个很整齐的数，以及 `ranges` 长度是否恰好等于 `computed_ray_count`：

     ros2 param set /rplidar_node interpolated_rays true
     ros2 topic echo /scan --once --field angle_increment
     ros2 topic echo /scan --once --field ranges | head -c 300

**(c)** 打开：画面规整，墙面变直，墙角更尖，适合建地图和定位；代价是 CPU 明显上升（每个格子都要算一次交点），而且近处贴着物体的读数会被“切掉”一截。关闭：省 CPU，障碍物检测够用，但同一面墙会看到锯齿。

**(d)** 坑一：打开它之后必须同步改 `computed_ray_count`，否则一圈要么太稀要么数据量爆炸——参数回调只会打警告提醒，不会帮你算。坑二：`intensities_as_angles` 在这个模式下不生效。坑三：调试完记得关掉，别一直开着。

关联参数：`computed_ray_count`（必须成对调）、`scan_mode`（别同时用 DenseBoost）、`intensities_as_angles`。

依据: src/rplidar_node.cpp 的 publish_scan 函数（搜索关键词 `beam_count = params_.computed_ray_count`、`scan_msg.angle_increment`、`beam_count - 1`）、parameters_callback 函数（搜索关键词 `Ray Interpolation: %s`）；include/rplidar_node.hpp 的 `Parameters` 结构体（搜索关键词 `computed_ray_count`）；param/rplidar.yaml 中「interpolated_rays」的注释段（搜索关键词 interpolated_rays）

### 3.9 `computed_ray_count`

**(a)** 只在 `interpolated_rays=true` 时有意义：一圈切成多少根光束。它同时决定三件事——`angle_increment = 2π / beam_count`、`ranges` 数组的长度、以及 `time_increment`。关掉插值时这个参数完全不看。

**(b)** 拿它跟 `/scan` 里 `ranges` 的长度对比，必须完全相等：

     ros2 param set /rplidar_node computed_ray_count 900
     ros2 topic echo /scan --once --field ranges | wc -c

**(c)** 调大：画面更细密、相邻点更近，但 CPU、带宽、`/cloud` 的点数一起涨；更关键的是**你一格的数据不够时，那些格子就只能是“无穷远”**，于是画面出现规则的放射状空洞。调小：省资源，但墙会变“点状”。

**(d)** 坑一：参数回调对这个值**完全没有范围校验**，填 0 会让一圈光束数变成 0，等于没有数据；填几万会让消息大到 RViz 卡死。**代码中未做校验**，安全范围要自己试。坑二：正确做法是先量一圈真实点数再取接近的数；填得比真实点数多就会出现空洞。**注意本包默认值 1450 是给 S 系准备的**：A2M12 在 `rpm=600`（默认）下一圈只有 **347** 点，直接开 `interpolated_rays` 且沿用 1450，等于把 347 个真实点外插成 1450 束，其中大部分是算出来的假点。要用请按 `ros2 topic echo /scan --once --field angle_increment` 量出点数（= 2π ÷ angle_increment）后再定。

关联参数：`interpolated_rays`、`rpm`、`publish_point_cloud`。同一场景下真实点数与转速成反比（硬件采样率恒定）。绝对值随场景变（驱动丢弃距离为 0 的点）：11-07 复测 600 → 545、900 → 343 点/帧，约 6.2 k 点/s；11-06 那次是 A2M12 实测 `rpm=600` 时 347 点/圈、`rpm=900` 时 224 点/圈，点率都在约 4.1 k 点/s。

依据: src/rplidar_node.cpp 的 publish_scan 函数（搜索关键词 `beam_count = params_.computed_ray_count`、`scan_msg.range_min`）、parameters_callback 函数（搜索关键词 `Ray Interpolation: %d`）；param/rplidar.yaml 中「computed_ray_count」的注释段（搜索关键词 computed_ray_count）

### 3.10 `use_intensities`

**(a)** 决定 `/scan` 里填不填 `intensities` 数组（回波有多强）。关掉时消息里根本没有这个数组，省带宽。

**(b)**

     ros2 param get /rplidar_node use_intensities
     ros2 topic echo /scan --once | grep -c intensities

**(c)** 打开：RViz 可以按强度上色，能看出哪些点弱（玻璃、黑布）；代价是消息体积变大，而且说明书提醒很多新型号的强度值本身不准。关闭：省流量，颜色只有一种。

**(d)** 坑：官方文档说关掉它更符合 `LaserScan` 的建议；如果你只是要看形状，别开。

关联参数：`intensities_as_angles`、`publish_point_cloud`（点云颜色也会用到强度）。

依据: src/rplidar_node.cpp 的 publish_scan 函数（搜索关键词 `scan_msg.intensities.assign`、`intensities_as_angles`、`*out_g`）；param/rplidar.yaml 中「use_intensities」的注释段（搜索关键词 use_intensities）

### 3.11 `max_distance`

**(a)** 只在消息的 `range_max` 字段上声明“最远多少米算有效”。填 0 表示用硬件能力值（A2M12 这类 A 系三角测距型号驱动里写死 12 m，S 系 DTOF 型号默认 40 m）；本仓库 `param/a2m12.yaml` 因此直接填 12.0；填正数时，实际发出的是**你填的值和硬件能力里更小的那个**。

**(b)**

     ros2 param set /rplidar_node max_distance 6.0
     ros2 topic echo /scan --once --field range_max      # 应显示 6.0

**(c)** 调大：RViz 不再自动裁掉远处的点，画面能显示更远的地方；但远处的点本来就更飘。调小：RViz 把超出范围的点全丢掉，画面变成一个“干净”的圆盘；适合室内小场地。

**(d)** 坑一（重要）：**这个参数并不裁剪真实数据**。`ranges` 里仍然可能大于你设的值，只有那些尊重 `range_max` 的消费者（RViz、laser_filters）才会丢掉它们。真正的裁剪在源码里注明是未来版本的事。坑二：`range_min` 是写死的 0.01 米，不是一个参数，改不了。

关联参数：`scan_mode`（不同模式上报的最远距离不同）。

依据: src/rplidar_node.cpp 的 scan_loop 函数（搜索关键词 `Max Range: %.2f m`）与 publish_scan 函数（搜索关键词 `scan_msg.range_min`）；src/lidar_driver_wrapper.cpp 的 detect_and_init_strategy 函数（搜索关键词 `hw_max_distance`）、start_motor 函数（搜索关键词 `detected_max_dist`）、get_hw_max_distance 函数（搜索关键词 `return profile_.hw_max_distance`）；param/rplidar.yaml 中「max_distance」的注释段（搜索关键词 max_distance）

### 3.12 `dummy_mode`

**(a)** 打开后用一个“假驱动”代替真雷达：不打开串口，自己编一圈 360 个点出来。用来在没有雷达的机器上把整条链路跑通。

**(b)**

     ros2 launch rplidar_a2m12_teaching_driver a2m12.launch.py dummy_mode:=true
     # 日志出现 DUMMY MODE ENABLED 与 [Dummy] Virtual RPLIDAR device ready

**(c)** 打开：RViz 里出现一个规则的圆环，永远不报硬件错误，非常适合排查“到底是雷达坏了还是我的参数坏了”。代价是：它完全不反映真实世界，所有测距类调参都失去意义。关闭：用真雷达。

**(d)** 坑：假驱动的每帧点数只有 360，所以拿它验证 `computed_ray_count=1450`（或任何远大于 360 的值）时会看到大量空洞——这不是参数错，是假数据太少。另外它上报的最远距离固定 40 米。

关联参数：`serial_port`、`serial_baudrate`（打开后这两个都不看）。

依据: src/rplidar_node.cpp 的 on_configure 函数（搜索关键词 `DUMMY MODE ENABLED`）与 scan_loop 函数（搜索关键词 `make_unique<DummyLidarDriver>`）；src/lidar_driver_wrapper.cpp 的 DummyLidarDriver::connect 函数（搜索关键词 `Virtual RPLIDAR device ready`）、DummyLidarDriver::grab_scan_data 函数（搜索关键词 `MockDriverState::SCANNING`）

### 3.13 `publish_tf`

**(a)** 打开时，节点自己发一条静态坐标变换：从 `base_link` 到 `frame_id`（默认 `laser_a2m12`），平移全是 0、旋转也是 0。也就是说它声明“雷达就装在车体正中心”。

**(b)**

     ros2 run tf2_ros tf2_echo base_link laser_a2m12
     ros2 topic echo /tf_static --once

**(c)** 打开：没有 URDF 的时候 RViz 也能用 `base_link` 当 Fixed Frame 正常显示；代价是这条假变换会和机器人真实的 URDF 打架，同一个坐标系被两个来源宣布。关闭：交给 `robot_state_publisher` 管，这是机器人上的正确做法。

**(d)** 坑：本仓库默认关闭，原因写在 yaml 注释里——真机上 TF 应该由机器人描述文件负责。只有单独测雷达时才打开。另外这条 TF 只在 configure 时发一次，postdate 到那时的时间戳，所以它不会自己更新。

关联参数：`frame_id`。

依据: src/rplidar_node.cpp 的 on_configure 函数（搜索关键词 `Broadcasting static transform`）；rviz/a2m12.rviz:84-85；param/rplidar.yaml 中「publish_tf」的注释段（搜索关键词 publish_tf）

### 3.14 `qos_policy`

**(a)** 决定 `/scan`（以及 `/cloud`）用什么传输规矩发出去。三选一：`sensor_data`、`services_default`、其它任何值都落到 `system_default`。详见第 4 章专章。

**(b)**

     ros2 topic info -v /scan        # 看 QoS 那一段的 Reliability / Depth

**(c)** 从 `sensor_data` 换成 `services_default`：不丢帧但延迟变大，网络差时 RViz 会“攒一堆一起出来”。换回去：刷新流畅但允许丢帧。

**(d)** 坑：这个参数是静态的，在线改只会得到一句“动态修改不支持”的警告，必须重 configure 或重启节点才生效。更严重的坑见 4.4：QoS 不匹配时不是“慢”，而是根本收不到。

关联参数：`publish_point_cloud`（两个话题共用同一套 QoS）。

依据: src/rplidar_node.cpp 的 on_configure 函数（搜索关键词 `[QoS] Policy:`）；param/rplidar.yaml 中「qos_policy」的注释段（搜索关键词 qos_policy）；rviz/a2m12.rviz:70-77

### 3.15 `max_retries`

**(a)** 在 RUNNING 状态下，连续多少次读不到数据就判定“硬件掉线”，然后进入重置流程（丢掉驱动对象、等 2 秒、重新连）。计数是“连续”的：只要读到一帧就清零。

**(b)** 想验证就拔一次线，看多久后 `/diagnostics` 变成 `Hardware Error / Resetting`：

     ros2 topic echo /diagnostics | grep -m3 'Hardware Error'

**(c)** 调大：偶发的线材抖动不会被误判成掉线，代价是拔线后要等更久才知道，期间 RViz 画面定格。调小：掉线检测快，代价是容易被瞬时噪声触发重连，导致周期性闪断。

**(d)** 坑：源码里判定条件是“失败次数 **大于** `max_retries`”，所以设 3 意味着第 4 次失败才动手。
每次 `grab_scan_data` 失败前要等 SDK 超时（`DEFAULT_TIMEOUT` = 2000 ms）。

【C1M1 实测，A2M12 未验证】`max_retries: 3` 时的拔线时间线（以拔掉 USB 为 0 秒）：

| 时刻 | 发生了什么 |
|---|---|
| 约 5 s | 看门狗发现 `/scan` 断流 |
| 约 9.5 s | `[FSM] Hardware unresponsive (Over 3 errors). Resetting...` |
| 约 11.7 s 起 | 每秒重试一次连接 |
| 插回后约 4.5 s | `Connection established`（这段时间主要是雷达自己上电启动） |
| 插回后约 8 s | 第一帧 `/scan` 恢复 |

调小 `max_retries` 只能缩短“约 9.5 s”这一段，插回后的约 8 s 不受它影响。

关联参数：无直接关联；它只影响掉线判定的快慢。

依据: src/rplidar_node.cpp 的 scan_loop 函数（搜索关键词 `Hardware unresponsive`、`recreating driver`）；param/rplidar.yaml 中「max_retries」的注释段（搜索关键词 max_retries）；include/rplidar_node.hpp 的 `enum class DriverState`

### 3.16 `angle_offset`

**(a)** 给每个点的角度统一加一个固定偏移（弧度）。用来纠正“雷达零位跟车头方向差了一点”这种安装问题。它是在角度归一化之前加上的，而且会用循环减回合法区间，所以填多大都不会算崩。

**(b)** 找一个已知方向的物体（比如正前方的墙），看它在 RViz 里是否落在红色 X 轴方向上；也可以直接读 `angle_min`：

     ros2 param get /rplidar_node angle_offset
     ros2 topic echo /scan --once --field angle_min

**(c)** 调大（正值）：整幅画面绕中心统一旋转，形状完全不变。3.1415926（半圈）是 A1/A2 老型号常见的修正值。代价：它只转画面，不改变报告的 `angle_min`/`angle_max` 区间，所以别指望用它去凑下游节点要求的范围。

**(d)** 坑：如果你的下游过滤器把 -3.14 到 3.14 之外全砍掉，转 `angle_offset` 是没用的——那要改 `symmetric_angle_range`。两件事别混。

关联参数：`symmetric_angle_range`、`angle_compensate`。

依据: src/rplidar_node.cpp 的 publish_scan 函数（搜索关键词 `angle_rad += params_.angle_offset`）；param/rplidar.yaml 中「angle_offset」的注释段（搜索关键词 angle_offset）

### 3.17 `symmetric_angle_range`

**(a)** 决定一圈角度的报法：`false` 报 [0, 2π)（从 0 开始往上加），`true` 报 [-π, π)（从负一半到正一半）。物理朝向完全不变，变的只是“刻度从哪儿开始算”。

**(b)**

     ros2 param set /rplidar_node symmetric_angle_range true   # 会提示不支持，需重启
     ros2 topic echo /scan --once --field angle_min    # 重启后应为 -3.14 左右

**(c)** 打开：跟 ROS 2 生态的常见约定一致（下游滤波器、建图算法默认这么假设），代价是极少数按 [0, 2π) 写死的老代码会算错。关闭：保持本驱动历史行为，兼容老部署。

**(d)** 坑：源码注释明确写了这是个**临时参数**，下一个大版本会无条件改成 [-π, π) 并删掉它。所以新项目应当直接当它是 `true` 来写。注意只有开插值时 `angle_min` 才会被显式设成 -π；关插值时上下界来自排完序的实际数据。

关联参数：`angle_offset`、`interpolated_rays`。

依据: src/rplidar_node.cpp 的 publish_scan 函数（搜索关键词 `params_.symmetric_angle_range`、`scan_msg.angle_min`）；param/rplidar.yaml 中「symmetric_angle_range」的注释段（搜索关键词 symmetric_angle_range）

### 3.18 `publish_point_cloud`

**(a)** 除了 `/scan`，再把同一圈数据以三维点云格式发一份到 `/cloud`。纯粹为了调试和可视化。

**(b)**

     ros2 param set /rplidar_node publish_point_cloud true
     ros2 topic hz /cloud
     ros2 topic echo /cloud --once --field width

**(c)** 打开：RViz 里能加一个 PointCloud2 显示，可以看到点云的排布、颜色（绿通道用了强度）；代价是每帧多做一次坐标转换和一次消息分配，带宽翻倍。关闭：只发 `LaserScan`，最省。

**(d)** 坑一：发布者只在 activate 那一刻根据当时的参数决定开不开，所以**中途把它从 false 改成 true，可能不会真的出现 `/cloud`**（推测：需要 deactivate 再 activate 一次才生效——源码里只在 activate 分支调用了发布者的激活）。坑二：yaml 注释明确建议“不调试就关掉，别一直开着”。

关联参数：`computed_ray_count`（调它的推荐手段就是先开点云数点数）、`use_intensities`。

依据: src/rplidar_node.cpp 的 on_configure 函数（搜索关键词 `"cloud", qos_profile`）、on_activate 函数（搜索关键词 `cloud_pub_->on_activate`）、publish_scan 函数（搜索关键词 `cloud_msg.header.stamp`、`*out_g = params_.use_intensities`）、parameters_callback 函数（搜索关键词 `PointCloud2 publishing`）；param/rplidar.yaml 中「publish_point_cloud」的注释段（搜索关键词 publish_point_cloud）

### 3.19 `intensities_as_angles`

**(a)** 一个纯调试开关：打开后，`intensities` 数组里放的不再是强度，而是硬件上报的原始角度。用来看“雷达自己说的角度”和“驱动算出来的角度”差多少。

**(b)**

     ros2 param set /rplidar_node use_intensities true
     ros2 param set /rplidar_node intensities_as_angles true
     ros2 topic echo /scan --once --field intensities | head -c 300   # 会出现 0~6.28 这样的值

**(c)** 打开：画面形状不变，但任何按强度上色的显示都会变成噪点。关闭：正常。这个参数没有“调大调小”，只有“开/关”。

**(d)** 坑一：它依赖 `use_intensities`，后者关着时这个开关什么也不做。坑二：`interpolated_rays=true` 时它不生效（那时填的是强度）。坑三：这是调试用的，别留在生产配置里。

关联参数：`use_intensities`、`interpolated_rays`。

依据: src/rplidar_node.cpp 的 publish_scan 函数（搜索关键词 `intensities_as_angles`、`scaleIntensity`）；param/rplidar.yaml 中「intensities_as_angles」的注释段（搜索关键词 intensities_as_angles）

### 3.20 两个服务：`stop_motor` / `start_motor`

**(a)** 手动把电机停下 / 叫起来，串口不断开。之所以做成服务而不是参数，是因为它是一次“动作”，不是一种“状态”。

**(b)**

     ros2 service call /stop_motor std_srvs/srv/Trigger
     ros2 topic echo /diagnostics --once | grep -E 'Standby|Connection'
     ros2 service call /start_motor std_srvs/srv/Trigger

**(c)** 调用成功只代表“请求已登记”，真正的停/转发生在后台线程的下一轮循环，所以返回信息写的是“马上就要停了”而不是“已经停了”。不要调用后立刻断言电机停了。

**(d)** 坑一：`auto_standby=true` 时两个服务都被拒绝（返回信息说明订阅者数量才是裁判）。坑二：节点不在 ACTIVE 状态时也被拒绝，因为执行者（后台扫描线程）根本没在跑。坑三：deactivate 时驱动会主动停电机，所以“deactivate + activate”不等于“什么都没发生”。

关联参数：`auto_standby`。

依据: src/rplidar_node.cpp 的 on_configure 函数（搜索关键词 `"stop_motor"`）、standby_request_refused 函数及调用它的两个服务回调（搜索关键词 `standby_request_refused`）、on_deactivate 函数（搜索关键词 `Deactivating node`）；param/rplidar.yaml 中「auto_standby」的注释段（搜索关键词 auto_standby）

## 4. QoS 专章：为什么你的 RViz 收不到数据

### 4.1 三档策略到底是什么

QoS 是“这个频道怎么送数据”的约定。本驱动提供三档：

| `qos_policy` 取值 | 实际用哪套 | 关键设置 | 翻译成人话 |
|---|---|---|---|
| `sensor_data` | `SensorDataQoS` | 只留最近 5 条、尽力而为、不重发 | 像 UDP 直播：掉一帧就掉一帧，绝不为了补发而卡住 |
| `services_default` | `ServicesQoS` | 只留最近 10 条、保证送达、不重发 | 像 TCP：一条都不能少，代价是网络差时会排队、变慢 |
| `system_default`（写其它值也是这个） | `SystemDefaultsQoS` | 由底层中间件决定 | 听天由命：不同机器、不同中间件可能给出不同结果 |

### 4.2 为什么默认是 `sensor_data`

雷达数据是“持续产生的、过时就没用的”数据。第 3 帧对第 1 帧没有任何补充价值，所以宁可丢掉旧的，也不该让发送方等确认。它的缓存深度只有 5，也是同一个道理：留得越少，延迟越低。

### 4.3 对三个典型场景的影响

| 场景 | `sensor_data` | `services_default` |
|---|---|---|
| RViz 实时看画面 | 流畅，偶尔丢帧但看不出来 | 可能“顿一下再一次性刷出一堆”，画面上像卡了一下 |
| `ros2 bag record` 录包 | 高频时可能漏记录几帧 | 一条不漏，但录制端跟不上时会拖慢发布方 |
| 多机 / Wi-Fi 通信 | 丢包无人补救，画面断续 | 弱网下能收全，但延迟可能涨到秒级 |

### 4.4 什么时候必须改，以及最危险的那个坑

必须改成 `services_default` 的场合：录包必须完整、跨 Wi-Fi 传数据、下游对丢帧零容忍。

真正危险的不是“选哪档”，而是**发布方和订阅方的可靠性对不上**：尽力而为的发布者无法配对“要求保证送达”的订阅者，这时话题列表里明明有 `/scan`，订阅方却一条也收不到，且不报错。表现就是 RViz 一片空白。两种典型踩法：

1. 把 `qos_policy` 改成 `services_default` 后，RViz 那边还是 Best Effort —— 这个方向是**兼容**的，一般没问题；反过来才致命。
2. 用别的工具（或自己写的订阅者）时默认要可靠性，而驱动是 `sensor_data` —— 收不到。这时要么把订阅方改成 Best Effort，要么把驱动改成 `services_default`。

本仓库的 `rviz/a2m12.rviz` 已经老老实实把 `/scan` 的 Reliability 设成 `Best Effort`，就是为了跟默认的 `sensor_data` 对上。你改 QoS 时，别忘了同时改订阅方。

另一个坑：`/cloud` 和 `/scan` 共用同一套 QoS，改一个就是改两个。

依据: src/rplidar_node.cpp 的 on_configure 函数（搜索关键词 `[QoS] Policy:`）；rviz/a2m12.rviz:70-77；param/rplidar.yaml 中「qos_policy」的注释段（搜索关键词 qos_policy）

## 5. 波特率型号对照表

| 型号 | 波特率 | 备注 |
|---|---|---|
| A1 / A2M8 | 115200 | 老三角测距型号 |
| A2M7 / A2M12 / A3 / S1 | 256000 | |
| **A2M12（本仓库）** | **256000** | A2M12 走这个值，`param/a2m12.yaml` 已填好 |
| S2 / S3 | 1000000 | `param/rplidar.yaml` 的默认值是给它们的 |

配错会出现什么：

- **波特率比实际低**：串口能打开，但一问设备信息就失败，日志出现 `Failed to get device info (data may be corrupted).`，然后不断重连，`/diagnostics` 卡在 `Connecting`。
- **波特率比实际高**：多半是串口能打开但一个字节都读不出来，表现为同一种“连不上”，所以光看现象分不出高低，只能查型号表。
- **两者都对的唯一证据**：启动日志里出现了型号和序列号（`S/N: ... FW: ... HW: ...`），以及 `Max Range: ... m`。看到这两行才叫真连上了。

依据: param/rplidar.yaml 中「serial_baudrate」的注释段（搜索关键词 serial_baudrate）；param/a2m12.yaml 中「serial_port」的注释段（搜索关键词 serial_port）；src/lidar_driver_wrapper.cpp 的 connect 函数（搜索关键词 `Failed to bind connection with device`）、get_device_info_str 函数（搜索关键词 `S/N:`）

## 6. 实验：验证调速到底有没有生效

理论公式只有一条：

    扫描频率 (Hz) = rpm / 60        （600 转 = 10 Hz）

但**公式成立的前提是：雷达真的执行了调速命令，而且这个参数真的是转速**。A2M12 实测：频率会变，但参数是 PWM 占空比，`rpm/60` 不成立（见 3.6 节）；C1M1 在旧驱动下实测频率恒定，原因是 SDK 把 C1 误判成 A 系、转速命令没发出去（见 3.6 节 (f)）；本包已修复，C1 现在 `rpm/60` 成立。
这个实验教你自己验证，以后换任何雷达都用得上。

**准备**：接上真雷达（假雷达固定约 93 Hz，和 rpm 无关，做不了这个实验）。
最省事的做法：驱动跑起来之后，直接跑 `ros2 run rplidar_a2m12_teaching_driver rpm_sweep.sh`，
它会按下面的表格逐档设 rpm、等稳定、量频率并直接给判定；想手动做就照下面的步骤来。

    # 终端 1
    ros2 launch rplidar_a2m12_teaching_driver a2m12.launch.py rviz:=false
    # 终端 2：一直开着
    ros2 topic hz /scan

**步骤**：在终端 3 里每改一次，等 10 秒，让终端 2 的 `average rate` 稳定下来再记录。

    ros2 param set /rplidar_node rpm 480
    ros2 param set /rplidar_node rpm 720
    ros2 param set /rplidar_node rpm 600
    ros2 param set /rplidar_node rpm 1500     # 应被拒绝
    ros2 param set /rplidar_node rpm 0        # 恢复默认

> 【A2M12 本机实测 2026-11-06】`rpm: 0`（驱动按 600 下发）时 `/scan` 约 11.6 Hz，即约 697 rpm，比标称的 10 Hz 高 16%。5 档 rpm 的完整对照还没测，请用下面的步骤补齐。

**记录表**（左两列留给你自己；右两列是两代硬件的实测值，供对照）：

| 设置的 rpm | 理论频率 | 你测到的频率 | C1M1 实测 | A2M12 实测（2026-11-06，FW 1.32/HW 6） |
|---|---|---|---|---|
| 600 | 10 Hz | | 10.009 Hz | 11.892 Hz |
| 480 | 8 Hz | | 10.004 Hz | 9.231 Hz |
| 720 | 12 Hz | | 10.010 Hz | 14.673 Hz |
| 360 | 6 Hz | | 9.997 Hz | 未测 |
| 900 | 15 Hz | | 10.007 Hz | 18.821 Hz |
| 1500 | — | | 被拒绝 | 被拒绝 |

**怎么判断**：

- 频率跟着 rpm 变、且误差在 10% 以内：这台雷达支持调速，`rpm/60` 公式成立。
- 频率跟着变但比例明显不是 1（像 A2M12 那样，设 600 实测约 713 rpm）：支持调速，但命令语义是 PWM 占空比，`rpm/60` 不成立，按上表自己标定。
- 频率一直不变（像 C1M1 在旧驱动下那样锁在 10 Hz）：先别下"硬件不支持"的结论。看启动日志 `motorCtrlSupport = N`：不是 `2 (RPM)` 或 `1 (PWM)`，说明命令根本没发出去，是驱动问题；是 2 或 1 仍然不变，才说明雷达不执行这条命令。
- 只在某个范围内变：记下能调的范围，写进你们自己的 yaml 注释里。

**这个实验要学会的事**：`ros2 param set` 显示成功、日志打印 `Updating RPM`、`/diagnostics` 里 `Target RPM` 变了，
这三样都只说明“驱动发出了命令”。只有测出来的频率才说明“硬件照做了”。

依据: src/lidar_driver_wrapper.cpp 的 set_motor_speed 函数（搜索关键词 `(rpm > 0) ? rpm : 600`）；src/rplidar_node.cpp 的 parameters_callback 函数（搜索关键词 `Rejecting RPM`）；SDK 的 setMotorSpeed（src/sdk/src/sl_lidar_driver.cpp，搜索关键词 `SL_LIDAR_CMD_HQ_MOTOR_SPEED_CTRL`）

## 7. 三个情景配方（可直接照抄）

三个配方都用同一个套路：把下面这段存成 `$HOME/my_a2m12.yaml`，然后用 `params_file` 指过去。**不要去改仓库里的 `param/a2m12.yaml`。**

启动命令（三个配方通用）：

     ros2 launch rplidar_a2m12_teaching_driver a2m12.launch.py params_file:=$HOME/my_a2m12.yaml

### 7.1 配方甲：RViz 画面一卡一卡 / 丢点

先去掉所有“吃 CPU 和带宽”的附加项，把最小可用配置跑通：

    rplidar_node:
      ros__parameters:
        serial_port: '/dev/ttyUSB0'
        serial_baudrate: 256000
        frame_id: 'laser_a2m12'
        scan_mode: 'Standard'
        rpm: 0                 # 600 转 = 10 Hz，先保证不丢点
        angle_compensate: true
        interpolated_rays: false   # 关掉插值，省 CPU
        use_intensities: false
        publish_point_cloud: false # 关掉点云，省一半带宽
        publish_tf: false
        qos_policy: 'sensor_data'
        max_retries: 3
        dummy_mode: false

配套动作（按顺序做，一步验证一步）：

     ros2 topic hz /scan            # 是不是稳定在 10 Hz 左右，有没有掉到 0
     ros2 topic info -v /scan       # Reliability 是不是 Best Effort
     ros2 topic echo /diagnostics --once   # 是不是 Scanning

还剩卡顿的话，依次检查：RViz 里 LaserScan 的 `Decay Time` 是否非 0（会累积多帧）、`Size (Pixels)` 是否过大、显示器的 `Frame Rate` 是否被调高、电脑 CPU 是否被别的程序占满。

### 7.2 配方乙：想让每帧光束数固定（给建图或算法用）

原来这里是“提高帧率”的配方。C1M1 上实测改 `rpm` 无效；A2M12 上有效，但那只是 PWM 占空比（见 3.6 节），调它不等于精确设帧率。所以这里换成“每帧光束数固定”的配方。

关掉插值时，每帧光束数 = 这一圈实际测到的点数，每帧都略有不同。有些算法希望每帧长度固定，这时打开插值。

**第 1 步：先量出真实点数。** 用默认的 `param/a2m12.yaml`（插值关闭）启动，然后：

     ros2 topic echo /scan --once --field angle_increment

真实点数约等于 `6.2832 ÷ angle_increment`。例如读到 `0.0125`，就是约 500 个点。

**第 2 步：写配置。** `computed_ray_count` 取比真实点数**略小**的整数，比如真实约 500 就填 480：

    rplidar_node:
      ros__parameters:
        serial_port: '/dev/ttyUSB0'
        serial_baudrate: 256000
        frame_id: 'laser_a2m12'
        scan_mode: 'Standard'
        rpm: 0
        interpolated_rays: true
        computed_ray_count: 480     # 换成你第 1 步量出来的数，略小一点
        use_intensities: false
        publish_point_cloud: false
        publish_tf: false
        qos_policy: 'sensor_data'
        max_retries: 3

**第 3 步：验证。**

     ros2 topic echo /scan --once --field angle_increment   # 应约等于 6.2832 ÷ 480 ≈ 0.0131

代价：插值光束的距离是相邻两个真实点连线算出来的，不是测出来的。做避障时宁可关掉。
`computed_ray_count` 比真实点数大太多，会出现规则的放射状空洞；千万别填 0（代码不校验，会算出无穷大的角度间隔）。

### 7.3 配方丙：RViz 里什么都看不到，按这个顺序排查

**第 0 步：先用假数据确认“软件链路”没问题。** 如果 dummy 能显示，问题一定在硬件或串口相关参数上。

     ros2 launch rplidar_a2m12_teaching_driver a2m12.launch.py dummy_mode:=true

**第 1 步：节点活着且被激活了吗？** 本节点是生命周期节点，只启动进程是不够的。

     ros2 node list
     ros2 lifecycle get /rplidar_node      # 必须是 active

**第 2 步：`/scan` 上真有数据吗？** 有话题不等于有数据。

     ros2 topic list | grep scan
     ros2 topic hz /scan

频率是 0 或空 → 问题在驱动层/硬件层（串口、波特率、`dummy_mode`、电机被停了）。往下看第 5 步和 `/diagnostics`。

**第 3 步：坐标系对得上吗？**

     ros2 topic echo /scan --once --field header.frame_id
     # 与 RViz 的 Fixed Frame 必须一致（本仓库是 laser_a2m12）

**第 4 步：QoS 对得上吗？**

     ros2 topic info -v /scan
     # Publisher 的 Reliability 与 RViz 的 Reliability 不能一个 Best Effort 一个要 Reliable

**第 5 步：雷达到底连上没有？**

     ros2 topic echo /diagnostics --once
     ls /dev/ttyUSB*
     # 期望看到：状态 Scanning、Connection Connected、Device Info 里有 S/N

`Connecting` + `Device Info: N/A` → 串口路径或波特率错（A2M12 是 256000）或没权限。`Standby` → 电机被 `stop_motor` 或 `auto_standby` 停了，看 `Standby Trigger` 字段。`Hardware Error / Resetting` → 拔插 USB 后等它自己恢复，恢复不了就重启节点。

**第 6 步：还是看不到，回到最小配置。** 用 7.1 的 yaml（除了 `serial_port` 之外全部取默认值）再试一次，逐项加回去，哪一项加回去就坏，就是哪一项的问题。

**最小可对照配置（第 6 步用）：**

    rplidar_node:
      ros__parameters:
        serial_port: '/dev/ttyUSB0'
        serial_baudrate: 256000
        frame_id: 'laser_a2m12'
        scan_mode: 'Standard'
        rpm: 0
        angle_compensate: true
        interpolated_rays: false
        computed_ray_count: 320
        use_intensities: false
        max_distance: 12.0
        dummy_mode: false
        publish_tf: false
        qos_policy: 'sensor_data'
        max_retries: 3
        angle_offset: 0.0
        symmetric_angle_range: false
        publish_point_cloud: false
        intensities_as_angles: false

依据: launch/a2m12.launch.py（`DeclareLaunchArgument`、`configure_event`、`activate_event`、`rviz_node`）；src/rplidar_node.cpp 的 on_configure 函数（搜索关键词 `[QoS] Policy:`）、update_diagnostics 函数（搜索关键词 `Node Inactive`）

## 8. 常见误解清单

| 误解 | 事实 | 依据 |
|---|---|---|
| `rpm: 0` 表示电机不转 | 0 表示“用固定默认 600 转/分” | src/lidar_driver_wrapper.cpp 的 start_motor 函数（搜索关键词 `user_rpm_pref > 0`）、set_motor_speed 函数（搜索关键词 `(rpm > 0) ? rpm : 600`） |
| `max_distance` 会把远处的点裁掉 | 它只改 `range_max` 声明，`ranges` 里的真实值不动 | src/rplidar_node.cpp 的 scan_loop 函数（搜索关键词 `Max Range: %.2f m`）；param/rplidar.yaml 中「max_distance」的注释段（搜索关键词 max_distance） |
| 改了 `angle_offset` 就能满足下游的角度范围要求 | 它只旋转数据，不改 `angle_min`/`angle_max`，那要用 `symmetric_angle_range` | param/rplidar.yaml 中「angle_offset」的注释段（搜索关键词 angle_offset） |
| 在线 `ros2 param set` 能改所有参数 | 只有 `rpm`、`publish_point_cloud`、`interpolated_rays`、`computed_ray_count`、`auto_standby`、`scan_mode` 六个有动态处理，其余只打一行警告 | src/rplidar_node.cpp 的 parameters_callback 函数（搜索关键词 `parameters_callback`） |
| 驱动没连上时改参数能救回来 | 驱动未连接时参数回调直接拒绝修改 | src/rplidar_node.cpp 的 parameters_callback 函数开头（搜索关键词 `Driver not ready`） |
| `scan_mode` 写错会启动失败 | 不会，会静默回退到自动选择 | src/lidar_driver_wrapper.cpp 的 start_motor 函数（搜索关键词 `Falling back to automatic selection`） |

---

最后一句话：**调参前先看 `/diagnostics`，它有答案；调参后只看 `/scan` 的数字，RViz 只是个橱窗。**
