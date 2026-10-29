// Read-aloud (text to speech) via the browser's built-in Web Speech API. No package, no server of ours.
//
// Privacy: some browsers' default voices are cloud-based (e.g. Chrome's "Google Deutsch" sends the text
// to Google). We prefer on-device voices (localService) and only fall back to a cloud voice if none exists.
//
// iOS Safari only allows speech that starts from a user tap. Call unlockSpeech() inside the tap handler
// (e.g. the send button) so speech triggered later, when results arrive, is allowed to play.

import { useEffect, useState } from "react";

const LANG = "de-DE";

export function isSpeechSupported(): boolean {
  return typeof window !== "undefined" && "speechSynthesis" in window && "SpeechSynthesisUtterance" in window;
}

function pickGermanVoice(): SpeechSynthesisVoice | undefined {
  const german = window.speechSynthesis.getVoices().filter((v) => v.lang.replace("_", "-").startsWith("de"));
  return german.find((v) => v.localService) ?? german[0];
}

// A non-German voice would mispronounce drug names and values, so read-aloud is only offered when a
// German voice exists. Voice lists load asynchronously in Chrome; this reports once they arrive.
export function useGermanVoiceAvailable(): boolean {
  const [available, setAvailable] = useState(() => isSpeechSupported() && pickGermanVoice() !== undefined);

  useEffect(() => {
    if (!isSpeechSupported()) return;
    const update = () => setAvailable(pickGermanVoice() !== undefined);
    update();
    window.speechSynthesis.addEventListener("voiceschanged", update);
    return () => window.speechSynthesis.removeEventListener("voiceschanged", update);
  }, []);

  return available;
}

export function unlockSpeech(): void {
  if (!isSpeechSupported()) return;
  const silent = new SpeechSynthesisUtterance(" ");
  silent.volume = 0;
  window.speechSynthesis.speak(silent);
}

// onStart/onEnd fire when audio really starts and stops (onEnd also on error or cancel).
export function speak(text: string, events: { onStart?: () => void; onEnd?: () => void } = {}): void {
  if (!isSpeechSupported() || !text.trim()) return;
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = LANG;
  const voice = pickGermanVoice();
  if (voice) utterance.voice = voice;
  if (events.onStart) utterance.onstart = events.onStart;
  if (events.onEnd) {
    utterance.onend = events.onEnd;
    utterance.onerror = events.onEnd;
  }
  window.speechSynthesis.speak(utterance);
}

export function stopSpeaking(): void {
  if (isSpeechSupported()) window.speechSynthesis.cancel();
}
