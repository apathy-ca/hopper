#!/usr/bin/env bash
set -e

# Hopper Install Script
# Usage: curl -fsSL https://raw.githubusercontent.com/apathy-ca/hopper/master/install.sh | bash

REPO="https://github.com/apathy-ca/hopper.git"
INSTALL_DIR="${HOPPER_INSTALL_DIR:-$HOME/.hopper-install}"

echo "Installing Hopper..."

# Check Python version
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is required but not installed."
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)

if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 11 ]); then
    echo "Error: Python 3.11+ required. Found Python $PYTHON_VERSION"
    exit 1
fi

echo "✓ Python $PYTHON_VERSION"

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

# Install with pip
echo "Installing package..."
pip install -q -e .

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
    echo "You may need to add pip's bin directory to your PATH."
    echo ""
    echo "Try: export PATH=\"\$HOME/.local/bin:\$PATH\""
fi
