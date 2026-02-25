import re

from bs4 import BeautifulSoup
from datetime import datetime
from pathlib import Path

from ..models import Player


def transform_player_page(page_path: Path | str) -> Player:
    path = Path(page_path)

    if not path.exists():
        raise FileNotFoundError(f"Player file not found {page_path}")

    with open(page_path, mode="r", encoding="utf-8", errors="replace") as f:
        soup = BeautifulSoup(markup=f, features="html.parser")

    player_name = soup.find("h1")

    if (player_name == None):
        raise RuntimeError(f"Player name could not be parsed {page_path}")

    birthdate_content = soup.find(string=re.compile("(\d{1,2}-[A-Za-z]{3}-\d{4})"))

    if (birthdate_content == None):
        raise RuntimeError(f"Player date of birth could not be parsed {page_path}")

    id = re.sub(".html", "", path.name)
    birthdate = re.sub(r" \(", "", birthdate_content)
    givenname, familyname = re.split(" ", player_name.text, maxsplit=1)

    return Player(
        id=id,
        givenname=givenname,
        familyname=familyname,
        birthdate=datetime.strptime(birthdate, "%d-%b-%Y")
    )

def transform_player_data():
    player_page_dir = Path("afl_scraper/data/raw/player/")
    player_page_files = [p for p in player_page_dir.iterdir() if p.is_file()]

    for player_page in player_page_files:
        print(transform_player_page(player_page))
