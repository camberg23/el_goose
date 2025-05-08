# * What are the 5 most recent Goose shows?
# * Show me all Goose shows in “Boulder”.
# * List every setlist from 2019.
# * Give me the setlist for show\_id 1615873444.
# * Fetch setlists for the song “Franklin’s Tower”.
# * What venues has Goose played in “New York”?
# * Show jamchart entries for city “Dunedin”.
# * List all albums and their tracks.
# * Get metadata for song\_slug “everything-must-go”.
# * Fetch links attached to show\_id 1615873444.
# * Show upload items (posters) for show\_id 1615873444.
# * List all appearances by person\_id 46.
# * List all years Goose has played.
# * List all countries Goose played in 2017.
# * Return the list of US states Goose has played.
# * Give me the HTML setlist for showyear 2020.

import requests
from datetime import date

url = "https://elgoose.net/api/v2/shows.json"
params = {
    "order_by": "showdate",
    "direction": "desc",
    "limit": 5
}

resp = requests.get(url, params=params)
print("Status:", resp.status_code)
try:
    data = resp.json()
except Exception as e:
    print("JSON error:", e)
    print("Text snippet:", resp.text[:200])
    raise SystemExit

print("Error flag:", data.get("error"))
print("Entries:", len(data.get("data", [])))
for show in data.get("data", []):
    print(f"  • {show.get('showdate')} – {show.get('venuename')}, {show.get('city')}")

# TODO:
# -fix song thing
# -have a few demos that yuou know work
# -beautfy the streamlit app to make it look sick
# -push it and send to Adam as "here's what I was able to hack out on the plane, there's more where that came from."