from pathlib import Path

IGNORE_DIRS = {
    ".git", ".idea", ".vscode",
    "venv", ".venv",
    "__pycache__",
    "node_modules",
    "dist", "build",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox",
}
IGNORE_SUFFIXES = {".pyc", ".pyo"}

def should_skip(path: Path) -> bool:
    if path.name in IGNORE_DIRS:
        return True
    if path.suffix in IGNORE_SUFFIXES:
        return True
    if path.name.endswith(".egg-info"):
        return True
    return False

def print_tree(root: Path, max_depth: int = 6, prefix: str = "", depth: int = 0):
    if depth > max_depth:
        return

    entries = []
    for p in sorted(root.iterdir(), key=lambda x: (x.is_file(), x.name.lower())):
        if should_skip(p):
            continue
        entries.append(p)

    for i, p in enumerate(entries):
        last = (i == len(entries) - 1)
        connector = "└── " if last else "├── "
        print(prefix + connector + p.name)

        if p.is_dir():
            extension = "    " if last else "│   "
            print_tree(p, max_depth=max_depth, prefix=prefix + extension, depth=depth + 1)

if __name__ == "__main__":
    print_tree(Path("."), max_depth=6)
