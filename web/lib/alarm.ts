/**
 * Frontend (web) · alarm.ts - the siren for the full-screen alert (made with the Web Audio API, no sound file).
 *
 * A two-tone "hi-lo" siren (960 Hz / 770 Hz, switching every 0.4 s) for 8 seconds, at a moderate volume.
 *
 * Browsers only allow sound after the person has clicked or tapped the page once. So:
 *   unlockSound()  is called on the first click anywhere, to make the sound ready in advance
 *   soundBlocked() tells the alarm to show a "Tap for sound" button when the browser still refuses
 * The person can switch the siren off; the choice is remembered on this device ("sz-alarm-sound").
 */
let audio: AudioContext | null = null;

function context(): AudioContext | null {
  if (typeof window === "undefined" || !("AudioContext" in window)) return null;
  audio ??= new AudioContext();
  return audio;
}

export function unlockSound(): void {
  const ctx = context();
  if (ctx && ctx.state === "suspended") ctx.resume().catch(() => {});
}

export function soundBlocked(): boolean {
  const ctx = context();
  return !ctx || ctx.state !== "running";
}

export function soundWanted(): boolean {
  try {
    return localStorage.getItem("sz-alarm-sound") !== "off";
  } catch {
    return true;
  }
}

export function setSoundWanted(on: boolean): void {
  try {
    localStorage.setItem("sz-alarm-sound", on ? "on" : "off");
  } catch { /* storage blocked: the choice lasts until the page closes */ }
}

/** Start the siren. Returns a function that stops it. */
export function startSiren(seconds = 8): () => void {
  const ctx = context();
  if (!ctx) return () => {};
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  const start = ctx.currentTime;
  osc.type = "square";
  for (let i = 0; i < seconds / 0.4; i++) osc.frequency.setValueAtTime(i % 2 ? 770 : 960, start + i * 0.4);
  gain.gain.setValueAtTime(0, start);
  gain.gain.linearRampToValueAtTime(0.08, start + 0.05); // moderate: an alarm, not a shock
  gain.gain.setValueAtTime(0.08, start + seconds - 0.3);
  gain.gain.linearRampToValueAtTime(0, start + seconds);
  osc.connect(gain).connect(ctx.destination);
  osc.start(start);
  osc.stop(start + seconds);
  return () => {
    try {
      gain.gain.cancelScheduledValues(ctx.currentTime);
      gain.gain.setValueAtTime(0, ctx.currentTime);
      osc.stop();
    } catch { /* already stopped */ }
  };
}
