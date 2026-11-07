#!/usr/bin/env python3
"""Measure real A2M12 rotation: stamp-based Hz + points per frame."""
import sys, math, statistics
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import LaserScan

DUR = float(sys.argv[1]) if len(sys.argv) > 1 else 6.0

class Probe(Node):
    def __init__(self):
        super().__init__('scan_probe')
        self.stamps, self.n, self.valid, self.inc = [], [], [], []
        self.create_subscription(LaserScan, '/scan', self.cb, qos_profile_sensor_data)
    def cb(self, m):
        self.stamps.append(m.header.stamp.sec + m.header.stamp.nanosec * 1e-9)
        self.n.append(len(m.ranges))
        self.valid.append(sum(1 for r in m.ranges if math.isfinite(r)))
        self.inc.append(m.angle_increment)

rclpy.init()
p = Probe()
end = p.get_clock().now().nanoseconds + DUR * 1e9
while p.get_clock().now().nanoseconds < end:
    rclpy.spin_once(p, timeout_sec=0.1)
s = p.stamps[2:]  # drop first frames
if len(s) < 3:
    print('NO_DATA'); sys.exit(1)
dt = [b - a for a, b in zip(s, s[1:])]
hz = 1.0 / statistics.mean(dt)
pts = statistics.mean(p.n[2:])
print(f'frames={len(s)} hz={hz:.3f} rpm_est={hz*60:.0f} '
      f'ranges/frame={pts:.1f} finite/frame={statistics.mean(p.valid[2:]):.1f} '
      f'2pi/inc={2*math.pi/statistics.mean(p.inc[2:]):.1f} pts_per_s={pts*hz:.0f}')
rclpy.shutdown()
