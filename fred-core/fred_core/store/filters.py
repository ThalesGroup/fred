# pyright: strict
from datetime import datetime
from typing import Any, Dict, Optional, Type, Union, get_args, get_origin
from pydantic import BaseModel, Field, create_model


FilterOpInfo = dict[Type[Any] | str, dict[str, Any]]

filter_ops_by_type: FilterOpInfo = {
    str: {
        "eq": {"description": "Exact match"},
        "icontains": {"description": "Case-insensitive substring match"},
        "in": {"description": "Value is one of the provided values"},
    },
    int: {
        "eq": {"description": "Exact match"},
        "lt": {"description": "Less than"},
        "lte": {"description": "Less than or equal"},
        "gt": {"description": "Greater than"},
        "gte": {"description": "Greater than or equal"},
        "in": {"description": "Value is one of the provided values"},
    },
    float: {
        "eq": {"description": "Exact match"},
        "lt": {"description": "Less than"},
        "lte": {"description": "Less than or equal"},
        "gt": {"description": "Greater than"},
        "gte": {"description": "Greater than or equal"},
        "in": {"description": "Value is one of the provided values"},
    },
    bool: {
        "eq": {"description": "Exact match"},
    },
    datetime: {
        "eq": {"description": "Exact match"},
        "lt": {"description": "Before this date"},
        "lte": {"description": "On or before this date"},
        "gt": {"description": "After this date"},
        "gte": {"description": "On or after this date"},
    },
    "list[str]": {
        "contains": {"description": "Check if value is present in list field"},
        "overlap": {"description": "Match if any values overlap with field list"},
    },
    "list[int]": {
        "contains": {"description": "Check if value is present in list field"},
        "overlap": {"description": "Match if any values overlap with field list"},
    },
}


def resolve_type(t: Type[Any]) -> Type[Any] | str:
    """
    Resolve a type annotation to its base type for filter operation mapping.

    Handles:
    - Optional[T] -> T
    - Union[T, None] -> T
    - T | None -> T (Python 3.10+)
    - list[T] -> "list[T]"
    - Regular types -> T
    """
    origin = get_origin(t)
    args = get_args(t)

    # Handle Union types (includes Optional which is Union[T, None])
    if origin is Union:
        # Filter out None/NoneType and get the actual type
        non_none_args = [arg for arg in args if arg is not type(None)]
        if len(non_none_args) == 1:
            # This is Optional[T] or T | None - recursively resolve the inner type
            return resolve_type(non_none_args[0])
        elif len(non_none_args) > 1:
            # This is a true Union of multiple non-None types
            # For now, we'll take the first non-None type
            # In the future, we could support multiple type operations
            return resolve_type(non_none_args[0])

    # Handle list types
    if origin is list:
        inner = args[0] if args else Any
        if hasattr(inner, "__name__"):
            return f"list[{inner.__name__}]"
        else:
            # Handle complex inner types
            resolved_inner = resolve_type(inner)
            if isinstance(resolved_inner, str):
                return f"list[{resolved_inner}]"
            else:
                return f"list[{resolved_inner.__name__}]"

    return t


class BaseFilter(BaseModel):
    """Base class for all generated filter models.

    This provides a common type that static type checkers can understand,
    while allowing dynamic field generation at runtime.
    """

    def to_dict(self) -> Dict[str, Any]:
        """Convert filter to dict, excluding None values."""
        return {k: v for k, v in self.model_dump().items() if v is not None}


def generate_filter_model(
    base_model: Type[BaseModel], name: str = "FilterModel"
) -> Type[BaseFilter]:
    """
    Generate a Pydantic filter model based on another model's fields.

    Creates dynamic filter fields like field_name_eq, field_name_icontains, etc.
    based on the field types in the base model.

    Returns:
        A class that inherits from BaseFilter, providing type safety for static analysis.
    """
    fields = {}
    base_annotations = base_model.__annotations__

    for field_name, field_type in base_annotations.items():
        resolved_type = resolve_type(field_type)
        op_map = filter_ops_by_type.get(resolved_type) or filter_ops_by_type.get(
            field_type
        )

        if not op_map:
            continue

        # For filter fields, we want to use the inner type (not the Optional wrapper)
        # The filter fields themselves will always be Optional in the generated model
        inner_type = resolved_type if not isinstance(resolved_type, str) else field_type

        # Extract inner type from Optional/Union for better type annotation
        if get_origin(field_type) is Union:
            non_none_args = [
                arg for arg in get_args(field_type) if arg is not type(None)
            ]
            if non_none_args:
                inner_type = non_none_args[0]

        for op, meta in op_map.items():
            description = meta.get("description", "")
            filter_field_name = f"{field_name}__{op}" if op != "eq" else field_name
            fields[filter_field_name] = (
                Optional[inner_type],
                Field(default=None, description=description),
            )

    # Create the model inheriting from BaseFilter
    return create_model(name, __base__=BaseFilter, **fields)


# Usage:
# DocumentFilter = generate_filter_model(DocumentMetadata, name="DocumentFilter")
