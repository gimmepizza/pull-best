---
name: pull-best
description: Automated GitHub discovery and integration pipeline. Use when the user wants to find the best GitHub repos for any intent and integrate their skills/agents/tools into ~/.claude. Activates for phrases like "find best repos for X", "pull best tools for X", "set up my stack for X", "what should I install to build X".
origin: custom-built
tools: Bash, Read, Write, Glob
---

# Pull-Best: GitHub Discovery → Install Pipeline

A novel end-to-end pipeline for discovering the best GitHub repositories for any build intent
and automatically integrating their skills, agents, and tools into your global Claude Code setup.

## When to Use

- User says "I want to build X, find me the best tools"
- User asks "what are the best GitHub repos for Y?"
- User says "set up my stack for Z"
- User wants to explore a new domain and bootstrap their toolkit
- After a `/pull-best` run, to understand what was installed

## Core Script

Located at `../../../scripts/pull-best.py`.

Subcommands:
| Command | Use |
|---------|-----|
| `expand <intent>` | Generate 5 search angles from natural language |
| `score` | Score and rank repos JSON by quality signals |
| `extract <dir>` | Inspect cloned repo for extractable content |
| `install <dir> <prefix>` | Copy with namespace prefix, skip duplicates |
| `license <owner/repo>` | Check license safety via gh API |

## Scoring Formula

```
score = star_weight × recency × fork_ratio × boost
```

- `star_weight` = log10(stars+1) / log10(10001)  — log scale
- `recency` = 1.0 (<90d) | 0.75 (<1y) | 0.5 (<2y) | 0.3 (older)
- `fork_ratio` = 1.0 if 5–40% fork/star ratio | 0.8 otherwise
- `boost` = 1.0 + 0.1 per matching keyword (skill/agent/ai/quant/trading/research)

## License Safety

**Skip:** GPL-2.0, GPL-3.0, AGPL-3.0 (copyleft propagates to extracted content)
**Allow:** MIT, Apache-2.0, BSD-*, ISC, Unlicense, CC0, unspecified

## Extraction Rules

| Repo has | Extracted to |
|----------|-------------|
| `skills/*/SKILL.md` | `~/.claude/skills/<prefix>-<name>/` |
| `SKILL.md` (root) | `~/.claude/skills/<prefix>-<repo>/` |
| `.claude/skills/*/SKILL.md` | `~/.claude/skills/<prefix>-<name>/` |
| `agents/*.md` | `~/.claude/agents/<prefix>-<name>.md` |
| `commands/*.md` | `~/.claude/commands/<prefix>-<name>.md` |

## Discovery Ceiling Awareness

Claude Code caps skill index at ~8K characters (~32 skills). This pipeline is designed to be
**selective** — install only what's relevant to the stated intent. Don't bulk-install hundreds
of skills; quality over quantity.

After any batch install, run `/skill-health` to verify no conflicts and check context budget.

## GitHub Policy Compliance

- Uses `gh search repos` (GitHub API, not web scraping) — explicitly permitted
- Shallow clones (`--depth=1`) — minimal bandwidth
- No automated starring, following, or rank manipulation
- Rate limits: 5K API calls/hour, 30 search/min — well within normal use
- Extracts and redistributes only from non-copyleft licenses

## Integration with Other Skills

- Use with `skill-scout` before running — check if what you need already exists locally
- Use `continuous-learning-v2` after — capture patterns from what was installed
- Use `mem-learn-codebase` — have claude-mem learn the newly installed skills
- Run `/skill-health` after every install batch
- Run `/learn` after using new skills to capture what worked

## Example Session

```
User: /pull-best "real-time options flow analysis and sentiment"

Claude runs:
1. expand → 5 angles (options flow, sentiment analysis, derivatives data, etc.)
2. gh search × 5 → 47 repos found, deduplicated
3. score → top 12 shown
4. license → 2 GPL skipped, 10 proceed
5. clone + extract → 4 repos have SKILL.md/skills/agents
6. confirm → user approves 9 items from 4 repos
7. install → pb-* prefix, all items copied
8. report → "335 skills, 67 agents now available"
```
