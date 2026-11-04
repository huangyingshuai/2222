# -*- coding: utf-8 -*-
"""图片 OCR：基于 RapidOCR（本地离线，支持中英文，无需联网）。

首次识别会加载识别模型（约 2 秒），之后每张图约 1~3 秒。
"""
from pathlib import Path

IMG_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}

_ENGINE = None


class OcrError(Exception):
    pass


def _engine():
    global _ENGINE
    if _ENGINE is None:
        from rapidocr_onnxruntime import RapidOCR
        _ENGINE = RapidOCR()
    return _ENGINE


_CJK_END = tuple("。！？；：")


def _lines_to_text(lines: list[str]) -> str:
    """按行拼成段落：行尾是中文句读则断段，CJK 行间不加空格。"""
    paras: list[list[str]] = [[]]
    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        paras[-1].append(s)
        if s.endswith(_CJK_END):
            paras.append([])
    out = []
    for p in paras:
        if not p:
            continue
        joined = ""
        for s in p:
            if joined and (joined[-1].isascii() and s[0].isascii()):
                joined += " "
            joined += s
        out.append(joined)
    return "\n\n".join(out)


def ocr_image(path: Path) -> str:
    """识别图片文字，返回按段落整理的文本。失败抛 OcrError。"""
    path = Path(path)
    if not path.exists():
        raise OcrError(f"文件不存在：{path}")
    try:
        result, _ = _engine()(str(path))
    except Exception as e:
        raise OcrError(f"OCR 识别失败：{e}") from e
    if not result:
        raise OcrError("图片中未识别到文字（可能是纯照片/图形，或文字过小过糊）")
    lines = [str(item[1]).strip() for item in result if item and str(item[1]).strip()]
    text = _lines_to_text(lines)
    if not text:
        raise OcrError("图片中未识别到有效文字")
    return text
