#!/usr/bin/env bash
set -euo pipefail
set -x

API_LEVEL="${1:?Usage: m0-device-smoke.sh API_LEVEL}"
PACKAGE="com.huanchengfly.tieba.post"
EVIDENCE_DIR="m0-device-evidence/api-${API_LEVEL}"
mkdir -p "$EVIDENCE_DIR"

# Capture diagnostics before the action shuts down the emulator, even on failure.
collect_evidence() {
  local exit_code=$?
  trap - EXIT
  timeout 30s adb exec-out screencap -p > "$EVIDENCE_DIR/launch.png" || true
  timeout 30s adb shell dumpsys activity activities > "$EVIDENCE_DIR/activity.txt" || true
  timeout 30s adb shell dumpsys package "$PACKAGE" > "$EVIDENCE_DIR/package.txt" || true
  timeout 30s adb logcat -d -t 500 > "$EVIDENCE_DIR/logcat.txt" || true
  printf '%s\n' "$exit_code" > "$EVIDENCE_DIR/exit-code.txt"
  exit "$exit_code"
}
trap collect_evidence EXIT

APK_PATH="$(find artifacts/apk -name '*.apk' -print -quit)"
test -n "$APK_PATH"
# Push the APK before installing to avoid a stalled streaming installation.
timeout 120s adb install --no-streaming -r "$APK_PATH"
timeout 30s adb shell am force-stop "$PACKAGE"
timeout 30s adb shell monkey -p "$PACKAGE" -c android.intent.category.LAUNCHER 1
sleep 10
APP_PID="$(timeout 30s adb shell pidof "$PACKAGE" | tr -d '\r')"
test -n "$APP_PID"
printf '%s\n' "$APP_PID" > "$EVIDENCE_DIR/pid.txt"
