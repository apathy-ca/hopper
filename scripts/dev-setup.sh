#!/bin/bash
# Development environment setup script

set -e

echo "🚀 Setting up Hopper development environment..."

# Check if Python 3.11+ is available
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3.11 or higher."
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
REQUIRED_VERSION="3.11"

if [ "$(printf '%s\n' "$REQUIRED_VERSION" "$PYTHON_VERSION" | sort -V | head -n1)" != "$REQUIRED_VERSION" ]; then
    echo "❌ Python version $PYTHON_VERSION is too old. Please install Python 3.11 or higher."
    exit 1
fi

echo "✅ Python $PYTHON_VERSION found"

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
else
    echo "✅ Virtual environment already exists"
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo "⬆️  Upgrading pip..."
pip install --upgrade pip

# Install package in development mode
echo "📥 Installing Hopper in development mode..."
pip install -e ".[dev]"

# Create .env file if it doesn't exist
if [ ! -f ".env" ]; then
    echo "📝 Creating .env file from template..."
    cp .env.template .env
    echo "⚠️  Please edit .env and set your configuration values"
else
    echo "✅ .env file already exists"
fi

# Check if Docker is running
if command -v docker &> /dev/null && docker info &> /dev/null; then
    echo "🐳 Starting Docker services..."
    docker-compose up -d postgres redis

    echo "⏳ Waiting for PostgreSQL to be ready..."
    sleep 5

    # Run database migrations (when Alembic is set up)
    # echo "🗄️  Running database migrations..."
    # alembic upgrade head

    echo "✅ Docker services started"
else
    echo "⚠️  Docker is not running. Please start Docker to use PostgreSQL and Redis."
    echo "   Alternatively, you can use SQLite by setting DATABASE_URL in .env:"
    echo "   DATABASE_URL=sqlite:///./hopper.db"
fi

echo ""
echo "✅ Development environment setup complete!"
echo ""
echo "Next steps:"
echo "  1. Activate the virtual environment: source venv/bin/activate"
echo "  2. Edit .env and configure your settings"
echo "  3. Run tests: pytest"
echo "  4. Start the API server: uvicorn hopper.api.main:app --reload"
echo ""
echo "Happy coding! 🎉"
