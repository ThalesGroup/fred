import argparse
from pathlib import Path
import chromadb

def main():
    parser = argparse.ArgumentParser(description="Inspect a ChromaDB collection at specified path")
    parser.add_argument(
        "--path",
        type=Path,
        required=True,
        help="Path to the ChromaDB persistent folder"
    )
    args = parser.parse_args()

    persist_path = args.path.expanduser()

    client = chromadb.PersistentClient(path=persist_path)

    # 1. List the collections
    collections = client.list_collections()
    print("Available collections:", collections)

    if not collections:
        print("No collections found. Check the path, the tenant/database or whether the collection was really added.")
        return

    # 2. Inspect first collection
    if isinstance(collections[0], str):
        col_name = collections[0]
        print("→ Inspecting collection:", col_name)
        col = client.get_collection(name=col_name)
    else:
        col = collections[0]
        col_name = col.name

    # 3. Show collection properties
    try:
        meta = col.metadata
    except AttributeError:
        meta = None
    print("Collection name:", col_name)
    print("Collection metadata:", meta)
    count = col.count()
    print("\nNumber of documents in the collection:", count)

    # 4. Display first 3 documents (if available)
    num_to_show = min(3, count)
    if num_to_show == 0:
        print("The collection is empty — no documents to display.")
    else:
        batch = col.get(offset=0, limit=num_to_show, include=["documents","metadatas","embeddings"])
        print(f"\nDisplaying the first {num_to_show} documents:")
        for i in range(num_to_show):
            print("\n-- Example", i+1, "--")
            print("ID:", batch["ids"][i])
            print("\nDocument:", batch["documents"][i])
            print("\nMetadata:", batch["metadatas"][i])
            embedding = batch["embeddings"][i]
            print("\nEmbedding (first components):", str(embedding[:10] if embedding is not None else embedding)[:-1]+ " ...]")

if __name__ == "__main__":
    main()
