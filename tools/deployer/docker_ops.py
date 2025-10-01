from collections.abc import Mapping
from pathlib import Path

from .command import run_process


def build_image(
    image: str, context: Path, dockerfile: Path | None = None, build_args: Mapping[str, str] | None = None, target: str | None = None
) -> None:
    command = ["docker", "build", "--tag", image]
    if dockerfile is not None:
        command += ["-f", str(dockerfile)]
    if build_args is not None:
        for key, value in build_args.items():
            command += ["--build-arg", f"{key}={value}"]
    if target is not None:
        command += ["--target", target]
    command.append(str(context))
    run_process(command)


def push_image(image: str) -> None:
    run_process(["docker", "push", image])


def pull_image(image: str) -> None:
    run_process(["docker", "pull", image])


def inspect_image_digest(image: str) -> str:
    result = run_process(["docker", "image", "inspect", "--format", "{{index .RepoDigests 0}}", image], capture_output=True)
    digest = (result.stdout or "").strip()
    if not digest:
        raise ValueError(f"no digest found for {image}")
    return digest
