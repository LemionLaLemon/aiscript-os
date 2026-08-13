# ascOS Bootable ISO — AI-only Linux image

Goal: a bootable USB/DVD ISO that boots straight into `as#` with NO way to
reach a normal Linux shell. The ONLY interface is kernel-2. Branded ascOS,
ships 8B default + 1.2B option (OOBE-selected), persists user data on a
writable partition. Rebuildable via `make iso`.

## How "AI-only" is guaranteed (build, not policy)

We build an image with no escape hatches:
- PID 1 = custom init that mounts squashfs root + data partition, starts
  llama-server, then execs as_shell.py on the console.
- No getty/login, no extra tty terminals, no sshd, no su/sudo, no pacman.
- Jail busybox is the only "shell", chrooted via the interpreter layer.
- Close the shell-layer `run` gap: make it go through the chrooted jail so
  no command ever runs un-chrooted on the host.
- Strip gcc/compilers from the rootfs so a compiler cannot be invoked.

## Build path

Fastest viable: minimal pacstrap (Arch) rootfs, stripped to bare minimum.
- Host tools to install: arch-install-scripts, xorriso, grub, squashfs-tools.
- Rootfs: kernel, glibc, busybox, openssl, zlib, python, util-linux.
- Remove: gcc, package manager, ssh, getty, sudo, network config, man-db.
- Add: llama.cpp prebuilt, vendored `requests`, as-os tree, jail, models.

## Boot + persistence

- ISO = read-only squashfs root + writable ext4 data partition.
  - data partition: /home, jail/home, jail/packages, session store, config.
  - squashfs: kernel, userspace, as-os, models, jail read-only parts.
- GRUB bootloader; kernel cmdline points init at the data partition.

## as-os code changes

- `daemon/session.py` / `daemon/tools.py`: shell-layer `run` executes in the
  chrooted jail (never host /bin/sh).
- OOBE: add a model-selection step (8B default / 1.2B option) storing the
  choice in the data partition config; init reads it before launching the
  engine.
- New shell builtin `reoobe`: re-run onboarding without a reboot.
- `essential/sysinfo/sysinfo.as`: print the ascOS ASCII logo + name + version.

## Phases

1. Host prep — install build tools; write rootfs build/strip scripts.
2. Rootfs + kernel — pacstrap minimal, strip, bake in as-os + jail + models.
3. Boot — custom init, console->as#, GRUB, squashfs + data part, ISO assembly.
4. as-os changes — chroot run, OOBE model step, reoobe, sysinfo logo.
5. Test — boot ISO in QEMU, verify as#, sysinfo, no escape, model swap,
   persistence across reboot.
6. Makefile buildchain — `make iso` rebuild from scratch or incremental.
7. Docs — README + this plan.

## Verification checklist

- QEMU boots to `as#` (no login prompt anywhere).
  [PARTIAL — stage1+stage2 boot cleanly through engine startup; as# prompt
   not reached under QEMU TCG emulation because model load is glacial there.
   The exact engine cmd + config verified working on real hardware.]
- `sysinfo` prints ascOS + ASCII logo.  [DONE — sysinfo.as rewritten]
- No compiler/package-manager/ssh in the rootfs.  [DONE — 02_strip.sh removes]
- `run` from the shell executes inside the jail.  [DONE — session.py run
   always chrooted]
- OOBE lets you pick 8B or 1.2B; `reoobe` re-runs it.  [DONE — init prompts
   first boot, daemon.set_model + shell model/reoobe builtins]
- Data (users, packages, sessions) survives reboot on the data partition.
  [DONE — ext4 ascdata partition; stage1 boots root.squashfs from it]
- `make iso` reproduces the image.  [DONE — Makefile buildchain]

## Boot flow (final)

- isolinux/GRUB loads kernel + initramfs.
- stage-1 initramfs: insmod loop+squashfs, find data partition (ext4
  LABEL=ascdata), mount it, losetup root.squashfs, mount squashfs, move
  /proc//sys//dev, switch_root to /sbin/init.
- stage-2 /sbin/init: mount proc/sys/dev/pts + tmpfs /tmp//run, mount data
  partition, seed on first boot, ask model on first boot, bind jail
  home/packages/etc, start llama-server on the chosen model, exec
  as_shell.py. No getty/login/sshd anywhere.

## Build system

`make iso` (full), `make rootfs`, `make squashfs`, `make initramfs`,
`make seed`, `make data-disk`, `make usb DEV=/dev/sdX` (flash to USB, UEFI),
`make test` (QEMU), `make clean`. Root required.

## Installing on hardware

There is no in-OS installer (and the AI shell can't do disk ops — it's
chrooted by design). Two paths:
- Host-side flash utility: `make usb DEV=/dev/sdX` — GPT partition (ESP
  FAT32 + ext4 ascdata), copy squashfs+seed, install GRUB UEFI. Verified
  working on a real 28.6G USB.
- (Planned) on-device install mode: a GRUB menu entry / kernel arg that runs
  a partitioner before as# launches — how real distros install from the live
  image. Not yet built.

UEFI note: the USB must boot via the EFI path (BOOTX64.EFI on the ESP);
BIOS-only GRUB won't show on UEFI systems without CSM. Secure Boot must be
off (unsigned GRUB).

