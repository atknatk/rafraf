#!/usr/bin/env bash
# generate-jwt-keys.sh — Dev RSA keypair generator for JWT RS256 (T2.9).
#
# Usage:
#   bash infra/scripts/generate-jwt-keys.sh [target_dir]
#
# Defaults to ./secrets. The directory is created if missing. Existing keys
# are NOT overwritten — delete them first if you want a fresh pair.
#
# In production, keys MUST come from AWS Secrets Manager / Kubernetes
# Secrets — never from a shell script. See docs/runbooks/jwt-key-rotation.md.

set -euo pipefail

KEYS_DIR="${1:-./secrets}"
PRIVATE_KEY="$KEYS_DIR/jwt_private.pem"
PUBLIC_KEY="$KEYS_DIR/jwt_public.pem"

mkdir -p "$KEYS_DIR"

if [[ -f "$PRIVATE_KEY" ]]; then
    echo "Refusing to overwrite existing $PRIVATE_KEY — delete it first." >&2
    exit 1
fi

openssl genpkey -algorithm RSA -out "$PRIVATE_KEY" -pkeyopt rsa_keygen_bits:2048
openssl rsa -in "$PRIVATE_KEY" -pubout -out "$PUBLIC_KEY"

chmod 600 "$PRIVATE_KEY"
chmod 644 "$PUBLIC_KEY"

echo "JWT RSA keypair written to $KEYS_DIR/"
echo "  private: $PRIVATE_KEY (chmod 600)"
echo "  public : $PUBLIC_KEY  (chmod 644)"
