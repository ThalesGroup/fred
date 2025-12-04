# Copyright Thales 2025
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class MappingValidationError(Exception):
    """Exception raised when OpenSearch index mapping validation fails."""

    pass


def validate_index_mapping(
    client,  # OpenSearch client instance (avoiding circular import)
    index_name: str,
    expected_mapping: Dict[str, Any],
    strict: bool = True,
    allow_missing_fields: bool = False,
) -> None:
    """
    Validate that an existing OpenSearch index has the expected field mappings.

    Args:
        client: OpenSearch client instance
        index_name: Name of the index to validate
        expected_mapping: Expected mapping structure (with "mappings" key)
        strict: If True, raises exception on critical mismatches. If False, only logs warnings.
        allow_missing_fields: If True, missing fields only generate warnings. If False, they are errors.

    Raises:
        MappingValidationError: When critical mapping mismatches are found
    """
    try:
        # Get current mapping from OpenSearch
        current_mapping_resp = client.indices.get_mapping(index=index_name)
        current_mapping = current_mapping_resp.get(index_name, {}).get("mappings", {})

        # Extract expected properties
        expected_properties = expected_mapping.get("mappings", {}).get("properties", {})
        current_properties = current_mapping.get("properties", {})

        # Validate field mappings
        mismatches: List[str] = []

        for field_name, expected_config in expected_properties.items():
            if field_name not in current_properties:
                error_msg = f"Missing root field: '{field_name}'"
                if allow_missing_fields:
                    logger.warning(f"[OPENSEARCH][MAPPING] {error_msg}")
                else:
                    mismatches.append(error_msg)
                continue

            current_config = current_properties[field_name]
            field_mismatches = _validate_field_mapping(
                field_name, expected_config, current_config
            )
            mismatches.extend(field_mismatches)

        # Log and handle validation results
        if mismatches:
            error_msg = (
                f"Index '{index_name}' has mapping validation errors: {mismatches}"
            )
            logger.error(f"[OPENSEARCH][MAPPING] {error_msg}")

            if strict:
                raise MappingValidationError(error_msg)
        else:
            logger.info(
                f"[OPENSEARCH][MAPPING] Index '{index_name}' mapping validation passed"
            )

    except Exception as e:
        if isinstance(e, MappingValidationError):
            raise
        logger.error(
            f"[MAPPING] Failed to validate mapping for index '{index_name}': {e}"
        )
        if strict:
            raise MappingValidationError(
                f"Mapping validation failed for index '{index_name}': {e}"
            ) from e


def _get_field_type(field_config: Dict[str, Any]) -> str | None:
    """
    Get the effective field type, handling OpenSearch's implicit object type.

    In OpenSearch:
    - If 'type' is specified, use it
    - If 'type' is None but 'properties' or 'dynamic' exist, it's implicitly an 'object'
    - Otherwise return None
    """
    explicit_type = field_config.get("type")
    if explicit_type is not None:
        return explicit_type

    # Check for implicit object indicators
    if "properties" in field_config or "dynamic" in field_config:
        return "object"

    return None


def _validate_field_mapping(
    field_path: str, expected: Dict[str, Any], current: Dict[str, Any]
) -> List[str]:
    """
    Validate a single field mapping recursively.

    Args:
        field_path: Dot-notation path to the field being validated
        expected: Expected field configuration
        current: Current field configuration from OpenSearch

    Returns:
        List of mismatch descriptions
    """
    mismatches: List[str] = []

    # Check field type (handle implicit object types)
    expected_type = _get_field_type(expected)
    current_type = _get_field_type(current)

    if expected_type != current_type:
        mismatches.append(
            f"'{field_path}': expected type '{expected_type}', got '{current_type}'"
        )

    # Check properties (for object/nested types)
    expected_has_props = "properties" in expected
    current_has_props = "properties" in current
    expected_is_dynamic = expected.get("dynamic") is True

    if expected_has_props and not current_has_props:
        mismatches.append(
            f"'{field_path}': expected object type with properties, but current field has no properties"
        )
    elif not expected_has_props and current_has_props and not expected_is_dynamic:
        # Only error if current has properties but expected doesn't AND expected is not dynamic
        mismatches.append(
            f"'{field_path}': expected primitive type, but current field has object properties"
        )
    elif expected_has_props and current_has_props:
        # Both have properties, validate nested fields
        expected_props = expected["properties"]
        current_props = current["properties"]

        for nested_field, nested_expected in expected_props.items():
            nested_path = f"{field_path}.{nested_field}"
            if nested_field in current_props:
                nested_current = current_props[nested_field]
                nested_mismatches = _validate_field_mapping(
                    nested_path, nested_expected, nested_current
                )
                mismatches.extend(nested_mismatches)
            else:
                mismatches.append(f"Missing nested field: '{nested_path}'")

    # Check multi-field configurations (e.g., text with keyword subfield)
    expected_has_fields = "fields" in expected
    current_has_fields = "fields" in current

    if expected_has_fields and not current_has_fields:
        mismatches.append(
            f"'{field_path}': expected multi-field configuration, but current field has no subfields"
        )
    elif not expected_has_fields and current_has_fields:
        mismatches.append(
            f"'{field_path}': expected simple field, but current field has multi-field configuration"
        )
    elif expected_has_fields and current_has_fields:
        # Both have fields, validate subfields
        expected_fields = expected["fields"]
        current_fields = current["fields"]

        for subfield_name, subfield_expected in expected_fields.items():
            subfield_path = f"{field_path}.{subfield_name}"
            if subfield_name in current_fields:
                subfield_current = current_fields[subfield_name]
                subfield_mismatches = _validate_field_mapping(
                    subfield_path, subfield_expected, subfield_current
                )
                mismatches.extend(subfield_mismatches)
            else:
                mismatches.append(f"Missing subfield: '{subfield_path}'")

    return mismatches
