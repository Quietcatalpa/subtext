"""从你自己的聊天记录里学说话风格。

my_style.jsonl 每行一条：{"context": [{"who": "对方|我", "text": ...}], "reply": "我实际回的话"}
用 build_corpus.py 从聊天截图生成。文件只存在本地，不会上传。
"""
import json
import re
from collections import Counter
from pathlib import Path

EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿]")
PUNCT = "。，！？、；：,.!?"
MAX_EXAMPLES = 6


def bigrams(s):
    s = re.sub(r"\s+", "", s)
    return {s[i:i + 2] for i in range(len(s) - 1)} or {s}


class Style:
    """加载语料、统计说话习惯、按相似度检索真实回复。文件变了会自动重新加载。"""

    def __init__(self, path):
        self.path = Path(path)
        self.samples, self.mtime = [], None
        self.reload()

    def reload(self):
        if not self.path.exists():
            self.samples, self.mtime = [], None
            return
        mtime = self.path.stat().st_mtime
        if mtime == self.mtime:
            return
        samples = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                s = json.loads(line)
            except ValueError:
                continue
            if s.get("reply"):
                s["_key"] = bigrams(" ".join(c["text"] for c in s.get("context", [])) + s["reply"])
                samples.append(s)
        self.samples, self.mtime = samples, mtime

    @property
    def ok(self):
        return len(self.samples) >= 20

    def profile(self):
        """把统计出来的习惯写成一段给大模型看的说明。"""
        replies = [s["reply"] for s in self.samples]
        n = len(replies)
        avg = sum(len(r) for r in replies) / n
        short = 100 * sum(1 for r in replies if len(r) <= 5) / n
        emoji = 100 * sum(1 for r in replies if EMOJI.search(r)) / n
        punct = 100 * sum(1 for r in replies if any(c in PUNCT for c in r)) / n
        openers = Counter(r[:2] for r in replies if len(r) >= 2)
        common = [k for k, v in openers.most_common(6) if v > 1]
        bits = ["平均每条 %.0f 个字，%.0f%% 的消息在 5 个字以内" % (avg, short)]
        bits.append("几乎不用标点" if punct < 20 else "会用标点" if punct > 60 else "偶尔用标点")
        bits.append("从不用 emoji" if emoji < 5 else "偶尔用 emoji（约 %.0f%%）" % emoji)
        if common:
            bits.append("常用开头：" + "、".join(common))
        return "；".join(bits)

    def examples(self, query, k=MAX_EXAMPLES):
        """挑出和当前对话最像的几段真实往来，按相似度从低到高排（最像的放最后，靠近指令）。"""
        q = bigrams(query)
        scored = []
        for s in self.samples:
            inter = len(q & s["_key"])
            if inter:
                scored.append((inter / (len(q | s["_key"]) ** 0.5), s))
        scored.sort(key=lambda x: -x[0])
        picked = [s for _, s in scored[:k]]
        if len(picked) < k:  # 相似的不够就随便补几条，让模型至少看到风格
            seen = {id(s) for s in picked}
            picked += [s for s in self.samples[-(k - len(picked)):] if id(s) not in seen]
        return list(reversed(picked))

    def examples_text(self, query, k=MAX_EXAMPLES):
        out = []
        for s in self.examples(query, k):
            ctx = "\n".join("%s：%s" % (c["who"], c["text"]) for c in s.get("context", [])[-2:])
            out.append("%s\n我：%s" % (ctx, s["reply"]) if ctx else "我：%s" % s["reply"])
        return "\n---\n".join(out)

    def max_len(self):
        replies = [len(s["reply"]) for s in self.samples]
        replies.sort()
        return max(12, int(replies[int(len(replies) * 0.9)]))  # 90 分位，别让它写得比你平时长太多
