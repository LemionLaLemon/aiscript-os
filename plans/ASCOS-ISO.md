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
- `sysinfo` prints ascOS + ASCII logo.
- No compiler/package-manager/ssh in the rootfs.
- `run` from the shell executes inside the jail.
- OOBE lets you pick 8B or 1.2B; `reoobe` re-runs it.
- Data (users, packages, sessions) survives reboot on the data partition.
- `make iso` reproduces the image.
