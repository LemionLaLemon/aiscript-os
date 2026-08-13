#!/bin/busybox sh
# ascOS stage-1 init (initramfs). Find the data partition, mount it, then
# switch_root into the squashfs root image it carries (root.squashfs).
# Everything else happens in the real /sbin/init.

export PATH=/bin:/usr/bin:/sbin

# Boot log — mirrored to the data partition once it's found, so it survives
# and can be read from the host by mounting the data disk.
BOOTLOG=/dev/console
say() { echo "ascOS: $*"; }

mount -t proc proc /proc
mount -t sysfs sysfs /sys
mount -t devtmpfs devtmpfs /dev 2>/dev/null || true
mkdir -p /dev/pts /mnt /mntroot
mount -t devpts devpts /dev/pts 2>/dev/null || true

say "stage1: loading modules..."
for m in /lib/modules/loop.ko /lib/modules/squashfs.ko \
         /lib/modules/usb-storage.ko /lib/modules/uas.ko; do
    if [ -e "$m" ]; then
        say "  insmod $(basename "$m")"
        insmod "$m" 2>/dev/null || say "  (insmod $(basename "$m") failed)"
    fi
done
# make sure loop devices exist
mknod /dev/loop0 b 7 0 2>/dev/null || true
mknod /dev/loop-control c 10 237 2>/dev/null || true

say "stage1: locating data partition..."
DATA_SRC=""

# USB/SCSI devices enumerate asynchronously — wait for them to appear.
# Also trigger a rescan of SCSI so late-plugged disks show up.
for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
    for h in /sys/class/scsi_host/host*/scan; do
        [ -e "$h" ] && echo "- - -" > "$h" 2>/dev/null
    done
    # scan every block partition for an ext4 filesystem holding root.squashfs
    for part in /sys/class/block/*[0-9]; do
        dev="/dev/$(basename "$part")"
        [ -b "$dev" ] || continue
        # skip the boot ESP (vfat) and swap — we want ext4 with root.squashfs
        if mount -t ext4 "$dev" /mnt 2>/dev/null; then
            if [ -e /mnt/root.squashfs ]; then
                DATA_SRC="$dev"
                say "stage1: found data partition: $dev"
                break 2
            fi
            umount /mnt 2>/dev/null || true
        fi
    done
    [ -n "$DATA_SRC" ] && break
    sleep 1
done

if [ -z "$DATA_SRC" ]; then
    say "FATAL: cannot find data partition (ext4 with root.squashfs)."
    say "Block devices present:"
    ls /dev/sd* /dev/vd* /dev/sr* 2>/dev/null || say "  (none)"
    say "Is the data disk attached?"
    sleep 10
    echo b > /proc/sysrq-trigger
    exit 1
fi

# persist boot log on the data partition
if [ -w /mnt ]; then
    echo "--- ascOS boot log ---" >> /mnt/boot.log 2>/dev/null || true
fi

if [ -e /mnt/root.squashfs ]; then
    say "stage1: mounting root image..."
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
    say "stage1: switching root"
    exec switch_root /mntroot /sbin/init
fi

say "FATAL: no root.squashfs on data partition."
sleep 10
echo b > /proc/sysrq-trigger
exit 1
