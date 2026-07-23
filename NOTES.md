# Maintenance notes

- When the user explicitly asks to publish the current repository state, use plain `git`; do not use `gh`.
- Inspect the worktree and intended scope, commit the changes intentionally, then ask the user for approval immediately before the `git push` tool call.
- Push to the branch the user explicitly names. For this repository, that may be `master`.
- If Git reports that `.git` access is denied, stop immediately and ask for permission; do not repeatedly retry or probe `.git\index`.
