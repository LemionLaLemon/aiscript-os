#!/usr/bin/env bash
# Final ISO assembly: xorriso hybrid image (BIOS isolinux + UEFI grub).
# The data partition image is dropped next to the ISO for the installer.
set -euo pipefail
ROOT="$(pwd)"
STAGE="$ROOT/build/staging"
OUT="$ROOT/build/ascOS.iso"

echo "==> staging boot configs..."
mkdir -p "$STAGE/isolinux" "$STAGE/boot/grub"
cp "$ROOT/scripts/iso/isolinux.cfg" "$STAGE/isolinux/isolinux.cfg"
cp "$ROOT/scripts/iso/grub.cfg" "$STAGE/boot/grub/grub.cfg"
if [ ! -e "$STAGE/boot/grub/grubx64.efi" ]; then
    grub-mkstandalone --format=x86_64-efi \
        --output="$STAGE/boot/grub/grubx64.efi" \
        --modules="normal efi_gop efi_uga search_label all_video boot linux echo configfile cat sleep" \
        /boot/grub/grub.cfg="$STAGE/boot/grub/grub.cfg" 2>&1 | tail -1
fi

echo "==> assembling $OUT ..."
xorriso -as mkisofs \
    -iso-level 3 \
    -full-iso9660-filenames \
    -volid ascOS \
    -eltorito-boot isolinux/isolinux.bin \
    -eltorito-catalog isolinux/boot.cat \
    -no-emul-boot -boot-load-size 4 -boot-info-table \
    -eltorito-alt-boot -e boot/grub/grubx64.efi -no-emul-boot \
    -isohybrid-mbr /usr/lib/syslinux/bios/mbr.bin \
    -isohybrid-gpt-basdat \
    -o "$OUT" \
    "$STAGE" 2>&1 | tail -3

ls -lh "$OUT"
echo "==> done: $OUT"
