#!/bin/sh
# ascOS PID 1 (busybox init). There is NO getty, NO login, NO sshd, NO shell
# escape. After mounting everything and starting the engine, this execs
# as_shell.py directly on the console. If the AI dies, the machine reboots.

PATH=/usr/bin:/bin:/usr/sbin:/sbin
export PATH

mount -t proc proc /proc
mount -t sysfs sysfs /sys
mount -t devtmpfs devtmpfs /dev 2>/dev/null || true
mkdir -p /dev/pts
mount -t devpts devpts /dev/pts 2>/dev/null || true

echo "ascOS booting..."
echo "  mounting data partition..."
mkdir -p /data
mount -t ext4 /dev/sda2 /data 2>/dev/null || \
mount -t ext4 LABEL=ascdata /data 2>/dev/null || {
    echo "  WARNING: no data partition found; running throwaway (tmpfs)."
    mount -t tmpfs tmpfs /data
}

# First boot: seed the writable data partition from the read-only seed.
if [ ! -e /data/.seeded ]; then
    echo "  first boot — seeding data partition..."
    cp -a /opt/as-os/seed/. /data/
    touch /data/.seeded
fi

# The jail's writable parts (home, packages, config) live on the data
# partition; bin/share/apps stay read-only in the squashfs.
for d in home packages etc; do
    mkdir -p /data/jail/$d /opt/as-os/jail/$d
    mount --bind /data/jail/$d /opt/as-os/jail/$d
done

echo "  starting the engine..."
export LD_LIBRARY_PATH=/opt/as-os/tools/llama.cpp/llama-b10333
MODEL=$(cat /data/etc/as-os/model 2>/dev/null || echo "LFM2.5-8B-A1B-Q4_K_M.gguf")
PORT=8080
SLOTS=4
THREADS=4
MASK=0,2,4,6
taskset -c "$MASK" /opt/as-os/tools/llama.cpp/llama-b10333/llama-server \
    -m "/opt/as-os/models/$MODEL" \
    -c $((8192 * SLOTS)) \
    -t "$THREADS" \
    --parallel "$SLOTS" \
    -ctk q8_0 -ctv q8_0 \
    --cache-prompt --cache-reuse 64 \
    -rea off \
    --host 127.0.0.1 \
    --port "$PORT" \
    --temp 0.2 \
    --top-k 80 \
    --repeat-penalty 1.05 \
    --no-webui \
    --log-disable \
    > /data/engine.log 2>&1 &

ENGINE_PID=$!
echo "  engine pid $ENGINE_PID (model $MODEL)"

# Wait for the engine to answer on the health endpoint (python, no curl).
echo "  waiting for engine..."
i=0
until [ "$i" -ge 180 ]; do
    if /usr/bin/python3 -c "import requests,sys; sys.exit(0 if requests.get('http://127.0.0.1:$PORT/health',timeout=2).ok else 1)" 2>/dev/null; then
        break
    fi
    i=$((i + 1))
    sleep 1
done
[ "$i" -lt 180 ] || echo "  WARNING: engine did not report healthy; proceeding anyway"

echo ""
echo "  hello. you are not in linux anymore. you are in ascOS."
echo ""

# The soul of the machine. There is no fallback.
cd /opt/as-os
exec /usr/bin/python3 shell/as_shell.py
