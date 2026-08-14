from dataclasses import dataclass
from typing import Any

from psycopg import sql

from ..models import DBModel


@dataclass(frozen=True)
class SaveResult:
    """The outcome of saving one model.

    ``identity`` contains every conflict column, so this result works for both
    conventional single-column IDs and composite natural keys.
    """

    was_inserted: bool
    identity: dict[str, Any]


def build_upsert_from_model(model: DBModel):
    data = model.model_dump()
    table = model.__table_name__
    conflict_cols = model.__conflict_cols__
    exclude_update = set(model.__exclude_updates_cols__)
    preserve_existing_on_null = set(model.__preserve_existing_on_null_cols__)

    columns = list(data.keys())

    insert_cols = sql.SQL(", ").join(map(sql.Identifier, columns))
    insert_vals = sql.SQL(", ").join(sql.Placeholder() * len(columns))

    update_cols = []
    for col in columns:
        if col in conflict_cols or col in exclude_update:
            continue
        if col in preserve_existing_on_null:
            assignment = sql.SQL("{c} = COALESCE(EXCLUDED.{c}, {table}.{c})").format(
                c=sql.Identifier(col), table=sql.Identifier(table)
            )
        else:
            assignment = sql.SQL("{c} = EXCLUDED.{c}").format(c=sql.Identifier(col))
        update_cols.append(assignment)

    query = sql.SQL(
        """
        INSERT INTO {table} ({insert_cols})
        VALUES ({insert_vals})
        ON CONFLICT ({conflict_cols})
        DO UPDATE SET {updates}
    """
    ).format(
        table=sql.Identifier(table),
        insert_cols=insert_cols,
        insert_vals=insert_vals,
        conflict_cols=sql.SQL(", ").join(map(sql.Identifier, conflict_cols)),
        updates=sql.SQL(", ").join(update_cols),
    )

    return query, list(data.values())


def save_model(conn, model: DBModel) -> SaveResult:
    """
    Save a model to the database using UPSERT logic.

    Args:
        conn: Database connection
        model: The DBModel instance to save

    Returns:
        A :class:`SaveResult` containing whether the row was inserted and its
        identity (the model's conflict columns).

    Transaction management belongs to the caller. This allows several related
    saves to be committed or rolled back as one unit.
    """
    query, values = build_upsert_from_model(model)

    identity_columns = model.__conflict_cols__

    # Return the model's natural identity and detect INSERT vs UPDATE.
    # xmax = 0 indicates an INSERT, xmax > 0 indicates an UPDATE
    query = sql.SQL("{query} RETURNING {identity}, (xmax = 0) AS inserted").format(
        query=query,
        identity=sql.SQL(", ").join(map(sql.Identifier, identity_columns)),
    )

    with conn.cursor() as cur:
        cur.execute(query, values)
        result = cur.fetchone()

    if result is None:
        raise RuntimeError(f"UPSERT into {model.__table_name__} returned no row")

    identity_values = result[:-1]
    return SaveResult(
        was_inserted=result[-1],
        identity=dict(zip(identity_columns, identity_values, strict=True)),
    )
