#!/usr/bin/env bash
set -euo pipefail
if [[ $# -lt 1 || $# -gt 2 ]]; then echo "用法：$0 /ABSOLUTE/PATH/TO/PROJECT [--purge-data]" >&2; exit 2; fi
PACKAGE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="$(command -v python3.11 || true)"
if [[ -z "$PYTHON_BIN" ]]; then echo "卸载失败：需要 Python 3.11 或更高版本。" >&2; exit 1; fi
PROJECT_ROOT="$1"; shift
exec "$PYTHON_BIN" "$PACKAGE_ROOT/scripts/package_manager.py" uninstall --scope project --project-root "$PROJECT_ROOT" "$@"
