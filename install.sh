#!/usr/bin/env bash
set -e

# Hopper Install Script
# Usage: curl -fsSL https://raw.githubusercontent.com/apathy-ca/hopper/master/install.sh | bash

REPO="https://github.com/apathy-ca/hopper.git"
INSTALL_DIR="${HOPPER_INSTALL_DIR:-$HOME/.hopper-install}"

echo "Installing Hopper..."

# Check uv
if ! command -v uv &> /dev/null; then
    echo "Error: uv is required but not installed."
    echo "Install it with: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

echo "✓ uv $(uv --version)"

# Clone or update repo
if [ -d "$INSTALL_DIR" ]; then
    echo "Updating existing installation..."
    cd "$INSTALL_DIR"
    git pull --quiet
else
    echo "Cloning Hopper..."
    git clone --quiet "$REPO" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

# Install with uv
echo "Installing package..."
uv pip install -q -e .

# Verify installation
if command -v hopper &> /dev/null; then
    echo ""
    echo "✓ Hopper installed successfully!"
    echo ""
    echo "Quick start:"
    echo "  cd /your/project"
    echo "  hopper init"
    echo "  hopper --local task add \"My first task\""
    echo ""
    echo "For AI agents, copy these files to your project:"
    echo "  cp $INSTALL_DIR/CLAUDE.md ."
    echo "  cp -r $INSTALL_DIR/.claude/skills .claude/"
    echo ""
else
    echo ""
    echo "Installed, but 'hopper' not in PATH."
    echo "You may need to add uv's bin directory to your PATH."
    echo ""
    echo "Try: export PATH=\"\$HOME/.local/bin:\$PATH\""
fi
