"""
WhatsApp Bulk Messenger Pro - Modern Web Dashboard Server Launcher.
Starts the FastAPI ASGI application on 127.0.0.1:8000 and automatically
launches the user's default web browser.
"""

import sys
import time
import argparse
import webbrowser
import threading
import uvicorn

from logger import get_logger

logger = get_logger("WebLauncher")


def open_browser_delayed(url: str, delay: float = 1.2):
    """Opens the web dashboard in the default browser after server initializes."""
    time.sleep(delay)
    try:
        webbrowser.open(url)
    except Exception as e:
        logger.warning(f"Could not open browser automatically: {e}")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="WhatsApp Bulk Messenger Pro - Modern Web Dashboard")
    parser.add_argument("--host", default="127.0.0.1", help="Host address to bind (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on (default: 8000)")
    parser.add_argument("--no-browser", action="store_true", help="Do not open browser automatically on launch")
    parser.add_argument("--reload", action="store_true", help="Enable uvicorn auto-reload for development")

    args = parser.parse_args()

    url = f"http://{args.host}:{args.port}"
    print("=" * 65)
    print("  [LAUNCH] WhatsApp Bulk Messenger Pro - Web Dashboard v2.0")
    print("=" * 65)
    print(f"  * Server URL      : {url}")
    print(f"  * Interactive Docs: {url}/api/docs")
    print(f"  * Binding Host    : {args.host} (Local Isolated)")
    print(f"  * Press Ctrl+C to stop the web server")
    print("=" * 65)

    if not args.no_browser:
        threading.Thread(target=open_browser_delayed, args=(url,), daemon=True).start()

    try:
        uvicorn.run(
            "backend.app:app",
            host=args.host,
            port=args.port,
            reload=args.reload,
            log_level="info"
        )
    except KeyboardInterrupt:
        print("\n[INFO] Web dashboard server stopped by operator.")
    except Exception as e:
        print(f"\n[ERROR] Server failed to start: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

