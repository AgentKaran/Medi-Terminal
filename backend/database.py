import sqlite3
import pandas as pd
from backend.config import DB_PATH

def get_db_connection():
    return sqlite3.connect(DB_PATH)

def get_schema_info() -> str:
    """
    Returns a text description of the database tables and columns,
    suitable for placing in an LLM prompt.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get table list
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [t[0] for t in cursor.fetchall()]
    
    schema_desc = []
    for table in tables:
        cursor.execute(f"PRAGMA table_info({table});")
        columns = cursor.fetchall()
        col_desc = []
        for col in columns:
            # col: (cid, name, type, notnull, dflt_value, pk)
            pk_suffix = " (PRIMARY KEY)" if col[5] else ""
            col_desc.append(f"    - {col[1]} ({col[2]}){pk_suffix}")
        
        cols_text = "\n".join(col_desc)
        schema_desc.append(f"Table: {table}\nColumns:\n{cols_text}")
        
        # Add sample data
        try:
            df_sample = pd.read_sql_query(f"SELECT * FROM {table} LIMIT 2", conn)
            sample_text = df_sample.to_string(index=False)
            schema_desc.append(f"Sample rows:\n{sample_text}\n")
        except Exception as e:
            schema_desc.append(f"Sample rows: error retrieving samples ({str(e)})\n")
            
    conn.close()
    return "\n\n".join(schema_desc)

def execute_read_query(sql_query: str):
    """
    Executes a read-only SQL query against the SQLite database.
    Returns the rows as a pandas DataFrame or a list of dicts.
    """
    # Force read-only by checking for modification statements
    forbidden = ["insert", "update", "delete", "drop", "create", "alter", "replace"]
    query_lower = sql_query.lower()
    for word in forbidden:
        if word in query_lower:
            raise ValueError(f"Write operation '{word}' is not allowed in read-only queries.")
            
    conn = get_db_connection()
    try:
        df = pd.read_sql_query(sql_query, conn)
        result = df.to_dict(orient="records")
        return result
    except Exception as e:
        raise Exception(f"SQL execution error: {str(e)}")
    finally:
        conn.close()

if __name__ == "__main__":
    # Test schema loading
    print("Database Schema Info:")
    print(get_schema_info())
