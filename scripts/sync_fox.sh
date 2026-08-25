#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCK_FILE="$ROOT/config/source-lock.env"
LOCKED_FOX_SYNC_REV="14eca5f7"
LOCKED_FOX_BRANCH="14.1"
if [[ -f "$LOCK_FILE" ]]; then
  v="$(sed -n 's/^FOX_SYNC_REV=//p' "$LOCK_FILE" | head -n1)"
  [[ -n "$v" ]] && LOCKED_FOX_SYNC_REV="$v"
  v="$(sed -n 's/^FOX_BRANCH=//p' "$LOCK_FILE" | head -n1)"
  [[ -n "$v" ]] && LOCKED_FOX_BRANCH="$v"
fi

FOX_SYNC_REV="${FOX_SYNC_REV:-$LOCKED_FOX_SYNC_REV}"
FOX_BRANCH="${FOX_BRANCH:-$LOCKED_FOX_BRANCH}"
FOX_SRC="${FOX_SRC:-$ROOT/.work/fox_${FOX_BRANCH}}"
SYNC_DIR="${FOX_SYNC_DIR:-$ROOT/.work/orangefox-sync}"
SYNC_JOBS="${SYNC_JOBS:-4}"
PATCH_FILE="patches/patch-manifest-fox_${FOX_BRANCH}.diff"

mkdir -p "$(dirname "$FOX_SRC")" "$(dirname "$SYNC_DIR")"

if [[ ! -d "$SYNC_DIR/.git" ]]; then
  git clone https://gitlab.com/OrangeFox/sync.git "$SYNC_DIR"
else
  git -C "$SYNC_DIR" fetch --all --tags --prune
fi

git -C "$SYNC_DIR" checkout --detach "$FOX_SYNC_REV"
echo "OrangeFox sync helper revision: $(git -C "$SYNC_DIR" rev-parse HEAD)"
echo "OrangeFox branch: $FOX_BRANCH"

for required in orangefox_sync.sh "$PATCH_FILE"; do
  if [[ ! -f "$SYNC_DIR/$required" ]]; then
    echo "ERROR: pinned OrangeFox sync helper is missing: $required" >&2
    exit 1
  fi
done

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

run_official_sync_helper() {
  (
    cd "$SYNC_DIR"
    ./orangefox_sync.sh --branch "$FOX_BRANCH" --path "$FOX_SRC"
  )
}

if [[ ! -d "$FOX_SRC/.repo" ]]; then
  retry 3 run_official_sync_helper
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

echo "OrangeFox $FOX_BRANCH source ready at: $FOX_SRC"
