#!/usr/bin/env bash
# Assemble the ascOS bootable ISO:
#   initramfs (stage-1 busybox) + squashfs root + GRUB BIOS/UEFI + data part.
set -euo pipefail
ROOT="$(pwd)"
cd "$ROOT"

R="$ROOT/build/rootfs"
INITRAMFS="$ROOT/build/initramfs"
ISO="$ROOT/build/iso"
STAGE="$ROOT/build/staging"

echo "==> staging directories..."
rm -rf "$STAGE"
mkdir -p "$STAGE"/{boot/grub,isolinux,data}

echo "==> building squashfs root..."
rm -f "$STAGE/boot/root.squashfs"
mksquashfs "$R" "$STAGE/boot/root.squashfs" \
    -comp xz -noappend 2>&1 | tail -2

echo "==> building initramfs (cpio)..."
rm -f "$STAGE/boot/initramfs.img"
( cd "$INITRAMFS" && find . | cpio -o -H newc 2>/dev/null > "$STAGE/boot/initramfs.img" )
echo "initramfs size: $(du -h "$STAGE/boot/initramfs.img" | cut -f1)"

echo "==> building data partition image (ext4, label ascdata)..."
rm -f "$STAGE/data/data.img"
truncate -s 2G "$STAGE/data/data.img"
mkfs.ext4 -q -L ascdata -F "$STAGE/data/data.img"

echo "==> copying kernel..."
cp "$R/usr/lib/modules"/*/vmlinuz "$STAGE/boot/vmlinuz-linux"
echo "kernel: $STAGE/boot/vmlinuz-linux"

echo "==> done staging. ISO assembly is next."
