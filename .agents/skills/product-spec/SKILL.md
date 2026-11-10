---
name: product-spec
description: Turn a rough app idea into a short product spec with users, core flows, data entities, non-goals, milestones and a first list of atomic build steps. Use it at the very start of a new app, before project-bootstrap, and whenever the user says "I want to build", "I have an idea for an app", "plan this app", "write a spec", "what should the milestones be" or describes an app without technical details. Also use it to cut a big feature into milestones for an existing project.
compatibility: Needs file read and file edit capabilities.
---

# Product spec

Stage zero for a new app. A spec keeps the build small and ordered, and it lets `project-bootstrap` skip most of its interview. Keep it short. A spec that runs past 2 pages will not be read.

## Read first

If `.agents/project-profile.yaml` exists, read it. Use its stack, rules and layers as constraints. If a spec already exists (`docs.spec`, or `docs/product-spec.md`), update it instead of starting over.

## Steps

1. **Capture the idea.** Ask for the idea in 1 sentence if the user has not given it. Do not ask more than 4 questions in total. Offer a default for each. Good questions:
   - Who is it for, and what do they do today instead?
   - What is the one thing it must do well?
   - Which platform: web, installable web app, desktop, mobile, command line or API?
   - Does it need accounts or a server, or can it live on the device?
2. **Write the spec** to `docs/product-spec.md` using `references/spec-template.md`. Use plain words. Mark every guess as `ASSUMPTION:` so the user can correct it.
3. **Cut milestones.** Each milestone is something a user can try. Milestone 1 is the thinnest working slice, not a foundation layer. A milestone has 3 to 8 build steps.
4. **Draft the build steps** for milestone 1 only. Each step names one functional unit and what proves it works. `audit-and-planning` will refine them with real file paths later.
5. **List non-goals.** Name at least 3 things the app will not do in version 1. This is the best defense against scope creep.
6. **Confirm with the user.** Show a summary of the goal, milestone 1 and the non-goals. Fix what they correct.
7. **Hand off.** If the profile does not exist, run `project-bootstrap` in new mode. If `docs.spec` is empty in the profile, set it to the spec path.

## Rules

- No technology choices in the spec unless the user stated them. Stack decisions belong in the profile.
- No feature that has no user and no flow. Every feature traces to a flow.
- Every data entity lists the fields the flows need and nothing more.
- Do not invent numbers: user counts, deadlines, prices. Leave a `TODO:` marker.
- Do not write code.
