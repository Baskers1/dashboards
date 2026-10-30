# Claude Code mods

Six mods that change how Claude Code itself behaves, published from this repository
as a plugin marketplace so any session on any machine can install them.

## Install

Add the marketplace once per machine, then install what you want:

    /plugin marketplace add baskers1/dashboards
    /plugin install guardrails --marketplace baskers-mods

Each mod installs on its own, so you can take the guardrails without the chime.

## What each one does

| Mod | Surface | Behaviour |
| --- | --- | --- |
| `guardrails` | tool calls | Denies force-pushes to shared branches, hard resets, working-tree wipes, risky recursive deletes, unreviewed Terraform changes, bulk `kubectl delete`, destructive SQL and fork bombs. Blocks AWS, GitHub, Anthropic, OpenAI, Slack and Google keys, private keys, JWTs and hard-coded credentials in shell commands, file writes and edits. Documented placeholders pass. |
| `session-pulse` | status line, band, audio | Context fill, turn count and last-turn length on the status line; session spend above the prompt, amber past $5; a toast and a chime when a turn runs past 60 seconds. |
| `task-pane` | pane | Lists every ask of the session, open / done / interrupted, with durations. `/tasks` reopens it. |
| `house-style` | system prompt | Appends a GOV.UK content, WCAG 2.2 AA and Service Standard brief. `/house-style` toggles it; the choice persists across sessions. |
| `decision-log` | prompts, answers, files | `/decided <what>` appends a dated line to `memory/decisions.md`. Also catches decisions stated in prompts and answers, while ignoring hedged proposals. |
| `ship-kit` | commands | `/adr <title>` writes a numbered ADR skeleton in `docs/adr/`. `/ship` detects the repo's own checks, runs them, and pushes only if every one passes — refusing on a protected branch. `/ship check` stops before pushing. |

## Working on them

Each mod is a standalone plugin folder. From `claude-mods/`:

    claude plugin validate <mod>
    claude plugin test <mod>

`tsconfig.json` in each folder points at `.claude-plugin/types/`, which the engine
writes when it loads the mod. Those generated types are not committed; load the mod
once before type-checking.

Note that `guardrails`, once live, denies shell commands that merely *contain* the
patterns it guards — including heredocs writing its own tests and this README. Edit
those files with the file tools rather than the shell.

## Known limits

- `/ship`'s push and draft-PR steps are not covered by tests — only its refusal to
  run on a protected branch is. Run `/ship check` first on a repo you care about.
- Spend is shown in US dollars, because that is the unit the API reports.
- The test files' fixture literals are looser than the engine's own types, so
  `tsc` reports errors in `*.test.ts` while every hook module type-checks clean.
