#!/bin/bash
# Run PyCharm inspections with automatic cleanup

set -e

PROJECT_ROOT="${PROJECT_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
TEMP_DIR=$(mktemp -d)

# Ensure cleanup on exit
trap "rm -rf $TEMP_DIR" EXIT

echo "Running PyCharm inspections..."
echo "Temporary results directory: $TEMP_DIR"

/Applications/PyCharm.app/Contents/bin/inspect.sh \
    "$PROJECT_ROOT" \
    "$PROJECT_ROOT/.idea/inspectionProfiles/Project_Default.xml" \
    "$TEMP_DIR" \
    -v2 \
    -d "$PROJECT_ROOT/addons"

echo "Inspection complete. Results cleaned up."