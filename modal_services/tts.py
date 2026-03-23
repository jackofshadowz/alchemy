"""
Alchemy TTS Service — Kokoro TTS on Modal.

Deploy:  modal deploy modal_services/tts.py
Dev:     modal serve modal_services/tts.py
"""

import modal

app = modal.App("alchemy-tts")

kokoro_image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("espeak-ng")
    .pip_install("kokoro", "soundfile", "numpy", "torch")
)


@app.cls(image=kokoro_image, gpu="T4", scaledown_window=300)
class KokoroTTS:
    @modal.enter()
    def load_model(self):
        from kokoro import KPipeline

        self.pipeline = KPipeline(lang_code="a")

    @modal.method()
    def synthesize(self, text: str, voice: str = "af_heart", speed: float = 1.0) -> bytes:
        import io
        import numpy as np
        import soundfile as sf

        generator = self.pipeline(text, voice=voice, speed=speed)
        audio_chunks = [audio for _, _, audio in generator]
        audio = np.concatenate(audio_chunks)

        buf = io.BytesIO()
        sf.write(buf, audio, 24000, format="WAV")
        return buf.getvalue()
