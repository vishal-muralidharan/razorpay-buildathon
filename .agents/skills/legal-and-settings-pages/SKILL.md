---
name: legal-and-settings-pages
description: Add a Settings page, public legal pages (terms of service, privacy policy, terms and conditions), a manage-my-data page with export, terms consent on signup, and server side account deletion to any web app. Audits the repo first, collects the legal details in a config file, adapts to the app's auth provider, database and host, and leaves visible TODO and CONFIRM markers instead of invented legal facts. Use it whenever the user asks for a settings page, privacy policy, terms and conditions, GDPR, DPDP or CCPA pages, consent checkbox, delete my account, export my data, or "make the app legal ready", even if they only name one of these.
compatibility: Needs file read, file edit, shell, Python 3, and PyYAML.
---

# Legal and settings pages

A feature module. It runs through `feature-delivery`, one atomic step at a time. It produces templates in plain language. It is not legal advice, and it never claims that a product is compliant with any law.

## Rules for this module

1. **No fabrication.** Never invent dates, jurisdictions, age limits, retention periods, emails, officer names, or what the data schema contains. Use a visible `[TODO: ...]` or `[CONFIRM: ...]` marker. A wrong legal fact is worse than a visible gap.
2. **Match the codebase.** Follow the profile: layers, naming, existing contexts, existing components. Do not add a dependency that the stack already covers. Use the framework's native title and meta handling.
3. **Styling.** Use the project's tokens only, with no raw color values. Check every theme and mode the project has. Reuse the existing theme system. Do not build a new one.
4. **Plain language.** Readable, not dense legalese, but specific.
5. **Sign Out lives in exactly one place:** the Settings page. If it exists elsewhere (header, top bar), flag it to the user before you remove it. They may want it kept.
6. **Account deletion is always server side**, with admin credentials. The client must never delete its own auth record or profile.
7. **Do not break what exists.** `commands.check` must pass after every commit.

## Read first

1. `.agents/project-profile.yaml`.
2. `references/page-outlines.md` for every page and component.
3. Later, the adapter files that match the audit: `references/auth-firebase.md` or `references/auth-supabase.md`, and `references/hosts.md`. If the app uses another provider, follow the same pattern: consent fields, owner only access, server side deletion, client side export.
4. `references/laws.md`, only for the jurisdictions the user selects.
5. If a reference with category backend or database matches the project's provider, read it before you apply the adapter. It never overrides the access rules in the adapter.

## Steps

Run each step through `feature-delivery`: audit, plan, build, verify, commit. Use one commit per numbered step. Pages in steps 9 and 10 get one commit each.

### 0. Read only audit

Change nothing. Report:

- Routes, the providers tree, and which pages and contexts relate to auth, the user profile or the theme.
- Whether a Settings, Profile or theme page already exists. If so, extend it. Do not duplicate it.
- Every data location the app reads or writes (collections, tables, storage buckets, browser storage). This is the **data inventory**.
- The current security rules or RLS policies, if they are in the repo.
- Enabled sign in methods.
- The layout shell, and which routes render without it (focus or full screen routes).
- Footer, analytics, cookies and browser storage use, and how reminders or notifications are delivered.
- Host and function setup, SPA fallback, and how credentials reach the build.
- Whether any admin or role concept exists. Assume none unless found.

End with a short findings summary and a list of everything marked `[CONFIRM]` that blocks later steps.

### 1. Intake

Copy `assets/legal-config.template.yaml` to `.agents/legal-config.yaml`. Fill what the audit proved. Ask the user for the rest in 1 batch, with the questions grouped: contact and grievance details, jurisdictions, age and governing law, retention and data region, analytics and notifications, terms version. Anything unanswered stays a marker. Never default the jurisdictions.

### 2. Routes and access control

Add the routes named in `routes` in the config. Settings and the manage-my-data page need a signed in user, and redirect to login otherwise. The 3 legal pages are public.

- Signed in pages render inside the existing shell. Make sure fixed bars do not hide content.
- If the existing layout assumes a signed in user, add a light public layout: a top bar with the logo and a link to login or the app, plus the legal footer. A signed in visitor still needs sensible back navigation.
- None of these are full screen focus routes.
- Confirm the SPA fallback covers all 5 paths (see `references/hosts.md`).

### 3. Consent data model

Add `agreed_to_terms`, `agreed_to_terms_at` and `terms_version` to the existing user profile record. Do not create a new store. Treat records without the fields as not agreed. Write the data inventory to `docs/data-inventory.md`. It drives the privacy policy, the manage-my-data page and the export.

### 4. Access rules

Use the adapter. Tighten only what is needed. The profile record cannot be deleted by the client. User owned data is readable and writable only by its owner, and users can still delete their own single items. Deny everything else by default. If no rules file is in the repo, add one and tell the user it needs deploying.

### 5. Consent flow

Add the signup checkbox and the agreement modal for existing users. Put the consent state in the existing auth or user context. Do not add a new context unless unavoidable. See `references/page-outlines.md`.

### 6. Client API layer

Place it where the project keeps API helpers. Provide:

- `deleteUserAccount()`: gets a fresh token, sends it as a Bearer token to the server function, and throws a readable error on failure.
- `exportUserData()`: reads the profile and every location in the data inventory for the current user. Returns an object with keys that match the real data, plus `exported_at`. Excludes fields from `data.export_exclude_fields`.
- `acceptTerms()`: the consent write from step 5.

### 7. Server function

Use the adapter and `references/hosts.md`. Verify the caller's token. Delete user data, then the auth user. Data deletion failing is logged and not fatal. Auth deletion failing is fatal. Read credentials from an environment variable. Tell the user the exact variable names to set. Add the server dependency. Confirm the host picks the function up.

### 8. Settings page

Build it from `references/page-outlines.md`. Add an entry point to the desktop header and the mobile top bar. Do not add it to the bottom tab bar.

### 9. Manage my data page

Build it from the outline. Use `references/laws.md` for the rights of each selected jurisdiction. One commit.

### 10. Public legal pages

One commit each: terms of service, privacy policy, terms and conditions. Read the outline for each. Take every specific from the config. If the terms and conditions would mostly repeat the terms of service, stop and tell the user instead of padding.

### 11. Shared components

The confirm dialog and the legal footer. Reuse existing modal, toast and button components. Do not create duplicates.

### 12. Tests

Follow the project's test patterns. Cover:

- Route guards: signed out redirect for the 2 private routes, public access for the 3 legal pages.
- Settings: the sign out confirm flow, the delete button disabled until exactly `DELETE` is typed, double submit prevention, and failure handling.
- Manage my data: the export button starts a download, and the contact placeholders render.
- The agreement modal: shows only when expected, and Continue stays disabled until the box is ticked.
- Legal pages: key headings and markers render.

Then run `commands.check` and fix failures.

## Final report

Run `python3 .agents/skills/legal-and-settings-pages/scripts/check_legal_placeholders.py --root .` and use its output. If python3 is not found, use python or py -3. Report:

1. Every commit, in order.
2. Every unresolved marker, grouped by file, with its section.
3. The final route map, public and signed in.
4. A deployment checklist: environment variables to set, rules to deploy, redirects to confirm, manual steps.
5. Any place where the existing code conflicted with these instructions, and what you chose.
6. A reminder: these pages are templates. A qualified person should review them before launch.
