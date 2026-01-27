from pydantic.dataclasses import dataclass


@dataclass
class RawPlayer:
    id: str
    first_name: str
    last_name: str
    date_of_birth: str
