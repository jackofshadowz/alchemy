"""
Alchemy — Full cinematic motivational short generator.
Script library → Qwen images → Helios animation → Kokoro voice → ffmpeg composite
"""
import sys
sys.path.insert(0, "src")

import os
import re
import json
import time
import random
import subprocess
import requests
import modal
import numpy as np

from uuid import uuid4
from config import ROOT_DIR, assert_folder_structure, get_font, get_fonts_dir, get_imagemagick_path
from llm_provider import init_provider, generate_text
from status import info, success, warning, error

# ─── CONFIG ───
VOICE = "am_adam"
VOICE_SPEED = 0.85
QWEN_API_KEY = "sk-a104311e82c44e9f8a70df2a32ec75b6"
QWEN_BASE = "https://dashscope-intl.aliyuncs.com/api/v1"

IMAGE_STYLE = (
    "Photorealistic cinematic still from a Netflix docuseries. "
    "Shot on ARRI Alexa Mini LF, Cooke S7/i lens, shallow depth of field. "
    "Natural dramatic lighting, warm amber highlights, deep shadows. "
    "European setting. Western European young man, mid-20s. "
    "9:16 vertical portrait composition. No text, no watermarks, no Asian settings."
)

# Guide the AI video model into its strengths, avoid common failure modes
VIDEO_PROMPT_RULES = (
    "\n\nCRITICAL RULES FOR VIDEO PROMPTS — these will be animated by AI video:\n"
    "EXCELLENT (use freely): specific real supercars with EXACT model names "
    "(e.g. 'white 2024 Lamborghini Revuelto', 'red 2023 Ferrari SF90 Stradale', "
    "'black 2024 Porsche 911 GT3 RS', 'grey 2024 McLaren 750S') — always specify color, year, model. "
    "Dramatic face close-ups with cinematic lighting, luxury watches (Rolex Daytona, AP Royal Oak) on wrist, "
    "wide aerial city shots, silhouettes against sunset, ocean waves, "
    "private jet exterior parked on tarmac, gym/weightlifting in motion, "
    "pouring whiskey or coffee in slow motion, slow-mo suit fabric movement, "
    "smoke and fog effects, reflections on wet surfaces, "
    "bokeh city lights, drone coastline shots, sunrise/sunset landscapes, "
    "swimming pool reflections, sunglasses reflecting city lights.\n"
    "HELICOPTER/AIRCRAFT: always show from the ground looking up, or parked static. "
    "NEVER show helicopters flying sideways or doing unrealistic movements.\n"
    "TASTEFUL COUPLE SHOTS (use sparingly, max 1 per video): "
    "couple walking away from camera along a waterfront at sunset, "
    "couple seen from behind in silhouette, elegant woman's hand on man's arm while walking, "
    "couple from far away on a balcony overlooking a city. "
    "ALWAYS from behind or in silhouette. NEVER facing camera. Wholesome, elegant, classy.\n"
    "AVOID (AI will butcher these): detailed hand manipulation (typing, writing), "
    "any readable text or signage, crowded scenes with 3+ people, "
    "specific famous landmarks (gondolas, Eiffel Tower), indoor kitchens or restaurants, "
    "detailed interiors with many small objects, anything requiring readable text.\n"
    "Mix shot types: aerials, close-ups of luxury objects, dramatic face shots, "
    "car driving shots, and silhouettes. Vary the lighting between scenes."
)


# ─── QWEN IMAGE GEN ───

def generate_image_qwen(prompt, output_path, max_retries=3):
    endpoint = f"{QWEN_BASE}/services/aigc/multimodal-generation/generation"
    for attempt in range(max_retries):
        resp = requests.post(
            endpoint,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {QWEN_API_KEY}"},
            json={
                "model": "qwen-image-2.0-pro",
                "input": {"messages": [{"role": "user", "content": [{"text": prompt}]}]},
                "parameters": {"size": "720*1280", "n": 1, "prompt_extend": True},
            },
            timeout=120,
        )
        if resp.status_code == 429:
            wait = 15 * (attempt + 1)
            warning(f"    Rate limited, waiting {wait}s...")
            time.sleep(wait)
            continue
        if resp.status_code != 200:
            warning(f"    Qwen error: {resp.status_code}")
            return False
        body = resp.json()
        for choice in body.get("output", {}).get("choices", []):
            for part in choice.get("message", {}).get("content", []):
                url = part.get("image")
                if url:
                    img = requests.get(url, timeout=60)
                    with open(output_path, "wb") as f:
                        f.write(img.content)
                    return True
        return False
    return False


# ─── HELIOS VIDEO GEN ───

def animate_image(image_path, prompt, output_path):
    """Animate a static image into a ~2s video clip using Helios."""
    video_cls = modal.Cls.from_name("alchemy-video", "HeliosVideo")
    video = video_cls()

    with open(image_path, "rb") as f:
        image_bytes = f.read()

    mp4_bytes = video.generate_i2v.remote(
        image_bytes=image_bytes,
        prompt=prompt,
        num_frames=49,  # ~2s at 24fps
        height=384,
        width=640,
    )

    with open(output_path, "wb") as f:
        f.write(mp4_bytes)
    return True


def generate_clip_t2v(prompt, output_path):
    """Generate a clip directly from text prompt."""
    video_cls = modal.Cls.from_name("alchemy-video", "HeliosVideo")
    video = video_cls()

    mp4_bytes = video.generate_t2v.remote(
        prompt=prompt,
        num_frames=49,
        height=384,
        width=640,
    )

    with open(output_path, "wb") as f:
        f.write(mp4_bytes)
    return True


# ─── TTS ───

def generate_voice(script, output_path):
    """Generate voiceover via Kokoro TTS on Modal."""
    import soundfile as sf
    from scipy.signal import resample as scipy_resample

    clean = re.sub(r"[^\w\s.?!,'\-]", "", script)

    tts_cls = modal.Cls.from_name("alchemy-tts", "KokoroTTS")
    tts = tts_cls()
    wav_bytes = tts.synthesize.remote(clean, voice=VOICE, speed=VOICE_SPEED)

    # Write raw, then normalize + resample
    raw_path = output_path + ".raw.wav"
    with open(raw_path, "wb") as f:
        f.write(wav_bytes)

    data, sr = sf.read(raw_path)
    # Normalize
    peak = np.abs(data).max()
    if peak > 0:
        data = data / peak * 0.92
    # Resample to 44100
    if sr != 44100:
        num = int(len(data) * 44100 / sr)
        data = scipy_resample(data, num)
        sr = 44100
    # Mono to stereo
    if data.ndim == 1:
        data = np.column_stack([data, data])

    sf.write(output_path, data, sr)
    os.remove(raw_path)
    return output_path


# ─── SENTENCE SPLITTING + TIMING ───

def split_sentences(script):
    """Split script into sentences, preserving fragments like 'Day after day.'"""
    raw = re.split(r'(?<=[.!?])\s+', script)
    return [s.strip() for s in raw if s.strip()]


def calculate_timings(sentences, total_duration):
    """Variable timing: short sentences get less time, long ones get more."""
    lengths = [len(s) for s in sentences]
    total_chars = sum(lengths)
    timings = []
    for length in lengths:
        # Weight by character count, but with a minimum of 1.5s
        t = max(1.5, (length / total_chars) * total_duration)
        timings.append(t)

    # Normalize to fit total duration
    scale = total_duration / sum(timings)
    timings = [t * scale for t in timings]
    return timings


# ─── MAIN PIPELINE ───

def main():
    assert_folder_structure()
    init_provider()

    mp_dir = os.path.join(ROOT_DIR, ".mp")
    videos_dir = os.path.join(ROOT_DIR, "videos")
    os.makedirs(videos_dir, exist_ok=True)

    vid_id = str(uuid4())[:8]

    # 1. Pick script
    info("1. Loading script...")
    with open(os.path.join(ROOT_DIR, "scripts_library.json")) as f:
        library = json.load(f)
    entry = random.choice(library)
    script = entry["script"]
    scene_hints = entry.get("scenes", [])
    success(f"   Script [{entry['id']}]: {script[:80]}...")

    # 2. Split into sentences
    sentences = split_sentences(script)
    info(f"   {len(sentences)} sentences")

    # 3. Generate voiceover first (to get total duration)
    info("2. Generating voiceover...")
    voice_path = os.path.join(mp_dir, f"voice_{vid_id}.wav")
    generate_voice(script, voice_path)

    from moviepy.editor import AudioFileClip
    voice_clip = AudioFileClip(voice_path)
    total_dur = voice_clip.duration
    voice_clip.close()
    success(f"   Voice: {total_dur:.1f}s")

    # 4. Calculate per-sentence timings
    timings = calculate_timings(sentences, total_dur)
    for i, (sent, dur) in enumerate(zip(sentences, timings)):
        info(f"   [{dur:.1f}s] {sent[:60]}")

    # 5. Generate image prompts per sentence
    info("3. Generating image prompts...")
    if scene_hints and len(scene_hints) >= len(sentences):
        hints_str = "\n".join(f"{i+1}. {scene_hints[i]}" for i in range(len(sentences)))
        prompts_raw = generate_text(
            f"Expand each scene tag into a detailed cinematic video prompt.\n\n"
            f"Scenes:\n{hints_str}\n\n"
            "For each, write ONE detailed sentence describing the shot."
            + VIDEO_PROMPT_RULES +
            f"\nReturn ONLY a JSON array of {len(sentences)} strings. No markdown."
        )
    else:
        prompts_raw = generate_text(
            f"Generate {len(sentences)} cinematic video prompts, one per sentence of this script:\n\n"
            + "\n".join(f'{i+1}. "{s}"' for i, s in enumerate(sentences))
            + VIDEO_PROMPT_RULES +
            f"\nReturn ONLY a JSON array of {len(sentences)} strings. No markdown."
        )

    prompts_raw = prompts_raw.replace("```json", "").replace("```", "").strip()
    try:
        image_prompts = json.loads(prompts_raw)
    except Exception:
        match = re.search(r"\[.*\]", prompts_raw, re.DOTALL)
        image_prompts = json.loads(match.group()) if match else []

    # Pad if needed
    while len(image_prompts) < len(sentences):
        image_prompts.append(f"Cinematic European scene, dramatic lighting, young man, luxury")
    image_prompts = image_prompts[:len(sentences)]
    success(f"   {len(image_prompts)} prompts")

    # 6. Generate clips — T2V for each sentence
    info("4. Generating video clips...")
    clip_paths = []
    for i, prompt in enumerate(image_prompts):
        clip_path = os.path.join(mp_dir, f"clip_{vid_id}_{i:02d}.mp4")
        full_prompt = f"{prompt}. {IMAGE_STYLE}"
        info(f"   [{i+1}/{len(sentences)}] Generating clip...")

        t0 = time.time()
        try:
            generate_clip_t2v(full_prompt, clip_path)
            elapsed = time.time() - t0
            success(f"   [{i+1}] Done in {elapsed:.1f}s")
            clip_paths.append(clip_path)
        except Exception as e:
            warning(f"   [{i+1}] Failed: {e}")
            clip_paths.append(None)

        # Small delay between clips
        if i < len(sentences) - 1:
            time.sleep(1)

    # Filter out failed clips
    valid = [(i, p) for i, p in enumerate(clip_paths) if p is not None]
    if not valid:
        error("No clips generated!")
        return

    # 7. Build concat file for ffmpeg with per-clip durations
    info("5. Compositing video...")

    # First, trim/loop each clip to its target duration
    trimmed_paths = []
    for idx, path in valid:
        target_dur = timings[idx]
        trimmed = os.path.join(mp_dir, f"trimmed_{vid_id}_{idx:02d}.mp4")
        # Scale to 1080x1920 (9:16) and trim to target duration
        subprocess.run([
            "ffmpeg", "-y",
            "-stream_loop", "-1",  # loop if clip is shorter than target
            "-i", path,
            "-t", str(target_dur),
            "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-an",  # no audio yet
            "-r", "24",
            trimmed,
        ], capture_output=True)
        trimmed_paths.append(trimmed)

    # Concatenate clips with short crossfade transitions via ffmpeg xfade
    raw_video = os.path.join(mp_dir, f"raw_{vid_id}.mp4")
    XFADE_DUR = 0.3  # 300ms crossfade

    if len(trimmed_paths) == 1:
        # Just copy
        subprocess.run(["cp", trimmed_paths[0], raw_video], capture_output=True)
    else:
        # Build xfade filter chain
        inputs = []
        for p in trimmed_paths:
            inputs.extend(["-i", os.path.abspath(p)])

        # Calculate offsets for each transition
        filter_parts = []
        offsets = []
        cumulative = 0.0
        for i in range(len(trimmed_paths)):
            idx_in_valid = valid[i][0] if i < len(valid) else i
            dur = timings[idx_in_valid] if idx_in_valid < len(timings) else 2.0
            if i == 0:
                cumulative = dur - XFADE_DUR
            else:
                cumulative += dur - XFADE_DUR
            offsets.append(cumulative)

        # Build filter: chain xfade between each pair
        n = len(trimmed_paths)
        if n == 2:
            filter_parts.append(f"[0:v][1:v]xfade=transition=fade:duration={XFADE_DUR}:offset={offsets[0]:.3f}[v]")
        else:
            # First pair
            filter_parts.append(f"[0:v][1:v]xfade=transition=fade:duration={XFADE_DUR}:offset={offsets[0]:.3f}[v1]")
            # Middle pairs
            for i in range(2, n):
                prev = f"v{i-1}"
                if i == n - 1:
                    out = "v"
                else:
                    out = f"v{i}"
                filter_parts.append(f"[{prev}][{i}:v]xfade=transition=fade:duration={XFADE_DUR}:offset={offsets[i-1]:.3f}[{out}]")

        filter_str = ";".join(filter_parts)

        cmd = ["ffmpeg", "-y"] + inputs + [
            "-filter_complex", filter_str,
            "-map", "[v]",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-r", "24",
            raw_video,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)

        # Fallback to simple concat if xfade fails
        if not os.path.exists(raw_video) or os.path.getsize(raw_video) < 1000:
            warning("   Crossfade failed, using hard cuts...")
            concat_list = os.path.join(mp_dir, f"concat_{vid_id}.txt")
            with open(concat_list, "w") as f:
                for p in trimmed_paths:
                    f.write(f"file '{os.path.abspath(p)}'\n")
            subprocess.run([
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0",
                "-i", concat_list,
                "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                "-r", "24",
                raw_video,
            ], capture_output=True)

    # 8. Add subtitles as SRT
    info("6. Generating subtitles...")
    srt_path = os.path.join(mp_dir, f"subs_{vid_id}.srt")
    srt_lines = []
    cumulative = 0.0
    for i, (sent, dur) in enumerate(zip(sentences, timings)):
        # Only include timings for valid clips
        if i < len(valid):
            start = cumulative
            end = cumulative + timings[valid[i][0]] if i < len(valid) else cumulative + dur
        else:
            start = cumulative
            end = cumulative + dur

        def fmt(s):
            ms = max(0, int(round(s * 1000)))
            h, ms = divmod(ms, 3600000)
            m, ms = divmod(ms, 60000)
            sec, ms = divmod(ms, 1000)
            return f"{h:02d}:{m:02d}:{sec:02d},{ms:03d}"

        srt_lines.extend([str(i + 1), f"{fmt(start)} --> {fmt(end)}", sent.upper(), ""])
        cumulative += dur

    with open(srt_path, "w") as f:
        f.write("\n".join(srt_lines))

    # 9. Mix voice + music via ffmpeg
    info("7. Mixing audio...")
    music_dir = os.path.join(ROOT_DIR, "music")
    music_files = [
        os.path.join(music_dir, f) for f in os.listdir(music_dir)
        if f.lower().endswith((".mp3", ".wav", ".m4a"))
    ] if os.path.isdir(music_dir) else []

    mixed_audio = os.path.join(mp_dir, f"audio_{vid_id}.wav")

    if music_files:
        bg_path = random.choice(music_files)
        info(f"   Music: {os.path.basename(bg_path)}")

        # Pick random start
        probe = AudioFileClip(bg_path)
        max_start = max(0, probe.duration - total_dur - 5)
        offset = random.uniform(0, max_start) if max_start > 0 else 0
        probe.close()

        subprocess.run([
            "ffmpeg", "-y",
            "-i", voice_path,
            "-ss", str(offset), "-i", bg_path,
            "-filter_complex",
            f"[1:a]atrim=0:{total_dur},asetpts=PTS-STARTPTS,volume=0.18[bg];"
            f"[0:a]volume=1.8[voice];"
            f"[voice][bg]amix=inputs=2:duration=first:dropout_transition=2[out]",
            "-map", "[out]",
            "-ac", "2", "-ar", "44100",
            mixed_audio,
        ], capture_output=True)
    else:
        # Voice only
        subprocess.run(["cp", voice_path, mixed_audio], capture_output=True)

    # 10. Final composite: video + audio + burned subtitles
    info("8. Final render...")
    output_path = os.path.join(videos_dir, f"alchemy_{vid_id}.mp4")

    font_path = os.path.join(get_fonts_dir(), get_font())
    # Escape special chars in path for ffmpeg
    srt_escaped = srt_path.replace("'", "'\\''").replace(":", "\\:")

    subprocess.run([
        "ffmpeg", "-y",
        "-i", raw_video,
        "-i", mixed_audio,
        "-vf", f"subtitles={srt_escaped}:force_style='FontName=Arial,FontSize=20,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,Outline=2,Alignment=2,MarginV=120'",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        "-r", "24",
        output_path,
    ], capture_output=True)

    # Check if it worked, if subtitles failed try without
    if not os.path.exists(output_path) or os.path.getsize(output_path) < 1000:
        warning("   Subtitle burn failed, rendering without...")
        subprocess.run([
            "ffmpeg", "-y",
            "-i", raw_video,
            "-i", mixed_audio,
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            output_path,
        ], capture_output=True)

    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    success(f"\nVideo saved: {output_path} ({size_mb:.1f}MB)")
    success(f"Script: {entry['id']}")
    success(f"Clips: {len(valid)}/{len(sentences)}")
    success(f"Duration: {total_dur:.1f}s")
    print(f"\n  open {output_path}")


if __name__ == "__main__":
    main()
