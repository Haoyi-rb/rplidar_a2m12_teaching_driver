"""
@file   a2m12.launch.py
@brief  Teaching launch file for RPLIDAR A2M12.

Same lifecycle flow as rplidar.launch.py (process start -> CONFIGURE ->
inactive -> ACTIVATE), but loads param/a2m12.yaml and exposes the few
arguments a beginner usually needs.

  ros2 launch rplidar_a2m12_teaching_driver a2m12.launch.py
  ros2 launch rplidar_a2m12_teaching_driver a2m12.launch.py serial_port:=/dev/ttyUSB1
  ros2 launch rplidar_a2m12_teaching_driver a2m12.launch.py dummy_mode:=true
  ros2 launch rplidar_a2m12_teaching_driver a2m12.launch.py rviz:=false   # headless / SSH
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, EmitEvent, LogInfo, TimerAction
from launch.actions import RegisterEventHandler
from launch.event_handlers import OnProcessStart
from launch.events import matches_action
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import LifecycleNode, Node
from launch_ros.event_handlers import OnStateTransition
from launch_ros.events.lifecycle import ChangeState
from launch_ros.parameter_descriptions import ParameterValue
from lifecycle_msgs.msg import Transition


def generate_launch_description() -> LaunchDescription:
    share_dir = get_package_share_directory("rplidar_a2m12_teaching_driver")

    args = [
        DeclareLaunchArgument(
            "params_file",
            default_value=os.path.join(share_dir, "param", "a2m12.yaml"),
            description="Parameter file."),
        DeclareLaunchArgument(
            "serial_port", default_value="/dev/ttyUSB0",
            description="Serial device of the A2M12."),
        DeclareLaunchArgument(
            "dummy_mode", default_value="false",
            description="true = synthetic data, no hardware needed."),
        DeclareLaunchArgument(
            "publish_tf", default_value="false",
            description="true = publish a zero base_link -> laser_a2m12 TF."),
        DeclareLaunchArgument(
            "rviz", default_value="true",
            description="true = also open RViz with rviz/a2m12.rviz. "
                        "Use false on a robot without a display."),
        DeclareLaunchArgument(
            "rviz_config",
            default_value=os.path.join(share_dir, "rviz", "a2m12.rviz"),
            description="RViz config file."),
    ]

    driver_node = LifecycleNode(
        package="rplidar_a2m12_teaching_driver",
        executable="rplidar_node",
        name="rplidar_node",
        namespace="",
        output="screen",
        parameters=[
            LaunchConfiguration("params_file"),
            {
                "serial_port": LaunchConfiguration("serial_port"),
                "dummy_mode": ParameterValue(
                    LaunchConfiguration("dummy_mode"), value_type=bool),
                "publish_tf": ParameterValue(
                    LaunchConfiguration("publish_tf"), value_type=bool),
            },
        ],
    )

    # Step 1: once the process is up, wait a beat, then request CONFIGURE.
    #
    # The delay is load-bearing. launch_ros creates its change_state client at
    # process start, i.e. before the node advertises the service, and the
    # request then sits waiting on discovery while the node stays in
    # 'unconfigured' (reproduced repeatedly, also with the upstream C1M1
    # package). Node startup costs ~0.3 s here, so 3 s is comfortably enough.
    configure_event = RegisterEventHandler(
        OnProcessStart(
            target_action=driver_node,
            on_start=[
                LogInfo(msg="[Lifecycle] Process started, requesting CONFIGURE in 3 s..."),
                TimerAction(period=3.0, actions=[
                    EmitEvent(event=ChangeState(
                        lifecycle_node_matcher=matches_action(driver_node),
                        transition_id=Transition.TRANSITION_CONFIGURE)),
                ]),
            ],
        )
    )

    # Step 2: after the FIRST configure (configuring -> inactive), request
    # ACTIVATE, exactly once. Later transitions belong to the user or to
    # examples/scan_watchdog.py:
    #   - start_state: a manual deactivate (active -> inactive) is not undone.
    #   - handle_once: a manual cleanup -> configure is not auto-activated,
    #     which would otherwise race with whoever is driving the lifecycle.
    activate_event = RegisterEventHandler(
        OnStateTransition(
            target_lifecycle_node=driver_node,
            start_state="configuring",
            goal_state="inactive",
            handle_once=True,
            entities=[
                LogInfo(msg="[Lifecycle] Transitioning to ACTIVE..."),
                EmitEvent(event=ChangeState(
                    lifecycle_node_matcher=matches_action(driver_node),
                    transition_id=Transition.TRANSITION_ACTIVATE)),
            ],
        )
    )

    # RViz is an ordinary node, independent of the driver lifecycle: it just
    # subscribes to /scan. Fixed Frame 'laser_a2m12' needs no TF.
    rviz_node = Node(
        package="rviz2",
        executable="rviz2",
        name="rviz2",
        output="log",
        arguments=["-d", LaunchConfiguration("rviz_config")],
        condition=IfCondition(LaunchConfiguration("rviz")),
    )

    return LaunchDescription(
        args + [driver_node, configure_event, activate_event, rviz_node])
