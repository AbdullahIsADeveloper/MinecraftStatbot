from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
import aiohttp
import json

app = FastAPI(title="Minecraft Stats API")

# ----------------------------
# GLOBAL SESSION
# ----------------------------
session = None


@app.on_event("startup")
async def startup():
    global session
    session = aiohttp.ClientSession()


@app.on_event("shutdown")
async def shutdown():
    await session.close()


# ----------------------------
# SERVER REGISTRY (SCALABLE)
# ----------------------------
SERVERS = {}


# ----------------------------
# BEAUTIFICATION HELPER
# ----------------------------
def build_embed(username: str, data: dict) -> str:
    ratings = data.get("ratings", {})

    lines = []

    # BIG HEADER
    lines.append(f"# 🏆 {username.title()}")
    lines.append("-# CatPVP Ranked Statistics")
    lines.append("")

    global_rating = data.get("global")

    if global_rating is not None:
        lines.append(f"> 🌍 **Global Rating:** `{global_rating}`")
        lines.append("")

    # rank emoji mapping
    rank_emojis = {
        "Copper": "🟫",
        "Iron": "⬜",
        "Gold": "🟨",
        "Emerald": "🟩",
        "Diamond": "🟦",
        "Master": "🟪",
        "Grandmaster": "🟥"
    }

    # sort by highest rating first
    sorted_ratings = sorted(
        ratings.items(),
        key=lambda x: x[1].get("rating", 0),
        reverse=True
    )

    for gm, v in sorted_ratings:
        gm_name = gm.replace("_", " ").title()

        rating = v.get("rating", "N/A")
        rank = v.get("rank", "N/A")

        tier = rank.split(" ")[0]
        emoji = rank_emojis.get(tier, "⬛")

        lines.append(f"## {emoji} {gm_name}")
        lines.append(f"> Rating: `{rating}`")
        lines.append(f"> Rank: **{rank}**")
        lines.append("")

    result = "\n".join(lines).strip()

    # Discord hard limit
    if len(result) > 1900:
        result = result[:1900] + "\n..."

    return result


# ----------------------------
# ROOT (UPTIMEROBOT)
# ----------------------------
@app.get("/")
async def root():
    return {
        "status": "online",
        "message": "Minecraft Stats API is running"
    }


# ----------------------------
# CATPVP PROVIDER
# ----------------------------
async def fetch_catpvp(username: str):
    url = f"https://catpvp.xyz/player/{username}?_rsc=1cc12"

    async with session.get(url) as r:
        text = await r.text()

    marker = '\\"ranked\\":{\\"ratings\\":'
    start = text.find(marker)

    if start == -1:
        return None

    start = text.find("{", start)

    brace_count = 0
    end = start

    for i in range(start, len(text)):
        if text[i] == "{":
            brace_count += 1
        elif text[i] == "}":
            brace_count -= 1

            if brace_count == 0:
                end = i + 1
                break

    ranked_json = text[start:end]
    ranked_json = ranked_json.replace('\\"', '"')

    data = json.loads(ranked_json)

    ratings = data.get("ratings", {})

    cleaned = {
        gm: {
            "rating": v["rating"],
            "rank": v["rank"],
            "rankColor": v["rankColor"],
            "rankSecondary": v.get("rankSecondary")
        }
        for gm, v in ratings.items()
    }

    return {
        "global": data.get("global"),
        "ratings": cleaned
    }


# ----------------------------
# REGISTER SERVERS
# ----------------------------
SERVERS["catpvp"] = fetch_catpvp


# ----------------------------
# MAIN ENDPOINT
# ----------------------------
@app.get("/stats")
async def get_stats(
    username: str,
    server: str = "catpvp",
    beautified: bool = False
):
    server = server.lower()

    if server not in SERVERS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported server. Available: {list(SERVERS.keys())}"
        )

    data = await SERVERS[server](username)

    if not data:
        raise HTTPException(
            status_code=404,
            detail="Player not found or data unavailable"
        )

    if beautified:
        embed = build_embed(username, data)

        return PlainTextResponse(content=embed)

    return {
        "username": username,
        "server": server,
        **data
    }