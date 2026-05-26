import hashlib
import importlib
import json
import logging
import os
from typing import Any, Optional

from config import get_redis_config, get_cache_ttl

logger = logging.getLogger(__name__)

KEY_PREFIX = "dd:query:"


class _MemoryCache:
    def __init__(self):
        self._store: dict[str, tuple[str, float]] = {}

    def get(self, key: str) -> Optional[str]:
        entry = self._store.get(key)
        if entry is None:
            return None
        return entry[0]

    def set(self, key: str, value: str, ttl: int) -> None:
        self._store[key] = (value, ttl)

    def delete(self, key: str) -> None:
        self._store.pop(key, None)

    def clear(self) -> None:
        self._store.clear()

    def keys(self, pattern: str) -> list[str]:
        if pattern.endswith("*"):
            prefix = pattern[:-1]
            return [k for k in self._store if k.startswith(prefix)]
        return [k for k in self._store if k == pattern]


def _create_redis_client():
    try:
        redis = importlib.import_module("redis")
    except ImportError:
        logger.warning("redis 包未安装，降级为内存缓存")
        return None
    try:
        cfg = get_redis_config()
        client = redis.Redis(
            host=cfg["host"],
            port=cfg["port"],
            db=cfg["db"],
            password=cfg["password"],
            decode_responses=True,
            socket_connect_timeout=3,
        )
        client.ping()
        logger.info("Redis 连接成功: %s:%s/%s", cfg["host"], cfg["port"], cfg["db"])
        return client
    except Exception as exc:
        logger.warning("Redis 连接失败 (%s)，降级为内存缓存", exc)
        return None


_redis_client = _create_redis_client()
_memory_cache: Optional[_MemoryCache] = None if _redis_client else _MemoryCache()


def build_cache_key(params: dict) -> str:
    parts = []
    for k in sorted(params.keys()):
        v = params[k]
        if isinstance(v, (list, dict)):
            v = json.dumps(v, sort_keys=True, ensure_ascii=False)
        else:
            v = str(v) if v is not None else ""
        parts.append(f"{k}={v}")
    raw = "&".join(parts)
    digest = hashlib.md5(raw.encode("utf-8")).hexdigest()
    return f"{KEY_PREFIX}{digest}"


def get_cache(key: str) -> Optional[dict]:
    try:
        if _redis_client:
            raw = _redis_client.get(key)
        else:
            raw = _memory_cache.get(key)
        if raw is None:
            return None
        return json.loads(raw)
    except Exception as exc:
        logger.warning("读取缓存失败 (%s)", exc)
        return None


def set_cache(key: str, data: dict, ttl: int = None) -> None:
    try:
        if ttl is None:
            ttl = get_cache_ttl()
        raw = json.dumps(data, ensure_ascii=False)
        if _redis_client:
            _redis_client.setex(key, ttl, raw)
        else:
            _memory_cache.set(key, raw, ttl)
    except Exception as exc:
        logger.warning("写入缓存失败 (%s)", exc)


def delete_cache(key: str) -> None:
    try:
        if _redis_client:
            _redis_client.delete(key)
        else:
            _memory_cache.delete(key)
    except Exception as exc:
        logger.warning("删除缓存失败 (%s)", exc)


def clear_all_cache() -> None:
    try:
        if _redis_client:
            pattern = f"{KEY_PREFIX}*"
            keys = _redis_client.keys(pattern)
            if keys:
                _redis_client.delete(*keys)
        else:
            _memory_cache.clear()
    except Exception as exc:
        logger.warning("清空缓存失败 (%s)", exc)


def reinit_redis():
    global _redis_client, _memory_cache
    old_client = _redis_client
    _redis_client = _create_redis_client()
    if _redis_client:
        _memory_cache = None
    else:
        _memory_cache = _MemoryCache()
    if old_client:
        try:
            old_client.close()
        except Exception:
            pass
    return _redis_client is not None
