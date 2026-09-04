#!/usr/bin/env bash
set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

echo "====================================================="
echo " Verifying Sandbox Network Isolation & Topology"
echo "====================================================="

TESTS_PASSED=0
TOTAL_TESTS=3

pass_test() {
    echo -e "${GREEN}[PASS] ${1}${NC}"
    TESTS_PASSED=$((TESTS_PASSED + 1))
}

fail_test() {
    echo -e "${RED}[FAIL] ${1}${NC}"
    exit 1
}

# -----------------------------------------------------------------------------
# Test 1: Assert internal container (hapi-fhir-jpaserver) cannot reach internet
# -----------------------------------------------------------------------------
echo "Running Test 1: Verifying internal sandbox network isolation..."
if docker exec hapi-fhir-jpaserver curl --max-time 5 -s -I https://google.com > /dev/null 2>&1; then
    fail_test "Test 1 Failed: hapi-fhir-jpaserver was able to access external internet!"
else
    pass_test "Test 1: hapi-fhir-jpaserver is strictly isolated (no direct internet access)."
fi

# -----------------------------------------------------------------------------
# Test 2: Assert orchestrator can reach allowlisted domain (api.openai.com) via egress-proxy
# -----------------------------------------------------------------------------
echo "Running Test 2: Verifying egress proxy allows target LLM API domain (api.openai.com)..."
HTTP_CODE=$(docker exec -e HTTPS_PROXY=http://egress-proxy:3128 orchestrator curl --max-time 5 -s -o /dev/null -w "%{http_code}" https://api.openai.com || echo "000")

if [ "$HTTP_CODE" != "000" ]; then
    pass_test "Test 2: Egress proxy successfully routed request to api.openai.com (HTTP $HTTP_CODE)."
else
    fail_test "Test 2 Failed: Failed to connect to api.openai.com via egress proxy."
fi

# -----------------------------------------------------------------------------
# Test 3: Assert orchestrator cannot reach unauthorized domain (google.com) via egress-proxy
# -----------------------------------------------------------------------------
echo "Running Test 3: Verifying egress proxy blocks non-allowlisted domain (google.com)..."
PROXY_RESPONSE=$(docker exec -e HTTPS_PROXY=http://egress-proxy:3128 orchestrator curl --max-time 5 -s -o /dev/null -w "%{http_code}" https://google.com || echo "000")

if [ "$PROXY_RESPONSE" == "403" ] || [ "$PROXY_RESPONSE" == "000" ] || [ "$PROXY_RESPONSE" == "502" ]; then
    pass_test "Test 3: Egress proxy successfully blocked unauthorized destination google.com (Response Code: $PROXY_RESPONSE)."
else
    fail_test "Test 3 Failed: egress-proxy allowed unauthorized traffic to google.com (HTTP $PROXY_RESPONSE)!"
fi

echo "====================================================="
echo -e "${GREEN}All $TESTS_PASSED/$TOTAL_TESTS network isolation checks passed successfully!${NC}"
echo "====================================================="
