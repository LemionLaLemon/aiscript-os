# ascOS ISO buildchain
#
#   make              build build/ascOS.iso (default target)
#   make iso          same as above
#   make rootfs       only build the stripped rootfs (fast iteration)
#   make squashfs     rebuild build/staging/boot/root.squashfs from rootfs
#   make initramfs    rebuild the stage-1 initramfs
#   make data-disk    create a bootable data disk image (root.squashfs inside)
#   make test         boot the ISO + data disk in QEMU (software emulation:
#                     slow model load — see make vbox for a fast VM)
#   make vbox         convert the data disk to a .vdi for VirtualBox and
#                     print setup instructions
#   make clean        remove build/ artifacts
#
# Everything needs root (pacstrap/arch-chroot/mksquashfs on mounted loop).
# Run as `make` and it will use `sudo` (prompts for your password), or set
# SUDO if your environment differs.

SUDO ?= sudo
PY ?= python3

.DEFAULT_GOAL := iso
.PHONY: iso rootfs strip squashfs initramfs data-disk test vbox clean

iso: build/ascOS.iso

# ---- full pipeline ----------------------------------------------------------

build/ascOS.iso: build/staging/boot/root.squashfs \
                 build/staging/boot/initramfs.img \
                 build/staging/boot/vmlinuz-linux \
                 build/staging/data/data.img
	$(SUDO) bash scripts/iso/04_iso.sh

rootfs: build/rootfs

build/rootfs:
	$(SUDO) bash scripts/iso/01_rootfs.sh
	$(SUDO) bash scripts/iso/02_strip.sh

# ---- squashfs ----------------------------------------------------------------

squashfs: build/staging/boot/root.squashfs

build/staging/boot/root.squashfs: build/rootfs scripts/iso/03_iso.sh
	mkdir -p build/staging
	$(SUDO) bash scripts/iso/03_iso.sh

# ---- initramfs ---------------------------------------------------------------

initramfs: build/staging/boot/initramfs.img

build/staging/boot/initramfs.img: scripts/iso/02b_initramfs.sh \
                                  scripts/iso/initramfs-init.sh
	$(SUDO) bash scripts/iso/02b_initramfs.sh
	cd build/initramfs && find . | cpio -o -H newc 2>/dev/null | $(SUDO) tee build/staging/boot/initramfs.img > /dev/null

# ---- kernel ------------------------------------------------------------------

build/staging/boot/vmlinuz-linux: build/rootfs
	mkdir -p build/staging/boot
	cp build/rootfs/usr/lib/modules/*/vmlinuz build/staging/boot/vmlinuz-linux

# ---- data partition -----------------------------------------------------------

data-disk: build/data-disk.img

build/data-disk.img: build/staging/boot/root.squashfs
	$(SUDO) bash scripts/iso/mkdata.sh $@ build/staging/boot/root.squashfs

# ---- test ---------------------------------------------------------------------

test: build/ascOS.iso build/data-disk.img
	qemu-system-x86_64 -cpu max -m 3072 -smp 4 \
		-cdrom build/ascOS.iso \
		-drive file=build/data-disk.img,format=raw,if=virtio \
		-boot order=d -nographic -no-reboot

# ---- virtualbox ----------------------------------------------------------------

vbox: build/data-disk.img
	@echo "==> converting data disk to VirtualBox VDI..."
	VBoxManage convertdd build/data-disk.img build/ascOS-data.vdi 2>/dev/null || \
		qemu-img convert -f raw -O vdi build/data-disk.img build/ascOS-data.vdi
	@echo ""
	@echo "==> VirtualBox setup ============================================"
	@echo "  1. New VM: Linux/Arch, 64-bit, >=6 GB RAM (8B) or 2 GB (1.2B)"
	@echo "  2. Storage:"
	@echo "     - Optical drive  : build/ascOS.iso"
	@echo "     - SATA controller: build/ascOS-data.vdi"
	@echo "  3. System > Processor: enable VT-x/AMD-V (already on by default)"
	@echo "  4. Boot order: Optical first"
	@echo "  5. Boot; pick 8B or 1.2B at the model prompt"
	@echo "  NOTE: the data disk must stay attached — it holds the root"
	@echo "  squashfs AND your persistent user data."
	@echo "================================================================"

# ---- clean --------------------------------------------------------------------

clean:
	rm -rf build/staging build/ascOS.iso build/data-disk.img build/initramfs
