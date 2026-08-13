#!/usr/bin/env bash
# Final ISO assembly: xorriso hybrid image (BIOS+UEFI bootable).
# The data partition image is dropped next to the ISO for the installer.
set -euo pipefail
ROOT="$(pwd)"
STAGE="$ROOT/build/staging"
OUT="$ROOT/build/ascOS.iso"

echo "==> assembling $OUT ..."
xorriso -as mkisofs \
    -iso-level 3 \
    -full-iso9660-filenames \
    -volid "ascOS" \
    -eltorito-boot isolinux/isolinux.bin \
    -eltorito-catalog isolinux/boot.cat \
    -no-emul-boot -boot-load-size 4 -boot-info-table \
    -eltorito-alt-boot -e boot/grub/grubx64.efi -no-emul-boot \
    -isohybrid-mbr /usr/lib/syslinux/bios/mbr.bin \
    -isohybrid-gpt-basdat \
    -o "$OUT" \
    "$STAGE" 2>&1 | tail -5

ls -lh "$OUT"
echo "==> done: $OUT"
