# Branch Mode Workflow

Use this workflow when working on a separate task branch for a feature, bug fix, or refactor.

## State Machine

The workflow state is stored in `.agents/work/branch-state.json`. It tracks the active task branch without timestamps.

```
       [ start ]
           |
           v
      ( started )
           |
           v
    ( in-progress ) <-----------------+
           |                          |
           v                          |
   ( ready-for-test )                 |
      /         \                     |
     /           \                    |
    v             v                   |
( approved )   ( changes-requested ) -+
    |
    v
( merged )
    |
    v
( cleaned )
```

Branch states:
- `started`: The branch was created from the base branch.
- `in-progress`: Commits are being added to the task branch.
- `ready-for-test`: Hand off ran. The task is waiting for user review.
- `changes-requested`: The user requested updates. The branch returns to active work.
- `approved`: The user approved the task branch.
- `merged`: The branch was merged into the target branch.
- `cleaned`: The local branch and worktree were deleted after proof of merge.
- `parked`: The task was put on hold. It can be resumed later.
- `abandoned`: The task was discarded. The branch is kept and tagged locally.

## Typed Confirmation Phrases

Dangerous operations require typed confirmation. The agent must prompt the user, wait for the response, and pass only the exact text typed by the user to the script via `--phrase`.

| Operation | Command | Exact phrase required |
|---|---|---|
| Rebase pushed branch | `branchflow.py sync` | `yes rewrite branch <name>` |
| Local merge | `branchflow.py merge-local` | `yes merge locally` |
| Abandon task | `branchflow.py abandon` | `yes abandon <name>` |
| Delete merged branch | `branchflow.py cleanup` | `yes delete branch <name>` |

In these phrases, `<name>` is the task slug or full branch name.

## Commands

All commands support `--root <path>` and `--json`.

### 1. status
Show the current branch, base branch, ahead and behind counts, dirty status, remote status, and active workflow state.
```bash
python3 .agents/skills/feature-delivery/scripts/branchflow.py status
```

### 2. start
Start a new task branch. Refuses if the tree is dirty, if the branch exists, or if the slug is invalid.
```bash
python3 .agents/skills/feature-delivery/scripts/branchflow.py start --name <slug> --type <type>
```
Options:
- `--base <branch>`: Base branch (default: detected default branch). Supports stacked branches up to depth 2.
- `--worktree`: Create the branch in an isolated git worktree under `.agents/worktrees/<slug>`.
- `--no-fetch`: Do not fetch from the remote before creating the branch.

### 3. guard
Exits with code 1 if a task branch is active and the current branch is the default branch. `atomic-commits` runs this before every commit to protect the default branch.
```bash
python3 .agents/skills/feature-delivery/scripts/branchflow.py guard
```

### 4. handoff
Prepares the task branch for user testing. Displays commits, changed files, how to switch to the branch or worktree, dev commands, the Try it checklist, known issues, and the 4 review choices (approve, changes-requested, park, abandon). Sets state to `ready-for-test`.
```bash
python3 .agents/skills/feature-delivery/scripts/branchflow.py handoff
```

### 5. sync
Syncs the task branch with its base branch using merge or rebase per `git.workflow.sync`.
```bash
python3 .agents/skills/feature-delivery/scripts/branchflow.py sync
```
If a conflict occurs, the script stops and leaves conflict markers in place for the user. It never resolves conflicts automatically.
If the branch has already been pushed to a remote and sync is set to rebase, pass `--phrase "yes rewrite branch <name>"`.

### 6. merge-local
Merges the approved task branch locally into the base branch or target branch.
```bash
python3 .agents/skills/feature-delivery/scripts/branchflow.py merge-local --approved --phrase "yes merge locally"
```
Preflight checks:
- Working tree must be clean.
- Project check command (`commands.check`) must exit 0.
- Branch must be synced with base.

Supports squash merge or standard merge commit per `git.workflow.merge_method`. Squash merges format the commit message and check it with `check_commit_message.py`. Never pushes to remote.

### 7. sync-main
Switches to the default branch, runs `git pull --ff-only`, and verifies the merge commit is present on the default branch.
```bash
python3 .agents/skills/feature-delivery/scripts/branchflow.py sync-main
```

### 8. park and resume
Park a task branch to switch to other work:
```bash
python3 .agents/skills/feature-delivery/scripts/branchflow.py park
```
Resume a parked task branch later:
```bash
python3 .agents/skills/feature-delivery/scripts/branchflow.py resume --task <slug>
```

### 9. abandon
Discard a task branch:
```bash
python3 .agents/skills/feature-delivery/scripts/branchflow.py abandon --approved --phrase "yes abandon <name>"
```
Sets status to `abandoned`, switches to the default branch, creates a local tag `abandoned/<slug>`, and keeps the branch.

### 10. cleanup
Delete the task branch after verifying proof of merge:
```bash
python3 .agents/skills/feature-delivery/scripts/branchflow.py cleanup --approved --phrase "yes delete branch <name>"
```
Checks for merge proof:
- `git branch --merged` contains the branch, OR
- State records status `merged` and the squash merge commit exists on the default branch.
Refuses deletion if proof is absent. Removes associated worktree if one was created.

### 11. revert-plan
Generates non-destructive revert instructions for a commit or branch using `git revert`:
```bash
python3 .agents/skills/feature-delivery/scripts/branchflow.py revert-plan <sha|branch>
```

## Hard Safety Rules

1. Never commit on the default branch when a task branch is active.
2. Never push to any remote.
3. Never force push without the typed rewrite phrase.
4. Never delete a branch without proof of merge and the typed delete phrase.
5. Never run `git reset --hard`, `git clean`, `git checkout -- .`, or destructive git commands.
6. Refuse to start with uncommitted changes in the working tree.

