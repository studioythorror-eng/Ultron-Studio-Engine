import os
import json
import asyncio
import numpy as np
from PIL import Image, ImageEnhance, ImageDraw
import edge_tts
from moviepy.editor import (
    ImageClip, AudioFileClip, CompositeVideoClip,
    CompositeAudioClip, concatenate_videoclips, afx
)

W, H = 1920, 1080

# 1. Studio-Grade Neural Voiceover Generator (Free via Edge-TTS)
async def _tts_async(text, voice, out_path):
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(out_path)

def generate_voice(text, out_path, voice="en-US-ChristopherNeural"):
    asyncio.run(_tts_async(text, voice, out_path))
    return AudioFileClip(out_path)

# 2. Dark Cinema Color Grading & Atmosphere Filter
def apply_atmosphere(img_pil, atmosphere):
    img = img_pil.convert("RGB").resize((W, H), Image.LANCZOS)
    img = ImageEnhance.Contrast(img).enhance(1.22)
    img = ImageEnhance.Color(img).enhance(0.78)
    arr = np.array(img, dtype=np.float32)

    if atmosphere == "rain_night":
        arr[:, :, 0] *= 0.78  # Reduce Red
        arr[:, :, 2] *= 1.15  # Boost Cold Blue
    elif atmosphere == "blood_tint":
        arr[:, :, 0] *= 1.25  # Boost Red
        arr[:, :, 1] *= 0.75
    elif atmosphere == "flicker_light":
        arr *= 0.88

    # Heavy Dark Vignette Edges
    Y, X = np.ogrid[:H, :W]
    dist = np.sqrt(((X - W / 2) / (W / 2)) ** 2 + ((Y - H / 2) / (H / 2)) ** 2)
    vignette = np.clip(1.15 - 0.55 * (dist ** 1.6), 0.25, 1.0)
    arr *= vignette[:, :, np.newaxis]

    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))

# 3. Dynamic Camera Movement Engine
def apply_camera_motion(clip, motion, duration):
    if motion == "slow_push_in":
        return clip.resize(lambda t: 1.0 + 0.08 * (t / max(duration, 0.1)))
    elif motion == "slow_pull_out":
        return clip.resize(lambda t: 1.10 - 0.08 * (t / max(duration, 0.1)))
    elif motion == "handheld_shake":
        return clip.resize(1.08).set_position(
            lambda t: (int(12 * np.sin(18 * t)), int(10 * np.cos(23 * t)))
        )
    elif motion == "dutch_tilt_zoom":
        return clip.resize(lambda t: 1.05 + 0.12 * (t / max(duration, 0.1))).rotate(
            lambda t: 3.5 * np.sin(2 * t), expand=False
        )
    return clip  # static_eerie

# 4. Build Single Scene with 3-Layer Audio & Character Overlay
def render_scene(scene, assets_dir, temp_dir, voice="en-US-ChristopherNeural"):
    sid = scene["scene_id"]
    vo_path = os.path.join(temp_dir, f"vo_{sid}.mp3")
    vo_clip = generate_voice(scene["narration"], vo_path, voice=voice)
    dur = max(vo_clip.duration + 0.4, float(scene.get("duration_sec", 4)))

    # Background + Atmosphere
    bg_path = os.path.join(assets_dir, scene["background_asset"])
    bg_img = Image.open(bg_path) if os.path.exists(bg_path) else Image.new("RGB", (W, H), (12, 14, 20))
    graded_bg = apply_atmosphere(bg_img, scene.get("atmosphere", "dark_vignette"))
    bg_clip = ImageClip(np.array(graded_bg)).set_duration(dur)

    layers = [bg_clip]

    # Optional Character Layer (Transparent PNG)
    char_file = scene.get("character_asset")
    if char_file:
        char_path = os.path.join(assets_dir, char_file)
        if os.path.exists(char_path):
            char_clip = ImageClip(char_path).resize(height=int(H * 0.82)).set_duration(dur)
            pos_map = {"left": ("left", "bottom"), "right": ("right", "bottom"), "center": ("center", "bottom")}
            char_clip = char_clip.set_position(pos_map.get(scene.get("character_position", "center"), ("center", "bottom")))
            layers.append(char_clip)

    comp = CompositeVideoClip(layers, size=(W, H)).set_duration(dur)
    comp = apply_camera_motion(comp, scene.get("camera_motion", "slow_push_in"), dur)

    # 3-Layer Audio Mixing (Voice + Ambience + SFX)
    audio_tracks = [vo_clip.volumex(1.15)]

    amb_name = scene.get("ambience", "eerie_drone")
    amb_path = os.path.join(assets_dir, f"{amb_name}.mp3")
    if os.path.exists(amb_path):
        amb_clip = afx.audio_loop(AudioFileClip(amb_path), duration=dur).volumex(0.22)
        audio_tracks.append(amb_clip)

    sfx_name = scene.get("sfx", "none")
    if sfx_name and sfx_name != "none":
        sfx_path = os.path.join(assets_dir, f"{sfx_name}.mp3")
        if os.path.exists(sfx_path):
            sfx_clip = AudioFileClip(sfx_path).subclip(0, min(dur, AudioFileClip(sfx_path).duration)).volumex(0.75)
            audio_tracks.append(sfx_clip)

    comp = comp.set_audio(CompositeAudioClip(audio_tracks))
    return comp

# 5. Master 4-Part Checkpoint Renderer (Crash-Proof for 20-Min Videos)
def build_full_horror_video(json_path, assets_dir, output_video_path, voice="en-US-ChristopherNeural"):
    with open(json_path, "r", encoding="utf-8") as f:
        scenes = json.load(f)

    temp_dir = os.path.join(os.path.dirname(output_video_path), "temp_parts")
    os.makedirs(temp_dir, exist_ok=True)

    # Split into 4 checkpoints so long renders never crash Colab RAM
    chunks = np.array_split(scenes, min(4, len(scenes)))
    part_files = []

    for idx, chunk in enumerate(chunks, 1):
        part_path = os.path.join(temp_dir, f"part_{idx}.mp4")
        if os.path.exists(part_path):
            print(f"⏩ Part {idx} already rendered, skipping...")
            part_files.append(part_path)
            continue

        print(f"🎬 Rendering Part {idx}/{len(chunks)} ({len(chunk)} scenes)...")
        clips = [render_scene(s, assets_dir, temp_dir, voice=voice) for s in chunk]
        part_video = concatenate_videoclips(clips, method="compose")
        part_video.write_videofile(part_path, fps=24, codec="libx264", audio_codec="aac", threads=4)
        part_files.append(part_path)

    # Merge all parts into Final Master MP4
    from moviepy.editor import VideoFileClip
    final_clips = [VideoFileClip(p) for p in part_files]
    final_video = concatenate_videoclips(final_clips, method="compose")
    final_video.write_videofile(output_video_path, fps=24, codec="libx264", audio_codec="aac", threads=4)
    print(f"🔥 MASTER VIDEO READY: {output_video_path}")
  
