#!/usr/bin/env bash
# Set up the jail with busybox so the interpreter can chroot into it.
set -euo pipefail
cd "$(dirname "$0")/.."

JAIL=jail
BBIN=/usr/bin/busybox

if [ ! -f "$BBIN" ]; then
    echo "busybox not found at $BBIN — install with: sudo pacman -S busybox"
    exit 1
fi

echo "setting up jail at $(realpath $JAIL)..."

# Create bin dir and copy busybox
mkdir -p "$JAIL/bin"
cp "$BBIN" "$JAIL/bin/busybox"
chmod 4755 "$JAIL/bin/busybox"

# Create common symlinks so /bin/sh etc. work in the chroot
cd "$JAIL/bin"
for applet in sh ls cat head tail wc sort grep find du df stat file echo \
              cp mv rm mkdir touch chmod chown sed awk xargs touch ln test \
              id whoami pwd date env printf readlink basename dirname seq; do
    ln -sf busybox "$applet"
done
cd ../..

# Ensure basic directory structure
mkdir -p "$JAIL/home" "$JAIL/apps" "$JAIL/packages" "$JAIL/etc/as-os"
mkdir -p "$JAIL/tmp" "$JAIL/dev" "$JAIL/share/man"

# Create /dev/null and /dev/urandom for commands that need them
# Skip if sudo is not available — most commands work without these
if [ ! -e "$JAIL/dev/null" ]; then
    sudo mknod -m 666 "$JAIL/dev/null" c 1 3 2>/dev/null || \
        echo "warning: could not create /dev/null (run with sudo for full setup)"
fi
if [ ! -e "$JAIL/dev/urandom" ]; then
    sudo mknod -m 666 "$JAIL/dev/urandom" c 1 9 2>/dev/null || true
fi

echo "jail ready — busybox + symlinks installed at $(realpath $JAIL/bin)"
echo "test: unshare --user --map-root-user chroot $JAIL /bin/sh -c 'ls /bin'"
