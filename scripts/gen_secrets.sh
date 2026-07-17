#!/usr/bin/env bash
# Generates all required Docker Secret files in secrets/ and syncs the matching
# .env placeholders. pydantic-settings resolves env > .env > /run/secrets, so a
# CHANGE_ME left in .env would shadow the real secret inside the api container —
# the postgres/redis/jwt values in .env must match the secret files.
# Idempotent: keeps existing non-placeholder values; only (re)generates missing
# files or CHANGE_ME placeholders.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SECRETS_DIR="$ROOT_DIR/secrets"
ENV_FILE="$ROOT_DIR/.env"
mkdir -p "$SECRETS_DIR"

gen() {
  local name="$1"
  local path="$SECRETS_DIR/$name"
  if [ -f "$path" ] && ! grep -q '^CHANGE_ME' "$path"; then
    echo "[keep] $name already set"
  else
    # tr -d '\r\n'：Windows (Git Bash) 下 openssl 输出 CRLF，残留 \r 会让
    # redis 的 $(cat secret) 密码与 .env 中的值不一致，导致认证失败。
    openssl rand -hex 32 | tr -d '\r\n' > "$path"
    chmod 600 "$path"
    echo "[gen]  $name"
  fi
}

# API keys cannot be generated — seed placeholder files so docker compose
# secret mounts do not fail; the user fills real values (mock mode needs none).
seed_placeholder() {
  local name="$1"
  local path="$SECRETS_DIR/$name"
  if [ ! -f "$path" ]; then
    cp "$ROOT_DIR/secrets.example/$name" "$path"
    chmod 600 "$path"
    echo "[seed] $name (placeholder — fill in a real value for LLM_MODE=real)"
  fi
}

# Replace a CHANGE_ME placeholder line in .env with the generated secret value.
# Lines already customized by the user are left untouched.
sync_env() {
  local var="$1"
  local name="$2"
  [ -f "$ENV_FILE" ] || return 0
  if grep -q "^${var}=CHANGE_ME" "$ENV_FILE"; then
    local value
    value="$(cat "$SECRETS_DIR/$name")"
    sed -i "s|^${var}=CHANGE_ME.*|${var}=${value}|" "$ENV_FILE"
    echo "[sync] $var -> .env (matches secrets/$name)"
  fi
}

# API keys can't be generated: comment out untouched CHANGE_ME lines in .env so
# the Docker secret file takes effect (env would shadow /run/secrets otherwise).
# Locally with LLM_MODE=real this yields a clear "must be set" validation error
# instead of silently sending the literal CHANGE_ME to the API.
comment_env_placeholder() {
  local var="$1"
  [ -f "$ENV_FILE" ] || return 0
  if grep -q "^${var}=CHANGE_ME" "$ENV_FILE"; then
    sed -i "s|^${var}=CHANGE_ME|# &|" "$ENV_FILE"
    echo "[mute] $var placeholder commented out in .env (secrets/ wins in Docker)"
  fi
}

gen jwt_secret
gen postgres_password
gen redis_password
gen grafana_password
seed_placeholder deepseek_api_key
seed_placeholder tavily_api_key

sync_env JWT_SECRET jwt_secret
sync_env POSTGRES_PASSWORD postgres_password
sync_env REDIS_PASSWORD redis_password
comment_env_placeholder DEEPSEEK_API_KEY
comment_env_placeholder TAVILY_API_KEY

echo ""
echo "Remaining manual steps (only needed when LLM_MODE=real):"
echo "  echo 'YOUR_DEEPSEEK_API_KEY' > secrets/deepseek_api_key"
echo "  echo 'YOUR_TAVILY_API_KEY'   > secrets/tavily_api_key"
