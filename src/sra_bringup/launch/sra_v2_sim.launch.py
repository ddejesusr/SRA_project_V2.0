"""Launch the isolated SRA V2 simulation stack.

This launch intentionally does not start any legacy SRA nodes.
It expects the new PostgreSQL database (default: sra_v2_db) to be initialized.

Usage:
  ros2 launch sra_bringup sra_v2_sim.launch.py
  ros2 launch sra_bringup sra_v2_sim.launch.py voice:=false
  ros2 launch sra_bringup sra_v2_sim.launch.py production_sim:=false
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo, TimerAction
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    voice_arg = DeclareLaunchArgument(
        "voice",
        default_value="true",
        description="Set to false to disable microphone input",
    )
    production_sim_arg = DeclareLaunchArgument(
        "production_sim",
        default_value="true",
        description="Set to false when normalized production events come from OPC UA",
    )

    production_tracker = Node(
        package="sra_production",
        executable="production_tracker",
        name="sra_production_tracker",
        output="screen",
        emulate_tty=True,
    )

    production_sim = Node(
        package="sra_production",
        executable="production_sim",
        name="sra_production_sim",
        output="screen",
        emulate_tty=True,
        condition=IfCondition(LaunchConfiguration("production_sim")),
    )

    storage_manager = Node(
        package="sra_storage",
        executable="storage_manager",
        name="sra_storage_manager",
        output="screen",
        emulate_tty=True,
    )

    delivery_manager = Node(
        package="sra_delivery",
        executable="delivery_manager",
        name="sra_delivery_manager",
        output="screen",
        emulate_tty=True,
    )

    robot_scheduler = Node(
        package="sra_robot_scheduler",
        executable="robot_scheduler",
        name="sra_robot_scheduler",
        output="screen",
        emulate_tty=True,
    )

    robot_sim = Node(
        package="sra_robot_sim",
        executable="robot_executor_sim",
        name="sra_robot_sim",
        output="screen",
        emulate_tty=True,
    )

    agent = Node(
        package="sra_agent",
        executable="agent_node",
        name="sra_agent",
        output="screen",
        emulate_tty=True,
    )

    tts = Node(
        package="sra_tts",
        executable="tts_node",
        name="sra_tts_node",
        output="screen",
        emulate_tty=True,
    )

    voice = TimerAction(
        period=2.0,
        actions=[
            Node(
                package="sra_voice_input",
                executable="voice_input",
                name="sra_voice_input",
                output="screen",
                emulate_tty=True,
                condition=IfCondition(LaunchConfiguration("voice")),
            )
        ],
    )

    return LaunchDescription(
        [
            voice_arg,
            production_sim_arg,
            LogInfo(msg="===="),
            LogInfo(msg="  SRA V2 simulation stack starting..."),
            LogInfo(msg="  Database: SRA_V2_DB_NAME (default sra_v2_db)"),
            LogInfo(msg="===="),
            tts,
            production_tracker,
            production_sim,
            storage_manager,
            delivery_manager,
            robot_scheduler,
            robot_sim,
            agent,
            voice,
        ]
    )
