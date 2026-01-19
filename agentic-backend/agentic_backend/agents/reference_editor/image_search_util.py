import io
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def search_image_by_name(image_name: str, vector_search_client, kf_base_client) -> Optional[str]:
    """
    Search for an image document by its name in the knowledge flow backend.

    Args:
        image_name: The name/title of the image to search for (e.g., "Apple", "Nvidia", "SharePoint")
        vector_search_client: VectorSearchClient instance for searching
        kf_base_client: KfBaseClient instance for downloading

    Returns:
        The document_uid of the image if found, None otherwise
    """
    try:
        logger.info(f"Searching for image with name: {image_name}")

        # Use VectorSearchClient.search() method
        hits = vector_search_client.search(
            question=image_name,
            top_k=5,
            search_policy="semantic"
        )

        if hits and len(hits) > 0:
            # Try to find exact match first (case-insensitive)
            for hit in hits:
                document_uid = hit.uid
                document_name = hit.file_name or ""

                # Check if document name matches (without extension)
                if document_name:
                    name_without_ext = document_name.rsplit(".", 1)[0]
                    if name_without_ext.lower() == image_name.lower():
                        logger.info(f"Found exact match image document: {document_uid} ({document_name}) for query: {image_name}")
                        return document_uid

            # If no exact match, return the first result
            hit = hits[0]
            document_uid = hit.uid
            document_name = hit.file_name or "unknown"
            logger.info(f"Found image document: {document_uid} ({document_name}) for query: {image_name}")
            return document_uid

        logger.warning(f"No image found for name: {image_name}")
        return None

    except Exception as e:
        logger.error(f"Error searching for image {image_name}: {e}", exc_info=True)
        return None


def download_image(document_uid: str, kf_base_client) -> Optional[io.BytesIO]:
    """
    Download the original image file from the knowledge flow backend.

    Args:
        document_uid: The document UID of the image
        kf_base_client: KfBaseClient instance

    Returns:
        BytesIO object containing the image data, or None if download fails
    """
    try:
        logger.info(f"Downloading image with document_uid: {document_uid}")

        # Use the internal method to make authenticated GET request
        response = kf_base_client._request_with_token_refresh(
            "GET",
            f"/raw_content/{document_uid}"
        )

        if response and response.content:
            image_data = io.BytesIO(response.content)
            logger.info(f"Successfully downloaded image: {document_uid}, size: {len(response.content)} bytes")
            return image_data

        logger.error(f"Failed to download image {document_uid}: Invalid response")
        return None

    except Exception as e:
        logger.error(f"Error downloading image {document_uid}: {e}", exc_info=True)
        return None


def get_image_for_technology(technology_name: str, vector_search_client, kf_base_client) -> Optional[io.BytesIO]:
    """
    High-level function to search and download an image for a given technology name.

    Args:
        technology_name: Name of the technology (e.g., "Apple", "Nvidia", "SharePoint")
        vector_search_client: VectorSearchClient instance for searching
        kf_base_client: KfBaseClient instance for downloading

    Returns:
        BytesIO object containing the image data, or None if not found
    """
    # Clean the technology name (remove extra whitespace, normalize)
    clean_name = technology_name.strip()

    logger.info(f"Getting image for technology: {clean_name}")

    # Search for the image
    document_uid = search_image_by_name(clean_name, vector_search_client, kf_base_client)

    if not document_uid:
        logger.warning(f"Could not find image for technology: {clean_name}")
        return None

    # Download the image
    image_data = download_image(document_uid, kf_base_client)

    if not image_data:
        logger.warning(f"Could not download image for technology: {clean_name}")
        return None

    logger.info(f"Successfully retrieved image for technology: {clean_name}")
    return image_data
