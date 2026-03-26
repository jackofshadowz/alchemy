"""
Alchemy Bark TTS — Expressive speech with emotion tags on Modal.

Deploy:  modal deploy modal_services/tts_bark.py
"""

import modal

app = modal.App("alchemy-tts-bark")

bark_pip = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("torch", "transformers", "scipy", "accelerate", "numpy", "huggingface_hub")
)


def _download_bark():
    from transformers import AutoProcessor, BarkModel
    AutoProcessor.from_pretrained("suno/bark")
    BarkModel.from_pretrained("suno/bark")
    print("Bark downloaded.")


bark_image = bark_pip.run_function(_download_bark)


@app.cls(image=bark_image, gpu="A10G", timeout=300, scaledown_window=300)
class BarkTTS:
    @modal.enter()
    def load_model(self):
        import torch
        from transformers import AutoProcessor, BarkModel

        self.processor = AutoProcessor.from_pretrained("suno/bark")
        self.model = BarkModel.from_pretrained("suno/bark", torch_dtype=torch.float16)
        self.model.to("cuda")
        self.sample_rate = self.model.generation_config.sample_rate
        print(f"Bark loaded. Sample rate: {self.sample_rate}")

    @modal.method()
    def synthesize(self, text: str, voice_preset: str = "v2/en_speaker_6") -> bytes:
        import io, torch, numpy as np
        import scipy.io.wavfile

        inputs = self.processor(
            text=[text],
            return_tensors="pt",
            voice_preset=voice_preset,
        ).to("cuda")

        with torch.no_grad():
            audio = self.model.generate(**inputs, do_sample=True)

        audio_np = audio.cpu().numpy().squeeze()
        if audio_np.max() > 0:
            audio_np = audio_np / np.abs(audio_np).max() * 0.92
        audio_int16 = (audio_np * 32767).astype(np.int16)

        buf = io.BytesIO()
        scipy.io.wavfile.write(buf, rate=self.sample_rate, data=audio_int16)
        return buf.getvalue()

    @modal.method()
    def synthesize_long(self, text: str, voice_preset: str = "v2/en_speaker_6") -> bytes:
        import io, re, numpy as np
        import scipy.io.wavfile

        sentences = re.split(r'(?<=[.!?])\s+', text)
        chunks = []
        current = ""
        for s in sentences:
            if len(current) + len(s) > 150:
                if current:
                    chunks.append(current.strip())
                current = s
            else:
                current = (current + " " + s).strip()
        if current:
            chunks.append(current.strip())

        all_audio = []
        for chunk in chunks:
            wav_bytes = self.synthesize(chunk, voice_preset)
            buf = io.BytesIO(wav_bytes)
            _, audio_data = scipy.io.wavfile.read(buf)
            all_audio.append(audio_data)
            silence = np.zeros(int(self.sample_rate * 0.3), dtype=audio_data.dtype)
            all_audio.append(silence)

        combined = np.concatenate(all_audio)
        buf = io.BytesIO()
        scipy.io.wavfile.write(buf, rate=self.sample_rate, data=combined)
        return buf.getvalue()
