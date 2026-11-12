# Interview question banks

Ask in as few messages as possible. Offer a default with every question. Accept "you decide". Never ask what discovery or the existing docs already answer.

## New mode: 3 rounds

### Round 1: product

1. What does the app do, in 1 sentence?
2. Who uses it, and on which platforms (web, installable web app, desktop, mobile, command line, API)?
3. What is the one thing it must do fast or well?
4. Does it need accounts, or should it work without sign in?

### Round 2: stack

1. Language and framework. Default: the most common choice for the platform.
2. Styling approach. Default: plain CSS with design tokens.
3. Where does data live: on the device, on a server, or both?
4. Backend or database, if any. Default: none until needed.
5. Test runner and linter. Default: the ones the bundler's ecosystem uses.
6. Where will it be hosted, if anywhere? Default: undecided. Do not enable deploy.

### Round 3: design and data

1. Visual direction in 1 phrase (for example monochrome, playful, dense, calm).
2. Themes: single, or light and dark.
3. Smallest and largest screen width to support. Default: 320 and 2560.
4. Copy style: plain sentences, or minimal labels.
5. The 1 to 3 data rules that must never break (for example one timestamp per record).
6. What needs your approval before it changes (storage keys, schema, public API).
7. Branch workflow: default branch (detected from git or main), whether you use pull requests, merge method (merge, squash, rebase; default: merge), and workflow mode (ask, always, off; default: ask).

Turn each answer into profile fields and rules. Do not keep the answer only in chat.

## Existing mode: gap questions

Ask only the ones discovery could not answer. Maximum 5 per batch.

1. Which command should be the single `check` command?
2. Is the guess for each folder's purpose right? List only the uncertain ones.
3. Which rules in the existing docs are enforced by a test or lint rule, and which are only habit?
4. What needs your approval before it changes?
5. Should agents ever push to the remote? Default: never.
6. Branch workflow: default branch (detected: <branch>), whether you use pull requests, merge method (merge, squash, rebase; default: merge), and workflow mode (ask, always, off; default: ask).
