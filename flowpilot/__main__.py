import argparse
import uvicorn
from .api import create_app
from .config import load_local_env


def main():
    parser = argparse.ArgumentParser(
        description="FlowPilot local enterprise investigation console"
    )
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument(
        "--import-recordings",
        action="store_true",
        help="Load the five bundled live recordings as read-only replays before starting",
    )
    args = parser.parse_args()
    load_local_env()
    app = create_app()
    if args.import_recordings:
        from .catalog import ROOT
        from .recordings import import_recordings

        print(
            f"Imported {import_recordings(app.state.store, ROOT / 'examples' / 'traces')} recorded showcase(s); no model or tool execution."
        )
    uvicorn.run(app, host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
