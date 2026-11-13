Read [AGENTS.md](AGENTS.md) first and follow it: it defines the roles, file ownership, the message board and the hard rules.

- Your role is `git config hackathon.role` (or `$SONARA_ROLE`). Only write in that role's files.
- Talk to other agents only through `python tools/board.py`. When idle, run `board wait` in the background.
- Never add `Co-Authored-By:` lines or any AI attribution to commits, PRs, issues or board posts.
