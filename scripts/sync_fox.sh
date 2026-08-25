#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FOX_SRC="${FOX_SRC:-$ROOT/.work/fox_12.1}"
SYNC_DIR="${FOX_SYNC_DIR:-$ROOT/.work/orangefox-sync}"
LOCK_FILE="$ROOT/config/source-lock.env"
LOCKED_FOX_SYNC_REV="14eca5f7"
if [[ -f "$LOCK_FILE" ]]; then
  v="$(sed -n 's/^FOX_SYNC_REV=//p' "$LOCK_FILE" | head -n1)"
  [[ -n "$v" ]] && LOCKED_FOX_SYNC_REV="$v"
fi
# Pinned by default for reproducibility. Explicit FOX_SYNC_REV still wins.
FOX_SYNC_REV="${FOX_SYNC_REV:-$LOCKED_FOX_SYNC_REV}"
SYNC_JOBS="${SYNC_JOBS:-4}"

mkdir -p "$(dirname "$FOX_SRC")" "$(dirname "$SYNC_DIR")"

if [[ ! -d "$SYNC_DIR/.git" ]]; then
  git clone https://gitlab.com/OrangeFox/sync.git "$SYNC_DIR"
else
  git -C "$SYNC_DIR" fetch --all --tags --prune
fi

git -C "$SYNC_DIR" checkout --detach "$FOX_SYNC_REV"

echo "OrangeFox sync helper revision: $(git -C "$SYNC_DIR" rev-parse HEAD)"

retry() {
  local max="$1"; shift
  local attempt=1
  until "$@"; do
    if (( attempt >= max )); then
      echo "ERROR: command failed after $attempt attempts: $*" >&2
      return 1
    fi
    echo "Command failed (attempt $attempt/$max). Retrying..." >&2
    attempt=$((attempt + 1))
    sleep 5
  done
}

if [[ ! -d "$FOX_SRC/.repo" ]]; then
  # The official helper is explicitly designed to be rerun if a network sync is
  # interrupted, so use a small retry budget for GitHub-hosted runners.
  retry 3 "$SYNC_DIR/orangefox_sync.sh" --branch 12.1 --path "$FOX_SRC"
else
  cd "$FOX_SRC"
  retry 3 repo sync --force-sync -c -j"$SYNC_JOBS" --no-clone-bundle --no-tags
  if [[ -d bootable/recovery/.git ]]; then
    retry 3 git -C bootable/recovery pull --ff-only
  fi
  if [[ -d vendor/recovery/.git ]]; then
    retry 3 git -C vendor/recovery pull --ff-only
  fi
fi

echo "OrangeFox source ready at: $FOX_SRC"
