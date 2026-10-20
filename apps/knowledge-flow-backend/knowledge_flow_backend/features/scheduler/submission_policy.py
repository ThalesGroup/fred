# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
from knowledge_flow_backend.common.structures import ProcessingConfig, extraction_task_queue, parse_duration_seconds


def submission_policy(processing: ProcessingConfig, base_task_queue: str, profile) -> dict:
    """The existing FileToProcess orchestration fields, shared with external submitters."""
    normalized_profile = processing.normalize_profile(profile)
    profile_config = processing.get_profile_config(normalized_profile)
    return {
        # Resolved per document, so one submission may freely mix profiles:
        # only the extraction activity leaves the common queue.
        "extraction_task_queue": extraction_task_queue(base_task_queue, normalized_profile),
        "push_metadata_activity_timeout_seconds": parse_duration_seconds(profile_config.push_metadata_activity_timeout, field_name="push_metadata_activity_timeout"),
        "pull_metadata_activity_timeout_seconds": parse_duration_seconds(profile_config.pull_metadata_activity_timeout, field_name="pull_metadata_activity_timeout"),
        "output_activity_timeout_seconds": parse_duration_seconds(profile_config.output_activity_timeout, field_name="output_activity_timeout"),
        "input_activity_timeout_seconds": profile_config.input_activity_timeout_seconds,
        "heartbeat_timeout_seconds": profile_config.activity_heartbeat_timeout_seconds,
        "retry_initial_interval_seconds": profile_config.retry_initial_interval_seconds,
        "retry_backoff_coefficient": profile_config.retry_backoff_coefficient,
        "retry_maximum_interval_seconds": profile_config.retry_maximum_interval_seconds,
        "retry_maximum_attempts": profile_config.retry_maximum_attempts,
        "retry_non_retryable_error_types": list(profile_config.retry_non_retryable_error_types),
    }
