from psycopg import sql

from ..models import DBModel

def build_upsert_from_model(model: DBModel):
    data = model.model_dump()
    table = model.__table_name__
    conflict_cols = model.__conflict_cols__
    exclude_update = set(model.__exclude_updates_cols__)

    columns = list(data.keys())

    insert_cols = sql.SQL(", ").join(map(sql.Identifier, columns))
    insert_vals = sql.SQL(", ").join(sql.Placeholder() * len(columns))

    update_cols = [
        sql.SQL("{c} = EXCLUDED.{c}").format(c=sql.Identifier(col))
        for col in columns
        if col not in conflict_cols and col not in exclude_update
    ]

    query = sql.SQL("""
        INSERT INTO {table} ({insert_cols})
        VALUES ({insert_vals})
        ON CONFLICT ({conflict_cols})
        DO UPDATE SET {updates}
    """).format(
        table=sql.Identifier(table),
        insert_cols=insert_cols,
        insert_vals=insert_vals,
        conflict_cols=sql.SQL(", ").join(map(sql.Identifier, conflict_cols)),
        updates=sql.SQL(", ").join(update_cols),
    )

    return query, list(data.values())

def save_model(conn, model: DBModel) -> tuple[bool, int]:
    """
    Save a model to the database using UPSERT logic.

    Args:
        conn: Database connection
        model: The DBModel instance to save

    Returns:
        A tuple of (was_inserted, record_id) where:
        - was_inserted: True if a new record was inserted, False if updated
        - record_id: The ID of the inserted/updated record
    """
    query, values = build_upsert_from_model(model)

    # Add RETURNING clause to get back the ID and detect INSERT vs UPDATE
    # xmax = 0 indicates an INSERT, xmax > 0 indicates an UPDATE
    query = sql.SQL("{query} RETURNING id, (xmax = 0) AS inserted").format(query=query)

    with conn.cursor() as cur:
        cur.execute(query, values)
        result = cur.fetchone()

    conn.commit()

    # Return (was_inserted, record_id)
    return (result[1], result[0])
