# -*- coding: utf-8 -*-
"""文档文本提取：把 docx/pdf/xlsx/pptx/txt/md/csv 统一抽成 Markdown 友好文本。"""
from pathlib import Path

SUPPORTED = {
    ".docx", ".pdf", ".xlsx", ".xlsm", ".pptx",
    ".txt", ".md", ".markdown", ".csv",
    ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff",
}


class ExtractError(Exception):
    pass


def _docx(path: Path) -> str:
    from docx import Document
    from docx.oxml.ns import qn
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    doc = Document(str(path))
    lines = []

    for child in doc.element.body.iterchildren():
        if child.tag == qn("w:p"):
            block = Paragraph(child, doc)
            text = block.text.strip()
            if not text:
                continue
            style = (block.style.name or "").lower()
            if "heading 1" in style or style.startswith("标题 1"):
                lines.append(f"## {text}")
            elif "heading 2" in style or style.startswith("标题 2"):
                lines.append(f"### {text}")
            elif "heading 3" in style or style.startswith("标题 3"):
                lines.append(f"#### {text}")
            elif "title" in style or style == "标题":
                lines.append(f"# {text}")
            else:
                lines.append(text)
        elif child.tag == qn("w:tbl"):
            block = Table(child, doc)
            rows = [[c.text.strip().replace("\n", " ") for c in row.cells] for row in block.rows]
            if rows and any(any(c for c in r) for r in rows):
                tbl = ["| " + " | ".join(rows[0]) + " |", "|" + "---|" * len(rows[0])]
                tbl += ["| " + " | ".join(r) + " |" for r in rows[1:]]
                lines.append("\n".join(tbl))
    return "\n\n".join(lines)


def _pdf(path: Path) -> str:
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    pages = []
    for i, page in enumerate(reader.pages):
        text = (page.extract_text() or "").strip()
        if text:
            pages.append(text)
    if not pages:
        raise ExtractError("PDF 未提取到文字，可能是扫描件/图片型 PDF")
    return "\n\n".join(pages)


def _xlsx(path: Path) -> str:
    from openpyxl import load_workbook
    wb = load_workbook(str(path), data_only=True, read_only=True)
    out = []
    for ws in wb.worksheets:
        rows = []
        for row in ws.iter_rows(values_only=True):
            if all(v is None or str(v).strip() == "" for v in row):
                continue
            rows.append(["" if v is None else str(v).strip() for v in row])
        if not rows:
            continue
        block = [f"### 工作表：{ws.title}", ""]
        head = rows[0]
        block.append("| " + " | ".join(head) + " |")
        block.append("|" + "---|" * len(head))
        for r in rows[1:500]:
            block.append("| " + " | ".join(r[: len(head)]) + " |")
        if len(rows) > 500:
            block.append(f"\n（共 {len(rows)} 行，仅显示前 500 行）")
        out.append("\n".join(block))
    wb.close()
    return "\n\n".join(out)


def _pptx(path: Path) -> str:
    from pptx import Presentation
    prs = Presentation(str(path))
    out = []
    for i, slide in enumerate(prs.slides, 1):
        parts = [f"### 第 {i} 页", ""]
        for shape in slide.shapes:
            if shape.has_text_frame:
                for para in shape.text_frame.paragraphs:
                    t = "".join(run.text for run in para.runs).strip()
                    if t:
                        parts.append(t)
            if getattr(shape, "has_table", False) and shape.has_table:
                rows = [[c.text.strip() for c in row.cells] for row in shape.table.rows]
                if rows:
                    parts.append("")
                    parts.append("| " + " | ".join(rows[0]) + " |")
                    parts.append("|" + "---|" * len(rows[0]))
                    parts += ["| " + " | ".join(r) + " |" for r in rows[1:]]
        out.append("\n".join(parts))
    return "\n\n".join(out)


def _plain(path: Path) -> str:
    for enc in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return path.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="replace")


def _csv(path: Path) -> str:
    import csv
    with open(path, "r", encoding="utf-8-sig", errors="replace", newline="") as f:
        rows = list(csv.reader(f))
    if not rows:
        return ""
    lines = ["| " + " | ".join(rows[0]) + " |", "|" + "---|" * len(rows[0])]
    lines += ["| " + " | ".join(r) + " |" for r in rows[1:500]]
    if len(rows) > 500:
        lines.append(f"\n（共 {len(rows)} 行，仅显示前 500 行）")
    return "\n".join(lines)


def _image(path: Path) -> str:
    from .ocr import OcrError, ocr_image
    try:
        return ocr_image(path)
    except OcrError as e:
        raise ExtractError(str(e)) from e


_HANDLERS = {
    ".docx": _docx, ".pdf": _pdf, ".xlsx": _xlsx, ".xlsm": _xlsx,
    ".pptx": _pptx, ".txt": _plain, ".md": _plain, ".markdown": _plain,
    ".csv": _csv,
}


def _register_images() -> None:
    try:
        from .ocr import IMG_EXTS
        for ext in IMG_EXTS:
            _HANDLERS[ext] = _image
    except ImportError:
        pass


_register_images()


def extract(path: Path) -> str:
    """抽取文本，失败抛 ExtractError。"""
    path = Path(path)
    if not path.exists():
        raise ExtractError(f"文件不存在：{path}")
    ext = path.suffix.lower()
    if ext in (".doc", ".xls"):
        raise ExtractError(f"{ext} 是旧格式，请先用 Office/WPS 另存为 {ext}x")
    handler = _HANDLERS.get(ext)
    if handler is None:
        raise ExtractError(f"不支持的格式：{ext}")
    try:
        text = handler(path)
    except ExtractError:
        raise
    except Exception as e:
        raise ExtractError(f"解析失败：{e}") from e
    if not text.strip():
        raise ExtractError("未提取到任何文字内容")
    return text.strip()
