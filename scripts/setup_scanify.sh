#!/bin/bash
# Scanify Setup Script
# Sets up all components of the Scanify platform

set -e

echo "╔═══════════════════════════════════════════════════════════╗"
echo "║                   SCANIFY SETUP                           ║"
echo "╚═══════════════════════════════════════════════════════════╝"
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"

echo -e "${YELLOW}Project root: ${PROJECT_ROOT}${NC}"
echo ""

# Check prerequisites
echo "Checking prerequisites..."

# Python
if command -v python3.11 &> /dev/null; then
    PYTHON="python3.11"
elif command -v python3 &> /dev/null; then
    PYTHON="python3"
else
    echo "Error: Python 3.11+ is required"
    exit 1
fi
echo -e "${GREEN}✓ Python: $($PYTHON --version)${NC}"

# Node.js
if command -v node &> /dev/null; then
    echo -e "${GREEN}✓ Node.js: $(node --version)${NC}"
else
    echo "Error: Node.js is required"
    exit 1
fi

# Rust (optional, for desktop app)
if command -v rustc &> /dev/null; then
    echo -e "${GREEN}✓ Rust: $(rustc --version)${NC}"
else
    echo -e "${YELLOW}! Rust not found (optional, needed for desktop app)${NC}"
fi

echo ""

# Setup Python environment
echo "Setting up Python environment..."
cd "$PROJECT_ROOT"

if [ ! -d "venv" ]; then
    $PYTHON -m venv venv
    echo -e "${GREEN}✓ Created virtual environment${NC}"
fi

source venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo -e "${GREEN}✓ Installed Python dependencies${NC}"

# Setup desktop app
echo ""
echo "Setting up desktop app..."
cd "$PROJECT_ROOT/desktop"

if [ -f "package.json" ]; then
    npm install --silent
    echo -e "${GREEN}✓ Installed desktop dependencies${NC}"
else
    echo -e "${YELLOW}! Desktop package.json not found, skipping${NC}"
fi

# Setup web app
echo ""
echo "Setting up web app..."
cd "$PROJECT_ROOT/web"

if [ -f "package.json" ]; then
    npm install --silent
    echo -e "${GREEN}✓ Installed web dependencies${NC}"
else
    echo -e "${YELLOW}! Web package.json not found, skipping${NC}"
fi

# Create .env if not exists
cd "$PROJECT_ROOT"
if [ ! -f ".env" ]; then
    cat > .env << 'EOF'
# Scanify Configuration
SCANIFY_SECRET_KEY=change-this-to-a-secure-random-string
SCANIFY_ADMIN_KEY=admin-key-change-this
SCANIFY_HOST=127.0.0.1
SCANIFY_PORT=8000
SCANIFY_DEBUG=true

# Data Providers (get keys from respective providers)
POLYGON_API_KEY=your_polygon_key
ALPACA_API_KEY=your_alpaca_key
ALPACA_SECRET_KEY=your_alpaca_secret
EOF
    echo -e "${GREEN}✓ Created .env file (edit with your API keys)${NC}"
else
    echo -e "${GREEN}✓ .env file exists${NC}"
fi

echo ""
echo "═══════════════════════════════════════════════════════════"
echo -e "${GREEN}Setup complete!${NC}"
echo ""
echo "Next steps:"
echo ""
echo "1. Edit .env with your API keys"
echo ""
echo "2. Start the API server:"
echo "   source venv/bin/activate"
echo "   python scanify_server.py --with-scanner"
echo ""
echo "3. Start desktop app (in new terminal):"
echo "   cd desktop && npm run tauri:dev"
echo ""
echo "4. Start web app (in new terminal):"
echo "   cd web && npm run dev"
echo ""
echo "API Docs: http://localhost:8000/api/docs"
echo "Web App:  http://localhost:3000"
echo "═══════════════════════════════════════════════════════════"
