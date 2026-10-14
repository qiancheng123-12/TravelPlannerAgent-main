"""Chroma 向量知识库服务。

默认使用轻量、离线、确定性的哈希向量，便于答辩现场在没有额外
Embedding API 的情况下演示完整 RAG 流程。生产环境可替换为更高质量的
OpenAI、百炼或本地 BGE Embedding。
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from ..core.config import get_settings


class LocalHashEmbeddings(Embeddings):
    """无需联网的稳定哈希向量，适合小型演示知识库。"""

    def __init__(self, dimensions: int = 384):
        self.dimensions = dimensions

    @staticmethod
    def _tokens(text: str) -> List[str]:
        units = re.findall(r"[\u4e00-\u9fff]|[a-z0-9]+", text.lower())
        bigrams = [f"{units[index]}{units[index + 1]}" for index in range(len(units) - 1)]
        return units + bigrams

    def _embed(self, text: str) -> List[float]:
        vector = [0.0] * self.dimensions
        for token in self._tokens(text):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            number = int.from_bytes(digest, "big")
            index = number % self.dimensions
            vector[index] += 1.0 if number & 1 else -1.0

        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> List[float]:
        return self._embed(text)


class VectorStoreService:
    """管理旅行知识、实时 POI 与用户偏好的 Chroma 集合。"""

    def __init__(
        self,
        persist_directory: Optional[str] = None,
        embeddings: Optional[Embeddings] = None,
    ):
        settings = get_settings()
        backend_root = Path(__file__).resolve().parents[2]
        configured = Path(persist_directory or settings.chroma_persist_directory)
        if not configured.is_absolute():
            configured = backend_root / configured

        configured.mkdir(parents=True, exist_ok=True)
        self._persist_dir = str(configured)
        self._knowledge_path = backend_root / "data" / "travel_knowledge.json"
        self._embeddings = embeddings or self._create_embeddings(settings)
        if embeddings is None:
            collection_key = f"{settings.embedding_provider}:{settings.embedding_model}"
        else:
            dimensions = getattr(embeddings, "dimensions", "default")
            collection_key = f"custom:{embeddings.__class__.__name__}:{dimensions}"
        self._collection_suffix = hashlib.sha1(collection_key.encode()).hexdigest()[:8]
        self._travel_store = None
        self._preference_store = None
        self._seeded = False
        self._lock = threading.Lock()

    @staticmethod
    def _create_embeddings(settings):
        """生产环境可切换真实 Embedding；默认离线模式保证可演示性。"""
        provider = settings.embedding_provider.lower().strip()
        if provider == "local":
            return LocalHashEmbeddings()

        if provider == "aliyun":
            if not settings.aliyun_dashscope_api_key:
                raise ValueError("使用阿里云 Embedding 时必须配置 ALIYUN_DASHSCOPE_API_KEY")
            from langchain_openai import OpenAIEmbeddings

            return OpenAIEmbeddings(
                model=settings.embedding_model,
                api_key=settings.aliyun_dashscope_api_key,
                base_url=settings.aliyun_embedding_base_url,
                chunk_size=10,
                check_embedding_ctx_length=False,
            )

        if provider == "openai":
            if not settings.openai_api_key:
                raise ValueError("使用 OpenAI Embedding 时必须配置 OPENAI_API_KEY")
            from langchain_openai import OpenAIEmbeddings

            return OpenAIEmbeddings(
                model=settings.embedding_model,
                api_key=settings.openai_api_key,
                base_url=settings.openai_base_url,
            )

        raise ValueError(f"不支持的 Embedding 提供商: {settings.embedding_provider}")

    def _get_travel_store(self):
        if self._travel_store is None:
            from langchain_chroma import Chroma

            self._travel_store = Chroma(
                collection_name=f"travel_knowledge_{self._collection_suffix}",
                embedding_function=self._embeddings,
                persist_directory=self._persist_dir,
            )
        return self._travel_store

    def _get_preference_store(self):
        if self._preference_store is None:
            from langchain_chroma import Chroma

            self._preference_store = Chroma(
                collection_name=f"user_preferences_{self._collection_suffix}",
                embedding_function=self._embeddings,
                persist_directory=self._persist_dir,
            )
        return self._preference_store

    def ensure_knowledge_base(self) -> int:
        """将仓库内置旅行知识幂等写入 Chroma。"""
        with self._lock:
            if self._seeded:
                return 0
            if not self._knowledge_path.exists():
                raise FileNotFoundError(f"知识库文件不存在: {self._knowledge_path}")

            records = json.loads(self._knowledge_path.read_text(encoding="utf-8"))
            documents = [
                Document(
                    page_content=record["content"],
                    metadata={
                        "chunk_id": record["id"],
                        "title": record["title"],
                        "source": record.get("source", "内置旅行知识库"),
                        "type": "travel_guide",
                    },
                )
                for record in records
            ]
            ids = [record["id"] for record in records]
            store = self._get_travel_store()
            existing = set(store.get(ids=ids).get("ids", []))
            pending = [document for document, item_id in zip(documents, ids) if item_id not in existing]
            pending_ids = [item_id for item_id in ids if item_id not in existing]
            if pending:
                store.add_documents(pending, ids=pending_ids)
            self._seeded = True
            return len(pending)

    def add_poi_knowledge(self, city: str, pois: List[Dict[str, Any]]) -> int:
        """把高德返回的实时 POI 写入同一向量库。"""
        documents: List[Document] = []
        ids: List[str] = []
        for poi in pois:
            poi_id = str(poi.get("id") or poi.get("name") or "unknown")
            stable_id = hashlib.sha1(f"{city}:{poi_id}".encode("utf-8")).hexdigest()
            location = poi.get("location") or {}
            content = (
                f"城市：{city}\n景点：{poi.get('name', '')}\n"
                f"地址：{poi.get('address', '')}\n类别：{poi.get('category', '')}\n"
                f"评分：{poi.get('rating', '')}\n描述：{poi.get('description', '')}\n"
                f"坐标：{location.get('longitude', 0)},{location.get('latitude', 0)}"
            )
            documents.append(
                Document(
                    page_content=content,
                    metadata={
                        "chunk_id": f"poi-{stable_id}",
                        "city": city,
                        "title": poi.get("name", "未命名景点"),
                        "source": "高德地图实时 POI",
                        "type": "poi",
                    },
                )
            )
            ids.append(f"poi-{stable_id}")

        if documents:
            store = self._get_travel_store()
            existing = store.get(ids=ids).get("ids", [])
            if existing:
                store.delete(ids=existing)
            store.add_documents(documents, ids=ids)
        return len(documents)

    def add_document_chunks(
        self, document_id: str, filename: str, chunks: List[Dict[str, Any]]
    ) -> int:
        """把 ETL 产生的语义片段幂等写入向量库。"""
        store = self._get_travel_store()
        ids = [f"doc-{document_id}-{index}" for index in range(len(chunks))]
        if ids:
            existing = store.get(ids=ids).get("ids", [])
            if existing:
                store.delete(ids=existing)
        documents = [
            Document(
                page_content=chunk["text"],
                metadata={
                    "chunk_id": ids[index],
                    "document_id": document_id,
                    "filename": filename,
                    "title": chunk.get("title") or filename,
                    "source": f"用户上传：{filename}",
                    "page": int(chunk.get("page", 0)),
                    "chunk_index": index,
                    "type": "uploaded_document",
                    "extraction_method": chunk.get("extraction_method", "native"),
                    "ocr_confidence": (
                        float(chunk["ocr_confidence"])
                        if chunk.get("ocr_confidence") is not None
                        else -1.0
                    ),
                },
            )
            for index, chunk in enumerate(chunks)
        ]
        if documents:
            store.add_documents(documents, ids=ids)
        return len(documents)

    def delete_document(self, document_id: str) -> int:
        store = self._get_travel_store()
        result = store.get(where={"document_id": document_id})
        ids = result.get("ids", [])
        if ids:
            store.delete(ids=ids)
        return len(ids)

    @staticmethod
    def _document_key(document: Document) -> str:
        return str(document.metadata.get("chunk_id") or hashlib.sha1(
            document.page_content.encode("utf-8")
        ).hexdigest())

    @staticmethod
    def _lexical_tokens(text: str) -> List[str]:
        units = re.findall(r"[\u4e00-\u9fff]|[a-z0-9]+", text.lower())
        return units + ["".join(units[i:i + 2]) for i in range(max(0, len(units) - 1))]

    def _lexical_search(
        self,
        query: str,
        k: int,
    ) -> List[Document]:
        """轻量 BM25 实现，弥补专有名词被向量召回遗漏的问题。"""
        payload = self._get_travel_store().get(include=["documents", "metadatas"])
        records = []
        for text, metadata in zip(
            payload.get("documents", []), payload.get("metadatas", [])
        ):
            records.append((text or "", metadata))
        texts = [item[0] for item in records]
        metadatas = [item[1] for item in records]
        if not texts:
            return []
        query_tokens = self._lexical_tokens(query)
        corpus_tokens = [self._lexical_tokens(text or "") for text in texts]
        avg_len = sum(len(tokens) for tokens in corpus_tokens) / max(len(corpus_tokens), 1)
        scores = []
        for index, tokens in enumerate(corpus_tokens):
            score = 0.0
            for token in set(query_tokens):
                document_frequency = sum(1 for item in corpus_tokens if token in item)
                idf = math.log(1 + (len(corpus_tokens) - document_frequency + 0.5) / (document_frequency + 0.5))
                frequency = tokens.count(token)
                denominator = frequency + 1.5 * (1 - 0.75 + 0.75 * len(tokens) / max(avg_len, 1))
                score += idf * (frequency * 2.5 / denominator) if frequency else 0
            if score > 0:
                scores.append((score, index))
        scores.sort(reverse=True)
        return [
            Document(page_content=texts[index], metadata=metadatas[index] or {})
            for _, index in scores[:k]
        ]

    def retrieve(
        self,
        query: str,
        k: int = 5,
    ) -> List[Document]:
        """向量检索和轻量 BM25 并行召回，再用 RRF 融合。"""
        self.ensure_knowledge_base()
        store = self._get_travel_store()
        rankings: List[List[Document]] = [
            store.similarity_search(query, k=max(k, 4)),
            self._lexical_search(query, max(k, 4)),
        ]

        scores: Dict[str, float] = {}
        documents: Dict[str, Document] = {}
        for ranking in rankings:
            for rank, document in enumerate(ranking, 1):
                key = self._document_key(document)
                scores[key] = scores.get(key, 0.0) + 1.0 / (60 + rank)
                documents[key] = document
        ordered = sorted(scores, key=scores.get, reverse=True)
        return [documents[key] for key in ordered[:k]]

    @staticmethod
    def format_context(documents: List[Document]) -> tuple[str, List[str]]:
        context_parts: List[str] = []
        sources: List[str] = []
        for index, document in enumerate(documents, 1):
            title = str(document.metadata.get("title", f"知识片段{index}"))
            source = str(document.metadata.get("source", "旅行知识库"))
            context_parts.append(f"[{index}] {title}\n{document.page_content}")
            sources.append(f"{title}（{source}）")
        return "\n\n".join(context_parts), sources

    def upsert_user_preference(
        self,
        memory_id: str,
        user_id: str,
        preference_type: str,
        preference_data: Any,
        summary: str,
        confidence: float = 0.8,
    ) -> None:
        """按稳定 ID 幂等写入用户偏好，供跨会话语义召回。"""
        document = Document(
            page_content=summary,
            metadata={
                "memory_id": memory_id,
                "user_id": user_id,
                "preference_type": preference_type,
                "value_json": json.dumps(preference_data, ensure_ascii=False),
                "confidence": float(confidence),
                "type": "preference",
            },
        )
        store = self._get_preference_store()
        existing = store.get(ids=[memory_id]).get("ids", [])
        if existing:
            store.delete(ids=existing)
        store.add_documents([document], ids=[memory_id])

    def save_user_preference(
        self, user_id: str, preference_type: str, preference_data: Dict[str, Any]
    ) -> None:
        """兼容旧调用；新代码应使用 ``upsert_user_preference``。"""
        memory_id = hashlib.sha1(f"{user_id}:{preference_type}".encode("utf-8")).hexdigest()
        summary = f"{preference_type}：{json.dumps(preference_data, ensure_ascii=False)}"
        self.upsert_user_preference(
            memory_id, user_id, preference_type, preference_data, summary
        )

    def search_user_preferences(
        self, user_id: str, query: str, k: int = 5
    ) -> List[Document]:
        """只在当前用户命名空间中做语义检索。"""
        return self._get_preference_store().similarity_search(
            query,
            k=max(1, k),
            filter={"user_id": user_id},
        )

    def delete_user_preference(self, memory_id: str) -> None:
        self._get_preference_store().delete(ids=[memory_id])

    def clear_user_preferences(self, user_id: str) -> int:
        store = self._get_preference_store()
        result = store.get(where={"user_id": user_id})
        ids = result.get("ids", [])
        if ids:
            store.delete(ids=ids)
        return len(ids)

    def get_user_preferences(self, user_id: str, preference_type: Optional[str] = None) -> Dict[str, Any]:
        where: Dict[str, Any] = {"user_id": user_id}
        if preference_type:
            where = {"$and": [where, {"preference_type": preference_type}]}
        return self._get_preference_store().get(where=where)


_vector_store: Optional[VectorStoreService] = None


def get_vector_store() -> VectorStoreService:
    global _vector_store
    if _vector_store is None:
        _vector_store = VectorStoreService()
    return _vector_store
