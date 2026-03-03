"""REST endpoints for Maestro mobile test integration.

Flow calistirma, suite calistirma, flow dogrulama, screenshot alma,
flow listeleme ve test raporu olusturma endpoint'leri.
"""

import structlog
from fastapi import APIRouter

from app.schemas.maestro import (
    ListFlowsRequest,
    ListFlowsResponse,
    MaestroTestReport,
    RunFlowRequest,
    RunFlowResponse,
    RunSuiteRequest,
    RunSuiteResponse,
    ScreenshotResponse,
    TakeScreenshotRequest,
    ValidateFlowRequest,
    ValidateFlowResponse,
)
from app.services.maestro_service import MaestroService

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/maestro", tags=["maestro"])

_service = MaestroService()


@router.post("/run-flow", response_model=RunFlowResponse)
async def run_flow(request: RunFlowRequest) -> RunFlowResponse:
    """Tek bir Maestro flow dosyasini calistirir.

    Agent tarafindaki MaestroRunner'a dispatch eder.
    Sonucu isleyerek yapilandirilmis yanit doner.
    """
    await logger.ainfo(
        "maestro_run_flow_request",
        flow_file=request.flow_file,
        platform=request.platform,
        timeout=request.timeout,
    )

    # Agent dispatch icin parametre hazirlama
    runner_params: dict[str, object] = {
        "flow_file": request.flow_file,
        "platform": request.platform.value,
        "timeout": request.timeout,
    }
    if request.cwd is not None:
        runner_params["cwd"] = request.cwd
    if request.project_slug is not None:
        runner_params["project_slug"] = request.project_slug

    # Placeholder: Agent dispatch mekanizmasi uzerinden calistirilacak
    # Simdilik bos sonuc donduruyor, agent baglantisi yapildiginda
    # gercek MaestroRunner.execute("run_flow", runner_params) cagirilacak
    runner_result: dict[str, object] = {
        "success": False,
        "error": "Agent baglantisi bekleniyor. MaestroRunner henuz dispatch edilmedi.",
        "output": "",
        "timed_out": False,
    }

    return await _service.run_flow(
        runner_result=runner_result,
        flow_file=request.flow_file,
        platform=request.platform.value,
    )


@router.post("/run-suite", response_model=RunSuiteResponse)
async def run_suite(request: RunSuiteRequest) -> RunSuiteResponse:
    """Birden fazla flow iceren bir suite'i calistirir.

    Her flow sirasiyla agent'a dispatch edilir.
    stop_on_failure True ise ilk hata aninda durur.
    """
    await logger.ainfo(
        "maestro_run_suite_request",
        suite_name=request.suite_name,
        flow_count=len(request.flows),
        stop_on_failure=request.stop_on_failure,
    )

    # Her flow icin runner sonuclarini topla
    runner_results: list[dict[str, object]] = []

    for flow_def in request.flows:
        runner_params: dict[str, object] = {
            "flow_file": flow_def.flow_file,
            "platform": flow_def.platform.value,
            "timeout": flow_def.timeout,
        }
        if request.cwd is not None:
            runner_params["cwd"] = request.cwd
        if request.project_slug is not None:
            runner_params["project_slug"] = request.project_slug

        # Placeholder: Agent dispatch
        runner_result: dict[str, object] = {
            "success": False,
            "error": "Agent baglantisi bekleniyor.",
            "output": "",
            "timed_out": False,
        }
        runner_results.append(runner_result)

        # Stop on failure kontrolu
        if request.stop_on_failure and not runner_result.get("success", False):
            break

    return await _service.run_suite(
        suite_name=request.suite_name,
        flows=request.flows,
        runner_results=runner_results,
        stop_on_failure=request.stop_on_failure,
    )


@router.post("/validate-flow", response_model=ValidateFlowResponse)
async def validate_flow(request: ValidateFlowRequest) -> ValidateFlowResponse:
    """Flow dosyasinin gecerliligini kontrol eder.

    Maestro YAML syntax dogrulamasi yapar.
    """
    await logger.ainfo(
        "maestro_validate_flow_request",
        flow_file=request.flow_file,
    )

    # Placeholder: Agent dispatch
    runner_result: dict[str, object] = {
        "success": False,
        "valid": False,
        "error": "Agent baglantisi bekleniyor.",
    }

    return await _service.process_validate_result(
        runner_result=runner_result,
        flow_file=request.flow_file,
    )


@router.post("/screenshot", response_model=ScreenshotResponse)
async def take_screenshot(request: TakeScreenshotRequest) -> ScreenshotResponse:
    """Mevcut simulator/emulator ekraninin screenshot'ini alir."""
    await logger.ainfo(
        "maestro_screenshot_request",
        platform=request.platform,
        project_slug=request.project_slug,
    )

    # Placeholder: Agent dispatch
    runner_result: dict[str, object] = {
        "success": False,
        "error": "Agent baglantisi bekleniyor.",
        "platform": request.platform.value,
    }

    return await _service.process_screenshot_result(
        runner_result=runner_result,
        platform=request.platform.value,
    )


@router.post("/list-flows", response_model=ListFlowsResponse)
async def list_flows(request: ListFlowsRequest) -> ListFlowsResponse:
    """Belirtilen dizindeki flow dosyalarini listeler."""
    await logger.ainfo(
        "maestro_list_flows_request",
        flows_dir=request.flows_dir,
    )

    # Placeholder: Agent dispatch
    runner_result: dict[str, object] = {
        "success": False,
        "error": "Agent baglantisi bekleniyor.",
        "flows_dir": request.flows_dir,
    }

    return await _service.process_list_flows_result(
        runner_result=runner_result,
    )


@router.post("/report", response_model=MaestroTestReport)
async def generate_report(request: RunSuiteRequest) -> MaestroTestReport:
    """Suite'i calistirir ve CI entegrasyonu icin detayli rapor olusturur.

    Screenshot bilgileri adim bazli raporlanir.
    """
    await logger.ainfo(
        "maestro_report_request",
        suite_name=request.suite_name,
        flow_count=len(request.flows),
    )

    # Once suite'i calistir
    suite_response = await run_suite(request)

    # Rapor olustur
    return await _service.generate_test_report(
        suite_response=suite_response,
    )
