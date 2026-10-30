// Read-aloud (text to speech) via the browser's built-in Web Speech API. No package, no server of ours.
//
// Privacy: some browsers' default voices are cloud-based (e.g. Chrome's "Google Deutsch" sends the text
// to Google). We prefer on-device voices (localService) and only fall back to a cloud voice if none exists.
//
// iOS Safari only allows speech that starts from a user tap. Call unlockSpeech() inside the tap handler
// (e.g. the send button) so speech triggered later, when results arrive, is allowed to play.

import { useEffect, useState } from "react";
import { getLocale, intlLocale } from "@/i18n/locale";

export function isSpeechSupported(): boolean {
  return typeof window !== "undefined" && "speechSynthesis" in window && "SpeechSynthesisUtterance" in window;
}

// A voice in the UI language (German voice for DE, English voice for EN), on-device first.
function pickVoice(): SpeechSynthesisVoice | undefined {
  const prefix = getLocale();
  const matching = window.speechSynthesis.getVoices().filter((v) => v.lang.replace("_", "-").startsWith(prefix));
  return matching.find((v) => v.localService) ?? matching[0];
}

// A voice in another language would mispronounce drug names and values, so read-aloud is only offered
// when a voice in the UI language exists. Voice lists load asynchronously in Chrome.
export function useVoiceAvailable(): boolean {
  const [available, setAvailable] = useState(() => isSpeechSupported() && pickVoice() !== undefined);

  useEffect(() => {
    if (!isSpeechSupported()) return;
    const update = () => setAvailable(pickVoice() !== undefined);
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
  utterance.lang = intlLocale();
  const voice = pickVoice();
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
