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

def get_bgg_collection():
    with requests.Session() as s:
        details = {
            "credentials": {
                "username": USER,
                "password": PW
            }
        }

        s.post("https://boardgamegeek.com/login/api/v1", json=details)

        req = s.get(f"https://boardgamegeek.com/xmlapi2/collection?username={USER}&showprivate=1")

        soup = BeautifulSoup(req.text, features="xml")
        if soup.find("message"):
            print("Collection request initiated.")
        else:
            return soup

def get_bgg_plays(page=1):
    with  requests.Session() as s:
        req = s.get(f"https://boardgamegeek.com/xmlapi2/plays?username={USER}&page={page}")
        return req.text

# data = get_bgg_data()
# with open("bgg_data.xml", "w") as f:
#     f.write(data)
    
# with open("plays.xml", "r") as f:
#     data = f.read()

def read_bgg_collection(data):

    items = data.findAll("item")

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

    return game_data

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
    bgg_data = get_bgg_collection()
    game_data = read_bgg_collection(bgg_data)
    update_airtable(game_data, table_id=COLLECTION_TABLE, key_fields=["game", "object_id", "coll_id"])
    # print(read_bgg_plays(data))
    # for i in range(1,11):
    #     data = get_bgg_plays(page=i)
    #     play_data = read_bgg_plays(data)
    #     update_airtable(play_data, PLAYS_TABLE, key_fields=["id"])
    #     time.sleep(3)
    # pass