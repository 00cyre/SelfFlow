import argparse
import asyncio

from .browser import PROFILE_DIR, FlowBrowser


def main() -> None:
    parser = argparse.ArgumentParser(prog="selfflow", description="Local API for Google Flow images")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--login", action="store_true", help="One-time visible Google sign-in, then exit")
    args = parser.parse_args()

    if args.login:
        print(f"Session profile: {PROFILE_DIR}", flush=True)
        asyncio.run(FlowBrowser().sign_in())
        return

    import uvicorn
    uvicorn.run("selfflow.api:app", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
