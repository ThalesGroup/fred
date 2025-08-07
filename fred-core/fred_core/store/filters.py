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


def extract_non_none_type(t: Type[Any]) -> Type[Any]:
    """
    Extract the non-None type from Optional/Union types.
    
    Args:
        t: Type annotation that may be Optional[T], Union[T, None], or T | None
        
    Returns:
        The inner non-None type, or the original type if not Optional/Union
    """
    origin = get_origin(t)
    args = get_args(t)

    # Handle Union types (includes Optional which is Union[T, None])
    if origin is Union:
        non_none_args = [arg for arg in args if arg is not type(None)]
        if len(non_none_args) == 1:
            # This is Optional[T] or T | None - recursively extract the inner type
            return extract_non_none_type(non_none_args[0])
        elif len(non_none_args) > 1:
            # This is a true Union of multiple non-None types
            # Take the first non-None type
            return extract_non_none_type(non_none_args[0])

    return t


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
    # First extract the non-None type
    inner_type = extract_non_none_type(t)
    origin = get_origin(inner_type)
    args = get_args(inner_type)

    # Handle list types
    if origin is list:
        list_inner = args[0] if args else Any
        if hasattr(list_inner, "__name__"):
            return f"list[{list_inner.__name__}]"
        else:
            # Handle complex inner types
            resolved_inner = resolve_type(list_inner)
            if isinstance(resolved_inner, str):
                return f"list[{resolved_inner}]"
            else:
                return f"list[{resolved_inner.__name__}]"

    return inner_type


def get_filter_field_type(field_type: Type[Any], resolved_type: Type[Any] | str, operation: str) -> Type[Any]:
    """
    Determine the appropriate type for a filter field based on the original field type and operation.
    
    Args:
        field_type: Original field type annotation
        resolved_type: Resolved type from resolve_type()
        operation: Filter operation (eq, contains, overlap, etc.)
        
    Returns:
        The type that should be used for the filter field
    """
    # Extract the non-None inner type for the base field type
    base_inner_type = extract_non_none_type(field_type)
    
    # For list operations, we need special handling
    if isinstance(resolved_type, str) and resolved_type.startswith("list["):
        list_origin = get_origin(base_inner_type)
        list_args = get_args(base_inner_type)
        
        if list_origin is list and list_args:
            if operation == "contains":
                # For list contains, expect a single element of the list's inner type
                return list_args[0]  # e.g., str from List[str]
            elif operation == "overlap":
                # For list overlap, expect a list of the same inner type  
                return base_inner_type  # e.g., List[str]
    
    # For non-list operations, use the base inner type
    return base_inner_type


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
            
            # Determine the correct type for this specific operation
            filter_field_type = get_filter_field_type(field_type, resolved_type, op)
            
            fields[filter_field_name] = (
                Optional[filter_field_type],
                Field(default=None, description=description),
            )

    # Create the model inheriting from BaseFilter
    return create_model(name, __base__=BaseFilter, **fields)


# Usage:
# DocumentFilter = generate_filter_model(DocumentMetadata, name="DocumentFilter")
