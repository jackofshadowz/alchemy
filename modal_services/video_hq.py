"""
Alchemy HQ Video Service — Wan2.1-T2V-14B on Modal.

Full quality (non-distilled) text-to-video generation.
Slower but significantly better visual quality than Helios-Distilled.

Deploy:  modal deploy modal_services/video_hq.py
"""

import modal

app = modal.App("alchemy-video-hq")


def _download_wan():
    """Download model at image build time."""
    import os
    os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "0"
    from huggingface_hub import snapshot_download
    print("Downloading Wan2.1-T2V-14B-Diffusers...")
    snapshot_download("Wan-AI/Wan2.1-T2V-14B-Diffusers", local_dir="/models/wan21-t2v-14b")
    print("Done downloading.")


wan_image = (
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
    .run_function(_download_wan)
)


@app.cls(
    image=wan_image,
    gpu="H100",
    timeout=900,
    scaledown_window=300,
)
class Wan21Video:
    @modal.enter()
    def load_model(self):
        import torch
        from diffusers import WanPipeline

        self.pipeline = WanPipeline.from_pretrained(
            "/models/wan21-t2v-14b",
            torch_dtype=torch.bfloat16,
        )
        self.pipeline.to("cuda")
        print("Wan2.1-T2V-14B loaded.")

    @modal.method()
    def generate_t2v(
        self,
        prompt: str,
        num_frames: int = 49,
        height: int = 480,
        width: int = 832,
        num_inference_steps: int = 50,
        guidance_scale: float = 5.0,
    ) -> bytes:
        """Text-to-video. Returns MP4 bytes."""
        import torch

        output = self.pipeline(
            prompt=prompt,
            num_frames=num_frames,
            height=height,
            width=width,
            num_inference_steps=num_inference_steps,
            guidance_scale=guidance_scale,
        )

        frames = output.frames[0]
        return self._frames_to_mp4(frames)

    def _frames_to_mp4(self, frames) -> bytes:
        """Convert frames to MP4 bytes via ffmpeg."""
        import tempfile
        import subprocess
        import os
        from PIL import Image
        import numpy as np

        with tempfile.TemporaryDirectory() as tmpdir:
            for i, frame in enumerate(frames):
                if isinstance(frame, np.ndarray):
                    if frame.dtype != np.uint8:
                        frame = (frame * 255).clip(0, 255).astype(np.uint8)
                    frame = Image.fromarray(frame)
                frame.save(os.path.join(tmpdir, f"{i:05d}.png"))

            output_path = os.path.join(tmpdir, "output.mp4")
            subprocess.run([
                "ffmpeg", "-y",
                "-framerate", "16",
                "-i", os.path.join(tmpdir, "%05d.png"),
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-crf", "18",
                "-preset", "fast",
                output_path,
            ], capture_output=True, check=True)

            with open(output_path, "rb") as f:
                return f.read()
