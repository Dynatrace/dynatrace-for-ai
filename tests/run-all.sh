#!/usr/bin/env bash
set -euo pipefail
# Run all tests and report pass/fail summary.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

TESTS=(
  test-skill-quality.sh
  test-structure.sh
)

pass=0
fail=0
failures=()

for test in "${TESTS[@]}"; do
  echo ""
  echo "━━━ Running $test ━━━"
  if bash "$SCRIPT_DIR/$test"; then
    pass=$((pass + 1))
  else
    fail=$((fail + 1))
    failures+=("$test")
  fi
done

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Results: $pass passed, $fail failed (out of ${#TESTS[@]})"
if [[ $fail -gt 0 ]]; then
  echo "Failed tests:"
  for f in "${failures[@]}"; do
    echo "  ✗ $f"
  done
  exit 1
fi
echo "All tests passed."
