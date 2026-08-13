#!/usr/bin/env bash
# Flash ascOS onto a USB drive. UEFI (GPT): sda1 = EFI System Partition
# (FAT32, kernel+initramfs+GRUB), sda2 = ext4 "ascdata" (root.squashfs +
# seeded jail). Requires build/staging artifacts.
#
# Usage:  scripts/iso/flash.sh /dev/sdX
#   DESTROYS everything on /dev/sdX. Double-check the device first.
set -euo pipefail
ROOT="$(pwd)"
DEV="${1:?usage: flash.sh /dev/sdX}"
ISO="$ROOT/build/staging"
SEED="$ROOT/build/seed"

if [ "$(id -u)" -ne 0 ]; then
    echo "ERROR: root required."
    exit 1
fi

if [ ! -e "$DEV" ]; then
    echo "ERROR: $DEV does not exist."
    exit 1
fi

# ---- safety: refuse to flash the live system disk --------------------------
for mnt in / /home /boot /efi; do
    r=$(df "$mnt" 2>/dev/null | tail -1 | awk '{print $1}')
    if [ -n "$r" ] && [ "$(readlink -f "$r" 2>/dev/null)" = "$(readlink -f "$DEV" 2>/dev/null)" ]; then
        echo "ERROR: $DEV looks like the live system disk ($mnt is mounted from it). Refusing."
        exit 1
    fi
done

# ---- confirm ---------------------------------------------------------------
echo ""
echo "!!! This DESTROYS everything on $DEV !!!"
lsblk -o NAME,SIZE,MODEL "$DEV" 2>/dev/null
if [ "${FORCE:-0}" != "1" ]; then
    read -r -p "Type the device path again to confirm: " CONFIRM
    if [ "$CONFIRM" != "$DEV" ]; then
        echo "aborted."
        exit 1
    fi
else
    echo "(FORCE=1 — skipping confirmation)"
fi

# ---- artifacts present? -----------------------------------------------------
for f in "$ISO/boot/vmlinuz-linux" "$ISO/boot/initramfs.img" \
         "$ISO/boot/root.squashfs"; do
    [ -e "$f" ] || { echo "ERROR: missing $f — run: make iso"; exit 1; }
done
if [ ! -d "$SEED" ]; then
    echo "ERROR: missing build/seed — run: make seed"
    exit 1
fi

# ---- wipe + partition (GPT: ESP + ascdata) ----------------------------------
echo "==> wiping $DEV..."
umount "${DEV}"* 2>/dev/null || true
wipefs -a "$DEV" >/dev/null 2>&1 || true
printf "label: gpt\nstart=2048, size=2000000, type=uefi, name=ESP\nstart=2002048, type=linux, name=ascdata\n" \
    > /tmp/ascos-gpt.spec
sfdisk --force "$DEV" < /tmp/ascos-gpt.spec >/dev/null 2>&1
partprobe "$DEV" 2>/dev/null || true
sleep 2

ESP="${DEV}1"
DATA="${DEV}2"

# ---- format -----------------------------------------------------------------
echo "==> formatting ESP (FAT32)..."
mkfs.vfat -F32 -n ESP "$ESP" >/dev/null 2>&1
echo "==> formatting data (ext4 ascdata)..."
mkfs.ext4 -q -L ascdata "$DATA"

# ---- populate ----------------------------------------------------------------
mkdir -p /mnt/ascos-esp /mnt/ascos-data
mount "$ESP" /mnt/ascos-esp
mount "$DATA" /mnt/ascos-data

echo "==> copying boot files to ESP..."
mkdir -p /mnt/ascos-esp/boot
cp "$ISO/boot/vmlinuz-linux" /mnt/ascos-esp/boot/vmlinuz-linux
cp "$ISO/boot/initramfs.img" /mnt/ascos-esp/boot/initramfs.img

echo "==> installing GRUB (UEFI)..."
grub-install --target=x86_64-efi --efi-directory=/mnt/ascos-esp \
    --boot-directory=/mnt/ascos-esp/boot --removable "$DEV" >/dev/null 2>&1
cat > /mnt/ascos-esp/boot/grub/grub.cfg << 'EOF'
set timeout=3
set default=0
menuentry "ascOS" {
    echo "loading ascOS..."
    linux /boot/vmlinuz-linux loglevel=4 console=tty0
    initrd /boot/initramfs.img
}
EOF

echo "==> copying root.squashfs + seed to data partition (slow)..."
cp "$ISO/boot/root.squashfs" /mnt/ascos-data/root.squashfs
cp -a "$SEED/." /mnt/ascos-data/
sync

umount /mnt/ascos-esp
umount /mnt/ascos-data

echo ""
echo "==> done. $DEV is now bootable ascOS (UEFI)."
lsblk -o NAME,SIZE,FSTYPE,LABEL "$DEV"
