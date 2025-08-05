"""File consolidator for GPT analysis - handles large file sets without context pollution."""

import os
import tempfile
from typing import Callable
import shutil


def consolidate_for_gpt_analysis(
    test_files: list[str],
    model_files: list[str],
    analysis_type: str = "general",
    max_files_per_chunk: int = 10,
    max_size_mb_per_chunk: int = 25,
) -> dict[str, list[str] | Callable[[], None]]:
    """Consolidate files into uploadable chunks for GPT analysis.

    Args:
        test_files: List of test file paths
        model_files: List of model file paths
        analysis_type: Type of analysis (for file naming)
        max_files_per_chunk: Maximum files per consolidated chunk
        max_size_mb_per_chunk: Maximum size in MB per chunk

    Returns:
        Dict with:
            - test_chunks: List of consolidated test file paths
            - model_chunks: List of consolidated model file paths
            - cleanup_func: Function to clean up temporary files
    """
    temp_dir = tempfile.mkdtemp(prefix=f"gpt_{analysis_type}_")
    chunks = {"test_chunks": [], "model_chunks": []}

    def create_chunks(files: list[str], chunk_type: str) -> list[str]:
        """Create consolidated chunks from file list."""
        consolidated_files = []
        current_chunk = []
        current_size = 0
        chunk_num = 1

        for file_path in files:
            try:
                file_size = os.path.getsize(file_path) / (1024 * 1024)  # Size in MB

                # Check if we need to start a new chunk
                if (len(current_chunk) >= max_files_per_chunk or current_size + file_size > max_size_mb_per_chunk) and current_chunk:
                    # Write current chunk
                    chunk_path = os.path.join(temp_dir, f"{chunk_type}_chunk_{chunk_num}.md")
                    write_chunk(current_chunk, chunk_path, chunk_type)
                    consolidated_files.append(chunk_path)

                    # Reset for next chunk
                    current_chunk = []
                    current_size = 0
                    chunk_num += 1

                current_chunk.append(file_path)
                current_size += file_size

            except Exception as e:
                print(f"Warning: Could not process {file_path}: {e}")
                continue

        # Write final chunk if any files remain
        if current_chunk:
            chunk_path = os.path.join(temp_dir, f"{chunk_type}_chunk_{chunk_num}.md")
            write_chunk(current_chunk, chunk_path, chunk_type)
            consolidated_files.append(chunk_path)

        return consolidated_files

    def write_chunk(file_paths: list[str], output_path: str, chunk_type: str) -> None:
        """Write a consolidated chunk file in markdown format."""
        with open(output_path, "w", encoding="utf-8") as out:
            out.write(f"# {chunk_type.upper()} FILES CHUNK\n\n")
            out.write(f"This chunk contains {len(file_paths)} files.\n\n")

            for file_path in file_paths:
                try:
                    # Get relative path for context
                    rel_path = file_path
                    if "addons/product_connect" in file_path:
                        rel_path = file_path.split("addons/product_connect")[-1]

                    out.write(f"## File: {rel_path}\n\n")
                    out.write("```python\n")

                    with open(file_path, encoding="utf-8") as f:
                        content = f.read()
                        out.write(content)
                        if not content.endswith("\n"):
                            out.write("\n")

                    out.write("```\n\n")

                except Exception as e:
                    out.write(f"ERROR reading file: {e}\n\n")

    # Process test and model files
    chunks["test_chunks"] = create_chunks(test_files, "test")
    chunks["model_chunks"] = create_chunks(model_files, "model")

    # Cleanup function
    def cleanup() -> None:
        """Remove temporary directory and all consolidated files."""
        try:
            shutil.rmtree(temp_dir)
            print(f"Cleaned up temporary files in {temp_dir}")
        except Exception as e:
            print(f"Warning: Could not clean up {temp_dir}: {e}")

    chunks["cleanup_func"] = cleanup

    # Print summary
    print(f"Consolidation complete:")
    print(f"  - Test files: {len(test_files)} -> {len(chunks['test_chunks'])} chunks")
    print(f"  - Model files: {len(model_files)} -> {len(chunks['model_chunks'])} chunks")
    print(f"  - Temporary directory: {temp_dir}")

    return chunks


def calculate_token_estimate(file_path: str) -> int:
    """Estimate token count for a file (rough approximation)."""
    try:
        with open(file_path, encoding="utf-8") as f:
            content = f.read()
            # Rough estimate: 1 token ≈ 4 characters
            return len(content) // 4
    except:
        return 0


def analyze_file_set(files: list[str]) -> dict[str, int]:
    """Analyze a set of files for size and token estimates."""
    total_size = 0
    total_tokens = 0

    for file_path in files:
        try:
            size = os.path.getsize(file_path)
            tokens = calculate_token_estimate(file_path)
            total_size += size
            total_tokens += tokens
        except:
            continue

    return {"file_count": len(files), "total_size_mb": round(total_size / (1024 * 1024), 2), "estimated_tokens": total_tokens}
