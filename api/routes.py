import json
import logging
import traceback
from datetime import timedelta
from flask import Flask, request, jsonify, send_from_directory, session
from config import CHART_TYPES, DIMENSIONS, load_app_config, save_app_config, DEFAULT_APP_CONFIG
from core.db_manager import DatabaseManager, DatabaseConnection
from core.query_engine import QueryEngine, PARAM_PATTERN
from core.data_merger import DataMerger
from core.cache import build_cache_key, get_cache, set_cache
from core import meta_store
from core.auth import (
    login_user, logout_user, require_login, require_permission,
    get_current_user, get_current_user_id, get_current_permissions, is_super_admin, get_current_username,
    touch_session, check_session_timeout,
)
from core.verify_code import send_sms_code, send_email_code, verify_code

logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder="../static", static_url_path="")
app.config["JSON_AS_ASCII"] = False
app.secret_key = "data_dashboard_secret_key_2026"
app.permanent_session_lifetime = timedelta(days=7)

db_manager = DatabaseManager()
query_engine = QueryEngine(db_manager)
data_merger = DataMerger(query_engine)

BUILTIN_PARAMS = {"dimension", "date_format", "start_date", "end_date", "year", "month", "day", "start_year", "end_year"}


@app.before_request
def _check_session_idle():
    if request.path.startswith("/api/auth/"):
        return
    if request.path.startswith("/api/") and get_current_user_id():
        cfg = load_app_config()
        timeout = cfg.get("session_timeout", 30)
        if not check_session_timeout(timeout):
            return jsonify({"ok": False, "error": "会话已过期，请重新登录"}), 401
        touch_session()


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
@require_permission("datasource_manage")
def add_connection():
    data = request.json
    conn = DatabaseConnection.from_dict(data)
    if db_manager.add_connection(conn):
        return jsonify({"ok": True, "name": conn.name})
    return jsonify({"ok": False, "error": f"连接名称 '{conn.name}' 已存在"}), 400


@app.route("/api/connections/<name>", methods=["PUT"])
@require_permission("datasource_manage")
def update_connection(name):
    data = request.json
    conn = DatabaseConnection.from_dict(data)
    if db_manager.update_connection(name, conn):
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "连接不存在"}), 404


@app.route("/api/connections/<name>", methods=["DELETE"])
@require_permission("datasource_manage")
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
@require_login
def list_scripts():
    uid = get_current_user_id()
    is_sa = is_super_admin()
    has_sm = "script_manage" in get_current_permissions()
    return jsonify(meta_store.list_scripts_for_user(uid, is_sa, has_sm))


@app.route("/api/scripts", methods=["POST"])
@require_permission("script_manage")
def add_script():
    data = request.json
    name = meta_store.add_script(data)
    if name:
        return jsonify({"ok": True, "name": name})
    return jsonify({"ok": False, "error": "脚本名称已存在"}), 400


@app.route("/api/scripts/<name>", methods=["PUT"])
@require_permission("script_manage")
def update_script(name):
    data = request.json
    if meta_store.update_script(name, data):
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "脚本不存在"}), 404


@app.route("/api/scripts/<name>", methods=["DELETE"])
@require_permission("script_manage")
def delete_script(name):
    if meta_store.delete_script(name):
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
    return jsonify(meta_store.list_quick_queries())


@app.route("/api/quick-queries", methods=["POST"])
@require_permission("quick_query_manage")
def add_quick_query():
    data = request.json
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"ok": False, "error": "请输入名称"}), 400
    result = meta_store.add_quick_query(data)
    if result:
        return jsonify({"ok": True, "name": result})
    return jsonify({"ok": False, "error": f"名称 '{name}' 已存在"}), 400


@app.route("/api/quick-queries/<name>", methods=["PUT"])
@require_permission("quick_query_manage")
def update_quick_query(name):
    data = request.json
    if meta_store.update_quick_query(name, data):
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "不存在"}), 404


@app.route("/api/quick-queries/<name>", methods=["DELETE"])
@require_permission("quick_query_manage")
def delete_quick_query(name):
    if meta_store.delete_quick_query(name):
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "不存在"}), 404


@app.route("/api/app-config", methods=["GET"])
def get_app_config():
    cfg = load_app_config()
    return jsonify({"ok": True, "config": cfg})


@app.route("/api/app-config", methods=["POST"])
@require_permission("system_settings")
def update_app_config():
    data = request.json
    current = load_app_config()
    if "nacos" in data and isinstance(data["nacos"], dict):
        current["nacos"] = {**DEFAULT_APP_CONFIG["nacos"], **data["nacos"]}
    if "cache_ttl" in data:
        current["cache_ttl"] = int(data["cache_ttl"])
    if "session_timeout" in data:
        current["session_timeout"] = int(data["session_timeout"])
    if "loading_style" in data:
        current["loading_style"] = data["loading_style"]
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
    meta_ok = False
    try:
        meta_ok = meta_store.reinit_meta_store()
    except Exception as e:
        logger.warning("重连元数据库失败: %s", e)
    return jsonify({"ok": True, "redis_connected": redis_ok, "nacos_connected": nacos_ok, "meta_db_connected": meta_ok})


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


# ── Auth API ──

@app.route("/api/auth/login", methods=["POST"])
def auth_login():
    data = request.json
    login_key = data.get("username", "").strip()
    password = data.get("password", "")
    if not login_key or not password:
        return jsonify({"ok": False, "error": "请输入用户名和密码"}), 400
    user = login_user(login_key, password)
    if not user:
        return jsonify({"ok": False, "error": "用户名/手机号/邮箱或密码错误"}), 401
    perms = get_current_permissions()
    return jsonify({"ok": True, "user": user, "permissions": perms})


@app.route("/api/auth/logout", methods=["POST"])
def auth_logout():
    logout_user()
    return jsonify({"ok": True})


@app.route("/api/auth/me", methods=["GET"])
def auth_me():
    user = get_current_user()
    if not user:
        return jsonify({"ok": False, "error": "未登录"}), 401
    perms = get_current_permissions()
    return jsonify({"ok": True, "user": user, "permissions": perms})


# ── User Management API ──

@app.route("/api/users", methods=["GET"])
@require_permission("user_manage")
def list_users():
    return jsonify(meta_store.list_users())


@app.route("/api/users", methods=["POST"])
@require_permission("user_manage")
def add_user():
    data = request.json
    uid = meta_store.add_user(data)
    if uid:
        return jsonify({"ok": True, "id": uid})
    return jsonify({"ok": False, "error": "用户名已存在或参数错误"}), 400


@app.route("/api/users/<int:user_id>", methods=["PUT"])
@require_permission("user_manage")
def update_user(user_id):
    data = request.json
    if meta_store.update_user(user_id, data):
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "用户不存在或更新失败"}), 404


@app.route("/api/users/<int:user_id>", methods=["DELETE"])
@require_permission("user_manage")
def delete_user(user_id):
    current = get_current_user()
    if current and current.get("id") == user_id:
        return jsonify({"ok": False, "error": "不能删除自己"}), 400
    if meta_store.delete_user(user_id):
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "用户不存在"}), 404


# ── Role Management API ──

@app.route("/api/roles", methods=["GET"])
@require_permission("user_manage")
def list_roles():
    return jsonify(meta_store.list_roles())


@app.route("/api/roles", methods=["POST"])
@require_permission("user_manage")
def add_role():
    data = request.json
    rid = meta_store.add_role(data)
    if rid:
        return jsonify({"ok": True, "id": rid})
    return jsonify({"ok": False, "error": "角色名已存在或参数错误"}), 400


@app.route("/api/roles/<int:role_id>", methods=["PUT"])
@require_permission("user_manage")
def update_role(role_id):
    data = request.json
    if meta_store.update_role(role_id, data):
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "角色不存在或更新失败"}), 404


@app.route("/api/roles/<int:role_id>", methods=["DELETE"])
@require_permission("user_manage")
def delete_role(role_id):
    if meta_store.delete_role(role_id):
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "角色不存在"}), 404


# ── Permission API ──

@app.route("/api/permissions", methods=["GET"])
@require_login
def list_permissions():
    return jsonify(meta_store.list_permissions())


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


# ── Registration API ──

@app.route("/api/auth/register", methods=["POST"])
def auth_register():
    data = request.json
    username = data.get("username", "").strip()
    password = data.get("password", "")
    if not username or not password:
        return jsonify({"ok": False, "error": "用户名和密码为必填项"}), 400
    if len(password) < 6:
        return jsonify({"ok": False, "error": "密码长度不能少于6位"}), 400
    phone = data.get("phone", "").strip()
    email = data.get("email", "").strip()
    if phone:
        sms_code = data.get("smsCode", "")
        if not sms_code:
            return jsonify({"ok": False, "error": "绑定手机号需要验证码"}), 400
        ok, msg = verify_code(phone, "sms", sms_code)
        if not ok:
            return jsonify({"ok": False, "error": msg}), 400
    if email:
        email_code = data.get("emailCode", "")
        if not email_code:
            return jsonify({"ok": False, "error": "绑定邮箱需要验证码"}), 400
        ok, msg = verify_code(email, "email", email_code)
        if not ok:
            return jsonify({"ok": False, "error": msg}), 400
    uid = meta_store.register_user(data)
    if uid:
        return jsonify({"ok": True, "id": uid})
    return jsonify({"ok": False, "error": "注册失败，用户名/手机号/邮箱可能已存在"}), 400


# ── Uniqueness Check API ──

@app.route("/api/auth/check-unique", methods=["POST"])
def auth_check_unique():
    data = request.json
    field = data.get("field", "")
    value = data.get("value", "").strip()
    if not field or not value:
        return jsonify({"ok": True, "unique": True})
    uid = get_current_user_id()
    unique = meta_store.check_unique_field(field, value, uid)
    return jsonify({"ok": True, "unique": unique})


# ── Profile API ──

@app.route("/api/profile", methods=["GET"])
@require_login
def get_profile():
    user = get_current_user()
    if not user:
        return jsonify({"ok": False, "error": "未登录"}), 401
    perms = get_current_permissions()
    return jsonify({"ok": True, "user": user, "permissions": perms})


@app.route("/api/profile", methods=["PUT"])
@require_login
def update_profile():
    data = request.json
    uid = get_current_user_id()
    if not uid:
        return jsonify({"ok": False, "error": "未登录"}), 401
    current_user = meta_store.get_user_by_id(uid)
    phone = data.get("phone", "").strip()
    email = data.get("email", "").strip()
    if phone and phone != (current_user.get("phone") or ""):
        sms_code = data.get("smsCode", "")
        if not sms_code:
            return jsonify({"ok": False, "error": "绑定手机号需要验证码"}), 400
        ok, msg = verify_code(phone, "sms", sms_code)
        if not ok:
            return jsonify({"ok": False, "error": msg}), 400
    if email and email != (current_user.get("email") or ""):
        email_code = data.get("emailCode", "")
        if not email_code:
            return jsonify({"ok": False, "error": "绑定邮箱需要验证码"}), 400
        ok, msg = verify_code(email, "email", email_code)
        if not ok:
            return jsonify({"ok": False, "error": msg}), 400
    if meta_store.update_user_profile(uid, data):
        updated = meta_store.get_user_by_id(uid)
        return jsonify({"ok": True, "user": updated})
    return jsonify({"ok": False, "error": "更新失败，手机号或邮箱可能已被占用"}), 400


@app.route("/api/profile/password", methods=["PUT"])
@require_login
def change_password():
    data = request.json
    uid = get_current_user_id()
    old_pwd = data.get("oldPassword", "")
    new_pwd = data.get("newPassword", "")
    if not old_pwd or not new_pwd:
        return jsonify({"ok": False, "error": "请输入旧密码和新密码"}), 400
    if len(new_pwd) < 6:
        return jsonify({"ok": False, "error": "新密码长度不能少于6位"}), 400
    if meta_store.change_user_password(uid, old_pwd, new_pwd):
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "旧密码不正确"}), 400


# ── Verification Code API ──

@app.route("/api/verify/sms", methods=["POST"])
def send_sms_verify():
    data = request.json
    phone = data.get("phone", "").strip()
    if not phone:
        return jsonify({"ok": False, "error": "请输入手机号"}), 400
    ok, msg, code = send_sms_code(phone)
    if ok:
        return jsonify({"ok": True, "message": msg, "demoCode": code})
    return jsonify({"ok": False, "error": msg}), 400


@app.route("/api/verify/email", methods=["POST"])
def send_email_verify():
    data = request.json
    email = data.get("email", "").strip()
    if not email:
        return jsonify({"ok": False, "error": "请输入邮箱"}), 400
    ok, msg, code = send_email_code(email)
    if ok:
        return jsonify({"ok": True, "message": msg, "demoCode": code})
    return jsonify({"ok": False, "error": msg}), 400


# ── User Script Authorization API ──

@app.route("/api/users/<int:user_id>/scripts", methods=["GET"])
@require_permission("user_manage")
def get_user_scripts(user_id):
    scripts = meta_store.get_user_authorized_scripts(user_id)
    return jsonify({"ok": True, "scriptNames": scripts})


@app.route("/api/users/<int:user_id>/scripts", methods=["PUT"])
@require_permission("user_manage")
def set_user_scripts(user_id):
    data = request.json
    script_names = data.get("scriptNames", [])
    if meta_store.set_user_authorized_scripts(user_id, script_names):
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "设置失败"}), 400


# ── All Scripts (for admin assignment) ──

@app.route("/api/all-scripts", methods=["GET"])
@require_login
def list_all_scripts():
    return jsonify(meta_store.list_scripts())
