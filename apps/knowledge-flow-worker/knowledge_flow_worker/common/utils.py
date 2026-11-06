# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
import sys
from typing import Dict

import yaml

from knowledge_flow_worker.common.structures import Configuration


def parse_server_configuration(configuration_path: str) -> Configuration:
    """
    Parses the server configuration from a YAML file.

    Args:
        configuration_path (str): The path to the configuration YAML file.

    Returns:
        Configuration: The parsed configuration object.
    """
    with open(configuration_path, "r") as f:
        try:
            config: Dict = yaml.safe_load(f)
        except yaml.YAMLError:
            # The YAML error quotes the file, which can hold secrets.
            sys.exit(f"Invalid YAML in configuration file {configuration_path}")
    return Configuration(**config)
