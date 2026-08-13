#!/usr/bin/env bash
# Build build/seed — the writable data that gets flashed to the ascdata
# partition: jail config (user, model, engine.conf) + essential packages.
set -euo pipefail
ROOT="$(pwd)"
SEED="$ROOT/build/seed"

rm -rf "$SEED"
mkdir -p "$SEED/jail/etc/as-os" \
         "$SEED/jail/home/demo/.as/sessions" \
         "$SEED/jail/home/demo/Documents" \
         "$SEED/jail/packages"

# ---- jail config -------------------------------------------------------------
echo "demo" > "$SEED/jail/etc/as-os/user"
echo "demo" > "$SEED/jail/etc/as-os/configured"
echo "${ASCOS_MODEL:-LFM2.5-8B-A1B-Q4_K_M.gguf}" > "$SEED/jail/etc/as-os/model"
# Engine config. The FULL config (4 slots x 8192 ctx) is the real-hardware
# default — the shell alone needs ~5k tokens for system prompt + tools, so
# lean settings overflow on start. Set LEAN=1 (or ASCOS_CTX/SLOTS) only for
# low-RAM VMs.
if [ "${LEAN:-0}" = "1" ]; then
    printf "SLOTS=%s\nCTX=%s\nTHREADS=%s\nMASK=%s\n" \
        "${ASCOS_SLOTS:-2}" "${ASCOS_CTX:-4096}" \
        "${ASCOS_THREADS:-4}" "${ASCOS_MASK:-0,1,2,3}" \
        > "$SEED/jail/etc/as-os/engine.conf"
else
    printf "SLOTS=%s\nCTX=%s\nTHREADS=%s\nMASK=%s\n" \
        "${ASCOS_SLOTS:-4}" "${ASCOS_CTX:-8192}" \
        "${ASCOS_THREADS:-4}" "${ASCOS_MASK:-0,1,2,3}" \
        > "$SEED/jail/etc/as-os/engine.conf"
fi

# ---- demo home ---------------------------------------------------------------
printf 'temp = 0.15\nchaos_p = 0.1\nmachine_name = "lemion"\nprompt = "as# "\n' \
    > "$SEED/jail/home/demo/.asrc"
printf 'Welcome to ascOS.\nEverything here is interpreted by an AI. Nothing is compiled.\n' \
    > "$SEED/jail/home/demo/Documents/welcome.txt"

# ---- essential packages (man, notepad, sysinfo, find-big, search-files) -------
for p in man notepad sysinfo find-big search-files; do
    if [ -e "$ROOT/essential/$p/$p.as" ]; then
        mkdir -p "$SEED/jail/packages/$p"
        cp "$ROOT/essential/$p/$p.as" "$ROOT/essential/$p/$p.aconf" \
           "$SEED/jail/packages/$p/" 2>/dev/null || true
    fi
done

# already-configured marker: skip the first-boot model prompt + seeding
touch "$SEED/.seeded"

echo "seed built at $SEED"
