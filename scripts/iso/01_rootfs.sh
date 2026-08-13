#!/usr/bin/env bash
# Build the ascOS rootfs: pacstrap a minimal Arch base, then strip it down
# to a bare AI-only system. Requires root.
set -euo pipefail
cd "$(dirname "$0")/.."

ROOTFS="build/rootfs"
SUDO=""

if [ "$(id -u)" -ne 0 ]; then
    echo "ERROR: root required (pacstrap/arch-chroot)."
    exit 1
fi

rm -rf "$ROOTFS"
mkdir -p "$ROOTFS"

# ---- 1. pacstrap minimal base ------------------------------------------------
# Only what as-os + llama-server need at runtime. gcc (the compiler) is
# deliberately NOT installed — the AI must never be able to invoke one.
# gcc-libs provides libstdc++/libgomp (runtime libs only, no compiler).
echo "==> pacstrap base..."
pacstrap -c "$ROOTFS" \
    linux \
    busybox \
    python \
    openssl \
    zlib \
    util-linux \
    bash \
    coreutils \
    sed \
    grep \
    procps-ng \
    gcc-libs \
    brotli \
    zstd \
    file \
    2>&1 | tail -5

echo "==> base rootfs ready"
