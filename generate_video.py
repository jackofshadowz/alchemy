"""
Alchemy — Syncopated motivational short generator.
Pexels photos → Wan2.1 I2V animation → syncopated editing → voice + music
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
from config import ROOT_DIR, assert_folder_structure, get_font, get_fonts_dir
from llm_provider import init_provider, generate_text
from status import info, success, warning, error

# ─── CONFIG ───
VOICES = ["am_adam", "am_michael", "am_eric", "bm_george", "bm_lewis"]
VOICE_SPEED = 0.85
PEXELS_KEY = "1yNyeaX2M7iYEaSujSemZfHAzMPL4vEMP6TlfVFOTlwaGrZ9A0kr7cmN"
PIXABAY_KEY = "55186402-09d87c724da81c760aa1a083f"
CLIP_DURATION = 1.2  # seconds — use only first 1.2s of each I2V clip
I2V_GUIDANCE = 7.5
I2V_STEPS = 25
QWEN_API_KEY = "sk-a104311e82c44e9f8a70df2a32ec75b6"


# ─── PEXELS SEARCH ───

def search_pexels_photos(query, count=3):
    """Search Pexels for landscape photos. Returns list of {url, alt, id}."""
    resp = requests.get(
        f"https://api.pexels.com/v1/search",
        params={"query": query, "per_page": count, "orientation": "landscape"},
        headers={"Authorization": PEXELS_KEY},
        timeout=15,
    )
    if resp.status_code != 200:
        return []
    photos = resp.json().get("photos", [])
    return [
        {"url": p["src"]["large2x"], "alt": p.get("alt", ""), "id": p["id"]}
        for p in photos
    ]


def search_pexels_videos(query, count=3, orientation="landscape"):
    """Search Pexels for videos. Returns list of {url, alt, id, duration}."""
    resp = requests.get(
        f"https://api.pexels.com/videos/search",
        params={"query": query, "per_page": count, "orientation": orientation},
        headers={"Authorization": PEXELS_KEY},
        timeout=15,
    )
    if resp.status_code != 200:
        return []
    videos = resp.json().get("videos", [])
    results = []
    for v in videos:
        # Pick the best quality file under 1080p
        files = sorted(v.get("video_files", []), key=lambda f: f.get("height", 0), reverse=True)
        for f in files:
            if f.get("height", 0) <= 1080 and f.get("link"):
                results.append({
                    "url": f["link"],
                    "alt": v.get("url", ""),
                    "id": v["id"],
                    "duration": v.get("duration", 0),
                })
                break
    return results


def search_pixabay_videos(query, count=3):
    """Search Pixabay for videos. Returns list of {url, id, duration}."""
    resp = requests.get(
        "https://pixabay.com/api/videos/",
        params={"key": PIXABAY_KEY, "q": query, "per_page": count},
        timeout=15,
    )
    if resp.status_code != 200:
        return []
    results = []
    for h in resp.json().get("hits", []):
        # Get medium or large video
        vid = h.get("videos", {})
        url = vid.get("large", {}).get("url") or vid.get("medium", {}).get("url", "")
        if url and h.get("duration", 0) >= 3:
            results.append({
                "url": url,
                "id": f"pb_{h['id']}",  # prefix to avoid ID collision with Pexels
                "duration": h["duration"],
            })
    return results


def download_file(url, path):
    """Download a URL to a local path."""
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    with open(path, "wb") as f:
        f.write(resp.content)
    return len(resp.content)


# ─── I2V ANIMATION ───

def animate_photo(image_path, prompt, output_path):
    """Animate a photo using Wan2.1-I2V. Returns True on success."""
    with open(image_path, "rb") as f:
        image_bytes = f.read()

    i2v_cls = modal.Cls.from_name("alchemy-video-i2v", "Wan21I2V")
    i2v = i2v_cls()

    mp4_bytes = i2v.animate.remote(
        image_bytes=image_bytes,
        prompt=prompt,
        num_frames=49,
        num_inference_steps=I2V_STEPS,
        guidance_scale=I2V_GUIDANCE,
    )

    with open(output_path, "wb") as f:
        f.write(mp4_bytes)
    return True


# ─── CLIP PROCESSING ───

def trim_and_crop(input_path, output_path, duration=CLIP_DURATION):
    """Trim to first N seconds and crop from landscape to 9:16 portrait."""
    subprocess.run([
        "ffmpeg", "-y",
        "-i", input_path,
        "-t", str(duration),
        "-vf", "crop=ih*9/16:ih,scale=1080:1920",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "fast", "-crf", "18",
        "-an", "-r", "24",
        output_path,
    ], capture_output=True)
    return os.path.exists(output_path) and os.path.getsize(output_path) > 1000


def trim_portrait_clip(input_path, output_path, start=0, duration=CLIP_DURATION):
    """Trim a portrait video — just scale, no crop needed."""
    subprocess.run([
        "ffmpeg", "-y",
        "-ss", str(start),
        "-i", input_path,
        "-t", str(duration),
        "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:-1:-1:color=black",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "fast", "-crf", "18",
        "-an", "-r", "24",
        output_path,
    ], capture_output=True)
    return os.path.exists(output_path) and os.path.getsize(output_path) > 1000


def trim_video_clip(input_path, output_path, start=0, duration=CLIP_DURATION):
    """Trim a Pexels video clip and crop to portrait."""
    subprocess.run([
        "ffmpeg", "-y",
        "-ss", str(start),
        "-i", input_path,
        "-t", str(duration),
        "-vf", "crop=ih*9/16:ih,scale=1080:1920",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "fast", "-crf", "18",
        "-an", "-r", "24",
        output_path,
    ], capture_output=True)
    return os.path.exists(output_path) and os.path.getsize(output_path) > 1000


# ─── TTS ───

def generate_voice(script, output_path, voice=None, voice_speed=None):
    """Generate voiceover via Kokoro TTS on Modal."""
    import soundfile as sf
    from scipy.signal import resample as scipy_resample

    clean = re.sub(r"[^\w\s.?!,'\-]", "", script)

    # TTS pronunciation fixes
    clean = clean.replace("Lamborghini", "Lambo").replace("lamborghini", "lambo")
    clean = clean.replace("Porsche", "Porsha")

    # Dramatic pauses
    dramatic_words = ['ends', 'begins', 'enough', 'choose', 'now', 'quit',
                      'win', 'stop', 'never', 'empire', 'collect', 'smile',
                      'obsession', 'fire', 'forges', 'sacrifice', 'professor']

    sentences_for_tts = re.split(r'(?<=[.!?])\s+', clean)
    paced_parts = []
    for s in sentences_for_tts:
        s = s.strip()
        paced_parts.append(s)
        if len(s) < 30:
            paced_parts.append("...")
        last_word = s.rstrip('.!?').split()[-1].lower() if s.strip() else ""
        if last_word in dramatic_words:
            paced_parts.append(".....")
    clean = " ".join(paced_parts)

    tts_cls = modal.Cls.from_name("alchemy-tts", "KokoroTTS")
    tts = tts_cls()

    voice = voice or random.choice(VOICES)
    voice_speed = voice_speed or VOICE_SPEED
    info(f"   Voice: {voice} (speed: {voice_speed})")
    wav_bytes = tts.synthesize.remote(clean, voice=voice, speed=voice_speed)

    raw_path = output_path + ".raw.wav"
    with open(raw_path, "wb") as f:
        f.write(wav_bytes)

    data, sr = sf.read(raw_path)
    peak = np.abs(data).max()
    if peak > 0:
        data = data / peak * 0.92
    if sr != 44100:
        num = int(len(data) * 44100 / sr)
        data = scipy_resample(data, num)
        sr = 44100
    if data.ndim == 1:
        data = np.column_stack([data, data])

    sf.write(output_path, data, sr)
    os.remove(raw_path)
    return output_path


# ─── SENTENCE TOOLS ───

def split_sentences(script):
    raw = re.split(r'(?<=[.!?])\s+', script)
    return [s.strip() for s in raw if s.strip()]


def sentence_to_search_query(sentence, style_tone=""):
    """Convert a sentence into a Pexels search query."""
    # Map common motivational words to visual search terms
    mappings = {
        "car": "luxury sports car driving",
        "ferrari": "ferrari supercar",
        "lambo": "lamborghini supercar",
        "porsche": "porsche sports car",
        "penthouse": "luxury penthouse city view",
        "gym": "gym workout fitness",
        "workout": "gym weights training",
        "morning": "sunrise city dawn",
        "4am": "dark city night dawn",
        "three am": "dark city night",
        "ocean": "ocean waves sunset",
        "coast": "coastal road scenic",
        "empire": "city skyline aerial",
        "build": "construction architecture modern",
        "pain": "athlete training determination",
        "fire": "fire flames dramatic",
        "suit": "man business suit walking",
        "desk": "modern office desk work",
        "couple": "couple walking elegant city",
        "silence": "empty room minimal",
        "dream": "sunrise horizon landscape",
        "mountain": "mountain road scenic",
        "dark": "dramatic shadows moody",
        "cold": "winter morning frost",
        "win": "victory celebration achievement",
        "collect": "luxury lifestyle success",
        "freedom": "open road freedom driving",
        "sacrifice": "athlete training hard",
        "sleep": "city night sleeping dark",
        "scroll": "phone social media",
        "compound": "growth chart success",
        "average": "crowd city ordinary",
        "private": "private jet luxury",
        "comfort": "comfortable couch lazy",
    }

    sentence_lower = sentence.lower()
    for keyword, query in mappings.items():
        if keyword in sentence_lower:
            return query

    # Fallback: use LLM to generate a search query
    return style_tone if style_tone else "cinematic luxury lifestyle motivational"


# ─── MAIN PIPELINE ───

def main():
    assert_folder_structure()
    init_provider()

    mp_dir = os.path.join(ROOT_DIR, ".mp")
    videos_dir = os.path.join(ROOT_DIR, "videos")
    os.makedirs(videos_dir, exist_ok=True)
    vid_id = str(uuid4())[:8]

    # 1. Load libraries
    info("1. Loading libraries...")
    with open(os.path.join(ROOT_DIR, "scripts_library.json")) as f:
        library = json.load(f)
    with open(os.path.join(ROOT_DIR, "speaker_styles.json")) as f:
        speaker_styles = json.load(f)

    entry = random.choice(library)
    script = entry["script"]
    style_name = entry.get("style", "preacher")
    style = speaker_styles["styles"].get(style_name, {})
    success(f"   [{entry['id']}] style={style_name}: {script[:70]}...")

    # 2. Split + voice
    sentences = split_sentences(script)
    info(f"   {len(sentences)} sentences")

    info("2. Generating voiceover...")
    voice_path = os.path.join(mp_dir, f"voice_{vid_id}.wav")
    generate_voice(
        script, voice_path,
        voice=style.get("voice"),
        voice_speed=style.get("voice_speed"),
    )

    from moviepy.editor import AudioFileClip
    voice_clip = AudioFileClip(voice_path)
    total_dur = voice_clip.duration
    voice_clip.close()
    success(f"   Duration: {total_dur:.1f}s")

    # 3. Calculate clip count for syncopated editing
    # More clips than sentences — rapid-fire staccato
    num_clips = max(20, int(total_dur / CLIP_DURATION))
    info(f"3. Building {num_clips} clips at {CLIP_DURATION}s each (syncopated)")

    # 4. Generate search queries — use LLM for unique queries per clip
    info("4. Generating search queries...")

    # Mood-specific query pools
    mood_queries = {
        "warrior": [
            "man boxing heavy bag gym", "dark gym empty weights room", "man running rain night city",
            "man fist clenching determined", "stadium empty dark dramatic", "man shadow boxing gym",
            "sports car speeding tunnel dark", "storm lightning ocean dramatic", "man pushups dawn outdoor",
            "man heavy barbell deadlift gym", "man running concrete stairs dawn", "dark road car headlights night",
            "man fighter training boxing ring", "man walking dark street alone", "cold morning breath dark city",
            "heavy iron chains industrial", "man training gym intense", "man alone weight room night",
            "dark tunnel light end walking", "man determined face close up dark",
            "bentley continental driving city", "rolls royce driving night", "lamborghini aventador driving highway",
            "private jet gulfstream tarmac", "superyacht mediterranean sea", "monte carlo casino night",
            "man tailored suit italian style", "pitti uomo street style menswear", "first class airplane cabin",
            "rooftop pool infinity city skyline", "ferrari 488 driving coastal road", "porsche 911 mountain road",
        ],
        "preacher": [
            "sunrise city dramatic", "man raising arms victory", "sports car driving fast",
            "crowd stadium lights", "man suit power walk", "gold luxury close up",
            "city skyline golden hour", "man gym determined", "ocean waves powerful",
            "bentley continental gt driving city night", "penthouse city view night", "man standing rooftop",
            "ferrari 488 driving fast road", "empty road sunrise", "boxing gloves close up",
            "rolls royce phantom parked hotel", "superyacht ocean aerial", "man silhouette sunrise",
            "pitti uomo man street style", "private jet gulfstream boarding", "monte carlo harbour yachts",
            "luxury watch close up", "skyscraper looking up",
        ],
        "philosopher": [
            "ocean horizon calm", "mountain peak clouds", "man walking alone beach",
            "library books old", "rain window contemplation", "chess pieces close up",
            "fire fireplace warm", "tree standing alone field", "stone sculpture classical",
            "empty road stretching horizon", "man suit looking out window",
            "clock gears mechanism", "bridge fog morning",
            "man thinking silhouette window", "sunrise over water still",
            "ancient architecture columns", "man walking path alone",
            "bentley driving country road elegant", "rolls royce interior luxury leather", "superyacht deck ocean",
            "private jet interior first class", "man bespoke suit italian menswear", "ferrari portofino coastal road",
        ],
        "hustler": [
            "man typing fast laptop office", "bentley continental parked valet", "city night neon lights street",
            "man suit walking fast city street", "money cash stack business",
            "modern glass office building exterior", "handshake business deal men",
            "coffee desk early morning dark", "gulfstream private jet interior cabin",
            "skyscraper elevator luxury", "man confident suit street style",
            "ferrari key fob hand leather", "boardroom meeting modern", "rooftop infinity pool city skyline",
            "briefcase leather man walking", "rolls royce driving city night",
            "man phone call walking city", "penthouse modern apartment interior",
            "pitti uomo menswear street style", "superyacht deck champagne ocean",
            "monte carlo night casino lights", "porsche taycan driving city",
        ],
        "sage": [
            "sunset golden beach calm", "man walking pier sunset", "ocean waves golden hour",
            "couple walking away sunset", "vineyard golden light", "man standing cliff ocean",
            "river flowing peaceful", "man suit overlooking city sunset",
            "mountain road winding scenic", "man sitting bench park alone",
            "door opening bright light", "balcony view city morning",
            "harbor boats calm water", "man walking toward horizon",
            "bentley parked manor house", "superyacht sunset calm sea", "penthouse terrace city panorama",
            "gulfstream private jet boarding", "porsche 911 turbo mountain road", "dom perignon champagne pouring",
        ],
    }

    style_pool = mood_queries.get(style_name, mood_queries["preacher"])

    queries_prompt = (
        f"Pick exactly {num_clips} search queries from this pool for a motivational video.\n\n"
        f"Script: \"{script}\"\n"
        f"Mood: {style_name} — {style.get('description', '')}\n\n"
        f"QUERY POOL (pick from these ONLY, you may rephrase slightly):\n"
        + "\n".join(f"- {q}" for q in style_pool) +
        "\n\nRules:\n"
        "- Match each query to the sentence being spoken at that moment\n"
        "- First 3 MUST be luxury/aspirational — a supercar, private jet, yacht, or city skyline. "
        "NEVER start with gym, fitness, workout, boxing, or any person exercising.\n"
        "- Last 3 should be triumphant/aspirational (luxury cars, penthouse, yacht)\n"
        "- Every query must be different\n"
        "- IMPORTANT: interleave grind shots with luxury reward shots throughout.\n"
        "  Every 3-4 hard work clips, drop in a ferrari, penthouse, yacht, or luxury shot.\n"
        "  The contrast between struggle and reward is what makes it compelling.\n"
        "- You may use queries not in the pool IF they match the mood perfectly\n"
        f"\nReturn ONLY a JSON array of exactly {num_clips} strings. No markdown."
    )

    queries_raw = generate_text(queries_prompt)
    queries_raw = queries_raw.replace("```json", "").replace("```", "").strip()
    try:
        clip_queries = json.loads(queries_raw)
    except Exception:
        match = re.search(r"\[.*\]", queries_raw, re.DOTALL)
        clip_queries = json.loads(match.group()) if match else []

    # Force first 3 queries to be luxury — never gym/fitness opener
    luxury_openers = [
        "ferrari 488 driving fast road", "bentley continental gt driving city",
        "rolls royce phantom driving night", "lamborghini aventador highway",
        "private jet gulfstream tarmac", "superyacht ocean aerial",
        "city skyline sunset dramatic", "penthouse city view night",
    ]
    gym_words = {"gym", "boxing", "training", "deadlift", "workout", "fitness",
                 "running", "pushup", "barbell", "shadow", "battle", "athlete",
                 "stairs", "sweat", "pull"}
    for i in range(min(3, len(clip_queries))):
        if any(w in clip_queries[i].lower() for w in gym_words):
            clip_queries[i] = random.choice(luxury_openers)

    # Pad if needed
    fallbacks = ["luxury car driving", "city skyline night", "ocean sunset waves",
                 "man walking suit", "penthouse city view",
                 "coastal road scenic", "sunrise mountain", "business office modern",
                 "couple walking city elegant"]
    while len(clip_queries) < num_clips:
        clip_queries.append(random.choice(fallbacks))
    clip_queries = clip_queries[:num_clips]

    for i, q in enumerate(clip_queries[:5]):
        info(f"   [{i+1}] {q}")
    info(f"   ... and {len(clip_queries) - 5} more")

    # 5. Source clips — try Pexels video first, then photo→I2V
    trimmed_clips = []
    used_ids = set()  # track used photo AND video IDs

    for i, query in enumerate(clip_queries):
        clip_path = os.path.join(mp_dir, f"clip_{vid_id}_{i:03d}.mp4")
        info(f"   [{i+1}/{num_clips}] \"{query[:40]}\"")

        sourced = False

        # Try Pexels VIDEO — portrait first, then landscape
        for orientation in ["portrait", "landscape"]:
            if sourced:
                break
            videos = search_pexels_videos(query, count=5, orientation=orientation)
            for v in videos:
                if v["duration"] < 2 or v["id"] in used_ids:
                    continue
                try:
                    raw = os.path.join(mp_dir, f"raw_{vid_id}_{i:03d}.mp4")
                    download_file(v["url"], raw)
                    max_start = max(0, v["duration"] - CLIP_DURATION - 1)
                    start = random.uniform(0, max_start) if max_start > 0 else 0
                    if orientation == "portrait":
                        # Portrait video — just trim and scale, no crop
                        if trim_portrait_clip(raw, clip_path, start=start, duration=CLIP_DURATION):
                            used_ids.add(v["id"])
                            success(f"     Pexels portrait video #{v['id']}")
                            sourced = True
                            break
                    else:
                        if trim_video_clip(raw, clip_path, start=start, duration=CLIP_DURATION):
                            used_ids.add(v["id"])
                            success(f"     Pexels landscape video #{v['id']}")
                            sourced = True
                            break
                except Exception:
                    continue

        # Try Pixabay videos
        if not sourced:
            pb_videos = search_pixabay_videos(query, count=5)
            for v in pb_videos:
                if v["id"] in used_ids:
                    continue
                try:
                    raw = os.path.join(mp_dir, f"raw_{vid_id}_{i:03d}.mp4")
                    download_file(v["url"], raw)
                    max_start = max(0, v["duration"] - CLIP_DURATION - 1)
                    start = random.uniform(0, max_start) if max_start > 0 else 0
                    if trim_video_clip(raw, clip_path, start=start, duration=CLIP_DURATION):
                        used_ids.add(v["id"])
                        success(f"     Pixabay video {v['id']}")
                        sourced = True
                        break
                except Exception:
                    continue

        # Fall back to Pexels PHOTO → I2V
        if not sourced:
            photos = search_pexels_photos(query, count=5)
            for p in photos:
                if p["id"] in used_ids:
                    continue
                try:
                    photo_path = os.path.join(mp_dir, f"photo_{vid_id}_{i:03d}.jpg")
                    download_file(p["url"], photo_path)
                    used_ids.add(p["id"])

                    # Animate with I2V
                    i2v_output = os.path.join(mp_dir, f"i2v_{vid_id}_{i:03d}.mp4")
                    info(f"     Animating photo #{p['id']}...")
                    t0 = time.time()
                    animate_photo(
                        photo_path,
                        f"{query}, filmic warm tones, cinematic motion, 35mm film grain",
                        i2v_output,
                    )
                    elapsed = time.time() - t0
                    info(f"     I2V done in {elapsed:.0f}s")

                    # Trim to first 1.2s and crop to portrait
                    if trim_and_crop(i2v_output, clip_path, duration=CLIP_DURATION):
                        success(f"     I2V from photo #{p['id']}")
                        sourced = True
                        break
                except Exception as e:
                    warning(f"     Failed: {e}")
                    continue

        if not sourced:
            warning(f"     No footage found for \"{query[:30]}\"")

        # Small delay between Pexels API calls
        time.sleep(0.5)

    # Filter successful clips
    valid_clips = [os.path.join(mp_dir, f"clip_{vid_id}_{i:03d}.mp4")
                   for i in range(num_clips)
                   if os.path.exists(os.path.join(mp_dir, f"clip_{vid_id}_{i:03d}.mp4"))
                   and os.path.getsize(os.path.join(mp_dir, f"clip_{vid_id}_{i:03d}.mp4")) > 1000]

    info(f"   {len(valid_clips)}/{num_clips} clips sourced")

    if len(valid_clips) < 5:
        error("Not enough footage. Aborting.")
        return

    # 6. Syncopated assembly — hard cuts, rapid fire
    info("5. Syncopated assembly...")
    concat_list = os.path.join(mp_dir, f"concat_{vid_id}.txt")
    with open(concat_list, "w") as f:
        for p in valid_clips:
            f.write(f"file '{os.path.abspath(p)}'\n")

    raw_video = os.path.join(mp_dir, f"raw_{vid_id}.mp4")
    subprocess.run([
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", concat_list,
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "fast", "-crf", "18",
        "-r", "24",
        raw_video,
    ], capture_output=True)

    # 7. Mix voice + music
    info("6. Mixing audio...")
    music_dir = os.path.join(ROOT_DIR, "music")
    music_files = [
        os.path.join(music_dir, f) for f in os.listdir(music_dir)
        if f.lower().endswith((".mp3", ".wav", ".m4a"))
    ] if os.path.isdir(music_dir) else []

    mixed_audio = os.path.join(mp_dir, f"audio_{vid_id}.wav")

    if music_files:
        bg_path = random.choice(music_files)
        info(f"   Music: {os.path.basename(bg_path)}")

        from moviepy.editor import AudioFileClip as AFC
        probe = AFC(bg_path)
        max_start = max(0, probe.duration - total_dur - 5)
        offset = random.uniform(0, max_start) if max_start > 0 else 0
        probe.close()

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
        subprocess.run(["cp", voice_path, mixed_audio], capture_output=True)

    # 8. Final composite
    info("7. Final render...")
    output_path = os.path.join(videos_dir, f"alchemy_{vid_id}.mp4")
    subprocess.run([
        "ffmpeg", "-y",
        "-i", raw_video,
        "-i", mixed_audio,
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        output_path,
    ], capture_output=True)

    if os.path.exists(output_path) and os.path.getsize(output_path) > 10000:
        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        success(f"\nVideo: {output_path} ({size_mb:.1f}MB)")
        success(f"Script: {entry['id']} | Voice: {style.get('voice', '?')} | Clips: {len(valid_clips)}")
        print(f"\n  open {output_path}")
    else:
        error("Final render failed.")


if __name__ == "__main__":
    main()
