# 新手导航（先看这一页）

[README.md](README.md) · [安装](README_INSTALL.md) · **新手导航** · [中文说明](README_CN.md) · [参数手册](doc/PARAM_GUIDE_A2M12.md) · [代码精读](doc/CODE_NOTES_CN.md)

> 第一次用这台电脑？先按 [README_INSTALL.md](README_INSTALL.md) 装好环境，再回到这里。

这不是功能说明书，是一张地图：告诉你「我现在想干这件事，该打开哪个文件、盯哪一段代码」。
完整的功能说明在 `README_CN.md`，本页不重复它，只负责把你送到那个位置。

先解释四个会一直出现的词：

- **节点（node）**：一个能独立运行的小程序。本包的主角叫 `rplidar_node`，它的工作就是「跟雷达说话，把结果翻译成 ROS 2 消息发出去」。
- **话题（topic）**：节点之间传消息的「广播频道」。发的人往里喊，收的人订阅它。本包主要有 `/scan`（一圈一圈的距离数据）和 `/cloud`（点云，可选）。
- **服务（service）**：一问一答的「打电话」。你打过去，对方回「收到」或「拒绝」。`/stop_motor` 和 `/start_motor` 就是这种。
- **参数（parameter）**：节点运行时能读能改的配置项，比如串口号、转速。改参数不用改代码。

还要提前建立一个概念，否则后面必然读晕：**这个驱动有两层「状态」**。
外层叫 **lifecycle**（生命周期），管「节点要不要干活」，只有三个档位：`unconfigured`（没准备好）、`inactive`（准备好了但没开工）、`active`（正在干活）。
内层叫 **DriverState**，管「雷达硬件现在怎么样」，只在 active 时由后台线程维护。
新手的经典困惑是「节点明明是 active，为什么没数据」——外层 active 只代表允许干活，内层可能正卡在重连里。

---

## 1. 五分钟跑起来

### 三条命令

```bash
# ① 装依赖、编译、把编译结果告诉当前终端
cd ~/A2M12_ros && source /opt/ros/humble/setup.bash && rosdep install --from-paths rplidar_a2m12_teaching_driver --ignore-src -y && colcon build --symlink-install --packages-select rplidar_a2m12_teaching_driver && source install/setup.bash

# ② 启动驱动 + RViz
ros2 launch rplidar_a2m12_teaching_driver a2m12.launch.py

# ③ 另开一个终端，验证数据有没有出来
ros2 topic hz /scan
```

命令 ① 有两个坑，都是新手必踩的：`source /opt/ros/humble/setup.bash` 少执行，编译脚本找不到 ROS 2；`source install/setup.bash` 少执行，`ros2 launch` 会报「找不到包 rplidar_a2m12_teaching_driver」——ROS 2 靠环境变量找包，不靠你当前在哪个目录。
（如果机器从没初始化过 rosdep，先跑一次 `sudo rosdep init && rosdep update`。）

### 没有雷达也能练：dummy_mode

```bash
ros2 launch rplidar_a2m12_teaching_driver a2m12.launch.py dummy_mode:=true rviz:=false
```

`dummy_mode:=true` 的意思是「别碰串口，用一个假雷达对象造数据」。对应代码是 `src/lidar_driver_wrapper.cpp` 里的 `DummyLidarDriver`，找 `sin` 关键字能看到它怎么用正弦波编出一圈点。`rviz:=false` 给没有显示器的机器（SSH 远程）用。
建议第一次就跑这条：先走通「节点 → 话题 → 终端」，再插硬件。因为假数据永远不会超时、不会掉线，能把「硬件问题」和「代码问题」彻底分开——这是排查最难也最值钱的一步。

### 应该看到什么

- 终端里依次出现 `[Lifecycle] Configuring node...`、`[Lifecycle] Activating node...`、`[FSM] Motor started. Entering RUNNING state.`。真机还会多一段 `RPLIDAR DRIVER CONFIG REPORT`，里面有 `Model` 和 `Target RPM`。
- RViz 弹出窗口，中间一团绿色的点（俯视图），点的位置随雷达所在环境变化。
- `ros2 topic hz /scan` 打印约 10 Hz。

### 看不到数据时的第一条排查命令

```bash
ros2 lifecycle get /rplidar_node
```

答案是三种之一，而且直接指向不同的方向：
`unconfigured` = 没经过 configure（或被人 cleanup 了）；`inactive` = 配好了但没人 activate，发布者没打开，所以一条也发不出去；`active` = 节点在干活，问题在硬件或订阅端。
为什么先查它：它一秒钟就把「代码/状态问题」和「硬件问题」分开，比挨个话题点名快得多。

---

## 2. 目录地图

| 目录 / 文件 | 一句话 | 什么时候需要打开它 |
|---|---|---|
| `src/rplidar_node.cpp` | 节点的全部逻辑：生命周期回调、后台读取线程、状态机、发布、诊断 | 想知道「程序到底在干什么」时第一个打开 |
| `src/lidar_driver_wrapper.cpp` | 真雷达 `RealLidarDriver` 和假雷达 `DummyLidarDriver` 两套实现，中间隔着思岚 SDK | 型号识别、开电机、读数据、造假数据 |
| `src/sdk/` | 思岚官方 SDK 源码，原样搬来的 | 一般不要改；只有想追「串口字节怎么变成测量点」时才看 |
| `include/rplidar_node.hpp` | 节点的「目录页」：类声明、`DriverState` 枚举、参数结构体、成员变量 | 想知道有哪些函数和字段、某个变量谁在写 |
| `include/lidar_driver_wrapper.hpp` | 真假雷达共用的接口（插座） | 想加第三种驱动实现（比如仿真器）时 |
| `launch/a2m12.launch.py` | 教学用启动文件：自动 configure→activate，再带一个 RViz | 想改启动默认值（串口、开不开 RViz） |
| `launch/debug_rviz.launch.py` | 只起一个 RViz，带 namespace 重映射 | 驱动已经在跑，只想再开一个 RViz 调显示 |
| `launch/rplidar.launch.py` 等 | 上游原有启动文件 | 一般不看；要讲组件化容器时才看 `composition.launch.py` |
| `param/a2m12.yaml` | A2M12 的默认参数值 | 改串口、波特率、`frame_id`、点云开关——改配置首选这里 |
| `param/rplidar.yaml` | 上游通用参数模板，注释最全 | 想查某个参数究竟什么意思 |
| `rviz/a2m12.rviz` | RViz 布局与显示设置（已把 LaserScan 设成 Best Effort） | RViz 里没画面、想改点的颜色和大小 |
| `config/` | 上游自带的两份 RViz 配置 | 对照着学 RViz 配置文件怎么写 |
| `examples/scan_watchdog.py` | 看门狗：`/scan` 断流就查 Lifecycle 状态再决定怎么办 | 学「订阅 + 调服务 + 异步回调」的完整小例子 |
| `doc/rplidar_driver_sequence.md` | 时序图：谁在什么时候调用谁 | 理不清调用顺序时（比如为什么先 connect 再建发布者） |
| `doc/dummy_driver_state.md` | 假雷达的三个状态怎么流转 | 只想搞懂 dummy_mode 的行为时 |
| `doc/license-audit.md` | 许可证审计记录 | 要拿去发布或商用之前 |
| `test/` | 两个 gtest 单测：节点行为、包装层行为 | 改完代码想知道有没有把别的功能改坏 |
| `scripts/create_udev_rules.sh` | 生成固定设备名 `/dev/rplidar` | 设备名老在 ttyUSB0 / ttyUSB1 之间跳 |
| `CMakeLists.txt`、`package.xml` | 编译脚本和依赖声明 | 加源文件、加依赖时 |

---

## 3. 我想…→ 去哪个文件 → 找哪个函数 → 看哪一段代码

本页所有定位都只用「文件 + 函数名 + 可 grep 的关键词」，不写行号：代码一改行号就会变，函数名和关键词才稳。
每个函数「为什么这么写」的长解释在 [doc/CODE_NOTES_CN.md](doc/CODE_NOTES_CN.md)，源码里只保留上游英文注释和少量 `[CN]` 短注释。

表里有两个词先补一句人话：**TF** 是两个坐标系之间的位置换算关系（雷达的「前方」相对车体在哪、转了多少度）；**QoS** 是发布端和订阅端事先约定的收发质量，最常见的一对是 Reliable（必须送到，缺了要重传）和 Best Effort（丢了就算了，图个快）。

| 我想… | 文件 | 函数 | 找哪个关键词 / 哪一段 |
|---|---|---|---|
| （甲）加一个新话题、发布新消息 | `src/rplidar_node.cpp` | `on_configure`、`publish_scan` | `create_publisher`（建发布者）、`cloud_pub_`（第二个发布者的完整样板） |
| （乙）改雷达转速 | `src/rplidar_node.cpp` | `parameters_callback`、`scan_loop` | `Updating RPM to`、`Applying configured motor speed` |
| （丙）改波特率 / 换型号 | `param/a2m12.yaml`、`src/lidar_driver_wrapper.cpp` | `RealLidarDriver::connect`、`detect_and_init_strategy` | `serial_baudrate`、`Detected new-type device`、`Detected legacy` |
| （丁）排查频繁掉线复位 | `src/rplidar_node.cpp` | `scan_loop` | `error_count`、`Hardware unresponsive`、`Performing hardware reset`、`max_retries` |
| （戊）RViz 里没画面 | `rviz/a2m12.rviz`、`src/rplidar_node.cpp` | `on_configure` | `qos_policy`、`SensorDataQoS`、`rmw_qos_profile_sensor_data` |
| （己）改 frame_id 与 TF | `param/a2m12.yaml`、`src/rplidar_node.cpp` | `publish_scan`、`on_configure` | `header.frame_id`、`publish_tf`、`StaticTransformBroadcaster` |
| （庚）打开点云输出 | `src/rplidar_node.cpp` | `on_activate`、`publish_scan` | `publish_point_cloud`、`cloud_pub_->on_activate` |
| （辛）用假数据调试 | `src/lidar_driver_wrapper.cpp` | `DummyLidarDriver::grab_scan_data` | `sin`、`Virtual RPLIDAR device ready` |
| （壬）在线改参数 | `src/rplidar_node.cpp` | `parameters_callback` | `param.get_name()`、`Driver not ready` |
| （癸）看诊断信息与日志 | `src/rplidar_node.cpp` | `update_diagnostics` | `stat.add`、`Connection`、`Health Code` |
| 停 / 启电机（节点不退出 active） | `src/rplidar_node.cpp` | `handle_stop_motor`、`handle_start_motor`、`standby_request_refused` | `Standby requested`、`auto_standby` |
| 没人订阅时自动停车 | `src/rplidar_node.cpp` | `count_output_subscribers`、`scan_loop` | `auto_standby`、`STANDBY` |
| 加一个新参数 | `include/rplidar_node.hpp`、`src/rplidar_node.cpp` | `init_param`、`init_parameters` | `has_parameter`、`declare_parameter` |

> 关于（庚）有个必须知道的细节：`publish_point_cloud` 在线打开时，驱动内部开关确实会翻成 ON（日志 `[Dynamic] PointCloud2 publishing: ON`），
> 但 `cloud_pub_` 是 lifecycle 发布者，只在 `on_activate` 那一刻被激活；对一个已经 active 的节点，它不会被补激活，`/cloud` 仍然没有消息。
> 所以两条路：要么改 `param/a2m12.yaml` 里的 `publish_point_cloud` 后重新 launch；要么走一趟 deactivate → activate（命令见第 5 节第 ③ 条）。
> 这条顺便说明一件事——**参数改成功了、日志也打了，不代表数据出得来**；验收永远看结果（`ros2 topic hz`），不看回显。

---

## 4. 三个专题小手册

### 4.1 加新功能的最小改动路径（比如再发一个「最近距离」话题）

要动三处，而且三处是联动的，漏一处就会「静默失败」（不报错，只是没数据）：

1. **声明参数**（只有需要用户配置时才做）：在 `init_parameters` 里加一行 `init_param("你起的名字", params_.你的成员)`，同时在 `include/rplidar_node.hpp` 的 `Parameters` 结构体里加同名字段。少加字段编译不过——编译器替你抓住了，是好事；可是「参数加了但只在一处用」，编译器就管不了了。
2. **建发布者**：在 `on_configure` 里照着 `cloud_pub_` 那几行抄一个 `create_publisher`。为什么必须放这里：configure 是「准备资源」的阶段，`on_cleanup` 会把发布者 `reset()` 掉；放进构造函数或 active 里，反复 configure / cleanup 就会出问题。
3. **填数据**：在 `publish_scan` 里算出值再 `publish`。为什么是这里：全项目只有这一处手里有「一圈已经解好的点」。

最容易踩的两脚：

- 发布者建了、`publish` 也调了，还是没数据：因为它是 **lifecycle 发布者**，必须在 `on_activate` 里 `on_activate()` 一次才肯发，否则 `publish` 直接被丢掉且不报错。照 `scan_pub_->on_activate()` 或 `cloud_pub_` 那段抄。
- 新参数想在运行中改：只加到 `init_parameters` 不够，还要在 `parameters_callback` 里加一个 `param.get_name() == "..."` 分支。否则 `ros2 param set` 照样显示成功（ROS 2 允许改任何已声明的参数），驱动只打印一条 `[Dynamic] Changing param ... dynamically is not supported`，然后把值丢掉——这就是「命令成功 ≠ 生效」的源码级原因。想支持热改，就必须在回调里写清「收到新值要做什么」。

### 4.2 改转速

- `rpm` 是「每分钟转多少圈」。600 就是每秒 10 圈，和 `ros2 topic hz /scan` 的 10 Hz 对得上：**转一圈发一帧**，所以频率 ≈ rpm ÷ 60。这个换算帮你在任何设备上反推真实转速。
- `rpm: 0` 不是「停转」，而是「用型号默认值」。`RealLidarDriver::set_motor_speed` 里把 0 换成 600，所以 0 和 600 效果一样。真想停电机，用 `/stop_motor` 服务或 `auto_standby`。
- 热生效还是重启：热生效。`parameters_callback` 里直接调 `set_motor_speed`，日志打印 `[Dynamic] Updating RPM to`，电机不用重启。合法范围 0 到 1200，超了会被拒并打印 `[Param] Rejecting RPM`。
- 但「命令成功」不等于「硬件真变了」：C1M1 在旧驱动下怎么设都还是 10 Hz；A2M12 上频率会变（约 8.9~18.8 Hz），但参数语义是 PWM 占空比、不是转速（`README_CN.md` 里有实测表）。C1M1 的原因在内置 SDK：它按 Model ID 高 4 位选调速通道，把 C1 当成 A 系，转速命令根本没发；调速命令又只发不等回应，所以驱动无从知道失败了。本包已修复，C1 实测 480/600/720/900 → 8.01/10.02/12.01/15.01 Hz。
- 改完怎么确认，只有一条路：

```bash
ros2 topic hz /scan
```

频率没变就是没生效，别信 `Set parameter successful` 这句话。

### 4.3 排查掉线

内层状态机在 `scan_loop` 里，六个状态顺序固定，照着顺序读就知道坏在哪一步：
CONNECTING（连串口、读设备信息）→ CHECK_HEALTH（问雷达「你还正常吗」）→ WARMUP（开电机、设扫描模式）→ RUNNING（一圈圈读数并发布）→ RESETTING（丢掉失效的驱动对象、重建）→ STANDBY（电机停、串口不关）。

- 卡在 CONNECTING：反复出现 `[Driver] Failed to get device info` 与 `[FSM] Connection failed. Retrying...`。这是**串口层**问题：线、权限、设备名、波特率。拔着 USB 时也是这两行，属于正常现象（`Failed to get device info` 两行一组是因为 `Retrying...` 每 2 秒才打印一次）。
- 到 CHECK_HEALTH 就掉：`[FSM] Health error`。串口通了但雷达自检不过，多半是供电或硬件。
- RUNNING 里崩：`[FSM] Hardware unresponsive (Over 3 errors). Resetting...`，数字就是 `max_retries`。C1M1 上实测（A2M12 未验证）设 3 时，拔线后约 9.5 秒出现这一行。调小它掉线判定更快，但串口偶尔的干扰会被误判成掉线。
- 反复 RESETTING：`[FSM] Performing hardware reset (recreating driver)...` 出现多次，再看 `[FSM] Connection established.` 有没有跟着来。

diagnostics 看哪个字段：`ros2 topic echo /diagnostics` 里 `Connection` 和 `Health Code` 两个字段对应上面的状态（CONNECTING 和 CHECK_HEALTH 都显示 `Connecting...`，其余各有一种显示）；再看 `Device Info`，它让你知道「驱动以为自己在跟谁说话」——是不是你手里那台。
什么时候可以断定是硬件问题：日志里出现过 `Connection established.`，但紧接着就是 `Health error`；或者连上后 `Device Info` 里型号是空的、`N/A`。软件这边已经尽力了，去查供电、排线、换根 USB 线、换台电脑。

---

## 5. 常见报错 5 条

**① `[Driver] CRITICAL: Failed to open serial port` 配上 `Hint: Check permissions`**
原因：当前用户不在 dialout 组，或者设备名写错。A2M12 走 CP2102N 串口芯片，插上一般是 `/dev/ttyUSB0`。

```bash
sudo usermod -aG dialout $USER && ls /dev/ttyUSB*
```

加组之后必须注销重登（新开终端不算）。只想先确认是不是权限问题，临时 `sudo chmod 666 /dev/ttyUSB0` 试一次。

**② 连上了，但一直 `[Driver] Failed to get device info (data may be corrupted).`**
原因：USB 没插好，或者波特率对不上。A2M12/A2M12 是 256000，而上游模板 `param/rplidar.yaml` 默认 1000000（那是 S 系列的）。波特率错了，字节全被解析成乱码，SDK 只能如实报「数据可能损坏」。

```bash
ros2 param get /rplidar_node serial_baudrate
```

不是 256000 就改 `param/a2m12.yaml` 里的 `serial_baudrate` 再重新 launch（这个参数运行中改了不生效）。

**③ 节点 `inactive`，`ros2 topic list` 里看得见 `/scan`，但 echo 一个消息都没有**
原因：发布者没被激活。lifecycle 发布者要 `on_activate` 之后才肯发，`inactive` 状态下 `publish` 被静默丢弃。

```bash
ros2 lifecycle set /rplidar_node activate && ros2 lifecycle get /rplidar_node
```

**④ 命令行能 echo 到 `/scan`，RViz 里却一片空白**
原因：RViz 的 LaserScan 默认用 Reliable（必须送到），而驱动发布的是 Best Effort（丢了就算）。传感器数据的常规选择是 Best Effort——一帧雷达数据晚了 100 毫秒就已经没用，重传只会把队列越堵越长。两边不匹配就一个点都收不到，而且**不报错**，这是它最坑的地方。

处置：RViz 里 LaserScan → Topic → Reliability Policy → Best Effort；或者直接用配好的 `rviz/a2m12.rviz`（`a2m12.launch.py` 默认加载它）。注意 `ros2 topic hz` 和 `ros2 topic echo` 会自适应发布端的 QoS，所以它们正常不代表 RViz 正常。

**⑤ RViz 报 `Fixed Frame [map] does not exist`**
原因：Fixed Frame 写了一个没人发布的坐标系。本包默认 `frame_id: laser_a2m12`，而 `publish_tf` 默认 `false`——意思是「消息里写这个名字，但不广播 TF」。

处置：把 RViz 的 Fixed Frame 改成 `laser_a2m12`。只有当你没有机器人 TF 树、又要和别的节点拼在一起时，才开 `publish_tf:=true`（它会广播 `base_link` → `laser_a2m12`）。

```bash
ros2 run tf2_ros tf2_echo base_link laser_a2m12
```

---

## 6. 改完代码怎么验证

按顺序过一遍清单，前一条不过就别看后一条：

- [ ] `colcon build --symlink-install --packages-select rplidar_a2m12_teaching_driver` 通过，然后 `source install/setup.bash`，并确认没有旧进程还在跑（旧进程不会加载新代码）。
- [ ] 无硬件先跑：`ros2 launch rplidar_a2m12_teaching_driver a2m12.launch.py dummy_mode:=true rviz:=false`，终端能看到 `[FSM] Motor started. Entering RUNNING state.`。
- [ ] `ros2 topic hz /scan` 有数据。真雷达约 10 Hz；假数据约 93 Hz（假雷达每圈只睡 10 ms），频率和 `rpm` 都无关，别被它骗了。
- [ ] `ros2 topic echo /diagnostics --once` 里 `Connection` 不是 `Connecting...`，`Health Code` 不是 `Error`。
- [ ] RViz（去掉 `rviz:=false`）里绿点铺满一圈。改过角度相关代码就转一下雷达，看点在不在跟着转。
- [ ] 真机再原样跑一遍，去掉 `dummy_mode`。假数据能跑不等于真雷达能跑：`DummyLidarDriver` 永远不会串口超时、不会掉线、不会有型号识别失败。
- [ ] 跑单测：`colcon test --packages-select rplidar_a2m12_teaching_driver`，再用 `colcon test-result --verbose` 看哪条挂了。

---

## 7. 下一步读什么

- `doc/rplidar_driver_sequence.md`：一张时序图，把「谁在什么时候调用谁」画清楚了。看不懂 `on_configure` 为什么先连串口再建发布者，看它最快。
- `doc/PARAM_GUIDE_A2M12.md`：参数逐条讲解（含义、取值范围、改了要不要重启），标【A2M12 实测】/【C1M1 实测】的都是真机数据。
- `doc/CODE_NOTES_CN.md`：核心函数精读，讲 `scan_loop`、`update_diagnostics`、`parameters_callback`、`publish_scan` 为什么这么写、防了什么坑。
- `doc/dummy_driver_state.md`：只想搞懂假雷达行为的时候。
- 想按顺序读代码：`include/rplidar_node.hpp` 的 `DriverState` 枚举（每个状态有一行中文注释）→ `src/rplidar_node.cpp` 的 `scan_loop` → `publish_scan`。先读状态机，再读发布，最后读参数回调，这样每一段都能挂到你已经理解的那张图上。读的时候旁边开着 `doc/CODE_NOTES_CN.md`。
