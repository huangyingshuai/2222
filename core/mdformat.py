# -*- coding: utf-8 -*-
"""把抽取出的文本整理成规范 Markdown。"""
import re
from datetime import datetime

_CN_NUM = r"[一二三四五六七八九十]+"
_HEAD_LINE = re.compile(rf"^({_CN_NUM})、\s*(.{{2,40}})$")
_HEAD_SUB = re.compile(rf"^（({_CN_NUM})）\s*(.{{2,40}})$")


def normalize(text: str) -> str:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out = []
    for raw in lines:
        line = raw.rstrip()
        if not line.strip():
            out.append("")
            continue
        # 纯编号小标题 -> Markdown 标题
        m = _HEAD_LINE.match(line.strip())
        if m and not line.strip().startswith("#"):
            cand = m.group(2).strip()
            if not cand.endswith(("。", "；", "，", ",", ";")):
                out.append(f"## {cand}")
                continue
        m2 = _HEAD_SUB.match(line.strip())
        if m2 and not line.strip().startswith("#"):
            cand = m2.group(2).strip()
            if not cand.endswith(("。", "；", "，", ",", ";")):
                out.append(f"### {cand}")
                continue
        out.append(line)

    text = "\n".join(out)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def build(text: str, title: str, source_name: str = "") -> str:
    """组装最终 Markdown：元信息注释 + 一级标题 + 正文。"""
    body = normalize(text)
    lines = body.split("\n")

    # 去掉正文开头的重复标题（标题行或纯文本行都可能重复）
    def _is_dup(s: str) -> bool:
        s = s.strip()
        if not s:
            return False
        h = re.sub(r"^#{1,4}\s+", "", s).strip()
        if s.startswith("#") and (h == title or (h and (h in title or title in h))):
            return True
        if h == title:
            return True
        return False

    while lines:
        if not lines[0].strip():
            lines.pop(0)
            continue
        if _is_dup(lines[0]):
            lines.pop(0)
            continue
        break

    body = "\n".join(lines).strip()
    # 正文内部多余的 H1 降级为 H2
    body = re.sub(r"(?m)^# ", "## ", body)

    meta = f"<!-- 源文件: {source_name} | 转换时间: {datetime.now():%Y-%m-%d %H:%M} -->"
    return f"{meta}\n\n# {title}\n\n{body}\n"


def stats(md: str) -> dict:
    plain = re.sub(r"[#|\-*>`\n\s]", "", md)
    return {"chars": len(plain), "headings": len(re.findall(r"(?m)^#{1,4} ", md))}


def retitle(md: str, title: str) -> str:
    """只替换 Markdown 的一级标题，正文保持不动。"""
    lines = md.split("\n")
    for idx, line in enumerate(lines):
        if line.startswith("# "):
            lines[idx] = f"# {title}"
            return "\n".join(lines)
    return f"# {title}\n\n{md}"
