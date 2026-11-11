#!/usr/bin/env python3
"""Opt-in branch workflow tool for Build Forge.

Manages task branches, stacked branches, handoffs, local merges, and cleanups.
Standard library only. All state is maintained in .agents/work/branch-state.json.
"""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

VALID_STATUSES = {
    "started",
    "in-progress",
    "ready-for-test",
    "changes-requested",
    "approved",
    "merged",
    "cleaned",
    "parked",
    "abandoned",
}

ACTIVE_STATUSES = {
    "started",
    "in-progress",
    "ready-for-test",
    "changes-requested",
    "approved",
}


def run_git(args, cwd, check=True):
    """Execute git command and return CompletedProcess."""
    cmd = ["git"] + args
    res = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, check=False)
    if check and res.returncode != 0:
        err = res.stderr.strip() or res.stdout.strip()
        raise RuntimeError(f"Git command failed ({' '.join(args)}): {err}")
    return res


def get_repo_root(start_dir):
    """Resolve git repository root."""
    res = run_git(["rev-parse", "--show-toplevel"], start_dir, check=False)
    if res.returncode == 0 and res.stdout.strip():
        return Path(res.stdout.strip()).resolve()
    return Path(start_dir).resolve()


def get_state_file(root):
    """Return path to branch-state.json."""
    return root / ".agents" / "work" / "branch-state.json"


def load_state(root):
    """Load state from .agents/work/branch-state.json."""
    sfile = get_state_file(root)
    if not sfile.is_file():
        return None
    try:
        return json.loads(sfile.read_text(encoding="utf-8"))
    except Exception as e:
        sys.stderr.write(f"Warning: Corrupted branch state file: {e}\n")
        return None


def save_state(root, state):
    """Save state to .agents/work/branch-state.json without timestamps."""
    sfile = get_state_file(root)
    sfile.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(state, indent=2) + "\n"
    sfile.write_text(content, encoding="utf-8")


def load_profile(root):
    """Load .agents/project-profile.yaml if present."""
    prof_path = root / ".agents" / "project-profile.yaml"
    if not prof_path.is_file():
        return {}
    try:
        import yaml
        return yaml.safe_load(prof_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def detect_default_branch(root, profile):
    """Detect default branch from profile, git remote, or local branches."""
    wf = profile.get("git", {}).get("workflow", {})
    if wf.get("default_branch"):
        return wf["default_branch"]

    res_rem = run_git(["symbolic-ref", "refs/remotes/origin/HEAD"], root, check=False)
    if res_rem.returncode == 0 and res_rem.stdout.strip():
        ref = res_rem.stdout.strip()
        return ref.split("/")[-1]

    for cand in ["main", "master"]:
        res_cand = run_git(["rev-parse", "--verify", cand], root, check=False)
        if res_cand.returncode == 0:
            return cand
    return "main"


def get_current_branch(root):
    """Return current branch name or empty string if detached."""
    res = run_git(["branch", "--show-current"], root, check=False)
    return res.stdout.strip() if res.returncode == 0 else ""


def is_tree_dirty(root):
    """Check whether working tree has uncommitted changes or untracked files."""
    res = run_git(["status", "--porcelain"], root, check=False)
    if res.returncode != 0:
        return True
    lines = [l for l in res.stdout.splitlines() if not l.startswith("?? .agents/work/")]
    return len(lines) > 0


def cmd_status(args, root, profile):
    """Report branch workflow status."""
    state = load_state(root)
    curr_branch = get_current_branch(root)
    def_branch = detect_default_branch(root, profile)
    dirty = is_tree_dirty(root)

    wf = profile.get("git", {}).get("workflow", {})
    remote_name = wf.get("remote", "origin")

    # Remote check
    res_rem = run_git(["remote"], root, check=False)
    remotes = res_rem.stdout.split() if res_rem.returncode == 0 else []
    has_remote = remote_name in remotes

    # Forge CLI detection
    gh_exists = False
    try:
        res_gh = subprocess.run(["gh", "--version"], capture_output=True, text=True, check=False)
        gh_exists = (res_gh.returncode == 0)
    except Exception:
        gh_exists = False

    base = state.get("base", def_branch) if state else def_branch
    ahead = 0
    behind = 0

    if curr_branch and base:
        res_rev = run_git(["rev-list", "--left-right", "--count", f"{base}...{curr_branch}"], root, check=False)
        if res_rev.returncode == 0 and res_rev.stdout.strip():
            parts = res_rev.stdout.strip().split()
            if len(parts) == 2:
                behind = int(parts[0])
                ahead = int(parts[1])

    info = {
        "branch": curr_branch,
        "base": base,
        "default_branch": def_branch,
        "ahead": ahead,
        "behind": behind,
        "dirty": dirty,
        "remote": remote_name if has_remote else None,
        "forge_command_exists": gh_exists,
        "state": state,
    }

    if args.json:
        print(json.dumps(info, indent=2))
    else:
        print(f"Branch: {curr_branch or '(detached)'}")
        print(f"Base: {base} (ahead: {ahead}, behind: {behind})")
        print(f"Working tree: {'dirty' if dirty else 'unmodified'}")
        print(f"Remote: {remote_name if has_remote else 'none'}")
        print(f"Forge CLI (gh): {'available' if gh_exists else 'not found'}")
        if state:
            print(f"Workflow State: task='{state.get('task')}', status='{state.get('status')}', parent='{state.get('parent')}'")
        else:
            print("Workflow State: no active task branch state")
    return 0


def cmd_start(args, root, profile):
    """Start a new task branch or stacked branch."""
    if is_tree_dirty(root):
        sys.stderr.write("Error: Working tree has uncommitted changes. Stash or commit before starting a task branch.\n")
        return 1

    wf = profile.get("git", {}).get("workflow", {})
    def_branch = detect_default_branch(root, profile)
    remote_name = wf.get("remote", "origin")

    # Validate type
    allowed_types = profile.get("git", {}).get("types") or ["feat", "fix", "refactor", "style", "test", "docs", "chore"]
    if args.type not in allowed_types:
        sys.stderr.write(f"Error: Invalid type '{args.type}'. Must be one of: {', '.join(allowed_types)}\n")
        return 1

    # Validate slug
    slug = args.name.strip()
    if not re.match(r"^[a-z0-9]+(-[a-z0-9]+)*$", slug) or len(slug) > 40:
        sys.stderr.write(f"Error: Branch name '{slug}' must be lowercase kebab-case and 40 characters or fewer.\n")
        return 1

    fmt = wf.get("branch_format", "<type>/<slug>")
    branch_name = fmt.replace("<type>", args.type).replace("<slug>", slug)

    # Check existing branch
    res_b = run_git(["rev-parse", "--verify", f"refs/heads/{branch_name}"], root, check=False)
    if res_b.returncode == 0:
        sys.stderr.write(f"Error: Branch '{branch_name}' already exists locally.\n")
        return 1

    base_branch = args.base if args.base else def_branch
    parent_branch = None

    # Check for stacked branches
    prev_state = load_state(root)
    if args.base and prev_state and prev_state.get("branch") == args.base:
        if prev_state.get("parent"):
            sys.stderr.write(f"Error: Stacked branch depth limit exceeded. Branch '{args.base}' already has parent '{prev_state.get('parent')}'. Max depth is 2.\n")
            return 1
        parent_branch = args.base

    # Check remote exists
    res_rem = run_git(["remote"], root, check=False)
    has_remote = remote_name in (res_rem.stdout.split() if res_rem.returncode == 0 else [])

    if has_remote and not args.no_fetch:
        run_git(["fetch", remote_name, base_branch], root, check=False)

    # Get base commit SHA
    res_sha = run_git(["rev-parse", base_branch], root, check=False)
    base_sha = res_sha.stdout.strip() if res_sha.returncode == 0 else ""

    worktree_path = None
    if args.worktree:
        wt_dir = root / ".agents" / "work" / "trees" / slug
        wt_dir.parent.mkdir(parents=True, exist_ok=True)
        run_git(["worktree", "add", str(wt_dir), "-b", branch_name, base_branch], root, check=True)
        worktree_path = str(wt_dir)
        print(f"Created worktree at: {worktree_path}")
    else:
        run_git(["checkout", "-b", branch_name, base_branch], root, check=True)

    state = {
        "task": slug,
        "branch": branch_name,
        "base": base_branch,
        "base_sha": base_sha,
        "parent": parent_branch,
        "status": "started",
        "worktree_path": worktree_path,
        "pr": "",
        "consent": [],
    }
    save_state(root, state)

    if args.json:
        print(json.dumps(state, indent=2))
    else:
        print(f"Started task branch '{branch_name}' from base '{base_branch}'.")
        print(f"Status: started (state recorded in .agents/work/branch-state.json)")
    return 0


def cmd_guard(args, root, profile):
    """Guard against committing on the default branch when branch workflow is active."""
    state = load_state(root)
    if not state:
        return 0

    status = state.get("status")
    if status not in ACTIVE_STATUSES:
        return 0

    curr_branch = get_current_branch(root)
    def_branch = detect_default_branch(root, profile)

    if curr_branch and curr_branch == def_branch:
        task = state.get("task", "unknown")
        target_branch = state.get("branch", "unknown")
        sys.stderr.write(
            f"Error: Branch workflow guard violation.\n"
            f"Cannot commit directly on default branch '{def_branch}' while task '{task}' is active on branch '{target_branch}'.\n"
            f"Switch to '{target_branch}' before committing, or park/abandon the active branch workflow task.\n"
        )
        return 1
    return 0


def cmd_handoff(args, root, profile):
    """Hand off task branch to user for manual testing."""
    state = load_state(root)
    if not state:
        sys.stderr.write("Error: No branch workflow state found. Run start first.\n")
        return 1

    branch = state.get("branch")
    base = state.get("base", "main")

    # Commits since base
    res_log = run_git(["log", f"{base}..{branch}", "--oneline"], root, check=False)
    commits = res_log.stdout.strip().splitlines() if res_log.returncode == 0 and res_log.stdout.strip() else []

    # Changed files
    res_files = run_git(["diff", "--name-only", f"{base}...{branch}"], root, check=False)
    changed_files = res_files.stdout.strip().splitlines() if res_files.returncode == 0 and res_files.stdout.strip() else []

    # Dev command from profile
    dev_cmd = profile.get("commands", {}).get("dev", "")

    # Try it checklist from CURRENT_GOAL.md if available
    goal_file = root / ".agents" / "work" / "CURRENT_GOAL.md"
    try_it_steps = []
    if goal_file.is_file():
        goal_text = goal_file.read_text(encoding="utf-8")
        in_invariants = False
        for line in goal_text.splitlines():
            if line.startswith("## Acceptance Invariants"):
                in_invariants = True
                continue
            elif line.startswith("## "):
                in_invariants = False
            if in_invariants and line.strip().startswith("- ["):
                try_it_steps.append(line.strip()[6:].strip())

    if not try_it_steps:
        try_it_steps = [
            f"Switch to branch '{branch}' and inspect changes.",
            f"Run tests: python3 -m unittest or project test suite.",
            "Confirm expected behavior in your browser or application.",
        ]

    state["status"] = "ready-for-test"
    save_state(root, state)

    output = {
        "branch": branch,
        "base": base,
        "commits": commits,
        "changed_files": changed_files,
        "try_it_steps": try_it_steps,
        "worktree_path": state.get("worktree_path"),
        "dev_command": dev_cmd,
        "choices": ["approve", "changes requested", "park", "abandon"],
    }

    if args.json:
        print(json.dumps(output, indent=2))
    else:
        print(f"=== Task Branch Handoff: {branch} ===")
        print(f"Base: {base}")
        print("\nCommits since base:")
        for c in commits:
            print(f"  {c}")
        print("\nChanged files:")
        for cf in changed_files:
            print(f"  {cf}")
        print("\nHow to test:")
        if state.get("worktree_path"):
            print(f"  cd '{state.get('worktree_path')}'")
        else:
            print(f"  git switch {branch}")
        if dev_cmd:
            print(f"  Run dev server: {dev_cmd}")
        print("\nTry it checklist:")
        for i, step in enumerate(try_it_steps, start=1):
            print(f"  {i}. {step}")
        print("\nNext steps (choose one):")
        print("  1. Approve: Proceed to merge")
        print("  2. Changes requested: Provide feedback and iterate on this branch")
        print("  3. Park: Pause work and switch to another branch")
        print("  4. Abandon: Discard changes and close task")
    return 0


def cmd_sync(args, root, profile):
    """Sync task branch with base branch (merge or rebase)."""
    state = load_state(root)
    base = state.get("base", "main") if state else detect_default_branch(root, profile)
    branch = state.get("branch") if state else get_current_branch(root)

    wf = profile.get("git", {}).get("workflow", {})
    policy = wf.get("sync", "merge")
    remote_name = wf.get("remote", "origin")

    # Check remote
    res_rem = run_git(["remote"], root, check=False)
    has_remote = remote_name in (res_rem.stdout.split() if res_rem.returncode == 0 else [])

    if has_remote:
        run_git(["fetch", remote_name, base], root, check=False)

    if args.dry_run:
        print(f"Dry run: Would {policy} '{base}' into '{branch}'.")
        return 0

    if policy == "rebase":
        # Check if branch has been pushed upstream
        res_push_chk = run_git(["rev-parse", "--verify", f"refs/remotes/{remote_name}/{branch}"], root, check=False)
        is_pushed = (res_push_chk.returncode == 0)

        valid_phrases = [f"yes rewrite branch {branch}"]
        if state and state.get("task"):
            valid_phrases.append(f"yes rewrite branch {state['task']}")
        if is_pushed:
            if not args.phrase or args.phrase.strip() not in valid_phrases:
                sys.stderr.write(
                    f"Error: Branch '{branch}' has already been pushed to remote.\n"
                    f"Rebasing will rewrite published history. To proceed, pass: --phrase \"yes rewrite branch {branch}\"\n"
                )
                return 1

        res_reb = run_git(["rebase", base], root, check=False)
        if res_reb.returncode != 0:
            sys.stderr.write(f"Sync conflict during rebase:\n{res_reb.stderr or res_reb.stdout}\n")
            sys.stderr.write("Repository left in conflict state. Resolve conflicts manually and run 'git rebase --continue'.\n")
            return 1
        print(f"Successfully rebased '{branch}' onto '{base}'.")
    else:
        res_merge = run_git(["merge", base, "-m", f"sync: merge {base} into {branch}"], root, check=False)
        if res_merge.returncode != 0:
            sys.stderr.write(f"Sync conflict during merge:\n{res_merge.stderr or res_merge.stdout}\n")
            sys.stderr.write("Repository left in conflict state. Resolve conflicts manually and commit the merge.\n")
            return 1
        print(f"Successfully merged '{base}' into '{branch}'.")

    return 0


def cmd_merge_local(args, root, profile):
    """Merge task branch locally into base or target branch."""
    expected_phrase = "yes merge locally"
    if not args.phrase or args.phrase.strip() != expected_phrase:
        sys.stderr.write(f"Error: Confirmation required. Pass: --phrase \"{expected_phrase}\"\n")
        return 1

    state = load_state(root)
    if not state:
        sys.stderr.write("Error: No branch workflow state found.\n")
        return 1

    target_branch = args.into if args.into else state.get("base", "main")
    branch = state.get("branch")

    if is_tree_dirty(root):
        sys.stderr.write("Error: Working tree is dirty. Stash or commit before merging.\n")
        return 1

    wf = profile.get("git", {}).get("workflow", {})
    method = wf.get("merge_method", "squash")

    # Run check command if configured
    check_cmd = profile.get("commands", {}).get("check")
    if check_cmd:
        res_chk = subprocess.run(check_cmd, shell=True, cwd=str(root), capture_output=True, text=True, check=False)
        if res_chk.returncode != 0:
            sys.stderr.write(f"Error: Pre-merge check command failed:\n{res_chk.stderr or res_chk.stdout}\n")
            return 1

    # Switch to target branch
    run_git(["checkout", target_branch], root, check=True)

    if method == "squash":
        res_m = run_git(["merge", "--squash", branch], root, check=False)
        if res_m.returncode != 0:
            sys.stderr.write(f"Error: Squash merge failed:\n{res_m.stderr or res_m.stdout}\n")
            return 1

        # Check commit message format
        c_fmt = profile.get("git", {}).get("commit_format", "<type>: <subject>")
        task_slug = state.get("task", "update")
        commit_msg = f"feat({task_slug}): complete {task_slug} task"

        run_git(["commit", "-m", commit_msg], root, check=True)
        res_sha = run_git(["rev-parse", "HEAD"], root, check=True)
        merge_sha = res_sha.stdout.strip()
    elif method == "rebase":
        res_m = run_git(["merge", "--ff-only", branch], root, check=False)
        if res_m.returncode != 0:
            sys.stderr.write(f"Error: Fast-forward merge failed:\n{res_m.stderr or res_m.stdout}\n")
            return 1
        res_sha = run_git(["rev-parse", "HEAD"], root, check=True)
        merge_sha = res_sha.stdout.strip()
    else:
        res_m = run_git(["merge", "--no-ff", branch, "-m", f"merge: {branch} into {target_branch}"], root, check=False)
        if res_m.returncode != 0:
            sys.stderr.write(f"Error: Merge failed:\n{res_m.stderr or res_m.stdout}\n")
            return 1
        res_sha = run_git(["rev-parse", "HEAD"], root, check=True)
        merge_sha = res_sha.stdout.strip()

    state["status"] = "merged"
    state["merge_sha"] = merge_sha
    if "consent" not in state:
        state["consent"] = []
    state["consent"].append(expected_phrase)
    save_state(root, state)

    print(f"Successfully merged '{branch}' into '{target_branch}' ({method} method, commit: {merge_sha[:7]}).")
    return 0


def cmd_sync_main(args, root, profile):
    """Switch to default branch, pull with ff-only, and verify merge commit presence."""
    def_branch = detect_default_branch(root, profile)
    wf = profile.get("git", {}).get("workflow", {})
    remote_name = wf.get("remote", "origin")

    run_git(["checkout", def_branch], root, check=True)

    res_rem = run_git(["remote"], root, check=False)
    has_remote = remote_name in (res_rem.stdout.split() if res_rem.returncode == 0 else [])

    if has_remote:
        res_pull = run_git(["pull", "--ff-only"], root, check=False)
        if res_pull.returncode != 0:
            sys.stderr.write(f"Warning: git pull --ff-only failed: {res_pull.stderr.strip()}\n")

    state = load_state(root)
    if state and state.get("merge_sha"):
        m_sha = state["merge_sha"]
        res_chk = run_git(["branch", def_branch, "--contains", m_sha], root, check=False)
        if res_chk.returncode == 0:
            print(f"Confirmed merge commit {m_sha[:7]} is present on '{def_branch}'.")
        else:
            print(f"Notice: Commit {m_sha[:7]} not yet reflected on '{def_branch}'.")
    else:
        print(f"Synchronized with default branch '{def_branch}'.")
    return 0


def cmd_park(args, root, profile):
    """Park active task branch and return to default branch."""
    state = load_state(root)
    if not state:
        sys.stderr.write("Error: No branch workflow state found.\n")
        return 1

    state["status"] = "parked"
    save_state(root, state)

    def_branch = detect_default_branch(root, profile)
    curr = get_current_branch(root)
    if curr != def_branch:
        run_git(["checkout", def_branch], root, check=False)

    print(f"Parked task branch '{state.get('branch')}'. State marked as parked.")
    return 0


def cmd_resume(args, root, profile):
    """Resume a parked task branch."""
    state = load_state(root)
    if not state:
        sys.stderr.write("Error: No branch workflow state found.\n")
        return 1

    task_name = args.task.strip() if args.task else ""
    if task_name and state.get("task") != task_name:
        sys.stderr.write(f"Error: State task '{state.get('task')}' does not match requested '{task_name}'.\n")
        return 1

    branch = state.get("branch")
    if not branch:
        sys.stderr.write("Error: No branch recorded in state.\n")
        return 1

    run_git(["checkout", branch], root, check=True)
    state["status"] = "in-progress"
    save_state(root, state)

    print(f"Resumed task branch '{branch}'. Status set to in-progress.")
    return 0


def cmd_abandon(args, root, profile):
    """Abandon task branch and keep branch."""
    state = load_state(root)
    if not state:
        sys.stderr.write("Error: No branch workflow state found.\n")
        return 1

    task_slug = state.get("task", "task")
    branch = state.get("branch", "")
    valid_phrases = [f"yes abandon {task_slug}"]
    if branch:
        valid_phrases.append(f"yes abandon {branch}")
    if not args.phrase or args.phrase.strip() not in valid_phrases:
        sys.stderr.write(f"Error: Confirmation required. Pass: --phrase \"yes abandon {task_slug}\"\n")
        return 1

    tag_name = f"abandoned/{task_slug}"
    run_git(["tag", "-f", tag_name, branch], root, check=False)

    state["status"] = "abandoned"
    if "consent" not in state:
        state["consent"] = []
    state["consent"].append(args.phrase.strip())
    save_state(root, state)

    def_branch = detect_default_branch(root, profile)
    run_git(["checkout", def_branch], root, check=False)

    print(f"Task branch '{branch}' abandoned (tagged locally as '{tag_name}'). Branch kept.")
    return 0


def cmd_cleanup(args, root, profile):
    """Delete local task branch after proof of merge and user phrase."""
    state = load_state(root)
    if not state:
        sys.stderr.write("Error: No branch workflow state found.\n")
        return 1

    task_slug = state.get("task", "task")
    branch = state.get("branch", "")
    valid_phrases = [f"yes delete branch {task_slug}"]
    if branch:
        valid_phrases.append(f"yes delete branch {branch}")

    if not args.phrase or args.phrase.strip() not in valid_phrases:
        sys.stderr.write(f"Error: Confirmation required. Pass: --phrase \"yes delete branch {task_slug}\"\n")
        return 1

    def_branch = detect_default_branch(root, profile)

    # Proof verification: standard git merge or squash merge proof
    res_merged = run_git(["branch", "--merged", def_branch], root, check=False)
    merged_branches = [b.strip().replace("*", "").strip() for b in res_merged.stdout.splitlines()]

    is_proven = (branch in merged_branches)
    if not is_proven and state.get("status") == "merged" and state.get("merge_sha"):
        # Check if merge_sha exists on default_branch
        m_sha = state["merge_sha"]
        res_sha_chk = run_git(["branch", def_branch, "--contains", m_sha], root, check=False)
        if res_sha_chk.returncode == 0:
            is_proven = True

    if not is_proven:
        sys.stderr.write(f"Error: Cannot delete branch '{branch}'. It is not proven merged into '{def_branch}'.\n")
        return 1

    # Switch away before delete
    curr = get_current_branch(root)
    if curr == branch:
        run_git(["checkout", def_branch], root, check=True)

    # Remove worktree if used
    wt_path = state.get("worktree_path")
    if wt_path and os.path.exists(wt_path):
        run_git(["worktree", "remove", "--force", wt_path], root, check=False)

    run_git(["branch", "-D", branch], root, check=True)

    state["status"] = "cleaned"
    if "consent" not in state:
        state["consent"] = []
    state["consent"].append(args.phrase.strip())
    save_state(root, state)

    print(f"Cleaned up task branch '{branch}' successfully.")
    return 0


def cmd_revert_plan(args, root, profile):
    """Print exact steps for a revert branch."""
    target = args.target.strip() if args.target else "HEAD"
    plan = {
        "target": target,
        "steps": [
            f"python3 .agents/skills/feature-delivery/scripts/branchflow.py start --name revert-{target[:7]} --type fix",
            f"git revert {target}",
            "Run test suite: commands.check",
            "python3 .agents/skills/feature-delivery/scripts/branchflow.py handoff",
            "python3 .agents/skills/feature-delivery/scripts/branchflow.py merge-local --approved --phrase \"yes merge locally\"",
        ],
    }
    if args.json:
        print(json.dumps(plan, indent=2))
    else:
        print(f"=== Revert Plan for {target} ===")
        for i, step in enumerate(plan["steps"], start=1):
            print(f"  {i}. {step}")
    return 0


def main():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root", default=".", help="Project root directory.")
    common.add_argument("--json", action="store_true", help="Output result as JSON.")

    parser = argparse.ArgumentParser(description="Build Forge branch workflow tool.", parents=[common])
    subparsers = parser.add_subparsers(dest="command", help="Workflow command.")

    # status
    subparsers.add_parser("status", help="Show branch workflow status.", parents=[common])

    # start
    p_start = subparsers.add_parser("start", help="Start a new task branch.", parents=[common])
    p_start.add_argument("--name", required=True, help="Task slug (kebab-case, <= 40 chars).")
    p_start.add_argument("--type", required=True, help="Change type from git.types.")
    p_start.add_argument("--base", help="Base branch (default: default_branch).")
    p_start.add_argument("--worktree", action="store_true", help="Create in separate worktree.")
    p_start.add_argument("--no-fetch", action="store_true", help="Skip remote fetch.")

    # guard
    subparsers.add_parser("guard", help="Verify branch guard before committing.", parents=[common])

    # handoff
    subparsers.add_parser("handoff", help="Hand off task branch for user testing.", parents=[common])

    # sync
    p_sync = subparsers.add_parser("sync", help="Sync task branch with base.", parents=[common])
    p_sync.add_argument("--dry-run", action="store_true", help="Dry run check.")
    p_sync.add_argument("--phrase", help="Confirmation phrase for history rewrite.")

    # merge-local
    p_merge = subparsers.add_parser("merge-local", help="Merge task branch locally.", parents=[common])
    p_merge.add_argument("--approved", action="store_true", help="Flag indicating user approval.")
    p_merge.add_argument("--phrase", required=True, help="Exact confirmation phrase: 'yes merge locally'.")
    p_merge.add_argument("--into", help="Target branch to merge into.")

    # sync-main
    subparsers.add_parser("sync-main", help="Switch to default branch and pull.", parents=[common])

    # park
    subparsers.add_parser("park", help="Park task branch.", parents=[common])

    # resume
    p_resume = subparsers.add_parser("resume", help="Resume task branch.", parents=[common])
    p_resume.add_argument("--task", help="Task name to resume.")

    # abandon
    p_abandon = subparsers.add_parser("abandon", help="Abandon task branch.", parents=[common])
    p_abandon.add_argument("--approved", action="store_true", help="Flag indicating approval.")
    p_abandon.add_argument("--phrase", required=True, help="Exact phrase: 'yes abandon <name>'.")

    # cleanup
    p_clean = subparsers.add_parser("cleanup", help="Delete task branch after merge.", parents=[common])
    p_clean.add_argument("--approved", action="store_true", help="Flag indicating approval.")
    p_clean.add_argument("--phrase", required=True, help="Exact phrase: 'yes delete branch <name>'.")
    p_clean.add_argument("--delete-remote", action="store_true", help="Delete remote branch as well.")

    # revert-plan
    p_rev = subparsers.add_parser("revert-plan", help="Print revert plan.", parents=[common])
    p_rev.add_argument("target", nargs="?", default="HEAD", help="Commit SHA or branch to revert.")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return 1

    root = get_repo_root(args.root)
    profile = load_profile(root)

    dispatch = {
        "status": cmd_status,
        "start": cmd_start,
        "guard": cmd_guard,
        "handoff": cmd_handoff,
        "sync": cmd_sync,
        "merge-local": cmd_merge_local,
        "sync-main": cmd_sync_main,
        "park": cmd_park,
        "resume": cmd_resume,
        "abandon": cmd_abandon,
        "cleanup": cmd_cleanup,
        "revert-plan": cmd_revert_plan,
    }

    handler = dispatch.get(args.command)
    if not handler:
        sys.stderr.write(f"Unknown command: {args.command}\n")
        return 1
    return handler(args, root, profile)


if __name__ == "__main__":
    sys.exit(main())
