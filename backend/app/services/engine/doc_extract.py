"""文档文本提取（本地解析，免费、不上传第三方）。

支持：PDF（文本型 + 扫描件 OCR 兜底）/ DOCX / TXT / 图片（PNG/JPG/WebP/BMP 等 OCR）。
- DOCX 直接解析 document.xml（含文本框内容），老版 .doc 明确提示另存
- 扫描件/纯图片：内置 RapidOCR 本地识别（pypdfium2 渲染 PDF 页面）；
  引擎不可用时给出明确原因
"""
from __future__ import annotations

import html
import io
import re
import zipfile

from pypdf import PdfReader

from .ocr import (
    IMAGE_FORMATS,
    OCRError,
    PDF_TEXT_MIN,
    ocr_image_bytes,
    ocr_pdf_pages,
)


class DocExtractError(Exception):
    pass


def extract_text(filename: str, content: bytes) -> str:
    name = (filename or "").lower()
    suffix = name.rsplit(".", 1)[-1] if "." in name else ""
    if name.endswith(".pdf"):
        return _extract_pdf(content)
    if name.endswith(".docx"):
        return _extract_docx(content)
    if name.endswith(".doc"):
        raise DocExtractError("老版 .doc 格式暂不支持，请用 Word/WPS 另存为 .docx 后重试")
    if f".{suffix}" in IMAGE_FORMATS:
        # 图片简历：OCR 识别
        try:
            text = ocr_image_bytes(content)
        except OCRError as exc:
            raise DocExtractError(f"图片识别不可用：{exc}") from exc
        if not text:
            raise DocExtractError("未能从图片中识别到文字（请确认图片清晰、内容为文字版简历）")
        return text
    if name.endswith(".txt"):
        return content.decode("utf-8", errors="replace")
    # 未知类型：尝试按文本读
    return content.decode("utf-8", errors="replace")


def _extract_pdf(content: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(content))
    except Exception as exc:  # noqa: BLE001
        raise DocExtractError(f"PDF 解析失败：{exc}") from exc
    pages = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:  # noqa: BLE001
            continue
    text = "\n".join(pages).strip()
    if not text:
        # 扫描件/图片型 PDF：渲染页面后 OCR
        return _pdf_ocr_fallback(content)
    if len(text) < PDF_TEXT_MIN:
        # 文本层极短（如仅页眉水印），大概率仍为图片型 PDF → OCR 兜底并合并
        try:
            ocr_text = _pdf_ocr_fallback(content)
        except DocExtractError:
            return text
        return ocr_text if len(ocr_text) > len(text) else text
    return text


def _pdf_ocr_fallback(content: bytes) -> str:
    """扫描件 PDF → OCR；引擎缺失时转可读的中文错误。"""
    try:
        text = ocr_pdf_pages(content)
    except OCRError as exc:
        raise DocExtractError(
            f"该 PDF 是扫描件/图片版，暂无法识别（{exc}）。请使用可复制的 PDF，"
            "或将简历截图/拍照为图片后上传（支持 png/jpg/webp）"
        ) from exc
    if not text:
        raise DocExtractError("扫描件识别结果为空（请确认页面内容清晰、方向正确）")
    return text


def _extract_docx(content: bytes) -> str:
    """直接解析 word/document.xml：段落（w:p）内拼接文本节点（w:t），
    兼容文本框（也在 document.xml 中）；表格文本同样包含。
    """
    # 老版 .doc 是 OLE 复合文档（D0 CF 11 E0），docx 是 zip（PK）
    if not content.startswith(b"PK"):
        raise DocExtractError("老版 .doc 格式暂不支持，请用 Word/WPS 另存为 .docx 后重试")
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            xml = zf.read("word/document.xml").decode("utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        raise DocExtractError(f"DOCX 解析失败：{exc}") from exc

    parts: list[str] = []
    # 按段落切分，保留段落结构
    for para in re.findall(r"<w:p[ >].*?</w:p>", xml, re.S):
        # 段内：换行/制表符 → 空格，文本节点拼接
        line = re.sub(r"<w:br[^>]*/>", " ", para)
        line = re.sub(r"<w:tab[^>]*/>", " ", line)
        texts = re.findall(r"<w:t[^>]*>(.*?)</w:t>", line, re.S)
        text = html.unescape("".join(texts)).strip()
        if text:
            parts.append(text)

    text = "\n".join(parts).strip()
    if not text:
        raise DocExtractError("DOCX 未提取到文本（文档可能为空、扫描件或内容为图片，暂不支持 OCR）")
    return text
