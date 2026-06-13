#!/usr/bin/env bash
# Generates all required Docker Secret files in secrets/
# Idempotent: skips files that already exist.
set -euo pipefail

SECRETS_DIR="$(cd "$(dirname "$0")/.." && pwd)/secrets"
mkdir -p "$SECRETS_DIR"

gen() {
  local name="$1"
  local path="$SECRETS_DIR/$name"
  if [ -f "$path" ]; then
    echo "[skip] $name already exists"
  else
    openssl rand -hex 32 > "$path"
    chmod 600 "$path"
    echo "[gen]  $name"
  fi
}

gen jwt_secret
gen postgres_password
gen redis_password
gen grafana_password

echo ""
echo "Remaining manual steps:"
echo "  echo 'YOUR_DEEPSEEK_API_KEY' > secrets/deepseek_api_key"
echo "  echo 'YOUR_TAVILY_API_KEY'   > secrets/tavily_api_key"
