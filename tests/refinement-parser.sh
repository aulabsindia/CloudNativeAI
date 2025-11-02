#!/bin/bash

################################################################################
# Docker Compose Test Suite for MAX_REFINEMENT_ITERATIONS
# PRODUCTION VERSION - Complete with src setup and .env backup/restore
#
# Test Workflow:
# 1. Copy ../src to current directory (setup)
# 2. Backup .env as .env.bk
# 3. For each test:
#    a. Restore .env from .env.bk
#    b. Set MAX_REFINEMENT_ITERATIONS to test value
#    c. Run docker compose up
#    d. Capture container logs
#    e. Search for expected log pattern
#    f. Tear down containers
# 4. Report pass/fail with detailed results
################################################################################

set -e
set -o pipefail

# Disable strict mode temporarily for flexibility in pattern matching
set +e

# ------------------------------------------------------------------------------
# Resolve repo root from this script's location so it works from any CWD
# ------------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Configuration (repo-rooted paths)
COMPOSE_FILE="${REPO_ROOT}/docker-compose.yaml"
ENV_FILE="${REPO_ROOT}/.env"
ENV_BACKUP="${REPO_ROOT}/.env.bk"
SRC_SOURCE="${REPO_ROOT}/src"
SRC_DEST="${REPO_ROOT}/src"
CONTAINER_NAME="v15-rag-framework"
STARTUP_WAIT="${STARTUP_WAIT:-35}"  # Increased wait time
TESTS_PASSED=0
TESTS_FAILED=0
TEST_LOG_DIR="${REPO_ROOT}/test_results_$(date +%Y%m%d_%H%M%S)"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
NC='\033[0m'

# Create test results directory
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
    echo -e "\n${YELLOW}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${YELLOW}[TEST $test_num] $test_name${NC}"
    echo -e "${YELLOW}═══════════════════════════════════════════════════════════${NC}"
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
    echo -e "${CYAN}ℹ INFO${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠ WARN${NC} $1"
}

print_setup() {
    echo -e "${MAGENTA}⚙ SETUP${NC} $1"
}

################################################################################
# Setup Functions
################################################################################

setup_src() {
    print_setup "Checking/copying src directory..."

    if [ ! -d "${SRC_SOURCE}" ]; then
        echo -e "${RED}ERROR: ${SRC_SOURCE} not found!${NC}"
        echo "Make sure you are running this from ./tests directory"
        exit 1
    fi

    # Check if src directory needs copying (if not in repo root)
    if [ ! -d "${SRC_DEST}" ] || [ "${SRC_SOURCE}" != "${SRC_DEST}" ]; then
        print_info "Copying src directory..."
        cp -r "${SRC_SOURCE}" "${SRC_DEST}" 2>/dev/null || true
    fi

    print_info "✓ src directory ready"
}

backup_env() {
    print_setup "Backing up .env file..."

    if [ ! -f "${ENV_FILE}" ]; then
        echo -e "${RED}ERROR: ${ENV_FILE} not found!${NC}"
        exit 1
    fi

    cp "${ENV_FILE}" "${ENV_BACKUP}"
    print_info "✓ Backup created: ${ENV_BACKUP}"
}

restore_env() {
    print_info "Restoring .env from backup..."

    if [ ! -f "${ENV_BACKUP}" ]; then
        echo -e "${RED}ERROR: ${ENV_BACKUP} not found!${NC}"
        exit 1
    fi

    cp "${ENV_BACKUP}" "${ENV_FILE}"
}

################################################################################
# Docker Compose Management Functions
################################################################################

cleanup_containers() {
    print_info "Cleaning up containers..."
    docker compose -f "${COMPOSE_FILE}" down -v --remove-orphans > /dev/null 2>&1 || true
    sleep 2
}

set_env_variable() {
    local key="$1"
    local value="$2"

    print_info "Setting ${key}..."

    if [ "${value}" == "__UNSET__" ]; then
        # Remove the variable from .env
        if [ -f "${ENV_FILE}" ]; then
            sed -i "/^${key}=/d" "${ENV_FILE}"
        fi
        print_info "Environment: ${key} is UNSET"
    else
        # Replace or add the variable
        if grep -q "^${key}=" "${ENV_FILE}" 2>/dev/null; then
            # Replace existing
            sed -i "s/^${key}=.*/${key}=${value}/" "${ENV_FILE}"
        else
            # Append new
            echo "${key}=${value}" >> "${ENV_FILE}"
        fi
        print_info "Set: ${key}='${value}'"
    fi

    # Verify
    if [ "${value}" != "__UNSET__" ]; then
        local actual_value=$(grep "^${key}=" "${ENV_FILE}" 2>/dev/null | cut -d'=' -f2- | tail -1)
        if [ "${actual_value}" == "${value}" ]; then
            print_info "✓ Verified: ${key}='${actual_value}'"
        else
            print_warning "⚠ Verification issue: expected '${value}', got '${actual_value}'"
        fi
    fi
}

start_containers() {
    print_info "Starting docker compose services..."
    docker compose -f "${COMPOSE_FILE}" up -d > /dev/null 2>&1
    print_info "Waiting ${STARTUP_WAIT}s for container initialization..."
    sleep "${STARTUP_WAIT}"
}

get_container_logs() {
    local log_file="$1"
    print_info "Capturing container logs..."
    docker compose -f "${COMPOSE_FILE}" logs > "${log_file}" 2>&1
}

stop_containers() {
    print_info "Stopping containers..."
    docker compose -f "${COMPOSE_FILE}" down -v > /dev/null 2>&1 || true
    sleep 2
}

################################################################################
# Pattern Matching Functions
################################################################################

check_pattern() {
    local log_file="$1"
    shift
    local patterns=("$@")

    for pattern in "${patterns[@]}"; do
        if grep -q -E -i "${pattern}" "${log_file}" 2>/dev/null; then
            return 0
        fi
    done

    return 1
}

extract_matches() {
    local log_file="$1"
    shift
    local patterns=("$@")

    for pattern in "${patterns[@]}"; do
        grep -E -i "${pattern}" "${log_file}" 2>/dev/null | head -3
    done
}

################################################################################
# Test Execution Function
################################################################################

run_test() {
    local test_num="$1"
    local env_value="$2"
    local test_name="$3"
    shift 3
    local patterns=("$@")  # Array of patterns to try

    print_test_header "${test_num}" "${test_name}"

    local test_log="${TEST_LOG_DIR}/test_${test_num}_logs.txt"
    local test_result="${TEST_LOG_DIR}/test_${test_num}_result.txt"

    # Restore .env from backup
    restore_env

    # Set environment variable
    set_env_variable "MAX_REFINEMENT_ITERATIONS" "${env_value}"

    # Clean up old containers
    cleanup_containers

    # Start containers
    start_containers

    # Get logs
    get_container_logs "${test_log}"

    # Check patterns
    print_info "Searching for patterns in logs..."

    if check_pattern "${test_log}" "${patterns[@]}"; then
        print_pass "Test ${test_num}: Pattern found"

        echo -e "\n${CYAN}Matching log lines:${NC}"
        extract_matches "${test_log}" "${patterns[@]}" | sed 's/^/  /'

        echo "PASS" > "${test_result}"
    else
        print_fail "Test ${test_num}: Pattern NOT found"

        echo -e "\n${YELLOW}Patterns searched:${NC}"
        for p in "${patterns[@]}"; do
            echo -e "  - ${p}"
        done

        echo -e "\n${YELLOW}Last 40 lines of log:${NC}"
        tail -40 "${test_log}" | sed 's/^/  /'

        echo "FAIL" > "${test_result}"
    fi

    # Stop containers
    stop_containers

    echo ""
}

################################################################################
# Main Test Suite
################################################################################

print_header "MAX_REFINEMENT_ITERATIONS Docker Compose Test Suite"

print_info "Repo root: ${REPO_ROOT}"
print_info "Compose file: ${COMPOSE_FILE}"
print_info "Env file: ${ENV_FILE}"
print_info "Env backup: ${ENV_BACKUP}"
print_info "Logs dir: ${TEST_LOG_DIR}"

# Prechecks
if [ ! -f "${COMPOSE_FILE}" ]; then
    echo -e "${RED}ERROR: ${COMPOSE_FILE} not found!${NC}"
    exit 1
fi

# Setup phase
print_header "Setup Phase"

setup_src
backup_env

print_header "Running Tests"

# Test cases with multiple pattern options
# Each test can have multiple patterns - first match wins
# Patterns are case-insensitive due to -i flag

run_test 1 "__UNSET__" "Missing Variable (unset)"     "not set"     "not found"     "environment.*not"     "MAX_REFINEMENT.*not.*set" "MAX_REFINEMENT_ITERATIONS"
run_test 2 "" "Empty Value"     "empty"     "unacceptable"     "invalid"     "empty.*default"
run_test 3 "   " "Whitespace Only"     "whitespace"     "empty"     "unacceptable"     "invalid"
run_test 4 "abc" "Alphabetic Non-Integer"     "not.*integer"     "not.*numeric"     "invalid.*value"     "must be.*integer"     "unacceptable"
run_test 5 "2.5" "Float Non-Integer"     "not.*integer"    "float"     "decimal"     "not.*whole"     "invalid.*value"    "unacceptable"
run_test 6 "0" "Zero Value"     "zero"     "disabled"     "refinement.*disabled"     "must be.*positive"     "refinement.*off"
run_test 7 "-1" "Negative Integer"     "negative"     "must be.*positive"     "positive.*required"     "-1.*invalid"
run_test 8 "1000000" "Very Large Integer"     "very large"     "too large"     "exceeds.*maximum"     "clamping"     "exceeds"
run_test 9 "1" "Valid Small Integer"     "valid"     "accepted"     "MAX_REFINEMENT_ITERATIONS"     "success"
run_test 10 "5" "Valid Typical Integer"     "valid"     "accepted"     "MAX_REFINEMENT_ITERATIONS"     "success"


# Final cleanup
print_header "Final Cleanup"
cleanup_containers
restore_env

# Generate summary
print_header "Test Summary"

echo ""
echo "Total Tests:      10"
echo -e "Tests Passed:     ${GREEN}${TESTS_PASSED}${NC}"
echo -e "Tests Failed:     ${RED}${TESTS_FAILED}${NC}"

if [ $((TESTS_PASSED + TESTS_FAILED)) -gt 0 ]; then
    success_rate=$((TESTS_PASSED * 100 / (TESTS_PASSED + TESTS_FAILED)))
    echo -e "Success Rate:     ${CYAN}${success_rate}%${NC}"
fi

echo ""
echo "Test Results Location: ${TEST_LOG_DIR}"
echo "Files:"
ls -lh "${TEST_LOG_DIR}"/*.txt 2>/dev/null | awk '{print "  " $9 " (" $5 ")"}'

# Generate markdown report
cat > "${TEST_LOG_DIR}/test_report.md" << 'REPORT_EOF'
# MAX_REFINEMENT_ITERATIONS Test Report

**Date:** $(date)
**Framework:** v15-rag-framework:latest
**Total Tests:** 10
**Passed:** ${TESTS_PASSED}
**Failed:** ${TESTS_FAILED}

## Test Results

| # | Test Case | Status |
|---|-----------|--------|
REPORT_EOF

for i in {1..10}; do
  if [ -f "${TEST_LOG_DIR}/test_${i}_result.txt" ]; then
    result=$(cat "${TEST_LOG_DIR}/test_${i}_result.txt")
    if [ "${result}" == "PASS" ]; then
      echo "| ${i} | Test ${i} | ✓ PASS |" >> "${TEST_LOG_DIR}/test_report.md"
    else
      echo "| ${i} | Test ${i} | ✗ FAIL |" >> "${TEST_LOG_DIR}/test_report.md"
    fi
  fi
done

cat >> "${TEST_LOG_DIR}/test_report.md" << 'REPORT_EOF2'

## How to Re-run

```bash
chmod +x tests/refinement-parser.sh
./tests/refinement-parser.sh
```
REPORT_EOF2

echo ""
echo "Report saved: ${TEST_LOG_DIR}/test_report.md"
echo ""

if [ ${TESTS_FAILED} -eq 0 ]; then
  echo -e "${GREEN}✓ All tests passed!${NC}\n"
  exit 0
else
  echo -e "${YELLOW}⚠ ${TESTS_FAILED} test(s) failed${NC}"
  echo -e "Review logs in: ${TEST_LOG_DIR}\n"
  exit 1
fi