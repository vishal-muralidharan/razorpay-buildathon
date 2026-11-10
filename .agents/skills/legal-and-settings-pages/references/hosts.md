# Hosting notes

Pick the section that matches the audit. Check the host's current docs for exact settings.

## Netlify

- Functions live in `netlify/functions/` unless `netlify.toml` sets another directory. A file named `delete-account.js` is served at `/.netlify/functions/delete-account`.
- Add server dependencies (for example `firebase-admin`) to `package.json`. Confirm the bundler picks them up. If the build fails on a native module, check the `node_bundler` and external modules settings in `netlify.toml`.
- Set credentials as environment variables in the site settings. Never commit them.
- SPA fallback: `/*  /index.html  200` in `public/_redirects` (or a redirect in `netlify.toml`). Confirm it covers the new routes, so direct loads and refreshes work.

## Vercel

- Functions live in `api/`. A file `api/delete-account.js` is served at `/api/delete-account`.
- Set credentials in the project's environment variables.
- SPA fallback: a rewrite in `vercel.json`, for example `{ "source": "/(.*)", "destination": "/index.html" }`. Vercel checks the filesystem and functions before rewrites, so `/api` keeps working. Confirm after deploy.

## Cloudflare Pages

- Functions live in `functions/`. A file `functions/api/delete-account.js` is served at `/api/delete-account`.
- Set credentials as environment variables or secrets in the project settings.
- SPA fallback: Pages serves `index.html` for unknown routes when there is no `404.html`. Confirm after deploy.

## Anything else

Use any server runtime that can hold admin credentials and verify the caller's token. The client must never hold those credentials.

## Always

- Never commit credentials.
- Tell the user the exact environment variable names to set, and where.
- Confirm the function path is picked up by the existing build setup.
