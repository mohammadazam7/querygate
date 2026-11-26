#!/usr/bin/env bash
# Put what the page needs to run Python next to it: the Pyodide runtime (from the npm
# package) and two wheels, querygate built from this checkout and the sqlglot version
# pinned in requirements-dev.lock. Nothing is fetched from a CDN at run time.
set -euo pipefail

HERE=$(cd "$(dirname "$0")/.." && pwd)
REPO=$(cd "$HERE/.." && pwd)
PY=${PYTHON:-python3}

rm -rf "$HERE/public/pyodide" "$HERE/public/py"
mkdir -p "$HERE/public/pyodide" "$HERE/public/py"

for f in pyodide.mjs pyodide.asm.js pyodide.asm.wasm python_stdlib.zip pyodide-lock.json; do
  cp "$HERE/node_modules/pyodide/$f" "$HERE/public/pyodide/"
done

SQLGLOT=$(grep -E '^sqlglot==' "$REPO/requirements-dev.lock" | head -1 | cut -d' ' -f1)
"$PY" -m pip download -q --no-deps --only-binary=:all: --implementation py --abi none \
  --platform any --python-version 3.12 -d "$HERE/public/py" "$SQLGLOT"
"$PY" -m pip wheel -q --no-deps -w "$HERE/public/py" "$REPO"

(cd "$HERE/public/py" && ls *.whl | "$PY" -c 'import json,sys; print(json.dumps(sorted(l.strip() for l in sys.stdin)))' > manifest.json)
echo "wheels: $(cat "$HERE/public/py/manifest.json")"
