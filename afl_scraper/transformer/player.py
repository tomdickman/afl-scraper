from datetime import datetime

from ..models import Player
from ..scraper.models import RawPlayer


def transform_player(input: RawPlayer) -> Player:
    return Player(
        id=input.id,
        givenname=input.first_name,
        familyname=input.last_name,
        birthdate=datetime.strptime(input.date_of_birth, "%d-%b-%Y"),
    )
