import { existsSync } from "node:fs";
import { readdir, readFile } from "node:fs/promises";
import path from "node:path";

import type { GitStatusEntry, GitStatusSnapshot } from "./git";
import { GitCliCommitter } from "./git";
import { completedCommitUnitNumbers, parseCommitUnits } from "./implementer";
import type { CommitUnit } from "./implementer";
import { parsePrLock } from "./pr-check";
import type { PrLock } from "./pr-check";
import type { MarkdownState, QueuedRequest } from "./state";
import { parseQueuedRequests } from "./state";

export type DashboardSnapshot = {
  repoRoot: string;
  crackDir: string;
  initialized: boolean;
  inbox: DashboardRequestQueueSummary;
  prLock: DashboardPrLockSummary | null;
  plans: DashboardPlanSummary[];
  git: DashboardGitStatusSummary;
};

export type DashboardPlanSummary = {
  directory: string;
  planPath: string;
  queuePath: string;
  logPath: string;
  relativeDirectory: string;
  relativePlanPath: string;
  branchName: string;
  title: string;
  commitUnits: DashboardCommitUnitProgress;
  queuedRequestCount: number;
  recentLogEntries: DashboardLogEntry[];
  nextCommands: DashboardNextCommand[];
};

export type DashboardRequestQueueSummary = {
  path: string;
  count: number;
  requests: QueuedRequest[];
};

export type DashboardPrLockSummary =
  | (PrLock & {
      path: string;
      raw: string;
      valid: true;
    })
  | {
      path: string;
      raw: string;
      valid: false;
      branchName?: string;
      prUrl?: string;
      status?: string;
    };

export type DashboardCommitUnitProgress = {
  total: number;
  completed: number;
  remaining: number;
  completedNumbers: number[];
  next: DashboardCommitUnitSummary | null;
};

export type DashboardCommitUnitSummary = {
  number: number;
  title: string;
};

export type DashboardNextCommand = {
  kind: "run-next" | "run-all";
  command: string;
};

export type DashboardLogEntry = {
  loggedAt?: string;
  text: string;
};

export type DashboardGitStatusSummary = {
  raw: string;
  entries: GitStatusEntry[];
  isDirty: boolean;
  changedFileCount: number;
  stagedFileCount: number;
  unstagedFileCount: number;
  untrackedFileCount: number;
};

export interface GitStatusReader {
  status(): Promise<GitStatusSnapshot>;
}

export type ReadDashboardSnapshotOptions = {
  gitStatusReader?: GitStatusReader;
};

export async function readDashboardSnapshot(
  state: MarkdownState,
  options: ReadDashboardSnapshotOptions = {},
): Promise<DashboardSnapshot> {
  const [inbox, prLock, plans, gitStatus] = await Promise.all([
    readRequestQueue(state.inboxPath),
    readPrLock(state.prLockPath),
    readPlans(state),
    (options.gitStatusReader ?? new GitCliCommitter(state.repoRoot)).status(),
  ]);

  return {
    repoRoot: state.repoRoot,
    crackDir: state.crackDir,
    initialized: existsSync(state.crackDir),
    inbox,
    prLock,
    plans,
    git: summarizeGitStatus(gitStatus),
  };
}

async function readRequestQueue(queuePath: string): Promise<DashboardRequestQueueSummary> {
  const content = await readTextIfExists(queuePath);
  const requests = parseQueuedRequests(content);

  return {
    path: queuePath,
    count: requests.length,
    requests,
  };
}

async function readPrLock(lockPath: string): Promise<DashboardPrLockSummary | null> {
  if (!existsSync(lockPath)) {
    return null;
  }

  const raw = await readFile(lockPath, "utf8");
  const parsed = parsePrLock(raw);
  if (!parsed) {
    return {
      path: lockPath,
      raw,
      valid: false,
    };
  }

  return {
    ...parsed,
    path: lockPath,
    raw,
    valid: true,
  };
}

async function readPlans(state: MarkdownState): Promise<DashboardPlanSummary[]> {
  if (!existsSync(state.plansDir)) {
    return [];
  }

  const entries = await readdir(state.plansDir, { withFileTypes: true });
  const plans = await Promise.all(
    entries
      .filter((entry) => entry.isDirectory())
      .map(async (entry) => {
        const directory = path.join(state.plansDir, entry.name);
        const planPath = path.join(directory, "plan.md");

        if (!existsSync(planPath)) {
          return null;
        }

        const queuePath = path.join(directory, "queue.md");
        const logPath = path.join(directory, "log.md");
        const [planContent, queueContent, logContent] = await Promise.all([
          readFile(planPath, "utf8"),
          readTextIfExists(queuePath),
          readTextIfExists(logPath),
        ]);

        return summarizePlan({
          repoRoot: state.repoRoot,
          directory,
          planPath,
          queuePath,
          logPath,
          planContent,
          queueContent,
          logContent,
          fallbackBranchName: entry.name,
        });
      }),
  );

  return plans
    .filter((plan): plan is DashboardPlanSummary => plan !== null)
    .sort((left, right) => left.directory.localeCompare(right.directory));
}

function summarizePlan(input: {
  repoRoot: string;
  directory: string;
  planPath: string;
  queuePath: string;
  logPath: string;
  planContent: string;
  queueContent: string;
  logContent: string;
  fallbackBranchName: string;
}): DashboardPlanSummary {
  const units = parseCommitUnits(input.planContent);
  const completed = completedCommitUnitNumbers(input.logContent);
  const remainingUnits = units.filter((unit) => !completed.has(unit.number));
  const completedNumbers = units
    .filter((unit) => completed.has(unit.number))
    .map((unit) => unit.number);
  const relativePlanPath = relativePath(input.repoRoot, input.planPath);

  return {
    directory: input.directory,
    planPath: input.planPath,
    queuePath: input.queuePath,
    logPath: input.logPath,
    relativeDirectory: relativePath(input.repoRoot, input.directory),
    relativePlanPath,
    branchName: branchNameFromPlan(input.planContent) ?? input.fallbackBranchName,
    title: titleFromPlan(input.planContent) ?? input.fallbackBranchName,
    commitUnits: {
      total: units.length,
      completed: completedNumbers.length,
      remaining: remainingUnits.length,
      completedNumbers,
      next: remainingUnits[0] ? commitUnitSummary(remainingUnits[0]) : null,
    },
    queuedRequestCount: parseQueuedRequests(input.queueContent).length,
    recentLogEntries: recentLogEntries(input.logContent),
    nextCommands: remainingUnits.length > 0 ? nextCommands(relativePlanPath) : [],
  };
}

function summarizeGitStatus(status: GitStatusSnapshot): DashboardGitStatusSummary {
  let stagedFileCount = 0;
  let unstagedFileCount = 0;
  let untrackedFileCount = 0;

  for (const entry of status.entries) {
    if (entry.status === "??") {
      untrackedFileCount += 1;
      continue;
    }

    if (entry.status[0] && entry.status[0] !== " ") {
      stagedFileCount += 1;
    }

    if (entry.status[1] && entry.status[1] !== " ") {
      unstagedFileCount += 1;
    }
  }

  return {
    raw: status.raw,
    entries: status.entries,
    isDirty: status.entries.length > 0,
    changedFileCount: status.entries.length,
    stagedFileCount,
    unstagedFileCount,
    untrackedFileCount,
  };
}

async function readTextIfExists(filePath: string): Promise<string> {
  if (!existsSync(filePath)) {
    return "";
  }

  return readFile(filePath, "utf8");
}

function commitUnitSummary(unit: CommitUnit): DashboardCommitUnitSummary {
  return {
    number: unit.number,
    title: unit.title,
  };
}

function nextCommands(planPath: string): DashboardNextCommand[] {
  const planArg = shellQuote(planPath);

  return [
    {
      kind: "run-next",
      command: `crack run-next --plan ${planArg}`,
    },
    {
      kind: "run-all",
      command: `crack run-all --plan ${planArg}`,
    },
  ];
}

function recentLogEntries(logContent: string, limit = 3): DashboardLogEntry[] {
  const entries: DashboardLogEntry[] = [];
  let loggedAt: string | undefined;

  for (const line of logContent.split(/\r?\n/)) {
    const heading = line.match(/^##\s+(.+?)\s*$/);
    if (heading) {
      loggedAt = heading[1].trim();
      continue;
    }

    const bullet = line.match(/^-\s+(.+?)\s*$/);
    if (bullet) {
      entries.push({ loggedAt, text: bullet[1].trim() });
    }
  }

  return entries.slice(-limit);
}

function branchNameFromPlan(content: string): string | undefined {
  return content.match(/^Branch:\s*(.+)\s*$/m)?.[1]?.trim() || undefined;
}

function titleFromPlan(content: string): string | undefined {
  return content.match(/^#\s+Plan:\s*(.+)\s*$/m)?.[1]?.trim() || undefined;
}

function relativePath(repoRoot: string, filePath: string): string {
  return path.relative(repoRoot, filePath).split(path.sep).join("/");
}

function shellQuote(value: string): string {
  if (/^[A-Za-z0-9_./:-]+$/.test(value)) {
    return value;
  }

  return `'${value.replace(/'/g, "'\\''")}'`;
}
