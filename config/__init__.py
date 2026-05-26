import json
import os

APP_NAME = "DataDashboard"
APP_VERSION = "1.0.0"

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
CONFIG_FILE = os.path.join(DATA_DIR, "app_config.json")
SCRIPTS_FILE = os.path.join(DATA_DIR, "scripts.json")
QUICK_QUERIES_FILE = os.path.join(DATA_DIR, "quick_queries.json")
QUERY_CACHE_FILE = os.path.join(DATA_DIR, "query_cache.json")

SUPPORTED_DB_TYPES = ["mysql", "postgresql", "sqlite"]

DIMENSION_DAY = "day"
DIMENSION_MONTH = "month"
DIMENSION_YEAR = "year"
DIMENSIONS = [DIMENSION_DAY, DIMENSION_MONTH, DIMENSION_YEAR]

DIMENSION_DATE_FORMATS = {
    DIMENSION_DAY: "%Y-%m-%d",
    DIMENSION_MONTH: "%Y-%m",
    DIMENSION_YEAR: "%Y",
}

DIMENSION_SQL_FORMATS = {
    DIMENSION_DAY: "%Y-%m-%d",
    DIMENSION_MONTH: "%Y-%m",
    DIMENSION_YEAR: "%Y",
}

CHART_TYPES = ["line", "bar", "pie", "scatter", "area"]

DEFAULT_THEME = "dark"

DEFAULT_APP_CONFIG = {
    "nacos": {
        "server_addresses": "127.0.0.1:8848",
        "namespace": "",
        "group": "DEFAULT_GROUP",
        "data_id": "data_dashboard_connections",
        "username": "nacos",
        "password": "nacos",
        "redis_data_id": "data_dashboard_redis",
    },
    "cache_ttl": 3600,
}


def load_app_config():
    data = load_json(CONFIG_FILE, {})
    merged = dict(DEFAULT_APP_CONFIG)
    if "nacos" in data and isinstance(data["nacos"], dict):
        merged["nacos"] = {**DEFAULT_APP_CONFIG["nacos"], **data["nacos"]}
    if "cache_ttl" in data:
        merged["cache_ttl"] = data["cache_ttl"]
    return merged


def save_app_config(config):
    save_json(CONFIG_FILE, config)


def get_redis_config():
    from core.nacos_config import load_redis_config
    nacos_redis = load_redis_config()
    if nacos_redis and isinstance(nacos_redis, dict):
        return {
            "host": os.environ.get("REDIS_HOST", nacos_redis.get("host", "localhost")),
            "port": int(os.environ.get("REDIS_PORT", nacos_redis.get("port", 6379))),
            "db": int(os.environ.get("REDIS_DB", nacos_redis.get("db", 0))),
            "password": os.environ.get("REDIS_PASSWORD", nacos_redis.get("password", "")) or None,
        }
    return None


def get_nacos_config():
    cfg = load_app_config()["nacos"]
    return {
        "server_addresses": os.environ.get("NACOS_SERVER_ADDRESSES", cfg["server_addresses"]),
        "namespace": os.environ.get("NACOS_NAMESPACE", cfg.get("namespace", "")),
        "group": os.environ.get("NACOS_GROUP", cfg.get("group", "DEFAULT_GROUP")),
        "data_id": os.environ.get("NACOS_DATA_ID", cfg.get("data_id", "data_dashboard_connections")),
        "username": os.environ.get("NACOS_USERNAME", cfg.get("username", "")),
        "password": os.environ.get("NACOS_PASSWORD", cfg.get("password", "")),
        "redis_data_id": os.environ.get("NACOS_REDIS_DATA_ID", cfg.get("redis_data_id", "data_dashboard_redis")),
    }


def get_cache_ttl():
    cfg = load_app_config()
    return cfg.get("cache_ttl", 3600)


def ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def load_json(filepath, default=None):
    if default is None:
        default = []
    if not os.path.exists(filepath):
        return default
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return default


def save_json(filepath, data):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
