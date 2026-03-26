"""
Alchemy I2V Service — Wan2.1-I2V-14B-480P on Modal.

Image-to-video: takes a source image and animates it into a short clip.
Best quality approach: Qwen generates perfect image → Wan2.1 animates it.

Deploy:  modal deploy modal_services/video_i2v.py
"""

import modal

app = modal.App("alchemy-video-i2v")


def _download_i2v():
    """Download model at image build time."""
    import os
    os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "0"
    from huggingface_hub import snapshot_download
    print("Downloading Wan2.1-I2V-14B-480P-Diffusers...")
    snapshot_download("Wan-AI/Wan2.1-I2V-14B-480P-Diffusers", local_dir="/models/wan21-i2v-14b")
    print("Done.")


i2v_image = (
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
    .run_function(_download_i2v)
)


@app.cls(
    image=i2v_image,
    gpu="H100",
    timeout=900,
    scaledown_window=300,
)
class Wan21I2V:
    @modal.enter()
    def load_model(self):
        import torch
        from diffusers import WanImageToVideoPipeline

        self.pipeline = WanImageToVideoPipeline.from_pretrained(
            "/models/wan21-i2v-14b",
            torch_dtype=torch.bfloat16,
        )
        self.pipeline.to("cuda")
        print("Wan2.1-I2V-14B loaded.")

    @modal.method()
    def animate(
        self,
        image_bytes: bytes,
        prompt: str,
        num_frames: int = 49,
        num_inference_steps: int = 25,
        guidance_scale: float = 5.0,
    ) -> bytes:
        """Animate a source image into a video clip. Returns MP4 bytes."""
        import torch
        from PIL import Image
        import io

        import numpy as np

        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")

        # Calculate dimensions that fit within 480p budget while preserving aspect ratio
        max_area = 480 * 832
        mod_value = 16  # must be divisible by 16
        aspect_ratio = image.height / image.width
        height = round(np.sqrt(max_area * aspect_ratio)) // mod_value * mod_value
        width = round(np.sqrt(max_area / aspect_ratio)) // mod_value * mod_value
        image = image.resize((width, height), Image.LANCZOS)
        print(f"I2V input: {width}x{height} (aspect {aspect_ratio:.2f})")

        output = self.pipeline(
            image=image,
            prompt=prompt,
            height=height,
            width=width,
            num_frames=num_frames,
            num_inference_steps=num_inference_steps,
            guidance_scale=guidance_scale,
        )

        frames = output.frames[0]
        return self._frames_to_mp4(frames)

    def _frames_to_mp4(self, frames) -> bytes:
        import tempfile
        import subprocess
        import os
        from PIL import Image as PILImage
        import numpy as np

        with tempfile.TemporaryDirectory() as tmpdir:
            for i, frame in enumerate(frames):
                if isinstance(frame, np.ndarray):
                    if frame.dtype != np.uint8:
                        frame = (frame * 255).clip(0, 255).astype(np.uint8)
                    frame = PILImage.fromarray(frame)
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
