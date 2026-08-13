#!/bin/sh
# ascOS PID 1 (busybox init). There is NO getty, NO login, NO sshd, NO shell
# escape. After mounting everything and starting the engine, this execs
# as_shell.py directly on the console. If the AI dies, the machine reboots.

PATH=/usr/bin:/bin:/usr/sbin:/sbin
export PATH

# Boot log: echoed to the console AND appended to /data/boot.log so it can
# be read from the host by mounting the data disk.
log() {
    echo "ascOS: $*"
    [ -w /data/boot.log ] && echo "ascOS: $*" >> /data/boot.log 2>/dev/null || true
}

log "stage2: mounting filesystems"
mount -t proc proc /proc 2>/dev/null || true
mount -t sysfs sysfs /sys 2>/dev/null || true
mount -t devtmpfs devtmpfs /dev 2>/dev/null || true
mkdir -p /dev/pts
mount -t devpts devpts /dev/pts 2>/dev/null || true
# writable scratch dirs (the root squashfs is read-only)
mount -t tmpfs tmpfs /tmp 2>/dev/null || true
mkdir -p /run
mount -t tmpfs tmpfs /run 2>/dev/null || true

log "mounting data partition"
mkdir -p /data
mount -t ext4 /dev/sda2 /data 2>/dev/null || \
mount -t ext4 LABEL=ascdata /data 2>/dev/null || {
    log "WARNING: no data partition found; running throwaway (tmpfs)."
    mount -t tmpfs tmpfs /data
}
echo "--- ascOS boot log ---" >> /data/boot.log 2>/dev/null || true

# First boot: seed the writable data partition from the read-only seed.
if [ ! -e /data/.seeded ]; then
    log "first boot — seeding data partition..."
    cp -a /opt/as-os/seed/. /data/
    touch /data/.seeded
fi

# Model selection: first boot asks; every boot reads the jail config.
MODEL_FILE=/data/jail/etc/as-os/model
if [ ! -e "$MODEL_FILE" ]; then
    echo ""
    echo "  which brain do you want?"
    echo "    1) 8B  (the full ascOS experience — needs ~8GB RAM)"
    echo "    2) 1.2B  (lightweight — runs on ~2GB RAM)"
    echo -n "  choice [1]: "
    read MODEL_CHOICE
    mkdir -p "$(dirname "$MODEL_FILE")"
    case "$MODEL_CHOICE" in
        2) echo "LFM2.5-1.2B-Instruct-Q4_K_M.gguf" > "$MODEL_FILE" ;;
        *) echo "LFM2.5-8B-A1B-Q4_K_M.gguf" > "$MODEL_FILE" ;;
    esac
fi

# The jail's writable parts (home, packages, config) live on the data
# partition; bin/share/apps stay read-only in the squashfs.
for d in home packages etc; do
    mkdir -p /data/jail/$d /opt/as-os/jail/$d
    mount --bind /data/jail/$d /opt/as-os/jail/$d
done

log "starting the engine"
export LD_LIBRARY_PATH=/opt/as-os/tools/llama.cpp/llama-b10333
MODEL=$(cat "$MODEL_FILE" 2>/dev/null || echo "LFM2.5-8B-A1B-Q4_K_M.gguf")
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
log "engine pid $ENGINE_PID (model $MODEL)"
echo "$ENGINE_PID" > /tmp/as-os-engine.pid

# Wait for the engine to answer on the health endpoint (python, no curl).
# Show a progress spinner so the user knows the model is loading.
log "waiting for engine (model load can take a while)..."
i=0
while [ "$i" -lt 300 ]; do
    if /usr/bin/python3 -c "import requests,sys; sys.exit(0 if requests.get('http://127.0.0.1:$PORT/health',timeout=2).ok else 1)" 2>/dev/null; then
        break
    fi
    i=$((i + 1))
    if [ $((i % 30)) -eq 0 ]; then
        log "  ...still loading model ($((i))s)"
    fi
    sleep 1
done
[ "$i" -lt 300 ] && log "engine healthy after ${i}s" || log "WARNING: engine not healthy after ${i}s; proceeding"

log "hello. you are not in linux anymore. you are in ascOS."

# The soul of the machine. There is no fallback.
cd /opt/as-os
exec /usr/bin/python3 shell/as_shell.py
