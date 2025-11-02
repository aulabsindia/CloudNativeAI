#!/bin/bash

################################################################################
# Docker Compose Test Suite for /build Endpoint
# COMPLETE VERSION - With Response Validation (Files & Nodes Count)
#
# Test Cases:
# 1. Empty directories      -> 200, status=index_built, files=0, nodes=0
# 2. Single Go file         -> 200, status=index_built, files=1, nodes>0
# 3. Multiple Go files (5)  -> 200, status=index_built, files=5, nodes>0
# 4. Go files only (5)      -> 200, status=index_built, files=5, nodes>0
# 5. Malformed Go syntax    -> 200, status=index_built, files>0, nodes>0
# 6. Empty Go files         -> 200, status=index_built, files>0, nodes>0
# 7. Load test (10 files)   -> 200, status=index_built, files=10, nodes>0
#
# Validation includes:
# - HTTP return code (200)
# - "status" field = "index_built"
# - "files" count matches expected
# - "nodes" count is correct
################################################################################

set -e
set -o pipefail
set +e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

COMPOSE_FILE="${REPO_ROOT}/docker-compose.yaml"
ENV_FILE="${REPO_ROOT}/.env"
ENV_BACKUP="${REPO_ROOT}/.env.bk"
FEEDS_DIR="${REPO_ROOT}/feeds"
API_PORT="${API_PORT:-5001}"
API_URL="http://localhost:${API_PORT}"
STARTUP_WAIT="${STARTUP_WAIT:-35}"
TESTS_PASSED=0
TESTS_FAILED=0
TEST_LOG_DIR="${REPO_ROOT}/test_results_build_$(date +%Y%m%d_%H%M%S)"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

mkdir -p "${TEST_LOG_DIR}"

################################################################################
# Helper Functions
################################################################################

print_header() {
    echo -e "\n${BLUE}$(printf '=%.0s' {1..80})${NC}"
    echo -e "${BLUE}  $1${NC}"
    echo -e "${BLUE}$(printf '=%.0s' {1..80})${NC}"
}

print_test_header() {
    local test_num="$1"
    local test_name="$2"
    echo -e "\n${YELLOW}[TEST $test_num]${NC} $test_name"
}

print_pass() {
    echo -e "${GREEN}✓ PASS${NC} $1"
    ((TESTS_PASSED++))
}

print_fail() {
    echo -e "${RED}✗ FAIL${NC} $1"
    ((TESTS_FAILED++))
}

print_info() {
    echo -e "${CYAN}ℹ${NC} $1"
}

################################################################################
# JSON Parsing Helper
################################################################################

json_get() {
    local json="$1"
    local key="$2"
    echo "$json" | grep -o "\"$key\"[^,}]*" | cut -d':' -f2 | tr -d ' "' | head -1
}

################################################################################
# Setup Functions
################################################################################

backup_env() {
    if [ ! -f "${ENV_FILE}" ]; then
        echo -e "${RED}ERROR: ${ENV_FILE} not found!${NC}"
        exit 1
    fi
    cp "${ENV_FILE}" "${ENV_BACKUP}"
    print_info "Backup created: ${ENV_BACKUP}"
}

restore_env() {
    if [ ! -f "${ENV_BACKUP}" ]; then
        echo -e "${RED}ERROR: ${ENV_BACKUP} not found!${NC}"
        exit 1
    fi
    cp "${ENV_BACKUP}" "${ENV_FILE}"
}

cleanup_feeds() {
    if [ -d "${FEEDS_DIR}" ]; then
        rm -rf "${FEEDS_DIR}"/*
    fi
}

cleanup_containers() {
    docker compose -f "${COMPOSE_FILE}" down -v --remove-orphans > /dev/null 2>&1 || true
    sleep 2
}

################################################################################
# Test Feed Generators
################################################################################

create_single_handler() {
    mkdir -p "$1"
    cat > "$1/handler.go" << 'EOF'
package main

import (
	"fmt"
)

func handlePod(name string) error {
	fmt.Printf("Processing pod: %s\n", name)
	return nil
}
EOF
}

create_multiple_handlers() {
    mkdir -p "$1"
    for i in {1..5}; do
        cat > "$1/handler_${i}.go" << EOF
package main

import "fmt"

func handler${i}(id int) {
	fmt.Printf("Handler %d processing ID: %d\n", $i, id)
}
EOF
    done
}

create_malformed_go() {
    mkdir -p "$1"
    cat > "$1/malformed.go" << 'EOF'
package main

import (
	"fmt"
)

func brokenFunction(
	fmt.Println("Missing closing brace and syntax"
	return nil
}
EOF
}

create_empty_go_file() {
    mkdir -p "$1"
    touch "$1/empty.go"
}

create_load_test_files() {
    mkdir -p "$1"
    for i in {1..10}; do
        cat > "$1/handler_load_${i}.go" << EOF
package main

import "fmt"

func processLoad${i}(data []byte) error {
	fmt.Printf("Processing load chunk %d\n", $i)
	return nil
}
EOF
    done
}

################################################################################
# Docker Management
################################################################################

start_containers() {
    print_info "Starting docker compose services..."
    docker compose -f "${COMPOSE_FILE}" up -d > /dev/null 2>&1
    print_info "Waiting ${STARTUP_WAIT}s for service..."
    sleep "${STARTUP_WAIT}"
}

check_api_health() {
    local max_attempts=10
    local attempt=0
    
    while [ $attempt -lt $max_attempts ]; do
        if curl -s "${API_URL}/verbose" > /dev/null 2>&1; then
            return 0
        fi
        attempt=$((attempt + 1))
        sleep 2
    done
    
    return 1
}

stop_containers() {
    docker compose -f "${COMPOSE_FILE}" down -v > /dev/null 2>&1 || true
    sleep 2
}

################################################################################
# API Calls
################################################################################

call_build_endpoint() {
    local directory="$1"
    local response_file="$2"
    
    curl -s -X POST "${API_URL}/build" \
        -H "Content-Type: application/json" \
        -d "{\"directory\": \"${directory}\"}" \
        -w "\n%{http_code}" \
        > "${response_file}" 2>&1
    
    local http_code=$(tail -n 1 "${response_file}")
    local body=$(head -n -1 "${response_file}")
    
    echo "${body}" > "${response_file}.body"
    echo "${http_code}" > "${response_file}.code"
}

call_build_endpoint_default() {
    local response_file="$1"
    
    curl -s -X POST "${API_URL}/build" \
        -H "Content-Type: application/json" \
        -d '{}' \
        -w "\n%{http_code}" \
        > "${response_file}" 2>&1
    
    local http_code=$(tail -n 1 "${response_file}")
    local body=$(head -n -1 "${response_file}")
    
    echo "${body}" > "${response_file}.body"
    echo "${http_code}" > "${response_file}.code"
}

################################################################################
# Response Validation with Files & Nodes Count Check
################################################################################

validate_response() {
    local test_num="$1"
    local response_file="$2"
    local expected_http="$3"
    local expected_status="$4"
    local expected_files="$5"
    local expected_nodes="$6"
    local test_name="$7"
    
    local http_code=$(cat "${response_file}.code")
    local body=$(cat "${response_file}.body")
    
    # Save response for debugging
    echo "${body}" > "${TEST_LOG_DIR}/test_${test_num}_response.json"
    
    print_info "HTTP Status Code: ${http_code}"
    
    # Check HTTP code
    if [ "$http_code" != "$expected_http" ]; then
        print_fail "HTTP ${http_code} (expected ${expected_http})"
        return 1
    fi
    
    # Parse JSON response
    local status=$(json_get "$body" "status")
    local files=$(json_get "$body" "files")
    local nodes=$(json_get "$body" "nodes")
    
    print_info "Response: status=$status, files=$files, nodes=$nodes"
    
    # Check status field
    if [ "$status" != "$expected_status" ]; then
        print_fail "status: expected '$expected_status', got '$status'"
        return 1
    fi
    
    # Check files count
    case "$expected_files" in
        ">0")
            if ! [ "$files" -gt 0 ] 2>/dev/null; then
                print_fail "files: expected >0, got $files"
                return 1
            fi
            ;;
        "0")
            if [ "$files" != "0" ]; then
                print_fail "files: expected 0, got $files"
                return 1
            fi
            ;;
        *)
            # Exact match expected
            if [ "$files" != "$expected_files" ]; then
                print_fail "files: expected $expected_files, got $files (CREATED: $expected_files files, INDEXED: $files files)"
                return 1
            fi
            ;;
    esac
    
    # Check nodes count
    case "$expected_nodes" in
        ">0")
            if ! [ "$nodes" -gt 0 ] 2>/dev/null; then
                print_fail "nodes: expected >0, got $nodes"
                return 1
            fi
            ;;
        "0")
            if [ "$nodes" != "0" ]; then
                print_fail "nodes: expected 0, got $nodes"
                return 1
            fi
            ;;
        *)
            # Exact match expected
            if [ "$nodes" != "$expected_nodes" ]; then
                print_fail "nodes: expected $expected_nodes, got $nodes"
                return 1
            fi
            ;;
    esac
    
    # All validations passed
    print_pass "HTTP $expected_http + status=$status + files=$files + nodes=$nodes"
    return 0
}

################################################################################
# Test Execution
################################################################################

run_test() {
    local test_num="$1"
    local test_name="$2"
    local setup_func="$3"
    local expected_http="$4"
    local expected_status="$5"
    local expected_files="$6"
    local expected_nodes="$7"
    
    print_test_header "${test_num}" "${test_name}"
    
    local test_response="${TEST_LOG_DIR}/test_${test_num}"
    local test_result="${TEST_LOG_DIR}/test_${test_num}_result.txt"
    
    # Setup
    restore_env
    cleanup_feeds
    mkdir -p "${FEEDS_DIR}"
    
    # Count files created by setup
    local created_files=0
    if [ "$setup_func" != "none" ]; then
        $setup_func "${FEEDS_DIR}"
        created_files=$(find "${FEEDS_DIR}" -name "*.go" 2>/dev/null | wc -l)
        print_info "Created $created_files .go files in ./feeds"
    fi
    
    cleanup_containers
    start_containers
    
    if ! check_api_health; then
        print_fail "API health check failed"
        echo "FAIL - API timeout" > "${test_result}"
        stop_containers
        cleanup_feeds
        return
    fi
    
    # Call endpoint with default (./feeds)
    print_info "Calling /build endpoint..."
    call_build_endpoint_default "${test_response}"
    
    # Validate response (including files and nodes count)
    if validate_response "${test_num}" "${test_response}" "${expected_http}" "${expected_status}" "${expected_files}" "${expected_nodes}" "${test_name}"; then
        echo "PASS" > "${test_result}"
    else
        echo "FAIL" > "${test_result}"
    fi
    
    # Cleanup
    stop_containers
    cleanup_feeds
    echo ""
}

################################################################################
# Main
################################################################################

print_header "/build Endpoint Test Suite - Complete Version with Response Validation"

print_info "Repo root: ${REPO_ROOT}"
print_info "API URL: ${API_URL}"
print_info "Results dir: ${TEST_LOG_DIR}"

if [ ! -f "${COMPOSE_FILE}" ]; then
    echo -e "${RED}ERROR: ${COMPOSE_FILE} not found!${NC}"
    exit 1
fi

# Setup
print_header "Setup Phase"
backup_env
mkdir -p "${FEEDS_DIR}"

print_header "Running Tests (With Response Validation)"

# Test 1: Empty directory -> files=0, nodes=0
run_test 1 "Empty Directory" "none" "200" "index_built" "0" "0"

# Test 2: Single Go file -> files=1, nodes>0
run_test 2 "Single Go File" "create_single_handler" "200" "index_built" "1" ">0"

# Test 3: Multiple Go files (5) -> files=5, nodes>0
run_test 3 "Multiple Go Files (5 files)" "create_multiple_handlers" "200" "index_built" "5" ">0"

# Test 4: Go files only (5) -> files=5, nodes>0
run_test 4 "Go Files Only (5 files)" "create_multiple_handlers" "200" "index_built" "5" ">0"

# Test 5: Malformed Go syntax -> files>0, nodes>0
run_test 5 "Malformed Go Syntax" "create_malformed_go" "200" "index_built" ">0" ">0"

# Test 6: Empty Go file -> files>0, nodes>0
run_test 6 "Empty Go File" "create_empty_go_file" "200" "index_built" ">0" ">0"

# Test 7: Load test (10 files) -> files=10, nodes>0
run_test 7 "Load Test (10 Go Files)" "create_load_test_files" "200" "index_built" "10" ">0"

# Cleanup
print_header "Final Cleanup"
cleanup_feeds
cleanup_containers
restore_env

# Summary
print_header "Test Summary"

echo ""
echo "Total Tests:      7"
echo -e "Tests Passed:     ${GREEN}${TESTS_PASSED}${NC}"
echo -e "Tests Failed:     ${RED}${TESTS_FAILED}${NC}"

if [ $((TESTS_PASSED + TESTS_FAILED)) -gt 0 ]; then
    success_rate=$((TESTS_PASSED * 100 / (TESTS_PASSED + TESTS_FAILED)))
    echo -e "Success Rate:     ${CYAN}${success_rate}%${NC}"
fi

echo ""
echo "Test Results: ${TEST_LOG_DIR}"
ls -lh "${TEST_LOG_DIR}"/*.json 2>/dev/null | awk '{print "  " $9}' | head -10

# Generate report
cat > "${TEST_LOG_DIR}/test_report.md" << 'REPORT_EOF'
# /build Endpoint Test Report - Response Validation

**Date:** $(date)
**Framework:** v15-rag-framework
**Endpoint:** POST /build
**Total Tests:** 7

## Test Cases with Expected Responses

| # | Test | Files Created | Expected Files | Expected Nodes | Expected HTTP | Status |
|---|------|---------------|-----------------|-----------------|----------------|--------|
| 1 | Empty Directory | 0 | 0 | 0 | 200 | - |
| 2 | Single Go File | 1 | 1 | >0 | 200 | - |
| 3 | Multiple Files (5) | 5 | 5 | >0 | 200 | - |
| 4 | Go Files Only (5) | 5 | 5 | >0 | 200 | - |
| 5 | Malformed Syntax | 1 | >0 | >0 | 200 | - |
| 6 | Empty Go File | 1 | >0 | >0 | 200 | - |
| 7 | Load Test (10) | 10 | 10 | >0 | 200 | - |

## Key Validations

✓ HTTP Status Code (200 for all)
✓ Status Field ("index_built")
✓ Files Count (matches expected)
✓ Nodes Count (matches expected)

## Results

Tests Passed: ${TESTS_PASSED}
Tests Failed: ${TESTS_FAILED}
Success Rate: $(echo "scale=1; $TESTS_PASSED * 100 / 7" | bc 2>/dev/null || echo "0")%

## Notes

- Test 1: Empty directory should return 0 files, 0 nodes
- Tests 2-7: Files indexed should match files created
- Tests 2-4: Nodes should be > 0 (depends on AST parsing)
- Test 5: Malformed code still gets indexed
- Test 6: Empty .go file still gets indexed
- Test 7: 10 files should all be indexed

## Individual Test Responses

See test_N_response.json files for detailed API responses.
REPORT_EOF

echo ""
echo "Report: ${TEST_LOG_DIR}/test_report.md"

if [ ${TESTS_FAILED} -eq 0 ]; then
    echo -e "${GREEN}✓ All tests passed! (Files & Nodes validation successful)${NC}\n"
    exit 0
else
    echo -e "${RED}✗ ${TESTS_FAILED} test(s) failed${NC}\n"
    exit 1
fi
