from knowledge_flow_backend.common.structures import TemporalSchedulerConfig


def test_temporal_scheduler_config_queue_fallbacks():
    cfg = TemporalSchedulerConfig(task_queue="ingestion")

    assert cfg.get_workflow_task_queue() == "ingestion"
    assert cfg.get_io_task_queue() == "ingestion"
    assert cfg.get_cpu_task_queue() == "ingestion"
    assert cfg.worker_role == "all"


def test_temporal_scheduler_config_queue_overrides():
    cfg = TemporalSchedulerConfig(
        task_queue="ingestion",
        workflow_task_queue="ingestion-workflow",
        io_task_queue="ingestion-io",
        cpu_task_queue="ingestion-cpu",
        worker_role="cpu",
    )

    assert cfg.get_workflow_task_queue() == "ingestion-workflow"
    assert cfg.get_io_task_queue() == "ingestion-io"
    assert cfg.get_cpu_task_queue() == "ingestion-cpu"
    assert cfg.worker_role == "cpu"
