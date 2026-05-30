---
description: Discover, score, and install the best GitHub repos for any build intent into ~/.claude. Searches GitHub across 5 angles, ranks by quality, checks licenses, extracts skills/agents/commands, installs globally.
argument-hint: "<what you want to build or research>"
allowed_tools: ["Bash", "Read", "Write", "Glob", "Grep"]
---

# /pull-best

**Automated GitHub discovery â†’ score â†’ extract â†’ install pipeline.**

Find the best GitHub repositories for any intent and integrate their skills, agents, and tools directly into your global Claude Code setup.

## Input

`$ARGUMENTS` â€” natural language description of what you want to build or research.

Examples:
- `/pull-best crypto sentiment analysis`
- `/pull-best touchdesigner generative AI visuals`
- `/pull-best options backtesting portfolio optimization`
- `/pull-best local LLM agent memory system`

---

## Execution Pipeline

### Phase 1: Expand Intent

Use `pull-best.py expand` to generate 5 search angles, then add 2 more based on your analysis of the intent:

```bash
python "$PSScriptRoot/../../scripts/pull-best.py" expand $ARGUMENTS
```

Present the 7 angles to the user and confirm before searching.

### Phase 2: Search GitHub

For each angle, search GitHub via the CLI:

```bash
gh search repos "<angle>" \
  --sort stars --order desc --limit 10 \
  --json fullName,stargazersCount,forksCount,language,description,pushedAt
```

Collect all results, deduplicate by `fullName`, giving you ~40â€“60 unique repos.

### Phase 3: Score and Rank

Pipe the deduplicated JSON through the scorer:

```bash
echo '<json>' | python "$PSScriptRoot/../../scripts/pull-best.py" score
```

The scorer applies:
- **Star weight** (log scale â€” prevents mega-repos dominating)
- **Recency** (1.0x < 90 days, 0.75x < 1 year, 0.5x < 2 years, 0.3x older)
- **Fork ratio** (rewards healthy engagement 5â€“40% fork/star ratio)
- **Keyword boost** (1.1â€“1.5x for skill/agent/AI relevance in description)

Present the **top 12** repos with scores to the user. Let them deselect any before proceeding.

### Phase 4: License Check

For each selected repo:

```bash
python "$PSScriptRoot/../../scripts/pull-best.py" license <owner/repo>
```

**Auto-skip** GPL-2.0, GPL-3.0, AGPL-3.0 with a warning.
**Continue** for MIT, Apache-2.0, BSD-*, ISC, Unlicense, and unspecified.

Show the license verdict table.

### Phase 5: Clone and Inspect

For each licensed-approved repo (process in parallel batches of 4):

```bash
git clone --depth=1 https://github.com/<repo> /tmp/pull-best/<name>
python "$PSScriptRoot/../../scripts/pull-best.py" extract /tmp/pull-best/<name>
```

Show the inspection summary: how many skills/agents/commands found per repo.

### Phase 6: Confirm and Install

Present the full extraction plan:
```
Repo: owner/repo (MIT, 12.4Kâ˜…)
  â†’ 3 skills: skill-name-1, skill-name-2, skill-name-3
  â†’ 1 agent: agent-name.md
  â†’ 0 commands
  Prefix: pb-ownr  (auto-derived from repo owner, max 6 chars)
```

Ask: "Install these 11 items from 4 repos? (y/n/edit)"

On confirm, run:

```bash
python "$PSScriptRoot/../../scripts/pull-best.py" install /tmp/pull-best/<name> <prefix>
```

### Phase 7: Persist Context

After installation, summarize what was added and why in `~/.claude/pull-best.log`:

```
[2026-05-30] Intent: "crypto sentiment analysis"
Repos: 4 installed, 2 skipped (license), 6 no extractable content
Skills added: pb-coinbase-skills/sentiment, pb-openbb-agents/news-analyzer ...
Agents added: 0
Commands added: 1
Total ~/.claude: 335 skills, 67 agents, 82 commands
```

### Phase 8: Report

Final summary:
```
/pull-best "crypto sentiment analysis"

Searched: 7 angles â†’ 52 unique repos â†’ 12 top-scored â†’ 9 license-approved
Inspected: 9 repos â†’ 4 had extractable content
Installed:
  + pb-coinbase-skills  â†’ 3 skills (sentiment, news-rag, crypto-data)
  + pb-finbert         â†’ 1 skill (finbert-inference)
  + pb-openbb-news     â†’ 1 skill (news-pipeline), 1 agent (news-analyzer.md)
  + pb-localllm-fin    â†’ 2 skills (local-rag, embedding-pipeline)

~/.claude now has 335 skills, 67 agents, 82 commands.
Run /skill-health to verify no conflicts.
```

---

## Options

- `--dry` â€” Show what would be installed without installing
- `--no-confirm` â€” Skip confirmation prompts (use in automated contexts)
- `--limit N` â€” Search top N repos per angle (default 10, max 20)
- `--lang python|typescript|rust|go` â€” Filter by language
- `--min-stars N` â€” Minimum star count (default 100)
- `--license-strict` â€” Skip repos with unspecified licenses too

---

## Notes

- Uses GitHub API (not scraping) â€” within ToS, rate-limited to 30 search req/min
- All installs are namespace-prefixed (`pb-` + derived slug) to avoid conflicts
- Shallow clones (`--depth=1`) â€” fast, low bandwidth
- GPL/AGPL repos are always skipped â€” prevents license propagation
- Run `/skill-health` after any batch install to check for conflicts
- The `~/.claude/pull-best.log` persists your discovery history for future sessions
