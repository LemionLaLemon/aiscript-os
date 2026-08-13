# ascOS VirtualBox VM provisioning.
#   - create the VM if missing, else update its settings
#   - RAM: default 12 GB (the 8B model needs ~9 GB RSS; 1.2B fits in 4 GB)
#   - cores = min(16, host logical CPUs)
#   - attach the ISO to the optical drive and the data VDI to SATA
#   - boot order: optical first, then disk
#   - optional: start the VM headless
#
# Usage: vbox.sh [--start]  (requires build/ascOS.iso + build/ascOS-data.vdi)
# Env:  VBOX_RAM=12288  VBOX_CORES=8  VM_NAME=ascOS
set -euo pipefail
ROOT="$(pwd)"

ISO="$ROOT/build/ascOS.iso"
VDI="$ROOT/build/ascOS-data.vdi"
VM="${VM_NAME:-ascOS}"
RAM="${VBOX_RAM:-12288}"                # 12 GB — 8B needs ~9 GB RSS
HOST_NPROC="$(nproc)"
CORES="${VBOX_CORES:-$(( HOST_NPROC < 16 ? HOST_NPROC : 16 ))}"

if [ ! -f "$ISO" ]; then
    echo "ERROR: $ISO missing — run: make iso"
    exit 1
fi
if [ ! -f "$VDI" ]; then
    echo "ERROR: $VDI missing — run: make vbox (builds it first)"
    exit 1
fi

echo "==> checking for $VM..."
if VBoxManage showvminfo "$VM" > /dev/null 2>&1; then
    echo "  $VM exists — updating settings"
    VBoxManage modifyvm "$VM" \
        --memory "$RAM" --cpus "$CORES" \
        --ostype ArchLinux_64 \
        --firmware bios \
        --boot1 dvd --boot2 disk --boot3 none --boot4 none \
        --nic1 none \
        --graphicscontroller vmsvga \
        --vram 16 \
        --audio none \
        --usb off
else
    echo "  creating $VM"
    VBoxManage createvm --name "$VM" --register
    VBoxManage modifyvm "$VM" \
        --memory "$RAM" --cpus "$CORES" \
        --ostype ArchLinux_64 \
        --firmware bios \
        --boot1 dvd --boot2 disk --boot3 none --boot4 none \
        --nic1 none \
        --graphicscontroller vmsvga \
        --vram 16 \
        --audio none \
        --usb off
fi

echo "==> storage controllers..."
# IDE controller hosts the optical drive; SATA hosts the data disk.
VBoxManage storagectl "$VM" --name "IDE" --add ide --controller PIIX4 --bootable on 2>/dev/null || true
VBoxManage storagectl "$VM" --name "SATA" --add sata --controller IntelAhci --portcount 2 --bootable on 2>/dev/null || true

echo "==> attaching ISO (optical)..."
VBoxManage storageattach "$VM" --storagectl "IDE" --port 0 --device 0 \
    --type dvddrive --medium "$ISO" --mtype readonly

echo "==> attaching data VDI (SATA port 0)..."
# If the VDI is already attached, detach it first so the file can be replaced.
VBoxManage storageattach "$VM" --storagectl "SATA" --port 0 --device 0 --medium none 2>/dev/null || true
VBoxManage storageattach "$VM" --storagectl "SATA" --port 0 --device 0 \
    --type hdd --medium "$VDI"

echo ""
echo "==> ascOS VM ready ============================================"
echo "  name : $VM"
echo "  ram  : ${RAM} MB   cores: $CORES   (host has $HOST_NPROC)"
echo "  iso  : $ISO"
echo "  data : $VDI"
echo "  boot : optical first, then disk"
echo "================================================================"

if [ "${1:-}" = "--start" ]; then
    echo "==> starting $VM (headless)..."
    VBoxManage startvm "$VM" --type headless
    echo "  started. console: VBoxManage startvm $VM (or the GUI)"
fi
