#!/usr/bin/env bash
# Verify Dynatrace iOS SDK setup end-to-end.
#
# Runs all checks serially with set -e so parallel agent invocation cannot
# break ordering. Each phase logs a clear header so partial failures are
# still debuggable from stdout.
#
# Usage:
#   verify-setup.sh <ProjectPath> <SchemeName> \
#                   <ExpectedAppID> <ExpectedBeaconURL> \
#                   [ExpectedOptIn:true|false]
#
# Arguments:
#   ProjectPath        Path to .xcodeproj (e.g., ./MyApp.xcodeproj)
#   SchemeName         Xcode scheme to build and verify (e.g., MyApp)
#   ExpectedAppID      Value DTXApplicationID must equal in Dynatrace.plist
#   ExpectedBeaconURL  Value DTXBeaconURL must equal in Dynatrace.plist
#   ExpectedOptIn      Optional. "true" or "false". Skip to not assert.
#
# Note: BundleID is derived automatically from xcodebuild -showBuildSettings.
#
# Exit codes:
#   0  All checks passed (framework linked, plist values correct, agent log found)
#   1  Bad arguments
#   2  Build output missing/incorrect (framework, plist, or plist values)
#   3  Simulator boot / install / launch failed
#   4  Dynatrace Core startup log not found
#   5  Log fetch failed (could not read simulator logs)

set -euo pipefail

if [[ $# -lt 4 ]]; then
  echo "Usage: $0 <ProjectPath> <SchemeName> <ExpectedAppID> <ExpectedBeaconURL> [ExpectedOptIn]" >&2
  exit 1
fi

PROJECT_PATH="$1"
SCHEME_NAME="$2"
EXPECTED_APP_ID="$3"
EXPECTED_BEACON_URL="$4"
EXPECTED_OPT_IN="${5:-}"

echo "=== Phase 1: Resolve build output directory ==="
# Capture build settings once and derive both BUILT_PRODUCTS_DIR and FULL_PRODUCT_NAME.
set +e
BUILD_SETTINGS=$(xcodebuild -project "$PROJECT_PATH" -scheme "$SCHEME_NAME" \
  -configuration Debug -sdk iphonesimulator -showBuildSettings 2>&1)
XCODE_STATUS=$?
set -e
if [[ $XCODE_STATUS -ne 0 ]]; then
  echo "ERROR: xcodebuild -showBuildSettings failed for scheme '$SCHEME_NAME' in '$PROJECT_PATH':" >&2
  echo "$BUILD_SETTINGS" >&2
  exit 2
fi

BUILD_DIR=$(echo "$BUILD_SETTINGS" | awk -F ' = ' '/^[[:space:]]*BUILT_PRODUCTS_DIR[[:space:]]*=/{print $2; exit}')
FULL_PRODUCT_NAME=$(echo "$BUILD_SETTINGS" | awk -F ' = ' '/^[[:space:]]*FULL_PRODUCT_NAME[[:space:]]*=/{print $2; exit}')
BUNDLE_ID=$(echo "$BUILD_SETTINGS" | awk -F ' = ' '/^[[:space:]]*PRODUCT_BUNDLE_IDENTIFIER[[:space:]]*=/{print $2; exit}')
if [[ -z "$BUILD_DIR" || -z "$FULL_PRODUCT_NAME" || -z "$BUNDLE_ID" ]]; then
  echo "ERROR: could not resolve BUILT_PRODUCTS_DIR/FULL_PRODUCT_NAME/PRODUCT_BUNDLE_IDENTIFIER for scheme '$SCHEME_NAME' in '$PROJECT_PATH'" >&2
  exit 2
fi
echo "BUILD_DIR=$BUILD_DIR"
echo "BUNDLE_ID=$BUNDLE_ID"

# Resolve the scheme's primary .app bundle deterministically.
APP_PATH="$BUILD_DIR/$FULL_PRODUCT_NAME"
if [[ ! -d "$APP_PATH" ]]; then
  echo "ERROR: App bundle not found at $APP_PATH" >&2
  exit 2
fi
echo "APP_PATH=$APP_PATH"

echo ""
echo "=== Phase 2: Check Dynatrace framework linked ==="
if ls "$APP_PATH/Frameworks/" 2>/dev/null | grep -i dynatrace; then
  echo "OK: Dynatrace framework present"
else
  echo "ERROR: No Dynatrace framework in $APP_PATH/Frameworks/" >&2
  exit 2
fi

echo ""
echo "=== Phase 3: Check Dynatrace.plist bundled and values correct ==="
PLIST="$APP_PATH/Dynatrace.plist"
if [[ ! -f "$PLIST" ]]; then
  echo "ERROR: Dynatrace.plist not bundled in app" >&2
  exit 2
fi
if ! plutil -p "$PLIST"; then
  echo "ERROR: Dynatrace.plist is invalid or unreadable: $PLIST" >&2
  exit 2
fi

ACTUAL_APP_ID=$(/usr/libexec/PlistBuddy -c 'Print :DTXApplicationID' "$PLIST" 2>/dev/null || true)
ACTUAL_BEACON_URL=$(/usr/libexec/PlistBuddy -c 'Print :DTXBeaconURL' "$PLIST" 2>/dev/null || true)

if [[ "$ACTUAL_APP_ID" != "$EXPECTED_APP_ID" ]]; then
  echo "ERROR: DTXApplicationID mismatch. expected='$EXPECTED_APP_ID' actual='$ACTUAL_APP_ID'" >&2
  exit 2
fi
echo "OK: DTXApplicationID=$ACTUAL_APP_ID"

if [[ "$ACTUAL_BEACON_URL" != "$EXPECTED_BEACON_URL" ]]; then
  echo "ERROR: DTXBeaconURL mismatch. expected='$EXPECTED_BEACON_URL' actual='$ACTUAL_BEACON_URL'" >&2
  exit 2
fi
echo "OK: DTXBeaconURL=$ACTUAL_BEACON_URL"

if [[ -n "$EXPECTED_OPT_IN" ]]; then
  ACTUAL_OPT_IN=$(/usr/libexec/PlistBuddy -c 'Print :DTXUserOptIn' "$PLIST" 2>/dev/null || true)
  if [[ "$ACTUAL_OPT_IN" != "$EXPECTED_OPT_IN" ]]; then
    echo "ERROR: DTXUserOptIn mismatch. expected='$EXPECTED_OPT_IN' actual='$ACTUAL_OPT_IN'" >&2
    exit 2
  fi
  echo "OK: DTXUserOptIn=$ACTUAL_OPT_IN"
fi

echo ""
echo "=== Phase 4: Select simulator ==="
# Pick the newest available iPhone simulator for consistent selection.
DEVICE_ID=$(xcrun simctl list devices available \
  | grep 'iPhone' | sort -rV | head -1 | grep -oE '[0-9A-Fa-f-]{36}' || true)
if [[ -z "$DEVICE_ID" ]]; then
  echo "ERROR: No available iPhone simulator found" >&2
  exit 3
fi
echo "DEVICE_ID=$DEVICE_ID"

echo ""
echo "=== Phase 5: Boot simulator ==="
# `simctl boot` exits non-zero when already booted; treat that as success.
BOOT_OUT=$(xcrun simctl boot "$DEVICE_ID" 2>&1) || {
  if echo "$BOOT_OUT" | grep -q "Booted"; then
    echo "(already booted)"
  else
    echo "ERROR: simctl boot failed: $BOOT_OUT" >&2
    exit 3
  fi
}
# Keep the Simulator.app foregrounded so the user can see the launch.
if ! open -a Simulator; then
  echo "WARN: Could not open Simulator.app; continuing with simctl-based verification." >&2
fi

echo ""
echo "=== Phase 6: Install app ==="
if ! xcrun simctl install "$DEVICE_ID" "$APP_PATH"; then
  echo "ERROR: simctl install failed for $APP_PATH on $DEVICE_ID" >&2
  exit 3
fi

echo ""
echo "=== Phase 7: Launch app ==="
if ! xcrun simctl launch "$DEVICE_ID" "$BUNDLE_ID"; then
  echo "ERROR: simctl launch failed for $BUNDLE_ID on $DEVICE_ID" >&2
  exit 3
fi

echo ""
echo "=== Phase 8: Wait for agent startup (poll up to 15s) ==="
# Resolve the process name from the app bundle to scope log filtering.
APP_EXECUTABLE=$(/usr/libexec/PlistBuddy -c 'Print :CFBundleExecutable' "$APP_PATH/Info.plist" 2>/dev/null || true)
if [[ -z "$APP_EXECUTABLE" ]]; then
  echo "WARN: Could not read CFBundleExecutable from Info.plist; falling back to unscoped log predicate." >&2
fi

# Poll instead of sleeping a fixed duration: fast on warm sims, still
# resilient on cold ones. Stops as soon as the log line appears.
LOG_OUTPUT=""
LOG_STATUS=0
for _ in $(seq 1 15); do
  set +e
  if [[ -n "$APP_EXECUTABLE" ]]; then
    LOG_OUTPUT=$(xcrun simctl spawn "$DEVICE_ID" log show \
      --predicate "process == \"$APP_EXECUTABLE\" AND composedMessage CONTAINS \"Dynatrace Core\"" \
      --last 30s --style compact 2>&1)
  else
    LOG_OUTPUT=$(xcrun simctl spawn "$DEVICE_ID" log show \
      --predicate 'composedMessage CONTAINS "Dynatrace Core"' \
      --last 30s --style compact 2>&1)
  fi
  LOG_STATUS=$?
  set -e
  if [[ $LOG_STATUS -eq 0 ]] && echo "$LOG_OUTPUT" | grep -q "Dynatrace Core"; then
    break
  fi
  sleep 1
done

echo ""
echo "=== Phase 9: Check logs for 'Dynatrace Core' ==="
if [[ $LOG_STATUS -ne 0 ]]; then
  echo "ERROR: log show failed (exit $LOG_STATUS):" >&2
  echo "$LOG_OUTPUT" >&2
  exit 5
fi

echo "$LOG_OUTPUT"

if echo "$LOG_OUTPUT" | grep -q "Dynatrace Core"; then
  echo ""
  echo "SUCCESS: Dynatrace SDK integrated and agent started."
  exit 0
else
  echo ""
  echo "WARN: 'Dynatrace Core' log line not found. Agent may not have started." >&2
  exit 4
fi
