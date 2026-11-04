# -*- coding: utf-8 -*-
"""标题生成：离线规则引擎 + 可选本地 Ollama 增强。"""
import json
import os
import re
from pathlib import Path

import requests

from .classify import TAXONOMY, classify

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")  # 可用环境变量指向远程 Ollama
_ILLEGAL = r'[\\/:*?"<>|\r\n\t]'
_GENERIC = {"通知", "公告", "目录", "附件", "表格", "说明", "前言", "摘要",
            "正文", "名单", "汇总表", "统计表", "文件", "文档", "无标题"}
_GENERIC_FILE = re.compile(
    r"(^(img|image|photo|pic|screenshot|shot|mmexport|wx|tmp|temp|untitled"
    r"|figure|scan)|新?建?(图片|位图|文本文档)|截图|微信图片|qq图片|屏幕截图)"
    r"[\d_\s\-\.]*$",
    re.IGNORECASE)
_SALUTATION = re.compile(r"各?[系部学院校处科室]{1,3}[：:，,\s]")


def clean_title(title: str, max_len: int = 40) -> str:
    t = re.sub(_ILLEGAL, " ", title or "").strip()
    t = re.sub(r"\s+", " ", t)
    t = t.strip(" -_·。.、，,")
    return t[:max_len].strip()


# ---------------- Ollama ----------------

def ollama_alive(timeout: float = 2.0) -> bool:
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=timeout)
        return r.status_code == 200
    except Exception:
        return False


def ollama_models() -> list[str]:
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=3)
        return [m["name"] for m in r.json().get("models", [])]
    except Exception:
        return []


def ollama_generate(prompt: str, model: str, timeout: float = 120.0) -> str:
    r = requests.post(
        f"{OLLAMA_URL}/api/generate",
        json={"model": model, "prompt": prompt, "stream": False,
              "options": {"temperature": 0.2, "num_predict": 240}},
        timeout=timeout,
    )
    r.raise_for_status()
    return r.json().get("response", "").strip()


def _extract_json(raw: str) -> dict | None:
    m = re.search(r"\{[\s\S]*\}", raw)
    if not m:
        return None
    for candidate in (m.group(0),):
        try:
            return json.loads(candidate)
        except Exception:
            continue
    return None


def ai_suggest(text: str, filename: str, categories: list[str],
               model: str, timeout: float = 120.0) -> dict:
    """调用本地模型给出标题 + 分类。失败时返回 {"error": ...}。"""
    cats = "\n".join(f"- {c}" for c in categories)

    def _ask(snippet: str) -> str:
        prompt = f"""你是高校经管院系的档案管理员。请阅读下面的文档内容，完成两件事：
1. 起一个最贴切的文档标题（中文，10-30字，不带扩展名，不含特殊符号）。
2. 从给定分类中选出最贴切的一个。

可选分类：
{cats}

文档名：{filename}

文档内容：
\"\"\"
{snippet}
\"\"\"

只输出 JSON，不要任何解释，格式：
{{"title": "标题", "category": "分类名", "reason": "一句话理由"}}"""
        return ollama_generate(prompt, model, timeout=timeout)

    snippet = re.sub(r"\n{2,}", "\n", text[:1500])
    try:
        raw = _ask(snippet)
        if not raw:                        # 部分模型偶尔返回空，用更短内容重试一次
            raw = _ask(snippet[:600])
    except Exception as e:
        return {"error": f"本地模型调用失败：{e}"}
    if not raw:
        return {"error": "本地模型返回为空，建议改用 qwen2.5-coder:7b 或关闭 AI 增强"}

    data = _extract_json(raw)
    if not data:
        return {"error": "模型返回格式无法解析", "raw": raw[:300]}
    title = clean_title(str(data.get("title", "")))
    cat = str(data.get("category", "")).strip()
    if cat not in categories:
        best = classify(text, filename)
        cat = best[0]["name"] if best else categories[0]
    return {"title": title, "category": cat,
            "reason": str(data.get("reason", ""))[:120]}


# ---------------- 离线规则 ----------------

def _first_heading(text: str) -> str | None:
    for line in text.splitlines()[:30]:
        s = line.strip()
        if not s:
            continue
        m = re.match(r"^#{1,3}\s+(.+)$", s)
        if m:
            cand = m.group(1).strip()
            if 3 <= len(cand) <= 45 and cand not in _GENERIC:
                return cand
            continue
        if len(s) <= 45 and not s.endswith(("。", "；", "，", ",", ";")):
            if s not in _GENERIC and re.search(r"(方案|通知|报告|总结|计划|办法|规定|纪要|名单|申请|表|书|大纲|细则|意见|函)$", s):
                return s
        break
    return None


def _year(text: str, filename: str) -> str:
    for src in (filename, text[:400]):
        m = re.search(r"(20\d{2})", src or "")
        if m:
            return m.group(1)
    return ""


def _doc_type(text: str, filename: str) -> str:
    blob = (filename or "") + "\n" + text[:1200]
    types = ["人才培养方案", "实施细则", "会议纪要", "申报书", "任务书", "统计表",
             "总结", "方案", "通知", "报告", "计划", "办法", "规定", "名单",
             "申请书", "大纲", "协议", "制度", "意见", "函", "表"]
    for t in types:
        if t in blob:
            return t
    return ""


def _subject(text: str, filename: str) -> str:
    """取文档主题词：优先用一级分类的关键词，其次文件名主干。"""
    cands = classify(text, filename)
    if cands and cands[0]["matched"]:
        kw = sorted(cands[0]["matched"], key=len, reverse=True)[0]
        return kw
    stem = Path(filename).stem if filename else ""
    stem = re.sub(r"^[\d\s_\-\.、]+|（?\d{4}）?年?|副本|最终版|修改版|\(?[0-9]+\)?$", "", stem)
    return stem[:20]


def guess_title(text: str, filename: str) -> tuple[str, str]:
    """返回 (标题, 理由)。"""
    heading = _first_heading(text)
    if heading:
        return clean_title(heading), "取自文档自带标题"

    stem = Path(filename).stem if filename else ""
    stem_clean = re.sub(r"[_\-]+", " ", stem).strip()
    stem_clean = re.sub(r"^\d+[\s\.]*", "", stem_clean).strip()
    # 无意义文件名（IMG_1234 / 微信图片 / 截图 等）：从正文首行找标题
    if _GENERIC_FILE.search(stem_clean or stem):
        first = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
        cand = _SALUTATION.split(first)[0].strip() if first else ""
        cand = re.sub(r"[「『“\"\']+", "", cand).strip()
        if 5 <= len(cand) <= 45 and not cand.endswith(("。", "；")):
            return clean_title(cand), "取自正文首行（文件名无意义）"

    generic_stem = (not stem_clean) or stem_clean in _GENERIC or len(stem_clean) < 4

    year = _year(text, filename)
    dtype = _doc_type(text, filename)
    subject = _subject(text, filename)

    if not generic_stem and len(stem_clean) <= 40:
        return clean_title(stem_clean), "沿用原文件名（已清理符号）"

    parts = [year, subject, dtype]
    title = "".join(p for p in parts if p) or "未命名文档"
    return clean_title(title), "由「年份 + 主题词 + 文种」组合生成"


def suggest(text: str, filename: str, categories: list[str],
            use_ai: bool = False, model: str = "") -> dict:
    """统一入口：返回 {title, category, reason, candidates, source, confidence}。"""
    from .classify import confidence

    title, t_reason = guess_title(text, filename)
    cands = classify(text, filename)
    # 只保留真实存在的分类
    cands = [c for c in cands if c["name"] in categories]
    cat = cands[0]["name"] if cands else (categories[0] if categories else "")
    reason = (f"命中关键词：{'、'.join(cands[0]['matched'][:4])}" if cands
              else "无明确关键词，需人工确认")
    conf = confidence(cands)
    out = {
        "title": title, "category": cat, "reason": reason,
        "title_reason": t_reason, "candidates": cands,
        "source": "规则引擎", "confidence": conf,
    }

    if use_ai and model:
        ai = ai_suggest(text, filename, categories, model)
        if "error" not in ai:
            if ai.get("title"):
                out["title"] = ai["title"]
                out["title_reason"] = "本地模型生成"
            out["category"] = ai["category"]
            out["reason"] = ai.get("reason") or out["reason"]
            out["source"] = f"本地模型 {model}"
            out["confidence"] = max(conf, 0.6)
        else:
            out["ai_error"] = ai["error"]
    return out
