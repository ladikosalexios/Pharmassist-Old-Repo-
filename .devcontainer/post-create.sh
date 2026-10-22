#!/usr/bin/env bash
# Installs this checkout's dependencies into the container's volumes, as docs/VERIFY.md describes.
set -euo pipefail

# New volumes are owned by root.
sudo chown dev: backend/.venv frontend/node_modules
# A host checkout's files can appear with another owner inside the container.
git config --global --add safe.directory "$PWD"

python3.13 -m venv backend/.venv
backend/.venv/bin/python -m pip install -r backend/requirements-dev.lock
(cd frontend && npm ci)
