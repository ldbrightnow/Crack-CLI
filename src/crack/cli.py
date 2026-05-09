from __future__ import annotations

import argparse
from pathlib import Path
import sys

from .router import Router
from .state import MarkdownState, find_repo_root


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="crack")
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Repository root. Defaults to the nearest parent containing .git.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init", help="Create .crack state directories.")

    route = subparsers.add_parser("route", help="Route a new user prompt.")
    route.add_argument("prompt")
    route.add_argument("--plan", type=Path, help="Existing plan directory or plan.md.")
    route.add_argument("--branch", help="Branch name for a new plan.")
    route.add_argument("--title", help="Plan title for a new plan.")
    route.add_argument("--reason", help="Routing reason to write into Markdown.")

    lock = subparsers.add_parser("set-pr-lock", help="Pause new plans during PR review.")
    lock.add_argument("--branch", required=True)
    lock.add_argument("--pr-url", required=True)
    lock.add_argument("--reason", required=True)
    lock.add_argument("--status", default="reviewing")

    subparsers.add_parser("clear-pr-lock", help="Remove .crack/pr-lock.md.")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = args.root or find_repo_root()
    state = MarkdownState(root)

    if args.command == "init":
        state.initialize()
        print(f"initialized {state.crack_dir}")
        return 0

    if args.command == "route":
        decision = Router(state).route(
            args.prompt,
            plan_path=args.plan,
            branch_name=args.branch,
            plan_title=args.title,
            reason=args.reason,
        )
        print(f"{decision.action}: {decision.target}")
        return 0

    if args.command == "set-pr-lock":
        target = state.set_pr_lock(
            pr_url=args.pr_url,
            branch_name=args.branch,
            reason=args.reason,
            status=args.status,
        )
        print(f"set_pr_lock: {target}")
        return 0

    if args.command == "clear-pr-lock":
        removed = state.clear_pr_lock()
        print("clear_pr_lock: removed" if removed else "clear_pr_lock: no lock")
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
