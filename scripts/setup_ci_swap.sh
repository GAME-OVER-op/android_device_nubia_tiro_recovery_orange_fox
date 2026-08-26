#!/usr/bin/env bash
set -euo pipefail

# Ensure the runner has at least the requested TOTAL swap capacity while
# preserving enough free disk for the Android output tree.
#
# GitHub-hosted runners can already expose a small /swapfile (for example 3 GiB).
# Do not treat that as satisfying a 16 GiB request. Instead, keep the existing
# swap active and add only the missing capacity in a second swapfile. This avoids
# swapoff before/after the memory-heavy Soong stage.
#
# Usage: setup_ci_swap.sh [desired_total_gib] [reserve_disk_gib]
DESIRED_TOTAL_GIB="${1:-16}"
RESERVE_GIB="${2:-18}"
EXTRA_SWAPFILE="${EXTRA_SWAPFILE:-/swapfile-ci-extra}"

if ! [[ "$DESIRED_TOTAL_GIB" =~ ^[0-9]+$ ]] || (( DESIRED_TOTAL_GIB < 1 )); then
  echo "ERROR: desired total swap must be a positive integer GiB" >&2
  exit 2
fi
if ! [[ "$RESERVE_GIB" =~ ^[0-9]+$ ]]; then
  echo "ERROR: reserve size must be an integer GiB" >&2
  exit 2
fi

BYTES_PER_GIB=$((1024 * 1024 * 1024))
DESIRED_BYTES=$((DESIRED_TOTAL_GIB * BYTES_PER_GIB))
RESERVE_BYTES=$((RESERVE_GIB * BYTES_PER_GIB))

current_swap_bytes() {
  swapon --show=SIZE --bytes --noheadings 2>/dev/null | awk '{sum += $1} END {printf "%.0f", sum + 0}'
}

CURRENT_BYTES="$(current_swap_bytes)"
CURRENT_GIB_HUMAN="$(awk -v b="$CURRENT_BYTES" 'BEGIN {printf "%.2f", b/1024/1024/1024}')"

echo "Existing active swap: ${CURRENT_GIB_HUMAN} GiB"
swapon --show || true

if (( CURRENT_BYTES >= DESIRED_BYTES )); then
  echo "Total active swap already meets the ${DESIRED_TOTAL_GIB} GiB target."
  free -h
  df -h /
  exit 0
fi

# If this workflow step is re-run inside the same runner and our extra swapfile
# is already active, CURRENT_BYTES already includes it. Never swap it off here.
if swapon --show=NAME --noheadings 2>/dev/null | grep -Fxq "$EXTRA_SWAPFILE"; then
  echo "::warning::${EXTRA_SWAPFILE} is already active but total swap is still below target; leaving it active and continuing with the current capacity."
  free -h
  df -h /
  exit 0
fi

MISSING_BYTES=$((DESIRED_BYTES - CURRENT_BYTES))
FREE_BYTES="$(df --output=avail -B1 / | tail -n 1 | tr -d ' ')"
MAX_EXTRA_BYTES=$((FREE_BYTES - RESERVE_BYTES))

if (( MAX_EXTRA_BYTES <= 0 )); then
  echo "::warning::Not enough disk to extend swap while preserving ${RESERVE_GIB} GiB for Android build output."
  echo "Requested total swap: ${DESIRED_TOTAL_GIB} GiB"
  swapon --show || true
  free -h
  df -h /
  exit 0
fi

ALLOC_BYTES="$MISSING_BYTES"
if (( ALLOC_BYTES > MAX_EXTRA_BYTES )); then
  ALLOC_BYTES="$MAX_EXTRA_BYTES"
fi

# Allocate whole MiB to keep fallocate/dd arguments simple and deterministic.
ALLOC_MIB=$((ALLOC_BYTES / 1024 / 1024))
if (( ALLOC_MIB < 512 )); then
  echo "::warning::Only ${ALLOC_MIB} MiB of additional swap can be created safely; skipping because it would add little value."
  swapon --show || true
  free -h
  df -h /
  exit 0
fi
ALLOC_BYTES=$((ALLOC_MIB * 1024 * 1024))
ALLOC_GIB_HUMAN="$(awk -v b="$ALLOC_BYTES" 'BEGIN {printf "%.2f", b/1024/1024/1024}')"
EXPECTED_TOTAL_BYTES=$((CURRENT_BYTES + ALLOC_BYTES))
EXPECTED_TOTAL_GIB="$(awk -v b="$EXPECTED_TOTAL_BYTES" 'BEGIN {printf "%.2f", b/1024/1024/1024}')"
FREE_GIB="$(awk -v b="$FREE_BYTES" 'BEGIN {printf "%.2f", b/1024/1024/1024}')"

echo "Creating ${ALLOC_GIB_HUMAN} GiB additional swap at ${EXTRA_SWAPFILE}"
echo "  target total swap : ${DESIRED_TOTAL_GIB} GiB"
echo "  existing swap     : ${CURRENT_GIB_HUMAN} GiB"
echo "  expected total    : ${EXPECTED_TOTAL_GIB} GiB"
echo "  free disk now     : ${FREE_GIB} GiB"
echo "  disk reserve      : ${RESERVE_GIB} GiB"

sudo rm -f "$EXTRA_SWAPFILE"
if ! sudo fallocate -l "$ALLOC_BYTES" "$EXTRA_SWAPFILE"; then
  echo "fallocate failed; using dd fallback"
  sudo dd if=/dev/zero of="$EXTRA_SWAPFILE" bs=1M count="$ALLOC_MIB" status=progress
fi
sudo chmod 600 "$EXTRA_SWAPFILE"
sudo mkswap "$EXTRA_SWAPFILE"
sudo swapon "$EXTRA_SWAPFILE"

# Keep the kernel from eagerly pushing the Soong working set out of RAM while
# still allowing the larger swap area to absorb transient peaks.
sudo sysctl -w vm.swappiness=60 >/dev/null || true

FINAL_BYTES="$(current_swap_bytes)"
FINAL_GIB="$(awk -v b="$FINAL_BYTES" 'BEGIN {printf "%.2f", b/1024/1024/1024}')"
echo "Total active swap after setup: ${FINAL_GIB} GiB"

if (( FINAL_BYTES < DESIRED_BYTES )); then
  echo "::warning::Total swap is below the ${DESIRED_TOTAL_GIB} GiB target because disk reserve limited allocation."
else
  echo "Swap target satisfied."
fi

swapon --show || true
free -h
df -h /
