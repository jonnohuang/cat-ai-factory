#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOOKS_DIR="$ROOT_DIR/scripts/githooks"

git config core.hooksPath "$HOOKS_DIR"
echo "✅ Installed git hooks from: $HOOKS_DIR"
