from __future__ import annotations

import argparse
import sys

from . import __version__
from .bridge import create_stage, mentors_incremental


def _add_common_mentor_flags(p: argparse.ArgumentParser) -> None:
    p.add_argument("stage", type=int, help="Stage number, e.g., 3 for stage-3")
    p.add_argument("--dry-run", action="store_true", help="Show what would change without calling Slack")
    p.add_argument("--process-all", action="store_true", help="Process all rows regardless of saved baseline")
    p.add_argument("--since-minutes", type=int, default=None, help="Process rows newer than now minus these minutes (overrides baseline)")
    p.add_argument("--reset-baseline", action="store_true", help="Clear saved baseline for the latest worksheet and exit")
    p.add_argument("--show-baseline", action="store_true", help="Show the current baseline and the matching row(s), then exit")
    p.add_argument("--show-newest", action="store_true", help="Show the newest rows by Timestamp (top 10) with row numbers, then exit")
    p.add_argument("--list-new", action="store_true", help="List rows newer than the baseline (what would be processed), then exit")
    p.add_argument("--baseline-mode", choices=["timestamp", "row"], default="timestamp", help="Use 'timestamp' or 'row' for incremental baseline tracking")


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    parser = argparse.ArgumentParser(
        prog="slack-stage-manager",
        description="Unified CLI for stage channel creation and mentor additions.",
    )
    parser.add_argument("--version", action="version", version=f"slack-stage-manager {__version__}")

    sub = parser.add_subparsers(dest="cmd", required=True)

    # create-stage
    p_create = sub.add_parser("create-stage", help="Create stage + track channels and add leads + mentors")
    p_create.add_argument("stage", type=int, help="Stage number, e.g., 4 for stage-4")

    # mentors (incremental with flags)
    p_mentors = sub.add_parser("mentors", help="Incrementally add mentors from latest worksheet")
    _add_common_mentor_flags(p_mentors)

    args = parser.parse_args(argv)

    if args.cmd == "create-stage":
        print(f"🚀 create-stage: stage-{args.stage}")
        create_stage(args.stage)
        print("\n✅ Done (create-stage)")
        return 0

    if args.cmd == "mentors":
        print(f"🚀 mentors (incremental): stage-{args.stage}")
        mentors_incremental(
            args.stage,
            dry_run=args.dry_run,
            process_all=args.process_all,
            since_minutes=args.since_minutes,
            reset_baseline=args.reset_baseline,
            show_baseline=args.show_baseline,
            show_newest=args.show_newest,
            list_new=args.list_new,
            baseline_mode=args.baseline_mode,
        )
        print("\n✅ Done (mentors)")
        return 0

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
