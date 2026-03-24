"""
Alchemy video generator — cinematic motivational shorts.
"""
import sys
sys.path.insert(0, "src")

import os
import re
import json
import base64
import requests
import modal
import random
import subprocess
import numpy as np

from uuid import uuid4
from config import (
    ROOT_DIR, assert_folder_structure, get_verbose, get_threads,
    get_image_gen_api_key, get_image_gen_api_base_url, get_image_gen_model,
    get_image_gen_aspect_ratio, get_font, get_fonts_dir, get_imagemagick_path,
)
from llm_provider import init_provider, generate_text
from status import info, success, warning, error
from moviepy.editor import (
    AudioFileClip, ImageClip, TextClip, CompositeVideoClip,
    CompositeAudioClip, concatenate_videoclips, afx, vfx,
)
from moviepy.video.fx.all import crop
from moviepy.config import change_settings

change_settings({"IMAGEMAGICK_BINARY": get_imagemagick_path()})

from PIL import Image
if not hasattr(Image, "ANTIALIAS"):
    Image.ANTIALIAS = Image.LANCZOS

# ─── CONFIG ───
NICHE = "motivational grindset for young men — European luxury lifestyle, discipline, wealth, supercars, Monaco, London, Milan"
LANGUAGE = "English"
NUM_IMAGES = 5
VOICE = "am_adam"

IMAGE_STYLE = (
    "Photorealistic cinematic still from a Netflix docuseries. "
    "Shot on ARRI Alexa Mini LF, Cooke S7/i lens, f/1.4 shallow depth of field. "
    "Natural dramatic lighting, warm amber highlights, deep shadow tones. "
    "European setting. Western European young man, mid-20s. "
    "9:16 vertical portrait composition. No text, no watermarks."
)

QWEN_API_KEY = "sk-a104311e82c44e9f8a70df2a32ec75b6"
QWEN_BASE = "https://dashscope-intl.aliyuncs.com/api/v1"


# ─── IMAGE GENERATION ───

def generate_image_qwen(prompt, max_retries=3):
    import time
    endpoint = f"{QWEN_BASE}/services/aigc/multimodal-generation/generation"

    for attempt in range(max_retries):
        resp = requests.post(
            endpoint,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {QWEN_API_KEY}",
            },
            json={
                "model": "qwen-image-2.0-pro",
                "input": {
                    "messages": [{"role": "user", "content": [{"text": prompt}]}]
                },
                "parameters": {"size": "720*1280", "n": 1, "prompt_extend": True},
            },
            timeout=120,
        )

        if resp.status_code == 429:
            wait = 15 * (attempt + 1)
            warning(f"  Rate limited, waiting {wait}s...")
            time.sleep(wait)
            continue

        if resp.status_code != 200:
            warning(f"  Qwen error {resp.status_code}: {resp.text[:200]}")
            return None

        body = resp.json()
        for choice in body.get("output", {}).get("choices", []):
            for part in choice.get("message", {}).get("content", []):
                image_url = part.get("image")
                if image_url:
                    img_resp = requests.get(image_url, timeout=60)
                    img_resp.raise_for_status()
                    path = os.path.join(ROOT_DIR, ".mp", f"{uuid4()}.png")
                    with open(path, "wb") as f:
                        f.write(img_resp.content)
                    success(f"  Image saved ({len(img_resp.content)//1024}KB)")
                    return path
        return None
    return None


# ─── KEN BURNS EFFECT ───

def ken_burns_clip(image_path, duration, direction="zoom_in"):
    """Create a clip with slow zoom/pan (Ken Burns effect)."""
    img = ImageClip(image_path)

    # Target 1080x1920, but work at higher res for zoom headroom
    base_w, base_h = 1080, 1920
    headroom = 1.15  # 15% zoom range

    # Resize image to fill with headroom
    img = img.resize(height=int(base_h * headroom))
    if img.w < base_w * headroom:
        img = img.resize(width=int(base_w * headroom))

    img_w, img_h = img.w, img.h

    if direction == "zoom_in":
        def make_frame(get_frame, t):
            progress = t / duration
            scale = 1.0 + progress * 0.12  # zoom in 12%
            cw = int(base_w / scale)
            ch = int(base_h / scale)
            cx = (img_w - cw) // 2
            cy = (img_h - ch) // 2
            frame = get_frame(t)
            cropped = frame[cy:cy+ch, cx:cx+cw]
            from PIL import Image as PILImage
            pil = PILImage.fromarray(cropped)
            pil = pil.resize((base_w, base_h), PILImage.LANCZOS)
            return np.array(pil)
        result = img.set_duration(duration).fl(make_frame)

    elif direction == "zoom_out":
        def make_frame(get_frame, t):
            progress = t / duration
            scale = 1.12 - progress * 0.12  # zoom out
            cw = int(base_w / scale)
            ch = int(base_h / scale)
            cx = (img_w - cw) // 2
            cy = (img_h - ch) // 2
            frame = get_frame(t)
            cropped = frame[cy:cy+ch, cx:cx+cw]
            from PIL import Image as PILImage
            pil = PILImage.fromarray(cropped)
            pil = pil.resize((base_w, base_h), PILImage.LANCZOS)
            return np.array(pil)
        result = img.set_duration(duration).fl(make_frame)

    elif direction == "pan_left":
        def make_frame(get_frame, t):
            progress = t / duration
            frame = get_frame(t)
            max_pan = img_w - base_w
            cx = int(max_pan * (1 - progress))
            cropped = frame[:base_h, cx:cx+base_w]
            if cropped.shape[0] < base_h or cropped.shape[1] < base_w:
                from PIL import Image as PILImage
                pil = PILImage.fromarray(frame)
                pil = pil.resize((base_w, base_h), PILImage.LANCZOS)
                return np.array(pil)
            return cropped
        result = img.set_duration(duration).fl(make_frame)

    else:  # pan_right
        def make_frame(get_frame, t):
            progress = t / duration
            frame = get_frame(t)
            max_pan = img_w - base_w
            cx = int(max_pan * progress)
            cropped = frame[:base_h, cx:cx+base_w]
            if cropped.shape[0] < base_h or cropped.shape[1] < base_w:
                from PIL import Image as PILImage
                pil = PILImage.fromarray(frame)
                pil = pil.resize((base_w, base_h), PILImage.LANCZOS)
                return np.array(pil)
            return cropped
        result = img.set_duration(duration).fl(make_frame)

    return result.set_fps(30)


# ─── MAIN ───

def main():
    import time

    assert_folder_structure()
    init_provider()

    # 1. Pick script from curated library
    info("Step 1: Loading script...")
    library_path = os.path.join(ROOT_DIR, "scripts_library.json")
    with open(library_path, "r") as f:
        scripts_library = json.load(f)

    entry = random.choice(scripts_library)
    script = entry["script"]
    scene_hints = entry.get("scenes", [])
    mood = entry.get("mood", "determined")
    success(f"Script:\n  {script}")

    # 2. Generate image prompts from scene hints
    info("Step 2: Generating image prompts...")
    if scene_hints and len(scene_hints) >= NUM_IMAGES:
        # Use LLM to expand the scene hints into full cinematic descriptions
        hints_str = "\n".join(f"{i+1}. {h}" for i, h in enumerate(scene_hints[:NUM_IMAGES]))
        prompts_raw = generate_text(
            f"Expand each of these scene descriptions into a detailed cinematic image prompt.\n\n"
            f"Scene list:\n{hints_str}\n\n"
            "For EACH scene, write one detailed paragraph describing:\n"
            "- Exact camera angle and lens (low angle, aerial, close-up, over-the-shoulder)\n"
            "- Specific European location details\n"
            "- Lighting conditions (golden hour, pre-dawn blue, neon reflections)\n"
            "- What the young Western European man (mid-20s, athletic) is doing\n"
            "- Mood and atmosphere\n\n"
            f"Return ONLY a JSON array of exactly {NUM_IMAGES} strings. No markdown."
        )
        prompts_raw = prompts_raw.replace("```json", "").replace("```", "").strip()
        try:
            image_prompts = json.loads(prompts_raw)
        except Exception:
            match = re.search(r"\[.*\]", prompts_raw, re.DOTALL)
            image_prompts = json.loads(match.group()) if match else []
    else:
        image_prompts = []

    # Fallback defaults
    if len(image_prompts) < NUM_IMAGES:
        defaults = [
            "Low angle shot of a young man silhouetted against Monaco harbor at pre-dawn, city lights reflecting on water",
            "Close-up of hands gripping a Lamborghini steering wheel, Swiss mountain road curving ahead, golden hour light",
            "Aerial cinematic shot of a man in a dark suit walking through Milan Galleria Vittorio Emanuele at night, wet reflections",
            "Over-the-shoulder shot through floor-to-ceiling windows of a London penthouse, man at desk, city lights below",
            "Wide dramatic shot of a supercar on a winding Amalfi Coast road, sunset, ocean in background",
        ]
        image_prompts.extend(defaults[len(image_prompts):NUM_IMAGES])

    image_prompts = image_prompts[:NUM_IMAGES]
    success(f"Got {len(image_prompts)} prompts")

    # 3. Generate images
    info("Step 3: Generating images...")
    images = []
    for i, prompt in enumerate(image_prompts):
        if i > 0:
            time.sleep(3)
        full_prompt = f"{prompt}. {IMAGE_STYLE}"
        info(f"  [{i+1}/{NUM_IMAGES}] {prompt[:70]}...")
        path = generate_image_qwen(full_prompt)
        if path:
            images.append(path)
        else:
            warning(f"  Failed, skipping")

    if len(images) < 2:
        error("Not enough images generated.")
        return

    # 4. TTS
    info("Step 4: Generating voiceover...")
    clean_script = re.sub(r"[^\w\s.?!,']", "", script)
    tts_cls = modal.Cls.from_name("alchemy-tts", "KokoroTTS")
    tts = tts_cls()
    wav_bytes = tts.synthesize.remote(clean_script, voice=VOICE, speed=0.85)
    tts_path = os.path.join(ROOT_DIR, ".mp", f"voice_{uuid4()}.wav")
    with open(tts_path, "wb") as f:
        f.write(wav_bytes)

    # Normalize and convert to stereo 44100Hz
    import soundfile as sf
    from scipy.signal import resample
    audio_data, audio_sr = sf.read(tts_path)
    max_amp = np.abs(audio_data).max()
    if max_amp > 0:
        audio_data = audio_data / max_amp * 0.92
    if audio_sr != 44100:
        num_samples = int(len(audio_data) * 44100 / audio_sr)
        audio_data = resample(audio_data, num_samples)
        audio_sr = 44100
    if audio_data.ndim == 1:
        audio_data = np.column_stack([audio_data, audio_data])
    sf.write(tts_path, audio_data, audio_sr)
    success(f"Voice: {tts_path}")

    # 5. Build video with Ken Burns effect + crossfade
    info("Step 5: Building video...")
    tts_clip = AudioFileClip(tts_path)
    total_duration = tts_clip.duration
    clip_duration = total_duration / len(images)

    directions = ["zoom_in", "zoom_out", "pan_left", "pan_right", "zoom_in"]
    clips = []
    for i, img_path in enumerate(images):
        direction = directions[i % len(directions)]
        dur = clip_duration + 0.5  # slight overlap for crossfade
        clip = ken_burns_clip(img_path, dur, direction)
        # Add fade
        clip = clip.crossfadein(0.4)
        clips.append(clip)

    # Concatenate with crossfade
    from moviepy.editor import concatenate_videoclips
    video = concatenate_videoclips(clips, method="compose", padding=-0.4)
    video = video.set_duration(total_duration)
    video = video.set_fps(30)

    # 6. Subtitles — word-by-word style at bottom third
    info("Step 6: Adding subtitles...")
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', clean_script) if s.strip()]
    dur_per = total_duration / len(sentences) if sentences else total_duration

    subtitle_clips = []
    for i, sentence in enumerate(sentences):
        start = i * dur_per
        end = (i + 1) * dur_per
        txt = TextClip(
            sentence.upper(),
            font=os.path.join(get_fonts_dir(), get_font()),
            fontsize=72,
            color="white",
            stroke_color="black",
            stroke_width=3,
            size=(980, None),
            method="caption",
        ).set_position(("center", 1550)).set_start(start).set_duration(end - start)
        # Fade in/out
        txt = txt.crossfadein(0.2).crossfadeout(0.2)
        subtitle_clips.append(txt)

    video = CompositeVideoClip([video] + subtitle_clips, size=(1080, 1920))

    # 7. Write video WITHOUT audio first (MoviePy audio embedding is broken)
    info("Step 7: Rendering video...")
    videos_dir = os.path.join(ROOT_DIR, "videos")
    os.makedirs(videos_dir, exist_ok=True)
    vid_id = str(uuid4())[:8]

    temp_video = os.path.join(ROOT_DIR, ".mp", f"temp_{vid_id}.mp4")
    video.write_videofile(temp_video, threads=get_threads(), audio=False)

    # 8. Pick background music and mux with ffmpeg
    info("Step 8: Adding audio with ffmpeg...")
    music_dir = os.path.join(ROOT_DIR, "music")
    music_files = [
        os.path.join(music_dir, f) for f in os.listdir(music_dir)
        if f.lower().endswith((".mp3", ".wav", ".m4a", ".ogg"))
    ] if os.path.isdir(music_dir) else []

    output_path = os.path.join(videos_dir, f"grindset_{vid_id}.mp4")

    if music_files:
        bg_path = random.choice(music_files)
        info(f"  Music: {os.path.basename(bg_path)}")

        # Pick random start point
        bg_probe = AudioFileClip(bg_path)
        max_start = max(0, bg_probe.duration - total_duration - 5)
        start_offset = random.uniform(0, max_start) if max_start > 0 else 0
        bg_probe.close()

        # Use ffmpeg to mix voice + music and mux with video
        # This is far more reliable than MoviePy for audio
        mixed_audio = os.path.join(ROOT_DIR, ".mp", f"mixed_{vid_id}.wav")
        cmd = [
            "ffmpeg", "-y",
            "-i", tts_path,
            "-ss", str(start_offset), "-i", bg_path,
            "-filter_complex",
            f"[1:a]atrim=0:{total_duration},asetpts=PTS-STARTPTS,volume=0.20[bg];"
            f"[0:a]volume=1.8[voice];"
            f"[voice][bg]amix=inputs=2:duration=first:dropout_transition=2[out]",
            "-map", "[out]",
            "-ac", "2", "-ar", "44100",
            mixed_audio,
        ]
        subprocess.run(cmd, capture_output=True)

        # Mux video + mixed audio
        cmd2 = [
            "ffmpeg", "-y",
            "-i", temp_video,
            "-i", mixed_audio,
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            output_path,
        ]
        subprocess.run(cmd2, capture_output=True)
    else:
        # Just mux voice
        cmd = [
            "ffmpeg", "-y",
            "-i", temp_video,
            "-i", tts_path,
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            output_path,
        ]
        subprocess.run(cmd, capture_output=True)

    success(f"\nVideo saved to: {output_path}")
    print(f"  Open: open {output_path}")


if __name__ == "__main__":
    main()
