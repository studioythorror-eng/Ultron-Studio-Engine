import os
import json
import subprocess
import asyncio
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter
from rembg import remove
import edge_tts
from moviepy.editor import (
    ImageClip, VideoFileClip, AudioFileClip, CompositeVideoClip,
    CompositeAudioClip, concatenate_videoclips, afx
)

W, H = 1920, 1080

# 1. Studio Neural Voiceover Generator (Free)
async def _tts_async(text, voice, out_path):
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(out_path)

def generate_voice(text, out_path, voice="hi-IN-SwaraNeural"):
    asyncio.run(_tts_async(text, voice, out_path))
    return AudioFileClip(out_path)

# 2. Auto Cutout White Background -> Clean Transparent Character PNG
def prepare_character_cutout(raw_char_path, clean_char_path):
    if os.path.exists(clean_char_path):
        return clean_char_path
    with open(raw_char_path, "rb") as i:
        output_bytes = remove(i.read())
    with open(clean_char_path, "wb") as o:
        o.write(output_bytes)
    return clean_char_path

# 3. Crop Face Portrait for AI Eye-Blink, Eyebrow & Lip-Sync Model
def extract_face_portrait(clean_char_path, face_out_path, bg_color=(18, 22, 32)):
    img = Image.open(clean_char_path).convert("RGBA")
    bbox = img.getbbox()
    if bbox:
        img = img.crop(bbox)
    cw, ch = img.size
    # Upper 38% focuses on face + shoulders for SadTalker/LivePortrait
    face_crop = img.crop((0, 0, cw, int(ch * 0.38)))
    size = max(face_crop.size)
    canvas = Image.new("RGBA", (size, size), (*bg_color, 255))
    offset = ((size - face_crop.width) // 2, (size - face_crop.height) // 2)
    canvas.paste(face_crop, offset, face_crop)
    canvas.convert("RGB").resize((512, 512), Image.LANCZOS).save(face_out_path)
    return face_out_path

# 4. Run SadTalker AI (Eye-Blink, Eyebrow Motion, Head Tilt & Lip-Sync)
def animate_talking_face(face_img_path, audio_path, out_dir, sadtalker_dir="/content/SadTalker"):
    cmd = [
        "python", f"{sadtalker_dir}/inference.py",
        "--driven_audio", audio_path,
        "--source_image", face_img_path,
        "--result_dir", out_dir,
        "--still",
        "--preprocess", "full",
        "--enhancer", "gfpgan"
    ]
    subprocess.run(cmd, check=True)
    # Find newest generated mp4
    mp4s = []
    for root, _, files in os.walk(out_dir):
        for f in files:
            if f.endswith(".mp4"):
                full_p = os.path.join(root, f)
                mp4s.append((os.path.getmtime(full_p), full_p))
    mp4s.sort(reverse=True)
    return mp4s[0][1]

# 5. Scary Pumpkin Night Grading & Flicker Lighting
def grade_horror_bg(img_pil, atmosphere, t=0.0):
    img = img_pil.convert("RGB").resize((W, H), Image.LANCZOS)
    img = ImageEnhance.Contrast(img).enhance(1.25)
    img = ImageEnhance.Color(img).enhance(0.72)
    arr = np.array(img, dtype=np.float32)

    if atmosphere == "rain_night":
        arr[:, :, 0] *= 0.72
        arr[:, :, 2] *= 1.18
    elif atmosphere == "flicker_light":
        flicker = 0.85 + 0.15 * np.sin(24 * t) * np.cos(11 * t)
        arr *= flicker
    else:  # dark_vignette
        arr[:, :, 0] *= 0.82
        arr[:, :, 2] *= 1.10

    Y, X = np.ogrid[:H, :W]
    dist = np.sqrt(((X - W / 2) / (W / 2)) ** 2 + ((Y - H / 2) / (H / 2)) ** 2)
    vignette = np.clip(1.12 - 0.58 * (dist ** 1.5), 0.22, 1.0)
    arr *= vignette[:, :, np.newaxis]
    return np.clip(arr, 0, 255).astype(np.uint8)

# 6. Build Single Scene (Lip-Sync AI OR 2.5D Multi-Layer Puppet)
def render_scary_scene(scene, assets_dir, temp_dir, voice="hi-IN-SwaraNeural"):
    sid = scene["scene_id"]
    vo_path = os.path.join(temp_dir, f"vo_{sid}.mp3")
    vo_clip = generate_voice(scene["narration"], vo_path, voice=voice)
    dur = max(vo_clip.duration + 0.35, float(scene.get("duration_sec", 4)))

    bg_path = os.path.join(assets_dir, scene["background_asset"])
    bg_pil = Image.open(bg_path) if os.path.exists(bg_path) else Image.new("RGB", (W, H), (12, 15, 24))
    atm = scene.get("atmosphere", "dark_vignette")

    # Background Clip with Flicker/Night Grade
    if atm == "flicker_light":
        bg_clip = ImageClip(grade_horror_bg(bg_pil, atm, 0)).fl(
            lambda gf, t: grade_horror_bg(bg_pil, atm, t)
        ).set_duration(dur)
    else:
        bg_clip = ImageClip(grade_horror_bg(bg_pil, atm, 0)).set_duration(dur)

    anim_type = scene.get("animation_type", "action_puppet")
    char_file = scene.get("character_asset")

    # MODE A: AI Talking Face (Eye-Blink + Eyebrow + Lip-Sync)
    if anim_type == "talking_lipsync" and char_file:
        raw_char = os.path.join(assets_dir, char_file)
        clean_char = os.path.join(temp_dir, f"clean_{char_file}.png")
        face_img = os.path.join(temp_dir, f"face_{char_file}.png")
        prepare_character_cutout(raw_char, clean_char)
        extract_face_portrait(clean_char, face_img)

        talk_out = os.path.join(temp_dir, f"talk_s{sid}")
        os.makedirs(talk_out, exist_ok=True)
        talk_mp4 = animate_talking_face(face_img, vo_path, talk_out)
        comp = VideoFileClip(talk_mp4).resize((W, H)).set_duration(dur)

    # MODE B: 2.5D Multi-Layer Puppet (Breathing, Sway & Depth Separation)
    else:
        layers = [bg_clip.resize(lambda t: 1.0 + 0.03 * (t / max(dur, 0.1)))]
        if char_file:
            raw_char = os.path.join(assets_dir, char_file)
            clean_char = os.path.join(temp_dir, f"clean_{char_file}.png")
            prepare_character_cutout(raw_char, clean_char)

            framing = scene.get("framing", "medium_shot")
            scale_h = int(H * (1.35 if framing == "medium_shot" else 0.85))
            char_clip = ImageClip(clean_char).resize(height=scale_h).set_duration(dur)

            # Subtle 2.5D breathing & eerie sway
            char_clip = char_clip.resize(lambda t: 1.0 + 0.015 * np.sin(2.5 * t))
            pos_x = {"left": 180, "right": W - 780, "center": (W - char_clip.w) // 2}.get(
                scene.get("character_position", "center"), (W - char_clip.w) // 2
            )
            base_y = H - char_clip.h + (280 if framing == "medium_shot" else 20)
            char_clip = char_clip.set_position(lambda t: (pos_x + int(6 * np.sin(1.8 * t)), base_y))
            layers.append(char_clip)

        comp = CompositeVideoClip(layers, size=(W, H)).set_duration(dur)

    # 3-Layer Horror Audio Mixing
    audio_tracks = [vo_clip.volumex(1.2)]
    for track_key, vol in [("ambience", 0.25), ("sfx", 0.75)]:
        t_name = scene.get(track_key, "none")
        if t_name and t_name != "none":
            t_path = os.path.join(assets_dir, f"{t_name}.mp3")
            if os.path.exists(t_path):
                a_clip = AudioFileClip(t_path)
                if track_key == "ambience":
                    a_clip = afx.audio_loop(a_clip, duration=dur).volumex(vol)
                else:
                    a_clip = a_clip.subclip(0, min(dur, a_clip.duration)).volumex(vol)
                audio_tracks.append(a_clip)

    return comp.set_audio(CompositeAudioClip(audio_tracks))
                                      
