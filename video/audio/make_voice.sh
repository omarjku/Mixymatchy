#!/usr/bin/env bash
# Voice-over for the Second Eye video, aligned to video/audio/captions.srt.
# macOS only (uses the built-in `say`, voice Samantha, fallback Daniel).
#
#   video/audio/make_voice.sh            # -> video/out/audio/voice.wav, then mixes it
#   VOICE=Daniel RATE=160 video/audio/make_voice.sh
#   NO_MIX=1 video/audio/make_voice.sh   # only write voice.wav
#
# On Linux/CI, `python3 -m video.audio.voice --fake` writes a placeholder voice
# so the ducking path can still be tested.
set -euo pipefail
cd "$(dirname "$0")/../.."

if ! command -v say >/dev/null 2>&1; then
  echo "error: 'say' not found. Run this on macOS (or use: python3 -m video.audio.voice --fake)" >&2
  exit 1
fi
command -v ffmpeg >/dev/null 2>&1 || { echo "error: ffmpeg not found (brew install ffmpeg)" >&2; exit 1; }

VOICES="${VOICE:-Samantha},Daniel"
RATE="${RATE:-165}"

python3 -m video.audio.voice --voices "$VOICES" --rate "$RATE"

if [[ -z "${NO_MIX:-}" ]]; then
  python3 -m video.audio.build --with-voice
fi
