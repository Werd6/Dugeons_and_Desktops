#!/usr/bin/env bash
# Sign (and optionally notarize + staple) the macOS .app for Developer ID distribution.
#
# Required:
#   CODESIGN_IDENTITY  e.g. "Developer ID Application: Your Name (TEAMID)"
#   APP path as $1     e.g. dist/Dungeons and Desktops.app
#
# Notarization (optional but recommended for Gatekeeper):
#   APPLE_API_KEY_ID, APPLE_API_ISSUER_ID, and either:
#     APPLE_API_KEY_PATH  → path to AuthKey_XXXX.p8
#     APPLE_API_KEY       → raw .p8 contents (CI)
#   APPLE_TEAM_ID
#
# Or Apple ID auth:
#   APPLE_ID, APPLE_APP_SPECIFIC_PASSWORD, APPLE_TEAM_ID
set -euo pipefail

APP="${1:?usage: sign_and_notarize.sh path/to/App.app}"
ENTITLEMENTS="$(cd "$(dirname "$0")" && pwd)/entitlements.plist"
IDENTITY="${CODESIGN_IDENTITY:?Set CODESIGN_IDENTITY to your Developer ID Application name}"

if [[ ! -d "$APP" ]]; then
  echo "error: app bundle not found: $APP" >&2
  exit 1
fi
if [[ ! -f "$ENTITLEMENTS" ]]; then
  echo "error: entitlements missing: $ENTITLEMENTS" >&2
  exit 1
fi

# PyInstaller's collect_all(PySide6) can leave Qt Designer/Assistant/Linguist
# helper apps that contain symlinks and fail deep codesign.
echo "==> Removing Qt helper app bundles (if any)"
find "$APP/Contents" \( -name "*.app" -o -name "*__dot__app" \) -print0 \
  | while IFS= read -r -d '' helper; do
      echo "    rm -rf $helper"
      rm -rf "$helper"
    done

echo "==> Signing $APP (hardened runtime)"
codesign --force --deep --options runtime --timestamp \
  --entitlements "$ENTITLEMENTS" \
  --sign "$IDENTITY" \
  "$APP"

echo "==> Verifying signature"
codesign --verify --deep --strict --verbose=2 "$APP"
# Gatekeeper assessment needs notarization; don't fail the local sign step on it.
spctl --assess --type execute --verbose=4 "$APP" || true

can_notarize=0
KEY_FILE=""
cleanup_key=0

if [[ -n "${APPLE_API_KEY_ID:-}" && -n "${APPLE_API_ISSUER_ID:-}" && -n "${APPLE_TEAM_ID:-}" ]]; then
  if [[ -n "${APPLE_API_KEY_PATH:-}" && -f "${APPLE_API_KEY_PATH}" ]]; then
    KEY_FILE="$APPLE_API_KEY_PATH"
  elif [[ -n "${APPLE_API_KEY:-}" ]]; then
    KEY_FILE="$(mktemp -t AuthKey).p8"
    cleanup_key=1
    printf '%s\n' "$APPLE_API_KEY" > "$KEY_FILE"
  fi
  if [[ -n "$KEY_FILE" ]]; then
    can_notarize=1
  fi
elif [[ -n "${APPLE_ID:-}" && -n "${APPLE_APP_SPECIFIC_PASSWORD:-}" && -n "${APPLE_TEAM_ID:-}" ]]; then
  can_notarize=1
fi

if [[ "$can_notarize" -ne 1 ]]; then
  echo "==> Skipping notarization (set App Store Connect API key or Apple ID secrets)"
  exit 0
fi

ZIP="$(mktemp -t dnd-notarize).zip"
ditto -c -k --sequesterRsrc --keepParent "$APP" "$ZIP"

echo "==> Submitting for notarization"
if [[ -n "$KEY_FILE" ]]; then
  xcrun notarytool submit "$ZIP" \
    --key "$KEY_FILE" \
    --key-id "$APPLE_API_KEY_ID" \
    --issuer "$APPLE_API_ISSUER_ID" \
    --wait
else
  xcrun notarytool submit "$ZIP" \
    --apple-id "$APPLE_ID" \
    --password "$APPLE_APP_SPECIFIC_PASSWORD" \
    --team-id "$APPLE_TEAM_ID" \
    --wait
fi

rm -f "$ZIP"
if [[ "$cleanup_key" -eq 1 ]]; then
  rm -f "$KEY_FILE"
fi

echo "==> Stapling notarization ticket"
xcrun stapler staple "$APP"
xcrun stapler validate "$APP"

echo "==> Done (signed + notarized)"
