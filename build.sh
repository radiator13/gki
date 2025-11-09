#!/usr/bin/env bash
set -euo pipefail

# -------------------------------------------------------------------
# CONFIGURATION — Adjust these variables as needed
# -------------------------------------------------------------------
SCRIPT_VERSION="1.0"
BUILD_DATE="$(date +%Y-%m-%dT%H:%M:%S%z)"
KMI_GENERATION=9
BRANCH='android12-5.10'
AOSP="https://android.googlesource.com"
GKI_URL="https://dl.google.com/android/gki/gki-certified-boot-android12-5.10-2025-09_r1.zip"

AVB_ALGO="SHA256_RSA2048"
AVB_KEY="./testkey_rsa2048.pem"
PARTITION_NAME="boot"
PARTITION_SIZE=$((64 * 1024 * 1024))   # adjust if your partition size differs

# Tools paths (these assume relative paths in your repo)
AVBTOOL="./avb/avbtool.py"
MKBOOTIMG="./mkbootimg/mkbootimg.py"
UNPACK_BOOTIMG="./mkbootimg/unpack_bootimg.py"

# -------------------------------------------------------------------
# LOGGING / UTILITY FUNCTIONS
# -------------------------------------------------------------------
log()   { echo "[${SCRIPT_VERSION}] [INFO]  $*"; }
warn()  { echo "[${SCRIPT_VERSION}] [WARN]  $*" >&2; }
error() { echo "[${SCRIPT_VERSION}] [ERROR] $*" >&2; exit 1; }

# -------------------------------------------------------------------
# PRE-CHECKS
# -------------------------------------------------------------------
log "Build script started at ${BUILD_DATE}"
which clang >/dev/null 2>&1 || error "clang not installed or not in PATH"
clang -v && ld.lld -v

# -------------------------------------------------------------------
# KERNEL BUILD STEPS
# -------------------------------------------------------------------
sed -i 's/-dirty//g' scripts/setlocalversion

export KMI_GENERATION=${KMI_GENERATION}
export BRANCH="${BRANCH}"

git submodule update --init --recursive

scripts/setlocalversion --save-scmversion . "${BRANCH}" "${KMI_GENERATION}" || error "setlocalversion failed"

make ARCH=arm64 V=0 LLVM=1 LLVM_IAS=1 O=out gki_defconfig CROSS_COMPILE=aarch64-linux-gnu-
cat out/.config

JOBS=$(nproc)
log "Running make with ${JOBS} jobs"
make -j"${JOBS}" ARCH=arm64 V=0 LLVM=1 LLVM_IAS=1 O=out CROSS_COMPILE=aarch64-linux-gnu- || error "Kernel build failed"

cp out/Module.symvers kmi/Module.symvers || error "Copying Module.symvers failed"

pushd kmi >/dev/null
python3 abi.py || error "abi.py failed"
popd >/dev/null

# -------------------------------------------------------------------
# TOOLCHAIN / AVBTOOL SETUP
# -------------------------------------------------------------------
log "Cloning AVB and build-tools repos"

# Clone external/avb repo if not present
AVB_REPO_URL="${AOSP}/platform/external/avb"

if [ -d "./avb" ]; then
  log "AVB repo already exists, skipping clone"
else
  git clone "${AVB_REPO_URL}" -b main --depth 1 avb || error "Cloning AVB repo failed"
fi
chmod +x ./avb/avbtool.py

git clone "${AOSP}/platform/system/tools/mkbootimg" -b main --depth 1 mkbootimg || error "Cloning mkbootimg repo failed"

# Confirm tools
[ -x "${AVBTOOL}" ]         || error "AVB tool not found or not executable: ${AVBTOOL}"
[ -x "${MKBOOTIMG}" ]       || error "mkbootimg not found or not executable: ${MKBOOTIMG}"
[ -x "${UNPACK_BOOTIMG}" ]  || error "unpack_bootimg not found or not executable: ${UNPACK_BOOTIMG}"

# -------------------------------------------------------------------
# FETCH GKI IMAGE
# -------------------------------------------------------------------
log "Fetching GKI image from ${GKI_URL}"
status=$(curl -sL -w "%{http_code}" "${GKI_URL}" -o /dev/null)
if [[ "${status}" == "200" ]]; then
  curl -Lo gki-kernel.zip "${GKI_URL}" || error "Downloading GKI image failed"
else
  error "Invalid HTTP status ${status} for GKI image"
fi

rm -rf out/kernel
unzip gki-kernel.zip || error "Unzip GKI kernel failed"
rm gki-kernel.zip

# -------------------------------------------------------------------
# BOOT IMAGE REBUILD & SIGNING
# -------------------------------------------------------------------
log "Unpacking boot image"
BOOT_IMG=$(find . -maxdepth 1 -type f -name "boot*.img" | head -n1)
[ -n "${BOOT_IMG}" ] || error "boot image not found"
"${UNPACK_BOOTIMG}" --boot_img="${BOOT_IMG}" || error "unpack_bootimg failed"
rm "${BOOT_IMG}"

log "Building new boot.img"
"${MKBOOTIMG}" --header_version 4 \
                --kernel out/arch/arm64/boot/Image.gz \
                --output boot.img \
                --ramdisk out/ramdisk \
                --os_version 12.0.0 \
                --os_patch_level 2025-09 || error "mkbootimg failed"

log "Inspecting boot.img before signing"
"${AVBTOOL}" info_image --image boot.img || warn "info_image failed (non-critical)"

log "Signing boot.img with AVB"
"${AVBTOOL}" add_hash_footer \
                --partition_name "${PARTITION_NAME}" \
                --partition_size "${PARTITION_SIZE}" \
                --image boot.img \
                --algorithm "${AVB_ALGO}" \
                --key "${AVB_KEY}" || error "AVB signing failed"

log "Inspecting boot.img after signing"
"${AVBTOOL}" info_image --image boot.img || warn "post-sign info_image failed"

log "Build and signing completed successfully"