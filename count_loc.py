#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Iterable

DEFAULT_EXTS = {
    ".py", ".js", ".ts", ".jsx", ".tsx",
    ".java", ".kt", ".c", ".h", ".cpp", ".hpp",
    ".go", ".rs", ".php", ".rb",
    ".html", ".css", ".scss",
    ".json", ".yaml", ".yml", ".toml",
    ".md", ".txt",
}

DEFAULT_EXCLUDE_DIRS = {
    ".git", ".hg", ".svn",
    "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    ".idea", ".vscode",
    "venv", ".venv", "env", ".env",
    "node_modules", "dist", "build", "out",
    ".next", ".nuxt",
    "coverage", ".coverage",
}


def iter_files(root: Path, exts: set[str], exclude_dirs: set[str]) -> Iterable[Path]:
    for dirpath, dirnames, filenames in os.walk(root):
        # modyfikujemy dirnames in-place, żeby os.walk nie schodził do wykluczonych katalogów
        dirnames[:] = [d for d in dirnames if d not in exclude_dirs]

        for name in filenames:
            p = Path(dirpath) / name
            if not exts or p.suffix.lower() in exts:
                yield p


def count_nonempty_lines(path: Path, ignore_whitespace_only: bool = True) -> int:
    count = 0
    try:
        # errors="ignore" -> omija krzaki kodowania; chcesz ściślej? ustaw errors="strict"
        with path.open("r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if ignore_whitespace_only:
                    if line.strip():
                        count += 1
                else:
                    if line != "":
                        count += 1
    except (OSError, UnicodeError):
        # nie da się odczytać / dziwne kodowanie
        return 0
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Liczy niepuste linie kodu w projekcie.")
    parser.add_argument("root", nargs="?", default=".", help="Ścieżka do projektu (domyślnie: .)")
    parser.add_argument(
        "--ext",
        action="append",
        default=[],
        help="Rozszerzenie do liczenia (np. --ext .py). Możesz podać wiele razy. "
             "Jeśli nie podasz żadnego, użyje domyślnej listy.",
    )
    parser.add_argument(
        "--exclude-dir",
        action="append",
        default=[],
        help="Nazwa katalogu do wykluczenia (np. --exclude-dir venv). Możesz podać wiele razy.",
    )
    parser.add_argument(
        "--include-hidden",
        action="store_true",
        help="Uwzględnij ukryte pliki/katalogi (z kropką) — domyślnie są pomijane tylko jeśli są na liście exclude.",
    )
    parser.add_argument(
        "--show-top",
        type=int,
        default=0,
        help="Pokaż N plików z największą liczbą niepustych linii.",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()

    exts = {e.lower() if e.startswith(".") else f".{e.lower()}" for e in args.ext} if args.ext else set(DEFAULT_EXTS)
    exclude_dirs = set(DEFAULT_EXCLUDE_DIRS) | set(args.exclude_dir)

    per_file: list[tuple[Path, int]] = []
    total = 0
    files = 0

    for path in iter_files(root, exts, exclude_dirs):
        # Opcjonalnie: pomiń "ukryte" ścieżki
        if not args.include_hidden:
            parts = path.relative_to(root).parts
            if any(part.startswith(".") for part in parts):
                # zostawiamy jednak pliki w katalogach typu ".github" tylko jeśli użytkownik włączy include_hidden
                continue

        n = count_nonempty_lines(path, ignore_whitespace_only=True)
        if n > 0:
            per_file.append((path, n))
            total += n
        files += 1

    print(f"Projekt: {root}")
    print(f"Rozszerzenia: {', '.join(sorted(exts))}")
    print(f"Przeskanowane pliki: {files}")
    print(f"Pliki z >=1 niepustą linią: {len(per_file)}")
    print(f"Łącznie niepustych linii: {total}")

    if args.show_top and per_file:
        per_file.sort(key=lambda x: x[1], reverse=True)
        print("\nTop pliki:")
        for p, n in per_file[: args.show_top]:
            rel = p.relative_to(root)
            print(f"{n:8d}  {rel}")


if __name__ == "__main__":
    main()
