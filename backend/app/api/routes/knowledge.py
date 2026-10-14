"""可通过 Swagger 直接演示的知识库 ETL 与检索接口。"""

from __future__ import annotations

import asyncio
import hashlib

from fastapi import APIRouter, File, HTTPException, Query, UploadFile

from ...models.schemas import KnowledgeIngestResponse
from ...services.document_loader import DocumentETL
from ...services.embedding_service import get_vector_store

router = APIRouter(prefix="/knowledge", tags=["RAG 知识库"])


@router.post("/documents", response_model=KnowledgeIngestResponse)
async def upload_document(file: UploadFile = File(...)):
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="文件为空")
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="文件不能超过 20MB")
    filename = file.filename or "document"
    document_id = hashlib.sha256(content).hexdigest()[:20]
    etl = DocumentETL()
    try:
        pages = await asyncio.to_thread(etl.extract, filename, content)
        chunks = await asyncio.to_thread(etl.transform, pages)
        if not chunks:
            raise ValueError("文档未提取到有效文本")
        count = await asyncio.to_thread(
            get_vector_store().add_document_chunks, document_id, filename, chunks
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    ocr_pages = [page for page in pages if page.get("extraction_method") == "ocr"]
    native_pages = len(pages) - len(ocr_pages)
    if ocr_pages and native_pages:
        extraction_mode = "hybrid"
    elif ocr_pages:
        extraction_mode = "ocr"
    else:
        extraction_mode = "native"
    confidences = [
        float(page["ocr_confidence"])
        for page in ocr_pages
        if page.get("ocr_confidence") is not None
    ]
    return KnowledgeIngestResponse(
        document_id=document_id,
        filename=filename,
        chunks=count,
        characters=sum(len(chunk["text"]) for chunk in chunks),
        pages=len(pages),
        native_pages=native_pages,
        ocr_pages=len(ocr_pages),
        extraction_mode=extraction_mode,
        average_ocr_confidence=(
            round(sum(confidences) / len(confidences), 4)
            if confidences
            else None
        ),
    )


@router.get("/search")
async def search_knowledge(q: str = Query(min_length=2), city: str = "", limit: int = Query(5, ge=1, le=20)):
    documents = await asyncio.to_thread(get_vector_store().retrieve, q, city or None, limit)
    return {
        "query": q,
        "strategy": "vector_bm25_rrf",
        "results": [
            {"content": doc.page_content, "metadata": doc.metadata}
            for doc in documents
        ],
    }


@router.delete("/documents/{document_id}")
async def delete_document(document_id: str):
    deleted = await asyncio.to_thread(get_vector_store().delete_document, document_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="文档不存在")
    return {"success": True, "deleted_chunks": deleted}
