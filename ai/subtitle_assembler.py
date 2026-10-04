"""
把 Live Translate 推送的两路增量文本（韩语原文 inputTranscription / 中文译文 outputTranscription）
切成一条条字幕。

实测 gemini-3.5-live-translate-preview 从不发送 turnComplete，并且服务端每隔约 1 秒就会推送
sessionResumptionUpdate / usageMetadata 等消息，所以既不能靠 turnComplete、也不能靠"一段时间收不到消息"
来断句 —— 只能看文本本身：译文出现句末标点，或者译文停止增长一段时间。
"""
import re
import time

_END = r'[.!?。！？…]+[\s"\'”’」』)）\]]*'
_PIECES = re.compile(rf'.*?{_END}|.+$', re.S)   # 按句末标点切开，标点留在前一段
_ENDS = re.compile(rf'{_END}$')


def _pieces(text: str) -> list:
    return [p for p in _PIECES.findall(text) if p]


def _ends_sentence(text: str) -> bool:
    return bool(_ENDS.search(text))


class SubtitleAssembler:
    """
    add_input / add_output / tick 返回事件列表 [(原文, 译文, is_final)]。
    is_final=False 表示更新"当前这一条"字幕；is_final=True 表示这一条已完结，下一条事件将开启新字幕。
    """

    def __init__(self, idle_close_sec: float = 2.0, pending_expire_sec: float = 4.0):
        self.idle_close_sec = idle_close_sec            # 译文停止增长多久后强制结束当前字幕
        self.pending_expire_sec = pending_expire_sec    # 原文多久没等到译文就丢弃（例如队友说的是中文）
        self.pending_orig = ""      # 已识别、但还没对应到译文的原文
        self.pending_time = 0.0
        self.cur_orig = None        # None 表示当前没有正在输出译文的字幕
        self.cur_trans = ""
        self.last_out_time = 0.0

    def add_input(self, text: str, now: float = None) -> list:
        now = time.monotonic() if now is None else now
        events = self.tick(now)
        pieces = _pieces(text)
        if not pieces:
            return events
        if self.cur_orig and not _ends_sentence(self.cur_orig):
            # 译文已经开始输出、但这句原文还没识别完：把这句剩下的部分补到当前字幕上
            self.cur_orig = (self.cur_orig + pieces.pop(0)).strip()
            events.append((self.cur_orig, self.cur_trans.strip(), False))
        if not pieces:
            return events
        if now - self.pending_time > self.pending_expire_sec:
            self.pending_orig = ""
        self.pending_orig += "".join(pieces)
        self.pending_time = now
        if self.cur_orig is None:
            events.append((self.pending_orig.strip(), "", False))  # 先把听到的原文显示出来
        return events

    def add_output(self, text: str, now: float = None) -> list:
        now = time.monotonic() if now is None else now
        events = self.tick(now)
        self.last_out_time = now
        for piece in _pieces(text):
            if self.cur_orig is None:
                if not re.search(r'\w', piece):
                    continue  # 上一句已结束后单独到来的标点
                # 新的一条译文开始：把目前积攒的原文整体归给它（只拿完整句子的话，一旦某句原文没被翻译，后面会整体错位）
                fresh = now - self.pending_time <= self.pending_expire_sec
                self.cur_orig = self.pending_orig.strip() if fresh else ""
                self.pending_orig = ""
            self.cur_trans += piece
            if _ends_sentence(self.cur_trans):
                events += self._close(now)
        if self.cur_orig is not None:
            events.append((self.cur_orig, self.cur_trans.strip(), False))
        return events

    def tick(self, now: float = None) -> list:
        now = time.monotonic() if now is None else now
        if self.cur_orig is not None and now - self.last_out_time >= self.idle_close_sec:
            return self._close(now)
        return []

    def _close(self, now: float) -> list:
        events = [(self.cur_orig, self.cur_trans.strip(), True)]
        self.cur_orig = None
        self.cur_trans = ""
        if self.pending_orig.strip() and now - self.pending_time <= self.pending_expire_sec:
            events.append((self.pending_orig.strip(), "", False))
        return events
