const tg = window.Telegram.WebApp;
tg.expand(); // Expand to full height if possible

// Backend API URL (assumes served from the same host, which normally happens via ngrok)
const API_BASE = window.location.origin;

const searchInput = document.getElementById('search-input');
const resultsContainer = document.getElementById('results-container');
const loadingIndicator = document.getElementById('loading');
const playerContainer = document.getElementById('player-container');
const audioPlayer = document.getElementById('audio-player');
const nowPlayingTitle = document.getElementById('now-playing-title');
const nowPlayingArtist = document.getElementById('now-playing-artist');
const nowPlayingThumbnail = document.getElementById('now-playing-thumbnail');

// Setup Telegram native MainButton instead of inline search button? Wait, MVP can use inline search button.
// For now let's stick to simple inline button as requested.

// Allow search on enter
function handleSearch(e) {
    if (e.key === 'Enter') {
        searchMusic();
    }
}

async function searchMusic() {
    const query = searchInput.value.trim();
    if (!query) return;

    // UI Updates
    loadingIndicator.classList.remove('hidden');
    resultsContainer.innerHTML = '';
    searchInput.blur(); // dismiss keyboard
    
    try {
        const response = await fetch(`${API_BASE}/search?q=${encodeURIComponent(query)}`);
        if (!response.ok) {
            throw new Error('Network response was not ok');
        }
        const data = await response.json();
        
        loadingIndicator.classList.add('hidden');
        renderResults(data.results);
    } catch (error) {
        console.error("Error fetching search results:", error);
        loadingIndicator.classList.add('hidden');
        resultsContainer.innerHTML = `<div style="color: var(--hint-color); text-align: center; margin-top: 20px;">Ошибка при поиске. Попробуйте снова.</div>`;
    }
}

function renderResults(results) {
    if (!results || results.length === 0) {
        resultsContainer.innerHTML = `<div style="text-align: center; color: var(--hint-color); margin-top: 20px;">Ничего не найдено</div>`;
        return;
    }

    results.forEach(track => {
        const trackElement = document.createElement('div');
        trackElement.className = 'track-item';
        
        const safeTitle = track.title || 'Unknown Title';
        const safeArtist = track.artist || 'Unknown Artist';
        const thumbnailSrc = track.thumbnail || 'data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="50" height="50" fill="%23eee"><rect width="50" height="50"/></svg>';

        trackElement.innerHTML = `
            <img class="track-thumbnail" src="${thumbnailSrc}" alt="cover" onerror="this.src='data:image/svg+xml;utf8,<svg xmlns=\\'http://www.w3.org/2000/svg\\' width=\\'50\\' height=\\'50\\' fill=\\'%23eee\\'><rect width=\\'50\\' height=\\'50\\'/></svg>'">
            <div class="track-info">
                <p class="track-title">${safeTitle}</p>
                <p class="track-artist">${safeArtist}</p>
            </div>
        `;

        trackElement.onclick = () => playTrack(track);
        resultsContainer.appendChild(trackElement);
    });
}

function playTrack(track) {
    // Show player
    playerContainer.classList.remove('hidden');
    
    // Update UI
    nowPlayingTitle.textContent = track.title || 'Unknown Title';
    nowPlayingArtist.textContent = track.artist || 'Unknown Artist';
    
    if (track.thumbnail) {
        nowPlayingThumbnail.src = track.thumbnail;
        nowPlayingThumbnail.classList.remove('hidden');
    } else {
        nowPlayingThumbnail.classList.add('hidden');
    }

    // Prepare audio stream URL
    const streamUrl = `${API_BASE}/stream?video_id=${track.id}&t=${Date.now()}`;
    
    // Start playback
    audioPlayer.src = streamUrl;
    audioPlayer.play().catch(e => {
        console.error("Playback failed:", e);
        // Autoplay might be blocked by browser policies if not initiated by direct user gesture,
        // but onclick is a user gesture so it should work smoothly.
    });

    // Notify Media Session API (System lock screen controls)
    if ('mediaSession' in navigator) {
        navigator.mediaSession.metadata = new MediaMetadata({
            title: track.title || 'Unknown Title',
            artist: track.artist || 'Unknown Artist',
            album: 'Telegram Music MVP',
            artwork: track.thumbnail ? [
                { src: track.thumbnail, sizes: '512x512', type: 'image/jpeg' }
            ] : []
        });
        
        // Telegram Mobile handles media play/pause nicely with system events mapping directly to the 
        // <audio> element via MediaSession API defaults.
    }
}
