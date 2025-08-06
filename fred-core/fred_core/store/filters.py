# pyright: strict
from datetime import datetime
from typing import Any, Dict, Optional, Type, get_args, get_origin
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
    origin = get_origin(t)
    args = get_args(t)
    if origin is list:
        inner = args[0] if args else Any
        return f"list[{inner.__name__}]"
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

        for op, meta in op_map.items():
            description = meta.get("description", "")
            filter_field_name = f"{field_name}__{op}" if op != "eq" else field_name
            fields[filter_field_name] = (
                Optional[field_type],
                Field(default=None, description=description),
            )

    # Create the model inheriting from BaseFilter
    return create_model(name, __base__=BaseFilter, **fields)


# Usage:
# DocumentFilter = generate_filter_model(DocumentMetadata, name="DocumentFilter")
# Now you can use DocumentFilter directly in type annotations!
