#!/bin/sh
set -eu
if [ "$#" -ne 1 ]; then
  echo "usage: ROLLBACK.sh TARGET" >&2
  exit 2
fi
baseline="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)/BASELINE_FILE"
cp -- "$baseline" "$1"
echo "restored baseline to $1"
