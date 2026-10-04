"""运行: python -m unittest discover tests"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ai.subtitle_assembler import SubtitleAssembler

# 真实录制：5 句韩语报点经修复后的录音链路推给 gemini-3.5-live-translate-preview，服务端返回的增量文本
REAL_SESSION = [
    (3.95, "IN", "A 사이트에 세 명 왔어요."),
    (4.12, "OUT", "A网站来了"),
    (4.64, "IN", " 조심"),
    (4.86, "OUT", "三个人。"),
    (5.66, "IN", " 하세요."),
    (5.75, "OUT", "小心点。"),
    (9.67, "IN", " 미드 한 명 개피예요."),
    (10.06, "OUT", "美剧有一个人"),
    (10.62, "IN", " 뒤 조심"),
    (10.77, "OUT", "残血了。"),
    (11.55, "IN", " 하세요."),
    (11.81, "OUT", "小心后面。"),
    (12.64, "IN", " 이로 리테이크 가요."),
    (12.81, "OUT", "我们去重新"),
    (13.62, "IN", " 지금"),
    (13.78, "OUT", "拿。现在"),
    (14.62, "IN", " 바로 가요."),
    (14.86, "OUT", "就去。"),
    (19.58, "IN", " 제가"),
    (19.81, "OUT", "我"),
    (20.50, "IN", " 설치할게요."),
    (20.86, "OUT", "来安装。"),
    (21.53, "IN", " 커버"),
    (21.86, "OUT", "掩护"),
    (22.53, "IN", " 부탁해요."),
    (22.78, "OUT", "一下。"),
    (26.55, "IN", " 상대"),
    (26.86, "OUT", "对方"),
    (27.41, "IN", " 오퍼가 미드에"),
    (27.52, "OUT", "的狙击手在"),
    (28.41, "IN", " 있어요."),
    (28.53, "OUT", "中路。"),
]


def run(session, until=None):
    """按 0.25s 一次 tick 回放（与 GeminiLiveStreamWorker 的接收循环一致），返回 (全部事件, 完结的字幕)。"""
    a = SubtitleAssembler()
    events, t, i = [], 0.0, 0
    until = until if until is not None else session[-1][0] + 5
    while t <= until:
        while i < len(session) and session[i][0] <= t:
            ts, kind, text = session[i]
            i += 1
            events += (a.add_input if kind == "IN" else a.add_output)(text, ts)
        events += a.tick(t)
        t += 0.25
    return events, [(o, tr) for o, tr, final in events if final]


class RealSessionTest(unittest.TestCase):
    def test_one_subtitle_per_sentence_with_matching_original(self):
        _, finals = run(REAL_SESSION)
        self.assertEqual(finals, [
            ("A 사이트에 세 명 왔어요.", "A网站来了三个人。"),
            ("조심 하세요.", "小心点。"),
            ("미드 한 명 개피예요.", "美剧有一个人残血了。"),
            ("뒤 조심 하세요.", "小心后面。"),
            ("이로 리테이크 가요.", "我们去重新拿。"),
            ("지금 바로 가요.", "现在就去。"),
            ("제가 설치할게요.", "我来安装。"),
            ("커버 부탁해요.", "掩护一下。"),
            ("상대 오퍼가 미드에 있어요.", "对方的狙击手在中路。"),
        ])

    def test_original_shows_up_before_translation(self):
        events, _ = run(REAL_SESSION, until=4.0)
        self.assertEqual(events, [("A 사이트에 세 명 왔어요.", "", False)])


class EdgeCaseTest(unittest.TestCase):
    def test_translation_without_punctuation_closes_after_idle(self):
        a = SubtitleAssembler(idle_close_sec=2.0)
        a.add_output("对方在A", 0.0)
        self.assertEqual(a.tick(1.9), [])
        self.assertEqual(a.tick(2.0), [("", "对方在A", True)])

    def test_untranslated_original_expires(self):
        a = SubtitleAssembler(pending_expire_sec=4.0)
        a.add_input("네.", 0.0)                       # 没有对应译文
        self.assertEqual(a.add_output("好的。", 5.0), [("", "好的。", True)])

    def test_two_sentences_in_one_chunk_become_two_subtitles(self):
        a = SubtitleAssembler()
        a.add_input("가자. 빨리.", 0.0)
        self.assertEqual(a.add_output("走。快点。", 0.5),
                         [("가자. 빨리.", "走。", True), ("", "快点。", True)])

    def test_stray_punctuation_does_not_create_subtitle(self):
        a = SubtitleAssembler()
        a.add_output("我来。", 0.0)
        self.assertEqual(a.add_output("。", 0.2), [])

    def test_rest_of_original_sentence_is_attached_to_running_subtitle(self):
        a = SubtitleAssembler()
        a.add_input("지금", 0.0)
        a.add_output("现在", 0.2)
        self.assertEqual(a.add_input(" 바로 가요. 상대", 0.4), [("지금 바로 가요.", "现在", False)])
        self.assertEqual(a.add_output("就去。", 0.6),
                         [("지금 바로 가요.", "现在就去。", True), ("상대", "", False)])


if __name__ == "__main__":
    unittest.main()
