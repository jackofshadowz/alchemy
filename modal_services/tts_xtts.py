"""
Alchemy XTTS v2 — Voice cloning TTS with emotion transfer on Modal.

Deploy:  modal deploy modal_services/tts_xtts.py
"""

import modal

app = modal.App("alchemy-tts-xtts")


def _download_xtts():
    import os
    os.environ["COQUI_TOS_AGREED"] = "1"
    from TTS.api import TTS
    TTS("tts_models/multilingual/multi-dataset/xtts_v2")
    print("XTTS v2 downloaded.")


xtts_image = (
    modal.Image.debian_slim(python_version="3.10")
    .apt_install("ffmpeg")
    .pip_install(
        "transformers==4.40.2",
        "torch==2.3.1",
        "torchaudio==2.3.1",
        "numpy<2",
        "soundfile",
    )
    .pip_install("TTS==0.22.0")
    .run_function(_download_xtts)
)


@app.cls(image=xtts_image, gpu="T4", timeout=300, scaledown_window=300)
class XTTSTTS:
    @modal.enter()
    def load_model(self):
        import os
        os.environ["COQUI_TOS_AGREED"] = "1"
        from TTS.api import TTS
        self.tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2", gpu=True)
        print("XTTS v2 loaded.")

    @modal.method()
    def synthesize(self, text: str, speaker_wav_bytes: bytes, language: str = "en") -> bytes:
        import tempfile, os

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(speaker_wav_bytes)
            speaker_path = f.name

        output_path = tempfile.mktemp(suffix=".wav")

        try:
            self.tts.tts_to_file(
                text=text,
                file_path=output_path,
                speaker_wav=speaker_path,
                language=language,
            )
            with open(output_path, "rb") as f:
                return f.read()
        finally:
            os.unlink(speaker_path)
            if os.path.exists(output_path):
                os.unlink(output_path)
