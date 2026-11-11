---
name: feature-delivery
description: Run any goal in a project end to end through the build pipeline with an iterative verification loop. Dispatches features, bug fixes, code reviews, and release preparation through specialized workflows. Use it for every request to add, build, fix, review, audit, release, refactor, change or ship code in a repo that has a .agents/project-profile.yaml.
compatibility: Needs file read, file edit, shell, git, and Python 3.
---

# Feature delivery

The conductor for the pipeline. It does not hold rules of its own. It decides which skill runs when, and it enforces gates between stages. The profile and convention skills hold the rules.

## Core Principle: Goal-Oriented, Not Task-Oriented

Agents often stop once a task checklist is complete, even if the user's ultimate goal remains unmet or broken. This pipeline is goal-oriented:
1. Define verifiable acceptance criteria and invariants for the goal before starting.
2. Execute the steps incrementally with atomic commits.
3. Run an evaluation loop after verification. If any acceptance invariant fails, the agent diagnoses the delta, adjusts the plan, and loops until the goal is fully achieved.

## Read first

1. `.agents/project-profile.yaml`. If it is missing:
   - Existing code: run `project-bootstrap`.
   - New app: run `product-spec`, then `project-bootstrap`, then `scaffold-app`.
2. Pre-flight branch gate: Check `git branch --show-current`. If on `main` or `master` and the task is a feature or non-trivial fix, check `git.protected_branches` in the profile. Ask the user or create a feature branch (`feat/<name>` or `fix/<name>`) before writing code.
3. `git status`. If the working tree has uncommitted changes you did not make, tell the user and ask whether to commit them, stash them or continue. Never mix someone else's changes into your commits.
4. The repo map at `docs.repo_map`.
5. Run `python3 .agents/skills/extend-pipeline/scripts/refs.py verify`. If it reports a difference, tell the user and ask.
6. Run `python3 .agents/skills/project-blueprints/scripts/blueprint.py stale` at the start.
7. After the last commit run `python3 .agents/skills/project-blueprints/scripts/blueprint.py extract` for touched areas, then `python3 .agents/skills/project-blueprints/scripts/blueprint.py verify`.

Open only what each stage needs. Do not load every skill at the start. That wastes context and slows the work.

## Task router

Pick the workflow matching the request type:

| Request type | Workflow file |
|---|---|
| Bug fix or regression | `references/workflows/fix-bug.md` |
| Code review or diff audit | `references/workflows/review-changes.md` |
| Release preparation or version bump | `references/workflows/release-prep.md` |
| Incident, unwritten convention, or rule gap | `references/workflows/incident-to-rule.md` |
| Branch workflow and lifecycle | `references/workflows/branch-mode.md` |
| Feature or general delivery | Stages 0 to 8 below |

All workflows honor branch mode. If `git.workflow.mode` is set, or if the user requests working on a separate branch, follow `references/workflows/branch-mode.md`.

## Stages and gates

| # | Stage | Skill to use | Gate: do not continue until |
|---|---|---|---|
| 0 | Pre-flight & Branch | git, `branchflow.py` | Branch verified and working tree clean. Unless `git.workflow.mode` is `off` or `always`, ask: "Work on a separate branch?" If yes, run `python3 .agents/skills/feature-delivery/scripts/branchflow.py start --name <slug> --type <type>`. If mode is `always`, start branch without asking. |
| 1 | Audit & Goal Definition | `audit-and-planning` (phases 1 and 2), `repo-search` | Root cause diagnosed. Protected data identified. Current goal invariants and measurable acceptance criteria written to `.agents/work/CURRENT_GOAL.md` (updated for each task in a series). |
| 2 | Plan | `audit-and-planning` (phases 3 and 4) | Every step has a target, a verify command, and a commit message. Plan approved if over 5 steps or touching protected items. |
| 3 | Build step | Area convention skill (`build-ui`, etc.) | The step does 1 thing and follows the rules of its area. |
| 3a | Verify step | `targeted-module-testing`, step 1 | The step's checks pass with 0 errors and 0 warnings. |
| 3b | Commit step | `atomic-commits` | Message passes checker. Step committed. |
| 4 | Sync | `sync-skills-and-docs`, `rules-to-tests` | Profile, generated files, docs match code. Drift checker clean. |
| 5 | Full verify | `targeted-module-testing`, steps 1 to 3 | `commands.check` passes. Tests and browser checks pass. |
| 5a | Goal loop gate | `targeted-module-testing`, step 3b | All acceptance invariants from `CURRENT_GOAL.md` are evaluated. If all pass, proceed to stage 6. If any fail, re-enter loop. |
| 6 | Deploy (optional) | `targeted-module-testing`, step 4 | Runs only if `capabilities.deploy.enabled` is true. |
| 7 | Report | `targeted-module-testing`, step 5 | Post-Build Audit written. `CURRENT_GOAL.md` marked completed; advances to next task if in a series. |
| 8 | Hand off | `branchflow.py`, `targeted-module-testing` | When on a task branch, run `python3 .agents/skills/feature-delivery/scripts/branchflow.py handoff`. Wait for the user to choose: approve, changes requested, park, or abandon. |

Stages 1, 5 and 6 consult references through `due`. A gate reference with a blocking finding stops the stage until the user decides.

Repeat stages 3, 3a and 3b for each step in the plan. Never start step N+1 while step N fails its checks or is uncommitted.

## The Goal Loop

After Stage 5 (Full verify), do not assume the task is finished just because tests exited with code 0. Evaluate the goal:

1. Check every acceptance invariant in `.agents/work/CURRENT_GOAL.md`.
2. Inspect the live behavior, output data, or rendered UI against the goal.
3. Decision:
   - **Goal Achieved**: All invariants proven true. Proceed to stage 6, 7 and 8.
   - **Goal Not Achieved**: Identify the gap between current behavior and the desired goal. Add corrective steps to the plan, increment iteration count in `CURRENT_GOAL.md`, and loop back to Stage 3.
   - **Safety Limit**: If the goal is not met after 3 corrective iterations, pause. Present the exact gap, current test status, and options to the user for direction.

## Atomic Rollback Protocol

When working on Stage 3 and 3a:
- If a step fails verification, fix the issue and re-verify.
- If the same step fails verification 2 times in a row, do not fix forward blindly. Piling edits onto broken code causes compound failures.
- Roll back the failed step to the last clean commit with `git restore .` or `git reset --hard HEAD`.
- Re-read the step requirements, rethink the approach, and attempt a clean implementation.

## Keeping track with CURRENT_GOAL.md

Always record active task progress in `.agents/work/CURRENT_GOAL.md`. This file is the execution ledger for the currently active goal. It must always reflect the task currently underway, never a prior or finished task.

```markdown
# Current Goal: <active task objective>
Iteration: 1
Status: in_progress

## Series Queue (only when a series of goals or tasks was given)
- [x] Task 1: <first objective> (completed)
- [ ] Task 2: <current objective> (active)
- [ ] Task 3: <upcoming objective> (pending)

## Acceptance Invariants
- [ ] Invariant 1: <measurable outcome for current goal>
- [ ] Invariant 2: <expected behavior or contract for current goal>

## Plan Steps
- [x] Step 1: <target> (commit: <hash>)
- [ ] Step 2: <target> (current)
- [ ] Step 3: <target>

## Completed Goals History
- Task 1: <first objective> (completed at commit <hash>)
```

Update the checkboxes after each commit. If a session is interrupted or context is compacted, read `CURRENT_GOAL.md` and `git log` to resume immediately at the first uncompleted step.

## Handling a Series of Goals or Tasks

When the user provides a series, backlog, or list of goals/tasks:

1. **Initialize the Queue**: In Stage 1 of the first task, record all requested tasks under `## Series Queue` in `CURRENT_GOAL.md`. Set `# Current Goal:` to the first task.
2. **Active Goal Scope**: `# Current Goal:`, `Acceptance Invariants`, and `Plan Steps` must strictly cover the active task being executed, never mixed across multiple tasks.
3. **Execute One Goal at a Time**: Run the active goal through Stages 1 to 8 with the Goal Loop. Never mix acceptance invariants or plan steps from multiple tasks into the active section.
4. **Transition to the Next Goal**:
   - In Stage 7, mark the finished task as `[x]` in `## Series Queue` and record it under `## Completed Goals History`.
   - If pending tasks remain in the series:
     - Immediately update `CURRENT_GOAL.md` before starting the next task:
       - Update `# Current Goal:` to the next task's objective description.
       - Reset `Iteration: 1`.
       - Set `Status: in_progress`.
       - Replace `Acceptance Invariants` with the 2 to 4 measurable invariants for this new goal.
       - Replace `Plan Steps` with the atomic plan steps for this new goal.
       - In `## Series Queue`, mark the new task as `(active)`.
     - Re-enter Stage 1 (`audit-and-planning`) for the new task.
   - Do not leave `CURRENT_GOAL.md` showing an old or completed goal once work on the next task begins.

## When to stop and ask

Stop and ask the user when:

- A step would change a protected item or do something destructive.
- A rule in the profile conflicts with what the user asked for. Name both. Do not pick silently.
- A step fails verification twice and rollback does not resolve it. Show the evidence.
- The goal loop reached 3 iterations without achieving all acceptance invariants.
- You need a decision that is not in the profile or the spec.

## New app milestones

1. Read the milestone in `docs.spec`. Use its draft steps as the starting plan. `audit-and-planning` makes them concrete with real paths.
2. Run stages 0 to 8 through the goal loop.
3. When the milestone ships and its acceptance invariants pass, mark it done in the spec. Draft steps for the next milestone and show the user. Do not start without a yes.

## Final message

End with this:

```
Goal: <what was achieved and verified, in 1 or 2 sentences>
Iterations: <count of goal loop cycles>
Commits: <short hash and message for each>
Checks: <what ran and the result>
Docs synced: <profile, generated files, README, repo map: yes or what remains>
Rule gaps: <none, or missing rules discovered and whether codified>
Post-Build Audit: <known issues and open questions, from verify skill>
Next: <1 sentence>
```

Do not push. Pushing follows the profile's push policy and the user's request.
