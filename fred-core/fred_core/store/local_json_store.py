import json
from pathlib import Path
from typing import TypeVar, Generic, List, Callable, Any
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class ResourceNotFoundError(Exception):
    """Raised when a resource is not found in the store."""

    pass


class ResourceAlreadyExistsError(Exception):
    """Raised when a resource already exists in the store."""

    pass


class LocalJsonStore(Generic[T]):
    """
    Generic file-based store for resources marshable to JSON (e.g., Pydantic models).
    Handles CRUD operations for any resource type, using a specified id field.

    Warning: This implementation can't be used with multiple threads or processes.
    """

    def __init__(
        self,
        json_path: Path,
        model: type[T],
        id_field: str = "id",
    ):
        self.path = json_path
        self.id_field = id_field
        self.model = model
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("[]")

    def _load(self) -> List[dict]:
        if not self.path.exists():
            return []
        return json.loads(self.path.read_text())

    def _save(self, data: List[dict]) -> None:
        self.path.write_text(json.dumps(data, indent=2))

    def list(self, filter_fn: Callable[[T], bool] = lambda x: True) -> List[T]:
        return [
            self.model(**item) for item in self._load() if filter_fn(self.model(**item))
        ]

    def get_by_id(self, resource_id: Any) -> T:
        for item in self._load():
            if item.get(self.id_field) == resource_id:
                return self.model(**item)
        raise ResourceNotFoundError(
            f"No resource found with {self.id_field}={resource_id}"
        )

    def create(self, resource: T) -> T:
        data = self._load()
        resource_dict = resource.model_dump()
        for item in data:
            if item.get(self.id_field) == resource_dict[self.id_field]:
                raise ResourceAlreadyExistsError(
                    f"Resource with {self.id_field}={resource_dict[self.id_field]} already exists"
                )
        data.append(resource_dict)
        self._save(data)
        return self.model(**resource_dict)

    def update(self, resource_id: Any, resource: T) -> T:
        data = self._load()
        for i, item in enumerate(data):
            if item.get(self.id_field) == resource_id:
                resource_dict = resource.model_dump()
                data[i] = resource_dict
                self._save(data)
                return self.model(**resource_dict)
        raise ResourceNotFoundError(
            f"No resource found with {self.id_field}={resource_id}"
        )

    def delete(self, resource_id: Any) -> None:
        data = self._load()
        original_len = len(data)
        data_without_resource_to_delete = [
            item for item in data if not (item.get(self.id_field) == resource_id)
        ]
        if len(data_without_resource_to_delete) == original_len:
            raise ResourceNotFoundError(
                f"No resource found with {self.id_field}={resource_id}"
            )
        self._save(data_without_resource_to_delete)
