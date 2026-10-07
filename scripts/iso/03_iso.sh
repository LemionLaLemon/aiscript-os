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

# ---------------------------------------------------------------------------
# Populate the rootfs with everything ascOS needs at runtime. This must run
# on EVERY squashfs build so code/model changes reach the image (the rootfs
# itself only gets rebuilt when pacstrap runs).
# ---------------------------------------------------------------------------
OPT="$R/opt/as-os"
echo "==> populating /opt/as-os + /sbin/init..."
rm -rf "$OPT"
mkdir -p "$OPT/tools/llama.cpp" "$OPT/models" "$OPT/packages"

# the OS init (switch_root execs /sbin/init inside the image)
install -m 755 "$ROOT/scripts/iso/init.sh" "$R/sbin/init"

# python runtime: shell + daemon + aiscript + ui
cp -a "$ROOT/daemon" "$ROOT/shell" "$ROOT/aiscript" "$ROOT/asui" "$OPT/"
cp -a "$ROOT/config.toml" "$OPT/"
[ -e "$ROOT/LICENSE" ] && cp -a "$ROOT/LICENSE" "$OPT/" || true

# runtime data: jail skeleton (home/packages/etc get bind-mounted over at
# boot), manual pages, template packages
cp -a "$ROOT/jail" "$OPT/jail"
cp -a "$ROOT/share" "$OPT/share"
cp -a "$ROOT/essential" "$OPT/essential"
cp -a "$ROOT/scripts" "$OPT/scripts"

# llama-server binary dir only (never the llama.cpp source tree)
cp -a "$ROOT/tools/llama.cpp/llama-b10333" "$OPT/tools/llama.cpp/"

# the brain — only the model ascOS ships (2.6B; hardlink to save 1.6GB)
MODEL="${ASCOS_MODEL:-LFM2.5-2.6B-Q4_K_M.gguf}"
if [ ! -e "$ROOT/models/$MODEL" ]; then
    echo "ERROR: model $ROOT/models/$MODEL not found" >&2
    exit 1
fi
cp -al "$ROOT/models/$MODEL" "$OPT/models/" 2>/dev/null || \
    cp -a "$ROOT/models/$MODEL" "$OPT/models/"

# first-boot seed — init.sh copies /opt/as-os/seed onto an empty data
# partition (the make test / vbox flow has no seed on the data disk).
if [ -d "$ROOT/build/seed" ]; then
    cp -a "$ROOT/build/seed" "$OPT/seed"
else
    echo "WARNING: build/seed missing — run 'make seed' (first boot will fail)"
fi

du -sh "$OPT"

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
