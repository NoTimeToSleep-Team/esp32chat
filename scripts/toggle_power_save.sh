#!/bin/bash
# Toggle RPi power-save settings over SSH.
# Requires passwordless sudo on the RPi (recommended) or LC_SUDO_PASSWORD in the environment.
RPI="${RPI_HOST:-gamecat@10.42.0.2}"
SUDO="sudo -n"
if [ -n "$LC_SUDO_PASSWORD" ]; then SUDO="echo '$LC_SUDO_PASSWORD' | sudo -S"; fi
case "${1:-status}" in
  on)  ssh "$RPI" "$SUDO sed -i 's/arm_freq=.*/arm_freq=1500/' /boot/firmware/config.txt && $SUDO sed -i '\$s/\$/ maxcpus=2/' /boot/firmware/cmdline.txt && $SUDO reboot" ;;
  off) ssh "$RPI" "$SUDO sed -i '/arm_freq=/d' /boot/firmware/config.txt && $SUDO sed -i 's/ maxcpus=2//' /boot/firmware/cmdline.txt && $SUDO reboot" ;;
  *)   ssh "$RPI" "cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq 2>/dev/null; grep arm_freq /boot/firmware/config.txt 2>/dev/null; grep maxcpus /boot/firmware/cmdline.txt 2>/dev/null; uptime" ;;
esac
