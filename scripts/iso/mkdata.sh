#!/usr/bin/env bash
# Create a bootable ascOS data-disk image (ext4, label ascdata) containing
# the root.squashfs. This is the "installed system" disk that stage-1 boots
# from. Usage: mkdata.sh <output.img> <root.squashfs>
set -euo pipefail

OUT="${1:?usage: mkdata.sh <out.img> <root.squashfs>}"
ROOTIMG="${2:?usage: mkdata.sh <out.img> <root.squashfs>}"
SIZE="${DATA_DISK_SIZE:-10G}"
PART_SECTORS="${DATA_DISK_SECTORS:-20000000}"

echo "==> creating data disk $OUT ($SIZE)..."
rm -f "$OUT"
truncate -s "$SIZE" "$OUT"
# non-interactive partition table via a spec file (keeps stdin free)
SPEC=$(mktemp)
printf 'label: dos\nstart=2048, size=%s, type=83, bootable\n' "$PART_SECTORS" > "$SPEC"
sfdisk --force "$OUT" < "$SPEC" > /dev/null 2>&1
rm -f "$SPEC"

losetup -f "$OUT"
DEV=$(losetup -j "$OUT" | cut -d: -f1)
PART_DEV="/dev/mapper/$(basename "$DEV")p1"
trap 'kpartx -dv "$DEV" > /dev/null 2>&1 || true; losetup -d "$DEV" 2>/dev/null || true' EXIT

kpartx -av "$DEV" > /dev/null 2>&1
mkfs.ext4 -q -L ascdata "$PART_DEV"

MNT=$(mktemp -d)
mount "$PART_DEV" "$MNT"
cp "$ROOTIMG" "$MNT/root.squashfs"
echo "copied root.squashfs: $(du -h "$MNT/root.squashfs" | cut -f1)"
umount "$MNT"
rmdir "$MNT"

echo "==> data disk ready: $OUT"
