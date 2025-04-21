import argparse
import ast
import os
from pathlib import Path
from typing import Any

EXCLUDE_DIRS: set[str] = {
    ".idea",
    "__pycache__",
    ".git",
    "node_modules",
    "venv",
    "build",
    "dist",
    ".mypy_cache",
    "migrations",
    ".venv",
    "shopify_client",
    ".run",
}

EXCLUDE_FILES: set[str] = {
    ".env",
    ".gitignore",
    ".coverage",
    "coverage.xml",
    "Pipfile",
    "*.min.js",
    "*.mmdb",
    "pluralize.js",
    ".DS_Store",
    ".gitmodules",
    ".git",
}


def set_parents(node: ast.AST) -> None:
    for child in ast.iter_child_nodes(node):
        child.parent = node
        set_parents(child)


def parse_python_file(file_path: Path) -> tuple[list[str], dict[str, list[str]], str | None]:
    try:
        with open(file_path, encoding="utf-8") as f:
            content = f.read()
        node = ast.parse(content, filename=file_path)
        set_parents(node)
    except Exception as e:
        return [], {}, f"Parsing error: {e}"

    functions = []
    classes = {}
    for n in ast.walk(node):
        if isinstance(n, ast.FunctionDef):
            # Consider only top-level functions (directly under the module)
            if hasattr(n, "parent") and isinstance(n.parent, ast.Module):
                functions.append(n.name)
        elif isinstance(n, ast.ClassDef):
            method_names = []
            for item in n.body:
                if isinstance(item, ast.FunctionDef):
                    method_names.append(item.name)
            classes[n.name] = method_names
    return functions, classes, None


def index_codebase(root: str, exclude_dirs: set[str] | None = None) -> dict[str, dict[str, Any]]:
    if exclude_dirs is None:
        exclude_dirs = EXCLUDE_DIRS
    summary: dict[str, dict[str, Any]] = {}

    for dir_path, dir_names, filenames in os.walk(root):
        dir_names[:] = [d for d in dir_names if d not in exclude_dirs]
        filenames = [f for f in filenames if f not in EXCLUDE_FILES]
        relative_path = os.path.relpath(dir_path, root)
        file_details: dict[str, Any] = {}
        for file in filenames:
            file_path = Path(dir_path) / file
            if file.endswith(".py"):
                funcs, classes, error = parse_python_file(file_path)
                if error:
                    file_details[file] = {"error": error}
                else:
                    file_details[file] = {"functions": funcs, "classes": classes}
            else:
                file_details[file] = {}
        summary[relative_path] = file_details
    return summary


def generate_markdown_summary(summary: dict[str, dict[str, Any]]) -> str:
    md_lines = ["# Codebase Summary", ""]
    for folder, files in sorted(summary.items()):
        md_lines.append(f"## {folder}")
        for file, details in sorted(files.items()):
            md_lines.append(f"- **{file}**")
            if details:
                if "error" in details:
                    md_lines.append(f"  - Error: {details['error']}")
                else:
                    funcs = details.get("functions", [])
                    if funcs:
                        md_lines.append(f"  - Functions: {', '.join(funcs)}")
                    classes = details.get("classes", {})
                    if classes:
                        for cls, methods in classes.items():
                            if methods:
                                md_lines.append(f"  - Class `{cls}` with methods: {', '.join(methods)}")
                            else:
                                md_lines.append(f"  - Class `{cls}` (no methods)")
        md_lines.append("")  # Blank line for spacing
    return "\n".join(md_lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Index your codebase and generate a Markdown summary.")
    parser.add_argument("root", help="Root directory of your codebase", default=".")
    parser.add_argument("-o", "--output", default="codebase_summary.md", help="Output Markdown file")
    args = parser.parse_args()

    summary = index_codebase(args.root)
    md_content = generate_markdown_summary(summary)

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(prompt_content)
        f.write(md_content)
    print(f"Codebase summary generated and saved to {args.output}")


prompt_content = """
# Company Details

- Outboard Parts Warehouse
- Production site: https://odoo.outboardpartswarehouse.com/
- Local development: http://localhost:8069/
- Primary Business: Buying outboard motors, and parting them out on eBay and Shopify
 - GitHub Repository: cbusillo/odoo-addons
- Permanent Branches: opw-prod, opw-testing

# Development Tools

- IntelliJ IDEA Ultimate 2024.3.1.1
- Odoo Framework Integration plugin
- Odoo 18 Enterprise
- Owl.js 2.0
- Python 3.13
- Shopify GraphQL API
- Docker

# Code Standards

- Pythonic, clean, and elegant code
- Follow Odoo core development patterns and best practices
- Proper use of inheritance and extension mechanisms
- Follow standard Odoo project structure and logging patterns
- PEP 8 compliance
- Descriptive function and variable names that convey purpose clearly instead of comments
- No comments or docstrings in returned code

# Workflow

## Code Review Process:

- Retrieve and examine relevant code, models, and views before analysis or explanation. For example, check model fields,
  XML views, and dependencies.
- Check for dependencies that may be relevant to the issue.
- Validate modifications through manual or automated testing.

# Project Structure

## Base Path
- JetBrains Project Root: /Users/cbusillo/Developer/odoo-addons/
- Module location: addons/product_connect

## Key Directories
- models/: Business logic and database models
- views/: XML view definitions
- static/: Static assets (CSS, JS, images)
- security/: Access rights and rules
- data/: Data files and demo data

## Common File Patterns
- Model files: models/*.py
- View files: views/*.xml
- JavaScript files: static/src/js/*.js
"""

if __name__ == "__main__":
    main()
