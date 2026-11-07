#!/usr/bin/env bash
# A2M12 调速验证：逐档设置 rpm，等稳定后测 /scan 频率，最后给判定。
#
# 前置：驱动已在另一个终端跑起来（rviz:=false 即可）：
#   source /opt/ros/humble/setup.bash
#   source ~/A2M12_ros/install/setup.bash
#   ros2 launch rplidar_a2m12_teaching_driver a2m12.launch.py rviz:=false
#
# 用法：
#   ros2 run rplidar_a2m12_teaching_driver rpm_sweep.sh
#   RPMS="480 900" ros2 run rplidar_a2m12_teaching_driver rpm_sweep.sh   # 只测两档
#   SETTLE=10 MEASURE=8 ros2 run rplidar_a2m12_teaching_driver rpm_sweep.sh
#
# 判读：各档 Hz 极差 < 3% -> 调速命令不生效；频率跟着 rpm/60 走 -> 支持调速。

set -uo pipefail

NODE="${NODE:-/rplidar_node}"
SETTLE="${SETTLE:-8}"     # 每档等待电机稳定的秒数
MEASURE="${MEASURE:-6}"   # 每档测量窗口的秒数
WINDOW="${WINDOW:-20}"    # ros2 topic hz 的滚动窗口（消息条数）
RPMS="${RPMS:-0 480 600 720 900}"

say() { printf '%s\n' "$*"; }
die() { printf '错误：%s\n' "$*" >&2; exit 1; }

command -v ros2 >/dev/null 2>&1 || die "找不到 ros2。先执行： source /opt/ros/humble/setup.bash"

# 节点发现给 5 次机会（每次 1 秒）：刚 launch 起来时发现可能还没传开
found=0
for _ in 1 2 3 4 5; do
  if ros2 node list --no-daemon 2>/dev/null | grep -qx "$NODE"; then found=1; break; fi
  sleep 1
done
[ "$found" = 1 ] || die "没找到节点 $NODE。
先在另一个终端把驱动拉起来（等到日志出现 'Entering RUNNING state'）：
    source /opt/ros/humble/setup.bash
    source ~/A2M12_ros/install/setup.bash
    ros2 launch rplidar_a2m12_teaching_driver a2m12.launch.py rviz:=false
如果驱动终端确实在跑还报这个：两个终端的 ROS_DOMAIN_ID 必须一致（echo \$ROS_DOMAIN_ID）。"

state="$(timeout 10 ros2 lifecycle get "$NODE" 2>/dev/null | head -1)"
case "$state" in
  active*) say "驱动状态：$state" ;;
  *) die "驱动状态不是 active（当前：${state:-未知}）。执行： ros2 lifecycle set $NODE activate" ;;
esac

ros2 topic list --no-daemon 2>/dev/null | grep -qx '/scan' || die "没有 /scan 话题，驱动没在发数据。"

get_rpm() { ros2 param get "$NODE" rpm 2>/dev/null | awk '{print $NF}'; }

measure_hz() {
  # 测量 MEASURE 秒，取最后一条滚动平均；一条都没读到就输出 NAN
  local rate
  rate="$(timeout "$MEASURE" ros2 topic hz /scan --window "$WINDOW" 2>/dev/null \
          | awk '/average rate:/{r=$3} END{if (r=="") print "NAN"; else printf "%.3f", r}')"
  printf '%s' "${rate:-NAN}"
}

restore() {
  printf '\n恢复 rpm=0（驱动按 600 下发）...'
  ros2 param set "$NODE" rpm 0 >/dev/null 2>&1 && printf ' 已恢复。\n'
}
trap restore EXIT INT TERM

say "=================================================================="
say " A2M12 调速验证  节点=$NODE  稳定=${SETTLE}s  测量=${MEASURE}s  窗口=${WINDOW} 条"
say "=================================================================="
printf '%-8s %-10s %-10s %-14s %s\n' '设定rpm' '参数读回' '实测Hz' '理论Hz' '相对首档'
printf '%-8s %-10s %-10s %-14s %s\n' '-------' '--------' '------' '------' '--------'
baseline=''
data=''
for r in $RPMS; do
  if ! ros2 param set "$NODE" rpm "$r" >/dev/null 2>&1; then
    say "rpm=$r 被拒绝（越界？），跳过"
    continue
  fi
  printf '  → 设 rpm=%s，等 %ss 稳定...\n' "$r" "$SETTLE"
  sleep "$SETTLE"
  rb="$(get_rpm)"
  hz="$(measure_hz)"
  if [ "$r" = "0" ]; then expect='10.00*'; else expect="$(awk -v v="$r" 'BEGIN{printf "%.2f", v/60}')"; fi
  if [ -z "$baseline" ] && [ "$hz" != 'NAN' ]; then baseline="$hz"; fi
  rel='—'
  if [ -n "$baseline" ] && [ "$hz" != 'NAN' ] && awk -v b="$baseline" 'BEGIN{exit !(b>0)}'; then
    rel="$(awk -v a="$hz" -v b="$baseline" 'BEGIN{printf "%+.1f%%", (a/b-1)*100}')"
  fi
  printf '  %-6s %-8s %-8s %-12s %s\n' "$r" "$rb" "$hz" "$expect" "$rel"
  data="${data}${hz}"$'\n'
done

say ''
say '* rpm=0 时驱动按 600 rpm 下发，理论 10.00 Hz。'
say ''
printf '%s' "$data" | awk '
  /^NAN$/ {next}
  {n++; if (n==1) {min=$1; max=$1} if ($1<min) min=$1; if ($1>max) max=$1}
  END {
    if (n < 2) { print "判定：有效读数少于 2 个，请确认 /scan 稳定后重跑。"; exit }
    if (min > 30) { printf "提示：读数约 %.0f Hz，说明当前是 dummy_mode（假数据固定频率），这个实验必须接真雷达做。\n", min; exit }
    spread = (max-min)/min*100
    printf "有效读数 %d 个：最小 %.3f Hz，最大 %.3f Hz，极差 %.1f%%\n", n, min, max, spread
    if (spread < 3) print "判定：各档频率基本不变 → 调速命令不生效（与 C1M1 同病）"
    else            print "判定：频率随 rpm 改变 → A2M12 支持调速"
  }'
say ''
say '把上面这一整段贴回去，用来填 doc/PARAM_GUIDE_A2M12.md 第 6 节的记录表。'
