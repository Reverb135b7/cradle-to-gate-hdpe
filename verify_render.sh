#!/usr/bin/env bash
# Post-deploy smoke tests for the Render service.
# Edit RENDER_URL below, then run:
#   chmod +x verify_render.sh
#   ./verify_render.sh
#
# These checks assume the Render service is live and the persistent disk is
# attached. They do not require openLCA; the openLCA card is expected to
# degrade gracefully.

set -euo pipefail

RENDER_URL="${RENDER_URL:-https://placeholder-onrender.com}"

if [[ "$RENDER_URL" == https://placeholder-onrender.com* ]]; then
  echo "Edit this script and set RENDER_URL to your live Render URL."
  echo "Example: export RENDER_URL=https://your-service-name.onrender.com"
  exit 2
fi

BASE="$RENDER_URL"
JSON_HEADER=( -H "content-type: application/json" )

pass() { echo "PASS: $*"; }
fail() { echo "FAIL: $*"; exitcode=1; }

exitcode=0

echo "=== 1. health endpoint ==="
if curl -s -f -o /dev/null -w "HTTP %{http_code}\n" "$BASE/api/health"; then
  pass "GET /api/health reachable"
else
  fail "GET /api/health not reachable"
fi

echo
echo "=== 2. PCF dashboard HTML ==="
if curl -s -f -o /dev/null -w "HTTP %{http_code}\n" "$BASE/"; then
  pass "GET / returns HTML"
else
  fail "GET / did not return 200"
fi

echo
echo "=== 3. LCA console HTML ==="
if curl -s -f -o /dev/null -w "HTTP %{http_code}\n" "$BASE/lca"; then
  pass "GET /lca returns HTML"
else
  fail "GET /lca did not return 200"
fi

echo
echo "=== 4. meta endpoint ==="
if curl -s -f "$BASE/api/meta" | python -c "import sys,json; d=json.load(sys.stdin); assert 'groups' in d and 'defaults' in d and 'presets' in d" >/dev/null 2>&1; then
  pass "GET /api/meta returned expected shape"
else
  fail "GET /api/meta missing expected fields"
fi

echo
echo "=== 5. simulate endpoint with baseline params ==="
if curl -s -f "${JSON_HEADER[@]}" -d '{"params":{}}' "$BASE/api/simulate" | python -c "import sys,json; d=json.load(sys.stdin); assert 'kpis' in d and 'validation' in d and 'stages' in d" >/dev/null 2>&1; then
  pass "POST /api/simulate with empty params returned a payload"
else
  fail "POST /api/simulate failed or returned unexpected shape"
fi

echo
echo "=== 6. primary-data recompute with ef_grid=0.2, hdpe_scope1=110 ==="
COMPUTE=$(curl -s -f "${JSON_HEADER[@]}" -d '{"params":{"ef_grid":0.2,"hdpe_scope1":110}}' "$BASE/api/lca/compute")
if echo "$COMPUTE" | python -c "import sys,json; d=json.load(sys.stdin); assert d['kpis']['gwp_t']==4.598, d['kpis'].get('gwp_t'); assert d['validation']['findings']>=1" >/dev/null 2>&1; then
  pass "POST /api/lca/compute returned gwp_t=4.598 with findings"
else
  fail "POST /api/lca/compute did not return expected recompute result"
  echo "response was: $COMPUTE"
fi

echo
echo "=== 7. openLCA methods are expected to be unavailable ==="
if curl -s -w "HTTP %{http_code}\n" -o /tmp/openlca_methods.json "$BASE/api/lca/openlca/methods"; then
  code=$(tail -1 /tmp/openlca_methods.json)
  if [[ "$code" == 503 ]]; then
    pass "GET /api/lca/openlca/methods returned 503 as expected (no openLCA)"
  else
    fail "GET /api/lca/openlca/methods returned $code; expected 503 when openLCA is absent"
  fi
else
  fail "GET /api/lca/openlca/methods did not complete"
fi

echo
echo "=== 8. characterisation coverage CSV writes into GENERATED_DIR ==="
if curl -s -f -o /tmp/coverage.csv "$BASE/lca/files/openlca/characterisation_coverage.csv"; then
  if head -1 /tmp/coverage.csv | grep -qiE 'category|impact|indicator|status' && [ -s /tmp/coverage.csv ]; then
    pass "GET /lca/files/openlca/characterisation_coverage.csv returned a non-empty CSV"
  else
    fail "GET /lca/files/openlca/characterisation_coverage.csv returned empty or unexpected content"
  fi
else
  fail "GET /lca/files/openlca/characterisation_coverage.csv failed"
fi

echo
echo "=== 9. PDF report generation into the mounted disk ==="
REPORT=$(curl -s -f "${JSON_HEADER[@]}" -d '{"params":{"ef_grid":0.2,"hdpe_scope1":110}}' "$BASE/api/report")
RUN_ID=$(echo "$REPORT" | python -c "import sys,json; print(json.load(sys.stdin).get('id','') or '')" 2>/dev/null || true)
if [[ -n "$RUN_ID" ]]; then
  PASS=0
  if curl -s -f -o /tmp/report.pdf "$BASE/generated/$RUN_ID/HDPE_PCF_cradle_to_gate_report.pdf"; then
    if [[ $(stat -c%s /tmp/report.pdf 2>/dev/null || stat -f%z /tmp/report.pdf 2>/dev/null || echo 0) -gt 50000 ]]; then
      pass "PDF report generated and downloadable: $RUN_ID"
      PASS=1
    else
      fail "PDF report downloaded but too small for a real report"
    fi
  else
    fail "PDF report URL not reachable after generation"
  fi

  if [[ $PASS -eq 0 ]]; then
    :
  fi
else
  fail "POST /api/report did not return a run id"
fi

echo
if [[ $exitcode -eq 0 ]]; then
  echo "All checks passed."
else
  echo "Some checks failed."
  exit 1
fi
