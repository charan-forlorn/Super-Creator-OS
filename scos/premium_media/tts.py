"""Optional TTS providers with explicit opt-in and no secret persistence."""
from __future__ import annotations

import base64
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class TTSProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class VoiceRequest:
    text: str
    language: str
    output_path: Path
    voice: str | None = None
    reference_audio: Path | None = None
    speed: float = 1.0


class TTSProvider(Protocol):
    provider_id: str
    languages: tuple[str, ...]

    def available(self) -> bool: ...
    def synthesize(self, request: VoiceRequest) -> Path: ...


class GoogleCloudChirpProvider:
    """Google Cloud Text-to-Speech adapter.

    Uses Application Default Credentials. The key/token is never written by this adapter.
    Chirp 3: HD currently advertises Thai and English voices; voice names are explicit in config.
    """

    provider_id = "google_chirp3_hd"
    languages = ("th-TH", "en-US")

    def __init__(self, voice_default: str = "th-TH-Chirp3-HD-Charon"):
        self.voice_default = voice_default

    def available(self) -> bool:
        try:
            import google.cloud.texttospeech_v1 as texttospeech  # type: ignore
            return bool(texttospeech and (os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or shutil.which("gcloud")))
        except Exception:
            return False

    def synthesize(self, request: VoiceRequest) -> Path:
        try:
            from google.cloud import texttospeech  # type: ignore
        except Exception as exc:
            raise TTSProviderError("google-cloud-texttospeech is not installed") from exc
        voice_name = request.voice or self.voice_default
        if request.language not in self.languages:
            raise TTSProviderError(
                f"{self.provider_id}: unsupported configured language {request.language!r}"
            )
        client = texttospeech.TextToSpeechClient()
        synthesis_input = texttospeech.SynthesisInput(text=request.text)
        voice = texttospeech.VoiceSelectionParams(
            language_code=request.language,
            name=voice_name,
        )
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.LINEAR16,
            sample_rate_hertz=48000,
        )
        response = client.synthesize_speech(
            request=synthesis_input,
            voice=voice,
            audio_config=audio_config,
        )
        request.output_path.parent.mkdir(parents=True, exist_ok=True)
        request.output_path.write_bytes(response.audio_content)
        if not request.output_path.exists() or request.output_path.stat().st_size == 0:
            raise TTSProviderError("Google TTS returned no audio bytes")
        return request.output_path


class PiperProvider:
    provider_id = "piper"
    languages = ("th-TH", "en-US")

    def __init__(self, executable: str = "piper", model: Path | None = None):
        self.executable = executable
        self.model = model

    def available(self) -> bool:
        return bool(shutil.which(self.executable) and self.model and self.model.exists())

    def synthesize(self, request: VoiceRequest) -> Path:
        exe = shutil.which(self.executable)
        if not exe:
            raise TTSProviderError("piper executable not installed")
        if self.model is None or not self.model.exists():
            raise TTSProviderError("piper voice model is not configured")
        request.output_path.parent.mkdir(parents=True, exist_ok=True)
        proc = subprocess.run(
            [exe, "--model", str(self.model), "--output_file", str(request.output_path)],
            input=request.text, text=True, capture_output=True,
        )
        if proc.returncode != 0 or not request.output_path.exists():
            raise TTSProviderError((proc.stderr or proc.stdout)[-1500:])
        return request.output_path


class ChatterboxProvider:
    provider_id = "chatterbox"
    languages = (
        "ar", "da", "de", "el", "en", "es", "fi", "fr", "he", "hi", "it",
        "ja", "ko", "ms", "nl", "no", "pl", "pt", "ru", "sv", "sw", "tr", "zh",
    )

    def available(self) -> bool:
        try:
            import chatterbox  # type: ignore
            return chatterbox is not None
        except Exception:
            return False

    def synthesize(self, request: VoiceRequest) -> Path:
        if request.language not in self.languages:
            raise TTSProviderError(f"Chatterbox multilingual does not advertise {request.language}")
        try:
            from chatterbox.mtl_tts import ChatterboxMultilingualTTS  # type: ignore
            import soundfile as sf  # type: ignore
        except Exception as exc:
            raise TTSProviderError("Chatterbox dependencies are not installed") from exc
        model = ChatterboxMultilingualTTS.from_pretrained(
            device="cuda" if _cuda() else "cpu",
            t3_model="v3",
        )
        kwargs = {}
        if request.reference_audio:
            kwargs["audio_prompt_path"] = str(request.reference_audio)
        wav = model.generate(request.text, language_id=request.language, **kwargs)
        request.output_path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(request.output_path), wav.squeeze(0).detach().cpu().numpy(), model.sr)
        return request.output_path


class VoiceRouter:
    def __init__(self, providers: dict[str, TTSProvider] | None = None):
        self.providers = providers or {
            "google_chirp3_hd": GoogleCloudChirpProvider(),
            "piper": PiperProvider(),
            "chatterbox": ChatterboxProvider(),
        }

    def select(self, language: str, *, premium: bool = False, provider_id: str | None = None) -> str:
        if provider_id:
            provider = self.providers.get(provider_id)
            if provider is None:
                raise TTSProviderError(f"unknown provider {provider_id}")
            if language not in provider.languages:
                raise TTSProviderError(f"{provider_id} does not advertise {language}")
            return provider_id

        # Premium path prefers a configured Thai/English cloud voice, otherwise local.
        candidates = (
            ("google_chirp3_hd", "piper", "chatterbox")
            if premium
            else ("piper", "chatterbox", "google_chirp3_hd")
        )
        for candidate in candidates:
            provider = self.providers.get(candidate)
            if provider and language in provider.languages and provider.available():
                return candidate
        raise TTSProviderError(
            f"no configured TTS provider available for {language}; "
            "install/configure an approved provider instead of silently falling back"
        )

    def synthesize(self, request: VoiceRequest, *, premium: bool = False, provider_id: str | None = None) -> Path:
        selected = self.select(request.language, premium=premium, provider_id=provider_id)
        return self.providers[selected].synthesize(request)


def _cuda() -> bool:
    try:
        import torch  # type: ignore
        return bool(torch.cuda.is_available())
    except Exception:
        return False
