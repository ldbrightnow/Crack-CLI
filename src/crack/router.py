from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .state import MarkdownState, slugify, title_from_prompt


RouteAction = Literal[
    "pause_for_pr_review",
    "route_to_existing_plan",
    "create_new_plan",
]


@dataclass(frozen=True)
class RouteDecision:
    action: RouteAction
    target: Path
    reason: str


class Router:
    def __init__(self, state: MarkdownState) -> None:
        self.state = state

    def route(
        self,
        prompt: str,
        *,
        plan_path: Path | str | None = None,
        branch_name: str | None = None,
        plan_title: str | None = None,
        reason: str | None = None,
        received_at: str | None = None,
    ) -> RouteDecision:
        self.state.initialize()

        if self.state.read_pr_lock() is not None:
            route_reason = reason or "PR review lock is active, so new requests are paused."
            target = self.state.append_inbox(prompt, route_reason, received_at)
            return RouteDecision("pause_for_pr_review", target, route_reason)

        if plan_path is not None:
            route_reason = reason or "Caller selected an existing active plan."
            target = self.state.append_queue(plan_path, prompt, route_reason, received_at)
            return RouteDecision("route_to_existing_plan", target, route_reason)

        title = plan_title or title_from_prompt(prompt)
        branch = branch_name or f"codex/{slugify(title).lower()}"
        route_reason = reason or "No PR lock or selected active plan; created a new plan."
        paths = self.state.create_plan(branch, title, prompt, route_reason, received_at)
        return RouteDecision("create_new_plan", paths.plan, route_reason)
