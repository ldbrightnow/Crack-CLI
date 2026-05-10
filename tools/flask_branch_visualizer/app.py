from __future__ import annotations

import argparse
import shlex
import sys
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template_string, request

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from tools.flask_branch_visualizer.actions import ActionError, run_action
    from tools.flask_branch_visualizer.state import find_repo_root, read_repository_snapshot
else:
    from .actions import ActionError, run_action
    from .state import find_repo_root, read_repository_snapshot


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 5050
DEFAULT_WEB_MAX_COMMITS = 12

PAGE_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Crack Branch Visualizer</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f6f8f7;
      --panel: #ffffff;
      --panel-muted: #eef4f1;
      --ink: #17201c;
      --muted: #60716a;
      --line: #d8e0dc;
      --accent: #23735a;
      --accent-strong: #16513e;
      --warn: #9a5a20;
      --danger: #9c3f3a;
    }

    * {
      box-sizing: border-box;
    }

    body {
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      font-size: 15px;
      line-height: 1.5;
    }

    .shell {
      width: min(1120px, calc(100% - 32px));
      margin: 0 auto;
      padding: 24px 0 40px;
    }

    .topbar {
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(280px, 480px);
      gap: 20px;
      align-items: start;
      padding-bottom: 18px;
      border-bottom: 1px solid var(--line);
    }

    h1,
    h2,
    h3,
    p {
      margin-top: 0;
    }

    h1 {
      margin-bottom: 8px;
      font-size: 1.9rem;
      line-height: 1.15;
    }

    h2 {
      margin-bottom: 12px;
      font-size: 0.82rem;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }

    h3 {
      margin-bottom: 4px;
      font-size: 1rem;
    }

    .muted,
    .meta,
    .label {
      color: var(--muted);
      font-size: 0.88rem;
    }

    .summary,
    .notice,
    .card,
    .timeline-item {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
    }

    .summary {
      display: grid;
      grid-template-columns: auto minmax(0, 1fr);
      gap: 6px 14px;
      padding: 14px;
    }

    .summary strong,
    code,
    .refs {
      overflow-wrap: anywhere;
      word-break: break-word;
    }

    .notice {
      margin-top: 16px;
      padding: 14px;
    }

    .notice.warning {
      border-color: rgba(156, 63, 58, 0.35);
      color: var(--danger);
    }

    .notice ul {
      margin: 8px 0 0;
      padding-left: 18px;
    }

    .section {
      padding-top: 24px;
    }

    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 12px;
    }

    .card,
    .timeline-item {
      padding: 14px;
    }

    .card.current {
      border-color: rgba(35, 115, 90, 0.58);
    }

    .card-head {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 12px;
    }

    .pill {
      align-self: flex-start;
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 2px 8px;
      color: var(--muted);
      font-size: 0.74rem;
      font-weight: 700;
      white-space: nowrap;
    }

    .pill.current {
      border-color: rgba(35, 115, 90, 0.45);
      color: var(--accent-strong);
    }

    .metrics {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 8px;
      margin: 12px 0;
    }

    .metric {
      min-width: 0;
      padding: 8px;
      border-radius: 6px;
      background: var(--panel-muted);
    }

    .metric-value {
      display: block;
      font-weight: 800;
    }

    .progress {
      height: 7px;
      overflow: hidden;
      border-radius: 999px;
      background: var(--panel-muted);
    }

    .progress span {
      display: block;
      height: 100%;
      background: var(--accent);
    }

    code {
      display: block;
      padding: 9px 10px;
      border-radius: 6px;
      background: #1f2723;
      color: #f6fbf8;
      font-size: 0.84rem;
    }

    .hash {
      color: var(--accent-strong);
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
      font-weight: 800;
    }

    .subject {
      margin-bottom: 6px;
      font-weight: 700;
    }

    .timeline {
      display: grid;
      gap: 10px;
    }

    .timeline-item {
      display: grid;
      grid-template-columns: 112px minmax(0, 1fr);
      gap: 14px;
    }

    .refs {
      color: var(--warn);
      font-size: 0.86rem;
    }

    @media (max-width: 760px) {
      .shell {
        width: min(100% - 20px, 1120px);
        padding-top: 16px;
      }

      .topbar,
      .summary,
      .timeline-item {
        grid-template-columns: 1fr;
      }

      .metrics {
        grid-template-columns: 1fr;
      }
    }
  </style>
</head>
<body>
  <main class="shell">
    <header class="topbar">
      <div>
        <h1>Crack Branch Visualizer</h1>
        <p class="muted">Local read-only view of Markdown workflow state and git history.</p>
      </div>
      <div class="summary" aria-label="Repository summary">
        <span class="label">Repository</span>
        <strong>{{ snapshot.repo_root }}</strong>
        <span class="label">Current branch</span>
        <strong>{{ snapshot.git.current_branch or "detached or unknown" }}</strong>
      </div>
    </header>

    {% if snapshot.warnings %}
      <section class="notice warning" aria-label="Warnings">
        <strong>Warnings</strong>
        <ul>
          {% for warning in snapshot.warnings %}
            <li>{{ warning }}</li>
          {% endfor %}
        </ul>
      </section>
    {% endif %}

    {% if not snapshot.initialized %}
      <section class="notice">
        <h2>No .crack State Found</h2>
        <p class="muted">This repository has no readable <strong>.crack/</strong> directory yet. Git branches and recent commits are still shown when available.</p>
      </section>
    {% else %}
      <section class="section" aria-labelledby="plans-heading">
        <h2 id="plans-heading">Crack Plans</h2>
        {% if snapshot.plans %}
          <div class="grid">
            {% for plan in snapshot.plans %}
              <article class="card">
                <div class="card-head">
                  <div>
                    <h3>{{ plan.title }}</h3>
                    <p class="meta">{{ plan.branch }}</p>
                  </div>
                  <span class="pill">{{ plan.queue_request_count }} queued</span>
                </div>
                <div class="progress" aria-label="Plan progress">
                  <span style="width: {{ progress_percent(plan) }}%"></span>
                </div>
                <div class="metrics">
                  <div class="metric">
                    <span class="metric-value">{{ plan.completed_commit_unit_count }}/{{ plan.total_commit_unit_count }}</span>
                    <span class="label">commit units</span>
                  </div>
                  <div class="metric">
                    <span class="metric-value">{{ progress_percent(plan) }}%</span>
                    <span class="label">complete</span>
                  </div>
                  <div class="metric">
                    <span class="metric-value">{{ plan.queue_request_count }}</span>
                    <span class="label">queue</span>
                  </div>
                </div>
                <p><strong>Next:</strong> {{ next_commit_text(plan) }}</p>
                <code>{{ run_command(plan) }}</code>
              </article>
            {% endfor %}
          </div>
        {% else %}
          <p class="muted">No plan files were found under <strong>.crack/plans/</strong>.</p>
        {% endif %}
      </section>
    {% endif %}

    <section class="section" aria-labelledby="branches-heading">
      <h2 id="branches-heading">Local Branches</h2>
      {% if snapshot.git.branches %}
        <div class="grid">
          {% for branch in snapshot.git.branches %}
            <article class="card{% if branch.name == snapshot.git.current_branch %} current{% endif %}">
              <div class="card-head">
                <h3>{{ branch.name }}</h3>
                {% if branch.name == snapshot.git.current_branch %}
                  <span class="pill current">current</span>
                {% endif %}
              </div>
              <p><span class="hash">{{ branch.short_hash or "no hash" }}</span></p>
              <p class="subject">{{ branch.subject or "No commit subject" }}</p>
              <p class="meta">{{ branch.committed_at or "No commit date" }}</p>
            </article>
          {% endfor %}
        </div>
      {% else %}
        <p class="muted">No local branch data found.</p>
      {% endif %}
    </section>

    <section class="section" aria-labelledby="commits-heading">
      <h2 id="commits-heading">Recent Commits</h2>
      {% if snapshot.git.recent_commits %}
        <div class="timeline">
          {% for commit in snapshot.git.recent_commits %}
            <article class="timeline-item">
              <div>
                <div class="hash">{{ commit.short_hash }}</div>
                <div class="refs">{{ commit.refs or "no decorations" }}</div>
              </div>
              <div>
                <p class="subject">{{ commit.subject or "No commit subject" }}</p>
                <p class="meta">{{ commit.author or "Unknown author" }} &middot; {{ commit.committed_at or "No commit date" }}</p>
              </div>
            </article>
          {% endfor %}
        </div>
      {% else %}
        <p class="muted">No recent commits found.</p>
      {% endif %}
    </section>
  </main>
</body>
</html>
"""


def create_app(repo_path: str | Path | None = None, max_commits: int = DEFAULT_WEB_MAX_COMMITS) -> Flask:
    repo_root = find_repo_root(repo_path)
    app = Flask(__name__)
    app.config["REPO_ROOT"] = repo_root
    app.config["MAX_COMMITS"] = max_commits

    app.jinja_env.globals.update(
        next_commit_text=next_commit_text,
        progress_percent=progress_percent,
        run_command=run_command,
    )

    @app.get("/")
    def index() -> str:
        snapshot = read_repository_snapshot(repo_root, max_commits)
        return render_template_string(PAGE_TEMPLATE, snapshot=snapshot)

    @app.get("/api/state")
    def api_state() -> Any:
        snapshot = read_repository_snapshot(repo_root, max_commits)
        return jsonify(snapshot)

    @app.post("/api/actions")
    def api_actions() -> Any:
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify({"error": "JSON body must be an object."}), 400

        plan_path = payload.get("plan_path")
        if plan_path is None:
            plan_path = payload.get("planPath")

        try:
            result = run_action(payload.get("action") or payload.get("name"), repo_root, plan_path)
        except ActionError as error:
            return jsonify({"error": str(error)}), 400

        response = result.to_dict()
        response["snapshot"] = read_repository_snapshot(repo_root, max_commits)
        return jsonify(response)

    return app


def progress_percent(plan: dict[str, Any]) -> int:
    total = int(plan.get("total_commit_unit_count") or 0)
    completed = int(plan.get("completed_commit_unit_count") or 0)
    if total <= 0:
        return 0

    return max(0, min(100, round((completed / total) * 100)))


def next_commit_text(plan: dict[str, Any]) -> str:
    next_unit = plan.get("next_commit_unit")
    if not next_unit:
        return "Plan complete"

    number = next_unit.get("number", "?")
    title = next_unit.get("title") or "Untitled commit unit"
    return f"Commit {number}: {title}"


def run_command(plan: dict[str, Any]) -> str:
    plan_path = plan.get("relative_plan_path") or plan.get("plan_path")
    if not plan_path:
        return "crack run-all"

    return f"crack run-all --plan {shlex.quote(str(plan_path))}"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the local Crack branch visualizer.")
    parser.add_argument("--repo", default=None, help="Repository root to visualize. Defaults to the nearest git root.")
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"Host to bind. Defaults to {DEFAULT_HOST}.")
    parser.add_argument("--port", default=DEFAULT_PORT, type=int, help=f"Port to bind. Defaults to {DEFAULT_PORT}.")
    parser.add_argument(
        "--max-commits",
        default=DEFAULT_WEB_MAX_COMMITS,
        type=int,
        help=f"Recent commit count to show. Defaults to {DEFAULT_WEB_MAX_COMMITS}.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    app = create_app(args.repo, args.max_commits)
    app.run(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
