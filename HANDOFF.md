TASK: Remove TokenHarbor gateway and fcc setup from the user's Mac; explain the ANTHROPIC_MODEL deepseek warning; explain /usage overage.
STATE: done (Mac cleanup verified); residual: thk_live lines in ~/.zsh_history not scrubbed.
FILES: /Users/baskersimac/.claude/settings.json; /Users/baskersimac/.zshrc; /Users/baskersimac/.zsh_history (unscrubbed); /Users/baskersimac/.tokenharbor (deleted); cloud env dashboards allowlist (env_011rHQnLFrmnxq6ZHSZ87qYF, 8 MCP hosts).
DECISIONS:
- TokenHarbor removed completely; user revoked the key, so no rotation needed.
- Kept the 8 MCP hosts on the dashboards environment (user approved all 8).
- Did not use fcc. User is on Ultra overage billing until the subscription limit resets; check claude.ai/settings/usage.
NEXT: Decide whether to scrub thk_live lines from ~/.zsh_history (back up first, then grep -v to a temp file and move it back).
GOTCHAS: Diagnostic greps typed the key prefix into zsh history. zsh -xl does not source .zshrc, so it cannot confirm shell exports. Key appeared in chat output; revoked. ~/.claude/projects grep was clean.
