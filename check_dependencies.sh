#!/bin/bash
# Integration Worker Dependency Checker
# Checks if upstream worker branches are ready for integration

set -e

echo "🔍 Integration Worker Dependency Checker"
echo "========================================"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Fetch latest from origin
echo "📡 Fetching latest changes..."
git fetch --all --quiet

# List of workers in dependency order
WORKERS=("project-setup" "database" "api-core" "routing-engine" "mcp-integration" "cli-tool" "testing")

# Initialization commit hash
INIT_COMMIT="ccc58d6"

echo ""
echo "📋 Worker Branch Status:"
echo "------------------------"

all_ready=true
workers_ready=0
total_workers=${#WORKERS[@]}

for worker in "${WORKERS[@]}"; do
    branch="cz1/feat/$worker"

    # Get the latest commit hash on the branch
    latest_commit=$(git log "$branch" --oneline --max-count=1 | awk '{print $1}')
    commit_count=$(git rev-list --count "$branch")

    # Check if branch has commits beyond initialization
    if [ "$commit_count" -gt 1 ]; then
        status="${GREEN}✅ Ready${NC}"
        workers_ready=$((workers_ready + 1))
    else
        status="${RED}❌ Not Started${NC}"
        all_ready=false
    fi

    echo -e "$branch: $status (commits: $commit_count)"
done

echo ""
echo "📊 Summary:"
echo "-----------"
echo "Workers ready: $workers_ready/$total_workers"

if [ "$all_ready" = true ]; then
    echo -e "${GREEN}✅ All dependencies ready! Integration can begin.${NC}"
    echo ""
    echo "Next steps:"
    echo "1. Review each worker's deliverables"
    echo "2. Begin merging in dependency order"
    echo "3. Test after each merge"
    exit 0
else
    echo -e "${YELLOW}⏸️  Waiting for workers to complete...${NC}"
    echo ""
    echo "Still waiting for:"
    for worker in "${WORKERS[@]}"; do
        branch="cz1/feat/$worker"
        commit_count=$(git rev-list --count "$branch")
        if [ "$commit_count" -le 1 ]; then
            echo "  - $worker"
        fi
    done
    exit 1
fi
