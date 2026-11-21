#!/bin/bash
# Post-recovery device health checks for the A1/A2 banner acceptance session (read-only).
set -u
export SSH_ASKPASS=/tmp/e2631-askpass-a1.sh SSH_ASKPASS_REQUIRE=force DISPLAY=:0
PW=/home/qc233/zte/e2631-device-password.txt
if [ -f "$PW" ]; then
  printf '#!/bin/bash\ncat %s\n' "$PW" > /tmp/e2631-askpass-a1.sh
  chmod 700 /tmp/e2631-askpass-a1.sh
fi
echo "== route =="
ip route get 192.168.1.1 2>&1 | head -1
echo "== ping wait (up to 90s) =="
ok=0
i=0
while [ "$i" -lt 18 ]; do
  if ping -c1 -W2 192.168.1.1 >/dev/null 2>&1; then ok=1; echo "ping ok after attempt $i"; break; fi
  i=$((i + 1))
  sleep 3
done
if [ "$ok" != 1 ]; then echo "PING_FAILED"; fi
echo "== ping stats =="
ping -c3 -W2 192.168.1.1 2>&1 | tail -2
echo "== ssh identity (retries) =="
attempt=0
while [ "$attempt" -lt 3 ]; do
  out=$(timeout 30 setsid -w ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
    -o ConnectTimeout=10 root@192.168.1.1 '
      echo VERSION=$(cat /etc/e2631-version 2>/dev/null)
      echo UPTIME=$(cut -d. -f1 /proc/uptime)
      echo MTD0=$(grep "mtd0:" /proc/mtd 2>/dev/null)
      echo PANICS=$(dmesg 2>/dev/null | grep -ci panic || true)
      echo MT7916=$(dmesg 2>/dev/null | grep -ci "MT7916" || true)
      echo WIFIBOOT=$(dmesg 2>/dev/null | grep -i "e2631-wifi-boot" | tail -1)
    ' 2>&1)
  if echo "$out" | grep -q "VERSION="; then echo "$out" | sed 's/^/  /'; break; fi
  echo "  ssh attempt $attempt failed: $(echo "$out" | tail -1)"
  attempt=$((attempt + 1))
  sleep 10
done
echo "== done =="
