# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Export the existing worker contract and resolved submission policies for manager.

Run with CONFIG_FILE/ENV_FILE used by KF. The export contains no credentials.
"""

import json

from knowledge_flow_backend.common.config_loader import load_configuration
from knowledge_flow_backend.features.scheduler.scheduler_structures import PipelineDefinition
from knowledge_flow_backend.features.scheduler.submission_policy import submission_policy


def export(config):
    return {
        "workflow": "ProcessPush",
        "schema": PipelineDefinition.model_json_schema(),
        "processor_profiles": {profile: config.processing.get_profile_config(profile).model_dump(mode="json") for profile in ("fast", "medium", "rich")},
        "profiles": {profile: submission_policy(config.processing, config.scheduler.temporal.task_queue, profile) for profile in ("fast", "medium", "rich")},
    }


if __name__ == "__main__":
    print(json.dumps(export(load_configuration()), indent=2))
