# pull-best

**Automated GitHub discovery → score → extract → install pipeline for Claude Code.**

Find the best GitHub repositories for any build intent and automatically integrate their skills, agents, and commands into your global `~/.claude` setup — in one command.

```
/pull-best "real-time options flow analysis and sentiment"
```

---

## The problem

Claude Code's usefulness scales with the skills, agents, and commands installed in `~/.claude`. Finding quality ones means manually searching GitHub, evaluating repos, checking licenses, cloning, and copying files. For every new domain you want to work in.

**pull-best automates the entire pipeline.**

---

## How it works

```
Intent: "crypto sentiment analysis"

1. expand     "crypto sentiment analysis"
              "ai agent crypto sentiment analysis"
              "python crypto sentiment"
              "crypto sentiment skill tool"
              "crypto sentiment 2025 2026"
                        |
2. search     gh search repos × 5 angles  →  47 unique repos
                        |
3. score      star weight × recency × fork ratio × keyword boost  →  top 12
                        |
4. license    MIT / Apache / BSD / ISC allowed
              GPL-2/3 / AGPL blocked
                        |
5. inspect    skills/*/SKILL.md  agents/*.md  commands/*.md
                        |
6. confirm    "Install 9 items from 4 repos? (y/n/edit)"
                        |
7. install    ~/.claude/skills/pb-coinbase-sentiment/
              ~/.claude/agents/pb-news-analyzer.md
              ~/.claude/commands/pb-news-pipeline.md
                        |
8. log        ~/.claude/pull-best.log  ← persists every session
```

---

## Install

**Requirements:** Python 3.10+, [Claude Code](https://claude.ai/code), [GitHub CLI](https://cli.github.com) (`gh auth login`)

```bash
git clone https://github.com/gimmepizza/pull-best.git
cd pull-best

# Copy the Claude Code integration files
cp -r .claude/commands/* ~/.claude/commands/
cp -r .claude/skills/*   ~/.claude/skills/
```

That's it. Restart Claude Code and `/pull-best` is available.

---

## Usage

### Slash command (inside Claude Code)

```
/pull-best "what you want to build"
```

Claude Code runs the full pipeline, shows scored results, asks for confirmation, then installs.

### CLI (standalone)

```bash
# Full pipeline: expand → search → score → print top 12
python scripts/pull-best.py full-run "options backtesting" --limit 15

# Just generate search angles for an intent
python scripts/pull-best.py expand "local LLM agent memory"

# Score a JSON file from gh search
gh search repos "sentiment analysis" --json fullName,stargazersCount,forksCount,language,description,pushedAt \
  | python scripts/pull-best.py score

# Pretty-print scored rankings
python scripts/pull-best.py print-scores repos.json

# Check a repo's license
python scripts/pull-best.py license owner/repo

# Inspect a cloned repo for extractable content
python scripts/pull-best.py extract /tmp/cloned-repo

# Install extracted items with a namespace prefix
python scripts/pull-best.py install /tmp/cloned-repo pb-myrepo
python scripts/pull-best.py install extracted.json   pb-myrepo --dry

# View session history
python scripts/pull-best.py log
python scripts/pull-best.py log 5
```

---

## Scoring formula

```
score = star_weight × recency × fork_ratio × boost
```

| Factor | Formula | Rationale |
|--------|---------|-----------|
| `star_weight` | `log10(stars+1) / log10(10001)` | Log scale — prevents 100K-star mega-repos from dominating niche tools |
| `recency` | `1.0 (<90d)` · `0.75 (<1y)` · `0.5 (<2y)` · `0.3 (older)` | Active maintenance matters |
| `fork_ratio` | `1.0` if 5–40% · `0.8` if <5% · `0.7` if >40% | Healthy engagement, not a fork farm |
| `boost` | `+0.1` per matching keyword, capped at `1.5×` | Rewards AI/agent/skill relevance in description |

Zero-star repos with forks score lower (suspicious). Zero-star with no forks score neutral (just new).

---

## License safety

| Allowed | Blocked |
|---------|---------|
| MIT, Apache-2.0, BSD-2/3-Clause | GPL-2.0, GPL-2.0-only |
| ISC, Unlicense, CC0-1.0, 0BSD | GPL-3.0, GPL-3.0-only |
| LGPL-2.1, LGPL-3.0, MPL-2.0 | AGPL-3.0, AGPL-3.0-only |
| Unspecified (assumed permissive) | |

Copyleft licenses (GPL, AGPL) are always skipped — extracting from them would propagate their license terms to your `~/.claude` content.

---

## Namespace prefixing

Every install uses a prefix derived from the repo owner (e.g. `pb-openbb`). This means:

- Installs never silently overwrite existing skills
- You can trace every installed item back to its source
- Running `install` twice is safe — existing destinations are skipped

---

## Session log

Every `full-run` and `install` appends a structured entry to `~/.claude/pull-best.log`:

```
------------------------------------------------------------
[2026-05-31 14:23] full-run  "crypto sentiment analysis"
  Angles: 5 | Repos found: 47 unique
  Top scored (12):
    1.5393  25000*  openbb-finance/openbb  (Python)
    1.2022   5000*  gpl/repo               (Python)
    ...

------------------------------------------------------------
[2026-05-31 14:25] install  prefix=pb-openbb  source=/tmp/openbb
  Installed: 3 skills, 1 agent, 0 commands
  Skills:   sentiment, news-rag, crypto-data
  Agents:   news-analyzer.md
  Total ~/.claude: 42 skills, 8 agents, 15 commands
```

View recent history with `python scripts/pull-best.py log`.

---

## GitHub policy compliance

- Uses `gh search repos` (GitHub API, not scraping) — within Terms of Service
- Shallow clones (`--depth=1`) — minimal bandwidth
- No automated starring, following, or ranking manipulation
- Rate limits: 30 search req/min, 5K API calls/hour — well within normal use

---

## After installing

```
/skill-health    # check for conflicts in ~/.claude
/learn           # capture patterns from newly installed skills
```

---

## Development

```bash
# Run tests
python -m pytest tests/ -v

# Run a specific subcommand
python scripts/pull-best.py expand "your intent here"
```

See [CLAUDE.md](CLAUDE.md) for architecture details and contribution guidance.

---

## License

[MIT](LICENSE) — © 2026 gimmepizza
