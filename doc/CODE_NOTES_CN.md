# 核心代码精读（中文）

[README.md](../README.md) · [安装](../README_INSTALL.md) · [新手导航](../README_NEWBIE.md) · [中文说明](../README_CN.md) · [参数手册](PARAM_GUIDE_A2M12.md) · **代码精读**

源码里的注释保持上游英文原文，只在状态机和修过 bug 的地方加了 `[CN]` 短注释。
"为什么要这么写、防了什么坑"这类长解释都放在本页。读代码时左边开源码，右边开本页。

本页只讲最难懂的几个函数。每节开头写了文件和函数名，在编辑器里搜函数名就能跳过去
（不写行号，因为行号一改代码就会变）。标了"推测"的地方是代码里看不出来、按常理推断的。

---

## 1. 两层状态机：Lifecycle 和 DriverState

**文件**：`include/rplidar_node.hpp`（`enum class DriverState`、`on_configure` 等声明）

### 外层：为什么继承 `LifecycleNode`，不用普通 `rclcpp::Node`

普通节点一启动就开始干活，出了问题只能杀进程重来。Lifecycle 节点把"启动"拆成几步，每一步都能单独触发、单独失败：

| 回调 | 状态变化 | 做什么 | 比喻 |
|---|---|---|---|
| `on_configure` | unconfigured → inactive | 读参数、创建驱动、试连一次串口、建发布者 | 把工具准备好 |
| `on_activate` | inactive → active | 打开发布者、启动 scan 线程 | 开工 |
| `on_deactivate` | active → inactive | 停 scan 线程、关发布者、停电机，串口不关 | 暂停，不收工具 |
| `on_cleanup` | inactive → unconfigured | 关串口、销毁驱动对象 | 把工具收起来 |

好处是上层系统（比如 Nav2 的 `lifecycle_manager`）可以统一管理一串节点的启动顺序。

几个容易忽略的细节：

- **`on_configure` 连不上串口也返回 SUCCESS**，只打一条 WARN。真正的"连上为止"交给 activate 之后的状态机，
  所以先启动节点、后插雷达也能工作。
- **`on_activate` 很快就返回**：它只开发布者、开线程。连串口、开电机这些慢活都在线程里做，
  所以 `ros2 lifecycle set ... activate` 不会因为硬件慢而卡住。
- **`on_deactivate` 的顺序很重要**：先 `is_scanning_ = false` 并 `join()` 等线程真正退出，再关发布者和电机。
  反过来的话，线程可能还在往一个已经关掉的发布者里发数据。

### 内层：`DriverState` 六个状态

```
CONNECTING -> CHECK_HEALTH -> WARMUP -> RUNNING
     ^                                   |  连续读失败 > max_retries 次
     +--------- RESETTING <--------------+  （例如拔了 USB）
                                 STANDBY（电机停、串口不断，从 RUNNING 进入）
```

内层只在外层是 active 时运行。**拔 USB 时外层一直是 active**，恢复全靠内层状态机。
新手最常见的困惑"节点明明是 active，为什么没数据"就是这个原因：外层 active 只表示允许干活，内层可能正卡在重连里。

---

## 2. `scan_loop()`：为什么单开一个线程

**文件**：`src/rplidar_node.cpp`，函数 `RPlidarNode::scan_loop`

### 为什么不在主线程里读串口

`grab_scan_data()` 是阻塞的：调用后要等雷达转完一圈、数据收齐才返回。USB 拔掉时还要等到超时，
SDK 的 `DEFAULT_TIMEOUT` 是 2000 ms。

本节点用 `SingleThreadedExecutor`，参数回调、服务、`/diagnostics` 定时器、lifecycle 的 `get_state` 全在**同一个主线程**里排队。
如果主线程卡在读串口上，这些全都排不上队，整个节点看起来像死了。所以读串口单独放进 `scan_thread_`，主线程保持空闲。

代价是两个线程会同时碰 `driver_`：

- `driver_mutex_`：谁要通过串口和雷达说话（读一圈、改转速）就先上锁。否则两条命令的字节会在串口上混在一起。
- `std::atomic`：跨线程的标志位（`is_scanning_`、`current_state_`、`standby_requested_` 等）。
  普通 `bool` 在两个线程同时读写时，可能读到半新半旧的值。
- **只有 scan 线程能写 `current_state_` 和动硬件**。服务回调只置一个 atomic 标志，由 scan 线程在下一圈去执行。
  这样"谁能改状态机"永远只有一个答案。

SDK 内部（`src/sdk/src/sl_async_transceiver.cpp`）还有两个线程：`_rxThread` 从串口收字节放进 `_rxQueue`，
`_decoderThread` 从队列取出来解包。所以 `grab_scan_data()` 拿到的已经是解好的测量点。

### 每个状态在防什么

| 状态 | 做什么 | 防的坑 |
|---|---|---|
| CONNECTING | 没有驱动对象就造一个；打开串口；失败睡 1 秒重试 | 拔着 USB 时就一直停在这里，直到插回去 |
| CHECK_HEALTH | 问自检结果：0 正常、1 警告都继续；2 错误就软复位一次、睡 2 秒 | 有些设备会**锁存**错误码，只重连不复位会永远报错，状态机在两个状态间无限转圈。所以每次连接只复位一次（`health_reset_attempted_`），还不行才断开重连 |
| WARMUP | `start_motor()` 开电机、选模式，算 `range_max` | 先问健康再开电机：问一句很便宜，开电机要几百毫安。**推测**：设备有故障时直接开电机可能把小问题放大成堵转 |
| RUNNING | 上锁读一圈 → 解锁 → 发布；第一圈成功后补发配置转速 | `publish_scan` 放在锁外，发消息时不占串口。补发转速的原因见第 5 节 kickstart |
| RESETTING | 销毁旧驱动对象、立刻造新的，睡 2 秒回 CONNECTING | 见下 |
| STANDBY | 什么都不做 | 电机停、串口开着；进出 STANDBY 都在 `switch` 之前统一处理 |

**为什么 RESETTING 要整个重建驱动对象，而不是在旧对象上再 `connect()`？**
驱动对象里不只有配置，还有打开的串口句柄、SDK 的收发线程、接收缓冲区、`_isConnected` 之类的内部标志。
USB 拔掉后这些都已经失效。在旧对象上重连，内部状态还停在上一次。第 9.2 节那个 bug（连接没完成却被当成已连接）
就是这类"半连上"状态的例子。重建对象把 SDK 内部状态全部清零，代价是多等 2 秒。

重建发生在 `driver_mutex_` 锁内，`reset()` 之后马上 `make_unique` 新对象，别的线程不会看到空指针。
同时 `initial_reset_required_ = true`，表示"配置的转速还没写进硬件"，下一次进 RUNNING 时会补发。

### 循环末尾的两个 sleep

- 不在 RUNNING 时每圈睡 10 ms：这个循环转得很快，不睡会白白占满一个 CPU 核。
- RUNNING 里读失败后睡 1 ms，而且这个 sleep 在锁**里面**。这是 [README_CN 第 10 节](../README_CN.md) 留的思考题。

---

## 3. `update_diagnostics()`：为什么连 `driver_mutex_` 都不能拿

**文件**：`src/rplidar_node.cpp`，函数 `RPlidarNode::update_diagnostics`

这个函数不是我们自己调的，是 `diagnostic_updater` 的定时器（约 1 秒一次）在**主线程**里调的。

原版这里第一行就 `lock_guard(driver_mutex_)`。拔 USB 时，scan 线程拿着这把锁在 `grab_scan_data()` 里等 2 秒超时，
诊断回调抢锁，主线程跟着停住，排在后面的 `get_state`、`param set` 全都要等。实测 `get_state` 等了 4.2 秒。
节点因为"要报告自己的状态"而假死，而状态恰恰是排查问题时最需要的东西。

而且这把锁本来就是多余的：函数根本不碰 `driver_`，只读 atomic、`params_` 和 `cached_device_info_`。

修法（[README_CN 9.3](../README_CN.md)）：

- 不再拿 `driver_mutex_`。
- `cached_device_info_` 用一把小锁 `info_mutex_` 保护，只圈住一次字符串拷贝，绝不涉及串口。
- `params_.rpm` 只在参数回调里写，参数回调和诊断都在主线程，不会同时执行，不用锁。

**以后想在这里加东西**：不能同步去问硬件。要让 scan 线程把结果存进 atomic 或小锁保护的缓存，这里只读缓存。

修复后实测：拔着 USB 时 `ros2 lifecycle get` 平均 0.87 秒，和插着时一样。

---

## 4. `parameters_callback()`：在线改参数

**文件**：`src/rplidar_node.cpp`，函数 `RPlidarNode::parameters_callback`

`ros2 param set /rplidar_node rpm 600` 会调用这里。它在**主线程**执行，第一行就 `lock(driver_mutex_)`，
因为 scan 线程可能正在用同一个 `driver_` 读串口。驱动没连上时直接拒绝：`Driver not ready`。

在线可改的参数分两类：

| 类别 | 参数 | 生效方式 |
|---|---|---|
| 直接改硬件 | `rpm` | `set_motor_speed()` 立刻发给雷达 |
| 直接改硬件 | `scan_mode` | `stop_motor()` → 等 500 ms → `start_motor(新模式)`，因为设备转着时不接受换模式 |
| 只改内部开关 | `interpolated_rays`、`computed_ray_count`、`auto_standby` | 下一圈 `publish_scan` / `scan_loop` 自动按新值来，不停电机 |
| 只改内部开关 | `publish_point_cloud` | **只翻转标志**，`/cloud` 发布者要 deactivate 再 activate 才会真正激活 |

其余参数在线改了只打一条警告，不生效。

返回 `successful = false` 时，ROS 会让这次设置作废，参数服务器上的值退回旧值。读代码时要注意三个"不一致"的地方：

1. **rpm 不检查结果**：`set_motor_speed()` 的返回值没有被检查，`params_.rpm` 无条件更新。
   而且 SDK 对调速命令本来就"只发不等回应"。所以参数显示的值不代表雷达真的在这个转速。
   C1M1 在旧驱动下实测：rpm 设成多少都是 10 Hz，原因是 SDK `checkMotorCtrlSupport()` 按 Model ID 高 4 位把 C1（0x41）当成 A 系、没发转速命令（本包已修复，实测 480 → 8.01 Hz）；A2M12 实测：频率会变（9.2~18.8 Hz），但该值是 PWM 占空比而不是转速（[README_CN 第 5 节](../README_CN.md)）。
2. **scan_mode 失败后状态分裂**：新模式启动失败时，代码退回自动模式并返回 false，参数值退回旧值；
   但雷达实际跑的是"自动选出的模式"，不一定等于旧值。
3. **scan_mode 切换会卡住主线程**：stop + 500 ms + start（新协议型号还要再预热 1 秒）都在主线程、都拿着锁。
   这期间 `get_state` 等请求要排队。

---

## 5. wrapper 层：`lidar_driver_wrapper.cpp`

**文件**：`include/lidar_driver_wrapper.hpp`、`src/lidar_driver_wrapper.cpp`

### 为什么要在 SDK 外面再包一层

思岚 SDK 暴露的是厂家风格：`sl::ILidarDriver` 指针、`sl_result` 返回码、很长的结构体名。
如果节点直接用 SDK，换 SDK 版本或换一家雷达就得改整个节点；没插雷达就跑不起来；拔线、健康报错这些情况也没法手动制造来测试。

所以中间加了一层接口 `LidarDriverInterface`，可以想成墙上的"插座标准"。节点只认 `connect` / `start_motor` / `grab_scan_data`
这些函数名，插座上插两种"插头"：

- `RealLidarDriver`：真雷达，内部调 SDK。
- `DummyLidarDriver`：假雷达，自己编数据。`dummy_mode:=true` 时用它。

想支持新雷达，就写一个新类继承 `LidarDriverInterface`，把纯虚函数实现掉。节点代码不用动。

### `connect()`：接通线 + 读设备信息

三步：`createSerialPortChannel()` 打开串口 → `drv_->connect()` 让 SDK 接管 → `getDeviceInfo()` 读型号、序列号、固件版本。

- 波特率配错时，串口能打开，但 `getDeviceInfo()` 一个字节都等不回来，`connect()` 返回 false，
  日志反复出现 `Failed to get device info`。看到这条先怀疑波特率，A2M12 必须是 256000。
- 第三步失败时要 `drv_->disconnect()` 回滚前两步，否则 SDK 以为自己还连着，下一轮会拿全零的设备信息去识别型号，
  误判成 A 系列（[README_CN 9.2](../README_CN.md)）。
- 型号判断交给 `detect_and_init_strategy()`：用 SDK 的 `getLIDARTechnologyType` / `getLIDARMajorType` 判断新老协议。
  具体型号名只命中两个：新协议分支里的 Model ID 65（0x41）= RPLIDAR C1；老协议 A 系分支里的 Model ID 44（0x2C）= RPLIDAR A2M12（其余 A 系型号仍打印 A-Series (Triangulation)）。后者是本包相对 C1M1 包唯一新增的 C++ 改动。

### `start_motor()`：两种型号启动流程不同

- **新协议（S/C 系，包括 A2M12）**：设转速 → 等 1 秒让电机转起来 → 查询支持的扫描模式 → 选一个 → `startScanExpress`。
  `scan_mode` 为空时的自选顺序：用户指定的名字 → 名字含 `DenseBoost` → 名字含 `Sensitivity` → 雷达的典型模式。
- **老协议（A 系）**：电机是开环 PWM 型，先用 600 "猛踩一脚"（kickstart）带起来，等 200 ms。
  静止电机要克服静摩擦，直接给一个低占空比可能转不起来。用户配置的转速由节点在**第一圈数据成功后**补发
  （`scan_loop` RUNNING 分支的 `initial_reset_required_`）。

rpm 为 0 时兜底成 600。`set_motor_speed(0)` 也是 600，不是停转；停转要用 `/stop_motor` 服务。

### `grab_scan_data()`：一次等一整圈

`grabScanDataHq` 会等凑齐一整圈 0~360° 才返回，等待上限 2000 ms。所以这个函数最坏会卡 2 秒，第 2、3 节的问题都源于此。

- `count` 既是输入也是输出：调用前填"缓冲最多能装几个点"，返回后 SDK 改成实际点数。
- 缓冲是 `static` 的 8192 个点，省得每圈重新分配。它只被 scan 线程在 `driver_mutex_` 锁内调用，不会两个线程同时写。
- 8192 是保险值：取小了 SDK 会按容量截断，表现为某一段角度永远缺点，这种 bug 很难看出来。
- `angle_compensate` 为 true 时才调 `ascendScanData` 排序并做几何换算。

拔 USB 的因果链：每次读超时 2 秒 → 失败计数 +1 → 超过 `max_retries`（3）次进 RESETTING。实测拔掉后约 9.5 秒判定掉线。

### `getHealth()` 和 `reset()`

`getHealth()` 返回 0 / 1 / 2，直接对应 SDK 的 `SL_LIDAR_STATUS_OK` / `WARNING` / `ERROR`。没连上时直接返回 2。

`reset()` 是软复位：发一条复位命令，让雷达自己重启，不重开串口。SDK 文档说它用来帮雷达跳出"自我保护模式"，
而 `getHealth()` 问的正是"你是不是在自我保护"。所以 CHECK_HEALTH 里报 2 时先复位一次。
只复位一次的原因：反复复位等于让雷达一直重启，永远没机会出数据。

### `DummyLidarDriver`：假雷达

它不碰硬件，用 `MockDriverState` 记三个状态：DISCONNECTED、CONNECTED、SCANNING。`start_motor` 只在 CONNECTED 时成功，
所以测试里故意乱序调用，就能验证上层有没有处理失败，不用真的去拔线。

它编的数据：

- 每圈 360 个点，第 i 个点角度是 i 度（Q14 格式里 16384 = 90°，代码写的是 `i * 16384 / 90`），正好一整圈。
- 距离是 2.0 ± 0.5 米的正弦波，每圈相位前进一点，RViz 里是一个缓慢起伏的圆。
- `quality` 固定 47；每次 `grab` 睡 10 ms，实测 `/scan` 约 93 Hz，比真雷达的 10 Hz 快得多。
- 上报的最远量程是 40 米。

用途：没有雷达也能把整条链路跑通（学习、CI、回归测试）。它不是在模拟真实场景，别拿它的数据调参数。

---

## 6. `publish_scan()`：原始点怎么变成 `/scan`

**文件**：`src/rplidar_node.cpp`，函数 `RPlidarNode::publish_scan`

1. **换单位**。雷达给的是整数：`angle_z_q14`（Q14 定点角度）、`dist_mm_q2`（毫米 × 4）、`quality`。
   - 角度 × `Q14_TO_RAD`。`Q14_TO_RAD = (90.0 / 16384.0) * (M_PI / 180.0)`：16384 格 = 90°，再把度换成弧度。
   - 距离 `dist_mm_q2 / 4000.0` 得到米；为 0 表示无效，记成无穷远。
2. **镜像**。`angle = TWO_PI - angle`：雷达原始角度是顺时针，ROS 约定逆时针（X 朝前、Y 朝左）。
   少了这一步，整幅图左右翻转，看起来却像一个完全正常的房间，很难发现。
3. **安装补偿**。`angle += angle_offset`，单位是**弧度**，正值 = 逆时针。
   注意：`include/rplidar_node.hpp` 里 `Parameters::angle_offset` 的英文注释写的是 "degrees"，这是上游注释的错误，
   代码实际按弧度用（`param/rplidar.yaml` 也写的是 radians）。
4. **归一化**。用 `while` 而不是 `if`，因为 offset 可能超过一整圈。
   `symmetric_angle_range` 决定区间是 `[-π, π)` 还是 `[0, 2π)`；上游标了 TEMPORARY，下个大版本会只留对称的一种。
5. **排序**。一圈的点不保证按角度顺序到达，所以 `std::sort`。
6. **装进 LaserScan**。
   - `interpolated_rays: false`：光束数 = 实测点数，每个点按角度放进最近的格子，同一格保留更近的距离。
   - `interpolated_rays: true`：光束数 = `computed_ray_count`，相邻两个实测点连成线段，求每根虚拟光束和线段的交点。
     这会产生插值出来的点。`computed_ray_count` 填 0 时 `angle_increment = 2π / 0`，代码不做校验，别这么填。
7. **`range_max`** 取 WARMUP 里算好的 `cached_current_max_range_`：`max_distance` 为 0 时用硬件量程，否则取两者较小值。
   它只是写进消息的声明，**不会裁掉**超出范围的点。

---

## 7. 读完可以自己验证的三件事

都用假雷达做，不需要硬件：`ros2 launch rplidar_a2m12_teaching_driver a2m12.launch.py dummy_mode:=true rviz:=false`

1. **两层状态**：`ros2 lifecycle set /rplidar_node deactivate`，观察驱动日志里 `[Lifecycle] Deactivating` 和
   `[FSM] Scan loop terminated` 的先后顺序，对照第 1 节 `on_deactivate` 的顺序说明。
2. **在线改参数**：`ros2 param set /rplidar_node publish_point_cloud true`，再 `ros2 topic hz /cloud`。
   没有数据；deactivate 再 activate 之后才有。对照第 4 节的表。
3. **镜像**：先在 RViz 里看假雷达的圆，圆上有一块"鼓起来"，它在慢慢绕圈（正常是逆时针）。
   然后把 `publish_scan()` 里的 `TWO_PI - ` 删掉，重新编译再看：鼓起来的那块会改成顺时针转。
   真雷达上这就是"整幅图左右翻转"。看完记得改回来：`git checkout src/rplidar_node.cpp`。
