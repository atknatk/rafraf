"""Git context service — proje git durumunu okur ve sistem prompt'a inject eder."""

from __future__ import annotations

import asyncio

import structlog

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

_GIT_TIMEOUT = 10  # seconds


async def _run_git(args: list[str], project_path: str) -> str:
    """Run a git command and return stdout. Returns empty string on failure."""
    cmd = ["git", "-C", project_path, *args]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=_GIT_TIMEOUT)
        except TimeoutError:
            proc.kill()
            await proc.communicate()
            await logger.awarning("git_command_timeout", cmd=cmd)
            return ""
        if proc.returncode != 0:
            return ""
        return stdout.decode("utf-8", errors="replace").strip()
    except (OSError, FileNotFoundError):
        return ""


async def build_git_context(project_path: str) -> str:
    """Build a git context string for the given project directory.

    Runs several git commands to collect branch, recent commits, changed files,
    and diff stats. Returns a formatted multi-line string ready to be appended
    to a system prompt, or an empty string when the path is not a git repo or
    any error occurs.

    Args:
        project_path: Absolute path to the project directory.

    Returns:
        Formatted git context string, or "" on error.
    """
    # First check: is this a git repo?
    is_repo = await _run_git(["rev-parse", "--is-inside-work-tree"], project_path)
    if is_repo != "true":
        await logger.ainfo("git_context_skipped_not_repo", project_path=project_path)
        return ""

    # Run remaining commands in parallel for speed
    branch_task = asyncio.create_task(
        _run_git(["branch", "--show-current"], project_path)
    )
    status_task = asyncio.create_task(
        _run_git(["status", "--short"], project_path)
    )
    log_task = asyncio.create_task(
        _run_git(["log", "--oneline", "-5"], project_path)
    )
    diff_stat_task = asyncio.create_task(
        _run_git(["diff", "--stat", "HEAD"], project_path)
    )

    branch, status, log, diff_stat = await asyncio.gather(
        branch_task, status_task, log_task, diff_stat_task
    )

    parts: list[str] = ["## Proje Git Durumu"]

    if branch:
        parts.append(f"Branch: {branch}")

    if log:
        log_lines = "\n".join(f"  {line}" for line in log.splitlines())
        parts.append(f"Son Commitler:\n{log_lines}")

    if status:
        status_lines = "\n".join(f"  {line}" for line in status.splitlines())
        parts.append(f"Degisiklikler:\n{status_lines}")
    else:
        parts.append("Temiz calisma dizini (staged/unstaged degisiklik yok)")

    if diff_stat:
        diff_lines = "\n".join(f"  {line}" for line in diff_stat.splitlines())
        parts.append(f"Diff Ozeti:\n{diff_lines}")

    context = "\n".join(parts)

    await logger.ainfo(
        "git_context_built",
        project_path=project_path,
        branch=branch,
        has_changes=bool(status),
    )

    return context
