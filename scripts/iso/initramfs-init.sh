#!/bin/busybox sh
# ascOS stage-1 init (initramfs). Minimal: get the squashfs root mounted and
# switch_root into it. Everything else happens in the real /sbin/init.

export PATH=/bin:/usr/bin:/sbin

mount -t proc proc /proc
mount -t sysfs sysfs /sys
mount -t devtmpfs devtmpfs /dev 2>/dev/null || true
mkdir -p /dev/pts
mount -t devpts devpts /dev/pts 2>/dev/null || true

echo "ascOS stage1: locating root image..."
ROOT_SRC=""
for dev in /dev/sr0 /dev/sr1 /dev/sda1 /dev/sdb1 /dev/vda1 /dev/vdb1; do
    if [ -b "$dev" ]; then
        if mount -t squashfs -o ro "$dev" /mnt 2>/dev/null; then
            ROOT_SRC="$dev"
            break
        fi
    fi
done

if [ -z "$ROOT_SRC" ]; then
    echo "ascOS: cannot find root squashfs image. panic (rebooting in 10s)"
    sleep 10
    echo b > /proc/sysrq-trigger
fi

echo "ascOS stage1: root = $ROOT_SRC"
mount --move /proc /mnt/proc 2>/dev/null || true
mount --move /sys /mnt/sys 2>/dev/null || true
mount --move /dev /mnt/dev 2>/dev/null || true

exec switch_root /mnt /sbin/init
