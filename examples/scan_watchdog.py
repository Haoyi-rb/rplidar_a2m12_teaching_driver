#!/usr/bin/env python3
"""
scan_watchdog.py —— 教学示例：/scan 看门狗

功能：
  订阅 /scan。如果 timeout_sec（默认 3 秒）没收到数据，就打印警告，
  再查询驱动节点的 Lifecycle 状态，按状态决定怎么处理：

    active        驱动内部的 scan_loop 状态机正在自动重连（比如 USB 被拔了），
                  不要插手，只提示用户检查线缆。
                  如果 force_restart=true，就主动 deactivate -> activate，
                  演示"手动重启节点生命周期"。
    inactive      节点被人 deactivate 了 -> 调用 activate 把它叫醒。
    unconfigured  节点被 cleanup 了 -> 先 configure 再 activate。
    查不到        驱动进程不在了（崩溃或没启动），watchdog 救不了，只报错。

运行：
  ros2 run rplidar_a2m12_teaching_driver scan_watchdog.py
  ros2 run rplidar_a2m12_teaching_driver scan_watchdog.py --ros-args -p force_restart:=true
"""

import time

import rclpy
from lifecycle_msgs.msg import State, Transition
from lifecycle_msgs.srv import ChangeState, GetState
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import LaserScan


class ScanWatchdog(Node):

    def __init__(self):
        super().__init__('scan_watchdog')

        # ---- 参数 ----
        self.declare_parameter('target_node', 'rplidar_node')
        self.declare_parameter('timeout_sec', 3.0)
        # force_restart：教学开关。
        #   false（默认）：节点是 active 时相信驱动自己的重连机制，不插手。
        #   true：节点是 active 但没数据时，强制走一遍
        #         active -> deactivate -> inactive -> activate -> active，
        #         用来观察 on_deactivate / on_activate 里到底发生了什么。
        #   注意：拔着 USB 时强制重启没有意义，插回去之前雷达照样没数据；
        #         这个开关的价值在于让你看清 Lifecycle 的流转过程。
        self.declare_parameter('force_restart', False)

        target = self.get_parameter('target_node').value
        self.timeout = float(self.get_parameter('timeout_sec').value)
        self.force_restart = bool(self.get_parameter('force_restart').value)

        # 用单调时钟计时，不受系统时间/仿真时间跳变影响。
        self.last_scan = time.monotonic()
        self.outage_start = None      # 本次断流开始的时间（用来算中断了多久）
        self.outage_reported = False  # 本次断流是否已经提示过
        self.last_warn = 0.0          # 上次打印"没收到 /scan"的时间（限频用）
        self.busy = False             # 是否有一串状态切换请求正在进行

        # 驱动发布 /scan 用的是 SensorDataQoS（best_effort），订阅端必须兼容，
        # 否则用默认的 reliable 订阅会一条都收不到。
        self.create_subscription(
            LaserScan, 'scan', self.on_scan, qos_profile_sensor_data)

        # 每个 Lifecycle 节点自带这两个服务：
        #   /<节点名>/get_state     查询当前状态
        #   /<节点名>/change_state  请求状态切换
        self.get_state_cli = self.create_client(GetState, f'/{target}/get_state')
        self.change_state_cli = self.create_client(
            ChangeState, f'/{target}/change_state')

        # 每秒检查一次。
        self.create_timer(1.0, self.check)
        self.get_logger().info(
            f'看门狗启动：监视 /scan，超时 {self.timeout:.1f}s，'
            f'force_restart={self.force_restart}')

    def on_scan(self, _msg):
        now = time.monotonic()
        if self.outage_start is not None:
            gap = now - self.outage_start
            self.get_logger().info(f'/scan 恢复了，中断约 {gap:.1f}s。')
            self.outage_start = None
        self.outage_reported = False
        self.last_warn = 0.0
        self.last_scan = now

    def check(self):
        silent = time.monotonic() - self.last_scan
        if silent < self.timeout or self.busy:
            return

        now = time.monotonic()
        if self.outage_start is None:
            self.outage_start = self.last_scan
        # 每秒都检查，但每 5 秒才打印一次，避免刷屏淹没驱动日志。
        if now - self.last_warn >= 5.0:
            self.get_logger().warn(f'已经 {silent:.1f}s 没收到 /scan 了！')
            self.last_warn = now

        if not self.get_state_cli.service_is_ready():
            self.get_logger().error(
                '找不到驱动的 get_state 服务：驱动节点没启动或已经崩溃。')
            return

        # 用异步调用(call_async)而不是同步 call()：
        # 定时器回调跑在执行器线程里，同步等待会把执行器自己卡住，
        # 服务的回应永远处理不到 -> 死锁。
        self.busy = True
        future = self.get_state_cli.call_async(GetState.Request())
        future.add_done_callback(self.on_state)

    def on_state(self, future):
        self.busy = False
        result = future.result()
        if result is None:
            self.get_logger().error('get_state 调用失败。')
            return
        state = result.current_state

        # 异步调用的回应可能来得很晚（实测拔 USB 时驱动的服务要等 4 秒以上）。
        # 如果回应到达时 /scan 已经恢复了，这个回应就过时了，直接丢弃。
        if self.outage_start is None:
            return

        if state.id == State.PRIMARY_STATE_ACTIVE:
            if self.force_restart:
                self.get_logger().warn(
                    '[force_restart] 节点是 active，强制 deactivate -> activate')
                self.run_transitions([Transition.TRANSITION_DEACTIVATE,
                                      Transition.TRANSITION_ACTIVATE])
            elif not self.outage_reported:
                self.get_logger().warn(
                    '驱动是 active，内部状态机正在自动重连。'
                    '请检查 USB 线 / 串口号 / 供电，插回去后会自己恢复。')
                self.outage_reported = True

        elif state.id == State.PRIMARY_STATE_INACTIVE:
            self.get_logger().warn('驱动是 inactive（被暂停了），发送 activate。')
            self.run_transitions([Transition.TRANSITION_ACTIVATE])

        elif state.id == State.PRIMARY_STATE_UNCONFIGURED:
            self.get_logger().warn(
                '驱动是 unconfigured，发送 configure -> activate。')
            self.run_transitions([Transition.TRANSITION_CONFIGURE,
                                  Transition.TRANSITION_ACTIVATE])

        else:
            # finalized，或者正处在 configuring/activating 等中间状态
            self.get_logger().warn(f'驱动状态是 {state.label}，暂不处理。')
            self.outage_reported = True

    def run_transitions(self, transitions):
        """按顺序请求一串状态切换，上一个成功了才发下一个。"""
        if not transitions:
            # 全部完成：重置计时，给驱动 timeout_sec 的时间出第一帧，
            # 避免下一秒又判定超时、重复重启。
            self.busy = False
            self.last_scan = time.monotonic()
            return

        self.busy = True
        req = ChangeState.Request()
        req.transition.id = transitions[0]

        def done(future):
            res = future.result()
            if res is None or not res.success:
                self.get_logger().error(
                    f'状态切换 {transitions[0]} 失败，稍后重试。')
                if transitions[0] == Transition.TRANSITION_CONFIGURE:
                    self.get_logger().error(
                        'configure 失败，请看驱动终端里 [Lifecycle] 附近的报错。')
                self.busy = False
                self.last_scan = time.monotonic()  # 冷却一个超时周期
                return
            self.get_logger().info(f'状态切换 {transitions[0]} 成功。')
            self.run_transitions(transitions[1:])

        self.change_state_cli.call_async(req).add_done_callback(done)


def main():
    rclpy.init()
    node = ScanWatchdog()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass  # Ctrl+C 正常退出，不打印报错堆栈
    except Exception:
        # Humble 下 Ctrl+C 时 rclpy 可能先关闭 context，spin 里会抛 RCLError。
        # context 已关闭说明是正在退出，忽略；否则是真错误，照常抛出。
        if rclpy.ok():
            raise
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
