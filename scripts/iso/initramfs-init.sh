#!/bin/busybox sh
# ascOS stage-1 init (initramfs). Find the data partition, mount it, then
# switch_root into the squashfs root image it carries (root.squashfs).
# Everything else happens in the real /sbin/init.

export PATH=/bin:/usr/bin:/sbin

mount -t proc proc /proc
mount -t sysfs sysfs /sys
mount -t devtmpfs devtmpfs /dev 2>/dev/null || true
mkdir -p /dev/pts /mnt /mntroot
mount -t devpts devpts /dev/pts 2>/dev/null || true

echo "ascOS stage1: loading root filesystem modules..."
for m in /lib/modules/loop.ko /lib/modules/squashfs.ko /lib/squashfs.ko; do
    [ -e "$m" ] && insmod "$m" 2>/dev/null
done
# make sure loop devices exist
mknod /dev/loop0 b 7 0 2>/dev/null || true
mknod /dev/loop-control c 10 237 2>/dev/null || true

echo "ascOS stage1: locating data partition..."
DATA_SRC=""
for dev in /dev/vda1 /dev/vda2 /dev/sda1 /dev/sda2 /dev/sdb1 /dev/vdb1 /dev/sr0; do
    if [ -b "$dev" ]; then
        if mount -t ext4 "$dev" /mnt 2>/dev/null; then
            DATA_SRC="$dev"
            break
        fi
    fi
done

if [ -z "$DATA_SRC" ]; then
    echo "ascOS: cannot find data partition. panic (rebooting in 10s)"
    sleep 10
    echo b > /proc/sysrq-trigger
    exit 1
fi
echo "ascOS stage1: data = $DATA_SRC"

if [ -e /mnt/root.squashfs ]; then
    echo "ascOS stage1: mounting root image..."
    # attach the squashfs file to a loop device explicitly, then mount
    losetup /dev/loop0 /mnt/root.squashfs 2>/dev/null || \
        losetup -f /mnt/root.squashfs 2>/dev/null || true
    mount -t squashfs -o ro /dev/loop0 /mntroot || \
        mount -t squashfs -o ro,loop /mnt/root.squashfs /mntroot
    # carry /proc /sys /dev into the new root so stage2 can use them
    mkdir -p /mntroot/proc /mntroot/sys /mntroot/dev
    mount --move /proc /mntroot/proc 2>/dev/null || true
    mount --move /sys /mntroot/sys 2>/dev/null || true
    mount --move /dev /mntroot/dev 2>/dev/null || true
    exec switch_root /mntroot /sbin/init
fi

echo "ascOS stage1: no root.squashfs on data partition. panic (rebooting in 10s)"
sleep 10
echo b > /proc/sysrq-trigger
exit 1
