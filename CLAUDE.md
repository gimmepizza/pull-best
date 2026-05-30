# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A single-purpose Claude Code plugin that provides the `/pull-best` slash command. Given a natural language build intent, it searches GitHub across 5 angles, scores repos by quality signals, checks licenses, clones candidates, extracts skills/agents/commands, and installs them into `~/.claude`.

## Running the Script

```bash
# Generate 5 search angles for an intent
python scripts/pull-best.py expand "crypto sentiment analysis"

# Score and rank repos from gh search JSON output
echo '<json>' | python scripts/pull-best.py score
# or from a file:
python scripts/pull-best.py score repos.json

# Print a ranked table (score + expand + search in one step)
python scripts/pull-best.py full-run "options backtesting"

# Inspect a cloned repo for extractable content
python scripts/pull-best.py extract /tmp/pull-best/<repo-name>

# Install extracted items with a namespace prefix
python scripts/pull-best.py install <items-json-file> <prefix> [--dry]

# Check license via GitHub API
python scripts/pull-best.py license owner/repo
```

Requires `gh` CLI authenticated (`gh auth login`) and Python 3.10+.

## Architecture

All logic lives in one file: `scripts/pull-best.py`. The `.claude/` directory wires it into Claude Code.

```
scripts/pull-best.py          — discovery, scoring, extraction, install engine
.claude/commands/pull-best.md — slash command definition (/pull-best)
.claude/skills/pull-best/
  SKILL.md                    — skill spec (when/how Claude should invoke the pipeline)
```

**Pipeline stages** (as invoked by the `/pull-best` command):
1. `expand` → 5 search angles from intent
2. `gh search repos` × 5 angles → deduplicated repo list
3. `score` → composite rank (star weight × recency × fork ratio × keyword boost)
4. `license` per repo → skip GPL-2.0/3.0/AGPL-3.0
5. `git clone --depth=1` + `extract` → find `skills/*/SKILL.md`, `agents/*.md`, `commands/*.md`
6. User confirms → `install` copies with `pb-<owner>` namespace prefix into `~/.claude`
7. Appends a session summary to `~/.claude/pull-best.log`

**Scoring formula:**
```
score = star_weight × recency × fork_ratio × boost
```
- `star_weight` = log10(stars+1) / log10(10001)
- `recency` = 1.0 (<90d) | 0.75 (<1y) | 0.5 (<2y) | 0.3 (older)
- `fork_ratio` = 1.0 if 5–40% fork/star ratio | 0.8 if fewer | 0.7 if more
- `boost` = 1.0 + 0.1 per matching keyword (max 1.5)

**Extraction targets** (what `inspect_repo` looks for):
- `skills/*/SKILL.md` or `SKILL.md` at root or `.claude/skills/*/SKILL.md`
- `agents/*.md` or `.claude/agents/*.md`
- `commands/*.md` or `.claude/commands/*.md`
- `hooks/hooks.json` or `.claude/hooks/hooks.json`

**Install paths:**
- Skills → `~/.claude/skills/<prefix>-<name>/`
- Agents → `~/.claude/agents/<prefix>-<name>.md`
- Commands → `~/.claude/commands/<prefix>-<name>.md`

Installs are idempotent — existing destinations are skipped, not overwritten.

## Constraints

- Only `MIT, Apache-2.0, BSD-*, ISC, Unlicense, CC0, LGPL, MPL-2.0, unspecified` licenses are installable.
- Skill index in Claude Code caps around 8K characters (~32 skills) — install selectively.
- GitHub rate limits: 30 search req/min, 5K API calls/hour.
- Run `/skill-health` after any install batch to check for conflicts.
