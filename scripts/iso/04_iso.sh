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
# the isolinux bootloader itself — xorriso boots /isolinux/isolinux.bin from
# inside the image, so it must be staged (plain KERNEL/INITRD cfg: no .c32 UI)
for f in isolinux.bin ldlinux.c32; do
    if [ -e "/usr/lib/syslinux/bios/$f" ]; then
        cp "/usr/lib/syslinux/bios/$f" "$STAGE/isolinux/"
    else
        echo "WARNING: /usr/lib/syslinux/bios/$f missing (BIOS boot)" >&2
    fi
done
cp "$ROOT/scripts/iso/grub.cfg" "$STAGE/boot/grub/grub.cfg"
# -s, not -e: a failed grub-mkstandalone leaves an EMPTY file behind, and an
# empty grubx64.efi is rejected by xorriso as an "invalid boot image".
if [ ! -s "$STAGE/boot/grub/grubx64.efi" ]; then
    rm -f "$STAGE/boot/grub/grubx64.efi"
    # Filter against the installed grub — module availability drifts with
    # grub versions (efi_uga, for example, no longer exists in 2.16).
    GRUB_MODS=""
    for m in normal efi_gop efi_uga search_label all_video boot linux \
             echo configfile cat sleep; do
        [ -e "/usr/lib/grub/x86_64-efi/$m.mod" ] && GRUB_MODS="$GRUB_MODS $m"
    done
    grub-mkstandalone --format=x86_64-efi \
        --output="$STAGE/boot/grub/grubx64.efi" \
        --modules="$GRUB_MODS" \
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
