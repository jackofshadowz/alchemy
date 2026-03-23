import os
import modal

from config import ROOT_DIR, get_tts_config


class TTS:
    def __init__(self) -> None:
        cfg = get_tts_config()
        self._voice = cfg["voice"]
        self._speed = cfg["speed"]
        cls = modal.Cls.from_name("alchemy-tts", "KokoroTTS")
        self._model = cls()

    def synthesize(self, text, output_file=None):
        if output_file is None:
            output_file = os.path.join(ROOT_DIR, ".mp", "audio.wav")
        wav_bytes = self._model.synthesize.remote(
            text, voice=self._voice, speed=self._speed
        )
        with open(output_file, "wb") as f:
            f.write(wav_bytes)
        return output_file
