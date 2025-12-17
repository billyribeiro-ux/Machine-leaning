#!/usr/bin/env python3
"""
Scanify API Server

Entry point for running the Scanify API server.
Can run standalone or integrated with the scanner engine.

Usage:
    # Development
    python scanify_server.py

    # Production
    python scanify_server.py --host 0.0.0.0 --port 8000 --workers 4

    # With scanner engine
    python scanify_server.py --with-scanner
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


def parse_args():
    parser = argparse.ArgumentParser(
        description="Scanify API Server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--host",
        default=os.getenv("SCANIFY_HOST", "127.0.0.1"),
        help="Host to bind to (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("SCANIFY_PORT", "8000")),
        help="Port to bind to (default: 8000)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Number of worker processes (default: 1, use 1 for WebSocket)",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for development",
    )
    parser.add_argument(
        "--with-scanner",
        action="store_true",
        help="Start with scanner engine integrated",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug mode",
    )

    return parser.parse_args()


async def init_scanner_engine():
    """Initialize and start the scanner engine"""
    try:
        from src.scanner.engine import ScannerEngine

        engine = ScannerEngine()
        await engine.start(continuous=True)
        return engine
    except ImportError as e:
        print(f"⚠️  Could not import scanner engine: {e}")
        return None
    except Exception as e:
        print(f"⚠️  Could not start scanner engine: {e}")
        return None


def main():
    args = parse_args()

    # Set debug env var
    if args.debug:
        os.environ["SCANIFY_DEBUG"] = "true"

    print("""
╔═══════════════════════════════════════════════════════════╗
║                                                           ║
║     ███████╗ ██████╗ █████╗ ███╗   ██╗██╗███████╗██╗   ██╗║
║     ██╔════╝██╔════╝██╔══██╗████╗  ██║██║██╔════╝╚██╗ ██╔╝║
║     ███████╗██║     ███████║██╔██╗ ██║██║█████╗   ╚████╔╝ ║
║     ╚════██║██║     ██╔══██║██║╚██╗██║██║██╔══╝    ╚██╔╝  ║
║     ███████║╚██████╗██║  ██║██║ ╚████║██║██║        ██║   ║
║     ╚══════╝ ╚═════╝╚═╝  ╚═╝╚═╝  ╚═══╝╚═╝╚═╝        ╚═╝   ║
║                                                           ║
║                    Trading Scanner API                    ║
╚═══════════════════════════════════════════════════════════╝
    """)

    print(f"🌐 Starting server on http://{args.host}:{args.port}")
    print(f"📚 API docs: http://{args.host}:{args.port}/api/docs")
    print(f"🔌 WebSocket: ws://{args.host}:{args.port}/ws/signals")

    if args.with_scanner:
        print("📡 Scanner engine: ENABLED")
    else:
        print("📡 Scanner engine: DISABLED (API only mode)")

    print()

    # Import uvicorn here to allow --help without dependencies
    import uvicorn

    # Initialize scanner if requested
    if args.with_scanner:
        # Run with scanner in same process
        async def run_with_scanner():
            engine = await init_scanner_engine()

            if engine:
                from src.api.main import set_scanner_engine
                set_scanner_engine(engine)
                print("✅ Scanner engine connected to API")

            # Run uvicorn in the same event loop
            config = uvicorn.Config(
                "src.api.main:app",
                host=args.host,
                port=args.port,
                reload=args.reload,
                workers=1,  # Must be 1 for shared scanner state
                log_level="info",
            )
            server = uvicorn.Server(config)
            await server.serve()

        asyncio.run(run_with_scanner())
    else:
        # Run API only
        uvicorn.run(
            "src.api.main:app",
            host=args.host,
            port=args.port,
            reload=args.reload,
            workers=args.workers,
            log_level="debug" if args.debug else "info",
        )


if __name__ == "__main__":
    main()
