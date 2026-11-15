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

config=${1:-config/config.yaml}
if [ "$#" -eq 0 ] && [ ! -e "$config" ]; then
    config=config/config.example.yaml
fi
python3 - "$config" <<'PY'
import sys
import yaml

try:
    with open(sys.argv[1], encoding="utf-8") as stream:
        safety = yaml.safe_load(stream)["safety"]
    if any(safety[gate] is not False for gate in
           ("allow_download", "allow_import", "allow_delete")):
        raise ValueError
except (OSError, KeyError, TypeError, ValueError, yaml.YAMLError):
    raise SystemExit("FAIL: config must be readable and all write gates must be false")
PY

echo "PASS: write gates disabled"

echo
echo "========== SECRET HYGIENE =========="

grep -qxF '.env' .dockerignore
grep -qxF '.env.approvals' .dockerignore
grep -qxF '.env.approvals' .gitignore
grep -qxF 'config/config.yaml' .dockerignore
grep -qxF 'data/' .dockerignore

echo "PASS: private runtime files excluded"

echo
echo "Validation: PASS"
