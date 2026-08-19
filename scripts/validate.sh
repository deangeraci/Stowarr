#!/bin/sh
set -eu

cd "$(dirname "$0")/.."

echo "========== PYTHON SYNTAX =========="

python3 -m compileall -q src tests

echo "PASS"

echo
echo "========== UNIT TESTS =========="

python3 -m unittest discover -s tests -v

echo
echo "========== CONFIG SAFETY =========="

if grep -Eq \
  'allow_download:[[:space:]]*true|allow_import:[[:space:]]*true|allow_delete:[[:space:]]*true' \
  config/config.yaml
then
    echo "FAIL: destructive safety gate enabled"
    exit 1
fi

echo "PASS: write gates disabled"

echo
echo "========== SECRET HYGIENE =========="

grep -qxF '.env' .dockerignore
grep -qxF 'config/config.yaml' .dockerignore
grep -qxF 'data/' .dockerignore

echo "PASS: private runtime files excluded"

echo
echo "Validation: PASS"
