"""从聊天截图生成风格语料 my_style.jsonl，供「像我说话」使用。

用法：
    python build_corpus.py 聊天记录            # 文件夹里放截图
    python build_corpus.py 聊天记录 -o my_style.jsonl --append

只提取「我」发的消息和它的上文，结果只写到本地文件，不会上传。
"""
import argparse
import json
import os
import re
import sys
from collections import Counter

os.environ.setdefault("USE_TF", "0")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿]")
PUNCT = "。，！？、；：,.!?"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src", help="放聊天截图的文件夹")
    ap.add_argument("-o", "--out", default="my_style.jsonl")
    ap.add_argument("--append", action="store_true", help="追加到已有语料后面")
    ap.add_argument("--context", type=int, default=4, help="每条保留几句上文")
    args = ap.parse_args()

    import server  # 加载模型需要几十秒

    samples, shots = [], 0
    for name in sorted(os.listdir(args.src)):
        if not name.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
            continue
        with open(os.path.join(args.src, name), "rb") as f:
            turns = server.ocr_chat(f.read())
        shots += 1
        print("  %-30s %2d 条" % (name[:30], len(turns)))
        for i, t in enumerate(turns):
            if t["who"] != "我" or not t["text"]:
                continue
            ctx = turns[max(0, i - args.context):i]
            if any(c["who"] == "对方" for c in ctx):
                samples.append({"context": [{"who": c["who"], "text": c["text"]} for c in ctx],
                                "reply": t["text"], "src": name})

    with open(args.out, "a" if args.append else "w", encoding="utf-8") as f:
        for s in samples:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")

    replies = [s["reply"] for s in samples]
    print("\n截图 %d 张 → 我的回复 %d 条 → 写入 %s" % (shots, len(replies), args.out))
    if replies:
        openers = Counter(r[:2] for r in replies if len(r) >= 2)
        print("平均 %.1f 字 · 5 字以内 %.0f%% · 含 emoji %.0f%% · 含标点 %.0f%%" % (
            sum(map(len, replies)) / len(replies),
            100 * sum(1 for r in replies if len(r) <= 5) / len(replies),
            100 * sum(1 for r in replies if EMOJI.search(r)) / len(replies),
            100 * sum(1 for r in replies if any(c in PUNCT for c in r)) / len(replies)))
        print("常用开头：", "、".join(k for k, v in openers.most_common(6) if v > 1))
    print("\n建议翻一遍生成的文件，把识别错的行删掉，再重启 Subtext。")


if __name__ == "__main__":
    main()
