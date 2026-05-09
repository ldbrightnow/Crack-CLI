import { runProcess } from "./process";

export interface BranchManager {
  prepareBranch(branchName: string): Promise<void>;
}

export class GitCliBranchManager implements BranchManager {
  constructor(private readonly repoRoot: string) {}

  async prepareBranch(branchName: string): Promise<void> {
    const trimmedBranchName = branchName.trim();
    if (!trimmedBranchName) {
      throw new Error("branchName is required");
    }

    const existingBranch = await runProcess(
      "git",
      ["rev-parse", "--verify", "--quiet", `refs/heads/${trimmedBranchName}`],
      { cwd: this.repoRoot },
    );

    if (existingBranch.status === 0) {
      await this.runGit(["switch", trimmedBranchName], `switch to ${trimmedBranchName}`);
      return;
    }

    await this.runGit(["switch", "-c", trimmedBranchName], `create branch ${trimmedBranchName}`);
  }

  private async runGit(args: string[], action: string): Promise<void> {
    const result = await runProcess("git", args, { cwd: this.repoRoot });

    if (result.status !== 0) {
      const details = result.stderr.trim() || result.stdout.trim();
      const suffix = details ? `: ${details}` : "";
      throw new Error(`Failed to ${action}${suffix}`);
    }
  }
}
