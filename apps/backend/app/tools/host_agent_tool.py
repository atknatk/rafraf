"""Host Agent Tool - Claude AI tool for dispatching tasks to host agents.

Enables the AI orchestrator to execute commands on remote host agents
(shell, docker, playwright, maestro) and query agent status.
"""

import json

import structlog

from app.orchestrator.tool_registry import ToolDefinition
from app.schemas.agent import AgentCapability
from app.services.agent_registry_service import AgentRegistryService
from app.services.task_manager_service import TaskManager
from app.tools.base import BaseTool

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

# Capability required per runner
_RUNNER_CAPABILITY: dict[str, AgentCapability] = {
    "shell": AgentCapability.SHELL,
    "docker": AgentCapability.DOCKER,
    "playwright": AgentCapability.PLAYWRIGHT,
    "maestro": AgentCapability.MAESTRO_IOS,
}

_HOST_AGENT_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "enum": [
                "execute_command",
                "docker_compose",
                "run_playwright_test",
                "run_maestro_test",
                "list_agents",
                "get_agent_status",
            ],
            "description": (
                "Yapilacak islem. execute_command: shell komutu calistir, "
                "docker_compose: docker compose islemleri, "
                "run_playwright_test: web testi, run_maestro_test: mobil test, "
                "list_agents: bagli agentlari listele, "
                "get_agent_status: agent detayi"
            ),
        },
        "host_id": {
            "type": "string",
            "description": (
                "Hedef agent host_id (ornek: macbook-pro). "
                "'auto' olursa en uygun agent otomatik secilir."
            ),
        },
        "command": {
            "type": "string",
            "description": "Shell komutu (execute_command icin)",
        },
        "cwd": {
            "type": "string",
            "description": "Calisma dizini (execute_command icin, opsiyonel)",
        },
        "timeout": {
            "type": "integer",
            "description": "Zaman asimi (saniye, opsiyonel)",
        },
        "compose_action": {
            "type": "string",
            "enum": [
                "compose_up",
                "compose_down",
                "compose_restart",
                "compose_logs",
                "health_check",
                "container_status",
            ],
            "description": "Docker compose islemi (docker_compose icin)",
        },
        "project_slug": {
            "type": "string",
            "description": "Docker proje adi (docker_compose icin)",
        },
        "services": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Docker servisleri (opsiyonel)",
        },
        "url": {
            "type": "string",
            "description": "Test URL (run_playwright_test icin)",
        },
        "playwright_action": {
            "type": "string",
            "enum": [
                "take_screenshot",
                "check_page_load",
                "check_element",
                "fill_form",
                "wait_for_response",
            ],
            "description": "Playwright islemi (run_playwright_test icin)",
        },
        "flow_file": {
            "type": "string",
            "description": "Maestro flow dosyasi yolu (run_maestro_test icin)",
        },
        "platform": {
            "type": "string",
            "enum": ["ios", "android"],
            "description": "Hedef platform (run_maestro_test icin)",
        },
        "params": {
            "type": "object",
            "description": "Ek parametreler (runner'a ozel)",
        },
    },
    "required": ["action"],
}


class HostAgentTool(BaseTool):
    """Host Agent tool for dispatching tasks to remote agents."""

    def __init__(
        self,
        task_manager: TaskManager,
        agent_registry: AgentRegistryService,
    ) -> None:
        self._task_manager = task_manager
        self._agent_registry = agent_registry

    def get_definition(self) -> ToolDefinition:
        """Return the tool definition for Claude API."""
        return ToolDefinition(
            name="host_agent",
            description=(
                "Host agent makinelerinde komut calistirir. Shell komutlari, "
                "Docker Compose islemleri, Playwright web testleri ve Maestro "
                "mobil testleri calistirabilir. Agent listesi ve durumu sorgulayabilir."
            ),
            input_schema=_HOST_AGENT_SCHEMA,
            requires_approval=False,
        )

    async def execute(self, params: dict[str, object]) -> str:
        """Execute a host agent action."""
        action = str(params.get("action", ""))

        if not action:
            return '{"error": "action parametresi zorunludur"}'

        await logger.ainfo("host_agent_tool_execute", action=action)

        try:
            if action == "list_agents":
                return await self._list_agents()
            if action == "get_agent_status":
                return await self._get_agent_status(params)
            if action == "execute_command":
                return await self._execute_command(params)
            if action == "docker_compose":
                return await self._docker_compose(params)
            if action == "run_playwright_test":
                return await self._run_playwright_test(params)
            if action == "run_maestro_test":
                return await self._run_maestro_test(params)
            return json.dumps({"error": f"Bilinmeyen action: {action}"})
        except ValueError as exc:
            return json.dumps({"error": str(exc)})
        except TimeoutError:
            return json.dumps({"error": "Agent zaman asimina ugradi. Islem tamamlanamadi."})
        except RuntimeError as exc:
            return json.dumps({"error": f"Agent hatasi: {exc}"})
        except Exception as exc:
            await logger.aexception("host_agent_tool_unexpected_error", action=action)
            return json.dumps({"error": f"Beklenmeyen hata: {exc}"})

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    async def _list_agents(self) -> str:
        response = await self._agent_registry.list_agents()
        agents = []
        for a in response.agents:
            agents.append({
                "host_id": a.host_id,
                "status": a.status.value,
                "capabilities": [c.value for c in a.capabilities],
                "os_info": a.os_info,
                "active_tasks": a.active_tasks,
                "uptime_seconds": a.uptime_seconds,
            })
        return json.dumps({
            "agents": agents,
            "total": response.total,
            "online_count": response.online_count,
        })

    async def _get_agent_status(self, params: dict[str, object]) -> str:
        host_id = str(params.get("host_id", ""))
        if not host_id:
            return '{"error": "host_id parametresi zorunludur"}'

        detail = await self._agent_registry.get_agent(host_id)
        if detail is None:
            return json.dumps({"error": f"Agent '{host_id}' bulunamadi"})

        return json.dumps({
            "host_id": detail.host_id,
            "status": detail.status.value,
            "capabilities": [c.value for c in detail.capabilities],
            "os_info": detail.os_info,
            "uptime_seconds": detail.uptime_seconds,
            "active_tasks": detail.active_tasks,
            "resources": detail.resources,
            "registered_at": detail.registered_at,
        })

    def _resolve_host_id(
        self,
        params: dict[str, object],
        required_capability: AgentCapability | None = None,
    ) -> str:
        """Resolve host_id from params, supporting 'auto' selection."""
        host_id = str(params.get("host_id", "auto"))

        if host_id == "auto":
            resolved = self._agent_registry.get_least_busy_online(required_capability)
            if resolved is None:
                cap_str = required_capability.value if required_capability else "herhangi"
                msg = f"Uygun agent bulunamadi (gerekli yetenek: {cap_str})"
                raise ValueError(msg)
            return resolved

        # Verify agent is online
        conn = self._agent_registry.get_connection_id(host_id)
        if conn is None:
            msg = f"Agent '{host_id}' bulunamadi veya cevrimdisi"
            raise ValueError(msg)
        return host_id

    async def _execute_command(self, params: dict[str, object]) -> str:
        command = params.get("command")
        if not command or not isinstance(command, str):
            return '{"error": "command parametresi zorunludur"}'

        host_id = self._resolve_host_id(params, AgentCapability.SHELL)

        runner_params: dict[str, object] = {"command": command}
        if params.get("cwd"):
            runner_params["cwd"] = str(params["cwd"])
        if timeout_val := params.get("timeout"):
            runner_params["timeout"] = int(str(timeout_val))

        result = await self._task_manager.dispatch(
            host_id=host_id,
            runner="shell",
            action="run_command",
            params=runner_params,
        )
        return json.dumps(result)

    async def _docker_compose(self, params: dict[str, object]) -> str:
        compose_action = str(params.get("compose_action", ""))
        project_slug = str(params.get("project_slug", ""))

        if not compose_action:
            return '{"error": "compose_action parametresi zorunludur"}'
        if not project_slug:
            return '{"error": "project_slug parametresi zorunludur"}'

        host_id = self._resolve_host_id(params, AgentCapability.DOCKER)

        runner_params: dict[str, object] = {"project_slug": project_slug}
        if params.get("services"):
            runner_params["services"] = params["services"]

        result = await self._task_manager.dispatch(
            host_id=host_id,
            runner="docker",
            action=compose_action,
            params=runner_params,
        )
        return json.dumps(result)

    async def _run_playwright_test(self, params: dict[str, object]) -> str:
        url = str(params.get("url", ""))
        pw_action = str(params.get("playwright_action", "take_screenshot"))

        if not url:
            return '{"error": "url parametresi zorunludur"}'

        host_id = self._resolve_host_id(params, AgentCapability.PLAYWRIGHT)

        runner_params: dict[str, object] = {"url": url}
        if params.get("params") and isinstance(params["params"], dict):
            runner_params.update(params["params"])

        result = await self._task_manager.dispatch(
            host_id=host_id,
            runner="playwright",
            action=pw_action,
            params=runner_params,
        )
        return json.dumps(result)

    async def _run_maestro_test(self, params: dict[str, object]) -> str:
        flow_file = str(params.get("flow_file", ""))

        if not flow_file:
            return '{"error": "flow_file parametresi zorunludur"}'

        host_id = self._resolve_host_id(params, AgentCapability.MAESTRO_IOS)

        runner_params: dict[str, object] = {
            "flow_file": flow_file,
        }
        if params.get("platform"):
            runner_params["platform"] = str(params["platform"])
        if params.get("params") and isinstance(params["params"], dict):
            runner_params.update(params["params"])

        result = await self._task_manager.dispatch(
            host_id=host_id,
            runner="maestro",
            action="run_flow",
            params=runner_params,
        )
        return json.dumps(result)
