#!/usr/bin/env bash
set -euo pipefail

# Create swap on ephemeral CI runners without consuming all remaining disk.
# Usage: setup_ci_swap.sh [desired_gib] [reserve_gib]
DESIRED_GIB="${1:-16}"
RESERVE_GIB="${2:-18}"
SWAPFILE="${SWAPFILE:-/swapfile}"

if ! [[ "$DESIRED_GIB" =~ ^[0-9]+$ ]] || (( DESIRED_GIB < 1 )); then
  echo "ERROR: desired swap size must be a positive integer GiB" >&2
  exit 2
fi
if ! [[ "$RESERVE_GIB" =~ ^[0-9]+$ ]]; then
  echo "ERROR: reserve size must be an integer GiB" >&2
  exit 2
fi

if swapon --show=NAME --noheadings 2>/dev/null | grep -Fxq "$SWAPFILE"; then
  echo "Swap is already active at $SWAPFILE"
  swapon --show
  free -h
  exit 0
fi

BYTES_PER_GIB=$((1024 * 1024 * 1024))
FREE_BYTES="$(df --output=avail -B1 / | tail -n 1 | tr -d ' ')"
FREE_GIB=$((FREE_BYTES / BYTES_PER_GIB))
MAX_SAFE_GIB=$((FREE_GIB - RESERVE_GIB))

if (( MAX_SAFE_GIB < 1 )); then
  echo "::warning::Not enough disk to create swap while preserving ${RESERVE_GIB} GiB for the Android build. Continuing without a new swapfile."
  df -h /
  free -h
  exit 0
fi

ALLOC_GIB="$DESIRED_GIB"
if (( ALLOC_GIB > MAX_SAFE_GIB )); then
  ALLOC_GIB="$MAX_SAFE_GIB"
  echo "::warning::Only ${FREE_GIB} GiB is free. Creating ${ALLOC_GIB} GiB swap instead of ${DESIRED_GIB} GiB to preserve about ${RESERVE_GIB} GiB for build output."
fi

# Avoid tiny swap files which add little value but still consume disk.
if (( ALLOC_GIB < 4 )); then
  echo "::warning::Safe swap size would be only ${ALLOC_GIB} GiB. Skipping swap creation to preserve build disk space."
  df -h /
  free -h
  exit 0
fi

echo "Creating ${ALLOC_GIB} GiB swap at ${SWAPFILE} (target=${DESIRED_GIB} GiB, disk reserve=${RESERVE_GIB} GiB)"
sudo swapoff "$SWAPFILE" 2>/dev/null || true
sudo rm -f "$SWAPFILE"

if ! sudo fallocate -l "${ALLOC_GIB}G" "$SWAPFILE"; then
  echo "fallocate failed; using dd fallback"
  sudo dd if=/dev/zero of="$SWAPFILE" bs=1M count=$((ALLOC_GIB * 1024)) status=progress
fi
sudo chmod 600 "$SWAPFILE"
sudo mkswap "$SWAPFILE"

if sudo swapon "$SWAPFILE"; then
  sudo sysctl -w vm.swappiness=80 >/dev/null || true
  echo "Swap enabled successfully"
else
  echo "::warning::swapon is not permitted on this runner; continuing without the new swapfile."
  sudo rm -f "$SWAPFILE" || true
fi

swapon --show || true
free -h
df -h /
