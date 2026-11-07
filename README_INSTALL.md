# 零基础安装指南（A2M12 教学版）

[README.md](README.md) · **安装** · [新手导航](README_NEWBIE.md) · [中文说明](README_CN.md) · [参数手册](doc/PARAM_GUIDE_A2M12.md) · [代码精读](doc/CODE_NOTES_CN.md)

这一页写给**第一次在自己电脑上跑 ROS 2** 的同学：从一台装好 Ubuntu 的电脑开始，到 RViz 里看到雷达点云为止。
每一步后面都有"怎么确认这一步成功了"，没确认就别往下走。

装好之后去看 [README_NEWBIE.md](README_NEWBIE.md)。

---

## 0. 你需要准备什么

| 项目 | 要求 | 怎么确认 |
|---|---|---|
| 系统 | **Ubuntu 22.04**（不是 20.04，也不是 24.04） | `lsb_release -ds` 显示 `Ubuntu 22.04.x LTS` |
| ROS 2 | **Humble**（和 Ubuntu 22.04 配套） | 第 1 步装完后 `ls /opt/ros` 能看到 `humble` |
| 雷达 | RPLIDAR A2M12 / A2M12 + 配套 USB 线 | 第 5 步再接，前面不需要 |
| 网络 | 能访问 ROS 软件源（第 1 步要下载约 2 GB） | |

虚拟机能用，但 RViz 可能很卡，USB 还要手动"连接到虚拟机"。有条件就用实体机。

---

## 1. 安装 ROS 2 Humble

**按官方文档安装**，选 **Desktop** 版（自带 RViz）：

> <https://docs.ros.org/en/humble/Installation/Ubuntu-Install-Debs.html>

官方文档里的软件源和密钥的配置方法会更新，以官方页面为准，这里不抄命令。按页面做到 `sudo apt install ros-humble-desktop`，
再加上开发工具 `sudo apt install ros-dev-tools` 即可。

国内网络慢的话，很多同学用"鱼香 ROS"一键安装脚本（fishros.com）。它是第三方脚本，会改你的软件源，
具体命令以它的官网为准；用之前问一下带你的学长学姐。

**确认成功**：

```bash
source /opt/ros/humble/setup.bash
ros2 --help | head -3          # 能打印用法，不是 "command not found"
which rviz2 colcon rosdep      # 三个都有路径
```

如果 `colcon` 或 `rosdep` 没有：`sudo apt install python3-colcon-common-extensions python3-rosdep`。

---

## 2. 初始化 rosdep（每台电脑只做一次）

rosdep 会帮你自动安装包需要的依赖。

```bash
sudo rosdep init        # 如果提示 "already exists"，说明做过了，跳过这句
rosdep update
```

`rosdep update` 在国内经常连不上 GitHub 而失败。多试几次，或者换一个网络。鱼香 ROS 里也有 `rosdepc` 可以用。

---

## 3. 拿到代码并编译

### 3.1 拿代码

本教学版**还没有公开**，代码向带你的学长学姐要（实验室 git 服务器、U 盘都行）。
**不要**直接 clone 上游 `github.com/frozenreboot/rplidar_driver`：那是原版，没有 A2M12 配置、看门狗和这些文档。

放到 `~/A2M12_ros/rplidar_a2m12_teaching_driver`，然后切到教学版：

```bash
mkdir -p ~/A2M12_ros
cd ~/A2M12_ros
# git clone <学长给你的仓库地址> rplidar_a2m12_teaching_driver
cd rplidar_a2m12_teaching_driver
git checkout teaching/a2m12        # 或者某个发布标签，例如 a2m12-v0.3
git log --oneline -1              # 确认在教学版上
```

### 3.2 装依赖、编译

**一定要在 `~/A2M12_ros` 下编译**，不要在 `~`（会把家目录里所有工程都扫一遍），也不要在 `rplidar_a2m12_teaching_driver` 里面（会在包里生成 build 目录）。

```bash
cd ~/A2M12_ros
source /opt/ros/humble/setup.bash
rosdep install --from-paths rplidar_a2m12_teaching_driver --ignore-src -y
colcon build --symlink-install
```

第一次编译要一两分钟（大部分时间在编译思岚 SDK）。`--symlink-install` 的意思是：之后改 Python、launch、yaml、rviz 文件不用重新编译；改 C++ 必须重新 `colcon build`。

**确认成功**：最后一行是 `Summary: 1 package finished`，没有 `Failed`。

---

## 4. 配置终端（每台电脑只做一次）

每开一个新终端都要 `source` 两个文件，否则会报"找不到包"。把它们写进 `~/.bashrc`，以后自动执行：

```bash
echo 'source /opt/ros/humble/setup.bash' >> ~/.bashrc
echo '[ -f ~/A2M12_ros/install/setup.bash ] && source ~/A2M12_ros/install/setup.bash' >> ~/.bashrc
echo 'export ROS_DOMAIN_ID=<你的编号>' >> ~/.bashrc      # 见下面的说明，换成一个数字
source ~/.bashrc
```

**`ROS_DOMAIN_ID` 一定要设，而且每个人不一样。** 同一个局域网（比如实验室 Wi-Fi）里，ROS 2 节点会自动互相发现。
如果大家都用默认的 0，你的 RViz 可能显示的是旁边同学的雷达，`ros2 topic list` 里也会出现别人的话题。
找带你的人分配一个 1~100 之间的数字。

**确认成功**：新开一个终端，执行 `ros2 pkg prefix rplidar_a2m12_teaching_driver`，能打印出 `.../a2m12_ros/install/rplidar_a2m12_teaching_driver`。

---

## 5. 先不接雷达，用假数据跑一遍

```bash
ros2 launch rplidar_a2m12_teaching_driver a2m12.launch.py dummy_mode:=true
```

**确认成功**：

- 终端里出现 `[FSM] Motor started. Entering RUNNING state.`
- 弹出 RViz 窗口，中间有一圈绿色的点，在慢慢"呼吸"
- 另开一个终端，`ros2 topic hz /scan` 显示约 93 Hz（假数据就是这么快，真雷达是 10 Hz）

这一步通过，说明 ROS 2、编译、RViz 都没问题。后面再出问题，就只可能是 USB、权限或者雷达本身。

按 `Ctrl+C` 退出。

---

## 6. 串口权限（每台电脑只做一次）

Linux 下普通用户默认没有权限打开串口。把自己加进 `dialout` 组：

```bash
sudo usermod -aG dialout $USER
```

然后**注销并重新登录**（或者重启）。只新开一个终端没用。

**确认成功**：`groups` 的输出里有 `dialout`。

---

## 7. 接上雷达

插上 A2M12 的 USB 线，然后：

```bash
ls -l /dev/ttyUSB*
```

**确认成功**：能看到 `/dev/ttyUSB0`（如果插了别的串口设备，可能是 `ttyUSB1`），所属组是 `dialout`。

A2M12 用的是 Silicon Labs CP2102N 串口芯片。想确认 `ttyUSB0` 就是雷达：

```bash
udevadm info -q property -n /dev/ttyUSB0 | grep -E "ID_VENDOR_ID|ID_MODEL_ID|ID_SERIAL="
# 应该看到 ID_VENDOR_ID=10c4、ID_MODEL_ID=ea60
```

**插上后 `/dev/ttyUSB*` 一闪就没了？** Ubuntu 22.04 自带的盲文显示器服务 `brltty` 有时会抢占 USB 串口设备。
`sudo dmesg | tail -20` 里如果看到 `brltty`，执行 `sudo apt remove brltty` 后重新插拔。

---

## 8. 固定设备名（可选，推荐）

插拔几次之后，雷达可能从 `ttyUSB0` 变成 `ttyUSB1`，驱动就连不上了。用 udev 规则给它一个固定名字 `/dev/rplidar`：

```bash
cd ~/A2M12_ros/rplidar_a2m12_teaching_driver
./scripts/create_udev_rules.sh        # 会要 sudo 密码
```

然后拔掉雷达再插上，**确认成功**：`ls -l /dev/rplidar` 指向某个 `ttyUSB*`。

以后启动时用这个名字：

```bash
ros2 launch rplidar_a2m12_teaching_driver a2m12.launch.py serial_port:=/dev/rplidar
```

**注意**：这个脚本按芯片型号（`10c4:ea60`）匹配，**所有用 CP210x 芯片的设备都会被叫成 `/dev/rplidar`**，
比如 ESP32 开发板、一些 USB 转串口线。电脑上同时插了这类设备时，`/dev/rplidar` 可能指向错的那个。
这种情况先拔掉其他设备，或者请学长帮你把规则改成按序列号匹配（序列号见上一步 `ID_SERIAL`）。

---

## 9. 真机跑起来

```bash
ros2 launch rplidar_a2m12_teaching_driver a2m12.launch.py
```

**确认成功**：

- 终端依次出现 `[FSM] Connection established.`、`Type: RPLIDAR A2M12`、`[FSM] Motor started. Entering RUNNING state.`
- RViz 里出现周围环境的轮廓（绿色的点）；用手在雷达前面挥一挥，点会跟着变
- `ros2 topic hz /scan` 约 10 Hz

到这里安装就全部完成了。接下来看 [README_NEWBIE.md](README_NEWBIE.md)。

---

## 10. 安装自检清单

全部打勾才算装好：

- [ ] `lsb_release -ds` 是 Ubuntu 22.04
- [ ] `ros2 pkg prefix rplidar_a2m12_teaching_driver` 能打印路径（新开终端也行）
- [ ] `echo $ROS_DOMAIN_ID` 是分配给你的数字，不是空的
- [ ] `groups` 里有 `dialout`
- [ ] `dummy_mode:=true` 能在 RViz 里看到一圈点
- [ ] 接上雷达后，RViz 里能看到周围环境，`/scan` 约 10 Hz

---

## 11. 常见问题

| 现象 | 原因 | 怎么办 |
|---|---|---|
| 启动后 `ros2 lifecycle get /rplidar_node` 显示 `unconfigured [1]`，`/scan` 没数据 | launch 的 CONFIGURE 请求比节点的服务早到（老版本 launch 或机器很慢） | 等 5 秒仍如此就手动补齐：`ros2 lifecycle set /rplidar_node configure`（本包的 `a2m12.launch.py` 已把请求延后 3 秒，正常不会遇到） |
| `Package 'rplidar_a2m12_teaching_driver' not found` | 当前终端没 source `install/setup.bash`，或者没编译成功 | 做第 4 步；或者手动 `source ~/A2M12_ros/install/setup.bash` |
| `ros2: command not found` | 没 source `/opt/ros/humble/setup.bash` | 做第 4 步 |
| `rosdep update` 报网络错误 | 连不上 GitHub | 换网络重试，或用 `rosdepc` |
| `rosdep install` 报 `Cannot locate rosdep definition` | 没做 `rosdep update` | 做第 2 步 |
| 编译报 `Could not find a package configuration file provided by "xxx"` | 缺依赖 | 重新执行第 3.2 步的 `rosdep install` |
| 驱动日志 `Failed to open serial port` + `Hint: Check permissions` | 没有串口权限，或设备名不对 | 做第 6 步并重新登录；用 `ls /dev/ttyUSB*` 确认设备名 |
| 一直 `Failed to get device info` + `Connection failed. Retrying...` | USB 没插好，或者波特率不对 | 检查 USB；`ros2 param get /rplidar_node serial_baudrate` 必须是 256000 |
| RViz 里一个点都没有，但 `ros2 topic hz /scan` 有数据 | RViz 的 QoS 或 Fixed Frame 不对 | 用 `a2m12.launch.py` 自带的 RViz 配置；自己开的 RViz 要把 Reliability 改成 Best Effort、Fixed Frame 改成 `laser_a2m12` |
| RViz 窗口打不开 / 报 OpenGL 错误 | 在 SSH 或没有显示器的机器上 | 加 `rviz:=false`，在有显示器的电脑上看 |
| RViz 里的点不是你的雷达 / 话题里有陌生的东西 | `ROS_DOMAIN_ID` 和别人一样 | 做第 4 步，设一个只属于你的编号 |
| `/dev/ttyUSB0` 一闪就没了 | `brltty` 抢占设备 | 见第 7 步 |

还解决不了，把驱动终端的**完整输出**复制下来去问人，比截图有用得多。
