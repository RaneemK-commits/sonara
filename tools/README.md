# tools/ — team tooling

> Back to the [project README](../README.md). Changes here are human decisions (role `lead`).

| Path | What it does |
|---|---|
| [board.py](board.py) | the team's message board: agents and humans talk through pinned issue #1 (`post`, `inbox`, `wait`, `log`, `whoami`) |
| [hooks/pre-commit](hooks/pre-commit) | file-ownership guard: each role may only commit its own files |

Enable once per clone:

```bash
git config core.hooksPath tools/hooks
git config hackathon.role <speech|device|ui|lead>
```

`SONARA_ROLE=<role>` in an agent's shell overrides the git config. Use it when one person runs two
agents from worktrees of the same clone. The rules are in [AGENTS.md](../AGENTS.md).
