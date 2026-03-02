from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
import httpx
import asyncio
import random

app = FastAPI(title="Telegram Music Bot MVP API (Robust Fallbacks + Redirect)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

INVIDIOUS_INSTANCES = [
    "https://invidious.private.coffee",
    "https://invidious.fdn.fr",
    "https://invidious.perennialte.ch",
    "https://invidious.nerdvpn.de",
    "https://invidious.privacyredirect.com",
    "https://iv.melmac.space",
    "https://vid.priv.au",
    "https://inv.tux.pizza"
]

PIPED_INSTANCES = [
    "https://pipedapi.kavin.rocks",
    "https://piped-api.privacy.com.de",
    "https://api.piped.yt",
]

async def search_invidious(client: httpx.AsyncClient, query: str, limit: int = 10) -> list:
    instances = list(INVIDIOUS_INSTANCES)
    random.shuffle(instances)
    for instance in instances:
        try:
            resp = await client.get(
                f"{instance}/api/v1/search",
                params={"q": query, "type": "video"},
                timeout=5.0
            )
            if resp.status_code == 200:
                data = resp.json()
                results = []
                for item in data[:limit]:
                    video_id = item.get("videoId")
                    if not video_id:
                        continue
                        
                    # Fix thumbnail url if it is relative
                    thumbnail = item.get("videoThumbnails", [{}])[-1].get("url", "")
                    if thumbnail and thumbnail.startswith("/"):
                        thumbnail = f"{instance}{thumbnail}"
                        
                    results.append({
                        "id": video_id,
                        "title": item.get("title", "Unknown Title"),
                        "artist": item.get("author", "Unknown Artist"),
                        "duration": item.get("lengthSeconds", 0),
                        "thumbnail": thumbnail
                    })
                if results:
                    return results
        except Exception as e:
            print(f"[Invidious Search Error] {instance} - {e}")
            continue
    return []

async def search_piped(client: httpx.AsyncClient, query: str, limit: int = 10) -> list:
    instances = list(PIPED_INSTANCES)
    random.shuffle(instances)
    for instance in instances:
        try:
            resp = await client.get(
                f"{instance}/search",
                params={"q": query, "filter": "music_songs"},
                timeout=5.0
            )
            if resp.status_code == 200:
                data = resp.json()
                results = []
                for item in data.get("items", [])[:limit]:
                    video_url = item.get("url", "")
                    video_id = video_url.split("v=")[-1] if "v=" in video_url else ""
                    if not video_id:
                        continue
                    results.append({
                        "id": video_id,
                        "title": item.get("title", "Unknown Title"),
                        "artist": item.get("uploaderName", "Unknown Artist"),
                        "duration": item.get("duration", 0),
                        "thumbnail": item.get("thumbnail", "")
                    })
                if results:
                    return results
        except Exception as e:
            print(f"[Piped Search Error] {instance} - {e}")
            continue
    return []

# --- Streaming Fallbacks ---

async def get_stream_piped(client: httpx.AsyncClient, video_id: str) -> str | None:
    """Gets audio stream URL using Piped API (usually provides robust proxy streams)."""
    instances = list(PIPED_INSTANCES)
    random.shuffle(instances)
    for instance in instances:
        try:
            resp = await client.get(f"{instance}/streams/{video_id}", timeout=5.0)
            if resp.status_code == 200:
                data = resp.json()
                audio_streams = data.get("audioStreams", [])
                if audio_streams:
                    best = sorted(audio_streams, key=lambda s: s.get("bitrate", 0), reverse=True)[0]
                    return best.get("url")
        except Exception as e:
            print(f"[Piped Stream Error] {instance} - {e}")
            continue
    return None

async def get_stream_cobalt(client: httpx.AsyncClient, video_id: str) -> str | None:
    """Gets audio stream URL using Cobalt API (High quality direct downloads)."""
    instances = ["https://co.wuk.sh/api/json", "https://api.cobalt.tools/api/json"]
    for url in instances:
        try:
            resp = await client.post(
                url,
                json={"url": f"https://www.youtube.com/watch?v={video_id}", "isAudioOnly": True},
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                },
                timeout=5.0
            )
            if resp.status_code == 200:
                data = resp.json()
                if "url" in data:
                    return data["url"]
        except Exception as e:
            print(f"[Cobalt Stream Error] {url} - {e}")
            continue
    return None

async def get_stream_invidious(client: httpx.AsyncClient, video_id: str) -> str | None:
    """Gets audio stream URL using Invidious API."""
    instances = list(INVIDIOUS_INSTANCES)
    random.shuffle(instances)
    for instance in instances:
        try:
            resp = await client.get(f"{instance}/api/v1/videos/{video_id}", timeout=5.0)
            if resp.status_code == 200:
                data = resp.json()
                streams = data.get("adaptiveFormats", []) + data.get("formatStreams", [])
                audio_streams = [s for s in streams if "audio" in s.get("type", "").lower()]
                if audio_streams:
                    best = sorted(audio_streams, key=lambda s: int(s.get("bitrate", 0) or 0), reverse=True)[0]
                    url = best.get("url")
                    if url and url.startswith("/"):
                        url = f"{instance}{url}"
                    return url
        except Exception as e:
            print(f"[Invidious Stream Error] {instance} - {e}")
            continue
    return None

# ─── Routes ───────────────────────────────────────────────────────────────────

@app.get("/api/search")
@app.get("/search")
async def search_endpoint(q: str = Query(..., min_length=1)):
    async with httpx.AsyncClient(follow_redirects=True) as client:
        # 1. Try Invidious First
        results = await search_invidious(client, q)
        if not results:
            # 2. Try Piped if Invidious is completely blocked
            results = await search_piped(client, q)
            
        if not results:
            raise HTTPException(status_code=404, detail="No results found across all providers")
            
        return {"results": results}

@app.get("/api/stream")
@app.get("/stream")
async def stream_endpoint(video_id: str):
    # Вместо того чтобы проксировать поток через Vercel API (которое может отвалиться по таймауту через 10 сек)
    # мы получаем прямую ссылку и делаем 302 Redirect. 
    # Браузер (и Telegram) сам перейдет по ссылке и начнет скачивать трек напрямую с Invidious/Cobalt сервера.
    async with httpx.AsyncClient(follow_redirects=True) as client:
        
        url = await get_stream_piped(client, video_id)
        if url: return RedirectResponse(url=url, status_code=302)
        
        url = await get_stream_cobalt(client, video_id)
        if url: return RedirectResponse(url=url, status_code=302)
        
        url = await get_stream_invidious(client, video_id)
        if url: return RedirectResponse(url=url, status_code=302)
        
        raise HTTPException(status_code=404, detail="Could not find an available audio stream")

@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "3.0 (Multi-Fallback & Redirects)"}
