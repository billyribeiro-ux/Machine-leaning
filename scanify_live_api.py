"""Local launcher: load .env and serve the SCANIFY API with a thread pool
big enough that /health stays responsive while data endpoints block on I/O."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

import anyio
from src.scanify.api.app import create_app

app = create_app()

if __name__ == "__main__":
    import uvicorn
    # Bump the AnyIO worker-thread cap so blocking sync calls in async
    # endpoints don't starve lightweight routes like /health.
    os.environ.setdefault("ANYIO_TOTAL_TOKENS", "64")
    uvicorn.run("scanify_live_api:app", host="0.0.0.0", port=8000,
                workers=4, log_level="warning")
