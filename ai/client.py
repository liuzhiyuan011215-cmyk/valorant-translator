import io
import time
import json
import base64
import queue
import threading
import collections
import requests
import random
import asyncio
import websockets
from PySide6.QtCore import QThread, Signal, QObject

from config import config_mgr
from ai.gaming_prompts import VALORANT_KOREAN_SYSTEM_PROMPT
from ai.subtitle_assembler import SubtitleAssembler, _ends_sentence

LIVE_MODEL = "models/gemini-3.5-live-translate-preview"
LIVE_URL = ("wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta."
            "GenerativeService.BidiGenerateContent?key={api_key}")
SILENCE_100MS = b"\x00" * 3200  # 100 ms of 16 kHz 16-bit mono silence

MOCK_KOREAN_TACTICAL_PHRASES = [
    ("A 사이트 밀고 있어요! 조심하세요!", "敌人在大举压A点！小心！"),
    ("미드 한 명 개피! HP 20!", "中路残血一个！剩20血！"),
    ("B로 리테이크! 지금 B로 가자!", "转B包点回防！现在去B！"),
    ("밴달 한 자루만 드랍해 주세요!", "谁能给我发把狂潮(Vandal)？"),
    ("해체 중! 디퓨즈 디퓨즈! 커버해줘!", "正在拆包！拆包！掩护我！"),
    ("CT에서 뒤치기 온다! 뒤 조심!", "敌人从CT家绕后了！小心屁股！"),
    ("지르지 말고 시간 끌고 세이브 하자!", "别拉枪！拖时间保枪！"),
    ("A 가짜로 치고 B로 가자, 설 할게!", "假打A转B，准备下包！"),
    ("수고하셨습니다! 잘 하셨어요!", "大家辛苦了！打得好！")
]

class AIClient:
    def __init__(self):
        pass

    def process_audio(self, wav_bytes: bytes) -> tuple[str, str]:
        """Fallback mock processing."""
        time.sleep(0.3)
        orig, trans = random.choice(MOCK_KOREAN_TACTICAL_PHRASES)
        return f"[韩语] {orig}", f"[中文同传] {trans}"

    def test_connection(self) -> tuple[bool, str]:
        """Test connection to Google Gemini 3.5 Live Translate WebSocket Live API endpoint."""
        api_key = config_mgr.get("api_key", "").strip()

        if not api_key:
            return False, "API Key 未填写"

        async def _async_test():
            url = f"wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent?key={api_key}"
            setup_msg = {
                "setup": {
                    "model": "models/gemini-3.5-live-translate-preview",
                    "generationConfig": {
                        "responseModalities": ["AUDIO"],
                        "translationConfig": {
                            "targetLanguageCode": "zh-Hans",
                            "echoTargetLanguage": False
                        }
                    },
                    "inputAudioTranscription": {},
                    "outputAudioTranscription": {}
                }
            }
            start_t = time.time()
            async with websockets.connect(url, open_timeout=8) as ws:
                await ws.send(json.dumps(setup_msg))
                resp = await ws.recv()
                latency = int((time.time() - start_t) * 1000)
                resp_json = json.loads(resp)
                if "setupComplete" in resp_json or "setup_complete" in resp_json:
                    return True, f"Gemini 3.5 Live Translate (官方同传 WebSocket API - 0/无限制 RPM) 握手成功！延迟: {latency} ms"
                else:
                    return False, f"WebSocket 握手响应: {resp}"

        try:
            return asyncio.run(_async_test())
        except Exception as e:
            print(f"WebSocket connection test failed: {e}")
            return False, f"WebSocket 连线失败: {e}"


class GeminiLiveStreamWorker(QThread):
    """
    Gemini 3.5 Live Translate streaming worker (teammates' Korean -> Chinese subtitles).

    Google ends every Live connection after about 10 minutes and sends goAway shortly before.
    On goAway we immediately open the next connection with the session-resumption handle,
    switch new audio to it, and let the old connection finish delivering its last words, so a
    callout spanning the switch is not cut. On an unexpected disconnect we reconnect right away
    and keep only the last 3 s of audio meanwhile, so stale callouts don't pop up late.
    """
    translation_received = Signal(str, str, bool) # original, translated, is_final
    status_changed = Signal(str)

    TARGET_LANGUAGE = "zh-Hans"
    ECHO_TARGET_LANGUAGE = False

    def __init__(self, parent=None):
        super().__init__(parent)
        self.audio_queue = queue.Queue(maxsize=100)
        self.running = False
        self.loop = None
        self.assembler = SubtitleAssembler()
        self.target_language = self.TARGET_LANGUAGE
        self.active_ws = None        # connection that receives new audio
        self.resume_handle = None    # latest session-resumption handle from the server

    def put_audio(self, pcm_bytes: bytes):
        """Enqueue 16kHz PCM audio chunk for real-time streaming."""
        try:
            self.audio_queue.put_nowait(pcm_bytes)
        except queue.Full:
            pass

    def stop(self):
        self.running = False

    def run(self):
        self.running = True
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._websocket_loop())

    def _setup_message(self) -> dict:
        return {
            "setup": {
                "model": LIVE_MODEL,
                "generationConfig": {
                    "responseModalities": ["AUDIO"],
                    "translationConfig": {
                        "targetLanguageCode": self.target_language,
                        "echoTargetLanguage": self.ECHO_TARGET_LANGUAGE
                    }
                },
                "inputAudioTranscription": {},
                "outputAudioTranscription": {},
                # Resume the previous session's context when switching connections
                "sessionResumption": {"handle": self.resume_handle} if self.resume_handle else {},
                # Sliding-window context compression; audio-only sessions otherwise end after 15 minutes
                "contextWindowCompression": {"slidingWindow": {}}
            }
        }

    async def _connect(self, url: str):
        ws = await websockets.connect(url, open_timeout=8, max_size=None)
        try:
            await ws.send(json.dumps(self._setup_message()))
            resp = json.loads(await asyncio.wait_for(ws.recv(), timeout=8))
        except Exception:
            await ws.close()
            raise
        if "setupComplete" not in resp and "setup_complete" not in resp:
            await ws.close()
            raise RuntimeError(f"握手失败: {str(resp)[:120]}")
        return ws

    async def _websocket_loop(self):
        api_key = config_mgr.get("api_key", "").strip()
        if not api_key:
            return

        url = LIVE_URL.format(api_key=api_key)
        self.go_away = asyncio.Event()
        self.pending_audio = collections.deque(maxlen=30)  # at most 3 s buffered while disconnected
        sender = asyncio.create_task(self._send_audio_loop())
        ticker = asyncio.create_task(self._tick_loop())
        readers = set()
        retry_delay = 0.5

        try:
            while self.running:
                if self.active_ws is None:
                    self.status_changed.emit("正在连接同传服务…")
                try:
                    ws = await self._connect(url)
                except Exception as e:
                    print(f"Gemini Live connect failed: {e}")
                    if not self.running:
                        break
                    self.status_changed.emit(f"重连中… ({e})")
                    await asyncio.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, 8.0)
                    continue

                retry_delay = 0.5
                self.go_away.clear()
                old_ws, self.active_ws = self.active_ws, ws  # new audio goes to the new connection from now on
                if old_ws is not None:
                    # The old connection got goAway: give it 5 s to deliver its last words, then close it
                    # ourselves (otherwise the server aborts it ~50 s later with 1008 policy violation).
                    closer = asyncio.create_task(self._close_later(old_ws, 5.0))
                    readers.add(closer)
                    closer.add_done_callback(readers.discard)
                self.status_changed.emit("同传已就绪")

                reader = asyncio.create_task(self._receive_loop(ws))
                readers.add(reader)
                reader.add_done_callback(readers.discard)
                go_away = asyncio.create_task(self.go_away.wait())
                done, _ = await asyncio.wait({reader, go_away, sender}, return_when=asyncio.FIRST_COMPLETED)
                go_away.cancel()
                if go_away in done:
                    print("Gemini Live goAway received, switching to a new connection")
                elif reader in done:
                    print("Gemini Live connection closed, reconnecting")
        finally:
            for task in [sender, ticker, *readers]:
                task.cancel()
            if self.active_ws is not None:
                try:
                    await self.active_ws.close()
                except Exception:
                    pass

    @staticmethod
    async def _close_later(ws, delay: float):
        await asyncio.sleep(delay)
        try:
            await ws.close()
        except Exception:
            pass

    @staticmethod
    def _audio_message(pcm_bytes: bytes) -> str:
        return json.dumps({
            "realtimeInput": {
                "audio": {
                    "mimeType": "audio/pcm;rate=16000",
                    "data": base64.b64encode(pcm_bytes).decode('utf-8')
                }
            }
        })

    async def _send_audio_loop(self):
        while self.running:
            try:
                pcm_bytes = await self.loop.run_in_executor(None, self.audio_queue.get, True, 0.1)
            except queue.Empty:
                continue

            self.pending_audio.append(pcm_bytes)
            ws = self.active_ws
            if ws is None:
                continue  # disconnected: keep the latest audio and send it after reconnecting
            try:
                while self.pending_audio:
                    await ws.send(self._audio_message(self.pending_audio[0]))
                    self.pending_audio.popleft()
            except Exception as e:
                print(f"Send audio error: {e}")  # unsent audio stays queued for the next connection

    async def _tick_loop(self):
        # Regular ticks so a stalled subtitle still gets closed when no message arrives
        while self.running:
            await asyncio.sleep(0.25)
            self._on_tick()

    async def _receive_loop(self, ws):
        try:
            async for msg_str in ws:
                data = json.loads(msg_str)
                if ("goAway" in data or "go_away" in data) and ws is self.active_ws:
                    self.go_away.set()

                update = data.get("sessionResumptionUpdate") or data.get("session_resumption_update") or {}
                if update.get("resumable") and update.get("newHandle"):
                    self.resume_handle = update["newHandle"]

                server_content = data.get("serverContent") or data.get("server_content") or {}

                # 1. Input transcription (recognized original speech)
                in_tx = server_content.get("inputTranscription") or server_content.get("input_transcription")
                if in_tx and in_tx.get("text"):
                    self._on_text("in", in_tx["text"])

                # 2. Output transcription (translated text from Gemini 3.5 Live Translate)
                out_tx = server_content.get("outputTranscription") or server_content.get("output_transcription")
                if out_tx and out_tx.get("text"):
                    self._on_text("out", out_tx["text"])

                # Check modelTurn parts
                model_turn = server_content.get("modelTurn") or server_content.get("model_turn")
                if model_turn and model_turn.get("parts"):
                    for part in model_turn["parts"]:
                        if part.get("text"):
                            self._on_text("out", part["text"])
        except Exception as e:
            print(f"Receive WS message error: {e}")
        finally:
            if self.active_ws is ws:
                self.active_ws = None

    # This model never sends turnComplete, and the server keeps pushing sessionResumptionUpdate /
    # usageMetadata about every second even in silence, so sentence splitting is decided from the
    # transcription text itself (see SubtitleAssembler).
    def _on_text(self, kind: str, text: str):
        events = self.assembler.add_input(text) if kind == "in" else self.assembler.add_output(text)
        self._emit(events)

    def _on_tick(self):
        self._emit(self.assembler.tick())

    def _emit(self, events):
        for orig, trans, is_final in events:
            self.translation_received.emit(orig, trans, is_final)


class MicTranslateWorker(GeminiLiveStreamWorker):
    """
    Hold F8 and speak Chinese -> English (Asia server) or Korean (KR server) text for the clipboard,
    using the model's own translation.
    Same connection handling as above, but audio only flows while F8 is held. After release we keep
    feeding silence in real time until the Korean is complete: the model finishes a sentence only after
    it has heard time pass, and with a one-off 3 s burst a slower translation stalled mid-sentence
    until the next F8 press. The phrase is handed over once the text stops growing.
    """
    phrase_updated = Signal(str, str)  # recognized Chinese, translation (live)
    phrase_done = Signal(str, str)     # final result; the main window copies the translation

    TARGET_LANGUAGE = "ko"
    ECHO_TARGET_LANGUAGE = True  # speaking the target language directly is transcribed as-is and can be copied too

    def __init__(self, target_language: str = "ko", parent=None):
        super().__init__(parent)
        self.target_language = target_language  # "en" for the Asia server, "ko" for the KR server
        self.zh = self.ko = ""
        self.holding = False
        self.released_at = None
        self.last_text_at = 0.0

    def begin_phrase(self):
        """F8 pressed (called from the GUI thread)."""
        for _ in range(5):
            self.put_audio(SILENCE_100MS)  # 0.5 s lead-in: speech right at the start of the stream lost its first word in tests
        if self.loop is not None:
            self.loop.call_soon_threadsafe(self._begin)

    def end_phrase(self):
        """F8 released (called from the GUI thread)."""
        if self.loop is not None:
            self.loop.call_soon_threadsafe(self._end)

    def _begin(self):
        if self.released_at is not None:
            self._finish()  # pressed again while the previous phrase was finishing: hand that one over first
        self.zh = self.ko = ""
        self.holding = True
        self.last_text_at = time.monotonic()

    def _end(self):
        if not self.holding:
            return
        self.holding = False
        self.released_at = time.monotonic()
        for _ in range(10):
            self.put_audio(SILENCE_100MS)  # 1 s at once: short phrases finish sooner (burst flushed 0.3-0.6 s faster)
        self.loop.create_task(self._trailing_silence(self.released_at))

    async def _trailing_silence(self, released_at: float):
        # ...then keep the model's clock running in real time until this phrase is handed over (max 8 s)
        while self.released_at == released_at and time.monotonic() - released_at < 8.0:
            self.put_audio(SILENCE_100MS)
            await asyncio.sleep(0.1)

    def _on_text(self, kind: str, text: str):
        if not self.holding and self.released_at is None:
            return  # outside a phrase
        if kind == "out" and not self.zh:
            return  # Korean before any Chinese of this phrase: a leftover of the previous phrase
        if kind == "in":
            self.zh += text
        else:
            self.ko += text
        self.last_text_at = time.monotonic()
        self.phrase_updated.emit(self.zh.strip(), self.ko.strip())

    def _on_tick(self):
        if self.released_at is None:
            return
        now = time.monotonic()
        idle = now - max(self.last_text_at, self.released_at)
        zh, ko = self.zh.strip(), self.ko.strip()
        # Complete when both the Chinese and the Korean end a sentence; otherwise wait longer
        # (silence keeps flowing meanwhile so the model can finish the tail).
        complete = _ends_sentence(zh) and _ends_sentence(ko)
        if (ko and idle >= (0.6 if complete else 2.5)) or now - self.released_at >= 8.0:
            self._finish()

    def _finish(self):
        self.released_at = None
        self.phrase_done.emit(self.zh.strip(), self.ko.strip())
