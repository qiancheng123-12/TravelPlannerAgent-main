from app.services.embedding_service import LocalHashEmbeddings, VectorStoreService


def test_local_hash_embeddings_are_deterministic():
    embeddings = LocalHashEmbeddings(dimensions=64)
    first = embeddings.embed_query("北京 历史文化 低预算")
    second = embeddings.embed_query("北京 历史文化 低预算")

    assert first == second
    assert len(first) == 64
    assert any(value != 0 for value in first)


def test_chroma_rag_retrieves_knowledge_and_live_poi(tmp_path):
    # 单元测试保持离线、确定性；生产配置可以独立切换云端 Embedding。
    service = VectorStoreService(
        persist_directory=str(tmp_path / "chroma"),
        embeddings=LocalHashEmbeddings(),
    )
    service.add_poi_knowledge(
        "北京",
        [
            {
                "id": "forbidden-city",
                "name": "故宫博物院",
                "address": "北京市东城区",
                "category": "历史文化",
                "rating": 4.9,
                "description": "明清皇家宫殿",
                "location": {"longitude": 116.397, "latitude": 39.916},
            }
        ],
    )
    documents = service.retrieve("北京历史文化行程和预算安排", k=5)
    context, sources = service.format_context(documents)

    assert documents
    assert "北京" in context or "预算" in context
    assert sources
