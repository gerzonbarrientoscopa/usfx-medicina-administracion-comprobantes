#!/usr/bin/env bash
set -euo pipefail

if ! python3 -c "import fastapi, uvicorn, motor, jwt, bcrypt, dotenv" >/dev/null 2>&1; then
  python3 -m pip install \
    --disable-pip-version-check \
    --no-input \
    -r backend/requirements.txt
fi

yarn --cwd frontend install --frozen-lockfile --non-interactive