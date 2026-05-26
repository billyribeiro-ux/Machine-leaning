# Scanify Setup Guide

Complete guide to deploying Scanify as a desktop app and web service.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    SCANIFY PLATFORM                          │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │           Python Backend (FastAPI)                    │   │
│  │  • Scanner Engine (ML-powered signal generation)      │   │
│  │  • REST API (/api/*)                                  │   │
│  │  • WebSocket (/ws/signals)                            │   │
│  │  • JWT Auth with Tier-based Access                    │   │
│  └──────────────────────────────────────────────────────┘   │
│                           │                                  │
│            ┌──────────────┴──────────────┐                  │
│            ▼                              ▼                  │
│  ┌─────────────────┐           ┌─────────────────┐          │
│  │  Desktop App    │           │  Browser App    │          │
│  │  (Tauri v2)     │           │  (SvelteKit)    │          │
│  │                 │           │                 │          │
│  │  • Your screen  │           │  • Subscribers  │          │
│  │  • System tray  │           │  • Login/Auth   │          │
│  │  • Notifications│           │  • Stripe       │          │
│  └─────────────────┘           └─────────────────┘          │
│          └──────────── same codebase ────────────┘          │
│                      (scanify/)                              │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## Quick Start

### 1. Start the API Server

```bash
# From project root
cd /path/to/Machine-leaning

# Install Python dependencies
pip install -r requirements.txt

# Start API server (without scanner)
python scanify_server.py

# OR start with scanner engine
python scanify_server.py --with-scanner

# API available at:
# - http://localhost:8000/api/docs (Swagger UI)
# - ws://localhost:8000/ws/signals (WebSocket)
```

### 2. Run Desktop App (For Screen Sharing)

```bash
cd scanify

# Install dependencies
pnpm install

# Development mode
pnpm tauri:dev

# Build for distribution
pnpm tauri:build
# Output: src-tauri/target/release/bundle/
```

### 3. Run Browser App (For Subscribers)

```bash
cd scanify

# Install dependencies
pnpm install

# Development
pnpm dev
# Available at http://localhost:5173

# Production build
pnpm build
pnpm preview
```

## Detailed Setup

### Prerequisites

| Component | Requirement |
|-----------|-------------|
| Python | 3.11+ |
| Node.js | 18+ |
| Rust | Latest stable (for Tauri) |
| pnpm | 10+ |

### Environment Variables

Create a `.env` file in the project root:

```env
# API Server
SCANIFY_SECRET_KEY=your-super-secret-jwt-key-change-this
SCANIFY_ADMIN_KEY=your-admin-key
SCANIFY_HOST=0.0.0.0
SCANIFY_PORT=8000
SCANIFY_DEBUG=false

# Data Providers (for scanner)
POLYGON_API_KEY=your_polygon_key
ALPACA_API_KEY=your_alpaca_key
ALPACA_SECRET_KEY=your_alpaca_secret

# CORS (comma-separated origins)
SCANIFY_CORS_ORIGINS=http://localhost:5173,https://yourdomain.com
```

### Desktop App Configuration

Edit `scanify/src-tauri/tauri.conf.json`:

```json
{
  "productName": "Scanify",
  "version": "1.0.0",
  "identifier": "com.scanify.app",
  "bundle": {
    "icon": [...]
  }
}
```

### Build Desktop App for Distribution

```bash
cd scanify

# macOS
pnpm tauri:build
# Output: src-tauri/target/release/bundle/dmg/Scanify.dmg

# Windows
pnpm tauri:build
# Output: src-tauri/target/release/bundle/msi/Scanify.msi

# Linux
pnpm tauri:build
# Output: src-tauri/target/release/bundle/appimage/Scanify.AppImage
```

## Subscription Tiers

| Tier | Price | Features |
|------|-------|----------|
| **Free** | $0 | 15-min delay, Momentum scanner only, 5 symbols |
| **Basic** | $29/mo | 1-min delay, 3 scanners, 25 symbols, Email alerts |
| **Pro** | $99/mo | Real-time, All 7 scanners, WebSocket, 100 symbols |
| **Elite** | $299/mo | Everything + API access, Unlimited symbols, Priority support |

## API Endpoints

### Authentication
- `POST /api/auth/register` - Create account
- `POST /api/auth/login` - Login
- `GET /api/auth/me` - Get profile
- `POST /api/auth/refresh` - Refresh token

### Signals
- `GET /api/signals/latest` - Get latest signals
- `GET /api/signals/symbol/{symbol}` - Signals for specific symbol
- `GET /api/signals/scanners` - Scanner statistics

### Alerts
- `GET /api/alerts` - Get alerts
- `GET /api/alerts/count` - Alert count
- `POST /api/alerts/rules` - Create alert rule (PRO+)

### Status
- `GET /health` - Health check
- `GET /api/status/` - Full system status
- `GET /api/status/markets` - Market status

### Admin
- `GET /api/admin/users` - List users
- `PUT /api/admin/users/{id}/tier` - Update user tier
- `GET /api/admin/metrics` - System metrics

### WebSocket
- `ws://host/ws/signals?token=JWT_TOKEN` - Real-time signals (PRO+)

## Deployment

### Production API (Docker)

```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
CMD ["python", "scanify_server.py", "--host", "0.0.0.0", "--with-scanner"]
```

```bash
docker build -t scanify-api .
docker run -p 8000:8000 --env-file .env scanify-api
```

### Production Web (Vercel/Cloudflare)

```bash
cd scanify
pnpm build
# Deploy the .svelte-kit/cloudflare output
```

### Production Desktop (Distribution)

1. Build for each platform
2. Code sign (macOS: Apple Developer, Windows: Code signing cert)
3. Distribute via:
   - Direct download from your website
   - macOS: App Store (optional)
   - Windows: Microsoft Store (optional)
   - Linux: Snap/Flatpak (optional)

## Running Your Screen Share Session

1. Start the API server with scanner:
   ```bash
   python scanify_server.py --with-scanner
   ```

2. Launch the desktop app:
   ```bash
   cd scanify && pnpm tauri:dev
   ```

3. Login as admin (create via API):
   ```bash
   curl -X POST "http://localhost:8000/api/auth/admin/create-user" \
     -H "Content-Type: application/json" \
     -d '{"email":"admin@scanify.app","password":"secure123","tier":"admin","admin_key":"your-admin-key"}'
   ```

4. Share your screen with members - they see the live scanner dashboard!

## Adding Stripe Payments

1. Create products in Stripe Dashboard for each tier
2. Add Stripe checkout to the web app
3. Set up webhooks to handle subscription changes
4. Update user tier in database when subscription status changes

## Support

- Documentation: `docs/`
- Issues: Report bugs on GitHub
- Email: support@scanify.app
