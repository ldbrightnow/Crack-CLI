from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from crack.router import Router
from crack.state import MarkdownState


class RouterTests(unittest.TestCase):
    def make_state(self, root: Path) -> MarkdownState:
        (root / ".git").mkdir()
        return MarkdownState(root)

    def test_route_creates_new_plan(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            state = self.make_state(root)

            decision = Router(state).route(
                "Add router state files",
                branch_name="codex/router-state",
                plan_title="Router State",
                received_at="2026-05-09 12:00",
            )

            self.assertEqual(decision.action, "create_new_plan")
            plan_dir = root / ".crack" / "plans" / "codex-router-state"
            self.assertEqual(decision.target, plan_dir / "plan.md")
            self.assertTrue((plan_dir / "queue.md").exists())
            self.assertIn(
                "Branch: codex/router-state",
                (plan_dir / "plan.md").read_text(encoding="utf-8"),
            )

    def test_pr_lock_routes_prompt_to_inbox(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            state = self.make_state(root)
            state.set_pr_lock(
                pr_url="https://github.com/example/repo/pull/1",
                branch_name="codex/reviewing",
                reason="PR is reviewing.",
            )

            decision = Router(state).route(
                "Start another feature",
                received_at="2026-05-09 12:00",
            )

            self.assertEqual(decision.action, "pause_for_pr_review")
            inbox = (root / ".crack" / "inbox.md").read_text(encoding="utf-8")
            self.assertIn("> Start another feature", inbox)
            self.assertFalse((root / ".crack" / "plans" / "codex-start-another-feature").exists())

    def test_existing_plan_routes_prompt_to_queue(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            state = self.make_state(root)
            paths = state.create_plan(
                branch_name="codex/current",
                plan_title="Current",
                prompt="Initial request",
                reason="test setup",
                received_at="2026-05-09 12:00",
            )

            decision = Router(state).route(
                "Add dependent follow-up",
                plan_path=paths.directory,
                reason="Depends on current plan.",
                received_at="2026-05-09 12:05",
            )

            self.assertEqual(decision.action, "route_to_existing_plan")
            queue = paths.queue.read_text(encoding="utf-8")
            self.assertIn("> Add dependent follow-up", queue)
            self.assertIn("Depends on current plan.", queue)


if __name__ == "__main__":
    unittest.main()
