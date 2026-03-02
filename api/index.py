from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import httpx
import asyncio
import random

app = FastAPI(title="Telegram Music Bot MVP API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Public Piped API instances (используем несколько на случай недоступности одного)
PIPED_INSTANCES = [
    "https://pipedapi.kavin.rocks",
    "https://piped-api.privacy.com.de",
    "https://api.piped.yt",
    "https://pipedapi.reallyaweso.me",
]

async def get_piped_instance(client: httpx.AsyncClient) -> str:
    """Возвращает первый доступный Piped instance."""
    for instance in PIPED_INSTANCES:
        try:
            r = await client.get(f"{instance}/healthcheck", timeout=3.0)
            if r.status_code == 200:
                return instance
        except Exception:
            continue
    # Если ни один не ответил на healthcheck — берём случайный
    return random.choice(PIPED_INSTANCES)


async def search_piped(query: str, limit: int = 10) -> list:
    """Поиск треков через Piped API."""
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        instance = await get_piped_instance(client)
        try:
            resp = await client.get(
                f"{instance}/search",
                params={"q": query, "filter": "music_songs"},
            )
            resp.raise_for_status()
            data = resp.json()
            
            results = []
            for item in data.get("items", [])[:limit]:
                # Piped возвращает url вида /watch?v=VIDEO_ID
                video_url = item.get("url", "")
                video_id = video_url.split("v=")[-1] if "v=" in video_url else ""
                
                if not video_id:
                    continue

                # Длительность в секундах
                duration = item.get("duration", 0)

                results.append({
                    "id": video_id,
                    "title": item.get("title", "Unknown Title"),
                    "artist": item.get("uploaderName", "Unknown Artist"),
                    "duration": duration,
                    "thumbnail": item.get("thumbnail", ""),
                })
            return results

        except Exception as e:
            print(f"[Piped search error] instance={instance}, error={e}")
            # Пробуем другой instance
            for fallback in PIPED_INSTANCES:
                if fallback == instance:
                    continue
                try:
                    resp = await client.get(
                        f"{fallback}/search",
                        params={"q": query, "filter": "music_songs"},
                    )
                    resp.raise_for_status()
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
                            "thumbnail": item.get("thumbnail", ""),
                        })
                    return results
                except Exception as e2:
                    print(f"[Piped fallback error] instance={fallback}, error={e2}")
                    continue
            return []


async def get_audio_url_piped(video_id: str) -> str | None:
    """Получаем прямую ссылку на аудио через Piped API."""
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        instance = await get_piped_instance(client)
        
        for attempt_instance in [instance] + [i for i in PIPED_INSTANCES if i != instance]:
            try:
                resp = await client.get(f"{attempt_instance}/streams/{video_id}")
                resp.raise_for_status()
                data = resp.json()
                
                audio_streams = data.get("audioStreams", [])
                if not audio_streams:
                    continue

                # Выбираем лучший аудио поток (сортируем по битрейту)
                audio_streams_sorted = sorted(
                    audio_streams,
                    key=lambda s: s.get("bitrate", 0),
                    reverse=True
                )
                
                best = audio_streams_sorted[0]
                return best.get("url")

            except Exception as e:
                print(f"[Piped streams error] instance={attempt_instance}, video={video_id}, error={e}")
                continue

    return None


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.get("/api/search")
@app.get("/search")
async def search(q: str = Query(..., min_length=1)):
    try:
        results = await search_piped(q)
        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/stream")
@app.get("/stream")
async def stream(video_id: str, request: Request):
    audio_url = await get_audio_url_piped(video_id)
    
    if not audio_url:
        raise HTTPException(status_code=404, detail="Audio stream not found")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://www.youtube.com/",
        "Origin": "https://www.youtube.com",
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
    return {"status": "ok"}
