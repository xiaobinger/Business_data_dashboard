import asyncio
import importlib
import json
import logging
import os
import threading

from config import get_nacos_config

logger = logging.getLogger(__name__)

_nacos_available = False
_nacos_config_service = None
_nacos_lock = threading.Lock()
_nacos_loop = None
_nacos_loop_thread = None


def _ensure_nacos_loop():
    global _nacos_loop, _nacos_loop_thread
    if _nacos_loop is not None and _nacos_loop.is_running():
        return _nacos_loop
    _nacos_loop = asyncio.new_event_loop()

    def _run():
        asyncio.set_event_loop(_nacos_loop)
        _nacos_loop.run_forever()

    _nacos_loop_thread = threading.Thread(target=_run, daemon=True)
    _nacos_loop_thread.start()
    return _nacos_loop


def _try_import_nacos():
    try:
        mod = importlib.import_module("v2.nacos")
        return mod
    except ImportError:
        pass
    try:
        mod = importlib.import_module("nacos")
        return mod
    except ImportError:
        pass
    return None


def _init_nacos_client():
    global _nacos_available, _nacos_config_service
    with _nacos_lock:
        if _nacos_available and _nacos_config_service is not None:
            return True
        nacos_mod = _try_import_nacos()
        if nacos_mod is None:
            logger.error("nacos-sdk-python 未安装，无法加载配置")
            return False
        try:
            cfg = get_nacos_config()
            if hasattr(nacos_mod, "ClientConfig"):
                client_cfg = nacos_mod.ClientConfig(
                    server_addresses=cfg["server_addresses"],
                    namespace_id=cfg.get("namespace", ""),
                    username=cfg.get("username") or None,
                    password=cfg.get("password") or None,
                )
                loop = _ensure_nacos_loop()
                svc_holder = [None]
                exc_holder = [None]

                def _create():
                    try:
                        asyncio.set_event_loop(loop)
                        svc_holder[0] = nacos_mod.NacosConfigService(client_cfg)
                    except Exception as e:
                        exc_holder[0] = e

                loop.call_soon_threadsafe(_create)
                import time
                for _ in range(50):
                    if svc_holder[0] is not None or exc_holder[0] is not None:
                        break
                    time.sleep(0.1)
                if exc_holder[0]:
                    raise exc_holder[0]
                _nacos_config_service = svc_holder[0]
            elif hasattr(nacos_mod, "NacosClient"):
                _nacos_config_service = nacos_mod.NacosClient(
                    server_addresses=cfg["server_addresses"],
                    namespace=cfg.get("namespace", ""),
                    username=cfg.get("username") or None,
                    password=cfg.get("password") or None,
                )
            else:
                logger.error("无法识别的 nacos SDK 版本")
                return False
            _nacos_available = True
            logger.info("Nacos 连接成功: %s", cfg["server_addresses"])
            return True
        except Exception as e:
            logger.error("Nacos 连接失败: %s", e)
            _nacos_available = False
            _nacos_config_service = None
            return False


def _run_async(coro):
    nacos_loop = _nacos_loop
    if nacos_loop is not None and nacos_loop.is_running():
        future = asyncio.run_coroutine_threadsafe(coro, nacos_loop)
        return future.result(timeout=15)
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        result = None
        exc = None
        def _run():
            nonlocal result, exc
            try:
                result = asyncio.run(coro)
            except Exception as e:
                exc = e
        t = threading.Thread(target=_run)
        t.start()
        t.join(timeout=15)
        if exc:
            raise exc
        return result
    else:
        return asyncio.run(coro)


def _nacos_get_config(data_id, group):
    svc = _nacos_config_service
    if svc is None:
        return None
    try:
        nacos_mod = _try_import_nacos()
        if hasattr(nacos_mod, "ConfigParam"):
            param = nacos_mod.ConfigParam(data_id=data_id, group=group)
            content = _run_async(svc.get_config(param))
        elif hasattr(svc, "get_config"):
            content = svc.get_config(data_id, group)
        else:
            return None
        return content
    except Exception as e:
        logger.error("从 Nacos 读取配置失败 (data_id=%s): %s", data_id, e)
        return None


def _nacos_publish_config(data_id, group, content):
    svc = _nacos_config_service
    if svc is None:
        return False
    try:
        nacos_mod = _try_import_nacos()
        if hasattr(nacos_mod, "ConfigParam"):
            param = nacos_mod.ConfigParam(data_id=data_id, group=group, content=content)
            _run_async(svc.publish_config(param))
        elif hasattr(svc, "publish_config"):
            svc.publish_config(data_id, group, content)
        return True
    except Exception as e:
        logger.error("写入 Nacos 失败 (data_id=%s): %s", data_id, e)
        return False


def load_connections():
    if not _init_nacos_client():
        logger.error("Nacos 不可用，无法加载数据库连接配置")
        return []
    cfg = get_nacos_config()
    content = _nacos_get_config(cfg.get("data_id", "data_dashboard_connections"), cfg.get("group", "DEFAULT_GROUP"))
    if content:
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            logger.error("Nacos 连接配置 JSON 解析失败")
    return []


def save_connections(connections):
    if not _init_nacos_client():
        logger.error("Nacos 不可用，无法保存数据库连接配置")
        return
    cfg = get_nacos_config()
    _nacos_publish_config(
        cfg.get("data_id", "data_dashboard_connections"),
        cfg.get("group", "DEFAULT_GROUP"),
        json.dumps(connections, ensure_ascii=False, indent=2),
    )


def load_redis_config():
    if not _init_nacos_client():
        return None
    cfg = get_nacos_config()
    redis_data_id = cfg.get("redis_data_id", "data_dashboard_redis")
    content = _nacos_get_config(redis_data_id, cfg.get("group", "DEFAULT_GROUP"))
    if content:
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            logger.error("Nacos Redis 配置 JSON 解析失败")
    return None


def save_redis_config(redis_cfg):
    if not _init_nacos_client():
        logger.error("Nacos 不可用，无法保存 Redis 配置")
        return
    cfg = get_nacos_config()
    redis_data_id = cfg.get("redis_data_id", "data_dashboard_redis")
    _nacos_publish_config(
        redis_data_id,
        cfg.get("group", "DEFAULT_GROUP"),
        json.dumps(redis_cfg, ensure_ascii=False, indent=2),
    )


def load_meta_db_config():
    if not _init_nacos_client():
        return None
    cfg = get_nacos_config()
    meta_data_id = cfg.get("meta_data_id", "data_dashboard_meta")
    content = _nacos_get_config(meta_data_id, cfg.get("group", "DEFAULT_GROUP"))
    if content:
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            logger.error("Nacos 元数据库配置 JSON 解析失败")
    return None


def save_meta_db_config(meta_cfg):
    if not _init_nacos_client():
        logger.error("Nacos 不可用，无法保存元数据库配置")
        return
    cfg = get_nacos_config()
    meta_data_id = cfg.get("meta_data_id", "data_dashboard_meta")
    _nacos_publish_config(
        meta_data_id,
        cfg.get("group", "DEFAULT_GROUP"),
        json.dumps(meta_cfg, ensure_ascii=False, indent=2),
    )


def reinit_nacos():
    global _nacos_available, _nacos_config_service
    with _nacos_lock:
        old = _nacos_config_service
        _nacos_available = False
        _nacos_config_service = None
    if old:
        try:
            if hasattr(old, "shutdown"):
                _run_async(old.shutdown())
        except Exception:
            pass
    return _init_nacos_client()
