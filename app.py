import streamlit as st
import json
from openai import OpenAI
from api_client import ElGooseClient
from datetime import datetime, date
from urllib.parse import quote_plus

# ── VERBOSITY: 0 hides raw debug output; 1 shows it ──
VERBOSITY = 0

# Initialize ElGoose API client
eg_client = ElGooseClient(base_url="https://elgoose.net/api/v2")

API_KEY = st.secrets['API_KEY']
# OpenAI client
oai = OpenAI(api_key=API_KEY)

#
# 1) Define a single, generic function schema that covers every API method:
#
functions = [
    {
        "type": "function",
        "name": "call_elgoose_api",
        "description": (
            "Make a request to any ElGoose.net API v2 endpoint. "
            "Parameters:\n"
            "- method: one of ['latest','shows','setlists','songs','venues',\n"
            "  'jamcharts','albums','metadata','links','uploads','appearances','list']\n"
            "- identifier: (optional) numeric ID for a specific row\n"
            "- column,value: (optional) filter by column/value\n"
            "- order_by,direction,limit: (optional) query-string args\n"
            "- artist,showyear: (optional) filters for list endpoints\n"
            "- fmt: 'json' or 'html' format\n"
            "Use list with column in ['year','country','state','city','venue','month','day']."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "method":    {"type": "string",  "description": "API method name"},
                "identifier":{"type": "integer", "description": "Specific row ID"},
                "column":    {"type": "string",  "description": "Column name for filtering"},
                "value":     {"type": "string",  "description": "Value to filter by"},
                "order_by":  {"type": "string",  "description": "Column to sort by"},
                "direction": {"type": "string",  "enum": ["asc","desc"], "description": "Sort direction"},
                "limit":     {"type": "integer", "description": "Max number of results"},
                "artist":    {"type": "integer", "description": "Artist ID for list endpoints (default=1)"},
                "showyear":  {"type": "integer", "description": "Year filter for list endpoints"},
                "fmt":       {"type": "string",  "enum": ["json","html"], "description": "Response format"}
            },
            "required": ["method"],
            "additionalProperties": False
        }
    }
]

#
# 2) Implement that generic function
#
from urllib.parse import quote_plus
from datetime import datetime, date
import json, streamlit as st

def call_elgoose_api(method: str,
                     identifier=None,
                     column=None,
                     value=None,
                     order_by=None,
                     direction=None,
                     limit=None,
                     artist=None,
                     showyear=None,
                     fmt="json"):

    # —— LIST endpoints: build /list/{column}.json with showyear & artist ——
    if method == "list" and column:
        url = f"{eg_client.base_url}/list/{column}.json"
        params = {"artist": artist if artist is not None else 1}
        if showyear is not None:
            params["showyear"] = showyear
        # actually call /list/{column}.json
        with st.spinner(f"Fetching list/{column}.json…"):
            raw = eg_client.fetch(
                f"list/{column}",  # <-- use "list/{column}" as the method
                None, None, None, fmt,
                **params
            )
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        return json.dumps({
            "data": raw.get("data", []),
            "url":   f"{url}?{qs}"
        })

    # —— 1) SONG PLAY COUNT ——
    if method == "songs" and column in ("song", "songname", "name"):
        song_filter = quote_plus(value.strip())
        url = f"{eg_client.base_url}/setlists/songname/{song_filter}.json"
        # st.write("🔍 [DEBUG] COUNT URL:", url)
        raw = eg_client.fetch(
            "setlists", None,
            "songname", song_filter,
            fmt, order_by="showdate",
            direction="asc", limit=10000
        )
        # st.write("🔍  [DEBUG] COUNT RAW PAYLOAD:", raw)
        plays = len(raw.get("data", []))
        return json.dumps({
            "data": {"song": value, "plays": plays},
            "url": url
        })

    # —— 2) TOP N MOST-PLAYED SONGS ——
    if method == "songs" and order_by == "times_played":
        raw = eg_client.fetch("setlists", None, None, None, fmt, limit=100000)
        counts = {}
        for rec in raw.get("data", []):
            name = rec.get("songname", "")
            counts[name] = counts.get(name, 0) + 1
        topn = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[: (limit or 5)]
        data = [{"song": n, "plays": c} for n, c in topn]
        url = f"{eg_client.base_url}/setlists.json?aggregate=times_played"
        return json.dumps({"data": data, "url": url})

    # —— 3) APPEARANCES name-based fallback ——
    if method == "appearances" and column and column not in ("person_id","show_id"):
        raw  = eg_client.fetch("appearances", None, None, None, fmt)
        rows = raw.get("data", [])
        name_keys = [k for k in (rows[0] if rows else {}) if "name" in k.lower()]
        for cand in ("personname","person_name","artist_name"):
            if cand in name_keys:
                name_key = cand
                break
        else:
            name_key = name_keys[0] if name_keys else None
        filtered = []
        if name_key:
            filtered = [r for r in rows if value.lower() in (r.get(name_key) or "").lower()]
        if limit:
            filtered = filtered[:limit]
        return json.dumps({
            "data": filtered,
            "url":  f"{eg_client.base_url}/appearances.json"
        })

    # —— 4) GENERIC ALBUMS HANDLER ——
    if method == "albums":
        sort_field = order_by or "releasedate"
        if sort_field == "release_date":
            sort_field = "releasedate"
        raw = eg_client.fetch(
            "albums", None, None, None, fmt,
            order_by=sort_field, direction=direction or "asc"
        )
        albums = {}
        for row in raw.get("data", []):
            key = row["album_url"]
            if key not in albums:
                albums[key] = {
                    "album_url":   key,
                    "album_title": row.get("album_title"),
                    "releasedate": row.get("releasedate"),
                    "artist":      row.get("artist"),
                    "tracks":      []
                }
            albums[key]["tracks"].append({
                "position":  row.get("position"),
                "song_name": row.get("song_name"),
                "tracktime": row.get("tracktime")
            })
        album_list = list(albums.values())
        album_list.sort(
            key=lambda a: a.get("releasedate") or "",
            reverse=(direction == "desc")
        )
        if limit:
            album_list = album_list[:limit]
        url = eg_client._build_url("albums", None, None, None, fmt)
        return json.dumps({"data": album_list, "url": url})

    # —— alias “song” → actual column “songname” elsewhere —
    if column == "song":
        column = "songname"
    if column == "year" and method in ("setlists","shows"):
        column = "showyear"

    # —— latest+limit>1 → shows(desc) redirection —
    if method == "latest" and limit and limit > 1:
        method, order_by, direction = "shows", order_by or "showdate", direction or "desc"

    # URL-encode the filter value
    if isinstance(value, str):
        value = quote_plus(value)

    # —— 5) SHOWS (filtered or unfiltered): over-fetch & drop future, then limit ——
    if method == "shows" and identifier is None:
        overfetch = (limit or 5) * 10
        raw = eg_client.fetch(
            "shows", None, column, value, fmt,
            order_by="showdate", direction="desc", limit=overfetch
        )
        today = date.today()
        past = []
        for item in raw.get("data", []):
            try:
                dt = datetime.strptime(item.get("showdate",""), "%Y-%m-%d").date()
                if dt <= today:
                    past.append(item)
                    if limit and len(past) >= limit:
                        break
            except:
                continue
        url = eg_client._build_url("shows", None, column, value, fmt)
        return json.dumps({"data": past, "url": url})

    # —— 6) GENERIC FALLBACK for everything else ——
    url = (f"{eg_client.base_url}/list/{column}.json"
           if method == "list" and column
           else eg_client._build_url(method, identifier, column, value, fmt))
    params = {k: v for k, v in {
        "order_by": order_by,
        "direction": direction,
        "limit": limit
    }.items() if v is not None}

    with st.spinner(f"Fetching {method}…"):
        raw = eg_client.fetch(
            method if not (method == "list" and column) else f"list/{column}",
            identifier, column, value, fmt, **params
        )

    # Post-fetch: if it’s a raw /shows.json with desc order, drop future
    if method == "shows" and direction == "desc" and isinstance(raw, dict):
        today = date.today()
        raw["data"] = [
            i for i in raw.get("data", [])
            if datetime.strptime(i.get("showdate",""), "%Y-%m-%d").date() <= today
        ]

    return json.dumps({
        "data": raw.get("data", raw),
        "url":  url
    })

#
# 3) Streamlit UI + LLM integration with chat-like interface
#
st.title("ElGoose.ai")

st.markdown(
    """
    **Welcome to ElGoose.ai** (WIP: CB hacked together on the plane ride over to Gonzo). 
    A conversational gateway to Goose’s entire ecosystem—shows, setlists, songs, venues, jam charts, appearances, albums, and more.

    **Ask questions like:**
    - Which countries did Goose tour in 2023?
    - When did Julian Lage appear with Goose?
    - Show me the setlist from June 30, 2024 at Westville Music Bowl.
    - List all albums and their tracklists.
    - What are Goose's top 5 most-played tunes?

    Behind the scenes, we’re dynamically calling every ElGoose API endpoint so you get exactly the data you need—no clicking required. Just chat!
    """
)

# system message content
system_content = (
    "You are an assistant that answers questions by calling the "
    "ElGoose API via the function call 'call_elgoose_api'.\n"
    "Note: the '/latest' endpoint always returns a single show. "
    "To fetch multiple recent shows, use method='shows' with "
    "order_by='showdate', direction='desc', and limit=<number>.\n\n"
    "IMPORTANT: *Whenever you are summarizing a ‘list’ endpoint (like "
    "`/list/country.json`), you must list **every** `field` value returned "
    "in the JSON—do not truncate, do not guess, do not paraphrase. "
    "If there are eight countries in the data, name all eight.*\n\n"
    "Choose the most appropriate parameters so the user gets exactly "
    "the data they want, and return a user-friendly natural-language summary. "
    "Always include the source URL at the end."
)

# initialize session state
if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "developer", "content": system_content}]

# render chat history
for msg in st.session_state.messages:
    if msg["role"] not in ("user", "assistant"):
        continue
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# accept user input
if prompt := st.chat_input("Ask about any Goose shows or setlists:"):
    # append and display user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # prepare for LLM + function-calling loop
    messages = st.session_state.messages.copy()
    final_resp = None
    result = None

    # multi-step function calling
    while True:
        with st.spinner("Deciding which API to call…"):
            resp = oai.responses.create(
                model="gpt-4.1",
                input=messages,
                tools=functions
            )

        # debug raw LLM output if verbosity
        raw_llm = [item.model_dump() for item in resp.output]
        if VERBOSITY > 0:
            st.write("**GPT raw response objects:**")
            st.json(raw_llm)

        # find function call
        tool_call = next(
            (item for item in resp.output if getattr(item, "type", None) == "function_call"),
            None
        )

        if VERBOSITY > 0:
            # debug expander
            with st.expander("🔍 Debug Info"):
                st.subheader("🔹 Full Message History")
                st.json(messages)
                if tool_call:
                    st.subheader("🔹 Selected Function Call")
                    st.json(tool_call.model_dump())
                    args = json.loads(tool_call.arguments)
                    st.subheader("🔹 Parsed Arguments")
                    st.json(args)
                else:
                    st.write("No function_call found")

        # if no more calls, break
        if not tool_call:
            final_resp = resp
            break

        # execute function call
        name  = tool_call.name
        args  = json.loads(tool_call.arguments)
        with st.spinner(f"Executing {name}…"):
            result = call_elgoose_api(**args)

        # append call + output to messages
        messages.append({
            "type": "function_call",
            "name": name,
            "arguments": tool_call.arguments,
            "call_id": tool_call.call_id
        })
        messages.append({
            "type": "function_call_output",
            "call_id": tool_call.call_id,
            "output": result
        })


    # render assistant response
    assistant_content = final_resp.output_text
    with st.chat_message("assistant"):
        st.markdown(assistant_content)
    st.session_state.messages.append({"role": "assistant", "content": assistant_content})

        # ── rescue: if result wasn't set by the final function_call, grab it from history ──
    if result is None:
        for msg in reversed(messages):
            if msg.get("type") == "function_call_output":
                result = msg["output"]
                break

    # ── only parse + render when we actually have a JSON string ──
    if result:
        parsed = json.loads(result)
        if "url" in parsed:
            st.markdown(f"**Source URL:** {parsed['url']}")

        import pandas as pd, itertools
        data = parsed["data"]

        # 1) Albums payload? detect by presence of 'tracks'
        if isinstance(data, list) and data and "tracks" in data[0]:
            for alb in data:
                title     = alb.get("album_title")
                date_     = alb.get("releasedate")
                album_url = alb.get("album_url")
                link      = f"https://elgoose.net{album_url}"
                header    = f"{title} ({date_})"
                with st.expander(header):
                    st.markdown(f"[View album details]({link})")
                    tracks = alb.get("tracks", [])
                    if tracks:
                        df = pd.DataFrame(tracks)
                        cols = [c for c in ["position","song_name","tracktime"] if c in df.columns]
                        st.table(df[cols])

        # # 2) Big list of shows/setlists? use generic _id grouping
        # elif isinstance(data, list) and len(data) > 10:
        #     grp_key = next((k for k in data[0].keys() if k.endswith("_id")), None)
        #     if grp_key:
        #         data = sorted(data, key=lambda r: r.get(grp_key))
        #         for group_val, items in itertools.groupby(data, key=lambda r: r.get(grp_key)):
        #             items = list(items)
        #             first = items[0]
        #             header = first.get("showdate") or str(group_val)
        #             with st.expander(f"{header} (ID {group_val})"):
        #                 showdate = first.get("showdate")
        #                 if showdate:
        #                     st.markdown(
        #                         f"[View full show on ElGoose]"
        #                         f"(https://elgoose.net/setlists/?date={showdate})"
        #                     )
        #                 df = pd.DataFrame(items)
        #                 cols = [c for c in df.columns if not c.endswith("_id")][:6]
        #                 st.table(df[cols])
        #     else:
        #         with st.expander("Full data (ungrouped)"):
        #             st.json(data)

        # 3) Small or non-list → raw JSON
        # else:
        #     st.json(data)

    else:
        st.info("No data to display for this query.")
