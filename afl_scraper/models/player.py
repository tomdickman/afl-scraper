from datetime import datetime

from .db import DBModel


class Player(DBModel):
    __table_name__ = "player"
    __conflict_cols__ = ["id"]
    __exclude_updates_cols__ = ["id"]

    id: str
    givenname: str
    familyname: str
    birthdate: datetime
