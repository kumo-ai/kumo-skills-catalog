#!/usr/bin/env bash
# Bootstrap the Kumo skills catalog into the current project.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/kumo-ai/kumo-skills-catalog/master/install.sh | bash
#   curl -fsSL ... | bash -s -- --add k8s-egress-diagnose init-vpc-workspace
set -euo pipefail

SCRIPT_URL="https://raw.githubusercontent.com/kumo-ai/kumo-skills-catalog/master/sync-skills-catalog.py"
TARGET_DIR=".agents/scripts"
TARGET_SCRIPT="$TARGET_DIR/sync-skills-catalog.py"

# Create .agents structure if missing
if [ ! -d ".agents" ]; then
  echo "Creating .agents/ directory..."
  mkdir -p ".agents/skills"
fi

mkdir -p "$TARGET_DIR"

# Download the sync script
echo "Downloading sync-skills-catalog.py..."
if ! curl -fsSL "$SCRIPT_URL" -o "$TARGET_SCRIPT"; then
  echo "Error: failed to download sync-skills-catalog.py" >&2
  exit 1
fi
chmod +x "$TARGET_SCRIPT"

# Initialize the catalog
echo "Initializing skills catalog..."
python3 "$TARGET_SCRIPT" --init

# Pass through any extra args (e.g., --add skill-name)
if [ $# -gt 0 ]; then
  echo "Running: sync-skills-catalog.py $*"
  python3 "$TARGET_SCRIPT" "$@"
fi

echo "Done. Run 'python3 $TARGET_SCRIPT --list' to see available skills."
