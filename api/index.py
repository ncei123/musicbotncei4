from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pytubefix import YouTube, Search
import asyncio
import httpx
import os

app = FastAPI(title="Telegram Music Bot MVP API")

# Allow CORS for Telegram Web Apps
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

async def search_youtube(query: str, limit: int = 5):
    def fetch():
        s = Search(query)
        results = []
        for v in s.videos[:limit]:
            results.append({
                "id": v.video_id,
                "title": v.title,
                "artist": v.author,
                "duration": v.length,
                "thumbnail": v.thumbnail_url
            })
        return results
            
    try:
        results = await asyncio.to_thread(fetch)
        return results
    except Exception as e:
        print(f"Error searching: {e}")
        return []

@app.get("/api/search")
@app.get("/search")
async def search(q: str = Query(..., min_length=1)):
    try:
        results = await search_youtube(q)
        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def get_audio_url(video_id: str):
    def fetch():
        yt = YouTube(f"https://www.youtube.com/watch?v={video_id}")
        # Get the best audio stream
        stream = yt.streams.filter(only_audio=True).order_by('abr').desc().first()
        if not stream:
            stream = yt.streams.filter(only_audio=True).first()
        return stream.url if stream else None
            
    try:
        url = await asyncio.to_thread(fetch)
        return url
    except Exception as e:
        print(f"Error fetching audio URL via pytubefix: {e}")
        return None

@app.get("/api/stream")
@app.get("/stream")
async def stream(video_id: str, request: Request):
    audio_url = await get_audio_url(video_id)
    if not audio_url:
        raise HTTPException(status_code=404, detail="Audio not found")
        
    client = httpx.AsyncClient(timeout=30.0, follow_redirects=True)
    
    headers = {
        "User-Agent": request.headers.get("user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"),
    }
    if "range" in request.headers:
        headers["Range"] = request.headers["range"]

    req = client.build_request("GET", audio_url, headers=headers)
    response = await client.send(req, stream=True)

    if response.status_code >= 400:
        await response.aclose()
        await client.aclose()
        raise HTTPException(status_code=response.status_code, detail="Error fetching from YouTube")

    async def stream_generator():
        try:
            async for chunk in response.aiter_bytes(chunk_size=8192):
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
        media_type=resp_headers.get("Content-Type", "audio/mpeg")
    )

@app.get("/api/health")
async def health():
    return {"status": "ok"}
