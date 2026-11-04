# -*- coding: utf-8 -*-
"""文档转 Markdown 归档工作台（本地可视化）。

启动：双击 start.bat，或  python -m streamlit run app.py
"""
import json
import re
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

import streamlit as st

from core import extract as ex
from core import mdformat, titler
from core.classify import TAXONOMY, classify

APP_DIR = Path(__file__).parent
CONFIG_PATH = APP_DIR / "config.json"
LOG_PATH = APP_DIR / "archive_log.jsonl"
UPLOAD_DIR = APP_DIR / ".uploads"

st.set_page_config(page_title="文档转 MD 归档台", page_icon="📂", layout="wide")

IMG_TYPES = ["png", "jpg", "jpeg", "webp", "bmp", "tif", "tiff"]

st.markdown("""
<style>
.block-container {padding-top: 2.2rem; padding-bottom: 2rem; max-width: 1500px;}
h1 {font-size: 1.55rem !important; margin-bottom: .2rem !important;}
.sub {color: #6b7280; font-size: .85rem; margin-bottom: 1rem;}
.pill {display:inline-block; padding:2px 9px; border-radius:99px; font-size:.72rem;
       background:#eef2ff; color:#4338ca; margin-right:6px;}
.pill.warn {background:#fff7ed; color:#c2410c;}
.pill.ok {background:#ecfdf5; color:#047857;}
div[data-testid="stFileUploader"] section {padding: 1rem;}
</style>
""", unsafe_allow_html=True)


# ---------------- 配置 ----------------

def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"root": "", "use_ai": False, "model": "", "threshold": 0.45}


def save_config(cfg: dict) -> None:
    CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def log_archive(src: str, title: str, cat: str, dest: Path) -> None:
    rec = {"time": f"{datetime.now():%Y-%m-%d %H:%M:%S}", "src": src,
           "title": title, "category": cat, "dest": str(dest)}
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def list_categories(root: str) -> tuple[list[str], str]:
    """返回 (分类列表, 来源说明)。"""
    if root and Path(root).is_dir():
        dirs = sorted(p.name for p in Path(root).iterdir()
                      if p.is_dir() and not p.name.startswith((".", "__")))
        if dirs:
            return dirs, f"目录实读（{len(dirs)} 个）"
    return list(TAXONOMY.keys()), "内置模板"


def unique_path(folder: Path, title: str) -> Path:
    p = folder / f"{title}.md"
    i = 2
    while p.exists():
        p = folder / f"{title} ({i}).md"
        i += 1
    return p


def archive(root: str, cat: str, title: str, content: str, src_name: str) -> Path:
    folder = Path(root) / cat
    folder.mkdir(parents=True, exist_ok=True)
    dest = unique_path(folder, title)
    dest.write_text(content, encoding="utf-8")
    log_archive(src_name, title, cat, dest)
    return dest


def safe_text(s: str, n: int = 60) -> str:
    return (s or "").replace("\n", " ")[:n]


# ---------------- 侧边栏 ----------------

cfg = load_config()

st.sidebar.header("⚙️ 设置")

root_input = st.sidebar.text_input(
    "归档根目录", value=cfg.get("root", ""),
    placeholder=r"例如 D:\资料\经管-md输出",
    help="指向已有分类文件夹的目录；留空则使用内置 11 类模板",
)
if root_input != cfg.get("root", ""):
    cfg["root"] = root_input
    save_config(cfg)

categories, cat_source = list_categories(cfg.get("root", ""))
st.sidebar.caption(f"分类来源：{cat_source}")

if cfg.get("root") and not Path(cfg["root"]).is_dir():
    st.sidebar.warning("根目录不存在，将使用内置分类模板")

with st.sidebar.expander("分类清单", expanded=False):
    for c in categories:
        desc = TAXONOMY.get(c, {}).get("desc", "")
        st.markdown(f"**{c}**  \n<span style='color:#6b7280;font-size:.8rem'>{desc}</span>",
                    unsafe_allow_html=True)

st.sidebar.divider()
st.sidebar.subheader("AI 增强（可选）")

ai_alive = titler.ollama_alive()
models = titler.ollama_models() if ai_alive else []
if ai_alive:
    st.sidebar.markdown("<span class='pill ok'>Ollama 在线</span>", unsafe_allow_html=True)
else:
    st.sidebar.markdown("<span class='pill warn'>Ollama 未启动</span>", unsafe_allow_html=True)

use_ai = st.sidebar.toggle("用本地模型生成标题与分类", value=bool(cfg.get("use_ai")) and ai_alive,
                          disabled=not ai_alive)
default_model = cfg.get("model") or (models[0] if models else "")
model = st.sidebar.selectbox("模型", models or ["（无可用模型）"],
                             index=models.index(default_model) if default_model in models else 0,
                             disabled=not ai_alive)
st.sidebar.caption("关闭时使用离线规则引擎，速度快、不占显存")

if use_ai != cfg.get("use_ai") or model != cfg.get("model"):
    cfg["use_ai"], cfg["model"] = use_ai, model
    save_config(cfg)

st.sidebar.divider()
st.sidebar.subheader("归档策略")
threshold = st.sidebar.slider("低置信度提醒阈值", 0.0, 1.0, float(cfg.get("threshold", 0.45)), 0.05)
if threshold != cfg.get("threshold"):
    cfg["threshold"] = threshold
    save_config(cfg)
st.sidebar.caption("低于该值时不自动选定分类，提示人工确认")


# ---------------- 主区 ----------------

st.markdown("# 📂 文档转 MD 归档台")
st.markdown("<div class='sub'>读取文档或图片 → 转 Markdown → 自动起标题 → 归入最贴切的分类文件夹。原始文件不做任何改动。</div>",
            unsafe_allow_html=True)

tab_single, tab_batch, tab_log = st.tabs(["单文档处理", "批量处理", "归档记录"])


# ============ 单文档 ============

def run_single(src_path: Path, src_name: str) -> None:
    is_img = src_path.suffix.lower() in ex.SUPPORTED and src_path.suffix.lower() in IMG_TYPES
    with st.spinner("第 1 步：正在识别图片文字（OCR，约需数秒）…" if is_img else "第 1 步：正在提取文档内容…"):
        try:
            text = ex.extract(src_path)
        except ex.ExtractError as e:
            st.session_state["single"] = {"error": str(e), "name": src_name}
            return
    tip = ("第 2 步：本地模型正在生成标题与分类（约需 10~60 秒，请勿关闭页面）…"
           if use_ai else "第 2 步：正在生成标题与分类…")
    with st.spinner(tip):
        res = titler.suggest(text, src_name, categories, use_ai=use_ai, model=model)
        md = mdformat.build(text, res["title"], src_name)
        st.session_state["single"] = {
            "name": src_name, "text": text, "md": md, **res,
        }


with tab_single:
    c_up, c_path = st.columns([2, 1])
    with c_up:
        up = st.file_uploader(
            "拖入文档或图片（docx / pdf / xlsx / pptx / txt / md / csv / 图片）",
            type=["docx", "pdf", "xlsx", "xlsm", "pptx", "txt", "md", "csv"] + IMG_TYPES,
            key="up_single",
        )
    with c_path:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        path_in = st.text_input("或输入本地文件路径", placeholder=r"D:\资料\某某通知.docx")

    if up is not None:
        UPLOAD_DIR.mkdir(exist_ok=True)
        tmp = UPLOAD_DIR / up.name
        tmp.write_bytes(up.getvalue())
        if st.button("解析并生成", type="primary"):
            run_single(tmp, up.name)

    if path_in and not up:
        if st.button("解析并生成", type="primary"):
            run_single(Path(path_in), Path(path_in).name)

    data = st.session_state.get("single")

    if data and data.get("error"):
        st.error(f"解析失败：{data['error']}（{data['name']}）")

    elif data:
        st.divider()
        st.markdown(
            f"<span class='pill'>{data['source']}</span>"
            f"<span class='pill {'warn' if data.get('confidence', 0) < threshold else 'ok'}'>"
            f"置信度 {data.get('confidence', 0):.0%}</span>"
            f"<span class='pill'>约 {len(re.sub(chr(10), '', data['md']))} 字符</span>",
            unsafe_allow_html=True,
        )

        col_form, col_preview = st.columns([2, 3], gap="large")

        with col_form:
            st.subheader("归档信息")

            title = st.text_input("文档标题", value=data["title"], key="t_edit")
            st.caption(f"生成依据：{data.get('title_reason', '')}")

            idx = categories.index(data["category"]) if data["category"] in categories else 0
            cat = st.selectbox("归档分类", categories, index=idx, key="c_edit",
                               format_func=lambda x: f"{x}")
            st.caption(f"判断依据：{data.get('reason', '')}")

            cands = data.get("candidates", [])[:3]
            if cands:
                with st.expander("候选分类得分", expanded=False):
                    for c in cands:
                        st.markdown(
                            f"**{c['name']}** — {c['score']}  \n"
                            f"<span style='color:#6b7280;font-size:.8rem'>"
                            f"{'、'.join(c['matched'][:5])}</span>",
                            unsafe_allow_html=True)

            if data.get("ai_error"):
                st.warning(f"AI 增强失败，已回退规则引擎：{data['ai_error']}")

            if not cfg.get("root"):
                st.info("未设置归档根目录（在线使用时可只用下方「下载」保存文件）")
            else:
                st.caption(f"将写入：`{Path(cfg['root']) / cat / (title + '.md')}`")

            st.download_button(
                "📥 下载 .md 文件", data=data["md"].encode("utf-8"),
                file_name=f"{title.strip() or '文档'}.md", mime="text/markdown",
                use_container_width=True,
            )

            b1, b2 = st.columns(2)
            with b1:
                do_archive = st.button("✅ 归档", type="primary", use_container_width=True,
                                       disabled=not cfg.get("root") or not title.strip())
            with b2:
                if st.button("↩︎ 清空", use_container_width=True):
                    st.session_state.pop("single", None)
                    st.rerun()

            if do_archive:
                try:
                    dest = archive(cfg["root"], cat, title.strip(), data["md"], data["name"])
                    st.success(f"已归档 → {dest}")
                    st.session_state.pop("single", None)
                    st.session_state["last_dest"] = str(dest)
                except Exception as e:
                    st.error(f"写入失败：{e}")

        with col_preview:
            st.subheader("Markdown 预览")
            MAX_PREVIEW = 30000
            too_long = len(data["md"]) > MAX_PREVIEW
            if too_long:
                st.info(f"📄 文档较长（约 {len(data['md']):,} 字符），预览仅显示前 3 万字符；"
                        f"点「归档」仍会写入完整内容。")
            view = st.radio("视图", ["渲染效果", "源码（可编辑）"],
                            horizontal=True, label_visibility="collapsed",
                            disabled=too_long)
            if view == "渲染效果":
                display = re.sub(r"^\s*<!--[\s\S]*?-->\s*", "", data["md"])
                st.markdown(display[:MAX_PREVIEW])
            else:
                if too_long:
                    st.text_area("markdown", value=data["md"][:MAX_PREVIEW], height=430,
                                 label_visibility="collapsed", key="md_edit", disabled=True)
                else:
                    edited = st.text_area("markdown", value=data["md"], height=430,
                                          label_visibility="collapsed", key="md_edit")
                    data["md"] = edited


# ============ 批量 ============

with tab_batch:
    st.markdown("扫描一个文件夹，或一次拖入多个文档，统一生成标题与分类方案后再批量归档。")

    b1, b2 = st.columns([3, 1])
    with b1:
        folder_in = st.text_input("扫描文件夹", placeholder=r"D:\资料\待整理文档")
    with b2:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        recurse = st.checkbox("含子文件夹", value=False)

    ups = st.file_uploader("或拖入多个文件（支持图片）", type=["docx", "pdf", "xlsx", "xlsm", "pptx", "txt", "md", "csv"] + IMG_TYPES,
                           accept_multiple_files=True, key="up_batch")

    if st.button("🔍 扫描并生成方案", type="primary"):
        files: list[Path] = []
        if folder_in and Path(folder_in).is_dir():
            pattern = "**/*" if recurse else "*"
            files = [p for p in Path(folder_in).glob(pattern)
                     if p.is_file() and p.suffix.lower() in ex.SUPPORTED]
        if ups:
            UPLOAD_DIR.mkdir(exist_ok=True)
            for u in ups:
                t = UPLOAD_DIR / u.name
                t.write_bytes(u.getvalue())
                files.append(t)
        if not files:
            st.warning("没有找到可处理的文档")
        else:
            items, bar = [], st.progress(0.0, text="解析中…")
            for i, f in enumerate(files, 1):
                bar.progress(i / len(files), text=f"解析中… {f.name}")
                item = {"src": str(f), "name": f.name}
                try:
                    text = ex.extract(f)
                    res = titler.suggest(text, f.name, categories, use_ai=use_ai, model=model)
                    item.update({"ok": True, "title": res["title"], "category": res["category"],
                                 "confidence": res["confidence"],
                                 "md": mdformat.build(text, res["title"], f.name),
                                 "reason": res["reason"]})
                except ex.ExtractError as e:
                    item.update({"ok": False, "error": str(e), "title": "", "category": "",
                                 "confidence": 0.0, "md": "", "reason": ""})
                items.append(item)
            bar.empty()
            st.session_state["batch"] = items

    items = st.session_state.get("batch", [])
    if items:
        ok_items = [i for i in items if i["ok"]]
        bad_items = [i for i in items if not i["ok"]]

        m1, m2, m3 = st.columns(3)
        m1.metric("待归档", len(ok_items))
        m2.metric("解析失败", len(bad_items))
        low = sum(1 for i in ok_items if i["confidence"] < threshold)
        m3.metric("需人工确认", low)

        if bad_items:
            with st.expander(f"⚠️ {len(bad_items)} 个文件解析失败"):
                for i in bad_items:
                    st.markdown(f"- **{i['name']}**：{i['error']}")

        if ok_items:
            st.markdown("##### 方案表（标题与分类可直接改）")
            edited_rows = st.data_editor(
                [{"文件": i["name"], "标题": i["title"], "分类": i["category"],
                  "置信度": f"{i['confidence']:.0%}"} for i in ok_items],
                use_container_width=True, hide_index=True,
                column_config={
                    "分类": st.column_config.SelectboxColumn(options=categories, width="medium"),
                    "置信度": st.column_config.TextColumn(width="small"),
                },
                key="batch_table",
                disabled=["文件", "置信度"],
            )
            # 把表格里的修改回写到数据（按文件名匹配）
            if edited_rows:
                for row in edited_rows:
                    for i in ok_items:
                        if i["name"] == row["文件"]:
                            if row["标题"] != i["title"]:
                                i["title"] = row["标题"]
                                i["md"] = mdformat.retitle(i["md"], row["标题"])
                            i["category"] = row["分类"]

            with st.expander("逐条修正 / 预览内容"):
                pick = st.selectbox("选择文件", [i["name"] for i in ok_items])
                target = next(i for i in ok_items if i["name"] == pick)
                new_title = st.text_input("标题", value=target["title"], key=f"bt_{pick}")
                new_cat = st.selectbox("分类", categories,
                                       index=categories.index(target["category"])
                                       if target["category"] in categories else 0,
                                       key=f"bc_{pick}")
                md_too_long = len(target["md"]) > 30000
                if md_too_long:
                    st.info("📄 文档过长，内容编辑已禁用（归档仍保存完整内容），可修改标题与分类。")
                new_md = st.text_area("Markdown", value=target["md"][:30000] if md_too_long else target["md"],
                                      height=320, key=f"bm_{pick}", disabled=md_too_long)
                if st.button("保存该条修改"):
                    for i in ok_items:
                        if i["name"] == pick:
                            i["title"], i["category"] = new_title, new_cat
                            head = new_md.lstrip()
                            i["md"] = (mdformat.retitle(new_md, new_title)
                                       if head.startswith(("#", "<!--"))
                                       else mdformat.build(new_md, new_title, i["name"]))
                    st.success("已更新，可继续批量归档")
                    st.rerun()

            # 打包下载（在线使用的主要保存方式）
            import io, zipfile
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
                for i in ok_items:
                    z.writestr(f"{i['title'] or i['name']}.md", i["md"])
            st.download_button("📥 打包下载全部 .md（zip）", data=buf.getvalue(),
                               file_name="md归档.zip", mime="application/zip",
                               use_container_width=True)

            if not cfg.get("root"):
                st.info("未设置归档根目录：可只用上方「打包下载」保存结果")
            if st.button(f"🚀 全部归档（{len(ok_items)} 个）", type="primary",
                         disabled=not cfg.get("root")):
                done, fail = [], []
                for i in ok_items:
                    try:
                        d = archive(cfg["root"], i["category"], i["title"], i["md"], i["name"])
                        done.append((i["name"], d))
                    except Exception as e:
                        fail.append(f"{i['name']}：{e}")
                st.success(f"已归档 {len(done)} 个文件")
                if fail:
                    st.error("以下失败：\n" + "\n".join(fail))
                for name, d in done:
                    st.markdown(f"- `{name}` → `{d}`")
                st.session_state.pop("batch", None)


# ============ 记录 ============

with tab_log:
    st.markdown("### 归档记录")
    if LOG_PATH.exists():
        rows = [json.loads(l) for l in LOG_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]
        rows.reverse()
        st.caption(f"共 {len(rows)} 条，记录保存在 {LOG_PATH.name}")
        st.dataframe(rows[:300], use_container_width=True, hide_index=True)
        if st.button("清空上传缓存"):
            if UPLOAD_DIR.exists():
                shutil.rmtree(UPLOAD_DIR, ignore_errors=True)
            st.success("已清理")
    else:
        st.info("还没有归档记录")
