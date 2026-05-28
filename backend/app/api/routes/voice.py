"""Server-side TTS — neural voice via Microsoft Edge TTS (free, no API key).

Why: browser SpeechSynthesis on some machines (notably some macOS setups) silently
accepts utterances but produces no audio. Streaming MP3 from a server through a
standard <audio> element bypasses the local speech daemon entirely.
"""
from __future__ import annotations

import edge_tts
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

router = APIRouter()

# Default neural voice — natural, warm, multilingual-capable.
DEFAULT_VOICE = "en-US-AvaMultilingualNeural"
# Safety cap: ~12s of speech is plenty for a summary; the full body still streams
# but in reasonable chunks.
MAX_CHARS = 4000


@router.get("/speak")
async def speak(
    text: str = Query(..., min_length=1),
    voice: str = Query(DEFAULT_VOICE),
    rate: str = Query("+0%"),
) -> StreamingResponse:
    """Stream MP3 audio for the given text."""
    if not text.strip():
        raise HTTPException(status_code=400, detail="text is empty")
    snippet = text[:MAX_CHARS]

    async def gen():
        try:
            comm = edge_tts.Communicate(snippet, voice, rate=rate)
            async for chunk in comm.stream():
                if chunk.get("type") == "audio":
                    yield chunk["data"]
        except Exception as exc:  # noqa: BLE001
            # Stream will close — the <audio> element will surface an error event.
            raise HTTPException(status_code=502, detail=f"TTS failed: {exc}") from exc

    return StreamingResponse(
        gen(),
        media_type="audio/mpeg",
        headers={"Cache-Control": "no-store"},
    )
