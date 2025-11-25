import argparse
from pathlib import Path
import duckdb
import shutil
import tempfile

def main():
    parser = argparse.ArgumentParser(description="Inspect a DuckDB database safely via a temporary copy")
    parser.add_argument(
        "--path",
        type=Path,
        required=True,
        help="Path to the DuckDB database file"
    )
    args = parser.parse_args()
    db_path = args.path.expanduser()

    # 1. Create a temporary copy
    with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as tmp_file:
        temp_path = Path(tmp_file.name)
    shutil.copy2(db_path, temp_path)
    print("Temporary copy created at:", temp_path)

    try:
        # 2. Connect to the temp database in read-only mode
        conn = duckdb.connect(database=str(temp_path), read_only=True)
        print("Connected to temporary DuckDB copy.")

        # 3. List tables
        tables = conn.execute("SHOW TABLES;").fetchall()
        print("Tables in database:", tables)

        if tables:

            for table in tables :
                table_name = table[0]
                print("→ Inspecting table:", table_name)
                count = conn.execute(f"SELECT COUNT(*) FROM {table_name};").fetchone()[0]
                print("Number of rows in", table_name, ":", count)

                rows = conn.execute(f"SELECT * FROM {table_name} LIMIT 3;").fetchall()
                print("First 3 rows:")
                for row in rows:
                    print(row)
        else:
            print("⚠️ No tables found. Database may be empty.")

        conn.close()

    finally:
        # 4. Delete the temporary copy
        temp_path.unlink()
        print("Temporary copy deleted.")

if __name__ == "__main__":
    main()
