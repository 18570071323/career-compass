"""向量精排（docs/07-§5.1 升级项，M7.4）。

可插拔：fastembed（ONNX，无 torch）+ BAAI/bge-small-zh-v1.5。
- 配置 vector_rerank_enabled=True 且模型可加载时启用；
- 模型缺失/加载失败/未启用 → is_available()=False，推荐流水线回退 TF-IDF 余弦，不影响功能。
- 模型首次加载可能联网下载：放入带超时的守护线程执行，下载超时/失败只降级、不阻塞请求。

向量在进程内缓存（按 jd_id + updated_at），小语料下无外部依赖。
"""
from __future__ import annotations

import logging
import os
import threading
import uuid
from typing import Any

from ...config import Settings

logger = logging.getLogger(__name__)

# 模型加载/下载超时（秒）：超时即降级 TF-IDF，避免冷启动卡死请求
_LOAD_TIMEOUT = 30.0

# 向量缓存：{jd_id: (updated_at_iso, embedding)}
_EMBED_CACHE: dict[uuid.UUID, tuple[str, list[float]]] = {}


class VectorReranker:
    """轻量向量相似度重排器（惰性加载，可用性探测）。"""

    def __init__(self, settings: Settings) -> None:
        self._enabled = bool(settings.vector_rerank_enabled)
        self._model_name = settings.vector_rerank_model
        self._weight = float(settings.vector_rerank_weight)
        self._model: Any | None = None
        self._load_error: str | None = None
        self._loading = False

    @property
    def weight(self) -> float:
        return max(0.0, min(1.0, self._weight))

    def is_available(self) -> bool:
        if not self._enabled:
            return False
        if self._model is None and self._load_error is None and not self._loading:
            self._try_load()
        return self._model is not None

    def _try_load(self) -> None:
        """带超时的懒加载：模型下载/导入放入守护线程，超过 _LOAD_TIMEOUT 即降级 TF-IDF。"""
        self._loading = True
        outcome: dict[str, Any] = {}

        def _work() -> None:
            try:
                # 国内镜像 + 沙箱友好缓存路径（仓库 .tools/hf-cache，可写）
                os.environ.setdefault(
                    "HF_ENDPOINT", os.environ.get("HF_ENDPOINT", "https://hf-mirror.com")
                )
                repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", ".."))
                os.environ.setdefault("HF_HOME", os.path.join(repo_root, ".tools", "hf-cache"))
                os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
                os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
                from fastembed import TextEmbedding  # type: ignore

                outcome["model"] = TextEmbedding(self._model_name)
            except Exception as exc:  # noqa: BLE001
                outcome["error"] = str(exc)

        t = threading.Thread(target=_work, daemon=True)
        t.start()
        t.join(timeout=_LOAD_TIMEOUT)
        self._loading = False
        if "model" in outcome:
            self._model = outcome["model"]
            logger.info("vector reranker loaded: %s", self._model_name)
        else:
            # 超时（outcome 为空）或异常 → 本次会话降级 TF-IDF，不阻塞请求
            self._load_error = outcome.get("error") or "模型加载/下载超时（网络受限），本次会话降级 TF-IDF"
            logger.warning("vector reranker unavailable, fallback to TF-IDF: %s", self._load_error)

    def encode(self, texts: list[str]) -> list[list[float]]:
        if self._model is None:
            return []
        try:
            return [list(map(float, v)) for v in self._model.embed(texts)]
        except Exception as exc:  # noqa: BLE001
            logger.warning("vector encode failed: %s", exc)
            return []

    def _cos(self, a: list[float], b: list[float]) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        na = sum(x * x for x in a) ** 0.5
        nb = sum(y * y for y in b) ** 0.5
        if not na or not nb:
            return 0.0
        return dot / (na * nb)

    def jd_embedding(self, jd_id: uuid.UUID, jd_text: str, updated_at: str | None) -> list[float] | None:
        """取岗位向量（缓存命中直接返回）。"""
        cached = _EMBED_CACHE.get(jd_id)
        if cached and cached[0] == updated_at:
            return cached[1]
        emb = self.encode([jd_text])
        if not emb:
            return None
        _EMBED_CACHE[jd_id] = (updated_at or "", emb[0])
        return emb[0]

    def query_embedding(self, text: str) -> list[float] | None:
        emb = self.encode([text])
        return emb[0] if emb else None

    def rerank_similarity(
        self,
        query_emb: list[float] | None,
        jd_emb: list[float] | None,
        tfidf_sim: float,
    ) -> float:
        """最终相似度 = w×向量余弦 + (1-w)×TF-IDF 余弦（向量不可用时原样返回 TF-IDF）。"""
        if query_emb is None or jd_emb is None:
            return tfidf_sim
        vec = self._cos(query_emb, jd_emb)
        return self.weight * vec + (1.0 - self.weight) * tfidf_sim


_reranker: VectorReranker | None = None


def get_reranker(settings: Settings | None = None) -> VectorReranker:
    """进程级单例。"""
    global _reranker
    if _reranker is None:
        from ...config import get_settings

        _reranker = VectorReranker(settings or get_settings())
    return _reranker


def clear_cache() -> None:
    _EMBED_CACHE.clear()
