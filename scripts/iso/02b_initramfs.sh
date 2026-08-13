#!/usr/bin/env bash
# Build the ascOS initramfs (stage-1): busybox + init script + squashfs module.
set -euo pipefail
ROOT="$(pwd)"
INITRAMFS="$ROOT/build/initramfs"
R="$ROOT/build/rootfs"

echo "==> staging initramfs files..."
rm -rf "$INITRAMFS"
mkdir -p "$INITRAMFS"/{bin,dev,proc,sys,mnt,lib/modules}
cp /usr/bin/busybox "$INITRAMFS/bin/busybox"
cp "$ROOT/scripts/iso/initramfs-init.sh" "$INITRAMFS/init"
chmod 755 "$INITRAMFS/init"
ln -sf busybox "$INITRAMFS/bin/sh"
# busybox applets the stage-1 script needs
for applet in mount umount insmod sleep echo cat grep readlink switch_root mkdir; do
    ln -sf busybox "$INITRAMFS/bin/$applet"
done

echo "==> decompressing kernel modules into initramfs..."
for mod in squashfs loop; do
    M=$(echo "$R"/usr/lib/modules/*/kernel/*/*/"$mod".ko.zst 2>/dev/null | tr ' ' '\n' | head -1)
    [ -e "$M" ] || M=$(find "$R"/usr/lib/modules -name "$mod.ko.zst" 2>/dev/null | head -1)
    if [ -e "$M" ]; then
        zstd -d -f -q "$M" -o "$INITRAMFS/lib/modules/$mod.ko"
        echo "$mod.ko: $(du -h "$INITRAMFS/lib/modules/$mod.ko" | cut -f1)"
    else
        echo "WARNING: $mod module not found"
    fi
done

echo "==> done staging initramfs"
