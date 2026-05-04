from knowledge_flow_backend.common.structures import Configuration


def test_configuration_migrates_legacy_ingestion_workers_to_scheduler_temporal(app_context) -> None:
    """
    Ensure legacy app-level ingestion concurrency still maps to scheduler.temporal.

    Why:
        Existing deployments can still provide `app.max_ingestion_workers` during rollout.
    How:
        Instantiate Configuration with the legacy field and verify all three
        scheduler.temporal ingestion knobs inherit that value.
    """
    payload = app_context.configuration.model_dump(mode="python")
    payload["app"]["max_ingestion_workers"] = 5
    payload["scheduler"]["temporal"].pop("ingestion_workflow_parallelism", None)
    payload["scheduler"]["temporal"].pop("ingestion_max_concurrent_workflow_tasks", None)
    payload["scheduler"]["temporal"].pop("ingestion_max_concurrent_activities", None)
    config = Configuration.model_validate(payload)

    assert config.scheduler.temporal.ingestion_workflow_parallelism == 5
    assert config.scheduler.temporal.ingestion_max_concurrent_workflow_tasks == 5
    assert config.scheduler.temporal.ingestion_max_concurrent_activities == 5


def test_configuration_keeps_explicit_scheduler_values_when_legacy_app_values_exist(app_context) -> None:
    """
    Ensure explicit scheduler.temporal values override legacy app fallback.

    Why:
        Gradual migration should allow teams to set the new scheduler.temporal
        knobs while old app-level values are still present.
    How:
        Provide `app.max_ingestion_workers` and explicit scheduler.temporal
        values, then verify scheduler.temporal values are preserved.
    """
    payload = app_context.configuration.model_dump(mode="python")
    payload["app"]["max_ingestion_workers"] = 5
    payload["scheduler"]["temporal"]["ingestion_workflow_parallelism"] = 2
    payload["scheduler"]["temporal"]["ingestion_max_concurrent_workflow_tasks"] = 3
    payload["scheduler"]["temporal"]["ingestion_max_concurrent_activities"] = 4
    config = Configuration.model_validate(payload)

    assert config.scheduler.temporal.ingestion_workflow_parallelism == 2
    assert config.scheduler.temporal.ingestion_max_concurrent_workflow_tasks == 3
    assert config.scheduler.temporal.ingestion_max_concurrent_activities == 4


def test_configuration_normalizes_profile_retry_policy(app_context) -> None:
    """
    Ensure processing profile retry policy accepts compact operator-friendly values.

    Why:
        Production deployments should be able to tune ingestion retries from YAML
        without duplicating Temporal-specific parsing rules in each backend.
    How:
        Override one processing profile retry block in the config payload and
        validate the normalized values exposed by the profile model.
    """
    payload = app_context.configuration.model_dump(mode="python")
    payload["processing"]["profiles"]["medium"]["retry_initial_interval"] = "20s"
    payload["processing"]["profiles"]["medium"]["retry_maximum_interval"] = "5m"
    payload["processing"]["profiles"]["medium"]["retry_maximum_attempts"] = 8

    config = Configuration.model_validate(payload)

    medium = config.processing.profiles.medium
    assert medium.retry_initial_interval == "20s"
    assert medium.retry_maximum_interval == "5m"
    assert medium.retry_initial_interval_seconds == 20
    assert medium.retry_maximum_interval_seconds == 300
    assert medium.retry_maximum_attempts == 8
