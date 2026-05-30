"""
Tests for scripts/pull-best.py

Run with: python -m pytest tests/test_pull_best.py -v
"""

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

# ---------------------------------------------------------------------------
# Load the module under test without executing main()
# ---------------------------------------------------------------------------

_SCRIPT = Path(__file__).parent.parent / "scripts" / "pull-best.py"
_spec = importlib.util.spec_from_file_location("pull_best", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

score_repos            = _mod.score_repos
inspect_repo           = _mod.inspect_repo
install_items          = _mod.install_items
generate_search_angles = _mod.generate_search_angles
_decode_bytes          = _mod._decode_bytes
_read_json             = _mod._read_json_bytes
_load_extract_input    = _mod._load_extract_input
_make_dest             = _mod._make_dest
_write_log             = _mod._write_log
_count_dir             = _mod._count_dir
_log_install           = _mod._log_install
_log_full_run          = _mod._log_full_run


# ---------------------------------------------------------------------------
# score_repos
# ---------------------------------------------------------------------------

class TestScoreRepos(unittest.TestCase):

    def _repo(self, **kw):
        return {
            "fullName": "x/y", "stargazersCount": 1000, "forksCount": 100,
            "pushedAt": "2026-01-01T00:00:00Z", "description": "",
            **kw,
        }

    def test_returns_new_list_input_not_mutated(self):
        repos = [self._repo()]
        orig = dict(repos[0])
        ranked = score_repos(repos)
        self.assertEqual(repos[0], orig)
        self.assertIn("_score", ranked[0])
        self.assertIsNot(ranked, repos)

    def test_sorted_descending(self):
        repos = [self._repo(stargazersCount=100), self._repo(stargazersCount=10000)]
        ranked = score_repos(repos)
        self.assertGreater(ranked[0]["_score"], ranked[1]["_score"])

    def test_empty_list(self):
        self.assertEqual(score_repos([]), [])

    def test_zero_stars_no_forks(self):
        r = score_repos([self._repo(stargazersCount=0, forksCount=0)])
        self.assertGreaterEqual(r[0]["_score"], 0)

    def test_zero_stars_with_forks_scored_lower_than_no_forks(self):
        no_fork   = score_repos([self._repo(stargazersCount=0, forksCount=0)])[0]["_score"]
        many_fork = score_repos([self._repo(stargazersCount=0, forksCount=1000)])[0]["_score"]
        self.assertLess(many_fork, no_fork,
            "suspicious zero-star/many-fork repo should score lower than zero-star/no-fork")

    def test_boost_capped(self):
        desc = "skill agent claude llm ai quant trading research"
        r = score_repos([self._repo(description=desc)])[0]
        self.assertLessEqual(r["_score"], 2.0)

    def test_old_repo_penalised(self):
        fresh = score_repos([self._repo(pushedAt="2026-04-01T00:00:00Z")])[0]["_score"]
        old   = score_repos([self._repo(pushedAt="2020-01-01T00:00:00Z")])[0]["_score"]
        self.assertGreater(fresh, old)

    def test_missing_pushed_at(self):
        r = score_repos([self._repo(pushedAt="")])[0]
        self.assertGreaterEqual(r[" _score".strip()], 0)

    def test_invalid_pushed_at(self):
        score_repos([self._repo(pushedAt="not-a-date")])  # must not raise

    def test_healthy_fork_ratio_rewarded(self):
        good = score_repos([self._repo(forksCount=150)])[0]["_score"]   # 15%
        poor = score_repos([self._repo(forksCount=1)])[0]["_score"]     # 0.1%
        self.assertGreater(good, poor)


# ---------------------------------------------------------------------------
# generate_search_angles
# ---------------------------------------------------------------------------

class TestGenerateSearchAngles(unittest.TestCase):

    def _angles(self, intent):
        return generate_search_angles(intent)

    def test_returns_five(self):
        self.assertEqual(len(self._angles("crypto sentiment")), 5)

    def test_no_blank_angles_two_char_words(self):
        for intent in ["AI", "Go", "ML", "AI Go", "options 0DTE flow"]:
            angles = self._angles(intent)
            for a in angles:
                self.assertTrue(a.strip(), f"blank angle for {intent!r}: {angles}")

    def test_no_blank_angles_single_char_words(self):
        # All words are single chars - must still produce 5 non-blank angles
        for intent in ["a b c", "I O", "x y z w"]:
            angles = self._angles(intent)
            for a in angles:
                self.assertTrue(a.strip(), f"blank angle for {intent!r}: {angles}")

    def test_two_char_word_in_output(self):
        angles = self._angles("AI trading")
        self.assertIn("AI trading", angles[0])

    def test_single_word(self):
        angles = self._angles("backtesting")
        self.assertEqual(len(angles), 5)
        self.assertTrue(all(a.strip() for a in angles))

    def test_preserves_original_case_first_angle(self):
        self.assertEqual(self._angles("Crypto Sentiment Analysis")[0], "Crypto Sentiment Analysis")

    def test_numeric_words_preserved(self):
        self.assertIn("AI tools 2025", self._angles("AI tools 2025")[0])

    def test_long_intent(self):
        angles = self._angles("real time options flow analysis and sentiment scoring for equities")
        self.assertEqual(len(angles), 5)
        self.assertTrue(all(a.strip() for a in angles))


# ---------------------------------------------------------------------------
# _decode_bytes
# ---------------------------------------------------------------------------

class TestDecodeBytes(unittest.TestCase):

    def test_plain_utf8(self):
        self.assertEqual(_decode_bytes(b'[{"a":1}]'), '[{"a":1}]')

    def test_utf8_bom(self):
        self.assertEqual(_decode_bytes(b'\xef\xbb\xbf[{"a":1}]'), '[{"a":1}]')

    def test_utf16_le_bom(self):
        raw = b'\xff\xfe' + '[{"a":1}]'.encode("utf-16-le")
        self.assertEqual(json.loads(_decode_bytes(raw)), [{"a": 1}])

    def test_utf16_be_bom(self):
        raw = b'\xfe\xff' + '[{"a":1}]'.encode("utf-16-be")
        self.assertEqual(json.loads(_decode_bytes(raw)), [{"a": 1}])

    def test_latin1_no_crash(self):
        # 0xe9 (é) is invalid UTF-8 — must not raise
        result = _decode_bytes(b'[{"name": "caf\xe9"}]')
        self.assertIn("caf", result)


# ---------------------------------------------------------------------------
# _read_json_bytes
# ---------------------------------------------------------------------------

class TestReadJsonBytes(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_valid_file(self):
        f = self.root / "data.json"
        f.write_text('[{"a":1}]', encoding="utf-8")
        self.assertEqual(_read_json(str(f)), [{"a": 1}])

    def test_missing_file_errors_cleanly(self):
        with self.assertRaises(SystemExit):
            _read_json(str(self.root / "nope.json"))

    def test_invalid_json_errors_cleanly(self):
        f = self.root / "bad.json"
        f.write_text("this is not json", encoding="utf-8")
        with self.assertRaises(SystemExit):
            _read_json(str(f))

    def test_directory_as_file_errors_cleanly(self):
        # Reading a directory as a file raises PermissionError/IsADirectoryError (both OSError)
        d = self.root / "a_dir"
        d.mkdir()
        with self.assertRaises(SystemExit):
            _read_json(str(d))


# ---------------------------------------------------------------------------
# _make_dest
# ---------------------------------------------------------------------------

class TestMakeDest(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_normal_name(self):
        dest = _make_dest(self.base, "pb-test", "my-skill")
        self.assertEqual(dest, self.base / "pb-test-my-skill")

    def test_rejects_forward_slash(self):
        with self.assertRaises(SystemExit):
            _make_dest(self.base, "pb", "../../evil")

    def test_rejects_backslash(self):
        with self.assertRaises(SystemExit):
            _make_dest(self.base, "pb", "..\\evil")

    def test_rejects_dotdot(self):
        with self.assertRaises(SystemExit):
            _make_dest(self.base, "pb", "..")


# ---------------------------------------------------------------------------
# inspect_repo
# ---------------------------------------------------------------------------

class TestInspectRepo(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _write(self, *parts, content="# skill"):
        p = self.root.joinpath(*parts)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return p

    def test_empty_repo(self):
        r = inspect_repo(self.root)
        self.assertEqual(r["skills"], [])
        self.assertEqual(r["agents"], [])
        self.assertEqual(r["commands"], [])

    def test_root_skill_md(self):
        self._write("SKILL.md")
        r = inspect_repo(self.root)
        self.assertTrue(r["has_skill_spec"])
        self.assertEqual(len(r["skills"]), 1)
        self.assertEqual(r["skills"][0]["type"], "root")

    def test_skills_subdir(self):
        self._write("skills", "my-skill", "SKILL.md")
        r = inspect_repo(self.root)
        self.assertEqual(len(r["skills"]), 1)
        self.assertEqual(r["skills"][0]["name"], "my-skill")

    def test_claude_skills_subdir(self):
        self._write(".claude", "skills", "pb-skill", "SKILL.md")
        self.assertEqual(len(inspect_repo(self.root)["skills"]), 1)

    def test_agents_found(self):
        self._write("agents", "my-agent.md")
        r = inspect_repo(self.root)
        self.assertEqual(len(r["agents"]), 1)
        self.assertEqual(r["agents"][0]["name"], "my-agent.md")

    def test_agents_readme_excluded(self):
        self._write("agents", "README.md")
        self.assertEqual(inspect_repo(self.root)["agents"], [])

    def test_commands_found(self):
        self._write("commands", "deploy.md")
        self.assertEqual(len(inspect_repo(self.root)["commands"]), 1)

    def test_hooks_found(self):
        self._write("hooks", "hooks.json", content="{}")
        self.assertEqual(len(inspect_repo(self.root)["hooks"]), 1)

    def test_readme_summary(self):
        self._write("README.md", content="# Title\n\nThis is a great tool.")
        self.assertEqual(inspect_repo(self.root)["readme_summary"], "This is a great tool.")

    def test_readme_skips_headers(self):
        self._write("README.md", content="# Header\n## Sub\nReal content here.")
        self.assertEqual(inspect_repo(self.root)["readme_summary"], "Real content here.")

    def test_no_duplicate_skills(self):
        self._write("skills", "foo", "SKILL.md")
        self._write(".claude", "skills", "foo", "SKILL.md")
        names = [s["name"] for s in inspect_repo(self.root)["skills"]]
        self.assertEqual(len(names), len(set(names)), f"Duplicate skill names: {names}")


# ---------------------------------------------------------------------------
# install_items
# ---------------------------------------------------------------------------

class TestInstallItems(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self._orig = (_mod.SKILLS_DIR, _mod.AGENTS_DIR, _mod.COMMANDS_DIR)
        _mod.SKILLS_DIR   = self.base / "skills"
        _mod.AGENTS_DIR   = self.base / "agents"
        _mod.COMMANDS_DIR = self.base / "commands"

    def tearDown(self):
        _mod.SKILLS_DIR, _mod.AGENTS_DIR, _mod.COMMANDS_DIR = self._orig
        self._tmp.cleanup()

    def _skill_src(self, name="my-skill"):
        src = self.base / "src" / name
        src.mkdir(parents=True, exist_ok=True)
        (src / "SKILL.md").write_text("# skill", encoding="utf-8")
        return src

    def _agent_src(self, name="agent.md"):
        src = self.base / "src" / name
        src.parent.mkdir(parents=True, exist_ok=True)
        src.write_text("# agent", encoding="utf-8")
        return src

    def _items(self, skills=(), agents=(), commands=()):
        return {
            "skills":   [{"path": str(s), "name": s.name} for s in skills],
            "agents":   [{"path": str(a), "name": a.name} for a in agents],
            "commands": [{"path": str(c), "name": c.name} for c in commands],
        }

    def test_dry_run_reports_would_install(self):
        src = self._skill_src()
        r = install_items(self._items(skills=[src]), "pb-test", dry_run=True)
        self.assertIn("my-skill", r["skills"])
        self.assertFalse((self.base / "skills" / "pb-test-my-skill").exists())

    def test_real_install_copies_skill(self):
        src = self._skill_src()
        r = install_items(self._items(skills=[src]), "pb-test")
        self.assertIn("my-skill", r["skills"])
        self.assertTrue((self.base / "skills" / "pb-test-my-skill").is_dir())

    def test_real_install_copies_agent(self):
        src = self._agent_src()
        r = install_items(self._items(agents=[src]), "pb-test")
        self.assertIn("agent.md", r["agents"])
        self.assertTrue((self.base / "agents" / "pb-test-agent.md").is_file())

    def test_skip_existing_dest(self):
        src  = self._skill_src()
        dest = self.base / "skills" / "pb-test-my-skill"
        dest.mkdir(parents=True)
        r = install_items(self._items(skills=[src]), "pb-test")
        self.assertIn("skill:my-skill", r["skipped"])
        self.assertEqual(r["skills"], [])

    def test_creates_parent_dirs(self):
        src = self._skill_src()
        install_items(self._items(skills=[src]), "pb-test")
        self.assertTrue((self.base / "skills").is_dir())

    def test_path_traversal_prefix_rejected(self):
        src = self._skill_src()
        with self.assertRaises(SystemExit):
            install_items(self._items(skills=[src]), "../../evil")

    def test_path_traversal_in_name_rejected(self):
        items = {"skills": [{"path": "/tmp/x", "name": "../../.bashrc"}],
                 "agents": [], "commands": []}
        with self.assertRaises(SystemExit):
            install_items(items, "pb-test")

    def test_missing_source_skipped(self):
        items = {"skills": [{"path": "/nonexistent", "name": "ghost"}],
                 "agents": [], "commands": []}
        r = install_items(items, "pb-test")
        self.assertTrue(any("ghost" in s for s in r["skipped"]))

    def test_invalid_prefix_rejected(self):
        empty = {"skills": [], "agents": [], "commands": []}
        for bad in ("", "--dry", "a" * 33):
            with self.assertRaises(SystemExit, msg=f"prefix {bad!r} should be rejected"):
                install_items(empty, bad)


# ---------------------------------------------------------------------------
# _load_extract_input
# ---------------------------------------------------------------------------

class TestLoadExtractInput(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_accepts_directory(self):
        r = _load_extract_input(str(self.root))
        self.assertIsInstance(r, dict)
        self.assertIn("skills", r)

    def test_accepts_json_file(self):
        f = self.root / "items.json"
        f.write_text(json.dumps({"skills": [], "agents": [], "commands": []}), encoding="utf-8")
        r = _load_extract_input(str(f))
        self.assertIsInstance(r, dict)

    def test_rejects_json_array(self):
        f = self.root / "bad.json"
        f.write_text('[{"fullName":"x/y"}]', encoding="utf-8")
        with self.assertRaises(SystemExit):
            _load_extract_input(str(f))

    def test_missing_file_errors_cleanly(self):
        with self.assertRaises(SystemExit):
            _load_extract_input(str(self.root / "nonexistent.json"))


# ---------------------------------------------------------------------------
# CLI integration (subprocess)
# ---------------------------------------------------------------------------

class TestCLI(unittest.TestCase):

    SCRIPT = str(_SCRIPT)

    def _run(self, *args, input_text=None):
        import subprocess
        return subprocess.run(
            [sys.executable, self.SCRIPT, *args],
            capture_output=True, text=True, input=input_text,
        )

    def test_no_args_shows_help(self):
        r = self._run()
        self.assertIn("Usage", r.stdout)
        self.assertEqual(r.returncode, 0)

    def test_unknown_command_shows_help(self):
        r = self._run("bogus-command")
        self.assertIn("Usage", r.stdout)
        self.assertEqual(r.returncode, 0)

    def test_expand_normal(self):
        r = self._run("expand", "crypto sentiment")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(len([l for l in r.stdout.splitlines() if l.strip()]), 5)

    def test_expand_no_args_errors(self):
        r = self._run("expand")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("usage", r.stderr.lower())

    def test_expand_empty_intent_errors(self):
        r = self._run("expand", "   ")
        self.assertNotEqual(r.returncode, 0)

    def test_expand_two_char_words_five_non_blank(self):
        r = self._run("expand", "AI trading")
        self.assertEqual(r.returncode, 0)
        non_blank = [l for l in r.stdout.splitlines() if l.strip()]
        self.assertEqual(len(non_blank), 5, f"expected 5 non-blank angles, got: {r.stdout!r}")

    def test_score_from_file(self):
        data = [{"fullName": "a/b", "stargazersCount": 100, "forksCount": 10,
                 "pushedAt": "2026-01-01T00:00:00Z", "description": ""}]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            name = f.name
        try:
            r = self._run("score", name)
            self.assertEqual(r.returncode, 0)
            self.assertIn("_score", json.loads(r.stdout)[0])
        finally:
            Path(name).unlink(missing_ok=True)

    def test_score_empty_stdin_errors(self):
        r = self._run("score", input_text="")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("error", r.stderr.lower())

    def test_score_invalid_json_errors_cleanly(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("this is not json")
            name = f.name
        try:
            r = self._run("score", name)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("error", r.stderr.lower())
            self.assertNotIn("Traceback", r.stderr)
        finally:
            Path(name).unlink(missing_ok=True)

    def test_extract_no_args_errors(self):
        r = self._run("extract")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("usage", r.stderr.lower())

    def test_extract_not_a_dir_errors(self):
        r = self._run("extract", "nonexistent_path_xyz")
        self.assertNotEqual(r.returncode, 0)

    def test_install_no_args_errors(self):
        self.assertNotEqual(self._run("install").returncode, 0)

    def test_install_one_arg_errors(self):
        self.assertNotEqual(self._run("install", "somedir").returncode, 0)

    def test_install_dry_flag_as_prefix_errors(self):
        with tempfile.TemporaryDirectory() as d:
            r = self._run("install", d, "--dry")
            self.assertNotEqual(r.returncode, 0, "--dry must not silently become the prefix")

    def test_license_no_args_errors(self):
        self.assertNotEqual(self._run("license").returncode, 0)

    def test_full_run_no_args_errors(self):
        self.assertNotEqual(self._run("full-run").returncode, 0)

    def test_full_run_limit_bad_value_errors_cleanly(self):
        # --limit abc should produce a clean error, not an IndexError traceback
        r = self._run("full-run", "trading", "--limit", "abc")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("error", r.stderr.lower())
        self.assertNotIn("Traceback", r.stderr, "must not crash with a traceback")
        self.assertNotIn("IndexError", r.stderr)


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

class TestLogging(unittest.TestCase):

    def setUp(self):
        self._tmp  = tempfile.TemporaryDirectory()
        self.root  = Path(self._tmp.name)
        # Redirect all logging globals into the temp dir
        self._orig_claude    = _mod.CLAUDE_DIR
        self._orig_log       = _mod.LOG_FILE
        self._orig_skills    = _mod.SKILLS_DIR
        self._orig_agents    = _mod.AGENTS_DIR
        self._orig_commands  = _mod.COMMANDS_DIR
        _mod.CLAUDE_DIR   = self.root
        _mod.LOG_FILE     = self.root / "pull-best.log"
        _mod.SKILLS_DIR   = self.root / "skills"
        _mod.AGENTS_DIR   = self.root / "agents"
        _mod.COMMANDS_DIR = self.root / "commands"

    def tearDown(self):
        _mod.CLAUDE_DIR   = self._orig_claude
        _mod.LOG_FILE     = self._orig_log
        _mod.SKILLS_DIR   = self._orig_skills
        _mod.AGENTS_DIR   = self._orig_agents
        _mod.COMMANDS_DIR = self._orig_commands
        self._tmp.cleanup()

    def _read_log(self) -> str:
        return _mod.LOG_FILE.read_text(encoding="utf-8")

    # --- _write_log ---

    def test_write_log_creates_file(self):
        _write_log(["hello world"])
        self.assertTrue(_mod.LOG_FILE.exists())

    def test_write_log_appends(self):
        _write_log(["entry one"])
        _write_log(["entry two"])
        text = self._read_log()
        self.assertIn("entry one", text)
        self.assertIn("entry two", text)

    def test_write_log_includes_timestamp(self):
        _write_log(["test"])
        text = self._read_log()
        import re as _re
        self.assertRegex(text, r"\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}\]")

    def test_write_log_includes_separator(self):
        _write_log(["test"])
        self.assertIn("-" * 60, self._read_log())

    def test_write_log_never_raises_on_bad_dir(self):
        _mod.CLAUDE_DIR = Path("/no/such/directory/ever")
        _mod.LOG_FILE   = Path("/no/such/directory/ever/pull-best.log")
        _write_log(["should not crash"])  # must not raise

    # --- _count_dir ---

    def test_count_dir_missing(self):
        self.assertEqual(_count_dir(self.root / "nonexistent"), 0)

    def test_count_dir_empty(self):
        d = self.root / "empty"
        d.mkdir()
        self.assertEqual(_count_dir(d), 0)

    def test_count_dir_counts_children(self):
        d = self.root / "filled"
        d.mkdir()
        (d / "a").mkdir()
        (d / "b").write_text("x")
        self.assertEqual(_count_dir(d), 2)

    # --- _log_install ---

    def test_log_install_writes_prefix_and_counts(self):
        result = {"skills": ["s1", "s2"], "agents": ["a1"], "commands": [],
                  "skipped": [], "dry_run": False}
        _log_install("/tmp/repo", "pb-test", result)
        text = self._read_log()
        self.assertIn("pb-test", text)
        self.assertIn("2 skills", text)
        self.assertIn("1 agents", text)
        self.assertIn("s1", text)

    def test_log_install_dry_run_noted(self):
        result = {"skills": ["s1"], "agents": [], "commands": [],
                  "skipped": [], "dry_run": True}
        _log_install("/tmp/repo", "pb-test", result)
        self.assertIn("DRY RUN", self._read_log())

    def test_log_install_skipped_shown(self):
        result = {"skills": [], "agents": [], "commands": [],
                  "skipped": ["skill:foo", "skill:bar"], "dry_run": False}
        _log_install("/tmp/repo", "pb-test", result)
        self.assertIn("foo", self._read_log())

    def test_log_install_skipped_truncated_at_5(self):
        skipped = [f"skill:x{i}" for i in range(10)]
        result  = {"skills": [], "agents": [], "commands": [],
                   "skipped": skipped, "dry_run": False}
        _log_install("/tmp/repo", "pb-test", result)
        text = self._read_log()
        self.assertIn("+5 more", text)

    def test_log_install_totals_absent_on_dry_run(self):
        result = {"skills": ["s1"], "agents": [], "commands": [],
                  "skipped": [], "dry_run": True}
        _log_install("/tmp/repo", "pb-test", result)
        self.assertNotIn("Total ~/.claude", self._read_log())

    # --- _log_full_run ---

    def test_log_full_run_writes_intent_and_count(self):
        repos = [{"fullName": "a/b", "stargazersCount": 1000, "forksCount": 100,
                  "pushedAt": "2026-01-01T00:00:00Z", "description": "tool",
                  "_score": 0.75, "language": "Python"}]
        _log_full_run("crypto sentiment", ["angle1", "angle2"], 42, repos)
        text = self._read_log()
        self.assertIn("crypto sentiment", text)
        self.assertIn("42 unique", text)
        self.assertIn("a/b", text)

    def test_log_full_run_shows_scores(self):
        repos = [{"fullName": "x/y", "stargazersCount": 500, "forksCount": 50,
                  "pushedAt": "2026-01-01T00:00:00Z", "description": "",
                  "_score": 0.5432, "language": "Go"}]
        _log_full_run("test", ["a"], 5, repos)
        self.assertIn("0.5432", self._read_log())

    # --- CLI: log command ---

    def test_cli_log_no_file_prints_message(self):
        import subprocess
        r = subprocess.run(
            [sys.executable, str(_SCRIPT), "log"],
            capture_output=True, text=True,
            env={**__import__("os").environ, "HOME": str(self.root)},
        )
        # Should exit 0 and print a helpful message, not crash
        self.assertEqual(r.returncode, 0)

    def test_cli_log_bad_n_errors(self):
        import subprocess
        r = subprocess.run(
            [sys.executable, str(_SCRIPT), "log", "abc"],
            capture_output=True, text=True,
        )
        self.assertNotEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
