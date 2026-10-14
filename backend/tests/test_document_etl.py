from io import BytesIO

from pypdf import PdfWriter

from app.services.document_loader import DocumentETL


def test_txt_etl_creates_overlapping_semantic_chunks():
    etl = DocumentETL()
    pages = etl.extract("攻略.txt", ("# 北京攻略\n" + "故宫适合上午参观。" * 120).encode("utf-8"))
    chunks = etl.transform(pages, chunk_size=180, overlap=30)

    assert len(chunks) > 2
    assert all(chunk["text"] for chunk in chunks)
    assert all(chunk["page"] == 1 for chunk in chunks)
    assert any("北京攻略" in chunk["title"] for chunk in chunks)


def test_ocr_detection_distinguishes_native_and_scanned_pages():
    etl = DocumentETL(ocr_enabled=True, ocr_min_chars=30)

    assert etl._needs_ocr("")
    assert etl._needs_ocr("\ufffd" * 40)
    assert not etl._needs_ocr("北京旅行攻略包含故宫预约、公共交通和住宿建议。" * 4)


def test_scanned_pdf_uses_ocr_and_propagates_metadata(monkeypatch):
    stream = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    writer.write(stream)

    etl = DocumentETL(ocr_enabled=True, ocr_min_chars=30)
    monkeypatch.setattr(
        etl,
        "_ocr_pdf_page",
        lambda _content, _index: (
            "北京扫描版旅行指南\n故宫实行实名预约，建议乘坐公共交通。",
            0.96,
        ),
    )

    pages = etl.extract("扫描攻略.pdf", stream.getvalue())
    chunks = etl.transform(pages)

    assert pages[0]["extraction_method"] == "ocr"
    assert pages[0]["ocr_confidence"] == 0.96
    assert "北京扫描版旅行指南" in pages[0]["text"]
    assert chunks[0]["extraction_method"] == "ocr"
    assert chunks[0]["ocr_confidence"] == 0.96
