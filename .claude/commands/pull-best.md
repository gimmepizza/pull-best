---
description: Discover, score, and install the best GitHub repos for any build intent into ~/.claude. Searches GitHub across 5 angles, ranks by quality, checks licenses, extracts skills/agents/commands, installs globally.
argument-hint: "<what you want to build or research>"
allowed_tools: ["Bash", "Read", "Write", "Glob", "Grep"]
---

# /pull-best

**Automated GitHub discovery -> score -> extract -> install pipeline.**

Find the best GitHub repositories for any build intent and integrate their skills, agents, and commands directly into your global Claude Code setup.

The engine lives at `~/.claude/scripts/pull-best.py`. All subcommands below call it directly — it works from any working directory.

## Input

`$ARGUMENTS` — natural language description of what you want to build or research.

Examples:
- `/pull-best crypto sentiment analysis`
- `/pull-best touchdesigner generative AI visuals`
- `/pull-best options backtesting portfolio optimization`
- `/pull-best local LLM agent memory system`

---

## Execution Pipeline

### Phase 1: Expand Intent

Generate 5 search angles from the intent, then add 2 more based on your own analysis:

```bash
python ~/.claude/scripts/pull-best.py expand $ARGUMENTS
```

Present all 7 angles to the user and confirm before searching.

### Phase 2: Search GitHub

For each angle, search GitHub via the CLI:

```bash
gh search repos "<angle>" \
  --sort stars --order desc --limit 10 \
  --json fullName,stargazersCount,forksCount,language,description,pushedAt
```

Collect all results, deduplicate by `fullName`, giving ~40-60 unique repos.

### Phase 3: Score and Rank

Pipe the deduplicated JSON through the scorer:

```bash
echo '<json>' | python ~/.claude/scripts/pull-best.py score
```

The scorer applies:
- **Star weight** (log scale — prevents mega-repos dominating)
- **Recency** (1.0x < 90 days, 0.75x < 1 year, 0.5x < 2 years, 0.3x older)
- **Fork ratio** (rewards healthy 5-40% fork/star ratio)
- **Keyword boost** (1.1-1.5x for skill/agent/AI relevance in description)

Present the **top 12** repos with scores. Let the user deselect any before proceeding.

### Phase 4: License Check

For each selected repo:

```bash
python ~/.claude/scripts/pull-best.py license <owner/repo>
```

**Auto-skip** GPL-2.0, GPL-3.0, AGPL-3.0 with a warning.
**Continue** for MIT, Apache-2.0, BSD-*, ISC, Unlicense, and unspecified.

Show the license verdict table.

### Phase 5: Clone and Inspect

For each license-approved repo (process in parallel batches of 4):

```bash
git clone --depth=1 https://github.com/<repo> /tmp/pull-best/<name>
python ~/.claude/scripts/pull-best.py extract /tmp/pull-best/<name>
```

Show the inspection summary: how many skills/agents/commands found per repo.

### Phase 6: Confirm and Install

Present the full extraction plan:
```
Repo: owner/repo (MIT, 12.4K stars)
  -> 3 skills: skill-name-1, skill-name-2, skill-name-3
  -> 1 agent: agent-name.md
  -> 0 commands
  Prefix: pb-ownr  (auto-derived from repo owner, max 6 chars)
```

Ask: "Install these 11 items from 4 repos? (y/n/edit)"

On confirm, run:

```bash
python ~/.claude/scripts/pull-best.py install /tmp/pull-best/<name> <prefix>
```

### Phase 7: Log and Report

After each install, the script automatically appends to `~/.claude/pull-best.log`.

View recent history:
```bash
python ~/.claude/scripts/pull-best.py log
```

Final summary:
```
/pull-best "crypto sentiment analysis"

Searched: 7 angles -> 52 unique repos -> 12 top-scored -> 9 license-approved
Inspected: 9 repos -> 4 had extractable content
Installed:
  + pb-coinbase-skills  -> 3 skills
  + pb-finbert         -> 1 skill
  + pb-openbb-news     -> 1 skill, 1 agent
  + pb-localllm-fin    -> 2 skills

~/.claude now has 335 skills, 67 agents, 82 commands.
Run /skill-health to verify no conflicts.
```

---

## Options

- `--dry` — Show what would be installed without installing
- `--no-confirm` — Skip confirmation prompts
- `--limit N` — Search top N repos per angle (default 10, max 20)
- `--lang python|typescript|rust|go` — Filter by language
- `--min-stars N` — Minimum star count (default 100)

---

## Notes

- Uses GitHub API (not scraping) — within ToS, rate-limited to 30 search req/min
- All installs are namespace-prefixed (`pb-` + derived slug) to avoid conflicts
- Shallow clones (`--depth=1`) — fast, low bandwidth
- GPL/AGPL repos are always skipped — prevents license propagation
- Run `/skill-health` after any batch install to check for conflicts
