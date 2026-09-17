#!/usr/bin/env bash
set -euo pipefail
if [[ $# -ne 1 ]]; then echo "用法：$0 /ABSOLUTE/PATH/TO/PROJECT" >&2; exit 2; fi
PACKAGE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="$(command -v python3.11 || true)"
if [[ -z "$PYTHON_BIN" ]]; then echo "安装失败：需要 Python 3.11 或更高版本。" >&2; exit 1; fi
exec "$PYTHON_BIN" "$PACKAGE_ROOT/scripts/package_manager.py" install --scope project --project-root "$1" --python "$PYTHON_BIN"
