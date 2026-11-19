#!/usr/bin/env bash
# ==============================================================================
# Scalable Capital Smart DCA Runner Script
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Ensure sc is available
if ! command -v sc >/dev/null 2>&1; then
    if [ -f "/opt/homebrew/bin/sc" ]; then
        export PATH="/opt/homebrew/bin:$PATH"
    else
        echo "Error: 'sc' (Scalable CLI) command not found in PATH." >&2
        exit 1
    fi
fi

# Pass all CLI args to the python module
exec python3 -m smart_dca "$@"
