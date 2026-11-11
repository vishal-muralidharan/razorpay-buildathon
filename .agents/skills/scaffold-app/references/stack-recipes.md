# Stack recipes

Each recipe gives the shape of the work, not exact commands or versions. Look up the current generator command and flags in the framework's own docs before you run it. Versions and flags change.

## Contents

1. Web app with React and Vite
2. Web app with a full stack framework (Next.js, Nuxt, SvelteKit, Remix, Astro)
3. Vue or Svelte with Vite
4. Node API or server
5. Python app or API
6. Command line tool
7. Mobile app with Expo
8. Anything else

## 1. Web app with React and Vite

- **Generator:** the Vite create tool with the React template (JavaScript or TypeScript to match `stack.language`).
- **Tests:** Vitest with Testing Library, jsdom environment, 1 setup file.
- **Lint:** the linter named in `stack.linter`. Add a `lint` script.
- **Check:** `lint`, `test`, `build` chained by `ensure_check_script.py`.
- **Layout:** the template puts files in `src/`. Move them into the profile's layers. Entry files stay at `src/` root.
- **Gotchas:** keep `index.html` in the root. If routing is needed, add the router named in `stack.router`. React 19 supports `<title>` and `<meta>` tags in components, so no head library is needed.

## 2. Web app with a full stack framework

- **Generator:** the framework's official create tool. Choose the options that match the profile (language, styling, router).
- **Tests:** the runner in `stack.test_runner`. Add it if the generator did not.
- **Check:** use the framework's lint and build. Add `test`.
- **Layout:** respect the framework's required folders (for example the routes folder). Record them as layers in the profile if they are missing.
- **Gotchas:** these frameworks have conventions the profile cannot override. Update the profile to match the framework, not the other way round.

## 3. Vue or Svelte with Vite

- **Generator:** the Vite create tool with the matching template.
- **Tests:** Vitest with the framework's testing library.
- **Layout and check:** same method as recipe 1.

## 4. Node API or server

- **Generator:** `npm init` plus the framework named in `stack.framework`, or its official starter.
- **Tests:** the runner in the profile, with 1 test that boots the app and calls a health route.
- **Layout:** routes, handlers, services, config. One layer each.
- **Gotchas:** read configuration from environment variables. Create an example env file with names only, no values.

## 5. Python app or API

- **Generator:** the project tool named in the profile (for example `uv init` or `poetry new`). If none is named, ask.
- **Tests:** pytest with 1 smoke test.
- **Lint and format:** the tool in `stack.linter`.
- **Check:** a single command, usually a `Makefile` target or a task runner entry, that runs lint, tests and any build step.
- **Gotchas:** pin a Python version in the project file. Use a virtual environment folder that git ignores.

## 6. Command line tool

- **Generator:** the language's standard project tool.
- **Tests:** 1 test that runs the command with `--help` and checks the exit code.
- **Layout:** entry point, commands, core logic. Keep core logic free of printing so it is testable.

## 7. Mobile app with Expo

- **Generator:** the official Expo create tool, with the TypeScript or JavaScript template.
- **Tests:** the runner the template provides.
- **Gotchas:** device features need a development build or a simulator. Say so in the README. Do not run emulators during scaffolding.

## 8. Anything else

Find the official starter for the stack. If there is none, create the smallest possible project by hand: 1 entry file, 1 test, 1 lint config, 1 check command. Tell the user which parts you wrote by hand.
