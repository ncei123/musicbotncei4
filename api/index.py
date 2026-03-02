from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
import yt_dlp
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
    ydl_opts = {
        'format': 'bestaudio/best',
        'noplaylist': True,
        'quiet': True,
        'extract_flat': True,
        'extractor_args': {'youtube': ['player_client=mweb,android,ios']},
    }
    proxy = os.environ.get("YOUTUBE_PROXY", "http://77W4fK:GXZ13y@196.18.13.81:8000")
    if proxy:
        ydl_opts['proxy'] = proxy
    
    def fetch():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(f"ytsearch{limit}:{query}", download=False)
            
    info = await asyncio.to_thread(fetch)
    
    results = []
    if 'entries' in info:
        for entry in info['entries']:
            thumbnail = entry.get("thumbnail")
            if not thumbnail and entry.get("thumbnails"):
                thumbnail = entry["thumbnails"][0].get("url")
                
            results.append({
                "id": entry.get("id"),
                "title": entry.get("title"),
                "artist": entry.get("uploader", "Unknown Artist"),
                "duration": entry.get("duration", 0),
                "thumbnail": thumbnail,
            })
    return results

@app.get("/api/search")
@app.get("/search")
async def search(q: str = Query(..., min_length=1)):
    try:
        results = await search_youtube(q)
        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def get_audio_url(video_id: str):
    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': True,
        'noplaylist': True,
        'extractor_args': {'youtube': ['player_client=mweb,android,ios']},
    }
    proxy = os.environ.get("YOUTUBE_PROXY", "http://77W4fK:GXZ13y@196.18.13.81:8000")
    if proxy:
        ydl_opts['proxy'] = proxy
    def fetch():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
            
    try:
        info = await asyncio.to_thread(fetch)
        return info.get('url')
    except Exception as e:
        print(f"Error fetching audio URL: {e}")
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
