"""Repository scanner - walks a repo, respects .gitignore, builds file tree."""

from __future__ import annotations

import fnmatch
import mimetypes
import os
from dataclasses import dataclass, field
from pathlib import Path

# Extensions that are almost certainly binary
BINARY_EXTENSIONS = frozenset(
    {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".bmp",
        ".ico",
        ".svg",
        ".webp",
        ".mp3",
        ".mp4",
        ".wav",
        ".avi",
        ".mov",
        ".mkv",
        ".zip",
        ".tar",
        ".gz",
        ".bz2",
        ".xz",
        ".7z",
        ".rar",
        ".exe",
        ".dll",
        ".so",
        ".dylib",
        ".o",
        ".a",
        ".pyc",
        ".pyo",
        ".class",
        ".wasm",
        ".pdf",
        ".doc",
        ".docx",
        ".xls",
        ".xlsx",
        ".ppt",
        ".pptx",
        ".ttf",
        ".otf",
        ".woff",
        ".woff2",
        ".eot",
        ".sqlite",
        ".db",
        ".sqlite3",
        ".bin",
        ".dat",
        ".pack",
        ".idx",
    }
)

# Directories to always skip (single source of truth — imported by agents.py)
SKIP_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "node_modules",
        "__pycache__",
        ".tox",
        ".nox",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "venv",
        ".venv",
        "env",
        ".env",
        "dist",
        "build",
        ".eggs",
        "*.egg-info",
        ".terraform",
        ".serverless",
        "vendor",
        "third_party",
    }
)


@dataclass
class FileInfo:
    """Metadata about a single file in the repository."""

    relative_path: str
    size_bytes: int
    extension: str
    is_binary: bool


@dataclass
class RepoMap:
    """Complete map of a repository's file structure."""

    root: str
    files: list[FileInfo] = field(default_factory=list)
    total_files: int = 0
    total_size_bytes: int = 0
    skipped_dirs: list[str] = field(default_factory=list)

    @property
    def file_tree(self) -> str:
        """Return a textual file tree representation."""
        lines: list[str] = []
        dirs: dict[str, list[str]] = {}
        for f in self.files:
            # Use forward-slash splitting to avoid Windows backslash issues
            if "/" in f.relative_path:
                parent = f.relative_path.rsplit("/", 1)[0]
                name = f.relative_path.rsplit("/", 1)[1]
            else:
                parent = ""
                name = f.relative_path
            dirs.setdefault(parent, []).append(name)

        for dir_path in sorted(dirs.keys()):
            if dir_path:
                lines.append(f"{dir_path}/")
            for name in sorted(dirs[dir_path]):
                prefix = f"  {dir_path}/" if dir_path else ""
                lines.append(f"  {prefix}{name}")

        return "\n".join(lines)

    @property
    def source_files(self) -> list[FileInfo]:
        """Return only non-binary source files."""
        return [f for f in self.files if not f.is_binary]


def _parse_gitignore(repo_path: Path) -> list[str]:
    """Parse .gitignore and return a list of patterns."""
    gitignore_path = repo_path / ".gitignore"
    patterns: list[str] = []
    if gitignore_path.is_file():
        try:
            text = gitignore_path.read_text(encoding="utf-8", errors="ignore")
            for line in text.splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    patterns.append(line)
        except OSError:
            pass
    return patterns


def _is_gitignored(relative_path: str, patterns: list[str]) -> bool:
    """Check if a relative path matches any gitignore pattern."""
    parts = Path(relative_path).parts
    for pattern in patterns:
        # Check against the full relative path
        if fnmatch.fnmatch(relative_path, pattern):
            return True
        # Check against just the filename
        if fnmatch.fnmatch(parts[-1], pattern):
            return True
        # Check against path components for directory patterns
        clean = pattern.rstrip("/")
        for part in parts:
            if fnmatch.fnmatch(part, clean):
                return True
    return False


def _should_skip_dir(dirname: str) -> bool:
    """Check if a directory should be skipped entirely."""
    for pattern in SKIP_DIRS:
        if fnmatch.fnmatch(dirname, pattern):
            return True
    return False


def _is_binary_file(filepath: Path) -> bool:
    """Heuristic check for binary files."""
    ext = filepath.suffix.lower()
    if ext in BINARY_EXTENSIONS:
        return True

    # Check MIME type
    mime, _ = mimetypes.guess_type(str(filepath))
    if mime and not mime.startswith("text/") and mime != "application/json":
        # Some application/* types are text
        text_app_types = {
            "application/xml",
            "application/javascript",
            "application/typescript",
            "application/x-yaml",
            "application/toml",
            "application/x-sh",
        }
        if mime not in text_app_types:
            return True

    # Last resort: try reading a chunk
    try:
        with open(filepath, "rb") as f:
            chunk = f.read(8192)
            if b"\x00" in chunk:
                return True
    except OSError:
        return True

    return False


def scan_repo(path: str | Path) -> RepoMap:
    """Walk a repository directory and build a RepoMap.

    Respects .gitignore patterns, skips binary files and known unneeded directories.
    """
    repo_path = Path(path).resolve()
    if not repo_path.is_dir():
        raise FileNotFoundError(f"Repository path does not exist: {repo_path}")

    gitignore_patterns = _parse_gitignore(repo_path)
    repo_map = RepoMap(root=str(repo_path))

    for dirpath_str, dirnames, filenames in os.walk(repo_path):
        dirpath = Path(dirpath_str)
        rel_dir = dirpath.relative_to(repo_path)

        # Filter out directories to skip (modifying dirnames in-place prunes os.walk)
        dirnames[:] = [
            d
            for d in dirnames
            if not _should_skip_dir(d) and not _is_gitignored(str(rel_dir / d), gitignore_patterns)
        ]

        for filename in filenames:
            filepath = dirpath / filename
            rel_path = str(filepath.relative_to(repo_path)).replace("\\", "/")

            if _is_gitignored(rel_path, gitignore_patterns):
                continue

            try:
                stat = filepath.stat()
                size = stat.st_size
            except OSError:
                continue

            # Skip very large files (>2MB)
            if size > 2 * 1024 * 1024:
                continue

            ext = filepath.suffix.lower()
            is_binary = _is_binary_file(filepath)

            file_info = FileInfo(
                relative_path=rel_path,
                size_bytes=size,
                extension=ext,
                is_binary=is_binary,
            )
            repo_map.files.append(file_info)
            repo_map.total_files += 1
            repo_map.total_size_bytes += size

    return repo_map
