import { existsSync } from "node:fs";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { test } from "node:test";
import assert from "node:assert/strict";

import { readDashboardSnapshot } from "../src/dashboard";
import type { GitStatusReader } from "../src/dashboard";
import { parseGitStatus } from "../src/git";
import type { GitStatusSnapshot } from "../src/git";
import { MarkdownState } from "../src/state";

test("readDashboardSnapshot summarizes plans, queues, PR lock, and git status", async () => {
  await withRepo(async (root) => {
    const state = new MarkdownState(root);
    const planDir = path.join(root, ".crack", "plans", "demo");
    const planPath = path.join(planDir, "plan.md");
    await mkdir(planDir, { recursive: true });
    await writeFile(
      state.inboxPath,
      [
        "# Inbox",
        "",
        queuedRequest("First inbox request", "PR lock.", "2026-05-09 12:00"),
        queuedRequest("Second inbox request", "PR lock.", "2026-05-09 12:05"),
      ].join("\n"),
      "utf8",
    );
    await writeFile(
      state.prLockPath,
      [
        "# PR Lock",
        "",
        "Branch: codex/demo",
        "PR: https://github.com/example/repo/pull/7",
        "Status: reviewing",
        "",
      ].join("\n"),
      "utf8",
    );
    await writeFile(
      planPath,
      [
        "# Plan: Demo Dashboard",
        "",
        "Branch: codex/demo",
        "",
        "## Commit Units",
        "",
        "### Commit 1: Add snapshot model",
        "",
        "Create the model.",
        "",
        "### Commit 2: Render dashboard",
        "",
        "Render it.",
        "",
        "### Commit 3: Wire CLI",
        "",
        "Expose the command.",
        "",
      ].join("\n"),
      "utf8",
    );
    await writeFile(
      path.join(planDir, "queue.md"),
      ["# Queue", "", queuedRequest("Follow-up request", "Depends on this plan.", "2026-05-09 12:10")].join("\n"),
      "utf8",
    );
    await writeFile(
      path.join(planDir, "log.md"),
      [
        "# Log",
        "",
        "## 2026-05-09 12:20",
        "",
        "- Started commit unit 1: Add snapshot model.",
        "- Completed commit unit 1.",
        "",
      ].join("\n"),
      "utf8",
    );

    const snapshot = await readDashboardSnapshot(state, {
      gitStatusReader: new StubGitStatusReader(parseGitStatus([
        "M  src/index.ts",
        " M src/dashboard.ts",
        "?? tests/dashboard.test.ts",
        "",
      ].join("\n"))),
    });

    assert.equal(snapshot.initialized, true);
    assert.equal(snapshot.inbox.count, 2);
    assert.equal(snapshot.prLock?.valid, true);
    assert.equal(snapshot.prLock?.branchName, "codex/demo");
    assert.equal(snapshot.prLock?.prUrl, "https://github.com/example/repo/pull/7");
    assert.equal(snapshot.prLock?.status, "reviewing");

    assert.equal(snapshot.plans.length, 1);
    const plan = snapshot.plans[0];
    assert.equal(plan.title, "Demo Dashboard");
    assert.equal(plan.branchName, "codex/demo");
    assert.equal(plan.relativePlanPath, ".crack/plans/demo/plan.md");
    assert.deepEqual(plan.commitUnits, {
      total: 3,
      completed: 1,
      remaining: 2,
      completedNumbers: [1],
      next: {
        number: 2,
        title: "Render dashboard",
      },
    });
    assert.equal(plan.queuedRequestCount, 1);
    assert.equal(
      plan.nextCommands.find((command) => command.kind === "run-all")?.command,
      "crack run-all --plan .crack/plans/demo/plan.md",
    );

    assert.equal(snapshot.git.isDirty, true);
    assert.equal(snapshot.git.changedFileCount, 3);
    assert.equal(snapshot.git.stagedFileCount, 1);
    assert.equal(snapshot.git.unstagedFileCount, 1);
    assert.equal(snapshot.git.untrackedFileCount, 1);
  });
});

test("readDashboardSnapshot does not initialize missing crack state", async () => {
  await withRepo(async (root) => {
    const state = new MarkdownState(root);

    const snapshot = await readDashboardSnapshot(state, {
      gitStatusReader: new StubGitStatusReader(parseGitStatus("")),
    });

    assert.equal(snapshot.initialized, false);
    assert.equal(snapshot.inbox.count, 0);
    assert.equal(snapshot.prLock, null);
    assert.deepEqual(snapshot.plans, []);
    assert.equal(existsSync(state.crackDir), false);
  });
});

async function withRepo(run: (root: string) => Promise<void>): Promise<void> {
  const root = await mkdtemp(path.join(tmpdir(), "crack-"));

  try {
    await mkdir(path.join(root, ".git"));
    await run(root);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
}

function queuedRequest(prompt: string, reason: string, receivedAt: string): string {
  return [
    "## Queued Request",
    "",
    `Received: ${receivedAt}`,
    "",
    "User prompt:",
    "",
    `> ${prompt}`,
    "",
    "Reason:",
    "",
    reason,
    "",
  ].join("\n");
}

class StubGitStatusReader implements GitStatusReader {
  constructor(private readonly snapshot: GitStatusSnapshot) {}

  async status(): Promise<GitStatusSnapshot> {
    return this.snapshot;
  }
}
