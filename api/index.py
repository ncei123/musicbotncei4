from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import httpx
import asyncio
import random

app = FastAPI(title="Telegram Music Bot MVP API (Invidious)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

INVIDIOUS_INSTANCES = [
    "https://inv.tux.pizza",
    "https://invidious.private.coffee",
    "https://invidious.fdn.fr",
    "https://invidious.perennialte.ch",
    "https://invidious.nerdvpn.de",
    "https://invidious.jing.rocks",
    "https://vid.priv.au",
    "https://invidious.privacyredirect.com",
    "https://iv.melmac.space"
]

async def search_invidious(query: str, limit: int = 10) -> list:
    """Поиск треков через Invidious API с перебором инстансов."""
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        instances = list(INVIDIOUS_INSTANCES)
        random.shuffle(instances)
        
        for instance in instances:
            try:
                resp = await client.get(
                    f"{instance}/api/v1/search",
                    params={"q": query, "type": "video"},
                )
                resp.raise_for_status()
                data = resp.json()
                
                results = []
                for item in data[:limit]:
                    video_id = item.get("videoId")
                    if not video_id:
                        continue

                    duration = item.get("lengthSeconds", 0)
                    thumbnails = item.get("videoThumbnails", [])
                    thumbnail_url = thumbnails[-1]["url"] if thumbnails else ""
                    
                    if thumbnail_url and thumbnail_url.startswith("/"):
                        thumbnail_url = f"{instance}{thumbnail_url}"

                    results.append({
                        "id": video_id,
                        "title": item.get("title", "Unknown Title"),
                        "artist": item.get("author", "Unknown Artist"),
                        "duration": duration,
                        "thumbnail": thumbnail_url,
                    })
                
                if results:
                    return results
                    
            except Exception as e:
                print(f"[Invidious search error] instance={instance}, error={e}")
                continue
        
        return []

async def get_audio_url_invidious(video_id: str) -> str | None:
    """Получаем прямую ссылку на аудио через Invidious API."""
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        instances = list(INVIDIOUS_INSTANCES)
        random.shuffle(instances)
        
        for instance in instances:
            try:
                resp = await client.get(f"{instance}/api/v1/videos/{video_id}")
                resp.raise_for_status()
                data = resp.json()
                
                adaptive_formats = data.get("adaptiveFormats", [])
                format_streams = data.get("formatStreams", [])
                
                all_formats = adaptive_formats + format_streams
                
                audio_streams = [f for f in all_formats if "audio" in f.get("type", "").lower()]
                if not audio_streams:
                    continue

                def get_bitrate(s):
                    try:
                        return int(s.get("bitrate", 0))
                    except (ValueError, TypeError):
                        return 0

                # Выбираем лучший аудио поток
                audio_streams_sorted = sorted(
                    audio_streams,
                    key=get_bitrate,
                    reverse=True
                )
                
                best = audio_streams_sorted[0]
                url = best.get("url")
                
                if url and url.startswith("/"):
                    url = f"{instance}{url}"
                    
                return url

            except Exception as e:
                print(f"[Invidious streams error] instance={instance}, video={video_id}, error={e}")
                continue

    return None


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.get("/api/search")
@app.get("/search")
async def search(q: str = Query(..., min_length=1)):
    try:
        results = await search_invidious(q)
        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/stream")
@app.get("/stream")
async def stream(video_id: str, request: Request):
    audio_url = await get_audio_url_invidious(video_id)
    
    if not audio_url:
        raise HTTPException(status_code=404, detail="Audio stream not found")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }
    if "range" in request.headers:
        headers["Range"] = request.headers["range"]

    client = httpx.AsyncClient(timeout=30.0, follow_redirects=True)
    req = client.build_request("GET", audio_url, headers=headers)
    response = await client.send(req, stream=True)

    if response.status_code >= 400:
        await response.aclose()
        await client.aclose()
        raise HTTPException(status_code=response.status_code, detail="Error fetching audio")

    async def stream_generator():
        try:
            async for chunk in response.aiter_bytes(chunk_size=16384):
                yield chunk
        finally:
            await response.aclose()
            await client.aclose()

    resp_headers = {}
    for k, v in response.headers.items():
        if k.lower() in ("content-type", "content-length", "content-range", "accept-ranges"):
            resp_headers[k] = v

    return StreamingResponse(
        stream_generator(),
        status_code=response.status_code,
        headers=resp_headers,
        media_type=resp_headers.get("content-type", "audio/webm"),
    )

@app.get("/api/health")
async def health():
    return {"status": "ok", "provider": "invidious"}
