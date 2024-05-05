import os
import time
import requests
from bs4 import BeautifulSoup
from pyairtable import Api

USER = os.environ["USERNAME"]
PW = os.environ["PW"]
AIRTABLE_TOKEN = os.environ["AIRTABLE_TOKEN"]

# move to .env?
AIRTABLE_BASE = "appP335Rk2WlkFqCs"
COLLECTION_TABLE = "tblFOoQ5UokcjjqNB"
PLAYS_TABLE = "tblWr6IW1xFO1ni3b"

class BGGConnection:
    def __init__(self, user = None, pw = None, infile = None):
        
        self.user = ""
        self.pw = ""
        self.file_path = ""
        self.data = ""

        if user and pw:
            self.user = user
            self.pw = pw

        if infile:
            self.file_path = infile

    def get_collection(self):
        if self.file_path:
            with open(self.file_path, "r") as f:
                self.data = f.read()

        elif self.user and self.pw:
            with requests.Session() as s:
                details = {
                    "credentials": {
                        "username": USER,
                        "password": PW
                    }
                }

                s.post("https://boardgamegeek.com/login/api/v1", json=details)

                req = s.get(f"https://boardgamegeek.com/xmlapi2/collection?username={self.user}&showprivate=1")

                self.data = req.text
                return self.data

    def get_bgg_plays(page=1):
        with  requests.Session() as s:
            req = s.get(f"https://boardgamegeek.com/xmlapi2/plays?username={self.user}&page={page}")
            return req.text

class BGGCollection:
    def __init__(self, raw_data):
        self.data = self.read_bgg_collection(raw_data)

    def read_bgg_collection(self, raw_data):

        items = raw_data.findAll("item")

        game_data = []

        for item in items:
            name = item.find("name").text
            object_id = item.get("objectid")
            coll_id = item.get("collid")
            pub_year = item.find("yearpublished").text if item.find("yearpublished") else ""
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
            game_data.append({
                "fields": {
                    "game": name,
                    "object_id": object_id,
                    "coll_id": coll_id,
                    "pub_year": int(pub_year) if pub_year else "",
                    "status": status,
                    "plays": int(plays) if plays else "",
                    "date_acquired": acquisition_date,
                    "year_acquired": acquisition_date.split("-")[0] if acquisition_date else "",
                    "price_paid": float(price_paid) if price_paid else "",
                    "acquired_from": acquired_from
                }
            })

        self.data = game_data
        return self.data

def read_bgg_plays(data):
    soup = BeautifulSoup(data, features="xml")
    plays = soup.findAll("play")

    play_data = []

    for play in plays:
        id = play.get("id")
        date = play.get("date")
        qty = play.get("quantity")
        location = play.get("location")
        game = play.find("item").get("name")
        players = []
        if play.find("players"):
            players = [player.get("name") for player in play.findAll("player")]

        play_data.append({
            "fields": {
                "date": date,
                "game": game,
                "plays": qty,
                "location": location,
                "players": players,
                "id": id 
            }   
        })

    return play_data

def update_airtable(game_data, table_id, key_fields):
    api = Api(api_key=AIRTABLE_TOKEN)
    table = api.table(AIRTABLE_BASE, table_id)
    table.batch_upsert(game_data, key_fields=key_fields, typecast=True)
    print(f"Updated Airtable. Found {len(game_data)} records.")


if __name__ == "__main__":
    cnx = BGGConnection(user=USER, pw=PW)
    data = cnx.get_collection()
    print(data)
    soup = BeautifulSoup(data, features="xml")
    if soup.find("message"):
        print("Request initiated. Waiting 30 seconds.")
        time.sleep(30)
        data = cnx.get_collection()
        print(data)
    collex = BGGCollection()
    game_data = collex.read_bgg_collection(soup)
    update_airtable(game_data, COLLECTION_TABLE, ["game", "object_id", "coll_id"])
    