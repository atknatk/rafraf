"""Git diff service — proje degisikliklerini parse eder."""

from __future__ import annotations

import asyncio

import structlog

from app.schemas.messages import (
    CodeDiffFilePayload,
    CodeDiffLinePayload,
    CodeDiffPayload,
)

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

_GIT_DIFF_TIMEOUT = 30  # seconds
_MAX_FILES = 20
_MAX_LINES = 500


async def get_project_diff(project_path: str) -> CodeDiffPayload | None:
    """Projenin git diff ciktisini alinir ve parse edilir.

    `git -C <path> diff HEAD` komutu calistirilir; boş çıktı veya hata
    durumunda None döner.

    Args:
        project_path: Projenin mutlak dosya sistemi yolu.

    Returns:
        CodeDiffPayload ya da None (degisiklik yok / hata).
    """
    cmd = ["git", "-C", project_path, "diff", "HEAD"]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_bytes, _ = await asyncio.wait_for(proc.communicate(), timeout=_GIT_DIFF_TIMEOUT)
        except TimeoutError:
            proc.kill()
            await proc.communicate()
            await logger.awarning("git_diff_timeout", project_path=project_path)
            return None

        if proc.returncode != 0:
            return None

        raw = stdout_bytes.decode("utf-8", errors="replace")
    except (OSError, FileNotFoundError):
        await logger.awarning("git_diff_exec_error", project_path=project_path)
        return None

    if not raw.strip():
        return None

    try:
        return _parse_diff(raw, project_path)
    except Exception:
        await logger.awarning("git_diff_parse_error", project_path=project_path)
        return None


def _parse_diff(raw: str, project_path: str) -> CodeDiffPayload | None:
    """Unified diff metnini parse ederek CodeDiffPayload olusturur."""
    files: list[CodeDiffFilePayload] = []
    total_additions = 0
    total_deletions = 0

    # Her `diff --git` blogu bir dosyaya karsilik gelir
    blocks = _split_into_file_blocks(raw)

    for block in blocks[:_MAX_FILES]:
        file_payload = _parse_file_block(block)
        if file_payload is not None:
            files.append(file_payload)
            total_additions += file_payload.additions
            total_deletions += file_payload.deletions

    if not files:
        return None

    return CodeDiffPayload(
        project_path=project_path,
        total_additions=total_additions,
        total_deletions=total_deletions,
        files_changed=len(files),
        files=files,
    )


def _split_into_file_blocks(raw: str) -> list[str]:
    """Unified diff metnini dosya bloklarına ayirir."""
    blocks: list[str] = []
    current: list[str] = []

    for line in raw.splitlines(keepends=True):
        if line.startswith("diff --git") and current:
            blocks.append("".join(current))
            current = []
        current.append(line)

    if current:
        blocks.append("".join(current))

    return blocks


def _parse_file_block(block: str) -> CodeDiffFilePayload | None:
    """Tek bir dosya diff blogunu parse eder."""
    lines_text = block.splitlines()
    if not lines_text:
        return None

    # Dosya yolunu `diff --git a/... b/...` satirindan al
    file_path = _extract_file_path(lines_text[0])
    if not file_path:
        return None

    is_new_file = any(line.startswith("new file mode") for line in lines_text)
    is_deleted = any(line.startswith("deleted file mode") for line in lines_text)

    diff_lines: list[CodeDiffLinePayload] = []
    additions = 0
    deletions = 0
    line_old = 0
    line_new = 0
    parsed_count = 0

    for line in lines_text:
        if parsed_count >= _MAX_LINES:
            break

        if line.startswith("@@"):
            # Hunk header: @@ -old_start,old_count +new_start,new_count @@
            old_start, new_start = _parse_hunk_header(line)
            line_old = old_start
            line_new = new_start
            continue

        if line.startswith("+") and not line.startswith("+++"):
            diff_lines.append(
                CodeDiffLinePayload(
                    type="added",
                    content=line[1:],
                    line_number_new=line_new,
                )
            )
            additions += 1
            line_new += 1
            parsed_count += 1
        elif line.startswith("-") and not line.startswith("---"):
            diff_lines.append(
                CodeDiffLinePayload(
                    type="removed",
                    content=line[1:],
                    line_number_old=line_old,
                )
            )
            deletions += 1
            line_old += 1
            parsed_count += 1
        elif line.startswith(" "):
            diff_lines.append(
                CodeDiffLinePayload(
                    type="context",
                    content=line[1:],
                    line_number_old=line_old,
                    line_number_new=line_new,
                )
            )
            line_old += 1
            line_new += 1
            parsed_count += 1

    return CodeDiffFilePayload(
        file_path=file_path,
        is_new_file=is_new_file,
        is_deleted=is_deleted,
        additions=additions,
        deletions=deletions,
        lines=diff_lines,
    )


def _extract_file_path(diff_header: str) -> str | None:
    """diff --git a/<path> b/<path> satirindan dosya yolunu cikarir."""
    # `diff --git a/foo/bar.py b/foo/bar.py`
    parts = diff_header.split(" ")
    if len(parts) < 4:
        return None
    # b/ ile baslayan kisim son dosya yolu
    b_part = parts[-1]
    if b_part.startswith("b/"):
        return b_part[2:]
    return b_part


def _parse_hunk_header(header: str) -> tuple[int, int]:
    """@@ -old_start,... +new_start,... @@ satirini parse eder."""
    try:
        # `@@ -3,7 +3,6 @@` gibi bir satir
        at_parts = header.split("@@")
        if len(at_parts) < 2:
            return 1, 1
        range_part = at_parts[1].strip()
        old_part, new_part = range_part.split(" ")
        old_start = int(old_part.lstrip("-").split(",")[0])
        new_start = int(new_part.lstrip("+").split(",")[0])
        return old_start, new_start
    except (ValueError, IndexError):
        return 1, 1
