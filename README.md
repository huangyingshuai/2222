# 文档转 MD 归档台

把 Word / PDF / Excel / PPT / TXT / 图片（OCR）转换为 Markdown，自动生成文档标题并推荐归档分类。

## 功能

- **格式支持**：docx / pdf / xlsx / pptx / txt / md / csv / png / jpg / jpeg / webp / bmp
- **图片 OCR**：本地离线识别（RapidOCR，支持中英文）
- **自动标题**：优先用文档原题；无题时按「年份 + 主题词 + 文种」生成；图片按识别首行取名
- **自动分类**：内置 11 类院系资料分类（专业建设、课程教材、学科竞赛……），关键词打分 + 置信度提示
- **输出**：在线点「下载 .md」或「打包下载 zip」；本地部署可归档到指定文件夹

## 部署到 Streamlit Cloud（免费）

1. 把本目录所有文件上传到你的 GitHub 仓库（public）
2. 打开 [share.streamlit.io](https://share.streamlit.io)，用 GitHub 账号登录
3. **New app** → 选择仓库和分支 → Main file path 填 `app.py` → **Deploy**
4. 等待几分钟（自动安装依赖），之后得到一个 `xxx.streamlit.app` 的链接，任何人可访问

> 云端版无本地 Ollama，AI 增强自动降级为离线规则引擎。
> 若有自己的 Ollama 服务器，部署时在 Advanced settings 添加环境变量 `OLLAMA_URL=http://你的地址:11434` 即可启用。

## 本地运行（Windows）

1. 安装 Python 3.10+
2. 命令行执行 `pip install -r requirements.txt`
3. 双击 `启动.bat`（或 `streamlit run app.py`），浏览器自动打开

## 说明

- 只新增 Markdown 文件，不改动原始文档
- 云端部署时建议仓库设为 public（Streamlit 免费版要求）；代码不含任何隐私数据
- 依赖中的 `opencv-python-headless` 是 Linux 服务器兼容处理，勿删
