import re
import base64
import json
import time
import os
import modal
import requests

from utils import *
from cache import *
from .Tts import TTS
from llm_provider import generate_text
from config import *
from status import *
from uuid import uuid4
from constants import *
from typing import List
from moviepy.editor import *
from termcolor import colored
from moviepy.video.fx.all import crop
from moviepy.config import change_settings
from moviepy.video.tools.subtitles import SubtitlesClip
from datetime import datetime

from playwright.sync_api import sync_playwright

# Set ImageMagick Path
change_settings({"IMAGEMAGICK_BINARY": get_imagemagick_path()})


class YouTube:
    """
    Class for YouTube Automation.

    Steps to create a YouTube Short:
    1. Generate a topic
    2. Generate a script
    3. Generate metadata (Title, Description)
    4. Generate AI Image Prompts
    5. Generate Images based on generated Prompts
    6. Convert Text-to-Speech
    7. Show images each for n seconds
    8. Combine Concatenated Images with the Text-to-Speech
    """

    def __init__(
        self,
        account_uuid: str,
        account_nickname: str,
        browser_profile_path: str,
        niche: str,
        language: str,
    ) -> None:
        self._account_uuid: str = account_uuid
        self._account_nickname: str = account_nickname
        self._browser_profile_path: str = browser_profile_path
        self._niche: str = niche
        self._language: str = language

        self.images = []

        # Initialize Playwright with persistent context
        self._pw = sync_playwright().start()
        self.browser = self._pw.firefox.launch_persistent_context(
            user_data_dir=self._browser_profile_path,
            headless=get_headless(),
        )
        self.page = self.browser.new_page()

    def __del__(self):
        try:
            self.browser.close()
            self._pw.stop()
        except Exception:
            pass

    @property
    def niche(self) -> str:
        return self._niche

    @property
    def language(self) -> str:
        return self._language

    def generate_response(self, prompt: str, model_name: str = None) -> str:
        return generate_text(prompt, model_name=model_name)

    def generate_topic(self) -> str:
        completion = self.generate_response(
            f"Please generate a specific video idea that takes about the following topic: {self.niche}. Make it exactly one sentence. Only return the topic, nothing else."
        )

        if not completion:
            error("Failed to generate Topic.")

        self.subject = completion
        return completion

    def generate_script(self) -> str:
        sentence_length = get_script_sentence_length()
        prompt = f"""
        Generate a script for a video in {sentence_length} sentences, depending on the subject of the video.

        The script is to be returned as a string with the specified number of paragraphs.

        Here is an example of a string:
        "This is an example string."

        Do not under any circumstance reference this prompt in your response.

        Get straight to the point, don't start with unnecessary things like, "welcome to this video".

        Obviously, the script should be related to the subject of the video.

        YOU MUST NOT EXCEED THE {sentence_length} SENTENCES LIMIT. MAKE SURE THE {sentence_length} SENTENCES ARE SHORT.
        YOU MUST NOT INCLUDE ANY TYPE OF MARKDOWN OR FORMATTING IN THE SCRIPT, NEVER USE A TITLE.
        YOU MUST WRITE THE SCRIPT IN THE LANGUAGE SPECIFIED IN [LANGUAGE].
        ONLY RETURN THE RAW CONTENT OF THE SCRIPT. DO NOT INCLUDE "VOICEOVER", "NARRATOR" OR SIMILAR INDICATORS OF WHAT SHOULD BE SPOKEN AT THE BEGINNING OF EACH PARAGRAPH OR LINE. YOU MUST NOT MENTION THE PROMPT, OR ANYTHING ABOUT THE SCRIPT ITSELF. ALSO, NEVER TALK ABOUT THE AMOUNT OF PARAGRAPHS OR LINES. JUST WRITE THE SCRIPT

        Subject: {self.subject}
        Language: {self.language}
        """
        completion = self.generate_response(prompt)

        # Apply regex to remove *
        completion = re.sub(r"\*", "", completion)

        if not completion:
            error("The generated script is empty.")
            return

        if len(completion) > 5000:
            if get_verbose():
                warning("Generated Script is too long. Retrying...")
            return self.generate_script()

        self.script = completion
        return completion

    def generate_metadata(self) -> dict:
        title = self.generate_response(
            f"Please generate a YouTube Video Title for the following subject, including hashtags: {self.subject}. Only return the title, nothing else. Limit the title under 100 characters."
        )

        if len(title) > 100:
            if get_verbose():
                warning("Generated Title is too long. Retrying...")
            return self.generate_metadata()

        description = self.generate_response(
            f"Please generate a YouTube Video Description for the following script: {self.script}. Only return the description, nothing else."
        )

        self.metadata = {"title": title, "description": description}
        return self.metadata

    def generate_prompts(self) -> List[str]:
        n_prompts = len(self.script) / 3

        prompt = f"""
        Generate {n_prompts} Image Prompts for AI Image Generation,
        depending on the subject of a video.
        Subject: {self.subject}

        The image prompts are to be returned as
        a JSON-Array of strings.

        Each search term should consist of a full sentence,
        always add the main subject of the video.

        Be emotional and use interesting adjectives to make the
        Image Prompt as detailed as possible.

        YOU MUST ONLY RETURN THE JSON-ARRAY OF STRINGS.
        YOU MUST NOT RETURN ANYTHING ELSE.
        YOU MUST NOT RETURN THE SCRIPT.

        The search terms must be related to the subject of the video.
        Here is an example of a JSON-Array of strings:
        ["image prompt 1", "image prompt 2", "image prompt 3"]

        For context, here is the full text:
        {self.script}
        """

        completion = (
            str(self.generate_response(prompt))
            .replace("```json", "")
            .replace("```", "")
        )

        image_prompts = []

        if "image_prompts" in completion:
            image_prompts = json.loads(completion)["image_prompts"]
        else:
            try:
                image_prompts = json.loads(completion)
                if get_verbose():
                    info(f" => Generated Image Prompts: {image_prompts}")
            except Exception:
                if get_verbose():
                    warning(
                        "LLM returned an unformatted response. Attempting to clean..."
                    )

                r = re.compile(r"\[.*\]")
                image_prompts = r.findall(completion)
                if len(image_prompts) == 0:
                    if get_verbose():
                        warning("Failed to generate Image Prompts. Retrying...")
                    return self.generate_prompts()

        if len(image_prompts) > n_prompts:
            image_prompts = image_prompts[: int(n_prompts)]

        self.image_prompts = image_prompts
        success(f"Generated {len(image_prompts)} Image Prompts.")
        return image_prompts

    def _persist_image(self, image_bytes: bytes, provider_label: str) -> str:
        image_path = os.path.join(ROOT_DIR, ".mp", str(uuid4()) + ".png")

        with open(image_path, "wb") as image_file:
            image_file.write(image_bytes)

        if get_verbose():
            info(f' => Wrote image from {provider_label} to "{image_path}"')

        self.images.append(image_path)
        return image_path

    def generate_image_nanobanana2(self, prompt: str) -> str:
        print(f"Generating Image using Gemini API: {prompt}")

        api_key = get_image_gen_api_key()
        if not api_key:
            error("Image generation API key is not configured.")
            return None

        base_url = get_image_gen_api_base_url().rstrip("/")
        model = get_image_gen_model()
        aspect_ratio = get_image_gen_aspect_ratio()

        endpoint = f"{base_url}/models/{model}:generateContent"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseModalities": ["IMAGE"],
                "imageConfig": {"aspectRatio": aspect_ratio},
            },
        }

        try:
            response = requests.post(
                endpoint,
                headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
                json=payload,
                timeout=300,
            )
            response.raise_for_status()
            body = response.json()

            candidates = body.get("candidates", [])
            for candidate in candidates:
                content = candidate.get("content", {})
                for part in content.get("parts", []):
                    inline_data = part.get("inlineData") or part.get("inline_data")
                    if not inline_data:
                        continue
                    data = inline_data.get("data")
                    mime_type = inline_data.get("mimeType") or inline_data.get("mime_type", "")
                    if data and str(mime_type).startswith("image/"):
                        image_bytes = base64.b64decode(data)
                        return self._persist_image(image_bytes, "Gemini API")

            if get_verbose():
                warning(f"Gemini API did not return an image payload. Response: {body}")
            return None
        except Exception as e:
            if get_verbose():
                warning(f"Failed to generate image with Gemini API: {str(e)}")
            return None

    def generate_image(self, prompt: str) -> str:
        return self.generate_image_nanobanana2(prompt)

    def generate_script_to_speech(self, tts_instance: TTS) -> str:
        path = os.path.join(ROOT_DIR, ".mp", str(uuid4()) + ".wav")

        # Clean script
        self.script = re.sub(r"[^\w\s.?!]", "", self.script)

        tts_instance.synthesize(self.script, path)

        self.tts_path = path

        if get_verbose():
            info(f' => Wrote TTS to "{path}"')

        return path

    def add_video(self, video: dict) -> None:
        videos = self.get_videos()
        videos.append(video)

        cache = get_youtube_cache_path()

        with open(cache, "r") as file:
            previous_json = json.loads(file.read())

            accounts = previous_json["accounts"]
            for account in accounts:
                if account["id"] == self._account_uuid:
                    account["videos"].append(video)

            with open(cache, "w") as f:
                f.write(json.dumps(previous_json))

    def generate_subtitles(self, audio_path: str) -> str:
        """Generate subtitles using Modal Whisper STT service."""
        with open(audio_path, "rb") as f:
            audio_bytes = f.read()

        cls = modal.Cls.from_name("alchemy-stt", "WhisperSTT")
        stt = cls()
        srt_content = stt.transcribe.remote(audio_bytes)

        srt_path = os.path.join(ROOT_DIR, ".mp", str(uuid4()) + ".srt")
        with open(srt_path, "w", encoding="utf-8") as f:
            f.write(srt_content)

        return srt_path

    def combine(self) -> str:
        combined_image_path = os.path.join(ROOT_DIR, ".mp", str(uuid4()) + ".mp4")
        threads = get_threads()
        tts_clip = AudioFileClip(self.tts_path)
        max_duration = tts_clip.duration
        req_dur = max_duration / len(self.images)

        generator = lambda txt: TextClip(
            txt,
            font=os.path.join(get_fonts_dir(), get_font()),
            fontsize=100,
            color="#FFFF00",
            stroke_color="black",
            stroke_width=5,
            size=(1080, 1920),
            method="caption",
        )

        print(colored("[+] Combining images...", "blue"))

        clips = []
        tot_dur = 0
        while tot_dur < max_duration:
            for image_path in self.images:
                clip = ImageClip(image_path)
                clip.duration = req_dur
                clip = clip.set_fps(30)

                if round((clip.w / clip.h), 4) < 0.5625:
                    if get_verbose():
                        info(f" => Resizing Image: {image_path} to 1080x1920")
                    clip = crop(
                        clip,
                        width=clip.w,
                        height=round(clip.w / 0.5625),
                        x_center=clip.w / 2,
                        y_center=clip.h / 2,
                    )
                else:
                    if get_verbose():
                        info(f" => Resizing Image: {image_path} to 1920x1080")
                    clip = crop(
                        clip,
                        width=round(0.5625 * clip.h),
                        height=clip.h,
                        x_center=clip.w / 2,
                        y_center=clip.h / 2,
                    )
                clip = clip.resize((1080, 1920))

                clips.append(clip)
                tot_dur += clip.duration

        final_clip = concatenate_videoclips(clips)
        final_clip = final_clip.set_fps(30)
        random_song = choose_random_song()

        subtitles = None
        try:
            subtitles_path = self.generate_subtitles(self.tts_path)
            equalize_subtitles(subtitles_path, 10)
            subtitles = SubtitlesClip(subtitles_path, generator)
            subtitles.set_pos(("center", "center"))
        except Exception as e:
            warning(f"Failed to generate subtitles, continuing without subtitles: {e}")

        random_song_clip = AudioFileClip(random_song).set_fps(44100)

        random_song_clip = random_song_clip.fx(afx.volumex, 0.1)
        comp_audio = CompositeAudioClip([tts_clip.set_fps(44100), random_song_clip])

        final_clip = final_clip.set_audio(comp_audio)
        final_clip = final_clip.set_duration(tts_clip.duration)

        if subtitles is not None:
            final_clip = CompositeVideoClip([final_clip, subtitles])

        final_clip.write_videofile(combined_image_path, threads=threads)

        success(f'Wrote Video to "{combined_image_path}"')

        return combined_image_path

    def generate_video(self, tts_instance: TTS) -> str:
        self.generate_topic()
        self.generate_script()
        self.generate_metadata()
        self.generate_prompts()

        for prompt in self.image_prompts:
            self.generate_image(prompt)

        self.generate_script_to_speech(tts_instance)

        path = self.combine()

        if get_verbose():
            info(f" => Generated Video: {path}")

        self.video_path = os.path.abspath(path)
        return path

    def get_channel_id(self) -> str:
        self.page.goto("https://studio.youtube.com")
        self.page.wait_for_load_state("networkidle")
        channel_id = self.page.url.split("/")[-1]
        self.channel_id = channel_id
        return channel_id

    def upload_video(self) -> bool:
        try:
            self.get_channel_id()
            verbose = get_verbose()

            self.page.goto("https://www.youtube.com/upload")
            self.page.wait_for_load_state("networkidle")

            # Set video file
            file_input = self.page.locator("ytcp-uploads-file-picker input[type='file']")
            file_input.set_input_files(self.video_path)

            # Wait for upload to process
            self.page.wait_for_timeout(5000)

            # Set title
            textboxes = self.page.locator(f"#{YOUTUBE_TEXTBOX_ID}").all()
            title_el = textboxes[0]
            description_el = textboxes[-1]

            if verbose:
                info("\t=> Setting title...")

            title_el.click()
            title_el.fill("")
            title_el.type(self.metadata["title"])

            if verbose:
                info("\t=> Setting description...")

            self.page.wait_for_timeout(2000)
            description_el.click()
            description_el.fill("")
            description_el.type(self.metadata["description"])

            self.page.wait_for_timeout(500)

            # Set `made for kids` option
            if verbose:
                info("\t=> Setting `made for kids` option...")

            if not get_is_for_kids():
                self.page.locator(f"[name='{YOUTUBE_NOT_MADE_FOR_KIDS_NAME}']").click()
            else:
                self.page.locator(f"[name='{YOUTUBE_MADE_FOR_KIDS_NAME}']").click()

            self.page.wait_for_timeout(500)

            # Click next 3 times
            for i in range(3):
                if verbose:
                    info(f"\t=> Clicking next ({i + 1}/3)...")
                self.page.locator(f"#{YOUTUBE_NEXT_BUTTON_ID}").click()
                self.page.wait_for_timeout(1000)

            # Set as unlisted
            if verbose:
                info("\t=> Setting as unlisted...")

            radio_buttons = self.page.locator(f"xpath={YOUTUBE_RADIO_BUTTON_XPATH}").all()
            radio_buttons[2].click()

            if verbose:
                info("\t=> Clicking done button...")

            self.page.locator(f"#{YOUTUBE_DONE_BUTTON_ID}").click()

            self.page.wait_for_timeout(2000)

            # Get latest video
            if verbose:
                info("\t=> Getting video URL...")

            self.page.goto(
                f"https://studio.youtube.com/channel/{self.channel_id}/videos/short"
            )
            self.page.wait_for_load_state("networkidle")

            first_video = self.page.locator("ytcp-video-row").first
            anchor_tag = first_video.locator("a").first
            href = anchor_tag.get_attribute("href")
            if verbose:
                info(f"\t=> Extracting video ID from URL: {href}")
            video_id = href.split("/")[-2]

            url = build_url(video_id)
            self.uploaded_video_url = url

            if verbose:
                success(f" => Uploaded Video: {url}")

            self.add_video(
                {
                    "title": self.metadata["title"],
                    "description": self.metadata["description"],
                    "url": url,
                    "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
            )

            self.browser.close()
            self._pw.stop()

            return True
        except Exception:
            try:
                self.browser.close()
                self._pw.stop()
            except Exception:
                pass
            return False

    def get_videos(self) -> List[dict]:
        if not os.path.exists(get_youtube_cache_path()):
            with open(get_youtube_cache_path(), "w") as file:
                json.dump({"videos": []}, file, indent=4)
            return []

        videos = []
        with open(get_youtube_cache_path(), "r") as file:
            previous_json = json.loads(file.read())
            accounts = previous_json["accounts"]
            for account in accounts:
                if account["id"] == self._account_uuid:
                    videos = account["videos"]

        return videos
