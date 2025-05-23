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

"""Module for File Data Access Object (DAO) to handle storage and retrieval of resources as files."""
import logging
import os
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Type, List, AnyStr, Any, TypeVar, Dict

from pydantic import BaseModel, ValidationError

from common.error import InvalidCacheError
from common.structure import WorkloadKind, DAOConfiguration

# 🔹 Create a module-level logger
logger = logging.getLogger(__name__)

class FileDAO:
    """
    Data Access Object (DAO) class for storing and retrieving resources as files.

    This class handles saving and loading of resources derived from `pydantic.BaseModel`
    to and from the file system. It constructs file paths dynamically based on the
    resource type and identifiers, supporting resources at various hierarchy levels
    (e.g., cluster, namespace, kind, workload).

    Attributes:
        base_dir (str): The base directory where all resource files are stored.
    """
    T = TypeVar('T', bound=BaseModel)

    def __init__(self, configuration: DAOConfiguration, subdir: str = ""):
        """
        Initializes the FileDAO with a base directory.

        Args:
            configuration (DAOConfiguration): The configuration of the DAO.
            subdir (str): An additional subdirectory to the base directory.
        """
        self.base_dir = os.path.expanduser(configuration.base_path + "/" + subdir)
        self.max_cached_delay_seconds = configuration.max_cached_delay_seconds
        self.cache_date: Dict[str, datetime] = dict()  # associate each bath to its date of writing
        logger.info(
            f"File DAO initialized with base directory '{self.base_dir}'"
        )
        if self.max_cached_delay_seconds < 0:
            logger.warning("Caching is unlimited; data will never expire once saved in the cache.")
        elif self.max_cached_delay_seconds == 0:
            logger.warning("Caching is disabled; data will always be retrieved from external sources.")
        else:
            logger.warning(f"Caching is enabled with a delay of {self.max_cached_delay_seconds} seconds. ")

    def _get_file_path(
            self,
            obj_class_name: str,
            cluster: str | None = None,
            namespace: str | None = None,
            kind: WorkloadKind | str | None = None,
            workload: str | None = None,
            **kwargs: Any
    ) -> AnyStr:
        """
        Constructs a resource-based path similar to a URL, organized by `cluster`, `namespace`, `kind`, and `workload`.
        The final filename is derived either from `obj`'s class name or the single key-value pair provided
        in `**kwargs`.

        Path structure:
          - `cluster/cluster_value/namespace/namespace_value/kind/kind_value/workload/workload_value/kwargs_key/kwargs_value.json`
            if `**kwargs` contains one key-value pair.
          - `cluster/cluster_value/namespace/namespace_value/kind/kind_value/workload/workload_value/<obj_class_name>.json`
            if `**kwargs` is empty.

        The path stops at the first `None` value encountered among `cluster`, `namespace`, `kind`, or `workload`.

        :param obj_class_name: The name of the object's class to be used as the default filename.
        :param cluster: Cluster name; path stops before this if `None`.
        :param namespace: Namespace name; the path stops before this if `None`.
        :param kind: Kind name; the path stops before this if `None`.
        :param workload: Workload name; the path stops before this if `None`.
        :param kwargs: A single optional key-value pair to define the final directory and filename.

        :return: The constructed resource path as a string.
        :raises ValueError: If more than one key-value pair is provided in `kwargs`.

        Examples:
            # With kwargs key-value pair
            path = save(obj_class_name=obj, cluster="clusterA", namespace="namespaceB", kind="kindX", workload="workloadC",
                        service="serviceX")
            # Result: "clusters/clusterA/namespaces/namespaceB/kinds/kindX/workloads/workloadC/service/serviceX.json"

            # Without kwargs
            path = save(obj_class_name=obj, cluster="clusterA", namespace="namespaceB", kind="kindX", workload="workloadC")
            # Result: "clusters/clusterA/namespaces/namespaceB/kinds/kindX/workloads/workloadC/obj.json"

            # Ends early when `workload` is None
            path = save(obj_class_name=obj, cluster="clusterA", namespace="namespaceB", kind="kindX")
            # Result: "clusters/clusterA/namespaces/namespaceB/kinds/kindX/obj.json"
        """
        # Ensure that **kwargs contains at most one key-value pair
        if len(kwargs) > 1:
            raise ValueError("Only one keyword argument (e.g., 'ingress', 'service', or 'facts') can be provided.")

        # Determine the filename and final part of the path
        if kwargs:
            _, value = next(iter(kwargs.items()))
            filename = f"{value}.json"
        else:
            filename = f"{obj_class_name}.json"

        # Construct the path as per hierarchy
        path_parts = [self.base_dir]

        # Append each component if it’s not None, stopping at the first None
        if cluster:
            path_parts.append(f"clusters/{cluster}")
        else:
            return os.path.join(*path_parts, filename)

        if namespace:
            path_parts.append(f"namespaces/{namespace}")
        else:
            return os.path.join(*path_parts, filename)

        if kind:
            path_parts.append(f"kinds/{kind}")
        else:
            return os.path.join(*path_parts, filename)

        if workload:
            path_parts.append(f"workloads/{workload}")
        else:
            return os.path.join(*path_parts, filename)

        # If kwargs is provided, add the key to the path
        if kwargs:
            key, _ = next(iter(kwargs.items()))
            path_parts.append(f"{key}/")

        # Join all parts and add the filename at the end
        return os.path.join(*path_parts, filename)

    def _is_cache_expired(self, file_path: str) -> bool:
        """
        Checks if the cache for a file is expired based on `self.max_cached_delay_seconds`.
        If `self.max_cached_delay_seconds` < 0, the function will always return False.

        Args:
            file_path (str): Path to the file.

        Returns:
            bool: True if cache expired; otherwise, False.
        """
        if self.max_cached_delay_seconds == 0:
            """ Cache is disabled """
            return True
        cache_time = self.cache_date.get(file_path)
        if not cache_time:
            return False

        elapsed_time = (datetime.now() - cache_time).total_seconds()
        return 0 <= self.max_cached_delay_seconds < elapsed_time

    def _remove_expired_cache_file(self, file_path: str) -> bool:
        """
        Removes a file if its cache delay has expired, and logs this action.

        Args:
            file_path (str): Path to the file to potentially delete.

        Returns:
            bool: True if cache expired and the file has been removed; otherwise, False.
        """
        if self.max_cached_delay_seconds == 0:
            """ Cache is disabled """
            return False
        if self._is_cache_expired(file_path):
            try:
                os.remove(file_path)
                logger.debug(f"Removed expired cache file '{file_path}'.")
                del self.cache_date[file_path]
                return True
            except Exception as e:
                logger.error(f"Error removing expired cache file '{file_path}': {e}")
        return False

    def saveCache(
            self,
            obj: T,
            cluster: str | None = None,
            namespace: str | None = None,
            kind: WorkloadKind | str | None = None,
            workload: str | None = None,
            **kwargs: Any
    ):
        """
        Saves the given object to a file based on the model class and identifiers and records its cache date.
        Use this method in conjunction with `loadCacheItem` to cache resources.

        :param obj: (BaseModel) The Pydantic model instance to save.
        :param cluster: (str) Cluster name.
        :param namespace: (str) Namespace.
        :param kind: (str) Kind name.
        :param workload: (str) Workload name.
        :param kwargs: A single optional key-value pair to define the final directory and filename.
        Like "ingresses", "summary" or "advanced".

        :raises ValueError: If more than one key-value pair is provided in `kwargs`.
        :raises IOError: If the file operation fails.
        """
        file_path = self._get_file_path(obj.__class__.__name__, cluster, namespace, kind, workload, **kwargs)
        os.makedirs(os.path.dirname(file_path), exist_ok=True)

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(obj.model_dump_json())
            self.cache_date[file_path] = datetime.now()  # Set cache time
            logger.debug(f"Saved object to '{file_path}' with updated cache time.")
        except IOError as e:
            raise IOError(f"Failed to save object to {file_path}: {e}") from e

    def save(
            self,
            obj: T,
            cluster: str | None = None,
            namespace: str | None = None,
            kind: WorkloadKind | str | None = None,
            workload: str | None = None,
            **kwargs: Any
    ):
        """
        Saves the given object to a file based on the model class and identifiers and records its cache date.
        Use this method in conjunction with `loadCacheItem` to cache resources.

        :param obj: (BaseModel) The Pydantic model instance to save.
        :param cluster: (str) Cluster name.
        :param namespace: (str) Namespace.
        :param kind: (str) Kind name.
        :param workload: (str) Workload name.
        :param kwargs: A single optional key-value pair to define the final directory and filename.
        Like "ingresses", "summary" or "advanced".

        :raises ValueError: If more than one key-value pair is provided in `kwargs`.
        :raises IOError: If the file operation fails.
        """
        file_path = self._get_file_path(obj.__class__.__name__, cluster, namespace, kind, workload, **kwargs)
        os.makedirs(os.path.dirname(file_path), exist_ok=True)

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(obj.model_dump_json())
            logger.debug(f"Saved object to '{file_path}'.")
        except IOError as e:
            raise IOError(f"Failed to save object to {file_path}: {e}") from e


    def loadCacheItem(
            self,
            model_class: Type[T],
            cluster: str | None = None,
            namespace: str | None = None,
            kind: WorkloadKind | str | None = None,
            workload: str | None = None,
            **kwargs: Any
    ) -> T:
        """
        Loads an object from a file, checking for cache expiration.

        :param model_class: (Type[T]): The Pydantic model class to load.
        :param cluster: (str) Cluster name.
        :param namespace: (str) Namespace.
        :param kind: (str) Kind name.
        :param workload: (str) Workload name.
        :param kwargs: A single optional key-value pair to define the final directory and filename.
        Like "ingresses", "summary" or "advanced".

        :return: (T) An instance of the loaded Pydantic model.
        """
        file_path = self._get_file_path(model_class.__name__, cluster, namespace, kind, workload, **kwargs)
        if self._remove_expired_cache_file(file_path):  # Check and remove the expired file if so
            raise InvalidCacheError(f"The cache has been invalided for file {file_path}")

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = f.read()
            return model_class.model_validate_json(data)
        except Exception as e:
            raise ValueError(f"Failed to load or parse object from {file_path}: {e}") from e

    def loadItem(
            self,
            model_class: Type[T],
            cluster: str | None = None,
            namespace: str | None = None,
            kind: WorkloadKind | str | None = None,
            workload: str | None = None,
            **kwargs: Any
    ) -> T:
        """
        Loads an object from a file. There is no cache logic here the item must exist.

        :param model_class: (Type[T]): The Pydantic model class to load.
        :param cluster: (str) Cluster name.
        :param namespace: (str) Namespace.
        :param kind: (str) Kind name.
        :param workload: (str) Workload name.
        :param kwargs: A single optional key-value pair to define the final directory and filename.
        Like "ingresses", "summary" or "advanced".

        :return: (T) An instance of the loaded Pydantic model.
        """
        file_path = self._get_file_path(model_class.__name__, cluster, namespace, kind, workload, **kwargs)
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = f.read()
            return model_class.model_validate_json(data)
        except Exception as e:
            raise ValueError(f"Failed to load or parse object from {file_path}: {e}") from e

    def list(
            self,
            model_class: Type[T],
            cluster: str | None = None,
            namespace: str | None = None,
            kind: WorkloadKind | str | None = None,
            workload: str | None = None,
            **kwargs: Any,
    ) -> List[T]:
        """
        Lists all instances of a model class, removing expired files along the way.

        :param model_class: (Type[T]): The Pydantic model class to load.
        :param cluster: (str) Cluster name.
        :param namespace: (str) Namespace.
        :param kind: (str) Kind name.
        :param workload: (str) Workload name.
        :param kwargs: A single optional key-value pair to define the final directory and filename.
        Like "ingresses", "summary" or "advanced".

        :return: (List[T]) A list of instances of the loaded Pydantic models.

        :raises IOError: If a file operation fails.
        :raises InvalidCacheError: If the cache of one or multiple files is invalid.
        """
        base_path = self._get_file_path(model_class.__name__, cluster, namespace, kind, workload, **kwargs)
        instances = []
        invalid_cache_path_list = []

        try:
            path = Path(os.path.dirname(base_path))
            for file_path in path.rglob('*.json'):
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = f.read()

                # Try to load the content as the given structures type that implements BaseModel
                try:
                    instance = model_class.model_validate_json(data)
                    if self._remove_expired_cache_file(str(file_path)):  # Remove expired files
                        invalid_cache_path_list.append(file_path)
                        continue
                except ValidationError:
                    logger.debug(
                        f"Skipping file '{file_path}' as it does not match model '{model_class.__name__}'.")
                    continue
                instances.append(instance)

            if len(invalid_cache_path_list) > 0:
                raise InvalidCacheError(f"The cache has been invalided for files: {invalid_cache_path_list}.")

        except IOError as e:
            raise IOError(f"Failed to read instances from path: {base_path}: {e}") from e

        return instances

    def delete[T](
            self,
            model_class: Type[T],
            cluster: str | None = None,
            namespace: str | None = None,
            kind: WorkloadKind | str | None = None,
            workload: str | None = None,
            **kwargs: Any
    ):
        """
        Deletes a specified file and its cache entry.

        :param model_class: (Type[T]): The Pydantic model class to load.
        :param cluster: (str) Cluster name.
        :param namespace: (str) Namespace.
        :param kind: (str) Kind name.
        :param workload: (str) Workload name.
        :param kwargs: A single optional key-value pair to define the final directory and filename.
        Like "ingresses", "summary" or "advanced".

        :raises OSError: In the case of the internal built path does not point to a file (e.g., a directory).
        :raises FileNotFoundError: In the case of the internal built path does not point to an existing file.
        """
        file_path = self._get_file_path(model_class.__name__, cluster, namespace, kind, workload, **kwargs)
        os.remove(file_path)
        self.cache_date.pop(file_path, None)  # Remove cache entry if exists
        logger.info(f"Deleted file and cache entry for '{file_path}'.")

    def exists[T](
            self,
            model_class: Type[T],
            cluster: str | None = None,
            namespace: str | None = None,
            kind: WorkloadKind | str | None = None,
            workload: str | None = None,
            **kwargs: Any
    ) -> bool:
        """
        Checks if a file exists, removing it if the cache delay is expired.

        :param model_class: (Type[T]): The Pydantic model class to load.
        :param cluster: (str) Cluster name.
        :param namespace: (str) Namespace.
        :param kind: (str) Kind name.
        :param workload: (str) Workload name.
        :param kwargs: A single optional key-value pair to define the final directory and filename.
        Like "ingresses", "summary" or "advanced".

        :return: True if the file exists and its cache is valid; False otherwise.

        :raises FileNotFoundError: If the resource does not exist.
        """
        file_path = self._get_file_path(model_class.__name__, cluster, namespace, kind, workload, **kwargs)
        expired = self._remove_expired_cache_file(file_path)  # Check for cache expiration
        return not expired and os.path.exists(file_path)

    def export_all(self, destination_directory: str):
        """
        Export the base directory and its contents to a ZIP file and return the archive name.
        """
        directory_to_archive_path = Path(self.base_dir)
        current_date = datetime.now().strftime("%Y-%m-%d")
        zip_filename = f"{destination_directory}/export-{current_date}.zip"
        logger.debug(f"Exporting files to {zip_filename}")

        with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            # Walk through the directory
            for file_path in directory_to_archive_path.rglob('*'):
                # Add the file to the ZIP, using its relative path
                zip_file.write(file_path, file_path.relative_to(directory_to_archive_path))

        logger.info(f"Successfully exported files of {directory_to_archive_path} to {zip_filename}")
        return zip_filename

    def import_all(self, zip_path: str):
        """
        Import a ZIP file and extract its contents to the base directory
        """
        extract_path = Path(self.base_dir)
        extract_path.mkdir(parents=True, exist_ok=True)  # Create directory if it doesn't exist

        with zipfile.ZipFile(zip_path, 'r') as zip_file:
            zip_file.extractall(extract_path)

        logger.info(f"Successfully imported files from {zip_path} in {self.base_dir}")
