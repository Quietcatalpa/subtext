"""Subtext 潜台词：Laya 分析对方意图/情绪并给候选回复排序，可选用大模型 API 生成候选。

运行：conda run --no-capture-output -n laya python server.py
然后浏览器打开 http://127.0.0.1:7860
"""
import os
os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

import json
import re
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock

import laya

HOST, PORT = "127.0.0.1", 7860
MODEL = "convaiinnovations/laya-multilingual"
HERE = Path(__file__).parent

# 生成候选回复用的大模型（任何 OpenAI 兼容接口）。默认 DeepSeek，key 从环境变量读取。
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.deepseek.com/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "deepseek-chat")
LLM_API_KEY = os.environ.get("LLM_API_KEY") or os.environ.get("DEEPSEEK_API_KEY")

# ---------- Laya 要回答的问题 ----------

ANALYSIS_QUESTIONS = {
    "intent": {
        "type": "choice",
        "instructions": "对方最后几条消息想干什么？",
        "criteria": {
            "闲聊": "随便聊聊",
            "提问": "问问题、要信息",
            "求助": "请我帮忙、替他做事、顶班",
            "邀约": "约我出去玩、吃饭、见面",
            "要求": "布置任务、催我交东西",
            "吐槽": "抱怨、发牢骚",
            "分享": "分享见闻或好消息",
            "调侃": "开玩笑、逗我",
            "收尾": "客套、想结束对话",
        },
    },
    "emotion": {
        "type": "choice",
        "instructions": "对方现在是什么情绪？",
        "criteria": {
            "开心": "高兴、兴奋",
            "平静": "语气平常",
            "焦虑": "着急、担心",
            "生气": "不满、恼火",
            "难过": "低落、委屈",
            "无聊": "敷衍、没兴致",
        },
    },
    "joking": {"type": "noul", "instructions": "对方是不是在开玩笑？"},
}


def rank_questions(candidates, relation, style):
    extra = []
    if relation:
        extra.append("对方是我的%s" % relation)
    if style:
        extra.append("我希望回复%s" % style)
    ins = "我接下来发哪条回复最合适？"
    if extra:
        ins += "（%s）" % "，".join(extra)
    labels = "ABCDEFGH"
    return {
        "best": {
            "type": "choice",
            "instructions": ins,
            "criteria": {labels[i]: c for i, c in enumerate(candidates)},
        }
    }


# ---------- 模型 ----------

print("[Subtext] 正在加载 Laya 模型…", flush=True)
_t = time.perf_counter()
agent = laya.load(MODEL)
agent.predict("你好", ANALYSIS_QUESTIONS)  # 预热
print("[Subtext] 模型就绪（%.1f 秒）" % (time.perf_counter() - _t), flush=True)
lock = Lock()  # 一次只跑一个推理，避免显存争用


def parse_chat(text):
    """每行「对方：…」或「我：…」；没写前缀的行算对方说的。"""
    turns = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(r"^(我|对方|他|她|ta|TA)\s*[:：]\s*(.*)$", line)
        if m:
            who = "我" if m.group(1) == "我" else "对方"
            turns.append((who, m.group(2)))
        else:
            turns.append(("对方", line))
    return turns[-12:]  # 只看最近 12 句


def chat_state(turns, relation):
    lines = ["%s：%s" % (w, t) for w, t in turns]
    head = "（对方是我的%s）\n" % relation if relation else ""
    return head + "\n".join(lines)


def run_laya(state, questions):
    with lock:
        t = time.perf_counter()
        res = agent.predict(state, questions)
        return res["answers"], (time.perf_counter() - t) * 1000


def analyze(state):
    ans, ms = run_laya(state, ANALYSIS_QUESTIONS)
    return {
        "intent": ans["intent"],
        "emotion": ans["emotion"],
        "joking": ans["joking"]["noul"],
        "ms": round(ms, 1),
    }


def rank(state, candidates, relation, style):
    """优先用单选题让候选互相比较；太长放不下时退回逐条判断「合不合适」再归一化。"""
    try:
        ans, ms = run_laya(state, rank_questions(candidates, relation, style))
        probs = list(ans["best"]["probabilities"].values())
        method = "对比"
    except ValueError:
        qs = {
            "c%d" % i: {"type": "noul", "instructions": "我接下来回复「%s」合适吗？" % c[:120]}
            for i, c in enumerate(candidates)
        }
        ans, ms = run_laya(state, qs)
        raw = [ans["c%d" % i]["noul"] for i in range(len(candidates))]
        s = sum(raw) or 1.0
        probs = [r / s for r in raw]
        method = "逐条"
    items = [{"text": c, "prob": round(p, 4)} for c, p in zip(candidates, probs)]
    items.sort(key=lambda x: -x["prob"])
    return {"ranked": items, "ms": round(ms, 1), "method": method}


def generate(turns, relation, style, analysis):
    if not LLM_API_KEY:
        raise RuntimeError("没有配置大模型 API key，请用「自己写候选」模式，或按 README 配置 DEEPSEEK_API_KEY")
    convo = "\n".join("%s：%s" % (w, t) for w, t in turns)
    hint = "对方意图：%s；情绪：%s" % (analysis["intent"]["choice"], analysis["emotion"]["choice"])
    prompt = (
        "下面是我和对方的微信聊天记录。请以「我」的身份，写 3 条不同风格的下一句回复，"
        "每条不超过 40 个字，口语化、像真人发的微信，不要加引号或解释。\n"
        "对方是我的：%s\n希望的风格：%s\n%s\n\n聊天记录：\n%s\n\n"
        '只输出 JSON：{"replies": ["…", "…", "…"]}'
    ) % (relation or "朋友", style or "自然", hint, convo)
    body = json.dumps({
        "model": LLM_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 1.0,
        "response_format": {"type": "json_object"},
    }).encode()
    req = urllib.request.Request(
        LLM_BASE_URL.rstrip("/") + "/chat/completions", data=body,
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + LLM_API_KEY},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError("大模型接口报错 %d：%s" % (e.code, e.read().decode(errors="replace")[:200]))
    content = data["choices"][0]["message"]["content"]
    replies = json.loads(content).get("replies", [])
    return [str(x).strip() for x in replies if str(x).strip()][:5]


# ---------- 截图识别 ----------

_ocr = None
TIME_RE = re.compile(r"^(上午|下午|晚上|凌晨|中午|昨天|前天|星期.|周.|\d{1,4}[年/-]\d{1,2}[月/-]\d{1,2}日?)?\s*\d{1,2}:\d{2}$")


def get_ocr():
    global _ocr
    if _ocr is None:
        from rapidocr_onnxruntime import RapidOCR
        _ocr = RapidOCR()
    return _ocr


def is_green(px):
    """微信「我」的气泡：浅色模式 #95EC69，深色模式 #3EB575 一类的绿色。"""
    b, g, r = (int(x) for x in px)
    return g > 120 and g - r > 35 and g - b > 35


def ocr_chat(img_bytes):
    """识别微信聊天截图：按气泡颜色和左右位置判断谁说的，同一气泡的多行合并成一条。"""
    import cv2
    import numpy as np

    img = cv2.imdecode(np.frombuffer(img_bytes, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise RuntimeError("图片读不出来，换一张试试")
    h, w = img.shape[:2]
    result, _ = get_ocr()(img)
    lines = []
    for box, text, score in result or []:
        text = text.strip()
        if not text or float(score) < 0.5:
            continue
        xs, ys = [p[0] for p in box], [p[1] for p in box]
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        cx = (x0 + x1) / 2
        # 居中的灰字（时间、「以下是新消息」）不是聊天内容
        if TIME_RE.match(text) or (abs(cx - w / 2) < w * 0.12 and (x1 - x0) < w * 0.3 and len(text) <= 14):
            continue
        # 取文字左侧、气泡内边距处的像素判断颜色
        sx, sy = int(max(0, x0 - 4)), int(min(h - 1, (y0 + y1) / 2))
        if is_green(img[sy, sx]) or is_green(img[sy, int(min(w - 1, x1 + 4))]):
            who = "我"
        elif x0 > w * 0.5 or (x1 > w * 0.75 and x0 > w * 0.35):
            who = "我"
        else:
            who = "对方"
        lines.append({"who": who, "text": text, "y0": y0, "y1": y1, "x0": x0})
    lines.sort(key=lambda l: l["y0"])

    # 同一人、上下紧挨、左边对齐的行属于同一个气泡
    turns = []
    for l in lines:
        prev = turns[-1] if turns else None
        lh = l["y1"] - l["y0"]
        if (prev and prev["who"] == l["who"] and l["y0"] - prev["y1"] < lh * 0.8
                and abs(l["x0"] - prev["x0"]) < lh * 1.5):
            prev["text"] += l["text"]
            prev["y1"] = l["y1"]
        else:
            turns.append(dict(l))
    return [{"who": t["who"], "text": t["text"]} for t in turns]


# ---------- HTTP ----------

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, obj, ctype="application/json; charset=utf-8"):
        data = obj if isinstance(obj, bytes) else json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, (HERE / "index.html").read_bytes(), "text/html; charset=utf-8")
        elif self.path == "/api/config":
            self._send(200, {"llm": bool(LLM_API_KEY), "llm_model": LLM_MODEL})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        try:
            n = int(self.headers.get("Content-Length", 0))
            req = json.loads(self.rfile.read(n) or b"{}")
            if self.path == "/api/ocr":
                import base64
                data = req.get("image", "").split(",", 1)[-1]
                t = time.perf_counter()
                turns = ocr_chat(base64.b64decode(data))
                return self._send(200, {"turns": turns, "ms": round((time.perf_counter() - t) * 1000)})
            turns = parse_chat(req.get("chat", ""))
            if not turns:
                return self._send(400, {"error": "先粘贴一段聊天记录"})
            relation = req.get("relation", "").strip()
            style = req.get("style", "").strip()
            state = chat_state(turns, relation)

            if self.path != "/api/run":
                return self._send(404, {"error": "not found"})

            analysis = analyze(state)
            if req.get("mode") == "generate":
                t = time.perf_counter()
                candidates = generate(turns, relation, style, analysis)
                gen_ms = round((time.perf_counter() - t) * 1000)
            else:
                candidates = [c.strip() for c in req.get("candidates", []) if c.strip()][:8]
                gen_ms = None
            if not candidates:
                return self._send(400, {"error": "至少写一条候选回复"})
            ranking = rank(state, candidates, relation, style)
            self._send(200, {"analysis": analysis, "gen_ms": gen_ms, **ranking})
        except Exception as e:
            self._send(500, {"error": str(e)})


if __name__ == "__main__":
    get_ocr()  # 预加载截图识别模型
    print("[Subtext] 打开 http://%s:%d" % (HOST, PORT), flush=True)
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
