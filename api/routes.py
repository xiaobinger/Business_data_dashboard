import json
import logging
import traceback
from flask import Flask, request, jsonify, send_from_directory
from config import CHART_TYPES, DIMENSIONS, QUICK_QUERIES_FILE, QUERY_CACHE_FILE, load_json, save_json, load_app_config, save_app_config, DEFAULT_APP_CONFIG
from core.db_manager import DatabaseManager, DatabaseConnection
from core.query_engine import QueryEngine, ScriptConfig, PARAM_PATTERN
from core.data_merger import DataMerger
from core.cache import build_cache_key, get_cache, set_cache

logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder="../static", static_url_path="")
app.config["JSON_AS_ASCII"] = False

db_manager = DatabaseManager()
query_engine = QueryEngine(db_manager)
data_merger = DataMerger(query_engine)

BUILTIN_PARAMS = {"dimension", "date_format", "start_date", "end_date", "year", "month", "day", "start_year", "end_year"}


@app.route("/")
def index():
    return send_from_directory("../static", "index.html")


@app.route("/api/connections", methods=["GET"])
def list_connections():
    conns = db_manager.get_all_connections()
    result = []
    for c in conns:
        d = c.to_dict()
        d["has_ssh"] = c.ssh_enabled
        result.append(d)
    return jsonify(result)


@app.route("/api/connections", methods=["POST"])
def add_connection():
    data = request.json
    conn = DatabaseConnection.from_dict(data)
    if db_manager.add_connection(conn):
        return jsonify({"ok": True, "name": conn.name})
    return jsonify({"ok": False, "error": f"连接名称 '{conn.name}' 已存在"}), 400


@app.route("/api/connections/<name>", methods=["PUT"])
def update_connection(name):
    data = request.json
    conn = DatabaseConnection.from_dict(data)
    if db_manager.update_connection(name, conn):
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "连接不存在"}), 404


@app.route("/api/connections/<name>", methods=["DELETE"])
def delete_connection(name):
    if db_manager.remove_connection(name):
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "连接不存在"}), 404


@app.route("/api/connections/<name>/test", methods=["POST"])
def test_connection(name):
    conn = db_manager.get_connection(name)
    if not conn:
        return jsonify({"ok": False, "error": "连接不存在"}), 404
    success, msg = conn.test_connection()
    conn.close()
    return jsonify({"ok": success, "message": msg})


@app.route("/api/connections/<name>/tables", methods=["GET"])
def get_tables(name):
    tables = db_manager.get_tables(name)
    return jsonify(tables)


@app.route("/api/connections/<name>/tables/<table>/columns", methods=["GET"])
def get_columns(name, table):
    columns = db_manager.get_columns(name, table)
    return jsonify(columns)


@app.route("/api/scripts", methods=["GET"])
def list_scripts():
    scripts = query_engine.get_all_scripts()
    return jsonify([s.to_dict() for s in scripts])


@app.route("/api/scripts", methods=["POST"])
def add_script():
    data = request.json
    script = ScriptConfig.from_dict(data)
    if query_engine.add_script(script):
        return jsonify({"ok": True, "name": script.name})
    return jsonify({"ok": False, "error": "脚本名称已存在"}), 400


@app.route("/api/scripts/<name>", methods=["PUT"])
def update_script(name):
    data = request.json
    script = ScriptConfig.from_dict(data)
    if query_engine.update_script(name, script):
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "脚本不存在"}), 404


@app.route("/api/scripts/<name>", methods=["DELETE"])
def delete_script(name):
    if query_engine.remove_script(name):
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "脚本不存在"}), 404


@app.route("/api/parse-params", methods=["POST"])
def parse_params():
    sql = request.json.get("sql", "")
    all_params = PARAM_PATTERN.findall(sql)
    builtin = [p for p in set(all_params) if p in BUILTIN_PARAMS]
    custom = sorted(set(p for p in all_params if p not in BUILTIN_PARAMS))
    return jsonify({"builtin": builtin, "custom": custom})


@app.route("/api/parse-columns", methods=["POST"])
def parse_columns():
    import re
    sql = request.json.get("sql", "")
    if not sql.strip():
        return jsonify({"columns": []})

    sql_clean = sql.strip().rstrip(";").strip()
    if sql_clean.lower().startswith("select"):
        sql_clean = sql_clean[len("select"):]

    from_pos = None
    depth = 0
    in_case = 0
    i = 0
    while i < len(sql_clean):
        ch = sql_clean[i]
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
        elif depth == 0 and in_case == 0:
            upper = sql_clean[i:i + 4].upper()
            if upper == 'CASE':
                in_case += 1
                i += 4
                continue
            if upper == 'FROM':
                prev = sql_clean[i - 1] if i > 0 else ' '
                if prev in (' ', '\t', '\n', '\r'):
                    from_pos = i
                    break
        if depth == 0 and in_case > 0:
            upper_rest = sql_clean[i:i + 3].upper()
            if upper_rest == 'END' and (i + 3 >= len(sql_clean) or not sql_clean[i + 3].isalnum()):
                in_case -= 1
                i += 3
                continue
        i += 1

    if from_pos is None:
        return jsonify({"columns": []})

    select_part = sql_clean[:from_pos].strip()

    columns = []
    depth = 0
    in_case = 0
    current = []
    i = 0
    while i < len(select_part):
        ch = select_part[i]
        if ch == '(':
            depth += 1
            current.append(ch)
        elif ch == ')':
            depth -= 1
            current.append(ch)
        elif ch == ',' and depth == 0 and in_case == 0:
            columns.append(''.join(current).strip())
            current = []
        else:
            current.append(ch)
        if depth == 0:
            upper = select_part[i:i + 4].upper()
            if upper == 'CASE':
                in_case += 1
            upper_end = select_part[i:i + 3].upper()
            if upper_end == 'END' and (i + 3 >= len(select_part) or not select_part[i + 3].isalnum()):
                in_case -= 1
        i += 1
    if current:
        columns.append(''.join(current).strip())

    result = []
    alias_pattern = re.compile(r'\bAS\s+(\w+)\s*$', re.IGNORECASE)
    no_as_pattern = re.compile(r'(\w+)\s*$', re.IGNORECASE)
    for col in columns:
        m = alias_pattern.search(col)
        if m:
            result.append(m.group(1))
        else:
            m2 = no_as_pattern.search(col)
            if m2:
                name = m2.group(1)
                if name.upper() not in ('FROM', 'WHERE', 'GROUP', 'ORDER', 'HAVING', 'LIMIT', 'AND', 'OR', 'ON', 'AS', 'BY', 'DESC', 'ASC'):
                    result.append(name)

    return jsonify({"columns": result})


@app.route("/api/execute", methods=["POST"])
def execute_query():
    data = request.json
    sql = data.get("sql", "").strip()
    conn_name = data.get("conn_name", "")
    merge_names = data.get("merge_conn_names", [])
    dimension = data.get("dimension", "day")
    date = data.get("date", "")
    custom_params = data.get("custom_params", {})
    chart_type = data.get("chart_type", "line")
    merge_mode = data.get("merge_mode", "separate")
    hide_fields = data.get("hide_fields", [])
    merge_key = data.get("merge_key", "")

    if not sql:
        return jsonify({"ok": False, "error": "请输入SQL"}), 400
    if not conn_name and not merge_names:
        return jsonify({"ok": False, "error": "请选择数据源"}), 400

    force_refresh = data.get("force_refresh", False)

    cache_params = {
        "sql": sql, "conn_name": conn_name,
        "merge_conn_names": sorted(merge_names) if merge_names else [],
        "dimension": dimension, "date": date,
        "custom_params": custom_params,
        "drill_start_date": data.get("drill_start_date", ""),
        "drill_end_date": data.get("drill_end_date", ""),
        "start_year": data.get("start_year"), "end_year": data.get("end_year"),
        "merge_mode": merge_mode, "merge_key": merge_key,
        "hide_fields": sorted(hide_fields) if hide_fields else [],
    }
    cache_key = build_cache_key(cache_params)

    if not force_refresh:
        cached = get_cache(cache_key)
        if cached is not None:
            return jsonify(cached)

    try:
        start_year = data.get("start_year")
        end_year = data.get("end_year")
        dim_params = query_engine.build_dimension_params(
            dimension, date,
            start_year=int(start_year) if start_year else None,
            end_year=int(end_year) if end_year else None,
        )
        drill_start_date = data.get("drill_start_date")
        drill_end_date = data.get("drill_end_date")
        if drill_start_date:
            dim_params["start_date"] = drill_start_date
        if drill_end_date:
            dim_params["end_date"] = drill_end_date
        all_params = {**dim_params, **custom_params}

        if merge_names:
            effective_merge_mode = "concat" if merge_mode == "separate" else "sum"
            df = data_merger.merge_from_sources(
                conn_names=merge_names, sql=sql, params=all_params, merge_mode=effective_merge_mode,
                merge_key=merge_key if merge_key else None,
            )
            title = f"合并数据 ({len(merge_names)}个源)"
        else:
            df = query_engine.execute_query(conn_name, sql, all_params)
            title = conn_name

        columns = df.columns.tolist() if df is not None and not df.empty else []
        if not columns:
            return jsonify({
                "ok": True,
                "title": title,
                "chart_type": chart_type,
                "columns": [],
                "rows": [],
                "row_count": 0,
            })
        if hide_fields:
            keep_cols = [c for c in columns if c not in hide_fields]
            df = df[keep_cols]
            columns = keep_cols
        rows = df.values.tolist()

        serializable_rows = []
        for row in rows:
            serializable_row = []
            for val in row:
                if hasattr(val, "item"):
                    serializable_row.append(val.item())
                elif isinstance(val, (float, int)):
                    serializable_row.append(val)
                else:
                    serializable_row.append(str(val))
            serializable_rows.append(serializable_row)

        result = {
            "ok": True,
            "title": title,
            "chart_type": chart_type,
            "columns": columns,
            "rows": serializable_rows,
            "row_count": len(df),
        }
        set_cache(cache_key, result)
        return jsonify(result)
    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f"Query error:\n{tb}")
        return jsonify({"ok": False, "error": str(e), "traceback": tb}), 500


@app.route("/api/config", methods=["GET"])
def get_config():
    return jsonify({
        "chart_types": CHART_TYPES,
        "dimensions": DIMENSIONS,
        "db_types": ["mysql", "postgresql", "sqlite"],
    })


@app.route("/api/quick-queries", methods=["GET"])
def list_quick_queries():
    data = load_json(QUICK_QUERIES_FILE, [])
    return jsonify(data)


@app.route("/api/quick-queries", methods=["POST"])
def add_quick_query():
    data = request.json
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"ok": False, "error": "请输入名称"}), 400
    queries = load_json(QUICK_QUERIES_FILE, [])
    if any(q["name"] == name for q in queries):
        return jsonify({"ok": False, "error": f"名称 '{name}' 已存在"}), 400
    queries.append(data)
    save_json(QUICK_QUERIES_FILE, queries)
    return jsonify({"ok": True, "name": name})


@app.route("/api/quick-queries/<name>", methods=["PUT"])
def update_quick_query(name):
    data = request.json
    queries = load_json(QUICK_QUERIES_FILE, [])
    for i, q in enumerate(queries):
        if q["name"] == name:
            new_name = data.get("name", name)
            if new_name != name and any(q2["name"] == new_name for q2 in queries):
                return jsonify({"ok": False, "error": f"名称 '{new_name}' 已存在"}), 400
            queries[i] = data
            save_json(QUICK_QUERIES_FILE, queries)
            return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "不存在"}), 404


@app.route("/api/quick-queries/<name>", methods=["DELETE"])
def delete_quick_query(name):
    queries = load_json(QUICK_QUERIES_FILE, [])
    new_queries = [q for q in queries if q["name"] != name]
    if len(new_queries) == len(queries):
        return jsonify({"ok": False, "error": "不存在"}), 404
    save_json(QUICK_QUERIES_FILE, new_queries)
    cache = load_json(QUERY_CACHE_FILE, {})
    cache.pop(name, None)
    save_json(QUERY_CACHE_FILE, cache)
    return jsonify({"ok": True})


@app.route("/api/query-cache/<name>", methods=["GET"])
def get_query_cache(name):
    cache = load_json(QUERY_CACHE_FILE, {})
    if name in cache:
        return jsonify({"ok": True, "data": cache[name]})
    return jsonify({"ok": False, "error": "无缓存"}), 404


@app.route("/api/query-cache/<name>", methods=["POST"])
def save_query_cache(name):
    data = request.json
    cache = load_json(QUERY_CACHE_FILE, {})
    cache[name] = data
    save_json(QUERY_CACHE_FILE, cache)
    return jsonify({"ok": True})


@app.route("/api/query-cache/<name>", methods=["DELETE"])
def delete_query_cache(name):
    cache = load_json(QUERY_CACHE_FILE, {})
    cache.pop(name, None)
    save_json(QUERY_CACHE_FILE, cache)
    return jsonify({"ok": True})


@app.route("/api/app-config", methods=["GET"])
def get_app_config():
    cfg = load_app_config()
    return jsonify({"ok": True, "config": cfg})


@app.route("/api/app-config", methods=["POST"])
def update_app_config():
    data = request.json
    current = load_app_config()
    if "nacos" in data and isinstance(data["nacos"], dict):
        current["nacos"] = {**DEFAULT_APP_CONFIG["nacos"], **data["nacos"]}
    if "cache_ttl" in data:
        current["cache_ttl"] = int(data["cache_ttl"])
    save_app_config(current)
    nacos_ok = False
    try:
        from core.nacos_config import reinit_nacos
        nacos_ok = reinit_nacos()
    except Exception as e:
        logger.warning("重连 Nacos 失败: %s", e)
    redis_ok = False
    try:
        from core.cache import reinit_redis
        redis_ok = reinit_redis()
    except Exception as e:
        logger.warning("重连 Redis 失败: %s", e)
    return jsonify({"ok": True, "redis_connected": redis_ok, "nacos_connected": nacos_ok})


@app.route("/api/app-config/test-redis", methods=["POST"])
def test_redis_connection():
    try:
        import importlib
        redis = importlib.import_module("redis")
        from config import get_redis_config
        cfg = get_redis_config()
        if not cfg:
            return jsonify({"ok": False, "error": "Nacos 上未配置 Redis"})
        client = redis.Redis(
            host=cfg["host"], port=cfg["port"], db=cfg["db"],
            password=cfg.get("password") or None,
            decode_responses=True, socket_connect_timeout=3,
        )
        client.ping()
        client.close()
        return jsonify({"ok": True, "host": cfg["host"], "port": cfg["port"]})
    except ImportError:
        return jsonify({"ok": False, "error": "redis 包未安装"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/app-config/test-nacos", methods=["POST"])
def test_nacos_connection():
    try:
        from core.nacos_config import _nacos_available, _init_nacos_client
        if _init_nacos_client() and _nacos_available:
            cfg = load_app_config()["nacos"]
            return jsonify({"ok": True, "addr": cfg["server_addresses"]})
        return jsonify({"ok": False, "error": "Nacos 连接失败"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})
