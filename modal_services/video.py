"""
Alchemy Video Service — Helios-Distilled (14B) on Modal.

Image-to-video generation using Helios, built on Wan2.1 14B.
Generates 2-5 second animated clips from static images.

Deploy:  modal deploy modal_services/video.py
Dev:     modal serve modal_services/video.py
"""

import modal

app = modal.App("alchemy-video")

helios_pip_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("git", "ffmpeg")
    .pip_install(
        "torch==2.5.1",
        index_url="https://download.pytorch.org/whl/cu121",
    )
    .pip_install(
        "git+https://github.com/huggingface/diffusers.git",
        "transformers",
        "accelerate",
        "sentencepiece",
        "Pillow",
        "numpy",
        "huggingface_hub",
        "ftfy",
    )
)


def _download_helios():
    """Download model at image build time."""
    import os
    os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "0"
    from huggingface_hub import snapshot_download
    print("Downloading Helios-Distilled...")
    snapshot_download("BestWishYsh/Helios-Distilled", local_dir="/models/helios-distilled")
    print("Done downloading.")


helios_image = helios_pip_image.run_function(_download_helios)


@app.cls(
    image=helios_image,
    gpu="H100",
    timeout=600,
    scaledown_window=300,
)
class HeliosVideo:
    @modal.enter()
    def load_model(self):
        import torch
        from diffusers import HeliosPyramidPipeline

        self.pipeline = HeliosPyramidPipeline.from_pretrained(
            "/models/helios-distilled",
            torch_dtype=torch.bfloat16,
        )
        self.pipeline.to("cuda")
        print("Helios model loaded.")

    @modal.method()
    def generate_t2v(
        self,
        prompt: str,
        num_frames: int = 49,
        height: int = 384,
        width: int = 640,
        guidance_scale: float = 1.0,
    ) -> bytes:
        """Text-to-video. Returns MP4 bytes."""
        import torch
        import tempfile
        import os

        output = self.pipeline(
            prompt=prompt,
            num_frames=num_frames,
            height=height,
            width=width,
            guidance_scale=guidance_scale,
            pyramid_num_inference_steps_list=[3, 3, 3],
        )

        frames = output.frames[0]  # list of PIL images
        return self._frames_to_mp4(frames)

    @modal.method()
    def generate_i2v(
        self,
        image_bytes: bytes,
        prompt: str,
        num_frames: int = 49,
        height: int = 384,
        width: int = 640,
        guidance_scale: float = 1.0,
    ) -> bytes:
        """Image-to-video. Returns MP4 bytes."""
        import torch
        from PIL import Image
        import io

        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        image = image.resize((width, height), Image.LANCZOS)

        output = self.pipeline(
            prompt=prompt,
            image=image,
            num_frames=num_frames,
            height=height,
            width=width,
            guidance_scale=guidance_scale,
            pyramid_num_inference_steps_list=[3, 3, 3],
        )

        frames = output.frames[0]
        return self._frames_to_mp4(frames)

    def _frames_to_mp4(self, frames) -> bytes:
        """Convert list of frames (PIL or numpy) to MP4 bytes via ffmpeg."""
        import tempfile
        import subprocess
        import os
        from PIL import Image
        import numpy as np

        with tempfile.TemporaryDirectory() as tmpdir:
            for i, frame in enumerate(frames):
                if isinstance(frame, np.ndarray):
                    # Handle numpy arrays — could be float [0,1] or uint8 [0,255]
                    if frame.dtype != np.uint8:
                        frame = (frame * 255).clip(0, 255).astype(np.uint8)
                    frame = Image.fromarray(frame)
                frame.save(os.path.join(tmpdir, f"{i:05d}.png"))

            output_path = os.path.join(tmpdir, "output.mp4")
            subprocess.run([
                "ffmpeg", "-y",
                "-framerate", "24",
                "-i", os.path.join(tmpdir, "%05d.png"),
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-crf", "18",
                "-preset", "fast",
                output_path,
            ], capture_output=True, check=True)

            with open(output_path, "rb") as f:
                return f.read()


@app.local_entrypoint()
def main():
    """Quick test: generate a short T2V clip."""
    video = HeliosVideo()
    mp4_bytes = video.generate_t2v.remote(
        prompt="A luxury sports car driving along a Mediterranean coastal road at golden hour, cinematic",
        num_frames=49,
    )
    with open("/tmp/helios_test.mp4", "wb") as f:
        f.write(mp4_bytes)
    print(f"Saved test video: {len(mp4_bytes)} bytes -> /tmp/helios_test.mp4")
