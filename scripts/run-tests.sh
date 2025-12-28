#!/bin/bash
# Test runner script

set -e

echo "🧪 Running Hopper test suite..."

# Activate virtual environment if not already active
if [ -z "$VIRTUAL_ENV" ]; then
    if [ -f "venv/bin/activate" ]; then
        echo "🔧 Activating virtual environment..."
        source venv/bin/activate
    else
        echo "❌ Virtual environment not found. Run scripts/dev-setup.sh first."
        exit 1
    fi
fi

# Default to running all tests
TEST_PATH=${1:-tests/}

# Parse arguments
COVERAGE=true
VERBOSE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --no-cov)
            COVERAGE=false
            shift
            ;;
        -v|--verbose)
            VERBOSE=true
            shift
            ;;
        *)
            TEST_PATH="$1"
            shift
            ;;
    esac
done

# Build pytest command
PYTEST_CMD="pytest"

if [ "$COVERAGE" = true ]; then
    PYTEST_CMD="$PYTEST_CMD --cov=hopper --cov-report=term-missing --cov-report=html"
fi

if [ "$VERBOSE" = true ]; then
    PYTEST_CMD="$PYTEST_CMD -v"
fi

PYTEST_CMD="$PYTEST_CMD $TEST_PATH"

echo "Running: $PYTEST_CMD"
echo ""

# Run tests
eval $PYTEST_CMD

# Report coverage
if [ "$COVERAGE" = true ]; then
    echo ""
    echo "📊 Coverage report generated in htmlcov/"
    echo "   Open htmlcov/index.html in a browser to view"
fi

echo ""
echo "✅ Tests complete!"
