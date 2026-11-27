"""领域服务注册表：通用资源路由按模块 key 分派到独立业务服务。"""
from __future__ import annotations

from app.services.base import BaseModuleService
from app.services.event_stream import EventStreamService
from app.services.exp_design import ExpDesignService
from app.services.variant_assign import VariantAssignService
from app.services.metric_catalog import MetricCatalogService
from app.services.metric_compute import MetricComputeService
from app.services.significance_test import SignificanceTestService
from app.services.attr_analysis import AttrAnalysisService
from app.services.cohort_builder import CohortBuilderService
from app.services.report_gen import ReportGenService
from app.services.report_dist import ReportDistService
from app.services.window_scheduler import WindowSchedulerService
from app.services.data_freshness import DataFreshnessService
from app.services.anomaly_metric import AnomalyMetricService
from app.services.anomaly_case import AnomalyCaseService
from app.services.anomaly_source import AnomalySourceService
from app.services.anomaly_investigation import AnomalyInvestigationService
from app.services.risk_action import RiskActionService
from app.services.exp_archive import ExpArchiveService
from app.services.sample_ratio import SampleRatioService
from app.services.aa_check import AaCheckService
from app.services.segment_slice import SegmentSliceService
from app.services.exposure_log import ExposureLogService
from app.services.conclusion_review import ConclusionReviewService
from app.services.metric_api import MetricApiService

SERVICES: dict[str, BaseModuleService] = {
    "event_stream": EventStreamService(),
    "exp_design": ExpDesignService(),
    "variant_assign": VariantAssignService(),
    "metric_catalog": MetricCatalogService(),
    "metric_compute": MetricComputeService(),
    "significance_test": SignificanceTestService(),
    "attr_analysis": AttrAnalysisService(),
    "cohort_builder": CohortBuilderService(),
    "report_gen": ReportGenService(),
    "report_dist": ReportDistService(),
    "window_scheduler": WindowSchedulerService(),
    "data_freshness": DataFreshnessService(),
    "anomaly_metric": AnomalyMetricService(),
    "anomaly_case": AnomalyCaseService(),
    "anomaly_source": AnomalySourceService(),
    "anomaly_investigation": AnomalyInvestigationService(),
    "risk_action": RiskActionService(),
    "exp_archive": ExpArchiveService(),
    "sample_ratio": SampleRatioService(),
    "aa_check": AaCheckService(),
    "segment_slice": SegmentSliceService(),
    "exposure_log": ExposureLogService(),
    "conclusion_review": ConclusionReviewService(),
    "metric_api": MetricApiService(),
}


def service_for(module: str) -> BaseModuleService | None:
    return SERVICES.get(module)
