#!/usr/bin/env bash
# Strip the rootfs to a bare AI-only system: remove anything that could be an
# escape hatch (compilers, package manager, ssh, sudo, network config) or
# that we don't ship on a 6GB image (docs, locales, python test suites).
set -euo pipefail
cd "$(dirname "$0")/.."
R=build/rootfs

echo "==> removing escape-hatch / bloat packages..."
# --- never-present tools (defense in depth) ---
rm -rf "$R/usr/bin/gcc" "$R/usr/bin/g++" "$R/usr/bin/cc" "$R/usr/bin/make"
rm -rf "$R/usr/bin/pacman" "$R/usr/bin/ssh" "$R/usr/bin/sshd" "$R/usr/bin/sudo"
rm -rf "$R/usr/bin/su" "$R/usr/bin/passwd" "$R/usr/bin/login"
rm -rf "$R/usr/bin/git" "$R/usr/bin/vim" "$R/usr/bin/nano" "$R/usr/bin/vi"
rm -rf "$R/usr/bin/python"* "$R/usr/bin/pip"* "$R/usr/lib/python"*/idlelib
rm -rf "$R/usr/lib/python"*/test "$R/usr/lib/python"*/ensurepip
rm -rf "$R/usr/lib/python"*/turtledemo

# --- init system: we use our own PID 1, drop systemd entirely ---
rm -rf "$R/usr/lib/systemd" "$R/etc/systemd" "$R/usr/lib/systemd-*"
rm -rf "$R/etc/systemd" "$R/usr/share/systemd"

# --- no network stack config (there is no network) ---
rm -rf "$R/etc/NetworkManager" "$R/usr/lib/NetworkManager" "$R/etc/systemd/network"
rm -rf "$R/etc/iwd" "$R/var/lib/iwd"

# --- no login/getty/tty helpers ---
rm -f "$R/usr/bin/getty" "$R/usr/bin/agetty" "$R/usr/bin/openvt"
rm -rf "$R/etc/security"

# --- docs, man, locales (keep C locale only) ---
rm -rf "$R/usr/share/doc" "$R/usr/share/man" "$R/usr/share/info"
find "$R/usr/share/locale" -mindepth 1 -maxdepth 1 ! -name "C*" ! -name "en*" -exec rm -rf {} + 2>/dev/null || true

# --- package db gone too ---
rm -rf "$R/var/lib/pacman" "$R/var/cache/pacman"

echo "==> stripped"
