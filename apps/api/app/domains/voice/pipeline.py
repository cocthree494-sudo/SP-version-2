"""Channel-neutral voice event normalization used by real-time connectors."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class VoiceTurn:
    transcript: str
    response_text: str
    should_interrupt: bool = False


def normalize_voice_turn(
    transcript: str, response_text: str, *, interrupted: bool = False
) -> VoiceTurn:
    """Normalize STT -> agent -> TTS handoff without storing audio or secrets."""

    clean_transcript = " ".join(transcript.split())
    clean_response = " ".join(response_text.split())
    if not clean_transcript or not clean_response:
        raise ValueError("Voice turns require non-empty transcript and response")
    return VoiceTurn(clean_transcript, clean_response, interrupted)


__all__ = ["VoiceTurn", "normalize_voice_turn"]
