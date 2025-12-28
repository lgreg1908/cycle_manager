#!/bin/bash

# Reset Database Script
# This script completely resets the database by:
# 1. Stopping containers and removing volumes
# 2. Starting fresh containers
# 3. Running migrations
# 4. Seeding dev data

set -e  # Exit on error

echo "🔄 Resetting database..."
echo ""

# Step 1: Stop containers and remove volumes
echo "Step 1: Stopping containers and removing volumes..."
if command -v docker-compose &> /dev/null; then
    docker-compose down -v
else
    docker compose down -v
fi
echo "✅ Containers stopped and volumes removed"
echo ""

# Step 2: Start containers
echo "Step 2: Starting containers..."
if command -v docker-compose &> /dev/null; then
    docker-compose up -d
else
    docker compose up -d
fi
echo "✅ Containers started"
echo "⏳ Waiting for database to be ready..."
sleep 3

# Wait for database to be ready (max 30 seconds)
MAX_ATTEMPTS=30
ATTEMPT=0
while [ $ATTEMPT -lt $MAX_ATTEMPTS ]; do
    if docker exec hr_postgres pg_isready -U hr_app -d hr_platform > /dev/null 2>&1; then
        echo "✅ Database is ready!"
        break
    fi
    ATTEMPT=$((ATTEMPT + 1))
    echo "   Waiting... ($ATTEMPT/$MAX_ATTEMPTS)"
    sleep 1
done

if [ $ATTEMPT -eq $MAX_ATTEMPTS ]; then
    echo "❌ Database did not become ready in time"
    exit 1
fi

echo ""

# Step 3: Activate virtual environment and run migrations
echo "Step 3: Running migrations..."
if [ -d ".venv" ]; then
    source .venv/bin/activate
else
    echo "⚠️  Warning: .venv not found. Make sure you're in the project root and have activated your virtual environment."
fi

alembic upgrade head
echo "✅ Migrations completed"
echo ""

# Step 4: Seed dev data
echo "Step 4: Seeding dev data..."
PYTHONPATH=$(pwd) python scripts/seed_dev.py
echo "✅ Dev data seeded"
echo ""

echo "✅ Database reset complete!"
echo ""
echo "Your database is now clean with:"
echo "  ✅ Fresh schema (all migrations applied)"
echo "  ✅ Dev seed data (users, employees, roles, forms, cycles, assignments)"
echo ""
echo "You can now:"
echo "  1. Restart your API server: uvicorn app.main:app --reload"
echo "  2. Run your Postman collection"
echo "  3. Start fresh with clean data"

