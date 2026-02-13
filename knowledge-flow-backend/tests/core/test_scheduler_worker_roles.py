from knowledge_flow_backend.common.structures import TemporalSchedulerConfig
from knowledge_flow_backend.features.scheduler.worker import _role_specs


def test_worker_role_specs_all_with_distinct_queues():
    config = TemporalSchedulerConfig(
        task_queue="ingestion",
        workflow_task_queue="ingestion-workflow",
        io_task_queue="ingestion-io",
        cpu_task_queue="ingestion-cpu",
        worker_role="all",
    )

    specs = _role_specs(config)
    assert len(specs) == 3
    queues = {spec.task_queue for spec in specs}
    assert queues == {"ingestion-workflow", "ingestion-io", "ingestion-cpu"}


def test_worker_role_specs_all_merges_when_queues_identical():
    config = TemporalSchedulerConfig(
        task_queue="ingestion",
        worker_role="all",
    )

    specs = _role_specs(config)
    assert len(specs) == 1
    assert specs[0].task_queue == "ingestion"
    assert len(specs[0].workflows) >= 2
    assert len(specs[0].activities) >= 2


def test_worker_role_specs_single_role():
    config = TemporalSchedulerConfig(
        task_queue="ingestion",
        workflow_task_queue="ingestion-workflow",
        io_task_queue="ingestion-io",
        cpu_task_queue="ingestion-cpu",
        worker_role="io",
    )

    specs = _role_specs(config)
    assert len(specs) == 1
    assert specs[0].task_queue == "ingestion-io"
