"""PDF/Word/TXT 文档 ETL：抽取、清洗、语义分割。"""

from __future__ import annotations

import re
import threading
from io import BytesIO
from pathlib import Path
from statistics import fmean
from typing import Any, Dict, List, Optional, Tuple

from ..core.config import get_settings


class DocumentETL:
    SUPPORTED = {".pdf", ".docx", ".txt", ".md"}
    _OCR_ENGINE = None
    _OCR_LOCK = threading.Lock()

    def __init__(
        self,
        *,
        ocr_enabled: Optional[bool] = None,
        ocr_dpi: Optional[int] = None,
        ocr_min_chars: Optional[int] = None,
        ocr_bad_char_ratio: Optional[float] = None,
    ):
        settings = get_settings()
        self.ocr_enabled = settings.ocr_enabled if ocr_enabled is None else ocr_enabled
        self.ocr_dpi = settings.ocr_dpi if ocr_dpi is None else ocr_dpi
        self.ocr_min_chars = settings.ocr_min_chars if ocr_min_chars is None else ocr_min_chars
        self.ocr_bad_char_ratio = (
            settings.ocr_bad_char_ratio
            if ocr_bad_char_ratio is None
            else ocr_bad_char_ratio
        )

    def extract(self, filename: str, content: bytes) -> List[Dict[str, Any]]:
        suffix = Path(filename).suffix.lower()
        if suffix not in self.SUPPORTED:
            raise ValueError("仅支持 PDF、DOCX、TXT 和 Markdown 文件")
        if suffix == ".pdf":
            return self._extract_pdf(content)
        if suffix == ".docx":
            from docx import Document

            document = Document(BytesIO(content))
            return [{
                "page": 1,
                "text": "\n".join(p.text for p in document.paragraphs),
                "extraction_method": "native",
                "ocr_confidence": None,
            }]
        return [{
            "page": 1,
            "text": content.decode("utf-8-sig", errors="replace"),
            "extraction_method": "native",
            "ocr_confidence": None,
        }]

    def _extract_pdf(self, content: bytes) -> List[Dict[str, Any]]:
        """优先提取文字层，仅对无字或乱码页面执行本地 OCR。"""
        from pypdf import PdfReader

        try:
            reader = PdfReader(BytesIO(content))
            native_pages = [page.extract_text() or "" for page in reader.pages]
        except Exception as exc:
            raise ValueError(f"PDF 解析失败: {exc}") from exc

        pages: List[Dict[str, Any]] = []
        for index, native_text in enumerate(native_pages):
            method = "native"
            confidence = None
            selected_text = native_text
            if self.ocr_enabled and self._needs_ocr(native_text):
                ocr_text, ocr_confidence = self._ocr_pdf_page(content, index)
                if self._prefer_ocr(native_text, ocr_text):
                    selected_text = ocr_text
                    method = "ocr"
                    confidence = ocr_confidence
            pages.append({
                "page": index + 1,
                "text": selected_text,
                "extraction_method": method,
                "ocr_confidence": confidence,
            })
        return pages

    def _needs_ocr(self, text: str) -> bool:
        compact = re.sub(r"\s+", "", text or "")
        if not compact:
            return True
        meaningful = re.findall(r"[\u4e00-\u9fffA-Za-z0-9]", compact)
        bad_ratio = compact.count("\ufffd") / max(len(compact), 1)
        return len(meaningful) < self.ocr_min_chars or bad_ratio > self.ocr_bad_char_ratio

    def _prefer_ocr(self, native_text: str, ocr_text: str) -> bool:
        if not ocr_text.strip():
            return False
        native_compact = re.sub(r"\s+", "", native_text or "")
        ocr_compact = re.sub(r"\s+", "", ocr_text)
        native_bad_ratio = native_compact.count("\ufffd") / max(len(native_compact), 1)
        if native_bad_ratio > self.ocr_bad_char_ratio:
            return True
        return len(ocr_compact) >= len(native_compact)

    def _ocr_pdf_page(self, content: bytes, page_index: int) -> Tuple[str, Optional[float]]:
        """将指定 PDF 页渲染为图片，并调用 RapidOCR 识别中文文本。"""
        try:
            import pymupdf
            from rapidocr import RapidOCR
        except ImportError as exc:
            raise ValueError(
                "检测到扫描版 PDF，但本地 OCR 依赖未安装。"
                "请执行 pip install pymupdf rapidocr onnxruntime"
            ) from exc

        with pymupdf.open(stream=content, filetype="pdf") as document:
            if page_index >= document.page_count:
                return "", None
            page = document.load_page(page_index)
            pixmap = page.get_pixmap(
                dpi=self.ocr_dpi,
                colorspace=pymupdf.csRGB,
                alpha=False,
            )
            image_bytes = pixmap.tobytes("png")

        with self._OCR_LOCK:
            if self.__class__._OCR_ENGINE is None:
                self.__class__._OCR_ENGINE = RapidOCR()
            result = self.__class__._OCR_ENGINE(image_bytes)

        texts = list(result.txts) if result.txts is not None else []
        scores = (
            [float(score) for score in result.scores]
            if result.scores is not None
            else []
        )
        confidence = round(fmean(scores), 4) if scores else None
        return "\n".join(str(text).strip() for text in texts if str(text).strip()), confidence

    def transform(self, pages: List[Dict[str, Any]], chunk_size: int = 700, overlap: int = 100) -> List[Dict[str, Any]]:
        chunks: List[Dict[str, Any]] = []
        for page in pages:
            text = self._clean(page.get("text", ""))
            if not text:
                continue
            sections = re.split(r"(?=^#{1,6}\s|^[一二三四五六七八九十]+[、.]|^\d+[、.])", text, flags=re.M)
            for section in sections:
                section = section.strip()
                if not section:
                    continue
                title_match = re.match(r"^(#{1,6}\s*)?([^\n]{2,60})", section)
                title = title_match.group(2).strip() if title_match else ""
                start = 0
                while start < len(section):
                    end = min(len(section), start + chunk_size)
                    if end < len(section):
                        boundary = max(section.rfind(mark, start, end) for mark in ["。", "！", "？", "\n"])
                        if boundary > start + chunk_size // 2:
                            end = boundary + 1
                    chunks.append({
                        "page": page.get("page", 0),
                        "title": title,
                        "text": section[start:end],
                        "extraction_method": page.get("extraction_method", "native"),
                        "ocr_confidence": page.get("ocr_confidence"),
                    })
                    if end >= len(section):
                        break
                    start = max(start + 1, end - overlap)
        return chunks

    @staticmethod
    def _clean(text: str) -> str:
        text = text.replace("\x00", "").replace("\r\n", "\n")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()
