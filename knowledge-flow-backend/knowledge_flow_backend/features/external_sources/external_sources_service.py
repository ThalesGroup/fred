#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Fsspec-based synchronization & ingestion service.

This module implements a complete, connector-agnostic ingestion pipeline that works
with any fsspec-compatible filesystem connector.

It provides a fully automated “remote → Fred” synchronization workflow including:

1. Remote File Discovery
   - Recursive listing of all files exposed by the connector
   - Parallel traversal of nested directories (async + thread pool)
   - Extraction of normalized logical paths (folder hierarchy + filename)

2. Change Detection (Sync Plan)
   - Comparison between the remote index and Fred’s metadata_v2 index
   - Classification into: new files, updated files, unchanged files, deleted files
   - Timestamp comparison using remote “modified” metadata (fallback: size checks)

3. Download & Local Processing
   - Download of remote files using the connector’s `download_file()`
   - Automatic filename normalization (force `.XLSM` when missing)
   - Safe reconstruction of folder/tag hierarchy using custom separators (“//”)
   - Automatic creation or reuse of semantic DOCUMENT tags

4. Fred Ingestion Pipeline
   - Metadata extraction (identity, extension, tags, source_tag)
   - Temporal activities executed in worker threads (input_process + output_process)
   - Storage of remote modification timestamps inside metadata.extensions

5. Deletion Propagation
   - Detection of files removed from the remote connector
   - Automatic cleanup in Fred via `MetadataService.remove_tag_id_from_document()`
   - Full document deletion when last tag is removed (including vector store + SQL table)

The class `FsspecFileIngestion` is responsible for orchestrating the whole workflow:
remote listing → sync plan → download → tagging → ingestion → deletion.

All connector-specific parameters (top_id, separator, authentication, etc.)
are provided by configuration.yaml via `FsspecPullSource`.
"""

from datetime import datetime
import logging
from pathlib import Path
import asyncio
import shutil
import tempfile
from typing import Any, Optional, TypedDict, Set, Dict, List

from fred_core import NO_AUTHZ_CHECK_USER
from fsspec import AbstractFileSystem

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.common.document_structures import DocumentMetadata
from knowledge_flow_backend.common.structures import FsspecPullSource
from knowledge_flow_backend.features.ingestion.ingestion_service import IngestionService
from knowledge_flow_backend.features.scheduler.scheduler_structures import FileToProcess
from knowledge_flow_backend.features.tag.tag_service import TagService
from knowledge_flow_backend.features.tag.structure import Tag, TagCreate, TagType
from knowledge_flow_backend.features.scheduler.activities import input_process, output_process, prepare_working_dir
from knowledge_flow_backend.features.metadata.service import MetadataService



logger = logging.getLogger(__name__)

def get_latest_working_dir(document_uid: str) -> Path:
    """
    Return the most recent /tmp/doc-<uid>-*/ directory.
    This avoids using the wrong working_dir if multiple were created.
    """
    tmp = Path(tempfile.gettempdir())
    prefix = f"doc-{document_uid}-"

    candidates = [p for p in tmp.iterdir()
                  if p.is_dir() and p.name.startswith(prefix)]

    if not candidates:
        raise FileNotFoundError(
            f"No working directory found for document_uid={document_uid}"
        )

    # Sort by creation time DESC
    candidates.sort(key=lambda p: p.stat().st_ctime, reverse=True)

    return candidates[0]


# -------------------------------------------------------------------
# Helper function
# -------------------------------------------------------------------
def _basename_generic(remote_path: str, separator: str) -> str:
    """
    Extract the filename from a connector path using the configured separator.

    Parameters
    ----------
    remote_path : str
        Full connector path (e.g., "external_source://FolderA // Subfolder // File.xlsm").
    separator : str
        Separator used in this connector (defined in configuration.yaml).

    Returns
    -------
    str
        The filename (last segment of the path).
    """
    # Remove protocol prefix if any
    path = remote_path.split("://", 1)[-1]

    # Split according to the configured separator
    parts = [p.strip() for p in path.split(separator) if p.strip()]
    return parts[-1] if parts else path

# -------------------------------------------------------------------
# Helper function
# -------------------------------------------------------------------
def _sanitize_folder_name(folder_name: str, separator: str, replacement_char: str = "-") -> str:
    """
    Sanitize a folder path before tag creation to prevent invalid hierarchies.

    This function ensures that folder paths coming from connectors using
    custom separators (e.g. `"//"`) remain compatible with FRED’s internal
    tag model, which interprets `'/'` as a hierarchy delimiter.

    Example
    -------
    >>> _sanitize_folder_name("09 2051//PPS / mesPPS//pps_2", separator="//")
    '09 2051//PPS - mesPPS//pps_2'

    Parameters
    ----------
    folder_name : str
        Original folder path extracted from the connector, e.g.
        `"09 2051//PPS / mesPPS//pps_2"`.

    separator : str, optional
        Folder separator used by the connector (default: `"//"`).

    replacement_char : str, optional
        Character used to replace forbidden `'/'` characters inside folder names
        (default: `'-'`).

    Returns
    -------
    str
        Sanitized folder path, safe to pass to FRED’s `TagService.create_tag_for_user()`.
    """
    safe_segments = []
    for segment in folder_name.split(separator):
        # Replace internal slashes in each segment
        if separator != "/":
            safe_segments.append(segment.replace("/", replacement_char))
        else:
            safe_segments.append(segment)
    return separator.join(safe_segments)

def normalize_filename(filename: str) -> str:
    """Ensure consistency: if no extension in filename → force .XLSM."""
    if "." not in filename:
        logger.warning(f"[Sync] File '{filename}' missing extension → forcing .XLSM")
        return filename + ".XLSM"
    return filename


class FileToIngest(TypedDict):
    local_path: str
    folder_name: str
    remote_modified: Optional[str]

class FileTagMapping(TypedDict):
    path: str
    tag: Tag
    remote_modified: Optional[str]


class RemoteFileInfo(TypedDict):
    full_path: str          # ex: "remote_connector://Top//Folder//file.xlsm"
    logical_path: str       # ex: "Top//Folder//file.xlsm" -> What we put in pull_location
    size: Optional[int]
    modified: Optional[str]
    raw: Dict[str, Any]

    
# -------------------------------------------------------------------
# FsspecFileIngestion class
# -------------------------------------------------------------------
class FsspecFileIngestion:
    """
    Generic ingestion pipeline for any fsspec-compatible connector.

    Responsibilities
    ----------------
    - Recursively list remote files
    - Group them under semantic tags (based on folder structure)
    - Download via connector.download_file()
    """

    def __init__(self, connector: AbstractFileSystem, settings: FsspecPullSource):
        self.app_context: ApplicationContext = ApplicationContext.get_instance()
        self.connector = connector
        self.settings = settings
        self.tag_service = TagService()
        self.ingestion_service = IngestionService()
        self.metadata_service = MetadataService()

    # -----------------------------------------------------------
    # Recursive listing
    # -----------------------------------------------------------
    
    async def _ls_async(self, path: str):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.connector.ls(path, detail=True)
        )

    async def _list_all_files_parallel(self, path: str = "", visited=None):
        if visited is None:
            visited = set()

        if path in visited:
            return []
        visited.add(path)

        # --- ls(path)  async/threadpool ---
        try:
            items = await self._ls_async(path)
        except Exception as e:
            logger.error(f"[Ingestion] Failed to list {path}: {e}")
            return []

        files = []
        subdirs = []

        for item in items:
            if item.get("type") == "file":
                files.append(item)
            elif item.get("type") == "directory":
                subdirs.append(item["name"])

        # --- parallelise run for subdirectories ---
        tasks = [
            self._list_all_files_parallel(sub, visited)
            for sub in subdirs
        ]

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for res in results:
                if isinstance(res, list):
                    files.extend(res)
                else:
                    logger.error(f"[Ingestion] Error in subtask: {res}")

        return files

    # -----------------------------------------------------------
    # Remote index (from fsspec connector)
    # -----------------------------------------------------------
    async def _build_remote_index(self) -> Dict[str, RemoteFileInfo]:
        """
        Build a complete index of all remote files exposed by the fsspec connector.

        The returned dictionary uses the *logical path* as key.  
        A logical path is defined as the portion located after the protocol prefix:
            "connector://A//B//file.txt" -> "A//B//file.txt"

        This logical path is later used internally as a stable identifier.
        """

        # list all files recursively parallel way
        files = await self._list_all_files_parallel("")
        index: Dict[str, RemoteFileInfo] = {}

        for item in files:
            # Skip folders
            if item.get("type", "").lower() != "file":
                continue

            full_path = item["name"]
            if not full_path:
                continue

            # Extract logical path (what will act as our unique key)
            raw_logical_path = full_path.split("://", 1)[-1]
            parts = [p for p in raw_logical_path.split(self._get_separator()) if p]
            filename = parts[-1]
            # Auto-fix missing extension for remote logical path (consistency with ingestion)
            filename = normalize_filename(filename)
        
            folder = self._get_separator().join(parts[:-1]) if len(parts) > 1 else "root"


            # Sanitize folder like in Fred
            safe_folder = _sanitize_folder_name(folder, self._get_separator())

            # Rebuild normalized logical path
            logical_path = safe_folder + self._get_separator() + filename

            index[logical_path] = {
                "full_path": full_path,
                "logical_path": logical_path,
                "size": item.get("size"),
                "modified": item.get("modified"),
                "raw": item,
            }

        logger.info(f"[Sync] Remote index built with {len(index)} files.")
        return index


    # -----------------------------------------------------------
    # Fred index (metadata_v2)
    # -----------------------------------------------------------
    async def _build_fred_index(self, source_tag: str = "fsspec") -> Dict[str, DocumentMetadata]:
        """
        Build a local index of all documents previously ingested into Fred,
        based on the tags (representing folder paths) and the stored filename.

        The resulting key follows the same layout as the remote logical path:
            <normalized_tag_name><separator><document_name>

        This ensures a strict one-to-one match between remote items and
        previously ingested Fred documents.
        """

        metadata_service = MetadataService()
        # apply filter on source tag for every document when getting documents metadata.
        filters = {
            "source": {
                "source_tag": source_tag
            }
        }
        # Fetch all documents whose source_tag matches the fsspec connector
        docs: List[DocumentMetadata] = await metadata_service.get_documents_metadata(
            user=NO_AUTHZ_CHECK_USER,
            filters_dict=filters,
        )
        
        separator = self._get_separator()
        index: Dict[str, DocumentMetadata] = {}

        # Preload all tags to reduce API calls
        existing_tags = await self._get_existing_tags()

        # Iterate over docs [DocumentMetadata]
        for doc in docs:
            
            filename = doc.identity.document_name
            # Auto-fix missing extension for remote logical path (consistency with ingestion)
            filename = normalize_filename(filename)
                
            tag_ids = doc.tags.tag_ids

            # Ignore malformed or incomplete entries
            if not filename or not tag_ids:
                continue

            # One tag per ingested document (by ingestion design)
            tag_id = tag_ids[0]

            # Retrieve the stored tag object
            tag_obj = await self.tag_service.get_tag_for_user(
                user=NO_AUTHZ_CHECK_USER,
                tag_id=tag_id
            )

            folder_name = tag_obj.name  # raw tag value

            # Ensure tag name follows our normalized ingestion rules
            normalized_tag = await self._get_or_create_tag(
                folder_name=folder_name,
                existing_tags=existing_tags,
            )

            normalized_tag_name = normalized_tag.name
            # Rebuild the canonical logical path
            if normalized_tag_name != "": # if tag has a name, rebuild the logical_path
                logical_path = normalized_tag_name + separator + filename
            else: # if tag name is empty, logical_path is just filename.
                logical_path = filename
            index[logical_path] = doc

        logger.info(
            f"[Sync] Fred index built with {len(index)} documents (source_tag={source_tag})."
        )
        return index


    # -----------------------------------------------------------
    # Diff computation (Fred vs Remote)
    # -----------------------------------------------------------
    async def compute_sync_plan(self, source_tag: str = "fsspec") -> Dict[str, Any]:
        """
        Compute a synchronization plan by comparing the remote index (from the fsspec
        connector) against the local Fred index for the specified `source_tag`.

        The result categorizes all files into:

            - to_add:     present remotely but missing in Fred
            - to_delete:  present in Fred but missing remotely
            - changed:    present in both but with differing content
            - unchanged:  present in both and considered identical

        Comparison strategy (in order of priority):
            1. Use the "modified" timestamp when available on both sides.
            2. Fallback to file size comparison when timestamps are not available.
            3. If neither timestamp nor size can be compared → treat as unchanged
            to avoid false positives.
        """

        # Build remote and local indexes
        remote_index = await self._build_remote_index()
        fred_index = await self._build_fred_index(source_tag=source_tag)

        remote_paths: Set[str] = set(remote_index.keys())
        fred_paths: Set[str] = set(fred_index.keys())

        logger.debug(f"remote_paths set : {remote_paths}")
        logger.debug(f"fred_paths set : {fred_paths}")
        # Files only on one side
        to_add = sorted(remote_paths - fred_paths)
        to_delete = sorted(fred_paths - remote_paths)

        changed: List[str] = []
        unchanged: List[str] = []

        # Compare files existing on both sides
        for logical_path in sorted(remote_paths & fred_paths):
            remote_info = remote_index[logical_path]
            fred_doc = fred_index[logical_path]

            # ---- Remote metadata ----
            remote_modification_date = remote_info.get("modified")

            # ---- Fred metadata ----
            extensions: Dict[str, Any] = fred_doc.extensions or {}
            fred_modification_date = extensions.get("source_modified")

            # Check update using modified timestamp
            logger.debug("Using timestamp comparison to check if some files have changed.")
            logger.debug(f"Last modified on remote : {remote_modification_date}")
            logger.debug(f"Last modified on Fred : {fred_modification_date}")
            if remote_modification_date != fred_modification_date:
                logger.info(f"File {logical_path} has changed and has been added to ingestion queue.")
                changed.append(logical_path)
            else:
                unchanged.append(logical_path)

        logger.info(
            "[Sync] Plan computed: to_add=%d, to_delete=%d, changed=%d, unchanged=%d",
            len(to_add),
            len(to_delete),
            len(changed),
            len(unchanged),
        )

        return {
            "to_add": to_add,
            "to_delete": to_delete,
            "changed": changed,
            "unchanged": unchanged,
            "remote_index": remote_index,
            "fred_index": fred_index,
        }

    # -----------------------------------------------------------
    # Sync execution (download + ingestion)
    # -----------------------------------------------------------
    async def sync_from_remote(self, source_tag: str = "fsspec", delete_missing: bool = True) -> Dict[str, Any]:
        """
        Execute the synchronization plan produced by `compute_sync_plan()`.

        This method performs two main operations:

            1. Download and ingest all files marked as:
                - "to_add"     → new files on the remote system
                - "changed"    → existing files whose content has been updated

            2. Optionally report files that no longer exist remotely ("to_delete").
            Physical or logical deletion inside Fred is *not implemented* yet.

        Returns
        -------
        Dict[str, Any]
            A dictionary containing the list of successfully ingested files and
            the complete synchronization plan.
        """

        # Build the sync plan (diff remote vs. Fred)
        plan = await self.compute_sync_plan(source_tag="fsspec")
        remote_index: Dict[str, RemoteFileInfo] = plan["remote_index"]

        separator = self._get_separator()
        files_to_ingest: list[FileToIngest] = []

        # -------------------------------------------------------
        # Download all new or modified files
        # -------------------------------------------------------
        for logical_path in plan["to_add"] + plan["changed"]:
            remote_info = remote_index[logical_path]
            full_remote_path = remote_info["full_path"]

            # Attempt to download the file
            local_path = self._download_file(
                remote_path=full_remote_path,
                dest_folder=Path(tempfile.gettempdir()),
                overwrite=True,
            )

            if not local_path or local_path.startswith("error:"):
                logger.error(f"[Sync] Failed to download '{full_remote_path}'. Skipping.")
                continue

            # Derive folder/tag name from the connector path
            folder_name = self._extract_folder_name(full_remote_path, separator)
            
            # handling errors for files with no suffix ("eg; .XLSM")

            filename = Path(local_path).name

            # Normalize filename (force .XLSM if missing)
            filename = normalize_filename(filename)

            # If remote file had no extension, rename the downloaded file LOCALLY
            local_path_obj = Path(local_path)
            if local_path_obj.suffix == "":  
                # remote had no extension → rename to match normalized name
                new_local_path = str(local_path_obj.with_suffix(".XLSM"))
                logger.warning(f"[Sync] File without extension detected: {local_path_obj.name} → forcing .XLSM")
                local_path_obj.rename(new_local_path)
                local_path = new_local_path

            # Now suffix is always correct here
            suffix = Path(local_path).suffix


            # And now skip only if still no suffix
            if not suffix:
                logger.warning(f"[Sync] Skipping file without extension: {filename}")
                continue

            # Prepare ingestion entry
            files_to_ingest.append({
                "local_path": local_path,
                "folder_name": folder_name,
                "remote_modified": remote_info.get("modified"),
            })

        # -------------------------------------------------------
        # Ingestion step
        # -------------------------------------------------------
        if files_to_ingest:
            logger.info(f"[Sync] Ingesting {len(files_to_ingest)} file(s) from remote...")
            await self.ingest_with_connector(files_to_ingest)
        else:
            logger.info("[Sync] No files to ingest (to_add + changed is empty).")

        # -------------------------------------------------------
        # Deletion step (files missing remotely)
        # -------------------------------------------------------
        if delete_missing and plan["to_delete"]:
            logger.info(f"[Sync] Deleting {len(plan['to_delete'])} documents missing remotely...")
            await self._delete_missing_documents(
                to_delete=plan["to_delete"],
                fred_index=plan["fred_index"],
            )

        # -------------------------------------------------------
        # Build and return summary
        # -------------------------------------------------------
        return {
            "synced_files": [e["local_path"] for e in files_to_ingest],
            "plan": {
                "to_add": plan["to_add"],
                "to_delete": plan["to_delete"],
                "changed": plan["changed"],
                "unchanged": plan["unchanged"],
            },
        }

    async def _delete_missing_documents(
        self,
        to_delete: list[str],
        fred_index: dict[str, DocumentMetadata],
    ):
        """
        Remove documents that exist in Fred but no longer exist remotely.
        The deletion logic relies on MetadataService.remove_tag_id_from_document(),
        which removes the tag, and deletes the document entirely if no tags remain.
        """

        for logical_path in to_delete:
            doc_metadata = fred_index.get(logical_path)
            if not doc_metadata:
                logger.warning(f"[Sync] Document '{logical_path}' not found in Fred index → skip deletion.")
                continue

            if not doc_metadata.tags or not doc_metadata.tags.tag_ids:
                logger.warning(f"[Sync] No tag found on doc '{doc_metadata.document_name}' → skip.")
                continue

            # ingestion design: one tag per file
            tag_id = doc_metadata.tags.tag_ids[0]

            logger.info(f"[Sync] Removing tag '{tag_id}' from deleted remote file '{logical_path}'")

            try:
                await self.metadata_service.remove_tag_id_from_document(
                    user=NO_AUTHZ_CHECK_USER,
                    metadata=doc_metadata,
                    tag_id_to_remove=tag_id,
                )
            except Exception as e:
                logger.error(f"[Sync] Failed to remove tag for '{logical_path}': {e}")


    # -----------------------------------------------------------
    # Configuration helpers
    # -----------------------------------------------------------
    def _get_separator(self) -> str:
        """
        Retrieve the path separator for this connector from configuration.yaml.

        Example:
        --------
        external_source:
          type: pull
          provider: external_source
          settings:
            - top_id: 0000001
            - separator: "//"
        """

        return self.settings.separator

    # -----------------------------------------------------------
    # Tag management
    # -----------------------------------------------------------
    async def _get_existing_tags(self) -> dict[str, Tag]:
        """
        Retrieve all existing DOCUMENT tags available to the ingestion user.

        Purpose
        -------
        This helper function is used to avoid creating duplicate tags during ingestion.
        It fetches all tags of type `DOCUMENT` from Fred’s tag service and returns them
        as a case-insensitive lookup dictionary (`name.lower() → Tag`).

        Returns
        -------
        dict[str, Tag]
            A mapping of lowercase tag names to their corresponding Tag objects.
            Example:
                {
                    "folder1": <Tag id='b9090785-f686-460f-ba4d-e923ce2a6fb7' name='Folder1'>,
                    "folder2": <Tag id='3e1a105a-2417-44a5-a460-07b9b586adaa' name='Folder2'>
                }

        Notes
        -----
        - Uses `NO_AUTHZ_CHECK_USER` to bypass authentication,.
        - Limits the result set to 500 tags to prevent excessive memory usage.
        - In case of any API failure, returns an empty dictionary and logs an error.
        """
        try:
            tags = await self.tag_service.list_all_tags_for_user(
                user=NO_AUTHZ_CHECK_USER,
                tag_type=TagType.DOCUMENT,
                limit=500,
            )
            return {t.name.lower(): t for t in tags}
        except Exception as e:
            logger.error(f"[Ingestion] Failed to retrieve existing tags: {e}")
            return {}

    def _extract_folder_name(self, remote_path: str, separator: str) -> str:
        """
        Return the full folder path (excluding the filename) as tag name.
        Example:
            "remote_connector://Engineering//R&D//Prototype//test.docx"
            → "Engineering//R&D//Prototype"
        """
        try:
            logical = remote_path.split("://", 1)[1] if "://" in remote_path else remote_path
            parts = [p.strip() for p in logical.split(separator) if p.strip()]
            # Remove the filename (last part) to keep the full folder path
            folder_parts = parts[:-1] if len(parts) > 1 else []
            return separator.join(folder_parts) if folder_parts else "root"
        except Exception:
            return "root"


    async def _get_or_create_tag(
        self,
        folder_name: str,
        existing_tags: dict[str, Tag],
        replacement_char: str = "-",
    ) -> Tag:
        """
        Retrieve an existing tag or create a new one if it does not already exist.

        This method ensures that every distinct folder path in the connector
        hierarchy corresponds to a single, unique tag in FRED.

        Behavior
        --------
        - If the tag corresponding to `folder_name` already exists in the cache
        (`existing_tags`), it is immediately returned to avoid redundant API calls.
        - Otherwise, the function sanitizes the folder path using the connector's
        configured separator (e.g., `"//"`), replacing any internal `'/'` characters
        inside folder names with a safe replacement character (default: `'-'`).
        This prevents accidental creation of multiple hierarchical tags by the
        TagService (which treats `'/'` as a path delimiter).
        - The sanitized folder path is then passed to `TagService.create_tag_for_user()`
        to create a new DOCUMENT-type tag in FRED.

        Parameters
        ----------
        folder_name : str
            Full folder path (up to the parent directory of the file) as extracted
            from the connector (e.g., `"09 2051//PPS / mesPPS//pps_2"`).

        existing_tags : dict[str, Tag]
            Dictionary of previously fetched tags (case-insensitive) used to prevent
            redundant creation of identical tags.

        replacement_char : str, optional
            Character used to replace `'/'` within folder names. Defaults to `'-'`.

        Returns
        -------
        Tag
            The existing or newly created Tag object representing this folder path.
        """
        separator = self._get_separator()
        safe_folder_name = _sanitize_folder_name(folder_name, separator, replacement_char)
        tag = existing_tags.get(safe_folder_name.lower())
        if tag:
            logger.debug(f"[Ingestion] Using existing tag: {tag.name}")
            return tag

        new_tag = await self.tag_service.create_tag_for_user(
            tag_data=TagCreate(name=safe_folder_name, type=TagType.DOCUMENT),
            user=NO_AUTHZ_CHECK_USER,
        )

        existing_tags[safe_folder_name.lower()] = new_tag
        logger.debug(f"[Ingestion] Created new tag: {new_tag.name} (id={new_tag.id})")
        return new_tag



    # -----------------------------------------------------------
    # File download (connector-based only)
    # -----------------------------------------------------------
    def _download_file(self, remote_path: str, dest_folder: Path, overwrite: bool = False) -> Optional[str]:
        """
        Download a single remote file to the local workspace using the connector’s `download_file()`.

        Notes
        -----
        - Only connectors implementing `download_file(remote_path, dest_path)` are supported.
        - fsspec itself does NOT define a standard `download_file()` API.
          This must be implemented in the connector class if file download is required.
        """
        separator = self._get_separator()
        local_filename = _basename_generic(remote_path, separator)
        dest_path = dest_folder / local_filename
        logger.debug(f"[Ingestion] Saving file to temporary path: {dest_path}")

        if not hasattr(self.connector, "download_file"):
            logger.error(
                f"[Ingestion] Connector '{type(self.connector).__name__}' "
                "does not implement `download_file()` — cannot download file.\n"
                "TODO: implement a `download_file(remote_path, dest_path)` method "
                "in the connector if you need file download capability."
            )  # @ TODO : handle case fsspec connector doesnt implement download_file method
            return None

        try:
            result = self.connector.download_file(remote_path, str(dest_path), overwrite=overwrite)  # type: ignore
            if isinstance(result, str) and not result.startswith("error:"):
                return result
            logger.error(f"[Ingestion] Connector.download_file() failed: {result}")
        except Exception as e:
            logger.error(f"[Ingestion] Error downloading {remote_path}: {e}")
        return None

    # -----------------------------------------------------------
    # Main ingestion logic
    # -----------------------------------------------------------
    async def ingest_with_connector(self, files_to_ingest: list[FileToIngest]) -> None:
        """Perform full ingestion: create/reuse tags and register downloaded files."""
        if not files_to_ingest:
            logger.warning("[Ingestion] No files to ingest.")
            return

        existing_tags = await self._get_existing_tags()
        file_tag_map: list[FileTagMapping] = []  # mapping file → Tag

        logger.debug("[Ingestion] Files to ingest:")
        for f in files_to_ingest:
            logger.debug(f"  - local={f['local_path']} | tag={f['folder_name']}")

        for entry in files_to_ingest:
            local_path = entry["local_path"]
            folder_name = entry["folder_name"]
            
            if not Path(local_path).suffix:
                logger.warning(f"[Ingestion] Skipping file without extension: {local_path}")
                continue
            
            tag = await self._get_or_create_tag(folder_name, existing_tags)
            file_tag_map.append({
                "path": local_path,
                "tag": tag,
                "remote_modified": entry["remote_modified"],
            })
            logger.debug(f"[Ingestion] File '{local_path}' → Tag '{folder_name}' (id={tag.id})")

        logger.debug(f"[Ingestion] Completed: {len(file_tag_map)} files processed.")
        await self.ingest_local_file(file_tag_map)

    # -------------------------------------------------------------------
    # ingestion pipeline -> FRED’s indexing layer
    # -------------------------------------------------------------------

    async def ingest_local_file(self, file_tag_map: list[FileTagMapping]) -> None:
        """
        Main ingestion pipeline for a list of FileTagMapping.

        Steps:
            1. save_input()      → store raw input in MinIO
            2. input_process()   → generate processed intermediate form
            3. output_process()  → generate preview files
            4. get_preview_file()
            5. save_output()     → store preview in MinIO
            6. save_metadata()   → persist metadata_v2
        """

        logger.info(
            f"[Ingestion] Indexing {len(file_tag_map)} local files with explicit tag mappings."
        )

        loop = asyncio.get_running_loop()

        for i, entry in enumerate(file_tag_map, start=1):
            logger.info(f"[Ingestion] Processing file {i}/{len(file_tag_map)}")

            input_file = Path(entry["path"])
            remote_modified = entry.get("remote_modified")
            tag_ids = [entry["tag"].id]

            # -------------------------------------------------------
            # METADATA EXTRACTION
            # -------------------------------------------------------
            metadata = self.ingestion_service.extract_metadata(
                NO_AUTHZ_CHECK_USER,
                file_path=input_file,
                tags=tag_ids,
                source_tag="fsspec",
            )

            metadata.extensions = metadata.extensions or {}
            if remote_modified:
                metadata.extensions["source_modified"] = remote_modified

                try:
                    parsed = datetime.strptime(remote_modified, "%Y-%m-%dT%H:%M:%S%z")
                    metadata.extensions["source_modified_parsed"] = parsed.isoformat()
                except Exception as e:
                    logger.warning(f"[Ingestion] Failed to parse remote modified date: {e}")

            document_uid = metadata.document_uid

            # -------------------------------------------------------
            # PREPARE WORKING DIRECTORY (but NOT USED later)
            # -------------------------------------------------------
            # We MUST call it because input_process/output_process expect it,
            # but the output may not be written here.
            prepare_working_dir(document_uid)

            # -------------------------------------------------------
            # 1) save_input()
            # -------------------------------------------------------
            latest_dir = get_latest_working_dir(document_uid)
            input_dir = latest_dir / "input"

            try:
                shutil.copy(input_file, input_dir / input_file.name)

                self.ingestion_service.save_input(
                    user=NO_AUTHZ_CHECK_USER,
                    metadata=metadata,
                    input_dir=input_dir,
                )
                logger.info(f"[Ingestion] Saved raw input for {document_uid}")

            except Exception as e:
                raise Exception(f"[Ingestion] save_input() failed: {e}")

            # -------------------------------------------------------
            # 2) input_process()
            # -------------------------------------------------------
            try:
                await loop.run_in_executor(
                    None,
                    input_process,
                    NO_AUTHZ_CHECK_USER,
                    input_file,
                    metadata,
                )
                logger.info("input_process() OK")
            except Exception as e:
                raise Exception(f"input_process() failed: {e}")

            # -------------------------------------------------------
            # Build FileToProcess object
            # -------------------------------------------------------
            file_to_process = FileToProcess(
                document_uid=document_uid,
                external_path=None,
                source_tag="fsspec",
                tags=tag_ids,
                processed_by=NO_AUTHZ_CHECK_USER,
            )

            # -------------------------------------------------------
            # 3) output_process()
            # -------------------------------------------------------
            try:
                await loop.run_in_executor(
                    None,
                    output_process,
                    file_to_process,
                    metadata,
                    True,
                )
                logger.info("output_process() OK")
            except Exception as e:
                raise Exception(f"output_process() failed: {e}")

            # -------------------------------------------------------
            # Locate the REAL working_dir (newest one)
            # -------------------------------------------------------
            working_dir = get_latest_working_dir(document_uid)
            output_dir = working_dir / "output"

            # -------------------------------------------------------
            # 4) get_preview_file()
            # -------------------------------------------------------
            try:
                preview_file = self.ingestion_service.get_preview_file(
                    user=NO_AUTHZ_CHECK_USER,
                    metadata=metadata,
                    output_dir=output_dir,
                )
                logger.info(f"[Ingestion] Preview file located at: {preview_file}")

            except Exception as e:
                # Debug crash helper
                logger.error(f"[DEBUG] output_dir content: {list(output_dir.iterdir())}")
                logger.error(f"[DEBUG] working_dir used: {working_dir}")
                raise Exception(f"get_preview_file() failed: {e}")

            # -------------------------------------------------------
            # 5) save_output()
            # -------------------------------------------------------
            try:
                self.ingestion_service.save_output(
                    user=NO_AUTHZ_CHECK_USER,
                    metadata=metadata,
                    output_dir=output_dir,
                )
                logger.info(f"[Ingestion] Saved output preview for {document_uid}")

            except Exception as e:
                raise Exception(f"save_output() failed: {e}")

            # -------------------------------------------------------
            # 6) save_metadata()
            # -------------------------------------------------------
            try:
                await self.ingestion_service.save_metadata(NO_AUTHZ_CHECK_USER, metadata)
                logger.info(f"[Ingestion] Metadata saved for {document_uid}")

            except Exception as e:
                raise Exception(f"save_metadata() failed: {e}")