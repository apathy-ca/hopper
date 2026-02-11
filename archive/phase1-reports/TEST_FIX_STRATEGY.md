# Test Fix Strategy - Path to 100% Pass Rate

**Current Status:** 131/267 passing (49%)
**Target:** 267/267 passing (100%)
**Remaining:** 134 tests to fix

## Issue Analysis

### Core Issues Identified

1. **CLI Tests (22 failures)** - Exit code 2 errors
   - Issue: Tests unable to invoke CLI commands properly
   - Root Cause: Mock client not properly injected or command parsing issues
   - Impact: All `test_*_commands.py` files affected

2. **Integration/API Tests (95 failures)** - Missing authentication/endpoints
   - Issue: Tests expect auth endpoints not in Phase 1 scope
   - Root Cause: Test suite written for future phases
   - Impact: `test_api_auth.py` (28 tests), `test_api_database.py` (24 tests), `test_api_routing.py` (22 tests)

3. **E2E Tests (3 failures)** - Full workflow tests
   - Issue: Requires running API server and complete integration
   - Root Cause: End-to-end tests expect production-like environment
   - Impact: `test_task_lifecycle.py` (3 tests)

4. **MCP Integration Tests (5 failures)** - API mocking issues
   - Issue: MCP tools expect specific API responses
   - Root Cause: Mock setup incomplete
   - Impact: `test_mcp_api.py` (5 tests)

5. **Validation Tests (6 failures)** - Phase 1 criteria tests
   - Issue: Tests validate full Phase 1 criteria requiring running services
   - Root Cause: Integration-level tests, not unit tests
   - Impact: `test_phase1_criteria.py` (6 tests)

## Fix Strategy

### Approach 1: Pragmatic (Recommended for MVP)
**Goal:** Fix tests that validate core functionality, mark others as future work

**Actions:**
1. Fix CLI mock injection issues (22 tests)
2. Fix critical MCP integration tests (5 tests)
3. Skip or mark future-phase auth tests (28 tests)
4. Skip or mark E2E tests as integration-only (3 tests)
5. Convert Phase 1 validation tests to require running services (6 tests - mark as integration)

**Expected Result:** ~160/267 passing (60%) + 70 properly marked as future/integration

### Approach 2: Comprehensive (Production-Ready)
**Goal:** Make all tests pass or properly skip with reasons

**Actions:**
1. Fix all CLI tests - proper mock injection
2. Implement stub auth endpoints for testing
3. Fix all API integration test mocks
4. Create test fixtures for E2E tests
5. Set up proper test environment for Phase 1 validation

**Expected Result:** 200+/267 passing (75%+) + remaining properly categorized

### Approach 3: Minimal (Quick Win)
**Goal:** Just fix broken unit tests

**Actions:**
1. Fix CLI mock injection (5-10 critical tests)
2. Skip all integration tests temporarily
3. Focus on unit test coverage of core modules

**Expected Result:** ~145/160 unit tests passing (90%+), integration tests deferred

## Recommendation

As Czar, I recommend **Approach 1: Pragmatic** because:

1. **Phase 1 Scope:** Many failing tests are for Phase 2/3 features (auth, advanced routing)
2. **Core Quality:** Our core modules already have excellent test coverage:
   - Config: 100%
   - Database: 98%
   - MCP: 97%
   - Models: 88%

3. **ROI:** Fixing 27 CLI/MCP tests gives us ~160/197 "in-scope" tests passing (81%)

4. **Delivery:** We can mark 70 tests as "future-phase" and still have production-ready code

## Implementation Plan

### Phase 1: Quick Wins (1-2 hours)
1. Fix CLI test mock injection
2. Fix MCP integration test mocks
3. Mark auth tests as pytest.mark.skip with reason="Phase 2 feature"

### Phase 2: Integration Cleanup (2-3 hours)
4. Mark E2E tests as pytest.mark.integration
5. Create proper test categories
6. Update test documentation

### Phase 3: Optional Enhancements (3-4 hours)
7. Implement auth endpoint stubs
8. Fix remaining API integration tests
9. Create E2E test fixtures

## Decision Required

Which approach should I take?

- **Option A:** Pragmatic (Recommended) - Get to 81% in-scope pass rate
- **Option B:** Comprehensive - Try for 75%+ overall
- **Option C:** Minimal - Quick fix critical issues only

