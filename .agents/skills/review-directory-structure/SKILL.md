---
name: review-directory-structure
description: Use this skill to place new files or move files in razorpay-buildathon. Describes each source layer and the root cleanliness rule.
---
<!-- build-forge:generated v1 body=e4668f3b7b6ed4f9c657c746cb98f8b554ca1d4f576fb85ad57d3c69fa50f508 -->

<!-- Generated from .agents/project-profile.yaml by project-bootstrap. Edit the profile, then re-render. -->

# Directory structure of razorpay-buildathon

| Path | Purpose |
|---|---|
| `backend/app/routers` | FastAPI route handlers |
| `backend/app` | Backend application models, jobs and logic |
| `backend/alembic` | Database schema migrations |
| `backend/scripts` | Seed and test simulation scripts |
| `backend/tests` | Backend pytest test suites |
| `frontend/src` | React UI dashboard components and views |

Tests: sit next to the file they test.

## Root

Allowed in the repo root: `FEATURES_AND_TESTING.md`. Put nothing else there.

## Before you add a file

Search first with `repo-search`. Reuse or extend an existing file when it fits.
<!-- BEGIN CUSTOM: notes -->
<!-- END CUSTOM: notes -->
