#!/usr/bin/env python3
"""
pull-best.py - GitHub discovery, scoring, extraction, and installation engine.
Called by the /pull-best Claude Code command.

Usage:
  python pull-best.py expand <intent>                Print 5 search angles for an intent
  python pull-best.py score [<json_file>]            Score and rank repos (stdin if no file)
  python pull-best.py print-scores [<json_file>]     Human-readable ranked table
  python pull-best.py license <owner/repo>           Check license via gh API
  python pull-best.py extract <repo_dir>             Inspect cloned repo; return extractable items
  python pull-best.py install <dir|json> <prefix> [--dry]
                                                     Install extracted items into ~/.claude
  python pull-best.py full-run <intent> [--limit N]  End-to-end: expand -> search -> score -> show
  python pull-best.py log [N]                        Show last N log entries (default 10)
"""

import sys
import json
import shutil
import subprocess
import math
import re
from datetime import datetime, timezone
from pathlib import Path

CLAUDE_DIR   = Path.home() / ".claude"
SKILLS_DIR   = CLAUDE_DIR / "skills"
AGENTS_DIR   = CLAUDE_DIR / "agents"
COMMANDS_DIR = CLAUDE_DIR / "commands"
LOG_FILE     = CLAUDE_DIR / "pull-best.log"

BLOCKED_LICENSES = {
    "GPL-2.0", "GPL-3.0", "AGPL-3.0",
    "GPL-2.0-only", "GPL-3.0-only", "AGPL-3.0-only",
}

_PREFIX_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,31}$")
_LOG_SEP   = "-" * 60


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def score_repos(repos: list) -> list:
    """Score and rank repos by composite quality signal. Returns a new list; input not mutated."""
    now = datetime.now(timezone.utc)
    scored = []
    for r in repos:
        stars = r.get("stargazersCount", 0)
        forks = r.get("forksCount", 0)
        pushed = r.get("pushedAt", "")
        description = (r.get("description", "") or "").lower()

        recency = 0.3
        if pushed:
            try:
                age_days = (now - datetime.fromisoformat(pushed.replace("Z", "+00:00"))).days
                if age_days < 90:    recency = 1.0
                elif age_days < 365: recency = 0.75
                elif age_days < 730: recency = 0.5
            except Exception:
                pass

        if stars > 0:
            ratio = forks / stars
            if 0.05 < ratio < 0.4: fork_ratio = 1.0
            elif ratio <= 0.05:    fork_ratio = 0.8
            else:                  fork_ratio = 0.7
        else:
            fork_ratio = 0.5 if forks > 0 else 0.7

        star_weight = math.log10(max(stars, 1) + 1) / math.log10(10001)

        boost = 1.0
        for kw in ["skill", "agent", "claude", "llm", "ai ", "quant", "trading", "research"]:
            if kw in description:
                boost = min(boost + 0.1, 1.5)

        scored.append({**r, "_score": round(star_weight * recency * fork_ratio * boost, 4)})

    return sorted(scored, key=lambda x: x["_score"], reverse=True)


def check_license(full_name: str) -> tuple[str | None, bool]:
    """Check repo license via gh API. Returns (spdx_id, is_safe)."""
    try:
        result = subprocess.run(
            ["gh", "api", f"repos/{full_name}", "--jq", ".license.spdx_id"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return None, True
        spdx = result.stdout.strip().strip('"')
        if not spdx or spdx == "null":
            spdx = None
        return spdx, spdx not in BLOCKED_LICENSES
    except Exception:
        return None, True


def inspect_repo(repo_dir: Path) -> dict:
    """Inspect a cloned repo for extractable AI pipeline content."""
    found: dict = {
        "skills": [], "agents": [], "commands": [],
        "hooks": [], "has_skill_spec": False, "readme_summary": "",
    }

    if (repo_dir / "SKILL.md").exists():
        found["has_skill_spec"] = True
        found["skills"].append({"path": str(repo_dir), "name": repo_dir.name, "type": "root"})

    for skills_root in [repo_dir / "skills", repo_dir / ".claude" / "skills"]:
        if skills_root.is_dir():
            for d in skills_root.iterdir():
                if d.is_dir() and (d / "SKILL.md").exists():
                    found["skills"].append({"path": str(d), "name": d.name, "type": "subdir"})

    seen: set[str] = set()
    deduped = []
    for s in found["skills"]:
        if s["name"] not in seen:
            seen.add(s["name"])
            deduped.append(s)
    found["skills"] = deduped

    for agents_path in [repo_dir / "agents", repo_dir / ".claude" / "agents"]:
        if agents_path.is_dir():
            for f in agents_path.glob("*.md"):
                if f.name.lower() != "readme.md":
                    found["agents"].append({"path": str(f), "name": f.name})

    for cmds_path in [repo_dir / "commands", repo_dir / ".claude" / "commands"]:
        if cmds_path.is_dir():
            for f in cmds_path.glob("*.md"):
                if f.name.lower() != "readme.md":
                    found["commands"].append({"path": str(f), "name": f.name})

    for hooks_path in [
        repo_dir / "hooks" / "hooks.json",
        repo_dir / ".claude" / "hooks" / "hooks.json",
    ]:
        if hooks_path.exists():
            found["hooks"].append(str(hooks_path))

    for readme_name in ["README.md", "readme.md", "Readme.md"]:
        p = repo_dir / readme_name
        if p.exists():
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
                lines = [ln.strip() for ln in text.splitlines()
                         if ln.strip() and not ln.startswith("#")]
                found["readme_summary"] = lines[0][:200] if lines else ""
            except Exception:
                pass
            break

    return found


def _make_dest(base: Path, prefix: str, name: str) -> Path:
    """Build and validate the install destination path. Calls _die on traversal attempts."""
    if "/" in name or "\\" in name:
        _die(f"unsafe item name (contains path separator): {name!r}")
    if name == ".." or name.startswith("../") or name.startswith("..\\"):
        _die(f"unsafe item name (path traversal): {name!r}")
    return base / f"{prefix}-{name}"


def _install_one(
    item: dict, base_dir: Path, kind: str, tag: str,
    copyfn, result: dict, prefix: str, dry_run: bool,
) -> None:
    name = item["name"]
    src  = Path(item["path"])
    dest = _make_dest(base_dir, prefix, name)
    if dest.exists():
        result["skipped"].append(f"{tag}:{name}")
    elif not src.exists():
        result["skipped"].append(f"{tag}:{name} (source missing)")
    elif dry_run:
        result[kind].append(name)
    else:
        copyfn(src, dest)
        result[kind].append(name)


def install_items(items: dict, prefix: str, dry_run: bool = False) -> dict:
    """Copy extracted items into ~/.claude with namespace prefix."""
    if not _PREFIX_RE.match(prefix):
        _die(f"prefix must be alphanumeric+hyphens/underscores (1-32 chars), got: {prefix!r}")

    result: dict = {"skills": [], "agents": [], "commands": [], "skipped": [], "dry_run": dry_run}

    if not dry_run:
        for d in (SKILLS_DIR, AGENTS_DIR, COMMANDS_DIR):
            d.mkdir(parents=True, exist_ok=True)

    for kind, base_dir, tag, copyfn in [
        ("skills",   SKILLS_DIR,   "skill", shutil.copytree),
        ("agents",   AGENTS_DIR,   "agent", shutil.copy2),
        ("commands", COMMANDS_DIR, "cmd",   shutil.copy2),
    ]:
        for item in items.get(kind, []):
            _install_one(item, base_dir, kind, tag, copyfn, result, prefix, dry_run)

    return result


def generate_search_angles(intent: str) -> list[str]:
    """Generate 5 diverse GitHub search queries from a non-empty intent."""
    intent = intent.strip()
    words = [w for w in re.split(r"\W+", intent.lower()) if w]
    head3 = " ".join(words[:3])
    head4 = " ".join(words[:4])
    return [
        intent,
        f"ai agent {intent}",
        f"python {head3}",
        f"{head3} skill tool",
        f"{head4} 2025 2026",
    ]


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def _count_dir(d: Path) -> int:
    """Count immediate children of a directory (0 if missing or unreadable)."""
    try:
        return sum(1 for _ in d.iterdir())
    except OSError:
        return 0


def _write_log(lines: list[str]) -> None:
    """Append a separated, timestamped entry to ~/.claude/pull-best.log.
    Never raises -- logging failure must not kill the main workflow."""
    try:
        CLAUDE_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        entry = _LOG_SEP + "\n" + f"[{ts}] " + "\n".join(lines) + "\n"
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(entry)
    except Exception:
        pass


def _log_install(src_arg: str, prefix: str, result: dict) -> None:
    skills_n   = len(result["skills"])
    agents_n   = len(result["agents"])
    commands_n = len(result["commands"])
    skipped_n  = len(result["skipped"])
    dry        = result.get("dry_run", False)

    lines = [
        f"install  prefix={prefix}  source={src_arg}" + ("  [DRY RUN]" if dry else ""),
        f"  Installed: {skills_n} skills, {agents_n} agents, {commands_n} commands",
    ]
    if result["skills"]:
        lines.append(f"  Skills:   {', '.join(result['skills'])}")
    if result["agents"]:
        lines.append(f"  Agents:   {', '.join(result['agents'])}")
    if result["commands"]:
        lines.append(f"  Commands: {', '.join(result['commands'])}")
    if result["skipped"]:
        shown = result["skipped"][:5]
        tail  = f" (+{skipped_n - 5} more)" if skipped_n > 5 else ""
        lines.append(f"  Skipped:  {', '.join(shown)}{tail}")
    if not dry:
        lines.append(
            f"  Total ~/.claude: {_count_dir(SKILLS_DIR)} skills, "
            f"{_count_dir(AGENTS_DIR)} agents, {_count_dir(COMMANDS_DIR)} commands"
        )
    _write_log(lines)


def _log_full_run(intent: str, angles: list[str], repo_count: int, ranked: list) -> None:
    lines = [
        f'full-run  "{intent}"',
        f"  Angles: {len(angles)} | Repos found: {repo_count} unique",
        f"  Top scored ({min(len(ranked), 12)}):",
    ]
    for r in ranked[:12]:
        name  = r.get("fullName", "")
        score = r.get("_score", 0)
        stars = r.get("stargazersCount", 0)
        lang  = r.get("language") or "?"
        desc  = (r.get("description") or "")[:55]
        lines.append(f"    {score:.4f}  {stars:>6}*  {name:<40}  ({lang})")
        if desc:
            lines.append(f"           {desc}")
    _write_log(lines)


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------

def _decode_bytes(raw: bytes) -> str:
    """Decode bytes to str, auto-detecting BOM for UTF-8 and UTF-16."""
    if raw[:3] == b"\xef\xbb\xbf":
        return raw[3:].decode("utf-8", errors="replace")
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16")
    return raw.decode("utf-8", errors="replace")


def _read_json_bytes(path_or_none: str | None) -> list | dict:
    """Read JSON from a file path or stdin, auto-detecting encoding."""
    try:
        raw = Path(path_or_none).read_bytes() if path_or_none else sys.stdin.buffer.read()
    except FileNotFoundError:
        _die(f"file not found: {path_or_none}")
    except OSError as e:
        _die(f"cannot read {path_or_none!r}: {e.strerror}")
    text = _decode_bytes(raw).strip()
    if not text:
        _die("no input -- pipe JSON or pass a file path")
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        _die(f"invalid JSON in {path_or_none or '(stdin)'}: {e}")


def _load_extract_input(arg: str) -> dict:
    """Load extract output: accepts a directory (auto-inspect) or a JSON file path."""
    p = Path(arg)
    if p.is_dir():
        return inspect_repo(p)
    data = _read_json_bytes(arg)
    if not isinstance(data, dict):
        _die(
            "install: expected a JSON object (output of 'extract'), "
            "but got a JSON array. Did you pass scored output by mistake?"
        )
    return data


def _die(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    args = sys.argv[1:]
    cmd = args[0] if args else "help"

    if cmd == "expand":
        if len(args) < 2:
            _die("usage: expand <intent>")
        intent = " ".join(args[1:])
        if not intent.strip():
            _die("intent must not be empty")
        for angle in generate_search_angles(intent):
            print(angle)

    elif cmd == "score":
        data = _read_json_bytes(args[1] if len(args) >= 2 else None)
        if not isinstance(data, list):
            _die("score: expected a JSON array of repo objects")
        print(json.dumps(score_repos(data), indent=2))

    elif cmd == "print-scores":
        data = _read_json_bytes(args[1] if len(args) >= 2 else None)
        if not isinstance(data, list):
            _die("print-scores: expected a JSON array of repo objects")
        ranked = score_repos(data)
        print(f"{'Score':>7}  {'Stars':>7}  {'Repo':<45}  Description")
        print("-" * 100)
        for r in ranked[:15]:
            desc = (r.get("description") or "")[:50]
            print(f"  {r['_score']:.4f}  {r.get('stargazersCount', 0):>7}"
                  f"  {r.get('fullName', ''):<45}  {desc}")

    elif cmd == "extract":
        if len(args) < 2:
            _die("usage: extract <repo_dir>")
        repo_dir = Path(args[1])
        if not repo_dir.is_dir():
            _die(f"not a directory: {repo_dir}")
        print(json.dumps(inspect_repo(repo_dir), indent=2))

    elif cmd == "install":
        flags       = [a for a in args[1:] if a.startswith("--")]
        positionals = [a for a in args[1:] if not a.startswith("--")]
        if len(positionals) < 2:
            _die("usage: install <repo_dir|items.json> <prefix> [--dry]")
        src_arg, prefix = positionals[0], positionals[1]
        dry    = "--dry" in flags
        items  = _load_extract_input(src_arg)
        result = install_items(items, prefix, dry_run=dry)
        print(json.dumps(result, indent=2))
        _log_install(src_arg, prefix, result)

    elif cmd == "license":
        if len(args) < 2:
            _die("usage: license <owner/repo>")
        spdx, safe = check_license(args[1])
        print(json.dumps({"spdx": spdx, "safe": safe}))

    elif cmd == "full-run":
        if len(args) < 2:
            _die("usage: full-run <intent> [--limit N]")

        limit = 10
        intent_parts = list(args[1:])
        if "--limit" in intent_parts:
            li = intent_parts.index("--limit")
            intent_parts.pop(li)
            if li >= len(intent_parts):
                _die("--limit requires an integer argument")
            raw_limit = intent_parts.pop(li)
            try:
                limit = int(raw_limit)
            except ValueError:
                _die(f"--limit requires an integer, got: {raw_limit!r}")

        intent = " ".join(intent_parts)
        if not intent.strip():
            _die("intent must not be empty")

        angles = generate_search_angles(intent)
        print(f"Intent: {intent}")
        print("Search angles:")
        for i, a in enumerate(angles, 1):
            print(f"  {i}. {a}")
        print()

        all_repos: dict = {}
        for angle in angles:
            try:
                result = subprocess.run(
                    ["gh", "search", "repos", angle,
                     "--sort", "stars", "--order", "desc",
                     "--limit", str(limit),
                     "--json", "fullName,stargazersCount,forksCount,language,description,pushedAt"],
                    capture_output=True, text=True, timeout=30,
                )
                if result.returncode != 0:
                    print(f"  warning: angle '{angle}' failed (gh exit {result.returncode})",
                          file=sys.stderr)
                    continue
                for r in json.loads(result.stdout or "[]"):
                    fn = r.get("fullName", "")
                    if fn and fn not in all_repos:
                        all_repos[fn] = r
            except Exception as e:
                print(f"  warning: angle '{angle}' failed: {e}", file=sys.stderr)

        if not all_repos:
            _die("no repos found -- check gh auth and network")

        ranked = score_repos(list(all_repos.values()))
        print(f"Found {len(all_repos)} unique repos. Top 12:")
        print(f"{'#':>3}  {'Score':>6}  {'Stars':>7}  {'Repo':<45}  Language")
        print("-" * 95)
        for i, r in enumerate(ranked[:12], 1):
            print(f"  {i:>2}  {r['_score']:.4f}  {r.get('stargazersCount', 0):>7}"
                  f"  {r.get('fullName', ''):<45}  {r.get('language', '') or ''}")

        _log_full_run(intent, angles, len(all_repos), ranked)

    elif cmd == "log":
        n = 10
        if len(args) >= 2:
            if not args[1].isdigit():
                _die("usage: log [N]  (N must be a positive integer)")
            n = int(args[1])

        if not LOG_FILE.exists():
            print("No log yet. Run 'full-run' or 'install' to create one.")
            print(f"Log will be written to: {LOG_FILE}")
            return

        text = LOG_FILE.read_text(encoding="utf-8", errors="replace")
        # Each entry starts right after a separator line
        raw_entries = text.split(_LOG_SEP + "\n")
        entries = [e.rstrip() for e in raw_entries if e.strip()]

        if not entries:
            print("Log file is empty.")
            return

        shown = entries[-n:]
        print(f"Showing {len(shown)} of {len(entries)} log entries  ({LOG_FILE})")
        for entry in shown:
            print(_LOG_SEP)
            print(entry)
        print(_LOG_SEP)

    else:
        print(__doc__)


if __name__ == "__main__":
    main()
