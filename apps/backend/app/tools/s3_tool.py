"""S3 File Manager Tool - Claude AI tool for S3 file operations.

Cloud tool that runs on EKS (no host agent required).
Provides file upload, download, listing, deletion, and pre-signed URL generation.
"""

import base64

import structlog

from app.orchestrator.tool_registry import ToolDefinition
from app.services.s3_service import S3Service, S3ServiceError
from app.tools.base import BaseTool

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

# Tool schema for Claude API
_S3_TOOL_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "enum": [
                "upload_file",
                "download_file",
                "list_files",
                "delete_file",
                "generate_presigned_upload_url",
                "generate_presigned_download_url",
            ],
            "description": "Yapilacak S3 islemi",
        },
        "project_id": {
            "type": "string",
            "description": "Proje ID'si (bucket yapisi: projects/{project_id}/...)",
        },
        "path": {
            "type": "string",
            "description": (
                "Dosya yolu (proje dizinine goreli, ornek: docs/report.pdf). "
                "upload_file, download_file, delete_file, "
                "generate_presigned_upload_url, generate_presigned_download_url icin"
            ),
        },
        "content_base64": {
            "type": "string",
            "description": "Base64 kodlanmis dosya icerigi (upload_file icin)",
        },
        "content_type": {
            "type": "string",
            "description": (
                "MIME tipi (upload_file ve generate_presigned_upload_url icin, "
                "varsayilan: application/octet-stream)"
            ),
            "default": "application/octet-stream",
        },
        "prefix": {
            "type": "string",
            "description": "Dosya listesi icin prefix filtresi (list_files icin)",
        },
        "max_keys": {
            "type": "integer",
            "description": "Maksimum sonuc sayisi (list_files icin, varsayilan: 100)",
            "default": 100,
        },
        "expiration": {
            "type": "integer",
            "description": (
                "Pre-signed URL gecerlilik suresi saniye cinsinden "
                "(varsayilan: 3600 = 1 saat)"
            ),
            "default": 3600,
        },
    },
    "required": ["action", "project_id"],
}

# Actions that require user approval
_APPROVAL_ACTIONS = frozenset({"upload_file", "delete_file"})


class S3Tool(BaseTool):
    """S3 File Manager tool for Claude AI.

    Provides S3 file operations as a Claude tool. Registered with the
    tool registry and called by the AI orchestrator during tool-calling loops.
    """

    def __init__(self) -> None:
        self._service = S3Service()

    def get_definition(self) -> ToolDefinition:
        """Return the tool definition for Claude API.

        Returns:
            ToolDefinition with s3_file_manager schema.
        """
        return ToolDefinition(
            name="s3_file_manager",
            description=(
                "S3 dosya yonetimi. Dosya yukleme/indirme/listeleme/silme ve "
                "pre-signed URL olusturma. Dosya yukleme ve silme onay gerektirir. "
                "Bucket yapisi: projects/{project_id}/..."
            ),
            input_schema=_S3_TOOL_SCHEMA,
            requires_approval=False,  # Per-action approval checked in execute
            approval_category="write_cloud",
        )

    async def execute(self, params: dict[str, object]) -> str:
        """Execute an S3 action.

        Args:
            params: Tool input parameters from Claude.

        Returns:
            JSON string result.
        """
        action = str(params.get("action", ""))
        project_id = str(params.get("project_id", ""))

        if not action or not project_id:
            return '{"error": "action ve project_id parametreleri zorunludur"}'

        await logger.ainfo(
            "s3_tool_execute",
            action=action,
            project_id=project_id,
        )

        try:
            return await self._dispatch(action, project_id, params)
        except S3ServiceError as exc:
            await logger.aexception(
                "s3_tool_error",
                action=action,
                project_id=project_id,
            )
            return f'{{"error": "S3 hatasi: {exc}"}}'
        except Exception as exc:
            await logger.aexception(
                "s3_tool_unexpected_error",
                action=action,
                project_id=project_id,
            )
            return f'{{"error": "Beklenmeyen hata: {exc}"}}'

    async def _dispatch(
        self, action: str, project_id: str, params: dict[str, object]
    ) -> str:
        """Dispatch to the appropriate action handler.

        Args:
            action: Action name.
            project_id: Project identifier.
            params: Full params dict.

        Returns:
            JSON string result.
        """
        if action == "upload_file":
            return await self._upload_file(project_id, params)
        if action == "download_file":
            return await self._download_file(project_id, params)
        if action == "list_files":
            return await self._list_files(project_id, params)
        if action == "delete_file":
            return await self._delete_file(project_id, params)
        if action == "generate_presigned_upload_url":
            return await self._generate_presigned_upload_url(project_id, params)
        if action == "generate_presigned_download_url":
            return await self._generate_presigned_download_url(project_id, params)
        return f'{{"error": "Bilinmeyen action: {action}"}}'

    def requires_action_approval(self, action: str) -> bool:
        """Check if a specific action requires approval.

        Args:
            action: Action name.

        Returns:
            True if approval is required.
        """
        return action in _APPROVAL_ACTIONS

    async def _upload_file(self, project_id: str, params: dict[str, object]) -> str:
        path = str(params.get("path", ""))
        if not path:
            return '{"error": "path parametresi zorunludur"}'

        content_base64 = str(params.get("content_base64", ""))
        if not content_base64:
            return '{"error": "content_base64 parametresi zorunludur"}'

        try:
            content = base64.b64decode(content_base64)
        except Exception:
            return '{"error": "content_base64 gecersiz base64 formati"}'

        content_type = str(params.get("content_type", "application/octet-stream"))

        result = await self._service.upload_file(
            project_id, path, content, content_type=content_type
        )
        return S3Service.format_result(result)

    async def _download_file(self, project_id: str, params: dict[str, object]) -> str:
        path = str(params.get("path", ""))
        if not path:
            return '{"error": "path parametresi zorunludur"}'

        content = await self._service.download_file(project_id, path)
        encoded = base64.b64encode(content).decode("utf-8")
        result = {
            "path": path,
            "content_base64": encoded,
            "size": str(len(content)),
        }
        return S3Service.format_result(result)

    async def _list_files(self, project_id: str, params: dict[str, object]) -> str:
        prefix = str(params.get("prefix", "")) if params.get("prefix") else ""
        max_keys_raw = params.get("max_keys", 100)
        max_keys = int(max_keys_raw) if isinstance(max_keys_raw, (int, float)) else 100

        files = await self._service.list_files(
            project_id, prefix=prefix, max_keys=max_keys
        )
        return S3Service.format_result(files)

    async def _delete_file(self, project_id: str, params: dict[str, object]) -> str:
        path = str(params.get("path", ""))
        if not path:
            return '{"error": "path parametresi zorunludur"}'

        result = await self._service.delete_file(project_id, path)
        return S3Service.format_result(result)

    async def _generate_presigned_upload_url(
        self, project_id: str, params: dict[str, object]
    ) -> str:
        path = str(params.get("path", ""))
        if not path:
            return '{"error": "path parametresi zorunludur"}'

        content_type = str(params.get("content_type", "application/octet-stream"))
        expiration_raw = params.get("expiration", 3600)
        expiration = (
            int(expiration_raw) if isinstance(expiration_raw, (int, float)) else 3600
        )

        result = await self._service.generate_presigned_upload_url(
            project_id, path, content_type=content_type, expiration=expiration
        )
        return S3Service.format_result(result)

    async def _generate_presigned_download_url(
        self, project_id: str, params: dict[str, object]
    ) -> str:
        path = str(params.get("path", ""))
        if not path:
            return '{"error": "path parametresi zorunludur"}'

        expiration_raw = params.get("expiration", 3600)
        expiration = (
            int(expiration_raw) if isinstance(expiration_raw, (int, float)) else 3600
        )

        result = await self._service.generate_presigned_download_url(
            project_id, path, expiration=expiration
        )
        return S3Service.format_result(result)
