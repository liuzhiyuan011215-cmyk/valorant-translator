import os
import json

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

DEFAULT_CONFIG = {
    "api_base_url": "wss://generativelanguage.googleapis.com",
    "api_key": "",  # 每个人在「API 设置」里填自己的 Gemini API Key，只保存在本机 config.json（已加入 .gitignore）
    "stt_model": "models/gemini-3.5-live-translate-preview",
    "llm_model": "models/gemini-3.5-live-translate-preview",
    "stt_prompt": "Valorant Korean voice chat, A site, B site, mid, Gaepi, defuse, plant, rotate.",
    "llm_system_prompt": (
        "你是一个专业的 FPS 游戏《瓦罗兰特 / 无畏契约 (Valorant)》韩服实时语音同声传译员。\n"
        "任务：将队友的韩语 (Korean) 语音识别结果翻译为简练、地道、标准的中文游戏口语。\n"
        "要求：\n"
        "1. 保持极高时效性与简练度，保留常用战术术语（如 A包点/B包点/中路/回防/拆包/拉枪/架枪/起枪/保枪/残血 개피）。\n"
        "2. 如果输入已经是中文，进行整理使其更通顺；如果是韩语/外语，直接输出精炼中文翻译。\n"
        "3. 直接输出中文翻译结果，不要包含任何解释性文字。"
    ),
    "audio_device_index": None,
    "selected_device_name": "CABLE Output (VB-Audio Virtual Cable) [Windows WASAPI]",
    "vad_threshold": 0.015,
    "silence_duration_ms": 1000,
    "min_speech_duration_ms": 500,
    "overlay_font_size": 22,
    "overlay_opacity": 0.85,
    "overlay_display_time_sec": 6,
    "auto_start_listening": True,
    "chat_language": "ko",  # 按住 F8 说中文要翻成的语言：亚服 "en"（英语），韩服 "ko"（韩语）
    "overlay_locked": False,
    "overlay_x": 100,
    "overlay_y": 800,
    "overlay_width": 630,
    "overlay_height": 140,
    "mock_mode": False
}

class ConfigManager:
    def __init__(self):
        self.config = DEFAULT_CONFIG.copy()
        self.load_config()

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                    self.config.update(saved)
            except Exception as e:
                print(f"Error loading config: {e}")

    def save_config(self):
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Error saving config: {e}")

    def get(self, key, default=None):
        return self.config.get(key, default)

    def set(self, key, value):
        self.config[key] = value
        self.save_config()

config_mgr = ConfigManager()
