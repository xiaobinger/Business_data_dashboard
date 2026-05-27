import functools
import logging
import time
from typing import List, Optional

from flask import request, jsonify, session

from core import meta_store

logger = logging.getLogger(__name__)

SESSION_KEY_USER_ID = "user_id"
SESSION_KEY_USERNAME = "username"
SESSION_KEY_IS_SUPER = "is_super_admin"
SESSION_KEY_LAST_ACTIVITY = "last_activity"


def login_user(login_key: str, password: str) -> Optional[dict]:
    user = meta_store.authenticate_user_multi(login_key, password)
    if not user:
        return None
    session[SESSION_KEY_USER_ID] = user["id"]
    session[SESSION_KEY_USERNAME] = user["username"]
    session[SESSION_KEY_IS_SUPER] = user.get("isSuperAdmin", False)
    session[SESSION_KEY_LAST_ACTIVITY] = time.time()
    session.permanent = True
    return user


def logout_user():
    session.pop(SESSION_KEY_USER_ID, None)
    session.pop(SESSION_KEY_USERNAME, None)
    session.pop(SESSION_KEY_IS_SUPER, None)
    session.pop(SESSION_KEY_LAST_ACTIVITY, None)


def touch_session():
    if get_current_user_id():
        session[SESSION_KEY_LAST_ACTIVITY] = time.time()


def check_session_timeout(timeout_minutes: int) -> bool:
    last = session.get(SESSION_KEY_LAST_ACTIVITY)
    if not last:
        return False
    if time.time() - last > timeout_minutes * 60:
        logout_user()
        return False
    return True


def get_current_user_id() -> Optional[int]:
    return session.get(SESSION_KEY_USER_ID)


def get_current_username() -> Optional[str]:
    return session.get(SESSION_KEY_USERNAME)


def is_super_admin() -> bool:
    return session.get(SESSION_KEY_IS_SUPER, False)


def get_current_user() -> Optional[dict]:
    uid = get_current_user_id()
    if not uid:
        return None
    return meta_store.get_user_by_id(uid)


def get_current_permissions() -> List[str]:
    uid = get_current_user_id()
    if not uid:
        return []
    return meta_store.get_user_permissions(uid)


def has_permission(code: str) -> bool:
    if is_super_admin():
        return True
    return code in get_current_permissions()


def require_login(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not get_current_user_id():
            return jsonify({"ok": False, "error": "未登录，请先登录"}), 401
        return f(*args, **kwargs)
    return decorated


def require_permission(code: str):
    def decorator(f):
        @functools.wraps(f)
        def decorated(*args, **kwargs):
            if not get_current_user_id():
                return jsonify({"ok": False, "error": "未登录，请先登录"}), 401
            if not has_permission(code):
                return jsonify({"ok": False, "error": "权限不足"}), 403
            return f(*args, **kwargs)
        return decorated
    return decorator
