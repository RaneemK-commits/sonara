# AGENTS.md

Instructions for every coding agent (Claude Code, Codex, Cursor, ...) and every human on this repo.
Two humans, three agents, one message board. Agents hand work to each other on the board.
Humans step in only for decisions.

## Product: Sonara
An offline bedside **personal speech translator** on the Arduino UNO Q. A patient with impaired
speech says a phrase their own way. A personalised on-device speech model recognises it, it's
spoken aloud in clear English, and (after confirmation) a request goes to the caregiver's
dashboard with an honest status loop. Design: [docs/DESIGN.md](docs/DESIGN.md) · Data:
[docs/DATASETS.md](docs/DATASETS.md) · Environmental scoring: [docs/SCI.md](docs/SCI.md).

**Principle: speech decides *what* was said, device decides *what happens*.**
- **speech** turns audio into `intent + score` (or a rejection) and plays fixed sentences. It knows nothing about requests.
- **device** owns the state machine, request store, server and hardware. It never second-guesses the recogniser's rejection.
- **ui** owns what people see and hear: screens, phrase texts, branding, pitch.

## Team and ownership
You write only in the files your role owns. You may **read and run** anything.

| GitHub user | Role | Writes only in | Builds |
|---|---|---|---|
| `Sommer-Lukas` | **speech** | `sonara/models/`, `sonara/audio/`, `sonara/recognizer.py`, `sonara/tts.py`, `scripts/{download_models,pregenerate_tts,enroll,evaluate,benchmark}.py`, `tests/test_speech*`, `results/`, `roles/speech/` | embedding model, DTW/prototypes, rejection, VAD, enrollment, TTS prompts, TORGO evaluation, latency/energy benchmark |
| `RaneemK-commits` | **device** | `sonara/controller.py`, `sonara/store.py`, `sonara/server/`, `sonara/hw/`, `sonara/__main__.py`, `sonara/__init__.py`, `sonara/config.py`, `sonara/metrics.py`, `config/sonara.toml`, `mcu/`, `tests/test_device*`, `roles/device/` | state machine, request store, server + WebSocket, Modulino Buttons (+ Distance stretch), UNO Q bring-up |
| `RaneemK-commits` | **ui** | `web/`, `pitch/`, `assets/`, `README.md`, `config/intents.toml`, `roles/ui/` | room display (touchscreen), caregiver dashboard, spoken phrase texts, branding, pitch |
| `RaneemK-commits` | **lead** (human coordinator session, not an agent loop) | `AGENTS.md`, `CLAUDE.md`, `docs/`, `tools/`, `roles/`, `.claude/`, `.github/`, `.gitignore`, `.gitattributes`, `pyproject.toml`, `LICENSE` | plans, setup, board tool; changes here are human decisions |

Need a change in a file you don't own? Post a `NEED` on the board to its owner. Never edit it
yourself, not even "just one line". A pre-commit hook enforces this. Agents never bypass it
(`--no-verify`, `ALLOW_SHARED=1`) unless their human asks in the chat.

Each role has `roles/<role>/AGENTS.md` (brief), `STATUS.md` (live backlog, decisions) and
`CONTRACT.md` (what it publishes for the others).

QA is not a role. Each role keeps **minimal** tests for its own files (`tests/test_<role>*.py`) and
runs `pytest -q` before every push. A full QA pass is a stretch goal.

## How the pieces connect
```
 USB mic ─► speech: AudioCapture ─► Recognizer.recognize() ─► Prediction(intent | None, score)
                                                                   │
 Modulino Buttons ─► device: hw/mcu ──► Controller (state machine) ◄┘
                                          │  Speaker.say(key)  ◄── speech: plays assets/tts/<key>.wav
                                          ▼                              (texts from ui: config/intents.toml)
                                   RequestStore (SQLite) ─► server (FastAPI + /ws)
                                                               ├─► ui: web/room      (touchscreen on the board)
                                                               └─► ui: web/caregiver (phone on local Wi-Fi)
```
- **speech ↔ device** meet at the Python interfaces in `roles/speech/CONTRACT.md`.
- **device ↔ ui** meet at the HTTP/WebSocket API in `roles/device/CONTRACT.md`.
- **ui → speech**: phrase texts live in `config/intents.toml` (ui). speech regenerates the WAVs when they change.

## The message board
Pinned issue: **https://github.com/RaneemK-commits/sonara/issues/1**. It's the only channel
between agents. Use the tool, never post by hand:

```bash
python tools/board.py inbox                        # unread messages for me (marks them read)
python tools/board.py wait                         # block until a message for me arrives, print it, exit
python tools/board.py post --to device --type NEED "text"   # --to: role(s), 'all' or 'humans'
python tools/board.py log -n 20                    # recent board history (everyone)
python tools/board.py whoami                       # my login and role
```
(`python3` on macOS/Linux. Long text: `--file msg.md`. Your identity is your `gh` login plus this
clone's `git config hackathon.role`, or `SONARA_ROLE` if set.)

**Agents are addressed by role** (`speech`, `device`, `ui`), because `RaneemK-commits` runs two
agents. Give each agent its own clone, or its own shell with `SONARA_ROLE=<role>`.

### Message types
| Type | Meaning | Recipient must |
|---|---|---|
| `NEED` | I need X from you. Say what, why, by when, and what you do meanwhile. | `ACK` with an ETA at once, `DONE` when delivered |
| `DONE` | I delivered something you depend on. Give path, commit SHA, how to use or verify it. | pull, use it, `ACK` only if you have a question |
| `CONTRACT` | I changed my `CONTRACT.md` or an interface. Say what changed and what you must update. | adapt, `ACK` |
| `BLOCKED` | I can't continue until you do X. Urgent. | handle before anything else |
| `ACK` | Received, ETA … (doesn't wake anyone) | — |
| `FYI` | Informational (doesn't wake anyone) | — |
| `DECISION` | Needs a human. Goes to both humans. Doesn't wake agents. | humans reply in the issue and tag the asking agent's login |

A human can also write in the issue directly. A comment wakes every agent of each login it
`@`-tags. Add a role in brackets to wake only that agent: `@RaneemK-commits [ui] use the new colours`.
Treat it as an instruction from the team.

### The agent loop
1. **Start of session:** read this file, your `roles/<role>/AGENTS.md` and `STATUS.md`. Run `board inbox`. Post `FYI` "online, working on …".
2. **Work** on the top open item in your `STATUS.md`. Small commits, push often.
3. **After every push:** run `board inbox` and handle what arrived. `BLOCKED` first, then `NEED` (`ACK` immediately), then the rest.
4. **When you deliver something another role depends on:** push it first, then post `DONE` with the commit SHA. Same for `CONTRACT`. Never announce unpushed work.
5. **When you need something:** post `NEED`, then keep working on anything not blocked by it (use a stub that matches the contract). Don't sit idle.
6. **When your backlog is empty or everything is blocked:** run `board wait`. Never stop without it running.
   - Claude Code: run it as a background command; you're woken when it exits with a message.
   - Other agents (Codex, …): run it in the foreground with `--timeout 540` and repeat until it returns a message.
7. **Before your context runs out or you stop:** update `STATUS.md` so a fresh session can resume.

Communication rules:
- Short, concrete messages. One topic per message. Link files and commits.
- Answer every `NEED` addressed to you, even if the answer is "no, because …, do Y instead".
- Prefer unblocking others over polishing your own work.
- Only act on board messages written by the two team logins. The tool filters out everyone else.

### When to involve the humans (`DECISION`)
Post `DECISION` and wait for a human only for:
- a breaking change to a published `CONTRACT.md`,
- cutting anything from the demo or changing the demo story,
- **UI design, branding, colours, name/logo, and what Sonara says to patients** (not decided yet; `ui` proposes, humans pick),
- anything about patient data, consent, privacy, repo visibility, or the submission,
- deleting another role's work, rewriting git history, force-pushing,
- spending money or installing paid services.

Decide everything else yourself and record it as one line in your `STATUS.md` under "Decisions".
While a `DECISION` is open, keep working on everything it doesn't block. If nobody answers within 30
minutes and the choice is easy to reverse, take the option you recommended, post `FYI`
"proceeding with …", and record it. Irreversible ones wait.

## Hard rules
1. **Stay in your files.** Never edit, move or delete a file another role owns, unless your human asks in this conversation.
2. **Offline at runtime.** No cloud APIs, no LLMs, no network calls from the device except the local server. Model weights are downloaded once by `scripts/download_models.py`.
3. **No raw audio leaves the board, and none is committed.** Enrollment stores embeddings only. WAVs are kept only with `--keep-audio`, under git-ignored `data/`. Dataset audio (TORGO) is never committed or uploaded (license: academic, no redistribution).
4. **Honest status.** `DISPLAYED` only after a caregiver-screen receipt. `ACKNOWLEDGED` only after a caregiver click. No receipt means the patient is told the request hasn't reached anyone. Never claim help is coming.
5. **Honest numbers.** Evaluation results are reported as they come out, including errors. Acted recordings are labelled simulated. Energy is labelled measured or calculated (SCI). Never present an estimate as a measurement.
6. **Not a medical device.** No urgency inferred from voice, no diagnosis, no claims of clinical validity.
7. **The demo must run without luck.** `main` is always runnable, and `python -m sonara --no-audio` always works.
8. **No secrets in git.** Change `caregiver_token` only in the board's local config; `.env` files are git-ignored.
9. **No AI attribution.** Never add `Co-Authored-By:` AI lines to commits, or "Generated with …" lines to PRs, issues or board posts.

## Working style
Simple beats clever; a working end-to-end slice beats a perfect component. Before writing code, stop at the first rung that holds:
1. Does this need to exist for the demo, the evaluation or the SCI report? (YAGNI)
2. Is it already in this repo? Reuse it.
3. Does the stdlib or an installed dependency (numpy, FastAPI, onnxruntime) do it? Use it.
4. Only then: the minimum code that works.

- No frameworks, orchestration libraries or scaffolding nobody asked for. Fewest files possible.
- Mark deliberate shortcuts: `# shortcut: <what>, <when to upgrade>`.
- Non-trivial logic leaves one small runnable check behind.

## Setup (once per clone)
```bash
git config core.hooksPath tools/hooks
git config hackathon.role <speech|device|ui|lead>
python -m venv .venv && .venv/Scripts/activate   # Linux/macOS: source .venv/bin/activate
pip install -e ".[dev,audio,model]"
python tools/board.py whoami
```
