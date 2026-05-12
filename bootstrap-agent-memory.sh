#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 /path/to/project-root" >&2
  exit 1
fi

project_root="$1"
source_dir="/home/dd/Projekte/templates/agent-memory"
target_dir="$project_root/agent-memory"

mkdir -p "$target_dir"
cp -r "$source_dir/." "$target_dir/"

echo "Created $target_dir from shared template."
echo "Next: edit PROJECT_OVERVIEW.md, CURRENT_STATE.md, DECISIONS.md, and SESSION_HANDOFF.md."
