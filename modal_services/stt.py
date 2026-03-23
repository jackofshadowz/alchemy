"""
Alchemy STT Service — Whisper large-v3 on Modal.

Deploy:  modal deploy modal_services/stt.py
Dev:     modal serve modal_services/stt.py
"""

import modal

app = modal.App("alchemy-stt")

whisper_image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("ffmpeg")
    .pip_install("faster-whisper")
)


def _format_ts(seconds: float) -> str:
    ms = max(0, int(round(seconds * 1000)))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


@app.cls(image=whisper_image, gpu="T4", scaledown_window=300)
class WhisperSTT:
    @modal.enter()
    def load_model(self):
        from faster_whisper import WhisperModel

        self.model = WhisperModel("large-v3", device="cuda", compute_type="float16")

    @modal.method()
    def transcribe(self, audio_bytes: bytes) -> str:
        """Transcribe audio bytes and return SRT-formatted subtitles."""
        import tempfile
        import os

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(audio_bytes)
            tmp_path = f.name

        try:
            segments, _ = self.model.transcribe(tmp_path, vad_filter=True)

            lines = []
            for idx, seg in enumerate(segments, 1):
                start = _format_ts(seg.start)
                end = _format_ts(seg.end)
                text = seg.text.strip()
                if text:
                    lines.extend([str(idx), f"{start} --> {end}", text, ""])
            return "\n".join(lines)
        finally:
            os.unlink(tmp_path)
