"""RAG 知识库服务: 基于 ChromaDB(内嵌持久化模式, 无需独立服务)。

- 三类集合: ddl_schemas(表结构) / knowledge_docs(业务文档) / sql_examples(SQL示例)
- 向量化优先使用 OpenAI Embedding(配置了 llm_api_key 时), 否则降级为本地
  字符 n-gram 哈希向量(离线可用)。集合元数据记录 embedding 模式, 模式切换
  后旧向量相似度会失真, 需重新保存数据以重建索引。
"""
import re
import math
import hashlib
import logging
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional

from app.llm import embed_texts

logger = logging.getLogger(__name__)

_CHROMA_PATH = Path(__file__).resolve().parents[2] / ".chroma_data"
_COLLECTIONS = ("ddl_schemas", "knowledge_docs", "sql_examples")
_EMB_DIM = 256

_client = None
_collections: Dict[str, Any] = {}


def _get_client():
    global _client
    if _client is None:
        import chromadb
        _CHROMA_PATH.mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(path=str(_CHROMA_PATH))
    return _client


def _get_collection(name: str):
    if name not in _collections:
        client = _get_client()
        _collections[name] = client.get_or_create_collection(
            name=name, metadata={"hnsw:space": "cosine"}
        )
    return _collections[name]


# ========== Embedding ==========

def _hash_embed(texts: List[str]) -> List[List[float]]:
    """本地兜底向量化: 字符bigram + 英文单词的签名哈希, L2归一化。"""
    vectors = []
    for text in texts:
        vec = [0.0] * _EMB_DIM
        s = re.sub(r"\s+", "", text.lower())
        tokens = [s[i:i + 2] for i in range(max(1, len(s) - 1))]
        tokens += re.findall(r"[a-z0-9]+", text.lower())
        for tok in tokens:
            h = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16)
            idx, sign = h % _EMB_DIM, (1 if (h >> 8) % 2 == 0 else -1)
            vec[idx] += sign
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        vectors.append([v / norm for v in vec])
    return vectors


async def _embed(texts: List[str]) -> List[List[float]]:
    result = await embed_texts(texts)
    if result is not None and len(result) == len(texts):
        return result
    return _hash_embed(texts)


# ========== 文本分块 ==========

def chunk_text(content: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
    """按段落优先、字符数兜底进行分块。"""
    content = (content or "").strip()
    if not content:
        return []
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", content) if p.strip()]
    chunks: List[str] = []
    buf = ""
    for para in paragraphs:
        if len(para) > chunk_size:
            if buf:
                chunks.append(buf)
                buf = ""
            step = max(1, chunk_size - overlap)
            for i in range(0, len(para), step):
                piece = para[i:i + chunk_size]
                if len(piece) < overlap and chunks:
                    chunks[-1] += piece
                else:
                    chunks.append(piece)
            continue
        if len(buf) + len(para) + 1 <= chunk_size:
            buf = f"{buf}\n{para}" if buf else para
        else:
            if buf:
                chunks.append(buf)
            buf = para
    if buf:
        chunks.append(buf)
    return chunks


# ========== 索引写入 ==========

async def index_document(doc_id: str, title: str, content: str,
                         datasource_id: Optional[str] = None) -> int:
    """文档分块并向量化入库, 返回分块数量。"""
    chunks = chunk_text(content)
    if not chunks:
        return 0
    vectors = await _embed(chunks)
    ids = [f"doc_{doc_id}_{i}" for i in range(len(chunks))]
    metadatas = [{"doc_id": str(doc_id), "title": title, "chunk_index": i,
                  "datasource_id": str(datasource_id or "")} for i in range(len(chunks))]

    def _run():
        col = _get_collection("knowledge_docs")
        col.upsert(ids=ids, documents=chunks, metadatas=metadatas, embeddings=vectors)

    await asyncio.to_thread(_run)
    return len(chunks)


async def index_sql_example(example_id: str, question: str, sql_content: str,
                            datasource_id: Optional[str] = None) -> None:
    vector = await _embed([question])
    def _run():
        col = _get_collection("sql_examples")
        col.upsert(
            ids=[f"sql_{example_id}"],
            documents=[f"问题: {question}\nSQL:\n{sql_content}"],
            metadatas=[{"example_id": str(example_id), "question": question,
                        "datasource_id": str(datasource_id or "")}],
            embeddings=vector,
        )
    await asyncio.to_thread(_run)


async def index_ddl(datasource_id: str, tables_info: List[Dict]) -> int:
    """将表结构(来自 engines.sync_schema)转为 DDL 文本并向量化。"""
    if not tables_info:
        return 0
    docs, ids, metadatas = [], [], []
    for t in tables_info:
        tname = t["table_name"]
        cols = []
        for c in t.get("columns", []):
            line = f"  {c['column_name']} {c['column_type']}"
            if c.get("column_comment"):
                line += f" -- {c['column_comment']}"
            cols.append(line)
        comment = f" -- {t['table_comment']}" if t.get("table_comment") else ""
        docs.append(f"CREATE TABLE {tname}{comment}\n" + "\n".join(cols))
        ids.append(f"ddl_{datasource_id}_{tname}")
        metadatas.append({"datasource_id": str(datasource_id), "table_name": tname})
    vectors = await _embed(docs)

    def _run():
        col = _get_collection("ddl_schemas")
        col.upsert(ids=ids, documents=docs, metadatas=metadatas, embeddings=vectors)

    await asyncio.to_thread(_run)
    return len(docs)


# ========== 检索 ==========

async def retrieve(query: str, top_k: int = 5,
                   datasource_id: Optional[str] = None) -> Dict[str, List[Dict]]:
    """
    向量检索三类知识。chroma 不可用时返回空结构(调用方应有DB关键词兜底)。
    每项: {id, content, metadata, score}
    """
    vector = (await _embed([query]))[0]

    def _query_one(name: str, n_results: int) -> List[Dict]:
        col = _get_collection(name)
        if col.count() == 0:
            return []
        res = col.query(query_embeddings=[vector], n_results=min(n_results, col.count()))
        items = []
        for i, rid in enumerate(res["ids"][0]):
            distance = res["distances"][0][i] if res.get("distances") else 1.0
            items.append({
                "id": rid,
                "content": res["documents"][0][i],
                "metadata": (res.get("metadatas") or [[{}]])[0][i] or {},
                "score": round(max(0.0, 1.0 - float(distance)), 3),
            })
        return items

    try:
        where = {"datasource_id": str(datasource_id)} if datasource_id else None
        results = {}
        for name, k in (("ddl_schemas", 3), ("knowledge_docs", 5), ("sql_examples", 3)):
            try:
                if where:
                    col = _get_collection(name)
                    if col.count() == 0:
                        results[name] = []
                        continue
                    res = col.query(query_embeddings=[vector],
                                    n_results=min(k, col.count()), where=where)
                    items = []
                    for i, rid in enumerate(res["ids"][0]):
                        distance = res["distances"][0][i] if res.get("distances") else 1.0
                        items.append({
                            "id": rid,
                            "content": res["documents"][0][i],
                            "metadata": (res.get("metadatas") or [[{}]])[0][i] or {},
                            "score": round(max(0.0, 1.0 - float(distance)), 3),
                        })
                    results[name] = items
                else:
                    results[name] = _query_one(name, k)
            except Exception:
                results[name] = _query_one(name, k)
        return results
    except Exception as e:
        logger.warning("RAG检索失败: %s", e)
        return {"ddl_schemas": [], "knowledge_docs": [], "sql_examples": []}


# ========== 删除清理 ==========

async def _delete_by_metadata(collection: str, field: str, value: str) -> None:
    """按 metadata 字段删除向量。"""
    def _run():
        _get_collection(collection).delete(where={field: value})

    await asyncio.to_thread(_run)


async def delete_doc_vectors(doc_id: str) -> None:
    await _delete_by_metadata("knowledge_docs", "doc_id", str(doc_id))


async def delete_sql_example_vectors(example_id: str) -> None:
    def _run():
        _get_collection("sql_examples").delete(ids=[f"sql_{example_id}"])
    try:
        await asyncio.to_thread(_run)
    except Exception:
        pass


async def delete_datasource_vectors(datasource_id: str) -> None:
    await _delete_by_metadata("ddl_schemas", "datasource_id", str(datasource_id))
