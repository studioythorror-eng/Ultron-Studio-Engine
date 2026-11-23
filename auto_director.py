import os
import json
import urllib.request
import google.generativeai as genai

# 1. Load Director Skills directly from GitHub
SKILL_URL = "https://raw.githubusercontent.com/studioythorror-eng/Ultron-Studio-Engine/main/director_skills.md"

def load_director_skills():
    with urllib.request.urlopen(SKILL_URL) as response:
        return response.read().decode("utf-8")

# 2. Convert Raw Story into Cinema-Grade JSON Scene Blueprint
def generate_scene_blueprint(story_text, gemini_api_key, output_json_path):
    genai.configure(api_key=gemini_api_key)
    skills = load_director_skills()
    
    prompt = f"""
{skills}

---
RAW HORROR STORY:
{story_text}
"""
    model = genai.GenerativeModel("gemini-2.5-flash")
    response = model.generate_content(prompt)
    
    raw_text = response.text.strip()
    if raw_text.startswith("```"):
        raw_text = raw_text.split("```")[1]
        if raw_text.startswith("json"):
            raw_text = raw_text[4:].strip()
            
    scenes = json.loads(raw_text)
    
    with open(output_json_path, "w", encoding="utf-8") as f:
        json.dump(scenes, f, indent=2, ensure_ascii=False)
        
    # Generate Asset Checklist
    bgs = sorted(list(set(s["background_asset"] for s in scenes)))
    chars = sorted(list(set(s["character_asset"] for s in scenes if s.get("character_asset"))))
    
    print(f"✅ Total Scenes Created: {len(scenes)}")
    print("📸 Required Backgrounds:", bgs)
    print("🧍 Required Characters:", chars)
    return scenes
  
