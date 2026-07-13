#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [ ! -d node_modules ]; then
  echo "node_modules not found. Run npm install once before using this script."
  exit 1
fi

echo "Building VitePress..."
npm run build

echo "Starting VitePress..."
npm run dev
