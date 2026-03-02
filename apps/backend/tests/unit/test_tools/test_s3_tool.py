"""Unit tests for S3Tool."""

import base64
import json
from unittest.mock import AsyncMock, patch

from app.services.s3_service import S3ServiceError
from app.tools.s3_tool import S3Tool


class TestGetDefinition:
    """Tests for S3Tool.get_definition."""

    def test_definition_name(self) -> None:
        """get_definition should return tool named s3_file_manager."""
        tool = S3Tool()
        definition = tool.get_definition()
        assert definition.name == "s3_file_manager"

    def test_definition_has_input_schema(self) -> None:
        """get_definition should have a valid input schema."""
        tool = S3Tool()
        definition = tool.get_definition()
        assert "properties" in definition.input_schema
        assert "action" in definition.input_schema["properties"]  # type: ignore[operator]
        assert "project_id" in definition.input_schema["properties"]  # type: ignore[operator]

    def test_definition_required_fields(self) -> None:
        """get_definition should require action and project_id."""
        tool = S3Tool()
        definition = tool.get_definition()
        assert "required" in definition.input_schema
        assert "action" in definition.input_schema["required"]  # type: ignore[operator]
        assert "project_id" in definition.input_schema["required"]  # type: ignore[operator]

    def test_definition_has_all_actions(self) -> None:
        """get_definition schema should list all 6 actions."""
        tool = S3Tool()
        definition = tool.get_definition()
        props = definition.input_schema["properties"]
        actions = props["action"]["enum"]  # type: ignore[index]
        expected = [
            "upload_file",
            "download_file",
            "list_files",
            "delete_file",
            "generate_presigned_upload_url",
            "generate_presigned_download_url",
        ]
        assert actions == expected

    def test_definition_approval_category(self) -> None:
        """get_definition should have write_cloud approval category."""
        tool = S3Tool()
        definition = tool.get_definition()
        assert definition.approval_category == "write_cloud"


class TestRequiresActionApproval:
    """Tests for S3Tool.requires_action_approval."""

    def test_upload_file_requires_approval(self) -> None:
        """upload_file should require approval."""
        tool = S3Tool()
        assert tool.requires_action_approval("upload_file") is True

    def test_delete_file_requires_approval(self) -> None:
        """delete_file should require approval."""
        tool = S3Tool()
        assert tool.requires_action_approval("delete_file") is True

    def test_download_file_no_approval(self) -> None:
        """download_file should not require approval."""
        tool = S3Tool()
        assert tool.requires_action_approval("download_file") is False

    def test_list_files_no_approval(self) -> None:
        """list_files should not require approval."""
        tool = S3Tool()
        assert tool.requires_action_approval("list_files") is False

    def test_presigned_upload_no_approval(self) -> None:
        """generate_presigned_upload_url should not require approval."""
        tool = S3Tool()
        assert tool.requires_action_approval("generate_presigned_upload_url") is False

    def test_presigned_download_no_approval(self) -> None:
        """generate_presigned_download_url should not require approval."""
        tool = S3Tool()
        assert tool.requires_action_approval("generate_presigned_download_url") is False


class TestExecuteMissingParams:
    """Tests for S3Tool.execute with missing parameters."""

    async def test_missing_action_returns_error(self) -> None:
        """execute should return error for missing action."""
        tool = S3Tool()
        result = await tool.execute({"project_id": "proj-1"})
        parsed = json.loads(result)
        assert "error" in parsed

    async def test_missing_project_id_returns_error(self) -> None:
        """execute should return error for missing project_id."""
        tool = S3Tool()
        result = await tool.execute({"action": "list_files"})
        parsed = json.loads(result)
        assert "error" in parsed

    async def test_unknown_action_returns_error(self) -> None:
        """execute should return error for unknown action."""
        tool = S3Tool()
        result = await tool.execute(
            {"action": "unknown_action", "project_id": "proj-1"}
        )
        parsed = json.loads(result)
        assert "error" in parsed
        assert "Bilinmeyen" in parsed["error"]


class TestExecuteUploadFile:
    """Tests for S3Tool.execute upload_file action."""

    async def test_upload_success(self) -> None:
        """execute upload_file should upload and return metadata."""
        tool = S3Tool()
        content = b"Hello, S3!"
        content_b64 = base64.b64encode(content).decode("utf-8")

        mock_result = {
            "bucket": "test-bucket",
            "key": "projects/proj-1/test.txt",
            "size": str(len(content)),
            "content_type": "text/plain",
        }

        with patch.object(
            tool._service, "upload_file", new_callable=AsyncMock, return_value=mock_result
        ):
            result = await tool.execute(
                {
                    "action": "upload_file",
                    "project_id": "proj-1",
                    "path": "test.txt",
                    "content_base64": content_b64,
                    "content_type": "text/plain",
                }
            )

        parsed = json.loads(result)
        assert parsed["key"] == "projects/proj-1/test.txt"
        assert parsed["content_type"] == "text/plain"

    async def test_upload_missing_path(self) -> None:
        """execute upload_file should require path."""
        tool = S3Tool()
        result = await tool.execute(
            {
                "action": "upload_file",
                "project_id": "proj-1",
                "content_base64": "dGVzdA==",
            }
        )
        parsed = json.loads(result)
        assert "error" in parsed
        assert "path" in parsed["error"]

    async def test_upload_missing_content(self) -> None:
        """execute upload_file should require content_base64."""
        tool = S3Tool()
        result = await tool.execute(
            {
                "action": "upload_file",
                "project_id": "proj-1",
                "path": "test.txt",
            }
        )
        parsed = json.loads(result)
        assert "error" in parsed
        assert "content_base64" in parsed["error"]

    async def test_upload_invalid_base64(self) -> None:
        """execute upload_file should return error for invalid base64."""
        tool = S3Tool()
        result = await tool.execute(
            {
                "action": "upload_file",
                "project_id": "proj-1",
                "path": "test.txt",
                "content_base64": "not-valid-base64!!!",
            }
        )
        parsed = json.loads(result)
        assert "error" in parsed
        assert "base64" in parsed["error"]


class TestExecuteDownloadFile:
    """Tests for S3Tool.execute download_file action."""

    async def test_download_success(self) -> None:
        """execute download_file should return base64 encoded content."""
        tool = S3Tool()
        content = b"downloaded content"

        with patch.object(
            tool._service, "download_file", new_callable=AsyncMock, return_value=content
        ):
            result = await tool.execute(
                {
                    "action": "download_file",
                    "project_id": "proj-1",
                    "path": "test.txt",
                }
            )

        parsed = json.loads(result)
        assert parsed["path"] == "test.txt"
        decoded = base64.b64decode(parsed["content_base64"])
        assert decoded == content
        assert parsed["size"] == str(len(content))

    async def test_download_missing_path(self) -> None:
        """execute download_file should require path."""
        tool = S3Tool()
        result = await tool.execute(
            {
                "action": "download_file",
                "project_id": "proj-1",
            }
        )
        parsed = json.loads(result)
        assert "error" in parsed
        assert "path" in parsed["error"]


class TestExecuteListFiles:
    """Tests for S3Tool.execute list_files action."""

    async def test_list_files_success(self) -> None:
        """execute list_files should return file list."""
        tool = S3Tool()
        mock_files = [
            {"key": "projects/proj-1/file1.txt", "size": "1024", "last_modified": "2026-01-01"},
            {"key": "projects/proj-1/file2.pdf", "size": "2048", "last_modified": "2026-01-02"},
        ]

        with patch.object(
            tool._service, "list_files", new_callable=AsyncMock, return_value=mock_files
        ):
            result = await tool.execute(
                {
                    "action": "list_files",
                    "project_id": "proj-1",
                }
            )

        parsed = json.loads(result)
        assert isinstance(parsed, list)
        assert len(parsed) == 2
        assert parsed[0]["key"] == "projects/proj-1/file1.txt"

    async def test_list_files_with_prefix(self) -> None:
        """execute list_files should pass prefix to service."""
        tool = S3Tool()

        with patch.object(
            tool._service, "list_files", new_callable=AsyncMock, return_value=[]
        ) as mock_list:
            await tool.execute(
                {
                    "action": "list_files",
                    "project_id": "proj-1",
                    "prefix": "docs/",
                }
            )

        mock_list.assert_called_once_with("proj-1", prefix="docs/", max_keys=100)

    async def test_list_files_with_max_keys(self) -> None:
        """execute list_files should pass max_keys to service."""
        tool = S3Tool()

        with patch.object(
            tool._service, "list_files", new_callable=AsyncMock, return_value=[]
        ) as mock_list:
            await tool.execute(
                {
                    "action": "list_files",
                    "project_id": "proj-1",
                    "max_keys": 50,
                }
            )

        mock_list.assert_called_once_with("proj-1", prefix="", max_keys=50)


class TestExecuteDeleteFile:
    """Tests for S3Tool.execute delete_file action."""

    async def test_delete_success(self) -> None:
        """execute delete_file should return deletion status."""
        tool = S3Tool()
        mock_result = {"status": "deleted", "key": "projects/proj-1/test.txt"}

        with patch.object(
            tool._service, "delete_file", new_callable=AsyncMock, return_value=mock_result
        ):
            result = await tool.execute(
                {
                    "action": "delete_file",
                    "project_id": "proj-1",
                    "path": "test.txt",
                }
            )

        parsed = json.loads(result)
        assert parsed["status"] == "deleted"

    async def test_delete_missing_path(self) -> None:
        """execute delete_file should require path."""
        tool = S3Tool()
        result = await tool.execute(
            {
                "action": "delete_file",
                "project_id": "proj-1",
            }
        )
        parsed = json.loads(result)
        assert "error" in parsed
        assert "path" in parsed["error"]


class TestExecutePresignedUrls:
    """Tests for S3Tool.execute presigned URL actions."""

    async def test_presigned_upload_success(self) -> None:
        """execute generate_presigned_upload_url should return URL info."""
        tool = S3Tool()
        mock_result = {
            "url": "https://s3.example.com/presigned-upload",
            "key": "projects/proj-1/upload.pdf",
            "method": "PUT",
            "content_type": "application/pdf",
            "expiration_seconds": "3600",
        }

        with patch.object(
            tool._service,
            "generate_presigned_upload_url",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            result = await tool.execute(
                {
                    "action": "generate_presigned_upload_url",
                    "project_id": "proj-1",
                    "path": "upload.pdf",
                    "content_type": "application/pdf",
                }
            )

        parsed = json.loads(result)
        assert parsed["url"] == "https://s3.example.com/presigned-upload"
        assert parsed["method"] == "PUT"

    async def test_presigned_upload_missing_path(self) -> None:
        """execute generate_presigned_upload_url should require path."""
        tool = S3Tool()
        result = await tool.execute(
            {
                "action": "generate_presigned_upload_url",
                "project_id": "proj-1",
            }
        )
        parsed = json.loads(result)
        assert "error" in parsed

    async def test_presigned_download_success(self) -> None:
        """execute generate_presigned_download_url should return URL info."""
        tool = S3Tool()
        mock_result = {
            "url": "https://s3.example.com/presigned-download",
            "key": "projects/proj-1/download.pdf",
            "method": "GET",
            "expiration_seconds": "3600",
        }

        with patch.object(
            tool._service,
            "generate_presigned_download_url",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            result = await tool.execute(
                {
                    "action": "generate_presigned_download_url",
                    "project_id": "proj-1",
                    "path": "download.pdf",
                }
            )

        parsed = json.loads(result)
        assert parsed["url"] == "https://s3.example.com/presigned-download"
        assert parsed["method"] == "GET"

    async def test_presigned_download_missing_path(self) -> None:
        """execute generate_presigned_download_url should require path."""
        tool = S3Tool()
        result = await tool.execute(
            {
                "action": "generate_presigned_download_url",
                "project_id": "proj-1",
            }
        )
        parsed = json.loads(result)
        assert "error" in parsed

    async def test_presigned_upload_custom_expiration(self) -> None:
        """execute generate_presigned_upload_url should pass custom expiration."""
        tool = S3Tool()

        with patch.object(
            tool._service,
            "generate_presigned_upload_url",
            new_callable=AsyncMock,
            return_value={"url": "https://s3.example.com", "key": "k", "method": "PUT",
                          "content_type": "application/octet-stream",
                          "expiration_seconds": "7200"},
        ) as mock_gen:
            await tool.execute(
                {
                    "action": "generate_presigned_upload_url",
                    "project_id": "proj-1",
                    "path": "upload.pdf",
                    "expiration": 7200,
                }
            )

        mock_gen.assert_called_once_with(
            "proj-1",
            "upload.pdf",
            content_type="application/octet-stream",
            expiration=7200,
        )


class TestExecuteErrorHandling:
    """Tests for error handling in S3Tool.execute."""

    async def test_s3_service_error_returns_error_json(self) -> None:
        """execute should return error JSON when S3ServiceError raised."""
        tool = S3Tool()

        with patch.object(
            tool._service,
            "list_files",
            new_callable=AsyncMock,
            side_effect=S3ServiceError("Bucket not found", operation="list_files"),
        ):
            result = await tool.execute(
                {"action": "list_files", "project_id": "proj-1"}
            )

        assert "error" in result
        assert "S3 hatasi" in result

    async def test_unexpected_error_returns_error_json(self) -> None:
        """execute should return error JSON for unexpected exceptions."""
        tool = S3Tool()

        with patch.object(
            tool._service,
            "list_files",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Unexpected"),
        ):
            result = await tool.execute(
                {"action": "list_files", "project_id": "proj-1"}
            )

        assert "error" in result
        assert "Beklenmeyen hata" in result


class TestToolRegistration:
    """Tests for S3Tool registration flow."""

    def test_register_adds_to_registry(self) -> None:
        """register should add tool to ToolRegistry."""
        from app.orchestrator.tool_registry import ToolRegistry

        tool = S3Tool()
        registry = ToolRegistry()
        tool.register(registry)

        assert registry.has_tool("s3_file_manager")
        assert registry.tool_count == 1

    def test_registered_handler_is_callable(self) -> None:
        """registered handler should be the execute method."""
        from app.orchestrator.tool_registry import ToolRegistry

        tool = S3Tool()
        registry = ToolRegistry()
        tool.register(registry)

        handler = registry.get_handler("s3_file_manager")
        assert handler is not None
