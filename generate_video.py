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
    "Show cars DRIVING or PARKED, never on fire, never crashing, never damaged. "
    "Dramatic face close-ups with cinematic lighting, "
    "wide aerial city shots, silhouettes against sunset, ocean waves, "
    "private jet exterior parked on tarmac, gym/weightlifting in motion, "
    "pouring coffee in slow motion, slow-mo suit fabric movement, "
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
    "ABSOLUTELY NEVER: overlays, split-screens, picture-in-picture, clocks, timers, "
    "montages, collages, text graphics, UI elements, countdowns, or any kind of "
    "visual compositing. EVERY prompt must be ONE SINGLE continuous camera shot "
    "of ONE scene. No transitions described in the prompt.\n"
    "PEOPLE: when showing men working out, they must ALWAYS be wearing a fitted t-shirt "
    "or athletic long sleeve. NEVER shirtless. Always look professional and put-together, "
    "even in the gym. No excessive sweat or unflattering angles.\n"
    "FACES: always clean, dry, composed, and confident. NEVER sweaty, wet, or glistening. "
    "Think GQ cover shoot, not mid-workout.\n"
    "FIRST CLIP: must be bright, vivid, and visually striking. NEVER start with a dark screen, "
    "black background, or dimly lit scene. Open with color and energy — a supercar in daylight, "
    "a bright cityscape, a man in a sharp suit in golden light.\n"
    "CARS: show them driving smoothly, parked elegantly, or from a cinematic angle. "
    "NEVER on fire, never with flames from exhaust, never crashed or damaged.\n"
    "WATCHES: DO NOT generate Rolex or any watch close-ups — AI cannot render watch faces well. "
    "Instead show luxury through cars, penthouses, suits, and city views.\n"
    "NO ALCOHOL: never show whiskey, wine, champagne, cocktails, bars, or drinking of any kind.\n"
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

    # Add pauses for dramatic effect + fix hard-to-pronounce words
    clean = re.sub(r"[^\w\s.?!,'\-]", "", script)

    # TTS pronunciation fixes
    clean = clean.replace("Lamborghini", "Lambo")
    clean = clean.replace("lamborghini", "lambo")
    clean = clean.replace("Revuelto", "Rev-welto")
    clean = clean.replace("Porsche", "Porsha")

    # Add pauses after short punchy sentences (under 30 chars ending with period)
    sentences_for_tts = re.split(r'(?<=[.!?])\s+', clean)
    paced_parts = []
    for s in sentences_for_tts:
        paced_parts.append(s.strip())
        if len(s.strip()) < 30:
            paced_parts.append("...")  # short pause after punchy lines
    clean = " ".join(paced_parts)

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

    # 5. Generate video prompts — sentence-matched + scroll-stopping opener
    info("3. Generating video prompts...")

    # Generate a large pool of rapid-fire montage clips
    # ~3x the number of sentences for rapid cuts
    num_clips = min(len(sentences) * 2, 20)

    sentence_list = "\n".join(f'  {i+1}. "{s}"' for i, s in enumerate(sentences))

    prompts_raw = generate_text(
        "You are a visual director for a rapid-fire motivational YouTube Short montage. "
        f"Generate exactly {num_clips} cinematic video shot descriptions.\n\n"
        f"SCRIPT (for thematic context):\n{sentence_list}\n\n"
        "RULES:\n"
        f"1. FIRST 3 PROMPTS must be SCROLL-STOPPERS — the most visually jaw-dropping shots possible. "
        "Examples: extreme close-up of a red 2023 Ferrari SF90 Stradale exhaust with flames, "
        "dramatic slow-motion face of a young man with sweat dripping staring into camera, "
        "a black 2024 Lamborghini Revuelto launching with tire smoke in slow motion, "
        "close-up of a Rolex Daytona face reflecting city lights. "
        "These must make someone STOP SCROLLING instantly.\n\n"
        "2. Shots should loosely follow the script's emotional arc — "
        "start with intensity/struggle, move through grind/work, end with luxury/triumph.\n\n"
        "3. Every prompt is a SINGLE continuous camera shot. No overlays, no split-screens, "
        "no compositing, no text, no clocks, no UI elements.\n\n"
        f"4. LAST 3 PROMPTS should be peak luxury/triumph: supercars, penthouses, "
        "couple walking into sunset, aerial Monaco, etc.\n\n"
        "5. Vary shot types rapidly: close-up object, wide aerial, face, car, silhouette, "
        "gym, cityscape. Never put two similar shots next to each other.\n"
        + VIDEO_PROMPT_RULES +
        f"\nReturn ONLY a JSON array of exactly {num_clips} strings. No markdown."
    )

    prompts_raw = prompts_raw.replace("```json", "").replace("```", "").strip()
    try:
        image_prompts = json.loads(prompts_raw)
    except Exception:
        match = re.search(r"\[.*\]", prompts_raw, re.DOTALL)
        image_prompts = json.loads(match.group()) if match else []

    while len(image_prompts) < num_clips:
        image_prompts.append("Cinematic aerial shot of a European coastal city at golden hour")
    image_prompts = image_prompts[:num_clips]

    info(f"   {len(image_prompts)} montage prompts (rapid-fire)")
    for i, p in enumerate(image_prompts[:5]):
        info(f"   [{i+1}] {p[:70]}...")
    info(f"   ... and {len(image_prompts) - 5} more")

    # 6. Generate clips — rapid-fire montage
    info("4. Generating video clips...")
    clip_paths = []
    for i, prompt in enumerate(image_prompts):
        clip_path = os.path.join(mp_dir, f"clip_{vid_id}_{i:02d}.mp4")
        full_prompt = f"{prompt}. {IMAGE_STYLE}"
        info(f"   [{i+1}/{len(image_prompts)}] Generating clip...")

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

    # 7. Build rapid-fire montage
    info("5. Compositing video...")

    # Each clip gets an equal slice of total duration (rapid cuts)
    clip_dur = total_dur / len(valid)
    info(f"   {len(valid)} clips x {clip_dur:.2f}s each = {total_dur:.1f}s")

    trimmed_paths = []
    for idx, path in valid:
        target_dur = clip_dur
        trimmed = os.path.join(mp_dir, f"trimmed_{vid_id}_{idx:02d}.mp4")
        # Scale to 1080x1920 (9:16) and trim to target duration
        subprocess.run([
            "ffmpeg", "-y",
            "-stream_loop", "-1",  # loop if clip is shorter than target
            "-i", path,
            "-t", str(target_dur),
            "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "fast", "-crf", "18",
            "-an",  # no audio yet
            "-r", "24",
            trimmed,
        ], capture_output=True)
        trimmed_paths.append(trimmed)

    # Hard-cut concat — rapid-fire montage style, no crossfades
    raw_video = os.path.join(mp_dir, f"raw_{vid_id}.mp4")
    concat_list = os.path.join(mp_dir, f"concat_{vid_id}.txt")
    with open(concat_list, "w") as f:
        for p in trimmed_paths:
            f.write(f"file '{os.path.abspath(p)}'\n")
    subprocess.run([
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", concat_list,
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "fast", "-crf", "18",
        "-r", "24",
        raw_video,
    ], capture_output=True)

    # 8. Add subtitles as SRT (timed to sentences, not clips)
    info("6. Generating subtitles...")
    srt_path = os.path.join(mp_dir, f"subs_{vid_id}.srt")
    srt_lines = []
    cumulative = 0.0

    def fmt(s):
        ms = max(0, int(round(s * 1000)))
        h, ms = divmod(ms, 3600000)
        m, ms = divmod(ms, 60000)
        sec, ms = divmod(ms, 1000)
        return f"{h:02d}:{m:02d}:{sec:02d},{ms:03d}"

    for i, (sent, dur) in enumerate(zip(sentences, timings)):
        start = cumulative
        end = cumulative + dur
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

        # Music volume rises and falls: starts at 0.35, peaks at 0.55 around 70%, settles at 0.40
        # Using volume filter with expression for dynamic volume
        subprocess.run([
            "ffmpeg", "-y",
            "-i", voice_path,
            "-ss", str(offset), "-i", bg_path,
            "-filter_complex",
            f"[1:a]atrim=0:{total_dur},asetpts=PTS-STARTPTS,"
            f"volume='0.35 + 0.20 * sin(PI * t / {total_dur})':eval=frame[bg];"
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
