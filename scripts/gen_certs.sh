#!/usr/bin/env bash
# Generates a self-signed TLS certificate for Nginx.
# Idempotent: skips if cert already exists.
set -euo pipefail

CERT_DIR="$(cd "$(dirname "$0")/.." && pwd)/nginx/certs"
mkdir -p "$CERT_DIR"

CERT="$CERT_DIR/server.crt"
KEY="$CERT_DIR/server.key"

if [ -f "$CERT" ] && [ -f "$KEY" ]; then
  echo "[skip] Certificates already exist at $CERT_DIR"
  exit 0
fi

# Use a config file to avoid shell path-conversion issues on Windows Git Bash
TMPCONF=$(mktemp)
cat > "$TMPCONF" << 'OPENSSL_CNF'
[req]
distinguished_name = req_distinguished_name
x509_extensions = v3_req
prompt = no

[req_distinguished_name]
CN = localhost

[v3_req]
subjectAltName = IP:127.0.0.1,DNS:localhost
OPENSSL_CNF

# On Windows Git Bash, openssl needs native Windows paths; on Linux the
# POSIX path works as-is.  cygpath is present in MSYS2/Git Bash only.
if command -v cygpath > /dev/null 2>&1; then
  WIN_DIR=$(cygpath -w "$CERT_DIR")
  WIN_CONF=$(cygpath -w "$TMPCONF")
  MSYS_NO_PATHCONV=1 openssl req -x509 -newkey rsa:2048 -nodes \
    -keyout "${WIN_DIR}\\server.key" \
    -out    "${WIN_DIR}\\server.crt" \
    -days 3650 \
    -config "$WIN_CONF"
else
  openssl req -x509 -newkey rsa:2048 -nodes \
    -keyout "$KEY" \
    -out    "$CERT" \
    -days 3650 \
    -config "$TMPCONF"
fi

rm -f "$TMPCONF"

chmod 600 "$KEY"
chmod 644 "$CERT"

echo "[gen]  server.crt + server.key written to $CERT_DIR"
echo "       Self-signed cert valid for 3650 days."
echo "       Import server.crt into your browser/OS trust store to remove warnings."
