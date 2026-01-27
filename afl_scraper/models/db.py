from pydantic import BaseModel


class DBModel(BaseModel):
    """
    Docstring for DBModel
    """

    __table_name__: str
    """
    The table name this model pertains to.
    """
    __conflict_cols__: list[str]
    """
    Column names which, when a value conflict is found in table with an existing row,
    `UPDATE` is conducted instead of an `INSERT`.
    """
    __exclude_updates_cols__: list[str]
    """
    Columns which are immutable, i.e. these column values are only entered on initial `INSERT`.
    If a conflict is found and an `UPDATE` is conducted instead of an `INSERT`, these columns are skipped.
    """
