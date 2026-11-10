import logging
import os
import sys
import time
from itertools import batched
import requests
from bs4 import BeautifulSoup
from pyairtable import Api

USER = os.getenv("BGGUSERNAME")
PW = os.getenv("PW")
AIRTABLE_TOKEN = os.getenv("AIRTABLE_TOKEN", "")

IN_GITHUB_ACTIONS = os.getenv("GITHUB_ACTIONS") == "true"

# Log to stdout, unbuffered, so messages show up in GitHub Actions output in
# order. Set LOG_LEVEL=DEBUG for more detail.
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
    force=True,
)
sys.stdout.reconfigure(line_buffering=True)
log = logging.getLogger("bgg")


def gha(command, message):
    """Emit a GitHub Actions workflow command (annotation) when running in CI."""
    if IN_GITHUB_ACTIONS:
        print(f"::{command}::{message}", flush=True)


def describe_secret(name, value):
    """Describe an env var without revealing its value."""
    if value is None:
        return f"{name}: NOT SET"
    if value == "":
        return f"{name}: SET BUT EMPTY"
    note = " (has leading/trailing whitespace!)" if value != value.strip() else ""
    return f"{name}: set, length {len(value)}{note}"


def log_response(label, resp, body_chars=300):
    """Log the key facts about an HTTP response. Body is truncated because the
    repo (and so the Actions log) is public."""
    log.info(
        "%s -> HTTP %s %s, %d bytes, content-type=%r, url=%s",
        label,
        resp.status_code,
        resp.reason,
        len(resp.content),
        resp.headers.get("Content-Type"),
        resp.url,
    )
    if resp.history:
        log.info(
            "%s redirect chain: %s",
            label,
            " -> ".join(f"{r.status_code} {r.url}" for r in resp.history),
        )
    interesting = {
        k: v
        for k, v in resp.headers.items()
        if k.lower() in ("server", "cf-ray", "cf-mitigated", "retry-after", "www-authenticate")
    }
    if interesting:
        log.info("%s notable headers: %s", label, interesting)
    if body_chars:
        log.info("%s body (first %d chars): %r", label, body_chars, resp.text[:body_chars])

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
        gha("group", "BGG login")
        log.info("Logging in to BGG as user %r", user)
        resp = self.post(
            "https://boardgamegeek.com/login/api/v1",
            json={"credentials": {"username": user, "password": pw}},
        )
        # Don't log the login body; just status and which cookies came back.
        log_response("Login", resp, body_chars=0)
        cookie_names = sorted(self.cookies.keys())
        log.info("Session cookies after login: %s", cookie_names or "NONE")
        if not resp.ok:
            log.error("BGG login failed with HTTP %s", resp.status_code)
            gha("error", f"BGG login failed with HTTP {resp.status_code}")
        elif "bggusername" not in [c.lower() for c in cookie_names]:
            log.warning("Login returned OK but no bggusername cookie; login may not have worked")
            gha("warning", "BGG login returned no bggusername cookie")
        gha("endgroup", "")

    def get_collection(self):
        """Requests BGG user collection with private items; returns BS4 soup"""
        req = self.get(
            f"https://boardgamegeek.com/xmlapi2/collection?username={self.user}&showprivate=1",
            headers={"Authorization": f"Bearer {os.environ['BGGTOKEN']}"},
        )
        log_response("Collection", req)
        soup = BeautifulSoup(req.text, features="xml")
        if soup.find("message"):
            log.info("Collection response contained <message>: %r", soup.find("message").text.strip())
            raise CollectionNotReadyException
        errors = soup.find_all("error")
        if errors:
            for e in errors:
                log.error("BGG collection API error: %r", e.get_text(strip=True))
            gha("error", "BGG collection API returned an error; see log")
        items_tag = soup.find("items")
        if items_tag is None:
            log.error("Collection response has no <items> element (not the expected XML)")
            gha("error", f"Collection response was not the expected XML (HTTP {req.status_code})")
        else:
            n = len(items_tag.find_all("item"))
            log.info(
                "Collection <items totalitems=%r>, parsed %d <item> elements; %d have <privateinfo>",
                items_tag.get("totalitems"),
                n,
                len(soup.find_all("privateinfo")),
            )
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
            log.info("Fetching %s", url)
            req = requests.get(
                url, headers={"Authorization": f"Bearer {os.environ['BGGTOKEN']}"}
            )
            log_response("Thing", req, body_chars=0 if req.ok else 300)
            lookup = {}
            soup = BeautifulSoup(req.text, features="xml")
            items_tag = soup.find("items")
            if items_tag is None:
                log.error("Thing response for batch has no <items>; skipping batch")
                gha("error", f"BGG thing API returned unexpected response (HTTP {req.status_code})")
                continue
            items = items_tag.find_all("item")
            log.info("Thing batch: requested %d ids, got %d items", len(batch), len(items))
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
                best_with_result = (
                    [
                        res
                        for res in suggest_numplayers_summary.find_all("result")
                        if res.get("name") == "bestwith"
                    ][0]
                    .get("value")
                    .replace("Best with ", "")
                    .replace(" players", "")
                )

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
    gha("group", "Airtable upsert")
    log.info(
        "Upserting %d records to Airtable base %s table %s (key fields %s)",
        len(game_data),
        AIRTABLE_BASE,
        table_id,
        key_fields,
    )
    if not game_data:
        log.warning("No records to send to Airtable; nothing will be updated")
        gha("warning", "0 records sent to Airtable - BGG collection came back empty")
    elif log.isEnabledFor(logging.DEBUG):
        log.debug("First record: %r", game_data[0])
    api = Api(api_key=AIRTABLE_TOKEN)
    table = api.table(AIRTABLE_BASE, table_id)
    try:
        result = table.batch_upsert(game_data, key_fields=key_fields, typecast=True)
    except Exception:
        log.exception("Airtable batch_upsert failed")
        gha("error", "Airtable batch_upsert raised an exception; see log")
        raise
    created = result.get("createdRecords", []) if isinstance(result, dict) else []
    updated = result.get("updatedRecords", []) if isinstance(result, dict) else []
    log.info(
        "Airtable upsert done: %d created, %d updated, %d records returned",
        len(created),
        len(updated),
        len(result.get("records", [])) if isinstance(result, dict) else -1,
    )
    gha("endgroup", "")


if __name__ == "__main__":
    gha("group", "Environment")
    log.info("Running in GitHub Actions: %s", IN_GITHUB_ACTIONS)
    log.info("Python %s", sys.version.split()[0])
    for name in ("BGGUSERNAME", "PW", "AIRTABLE_TOKEN", "BGGTOKEN"):
        log.info(describe_secret(name, os.getenv(name)))
    gha("endgroup", "")
    for name in ("BGGUSERNAME", "PW", "AIRTABLE_TOKEN", "BGGTOKEN"):
        if not os.getenv(name):
            gha("error", f"Environment variable {name} is missing or empty - check repo secrets")

    bgg = BGGSession()
    retries = 1
    data = None
    while retries < 4:
        try:
            data = bgg.get_collection()
            break
        except CollectionNotReadyException:
            log.info(
                "Collection not ready; trying again in 30 seconds. (Attempt #%d)", retries
            )
            time.sleep(30)
            retries += 1
    if data is None or data.find("message"):
        log.error("The collection wasn't successfully retrieved after %d attempts.", retries - 1)
        gha("error", "BGG collection was never ready")
    else:
        game_data = BGGCollection(data)
        update_airtable(
            game_data.data, COLLECTION_TABLE, ["game", "object_id", "coll_id"]
        )
        with open("log.txt", "a") as f:
            f.write(
                f"{time.strftime('%Y-%m-%d', time.localtime(time.time()))}: Found {len(game_data.data)} games and {sum([int(r['fields']['plays']) for r in game_data.data if r['fields']['plays']])} plays\n"
            )
