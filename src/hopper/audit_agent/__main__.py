"""Entry point: python -m hopper.audit_agent [--hopper-path PATH] [--once]"""

import argparse
import logging
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Hopper audit agent v0 — tag normalization and idea synthesis"
    )
    parser.add_argument(
        "--hopper-path",
        type=Path,
        default=Path.home() / ".hopper",
        help="Path to the .hopper directory (default: ~/.hopper)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run both jobs once then exit (useful for cron / systemd oneshot)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    hopper_path = args.hopper_path.expanduser().resolve()
    if not hopper_path.exists():
        print(f"ERROR: hopper path not found: {hopper_path}", file=sys.stderr)
        sys.exit(1)

    from hopper.audit_agent.agent import run_once, run_loop
    if args.once:
        run_once(hopper_path)
    else:
        run_loop(hopper_path)


if __name__ == "__main__":
    main()
