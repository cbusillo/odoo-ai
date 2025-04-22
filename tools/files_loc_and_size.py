#!/usr/bin/env python3

from pathlib import Path

# noinspection PyPackageRequirements
from rich.console import Console

# noinspection PyPackageRequirements
from rich.table import Table

TARGET_EXTENSIONS = {
    "*.py",
    "*.xml",
    "*.js",
    "*.scss",
    "*.graphql",
    "*.yml",
    "*.yaml",
    "*.conf",
    "*.sh",
}
EXCLUDE_DIRS = {
    ".git",
    "__pycache__",
    ".venv",
    "node_modules",
    ".idea",
    "shopify_client",
}
EXCLUDE_FILES = {
    "*.min.js",
    "*.mmdb",
    "pluralize.js",
    ".DS_Store",
}


def matches_pattern(file: Path, patterns: set[str]) -> bool:
    return any(file.match(pattern) for pattern in patterns)


def calculate_loc_and_size(start_dir: str = ".") -> None:
    total_lines = 0
    total_size = 0
    results = []

    console = Console()

    for file in Path(start_dir).rglob("*"):
        if file.is_dir():
            continue
        if any(part in EXCLUDE_DIRS for part in file.parts):
            continue
        if matches_pattern(file, EXCLUDE_FILES):
            continue
        if matches_pattern(file, TARGET_EXTENSIONS):
            try:
                file_size = file.stat().st_size / 1024

                with file.open(encoding="utf-8", errors="ignore") as f:
                    line_count = sum(1 for _ in f)

                results.append((file.stem, line_count, file_size))
                total_lines += line_count
                total_size += file_size
            except Exception as e:
                console.print(f"[red]Error processing file {file}: {e}[/red]")

    results.sort(key=lambda x: x[2])

    table = Table(title="Code Analysis", header_style="bold cyan")
    table.add_column("File", style="dim", no_wrap=True)
    table.add_column("Lines of Code", justify="right")
    table.add_column("Size (KB)", justify="right")

    for file, line_count, file_size in results:
        table.add_row(str(file), str(line_count), f"{file_size:.2f}")

    console.print(table)

    console.print("\n[bold yellow]Summary:[/bold yellow]")
    console.print(f"[green]Total Lines of Code:[/green] {total_lines}")
    console.print(f"[green]Total Size in KB:[/green] {total_size:.2f}")


# Run the script
if __name__ == "__main__":
    calculate_loc_and_size()
