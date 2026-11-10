# Page outlines

Section lists for each page and component. Keep the tone plain and readable, not dense legal language, but still specific. Every page gets: a page title, a meta description, a canonical link, and the last updated marker from the legal config. Use the framework's native head handling. Add a head library only if the stack has no native option.

Pull every specific (names, emails, dates, periods, regions, ages, law) from the legal config. If a value is still a marker, show the marker on the page.

## Terms of Service

1. Welcome, and what the app does.
2. Description of the service. State the current pricing from `product.paid_features`. If paid features may come later, say there will be notice.
3. Your content. Users own what they enter. The service claims no ownership and uses it only to run the service.
4. Acceptable use. No unlawful content. No abuse, scraping, reverse engineering or attacks. No access to other people's accounts.
5. Not professional advice. Any analytics or insights are informational. They are not medical, mental health, financial or professional advice. Adjust the wording to the product.
6. Accounts and termination. Keep credentials secure. Suspension and termination rights. Users can delete their account at any time.
7. Data backup. Point to the export tool. No guarantee against data loss.
8. Disclaimer of warranties ("as is" and "as available").
9. Limitation of liability.

## Privacy Policy

1. Information we collect: account data, user content (from the data inventory), preferences.
2. How we use it: provide the service, manage accounts, support, security. `[CONFIRM: product improvement use]`.
3. Third party services: name each processor from the audit, with its role. Data region from the config.
4. Retention, from the config. Data is deleted when the account is deleted.
5. Reminders and notifications, as described in `data.notifications`.
6. Your rights: short summary, with a link to the manage-my-data page.
7. Cookies, local storage and analytics: list what the audit found. State "no analytics" only if the config says so.
8. Security measures: only what is confirmed. A safe generic line is encryption in transit and owner only access rules, if the audit confirmed them.
9. Children, from `minimum_age`.
10. Changes to this policy.
11. Contact us, from `contact`.

## Terms and Conditions

Keep it distinct from the Terms of Service. General conditions only.

1. Eligibility, from `minimum_age`.
2. Changes to the service and to these terms. Continued use means acceptance.
3. Third party links and services. Not responsible for their content or privacy, including the sign in provider.
4. Governing law and jurisdiction, from `governing_law`.
5. Severability.
6. Entire agreement, together with the Terms of Service and the Privacy Policy.

If this would mostly repeat the Terms of Service, stop and tell the user. Do not pad it.

## Manage my data page (signed in)

1. Back link to Settings.
2. Data we process: list exactly what the data inventory shows.
3. Your rights: plain language for each right in the selected jurisdictions (see `laws.md`). For each, say how to use it in the app.
4. Tools: a "Download my data" button that exports JSON through the export helper. File name `<app>-data-export-YYYY-MM-DD.json`. Revoke the object URL after download. Show a success message. A link to the Danger Zone in Settings for erasure. Do not duplicate deletion logic.
5. Contact box, highlighted with theme tokens: grievance officer or privacy contact from the config.

## Settings page (signed in)

1. Account: display name (fall back to email), email, sign in method, Sign Out. Sign Out opens a confirm dialog. Only on confirm does it sign out.
2. Appearance: link to or embed the existing theme controls. Add this section only if no theme UI exists elsewhere.
3. Legal and privacy: links to the Terms of Service, Privacy Policy, Terms and Conditions and Manage my data.
4. Contact: the support email as a `mailto:` link.
5. Danger Zone, styled with the theme's danger tokens. List what deletion removes, in terms of the data inventory. Enable the delete button only when the user types exactly `DELETE`. Block double submit. On success: toast, clear local state, sign out, go to the login page. On failure: show the error and re-enable.

Sign Out lives in exactly one place: Settings. If it already exists elsewhere, flag it to the user before moving it.

## Terms agreement modal

Shows above all routes only when the user is signed in, has not agreed, and is not on the login route. Short explanation, links to the 3 legal pages in new tabs, a checkbox that must be ticked to enable Continue. On submit, write the consent fields and close.

## Signup consent checkbox

Required, unticked by default. Text names the Terms of Service, Terms and Conditions and Privacy Policy, each a link that opens in a new tab. Write the consent fields when the profile is created.

## Confirm dialog

Reusable. Props: title, message, confirm label, on cancel, on confirm. Fixed overlay with a scrim (clicking it cancels). Neutral cancel button. Danger styled confirm button. Focus trap. Escape cancels. Tokens only. Reuse an existing modal primitive if the project has one.

## Legal footer

Shown on public legal pages and, if suitable, the login page. Current year, the app name, and links to the Terms of Service and the Privacy Policy only. The other pages are reached through the signup text, the agreement modal, Settings and the manage-my-data page.
