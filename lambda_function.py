import os
import time
from itertools import batched
import requests
from bs4 import BeautifulSoup
from pyairtable import Api

USER = os.getenv("BGGUSERNAME")
PW = os.getenv("PW")
AIRTABLE_TOKEN = os.getenv("AIRTABLE_TOKEN")

# move to .env?
AIRTABLE_BASE = "appP335Rk2WlkFqCs"
COLLECTION_TABLE = "tblFOoQ5UokcjjqNB"
PLAYS_TABLE = "tblWr6IW1xFO1ni3b"


class CollectionNotReadyException(BaseException):
    pass


class BGGSession(requests.Session):
    """An authenticated BGG session"""

    def __init__(self, user=USER, pw=PW):
        self.user = user
        super().__init__()
        self.post(
            "https://boardgamegeek.com/login/api/v1",
            json={"credentials": {"username": user, "password": pw}},
        )

    def get_collection(self):
        """Requests BGG user collection with private items; returns BS4 soup"""
        req = self.get(
            f"https://boardgamegeek.com/xmlapi2/collection?username={self.user}&showprivate=1"
        )
        soup = BeautifulSoup(req.text, features="xml")
        if soup.find("message"):
            raise CollectionNotReadyException
        else:
            return soup

    # def get_bgg_plays(page=1):
    #     with  requests.Session() as s:
    #         req = s.get(f"https://boardgamegeek.com/xmlapi2/plays?username={self.user}&page={page}")
    #         return req.text


class BGGCollection:
    def __init__(self, raw_data):
        self.data = self.read_bgg_collection(raw_data)

    def read_bgg_collection(self, raw_data):
        items = raw_data.find_all("item")

        game_data = []

        for item in items:
            name = item.find("name").text
            object_id = item.get("objectid")
            coll_id = item.get("collid")
            pub_year = (
                item.find("yearpublished").text if item.find("yearpublished") else ""
            )
            status = []
            statuses = item.find("status")
            if statuses.get("own") == "1":
                status.append("Own")
            if statuses.get("prevowned") == "1":
                status.append("Previously owned")
            if statuses.get("wishlist") == "1":
                status.append("Wishlist")
            plays = int(item.find("numplays").text)
            private = item.find("privateinfo")
            acquisition_date = private.get("acquisitiondate") if private else ""
            price_paid = private.get("pricepaid") if private else ""
            acquired_from = private.get("acquiredfrom") if private else ""
            game_data.append(
                {
                    "fields": {
                        "game": name,
                        "object_id": object_id,
                        "coll_id": coll_id,
                        "pub_year": int(pub_year) if pub_year else "",
                        "status": status,
                        "plays": int(plays) if plays else "",
                        "date_acquired": acquisition_date,
                        "year_acquired": acquisition_date.split("-")[0]
                        if acquisition_date
                        else "",
                        "price_paid": float(price_paid) if price_paid else "",
                        "acquired_from": acquired_from,
                        "weight": 0.0,
                        "min_players": 0,
                        "max_players": 0,
                        "recommended_players": "",
                        "designers": [],
                    }
                }
            )

        self.data = game_data
        self.set_game_specific_data()
        return self.data

    def set_game_specific_data(self):
        ids = [game["fields"]["object_id"] for game in self.data]
        for batch in batched(ids, 20):
            url = (
                f"https://boardgamegeek.com/xmlapi2/thing?stats=1&id={','.join(batch)}"
            )
            print(f"Fetching {url}...")
            req = requests.get(url)
            lookup = {}
            soup = BeautifulSoup(req.text, features="xml")
            items = soup.find("items").find_all("item")
            for item in items:
                id = item.get("id")
                weight = item.find("statistics").find("averageweight").get("value")
                min_players = item.find("minplayers").get("value")
                max_players = item.find("maxplayers").get("value")
                poll_summaries = item.find_all("poll-summary")
                suggest_numplayers_summary = [
                    summary
                    for summary in poll_summaries
                    if summary.get("name") == "suggested_numplayers"
                ][0]
                best_with_result = [
                    res
                    for res in suggest_numplayers_summary.find_all("result")
                    if res.get("name") == "bestwith"
                ][0].get("value")

                designers = [
                    lnk.get("value")
                    for lnk in item.find_all("link")
                    if lnk.get("type") == "boardgamedesigner"
                ]
                pub_year = item.find("yearpublished").get("value")
                lookup[id] = {
                    "weight": weight,
                    "designers": designers,
                    "pub_year": pub_year,
                    "min_players": min_players,
                    "max_players": max_players,
                    "recommended_players": best_with_result,
                }
            for game in self.data:
                gid = game["fields"]["object_id"]
                if gid in lookup:
                    game["fields"]["weight"] = lookup[gid]["weight"]
                    game["fields"]["designers"] = lookup[gid]["designers"]
                    game["fields"]["pub_year"] = lookup[gid]["pub_year"]
                    game["fields"]["min_players"] = lookup[gid]["min_players"]
                    game["fields"]["max_players"] = lookup[gid]["max_players"]
                    game["fields"]["recommended_players"] = lookup[gid][
                        "recommended_players"
                    ]


# def read_bgg_plays(data):
#     soup = BeautifulSoup(data, features="xml")
#     plays = soup.find_all("play")

#     play_data = []

#     for play in plays:
#         id = play.get("id")
#         date = play.get("date")
#         qty = play.get("quantity")
#         location = play.get("location")
#         game = play.find("item").get("name")
#         players = []
#         if play.find("players"):
#             players = [player.get("name") for player in play.find_all("player")]

#         play_data.append({
#             "fields": {
#                 "date": date,
#                 "game": game,
#                 "plays": qty,
#                 "location": location,
#                 "players": players,
#                 "id": id
#             }
#         })

#     return play_data


def update_airtable(game_data, table_id, key_fields):
    api = Api(api_key=AIRTABLE_TOKEN)
    table = api.table(AIRTABLE_BASE, table_id)
    table.batch_upsert(game_data, key_fields=key_fields, typecast=True)
    print(f"Updated Airtable. Found {len(game_data)} records.")


if __name__ == "__main__":
    bgg = BGGSession()
    retries = 1
    while retries < 4:
        try:
            data = bgg.get_collection()
            break
        except CollectionNotReadyException:
            print(
                f"Collection not ready; trying again in 30 seconds. (Attempt #{retries})"
            )
            time.sleep(30)
            retries += 1
    if data.find("message"):
        print("The collection wasn't successfully retrieved.")
    else:
        game_data = BGGCollection(data)
        update_airtable(
            game_data.data, COLLECTION_TABLE, ["game", "object_id", "coll_id"]
        )
