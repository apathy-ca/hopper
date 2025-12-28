#!/bin/bash
# Database reset script for testing

set -e

echo "⚠️  This will delete all data in the database!"
read -p "Are you sure you want to continue? (y/N) " -n 1 -r
echo

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "❌ Aborted"
    exit 1
fi

echo "🗑️  Resetting database..."

# Check if using Docker
if docker ps | grep -q hopper-postgres; then
    echo "🐳 Resetting PostgreSQL in Docker..."
    docker-compose down -v postgres
    docker-compose up -d postgres

    echo "⏳ Waiting for PostgreSQL to be ready..."
    sleep 5
else
    # Using SQLite
    if [ -f "hopper.db" ]; then
        echo "🗃️  Removing SQLite database..."
        rm hopper.db
    fi
fi

# Run migrations (when Alembic is set up)
# echo "🗄️  Running migrations..."
# alembic upgrade head

# Seed database (when seed script exists)
# echo "🌱 Seeding database..."
# python scripts/seed_db.py

echo "✅ Database reset complete!"
