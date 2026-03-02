from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import yt_dlp
import asyncio
import httpx

app = FastAPI(title="Telegram Music Bot MVP API")

# Allow CORS for Telegram Web Apps
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust this in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"message": "Music Bot API is running"}

async def search_youtube(query: str, limit: int = 5):
    ydl_opts = {
        'format': 'bestaudio/best',
        'noplaylist': True,
        'quiet': True,
        'extract_flat': True,
    }
    
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
    }
    def fetch():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(video_id, download=False)
            
    try:
        info = await asyncio.to_thread(fetch)
        return info.get('url')
    except Exception as e:
        print(f"Error fetching audio URL: {e}")
        return None

@app.get("/stream")
async def stream(video_id: str):
    audio_url = await get_audio_url(video_id)
    if not audio_url:
        raise HTTPException(status_code=404, detail="Audio not found")
        
    async def stream_generator():
        # Using a higher timeout for continuous streaming of media
        async with httpx.AsyncClient(timeout=30.0) as client:
            async with client.stream('GET', audio_url) as response:
                if response.status_code != 200:
                    yield b""
                    return
                async for chunk in response.aiter_bytes():
                    yield chunk

    # Return audio/mpeg headers to stream standard audio formats correctly
    return StreamingResponse(stream_generator(), media_type="audio/mpeg")

from fastapi.staticfiles import StaticFiles
import os

# Create static directory if it doesn't exist
os.makedirs("static", exist_ok=True)
# Mount the static files at the end of the file so that API routes have priority
app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    # Запускаем сервер uvicorn на порту 8000
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
