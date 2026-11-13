# GitHub rules for READMEs and repo settings

These limits were current when this skill was written. `check_readme.py` holds them as constants. Update them there if GitHub changes them.

## Repository settings

- Description: 350 characters at most, on 1 line.
- Topics: 20 at most. Lowercase letters, digits, and hyphens. 50 characters each. Start with a letter or digit.
- Homepage: a full https URL, or empty.
- Social preview image: at least 640 by 320 pixels, 1280 by 640 recommended. Set it in the repository settings.
- The user applies these with the commands that `check_readme.py --print-gh` prints.

## Where GitHub looks for the README

GitHub shows the first README it finds in `.github/`, then the root, then `docs/`. Keep 1 README, in the root, unless the profile sets another path.

## Markdown that GitHub renders

- Relative links and images resolve from the README folder. Use them for files in the repo.
- Alerts start a quote with a marker such as NOTE, TIP, IMPORTANT, WARNING, or CAUTION in brackets.
- The details and summary elements collapse long sections.
- Mermaid diagrams render in fenced mermaid blocks.
- Light and dark images: a picture element with prefers-color-scheme sources.
- Heading anchors come from the heading text.
- Scripts, styles, and most HTML attributes are removed.

## Community health files

GitHub links these from the repository page when they exist: `LICENSE`, `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, `SUPPORT.md`. A `.github` repository on the owner account can supply defaults for every repo that has none of its own.
