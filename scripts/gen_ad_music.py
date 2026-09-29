"""Procedurally generate futuristic electronic music for the AI Automation ad."""
from __future__ import annotations

import hashlib
import json
import math
import struct
import wave
from pathlib import Path

OUT = Path("C:/Workspace/super-creator-os/scos/work/ai-auto-ad-c1b9427f/audio")
OUT.mkdir(parents=True, exist_ok=True)

SAMPLE_RATE = 44100
DURATION = 22.0  # Slightly longer than 20s video for trim flexibility
BPM = 128
BEAT_DUR = 60.0 / BPM

def sine(freq, dur, sr=SAMPLE_RATE):
    """Generate sine wave samples."""
    n = int(dur * sr)
    return [0.5 * math.sin(2 * math.pi * freq * t / sr) for t in range(n)]

def saw(freq, dur, sr=SAMPLE_RATE):
    """Generate sawtooth wave samples."""
    n = int(dur * sr)
    p = sr / freq
    return [2.0 * ((t % p) / p) - 1.0 for t in range(n)]

def square(freq, dur, duty=0.5, sr=SAMPLE_RATE):
    """Generate square wave samples."""
    n = int(dur * sr)
    p = sr / freq
    return [1.0 if (t % p) / p < duty else -1.0 for t in range(n)]

def noise(dur, sr=SAMPLE_RATE):
    """Generate white noise."""
    import random
    n = int(dur * sr)
    return [random.uniform(-1, 1) for _ in range(n)]

def fade_in(samples, dur, sr=SAMPLE_RATE):
    """Apply linear fade in."""
    n = int(dur * sr)
    for i in range(min(n, len(samples))):
        samples[i] *= i / max(1, n)
    return samples

def fade_out(samples, dur, sr=SAMPLE_RATE):
    """Apply linear fade out."""
    n = int(dur * sr)
    total = len(samples)
    for i in range(min(n, total)):
        samples[total - 1 - i] *= i / max(1, n)
    return samples

def adsr(attack, decay, sustain, release, peak=1.0):
    """Generate ADSR envelope."""
    env = []
    a_n = int(attack * SAMPLE_RATE)
    d_n = int(decay * SAMPLE_RATE)
    r_n = int(release * SAMPLE_RATE)
    for i in range(a_n):
        env.append(peak * i / max(1, a_n))
    for i in range(d_n):
        env.append(peak - (peak - sustain) * i / max(1, d_n))
    # sustain held indefinitely (return sustain level)
    env.append(sustain)
    for i in range(r_n):
        env.append(sustain * (1 - i / max(1, r_n)))
    return env

def apply_env(samples, env):
    """Apply envelope to samples."""
    result = []
    for i, s in enumerate(samples):
        if i < len(env):
            result.append(s * env[i])
        else:
            result.append(s * env[-1] if env else 0)
    return result

def mix(target, source, offset=0, gain=1.0):
    """Mix source into target at offset with gain."""
    for i, s in enumerate(source):
        idx = offset + i
        if idx < len(target):
            target[idx] += s * gain

def clamp(samples):
    """Soft-clip samples to [-1, 1]."""
    result = []
    for s in samples:
        # Soft clipping
        if s > 1.0:
            s = 1.0
        elif s < -1.0:
            s = -1.0
        result.append(s)
    return result

def lowpass(samples, cutoff=0.5):
    """Simple low-pass filter."""
    result = []
    prev = 0.0
    alpha = cutoff
    for s in samples:
        prev = prev + alpha * (s - prev)
        result.append(prev)
    return result

def highpass(samples, cutoff=0.1):
    """Simple high-pass filter."""
    result = []
    prev_in = 0.0
    prev_out = 0.0
    alpha = cutoff
    for s in samples:
        out = alpha * (prev_out + s - prev_in)
        result.append(out)
        prev_in = s
        prev_out = out
    return result

def write_wav(path, samples, sr=SAMPLE_RATE):
    """Write 16-bit mono WAV."""
    path.parent.mkdir(parents=True, exist_ok=True)
    n = len(samples)
    with wave.open(str(path), 'w') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        frames = bytearray()
        for s in samples:
            val = int(max(-1.0, min(1.0, s)) * 32767)
            frames.extend(struct.pack('<h', val))
        w.writeframes(bytes(frames))
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    return sha

# ============================================================
# BUILD THE TRACK
# ============================================================

total_samples = int(DURATION * SAMPLE_RATE)
mix_bus = [0.0] * total_samples

# --- Layer 1: Sub bass (sine root note at C2 = 65.41 Hz) -------
# Pulsing sub bass on every beat
bass_freq = 65.41  # C2
for beat in range(int(DURATION / BEAT_DUR)):
    start = int(beat * BEAT_DUR * SAMPLE_RATE)
    dur = BEAT_DUR * 0.8
    bass = sine(bass_freq, dur)
    env = adsr(0.01, 0.05, 0.7, 0.2)
    bass = apply_env(bass, env)
    bass = [s * 0.3 for s in bass]
    mix(mix_bus, bass, start)

# --- Layer 2: Pad chord (detuned saws - Cmadd9 = C-Eb-G-D) ----
# Chord notes: C3(130.81), Eb3(155.56), G3(196.00), D4(293.66)
pad_notes = [130.81, 155.56, 196.00, 293.66]
chord_change_interval = 4  # Change chord every 4 beats
chord_progressions = [
    [130.81, 155.56, 196.00, 293.66],  # Cmadd9
    [123.47, 146.83, 185.00, 277.18],  # Bbmaj9
    [110.00, 138.59, 164.81, 261.63],  # Am9
    [116.54, 146.83, 174.61, 246.94],  # Bbadd9
]

chord_idx = 0
beat_count = 0
notes = chord_progressions[0]
for t_ms in range(0, int(DURATION * 1000), int(BEAT_DUR * 1000)):
    if beat_count % chord_change_interval == 0:
        notes = chord_progressions[chord_idx % len(chord_progressions)]
        chord_idx += 1
    start = int(t_ms / 1000 * SAMPLE_RATE)
    dur = BEAT_DUR * chord_change_interval
    for note in notes:
        osc1 = saw(note, dur)
        osc2 = saw(note * 1.005, dur)  # Slight detune
        combined = [(a + b) / 2 * 0.15 for a, b in zip(osc1, osc2)]
        combined = lowpass(combined, 0.3)
        env = adsr(0.1, 0.2, 0.6, 0.3)
        combined = apply_env(combined, env)
        mix(mix_bus, combined, start)
    beat_count += 1

# --- Layer 3: Arpeggiated pluck (D4, G3, Eb3, C3 repeating) ----
arp_notes = [293.66, 196.00, 155.56, 130.81]
arp_speed = BEAT_DUR / 2  # 8th notes
for i in range(int(DURATION / arp_speed)):
    note = arp_notes[i % len(arp_notes)]
    start = int(i * arp_speed * SAMPLE_RATE)
    dur = arp_speed * 0.7
    pluck = saw(note, dur)
    pluck = [s * 0.8 for s in pluck]
    env = adsr(0.005, 0.05, 0.3, 0.1)
    pluck = apply_env(pluck, env)
    pluck = lowpass(pluck, 0.15)
    mix(mix_bus, pluck, start, gain=0.25)

# --- Layer 4: Kick drum (sine sweep + click) on every 2 beats ---
kick_interval = 2  # Every 2 beats
for i in range(int(DURATION / (BEAT_DUR * kick_interval))):
    start = int(i * kick_interval * BEAT_DUR * SAMPLE_RATE)
    dur = 0.15
    n = int(dur * SAMPLE_RATE)
    # Frequency sweep from 150Hz to 50Hz
    kick = []
    for s in range(n):
        phase = s / SAMPLE_RATE
        freq = 150 - 100 * (phase / dur)
        kick.append(0.8 * math.sin(2 * math.pi * freq * phase))
    # Click transient
    click = noise(0.01)
    click = highpass(click, 0.5)
    click = [c * 0.3 for c in click]
    kick[:len(click)] = [k + c for k, c in zip(kick[:len(click)], click)]
    env = adsr(0.001, 0.05, 0.0, 0.1)
    kick = apply_env(kick, env)
    mix(mix_bus, kick, start)

# --- Layer 5: Hi-hat (filtered noise) on every beat -------------
for i in range(int(DURATION / BEAT_DUR)):
    start = int(i * BEAT_DUR * SAMPLE_RATE)
    if i % 2 == 1:
        # Off-beat hi-hat
        dur = 0.05
        hh = noise(dur)
        hh = highpass(hh, 0.7)
        env = adsr(0.001, 0.02, 0.0, 0.03)
        hh = apply_env(hh, env)
        mix(mix_bus, hh, start, gain=0.2)

# --- Layer 6: Snare/clap (noise burst) on 4th beat of each bar ---
snare_interval = 4
for i in range(int(DURATION / (BEAT_DUR * snare_interval))):
    start = int(i * snare_interval * BEAT_DUR * SAMPLE_RATE + BEAT_DUR * 2 * SAMPLE_RATE)  # Beat 3
    dur = 0.2
    snare = noise(dur)
    snare = highpass(snare, 0.3)
    env = adsr(0.001, 0.1, 0.0, 0.15)
    snare = apply_env(snare, env)
    mix(mix_bus, snare, start, gain=0.35)

# --- Layer 7: Riser (noise sweep up) at 8s and 16s --------------
for riser_time in [6.5, 14.0]:
    dur = 1.5
    riser = noise(dur)
    # Frequency sweep (filter opens up)
    filtered = []
    prev = 0.0
    for i, s in enumerate(riser):
        t = i / len(riser)
        alpha = 0.05 + 0.6 * t  # Increasing cutoff
        prev = prev + alpha * (s - prev)
        filtered.append(prev)
    env = adsr(0.1, 0.2, 0.8, 0.3)
    filtered = apply_env(filtered, env)
    start = int(riser_time * SAMPLE_RATE)
    mix(mix_bus, filtered, start, gain=0.3)

# --- Layer 8: Impact hit at build points -------------------------
for impact_time in [4.0, 8.0, 12.0, 16.0]:
    dur = 0.3
    n = int(dur * SAMPLE_RATE)
    impact = []
    for s in range(n):
        phase = s / SAMPLE_RATE
        freq = 80 - 60 * (phase / dur)
        impact.append(math.sin(2 * math.pi * freq * phase))
    # Add noise transient
    imp_noise = noise(0.02)
    impact[:len(imp_noise)] = [i + n for i, n in zip(impact[:len(imp_noise)], imp_noise)]
    env = adsr(0.001, 0.15, 0.0, 0.15)
    impact = apply_env(impact, env)
    start = int(impact_time * SAMPLE_RATE)
    mix(mix_bus, impact, start, gain=0.5)

# ============================================================
# FINALIZE
# ============================================================

# Normalize
max_amp = max(abs(s) for s in mix_bus) if mix_bus else 1
if max_amp > 0:
    mix_bus = [s / max_amp * 0.85 for s in mix_bus]

# Fade in/out
mix_bus = fade_in(mix_bus, 0.5)
mix_bus = fade_out(mix_bus, 1.0)

# Write output
path = OUT / "music_futuristic_main.wav"
sha = write_wav(path, mix_bus)
print(f"Music: {path}")
print(f"SHA256: {sha}")
print(f"Duration: {DURATION}s | Size: {path.stat().st_size / 1024:.1f} KB")

# Write manifest
manifest = {
    "filename": "music_futuristic_main.wav",
    "source": "Procedural Generation (Python synthesis)",
    "license": "CC0 (original work - no copyright)",
    "sha256": sha,
    "size_bytes": path.stat().st_size,
    "duration_s": DURATION,
    "bpm": BPM,
    "layers": [
        "Sub bass (sine, C2, every beat)",
        "Pad chord (detuned saw, Cmadd9 progression)",
        "Arpeggiated pluck (saw, 8th notes)",
        "Kick drum (sine sweep + click, every 2 beats)",
        "Hi-hat (filtered noise, off-beats)",
        "Snare/clap (noise burst, beat 3)",
        "Riser (noise sweep up, at 6.5s, 14s)",
        "Impact hit (sine sub drop + noise, every 4s)"
    ],
    "generated_at": "2026-09-21T00:00:00Z",
    "intended_usage": "Background music for AI Automation advertisement"
}
with open(OUT / "audio_manifest.json", "w") as f:
    json.dump(manifest, f, indent=2)

print("\nTrack complete: layers = bass + pad + arp + kick + hihat + snare + riser + impact")
