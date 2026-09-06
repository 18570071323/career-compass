# -*- coding: utf-8 -*-
"""OCR 文本识别（纯本地，无网络依赖）：图片 / 扫描件 PDF。

- 引擎：RapidOCR（PaddleOCR 模型转 ONNX）+ onnxruntime，简体中文效果好、CPU 快
- PDF 渲染：pypdfium2 把页面渲染成图像后 OCR（无需系统安装 poppler）
- 依赖缺失/模型不可用：抛 OCRError，由上层转成明确的中文提示
"""
from __future__ import annotations

import io
import logging
from typing import Any

logger = logging.getLogger(__name__)

_engine: Any | None = None
_engine_error: str | None = None

IMAGE_FORMATS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
# PDF 文本层少于该字符数视为扫描件/图片型 PDF，转 OCR
PDF_TEXT_MIN = 40
# 扫描件 PDF 最多渲染页数（防超大文件拖垮）
PDF_MAX_PAGES = 6
# OCR 输入图像缩放渲染倍率
RENDER_SCALE = 2.0


class OCRError(Exception):
    pass


def _load_engine() -> Any:
    """懒加载 RapidOCR 引擎（首次调用初始化，失败记录原因）。"""
    global _engine, _engine_error
    if _engine is not None:
        return _engine
    if _engine_error is not None:
        raise OCRError(f"OCR 引擎不可用：{_engine_error}")
    try:
        from rapidocr_onnxruntime import RapidOCR

        _engine = RapidOCR()
        logger.info("RapidOCR engine loaded")
        return _engine
    except OCRError:
        raise
    except Exception as exc:  # noqa: BLE001
        _engine_error = str(exc)
        logger.warning("OCR engine init failed: %s", exc)
        raise OCRError(f"OCR 引擎初始化失败：{_engine_error[:160]}") from exc


def _call(engine: Any, img: Any) -> list[str]:
    """兼容 rapidocr_onnxruntime(1.x) 与 rapidocr(6.x) 的调用与返回结构差异。"""
    raw = engine(img) if hasattr(engine, "__call__") else engine.ocr(img)
    texts: list[str] = []
    # 形态 A：tuple([ [box, text, score], ... ], elapse)
    if isinstance(raw, tuple) and raw:
        items = raw[0]
        if isinstance(items, list):
            for it in items:
                if isinstance(it, (list, tuple)) and len(it) >= 2 and isinstance(it[1], str):
                    texts.append(it[1])
                elif isinstance(it, str):
                    texts.append(it)
    # 形态 B：RapidOCROutput（带 .txts / .boxes）
    elif raw is not None and not isinstance(raw, (list, tuple)):
        txts = getattr(raw, "txts", None)
        if isinstance(txts, list):
            texts = [str(t) for t in txts]
    # 形态 C：直接是 [ [box,text,score], ... ] 或 [text, ...]
    elif isinstance(raw, list):
        for it in raw:
            if isinstance(it, (list, tuple)) and len(it) >= 2 and isinstance(it[1], str):
                texts.append(it[1])
            elif isinstance(it, str):
                texts.append(it)
    # 去空
    return [t.strip() for t in texts if t and t.strip()]


def ocr_image_bytes(content: bytes) -> str:
    """识别单张图片内容 → 文本（失败抛 OCRError）。"""
    try:
        import numpy as np
        from PIL import Image
    except Exception as exc:  # noqa: BLE001
        raise OCRError(f"图片解码依赖不可用：{exc}") from exc
    engine = _load_engine()
    try:
        img = Image.open(io.BytesIO(content))
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        elif img.mode == "L":
            img = img.convert("RGB")
        lines = _call(engine, np.array(img))
    except OCRError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning("ocr image failed: %s", exc)
        raise OCRError(f"图片文字识别失败：{exc}") from exc
    return "\n".join(lines).strip()


def ocr_pdf_pages(content: bytes) -> str:
    """扫描件 PDF：渲染前若干页并 OCR（返回每页文本，空页跳过）。"""
    try:
        import pypdfium2 as pdfium
    except Exception as exc:  # noqa: BLE001
        raise OCRError("扫描件识别组件不可用（未安装 pypdfium2）") from exc
    engine = _load_engine()
    import numpy as np

    texts: list[str] = []
    try:
        pdf = pdfium.PdfDocument(io.BytesIO(content))
        n = min(len(pdf), PDF_MAX_PAGES)
        if n == 0:
            return ""
        for i in range(n):
            page = pdf[i]
            bitmap = page.render(scale=RENDER_SCALE)
            pil_img = bitmap.to_pil()
            if pil_img.mode not in ("RGB", "L"):
                pil_img = pil_img.convert("RGB")
            lines = _call(engine, np.array(pil_img))
            page_text = "\n".join(lines).strip()
            if page_text:
                texts.append(page_text)
    except OCRError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning("ocr pdf failed: %s", exc)
        raise OCRError(f"扫描件识别失败：{exc}") from exc
    return "\n\n".join(texts).strip()


def reset_engine() -> None:
    """重置引擎（测试/换模型用）。"""
    global _engine, _engine_error
    _engine = None
    _engine_error = None
