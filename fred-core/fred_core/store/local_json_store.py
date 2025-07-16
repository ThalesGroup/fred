from pathlib import Path
from typing import Callable, Generic, List, TypeVar

from pydantic import BaseModel, TypeAdapter


class BaseModelWithId(BaseModel):
    id: str


T = TypeVar("T", bound=BaseModelWithId)


class ResourceNotFoundError(Exception):
    """Raised when a resource is not found in the store."""

    pass


class ResourceAlreadyExistsError(Exception):
    """Raised when a resource already exists in the store."""

    pass


class LocalJsonStore(Generic[T]):
    # class LocalJsonStore:
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
        self.modelListAdapter = TypeAdapter(list[model])

        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("[]")

    def _load(self) -> list[T]:
        if not self.path.exists():
            return []
        return self.modelListAdapter.validate_json(self.path.read_text())

    def _save(self, data: list[T]) -> None:
        self.path.write_bytes(self.modelListAdapter.dump_json(data))

    def list(self, filter_fn: Callable[[T], bool] = lambda x: True) -> List[T]:
        return [item for item in self._load() if filter_fn(item)]

    def get_by_id(self, resource_id: str) -> T:
        for item in self._load():
            if item.id == resource_id:
                return item
        raise ResourceNotFoundError(
            f"No resource found with {self.id_field}={resource_id}"
        )

    def create(self, resource: T) -> T:
        data = self._load()
        for item in data:
            if item.id == resource.id:
                raise ResourceAlreadyExistsError(
                    f"Resource with {self.id_field}={resource.id} already exists"
                )
        data.append(resource)
        self._save(data)
        return resource

    def update(self, resource_id: str, resource: T) -> T:
        data = self._load()
        for i, item in enumerate(data):
            if item.id == resource_id:
                resource.id = resource_id
                data[i] = resource
                self._save(data)
                return resource
        raise ResourceNotFoundError(
            f"No resource found with {self.id_field}={resource_id}"
        )

    def delete(self, resource_id: str) -> None:
        data = self._load()
        original_len = len(data)
        data_without_resource_to_delete = [
            item for item in data if not (item.id == resource_id)
        ]
        if len(data_without_resource_to_delete) == original_len:
            raise ResourceNotFoundError(
                f"No resource found with {self.id_field}={resource_id}"
            )
        self._save(data_without_resource_to_delete)
