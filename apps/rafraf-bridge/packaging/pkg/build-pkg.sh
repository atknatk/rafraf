#!/bin/bash
# build-pkg.sh — produce a signed + notarized RafRaf bridge .pkg installer.
#
# Implements Doc 11 §11.3 with the V1.2 addition: the rafraf-perm-hook
# binary MUST ship in the same payload as rafraf-bridge — the bridge's
# resolvePermissionHookPath (cmd/bridge/main.go) discovers the hook via
# os.Executable() + EvalSymlinks + sibling lookup at runtime, so the
# install layout requires both binaries to live next to each other under
# /usr/local/bin/.
#
# USAGE:
#
#   # Build a signed + notarized arm64 .pkg for v0.1.0 release:
#   APPLE_ID=mr.the.abi@gmail.com NOTARY_PASSWORD=app-specific-password \
#     packaging/pkg/build-pkg.sh 0.1.0 arm64
#
#   # Skip notarize for local smoke (signed but not stapled):
#   SKIP_NOTARIZE=1 packaging/pkg/build-pkg.sh 0.1.0 arm64
#
# REQUIREMENTS:
#   - macOS with Xcode CLT (xcrun, codesign, productbuild, pkgbuild,
#     stapler, notarytool).
#   - Developer ID Application + Developer ID Installer certs imported
#     in the login keychain (Apple Team VT3X56P4ZL).
#   - APPLE_ID env var (e.g. mr.the.abi@gmail.com).
#   - NOTARY_PASSWORD env var = app-specific password generated at
#     https://appleid.apple.com/account/manage (NOT the Apple ID
#     password itself).
#   - Go 1.25 toolchain (matches go.mod).
#
# OUTPUT:
#   dist/rafraf-bridge-<version>-<arch>.pkg — signed + (unless SKIP_NOTARIZE)
#                                              notarized + stapled.

set -euo pipefail

# ---------------------------------------------------------------------------
# Args + env validation
# ---------------------------------------------------------------------------
VERSION="${1:-}"
ARCH="${2:-arm64}"

if [ -z "${VERSION}" ]; then
    echo "ERROR: usage: $0 <version> [arch=arm64]" >&2
    exit 64
fi
if [ "${ARCH}" != "arm64" ] && [ "${ARCH}" != "amd64" ]; then
    echo "ERROR: arch must be arm64 or amd64 (got '${ARCH}')" >&2
    exit 64
fi

SKIP_NOTARIZE="${SKIP_NOTARIZE:-0}"
if [ "${SKIP_NOTARIZE}" != "1" ]; then
    if [ -z "${APPLE_ID:-}" ] || [ -z "${NOTARY_PASSWORD:-}" ]; then
        echo "ERROR: APPLE_ID and NOTARY_PASSWORD env vars required for notarize" >&2
        echo "       (set SKIP_NOTARIZE=1 to skip, e.g. for local smoke)" >&2
        exit 64
    fi
fi

# ---------------------------------------------------------------------------
# Locate self + repo root
# ---------------------------------------------------------------------------
# Resolve the script's actual dir (handle symlinks).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
# packaging/pkg/build-pkg.sh → repo: ../../
BRIDGE_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd -P)"
PACKAGING_DIR="${BRIDGE_DIR}/packaging"

cd "${BRIDGE_DIR}"

TEAM_ID="VT3X56P4ZL"
DEV_APP_CERT="Developer ID Application: The Abi (${TEAM_ID})"
DEV_INST_CERT="Developer ID Installer: The Abi (${TEAM_ID})"
PKG_IDENT="app.rafraf.bridge"

BUILD_DIR="${BRIDGE_DIR}/build"
PAYLOAD_DIR="${BUILD_DIR}/payload"
DIST_DIR="${BRIDGE_DIR}/dist"
PKG_NAME="rafraf-bridge-${VERSION}-${ARCH}.pkg"
COMPONENT_PKG="${BUILD_DIR}/rafraf-bridge-component.pkg"
FINAL_PKG="${DIST_DIR}/${PKG_NAME}"

echo "[build-pkg] version=${VERSION} arch=${ARCH} skip_notarize=${SKIP_NOTARIZE}"
echo "[build-pkg] bridge_dir=${BRIDGE_DIR}"

# ---------------------------------------------------------------------------
# 1. Clean prior build
# ---------------------------------------------------------------------------
rm -rf "${BUILD_DIR}" "${DIST_DIR}"
mkdir -p \
    "${PAYLOAD_DIR}/usr/local/bin" \
    "${PAYLOAD_DIR}/Library/LaunchAgents" \
    "${BUILD_DIR}" \
    "${DIST_DIR}"

# ---------------------------------------------------------------------------
# 2. Build both binaries (cross-arch via GOOS/GOARCH)
# ---------------------------------------------------------------------------
echo "[build-pkg] compiling rafraf-bridge..."
GOOS=darwin GOARCH="${ARCH}" CGO_ENABLED=0 \
    go build -trimpath -ldflags="-s -w -X main.Version=${VERSION}" \
    -o "${PAYLOAD_DIR}/usr/local/bin/rafraf-bridge" \
    ./cmd/bridge

echo "[build-pkg] compiling rafraf-perm-hook (V1.2)..."
GOOS=darwin GOARCH="${ARCH}" CGO_ENABLED=0 \
    go build -trimpath -ldflags="-s -w" \
    -o "${PAYLOAD_DIR}/usr/local/bin/rafraf-perm-hook" \
    ./internal/cmd/rafraf-perm-hook

# ---------------------------------------------------------------------------
# 3. Sign both binaries (Hardened Runtime — required for notarize)
# ---------------------------------------------------------------------------
for binary in rafraf-bridge rafraf-perm-hook; do
    echo "[build-pkg] codesign ${binary}..."
    codesign --force --timestamp \
        --sign "${DEV_APP_CERT}" \
        --options runtime \
        "${PAYLOAD_DIR}/usr/local/bin/${binary}"
    codesign --verify --strict --verbose=2 \
        "${PAYLOAD_DIR}/usr/local/bin/${binary}"
done

# ---------------------------------------------------------------------------
# 4. Stage launchd plist
# ---------------------------------------------------------------------------
cp "${PACKAGING_DIR}/launchd/com.rafraf.bridge.plist" \
   "${PAYLOAD_DIR}/Library/LaunchAgents/"
chmod 644 "${PAYLOAD_DIR}/Library/LaunchAgents/com.rafraf.bridge.plist"

# ---------------------------------------------------------------------------
# 5. Build component .pkg via pkgbuild
# ---------------------------------------------------------------------------
echo "[build-pkg] pkgbuild component..."
pkgbuild \
    --root "${PAYLOAD_DIR}" \
    --identifier "${PKG_IDENT}" \
    --version "${VERSION}" \
    --scripts "${PACKAGING_DIR}/pkg/scripts" \
    --install-location "/" \
    "${COMPONENT_PKG}"

# ---------------------------------------------------------------------------
# 6. Build distribution .pkg via productbuild + sign with Installer cert
# ---------------------------------------------------------------------------
echo "[build-pkg] productbuild distribution..."
productbuild \
    --distribution "${PACKAGING_DIR}/pkg/distribution.xml" \
    --package-path "${BUILD_DIR}" \
    --sign "${DEV_INST_CERT}" \
    --timestamp \
    "${FINAL_PKG}"

# ---------------------------------------------------------------------------
# 7. Notarize (unless SKIP_NOTARIZE=1)
# ---------------------------------------------------------------------------
if [ "${SKIP_NOTARIZE}" = "1" ]; then
    echo "[build-pkg] SKIP_NOTARIZE=1 — skipping notarize + staple"
    echo "[build-pkg] DONE (signed only): ${FINAL_PKG}"
    exit 0
fi

echo "[build-pkg] notarytool submit (this may take 5-15 minutes)..."
xcrun notarytool submit "${FINAL_PKG}" \
    --apple-id "${APPLE_ID}" \
    --team-id "${TEAM_ID}" \
    --password "${NOTARY_PASSWORD}" \
    --wait

echo "[build-pkg] stapler staple..."
xcrun stapler staple "${FINAL_PKG}"

# ---------------------------------------------------------------------------
# 8. Final verification
# ---------------------------------------------------------------------------
echo "[build-pkg] spctl assess..."
spctl --assess --type install --verbose "${FINAL_PKG}" || {
    echo "WARNING: spctl assess failed (may be transient — retry after a few seconds)" >&2
}

PKG_SIZE=$(stat -f%z "${FINAL_PKG}")
PKG_SHA=$(shasum -a 256 "${FINAL_PKG}" | awk '{print $1}')

echo ""
echo "==============================================================="
echo "BUILD-PKG DONE"
echo "  File:   ${FINAL_PKG}"
echo "  Size:   ${PKG_SIZE} bytes"
echo "  SHA256: ${PKG_SHA}"
echo "  Stapled + notarized for arch=${ARCH}, version=${VERSION}"
echo "==============================================================="
echo ""
echo "Next steps:"
echo "  1. Smoke install: sudo installer -pkg ${FINAL_PKG} -target /"
echo "  2. Verify launchd: launchctl list | grep com.rafraf.bridge"
echo "  3. Tag release:    git tag bridge-v${VERSION} && git push origin bridge-v${VERSION}"
echo "  4. Distribute:     upload ${FINAL_PKG} to GitHub release page"
