"""Tests for scanner.py and agents.ToolExecutor."""

from pathlib import Path

import pytest

from tribl.agents import ToolExecutor
from tribl.scanner import (
    SKIP_DIRS,
    _is_binary_file,
    _is_gitignored,
    _should_skip_dir,
    scan_repo,
)

# ─── Fixtures ────────────────────────────────────────────────────


@pytest.fixture()
def tmp_repo(tmp_path: Path) -> Path:
    """Create a minimal repo structure for testing."""
    (tmp_path / "README.md").write_text("# Hello", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("print('hi')", encoding="utf-8")
    (tmp_path / "src" / "utils.py").write_text("x = 1", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_main.py").write_text("assert True", encoding="utf-8")
    return tmp_path


# ─── _should_skip_dir ────────────────────────────────────────────


class TestShouldSkipDir:
    def test_git_skipped(self):
        assert _should_skip_dir(".git") is True

    def test_node_modules_skipped(self):
        assert _should_skip_dir("node_modules") is True

    def test_pycache_skipped(self):
        assert _should_skip_dir("__pycache__") is True

    def test_venv_skipped(self):
        assert _should_skip_dir("venv") is True

    def test_normal_dir_not_skipped(self):
        assert _should_skip_dir("src") is False

    def test_egg_info_pattern(self):
        assert _should_skip_dir("mypackage.egg-info") is True

    def test_terraform_skipped(self):
        assert _should_skip_dir(".terraform") is True


# ─── _is_gitignored ─────────────────────────────────────────────


class TestIsGitignored:
    def test_exact_match(self):
        assert _is_gitignored("dist/bundle.js", ["dist"]) is True

    def test_wildcard(self):
        assert _is_gitignored("src/main.pyc", ["*.pyc"]) is True

    def test_not_ignored(self):
        assert _is_gitignored("src/main.py", ["*.pyc"]) is False

    def test_directory_pattern(self):
        assert _is_gitignored("build/output.js", ["build/"]) is True

    def test_nested_path(self):
        assert _is_gitignored("src/vendor/lib.js", ["vendor"]) is True


# ─── _is_binary_file ────────────────────────────────────────────


class TestIsBinaryFile:
    def test_text_file(self, tmp_path: Path):
        f = tmp_path / "hello.py"
        f.write_text("print('hello')", encoding="utf-8")
        assert _is_binary_file(f) is False

    def test_binary_extension(self, tmp_path: Path):
        f = tmp_path / "image.png"
        f.write_bytes(b"\x89PNG\r\n")
        assert _is_binary_file(f) is True

    def test_null_byte_detection(self, tmp_path: Path):
        f = tmp_path / "mystery.dat"
        f.write_bytes(b"hello\x00world")
        assert _is_binary_file(f) is True


# ─── scan_repo ───────────────────────────────────────────────────


class TestScanRepo:
    def test_basic_scan(self, tmp_repo: Path):
        repo_map = scan_repo(tmp_repo)
        assert repo_map.total_files >= 4
        paths = {f.relative_path for f in repo_map.files}
        assert "README.md" in paths
        assert "src/main.py" in paths

    def test_skips_git_dir(self, tmp_repo: Path):
        (tmp_repo / ".git").mkdir()
        (tmp_repo / ".git" / "config").write_text("x", encoding="utf-8")
        repo_map = scan_repo(tmp_repo)
        paths = {f.relative_path for f in repo_map.files}
        assert ".git/config" not in paths

    def test_file_tree_output(self, tmp_repo: Path):
        repo_map = scan_repo(tmp_repo)
        tree = repo_map.file_tree
        assert "README.md" in tree
        assert "src/" in tree

    def test_nonexistent_path_raises(self):
        with pytest.raises(FileNotFoundError):
            scan_repo("/nonexistent/path/that/does/not/exist")

    def test_respects_gitignore(self, tmp_repo: Path):
        (tmp_repo / ".gitignore").write_text("*.log\n", encoding="utf-8")
        (tmp_repo / "debug.log").write_text("log data", encoding="utf-8")
        repo_map = scan_repo(tmp_repo)
        paths = {f.relative_path for f in repo_map.files}
        assert "debug.log" not in paths

    def test_source_files_excludes_binary(self, tmp_repo: Path):
        (tmp_repo / "image.png").write_bytes(b"\x89PNG\r\n")
        repo_map = scan_repo(tmp_repo)
        source_paths = {f.relative_path for f in repo_map.source_files}
        assert "image.png" not in source_paths


# ─── SKIP_DIRS consistency ───────────────────────────────────────


class TestSkipDirsConsistency:
    def test_core_dirs_present(self):
        for d in [".git", "node_modules", "__pycache__", "venv", ".venv"]:
            assert d in SKIP_DIRS


# ─── ToolExecutor ────────────────────────────────────────────────


class TestToolExecutor:
    def test_path_traversal_blocked(self, tmp_repo: Path):
        executor = ToolExecutor(str(tmp_repo))
        with pytest.raises(ValueError, match="Path outside repository"):
            executor._safe_path("../../etc/passwd")

    def test_path_traversal_dotdot(self, tmp_repo: Path):
        executor = ToolExecutor(str(tmp_repo))
        with pytest.raises(ValueError, match="Path outside repository"):
            executor._safe_path("src/../../outside")

    def test_safe_path_within_repo(self, tmp_repo: Path):
        executor = ToolExecutor(str(tmp_repo))
        result = executor._safe_path("src/main.py")
        assert result == (tmp_repo / "src" / "main.py").resolve()

    def test_read_file(self, tmp_repo: Path):
        executor = ToolExecutor(str(tmp_repo))
        result = executor.execute("read_file", {"path": "README.md"})
        assert "# Hello" in result

    def test_read_file_not_found(self, tmp_repo: Path):
        executor = ToolExecutor(str(tmp_repo))
        result = executor.execute("read_file", {"path": "nope.txt"})
        assert "File not found" in result

    def test_read_file_line_range(self, tmp_repo: Path):
        (tmp_repo / "lines.txt").write_text("a\nb\nc\nd\ne\n", encoding="utf-8")
        executor = ToolExecutor(str(tmp_repo))
        result = executor.execute(
            "read_file", {"path": "lines.txt", "start_line": 2, "end_line": 3}
        )
        assert "b" in result
        assert "c" in result

    def test_list_files(self, tmp_repo: Path):
        executor = ToolExecutor(str(tmp_repo))
        result = executor.execute("list_files", {"path": "src"})
        assert "main.py" in result
        assert "utils.py" in result

    def test_list_files_skips_dirs(self, tmp_repo: Path):
        (tmp_repo / "node_modules").mkdir()
        (tmp_repo / "node_modules" / "pkg.json").write_text("{}", encoding="utf-8")
        executor = ToolExecutor(str(tmp_repo))
        result = executor.execute("list_files", {"path": "."})
        assert "node_modules" not in result

    def test_list_files_with_pattern(self, tmp_repo: Path):
        executor = ToolExecutor(str(tmp_repo))
        result = executor.execute("list_files", {"path": ".", "pattern": "*.py"})
        assert "main.py" in result
        assert "README.md" not in result

    def test_grep(self, tmp_repo: Path):
        executor = ToolExecutor(str(tmp_repo))
        result = executor.execute("grep", {"pattern": "print"})
        assert "main.py" in result
        assert "print" in result

    def test_grep_no_match(self, tmp_repo: Path):
        executor = ToolExecutor(str(tmp_repo))
        result = executor.execute("grep", {"pattern": "ZZZZNOTFOUND"})
        assert "No matches" in result

    def test_grep_file_pattern(self, tmp_repo: Path):
        executor = ToolExecutor(str(tmp_repo))
        result = executor.execute("grep", {"pattern": ".", "file_pattern": "*.md"})
        assert "README.md" in result

    def test_unknown_tool(self, tmp_repo: Path):
        executor = ToolExecutor(str(tmp_repo))
        result = executor.execute("delete_file", {"path": "x"})
        assert "Unknown tool" in result
