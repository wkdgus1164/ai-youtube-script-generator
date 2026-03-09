#!/usr/bin/env bash
set -euo pipefail

python /app/codex/generate_script_writer_config.py
exec bash start.sh
