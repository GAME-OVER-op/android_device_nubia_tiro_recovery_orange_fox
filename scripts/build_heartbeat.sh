#!/usr/bin/env bash
set -u

INTERVAL="${1:-60}"
if ! [[ "$INTERVAL" =~ ^[0-9]+$ ]] || (( INTERVAL < 10 )); then
  echo "ERROR: heartbeat interval must be an integer >= 10 seconds" >&2
  exit 2
fi

WORKSPACE="${GITHUB_WORKSPACE:-$(pwd)}"

echo "Build heartbeat started: interval=${INTERVAL}s workspace=${WORKSPACE}"
while true; do
  echo
  echo "::group::BUILD HEARTBEAT $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  echo "--- uptime/load ---"
  uptime || true
  echo "--- memory/swap ---"
  free -h || true
  swapon --show || true
  echo "--- vmstat ---"
  vmstat 1 2 2>/dev/null | tail -n 3 || true
  echo "--- disk ---"
  df -h "$WORKSPACE" /tmp 2>/dev/null || df -h || true
  echo "--- Android build processes ---"
  pgrep -af 'soong_build|soong_ui|ninja|ckati|kati|clang|clang\+\+|ld\.lld|javac|kotlinc|metalava' || true
  echo "--- top memory consumers ---"
  ps -eo pid,ppid,%cpu,%mem,rss,vsz,etime,stat,comm,args --sort=-rss 2>/dev/null | head -n 20 || true
  echo "::endgroup::"
  sleep "$INTERVAL"
done
