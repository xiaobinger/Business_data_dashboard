import json
import logging
import threading
from datetime import datetime
from typing import Optional, List, Dict, Any

from sqlalchemy import create_engine, text, Column, Integer, String, Text, DateTime, JSON, ForeignKey, Boolean
from sqlalchemy.orm import declarative_base, sessionmaker, Session, relationship
from sqlalchemy.engine import Engine

from config import get_meta_db_config

logger = logging.getLogger(__name__)

Base = declarative_base()


class QuickQuery(Base):
    __tablename__ = "quick_queries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), unique=True, nullable=False)
    script_name = Column(String(255), default="")
    conn_name = Column(String(255), default="")
    merge_names = Column(JSON, default=list)
    merge_mode = Column(String(50), default="aggregate")
    merge_key = Column(String(255), default="")
    hide_fields = Column(JSON, default=list)
    dimension = Column(String(50), default="day")
    dp_year = Column(Integer, default=None)
    dp_month = Column(Integer, default=None)
    dp_year_start = Column(Integer, default=None)
    dp_year_end = Column(Integer, default=None)
    custom_params = Column(JSON, default=dict)
    layout_count = Column(Integer, default=1)
    chart_configs = Column(JSON, default=list)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "scriptName": self.script_name,
            "connName": self.conn_name,
            "mergeNames": self.merge_names or [],
            "mergeMode": self.merge_mode,
            "mergeKey": self.merge_key,
            "hideFields": self.hide_fields or [],
            "dimension": self.dimension,
            "dpYear": self.dp_year,
            "dpMonth": self.dp_month,
            "dpYearStart": self.dp_year_start,
            "dpYearEnd": self.dp_year_end,
            "customParams": self.custom_params or {},
            "layoutCount": self.layout_count,
            "chartConfigs": self.chart_configs or [],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "QuickQuery":
        return cls(
            name=data.get("name", ""),
            script_name=data.get("scriptName", ""),
            conn_name=data.get("connName", ""),
            merge_names=data.get("mergeNames", []),
            merge_mode=data.get("mergeMode", "aggregate"),
            merge_key=data.get("mergeKey", ""),
            hide_fields=data.get("hideFields", []),
            dimension=data.get("dimension", "day"),
            dp_year=data.get("dpYear"),
            dp_month=data.get("dpMonth"),
            dp_year_start=data.get("dpYearStart"),
            dp_year_end=data.get("dpYearEnd"),
            custom_params=data.get("customParams", {}),
            layout_count=data.get("layoutCount", 1),
            chart_configs=data.get("chartConfigs", []),
        )


class Script(Base):
    __tablename__ = "scripts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), unique=True, nullable=False)
    sql = Column(Text, default="")
    chart_type = Column(String(50), default="line")
    conn_name = Column(String(255), default="")
    merge_conn_names = Column(JSON, default=list)
    description = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    authorized_users = relationship("User", secondary="user_scripts", back_populates="authorized_scripts")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "sql": self.sql,
            "chart_type": self.chart_type,
            "conn_name": self.conn_name,
            "merge_conn_names": self.merge_conn_names or [],
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Script":
        return cls(
            name=data.get("name", ""),
            sql=data.get("sql", ""),
            chart_type=data.get("chart_type", "line"),
            conn_name=data.get("conn_name", ""),
            merge_conn_names=data.get("merge_conn_names", []),
            description=data.get("description", ""),
        )


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    display_name = Column(String(255), default="")
    phone = Column(String(20), unique=True, nullable=True)
    email = Column(String(255), unique=True, nullable=True)
    is_super_admin = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    roles = relationship("Role", secondary="user_roles", back_populates="users")
    authorized_scripts = relationship("Script", secondary="user_scripts", back_populates="authorized_users")

    def to_dict(self, include_roles=True) -> Dict[str, Any]:
        d = {
            "id": self.id,
            "username": self.username,
            "displayName": self.display_name,
            "phone": self.phone or "",
            "email": self.email or "",
            "isSuperAdmin": self.is_super_admin,
            "isActive": self.is_active,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
        }
        if include_roles:
            d["roles"] = [r.to_dict(include_users=False) for r in self.roles]
            d["authorizedScriptNames"] = [s.name for s in self.authorized_scripts]
        return d


class Role(Base):
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), unique=True, nullable=False)
    description = Column(String(255), default="")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    users = relationship("User", secondary="user_roles", back_populates="roles")
    permissions = relationship("Permission", secondary="role_permissions", back_populates="roles")

    def to_dict(self, include_users=False, include_permissions=True) -> Dict[str, Any]:
        d = {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
        }
        if include_permissions:
            d["permissions"] = [p.to_dict() for p in self.permissions]
        if include_users:
            d["users"] = [u.to_dict(include_roles=False) for u in self.users]
        return d


class Permission(Base):
    __tablename__ = "permissions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(100), unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(String(255), default="")
    roles = relationship("Role", secondary="role_permissions", back_populates="permissions")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "code": self.code,
            "name": self.name,
            "description": self.description,
        }


class UserRole(Base):
    __tablename__ = "user_roles"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role_id = Column(Integer, ForeignKey("roles.id", ondelete="CASCADE"), nullable=False)


class RolePermission(Base):
    __tablename__ = "role_permissions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    role_id = Column(Integer, ForeignKey("roles.id", ondelete="CASCADE"), nullable=False)
    permission_id = Column(Integer, ForeignKey("permissions.id", ondelete="CASCADE"), nullable=False)


class UserScript(Base):
    __tablename__ = "user_scripts"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    script_id = Column(Integer, ForeignKey("scripts.id", ondelete="CASCADE"), nullable=False)


_engine: Optional[Engine] = None
_SessionLocal: Optional[sessionmaker] = None
_lock = threading.Lock()
_initialized = False


def _build_db_url(cfg: Dict[str, Any]) -> str:
    return (
        f"mysql+pymysql://{cfg['username']}:{cfg['password']}"
        f"@{cfg['host']}:{cfg['port']}/{cfg['database']}?charset=utf8mb4"
    )


def init_meta_store() -> bool:
    global _engine, _SessionLocal, _initialized
    with _lock:
        if _initialized and _engine is not None:
            return True
        cfg = get_meta_db_config()
        if not cfg:
            logger.warning("元数据库配置未从 Nacos 获取到，meta_store 未初始化")
            return False
        try:
            url = _build_db_url(cfg)
            _engine = create_engine(url, pool_pre_ping=True, pool_recycle=3600)
            Base.metadata.create_all(_engine)
            _migrate_schema(_engine)
            _SessionLocal = sessionmaker(bind=_engine)
            _seed_if_empty()
            _initialized = True
            logger.info("元数据库连接成功: %s:%s/%s", cfg["host"], cfg["port"], cfg["database"])
            return True
        except Exception as e:
            logger.error("元数据库初始化失败: %s", e)
            _engine = None
            _SessionLocal = None
            return False


def reinit_meta_store() -> bool:
    global _engine, _SessionLocal, _initialized
    with _lock:
        old_engine = _engine
        _engine = None
        _SessionLocal = None
        _initialized = False
        if old_engine:
            try:
                old_engine.dispose()
            except Exception:
                pass
    return init_meta_store()


def _get_session() -> Session:
    if _SessionLocal is None:
        raise RuntimeError("meta_store 未初始化，请先调用 init_meta_store()")
    return _SessionLocal()


def _migrate_schema(engine: Engine):
    import sqlalchemy as sa
    insp = sa.inspect(engine)
    existing_cols = {c["name"] for c in insp.get_columns("users")}
    migrations = [
        ("phone", "ALTER TABLE users ADD COLUMN phone VARCHAR(20) NULL UNIQUE"),
        ("email", "ALTER TABLE users ADD COLUMN email VARCHAR(255) NULL UNIQUE"),
    ]
    with engine.begin() as conn:
        for col_name, sql in migrations:
            if col_name not in existing_cols:
                try:
                    conn.execute(text(sql))
                    logger.info("已迁移: 添加 users.%s 列", col_name)
                except Exception as e:
                    logger.warning("迁移 users.%s 失败: %s", col_name, e)


def _seed_if_empty():
    session = _get_session()
    try:
        if session.query(QuickQuery).count() == 0:
            _seed_quick_queries(session)
        if session.query(Script).count() == 0:
            _seed_scripts(session)
        _seed_missing_permissions(session)
        if session.query(User).count() == 0:
            _seed_admin_user(session)
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error("种子数据写入失败: %s", e)
    finally:
        session.close()


def _seed_quick_queries(session: Session):
    seeds = [
        {
            "name": "商户进件数年度汇总统计",
            "scriptName": "商户进件情况",
            "connName": "融聚商户通",
            "mergeNames": ["融聚商户通", "融付商户通", "乐势通", "掌银刷"],
            "mergeMode": "aggregate",
            "mergeKey": "日期",
            "hideFields": [],
            "dimension": "year",
            "dpYear": 2026,
            "dpMonth": 5,
            "dpYearStart": 2018,
            "dpYearEnd": 2033,
            "customParams": {},
            "layoutCount": 1,
            "chartConfigs": [
                {
                    "xCol": "日期",
                    "yCols": ["总进件商户", "进件成功商户数", "激活商户数"],
                    "chartType": "line",
                    "title": "图表 1",
                }
            ],
        },
        {
            "name": "商户交易年度统计",
            "scriptName": "商户交易统计",
            "connName": "融聚商户通",
            "mergeNames": ["融付商户通", "乐势通", "掌银刷", "融聚商户通"],
            "mergeMode": "aggregate",
            "mergeKey": "日期",
            "hideFields": [],
            "dimension": "year",
            "dpYear": 2026,
            "dpMonth": 5,
            "dpYearStart": 2018,
            "dpYearEnd": 2033,
            "customParams": {},
            "layoutCount": 1,
            "chartConfigs": [
                {
                    "xCol": "日期",
                    "yCols": ["总交易流水笔数", "总交易流水金额", "总流量卡金额", "总手续费金额"],
                    "chartType": "line",
                    "title": "图表 1",
                }
            ],
        },
    ]
    for seed in seeds:
        session.add(QuickQuery.from_dict(seed))
    logger.info("已初始化 %d 条快捷查询种子数据", len(seeds))


def _seed_scripts(session: Session):
    seeds = [
        {
            "name": "商户进件情况",
            "sql": "SELECT CASE WHEN m.channel_type='HKRT' THEN '海科融通' WHEN m.channel_type='LEPASS' THEN '乐刷' WHEN m.channel_type='DYIN' THEN '电银' WHEN m.channel_type='HELIPAY' THEN '合利宝' WHEN m.channel_type='ZF' THEN '中付' END 通道,DATE_FORMAT(m.create_time,{{date_format}}) 日期,count(1) 总进件商户,SUM(CASE WHEN m.apply_status=2 THEN 1 ELSE 0 END) 进件成功商户数,SUM(IF(m.activate_time IS NOT NULL,1,0)) 激活商户数 FROM posp_business.merchant m WHERE m.create_time BETWEEN CONCAT({{start_date}},' 00:00:00') AND CONCAT({{end_date}},' 23:59:59') GROUP BY DATE_FORMAT(m.create_time,{{date_format}})",
            "chart_type": "line",
            "conn_name": "融聚商户通",
            "merge_conn_names": [],
            "description": "",
        },
        {
            "name": "商户交易统计",
            "sql": "SELECT CASE WHEN t.channel_code='hkrt' THEN '融聚商户通' WHEN t.channel_code='zft_plus' THEN '支付通PLUS' WHEN t.channel_code='dyin' THEN '电银' WHEN t.channel_code='helipay' THEN '合利宝' WHEN t.channel_code='zf' THEN '中付' WHEN t.channel_code='lepass' THEN '乐刷' END 通道,DATE_FORMAT(t.trade_time,{{date_format}}) 日期,count(1) 总交易流水笔数,sum(t.trade_amount)/100 总交易流水金额,sum(IF(t.flow_activity_amount IS NULL,0,t.flow_activity_amount))/100 总流量卡金额,sum(ifnull(t.trade_t0_fee,0)+ifnull(t.trade_fee_amount,0))/100 总手续费金额 FROM posp_business.trade_order t WHERE t.trade_time BETWEEN CONCAT({{start_date}},' 00:00:00') AND CONCAT({{end_date}},' 23:59:59') AND t.trade_status=1 GROUP BY DATE_FORMAT(t.trade_time,{{date_format}}),t.channel_code ORDER BY t.channel_code,DATE_FORMAT(t.trade_time,{{date_format}})",
            "chart_type": "line",
            "conn_name": "融聚商户通",
            "merge_conn_names": [],
            "description": "",
        },
    ]
    for seed in seeds:
        session.add(Script.from_dict(seed))
    logger.info("已初始化 %d 条脚本种子数据", len(seeds))


BUILTIN_PERMISSIONS = [
    ("script_manage", "脚本管理", "新增、编辑、删除SQL脚本"),
    ("datasource_manage", "数据源管理", "新增、编辑、删除数据库连接"),
    ("chart_layout", "图表布局设置", "修改图表布局和配置"),
    ("system_settings", "系统设置", "修改Nacos、Redis、缓存等系统配置"),
    ("quick_query_manage", "快捷查询管理", "新增、编辑、删除快捷查询"),
    ("user_manage", "用户管理", "管理用户、角色和权限"),
    ("export_data", "导出数据", "导出查询结果为Excel/CSV"),
    ("save_chart", "保存图表", "保存图表为图片"),
]


def _seed_permissions(session: Session):
    for code, name, desc in BUILTIN_PERMISSIONS:
        session.add(Permission(code=code, name=name, description=desc))
    logger.info("已初始化 %d 条权限种子数据", len(BUILTIN_PERMISSIONS))


def _seed_missing_permissions(session: Session):
    existing = {p.code for p in session.query(Permission).all()}
    added = 0
    for code, name, desc in BUILTIN_PERMISSIONS:
        if code not in existing:
            session.add(Permission(code=code, name=name, description=desc))
            added += 1
    if added:
        logger.info("已补全 %d 条缺失权限", added)


def _seed_admin_user(session: Session):
    from werkzeug.security import generate_password_hash
    admin = User(
        username="admin",
        password_hash=generate_password_hash("admin123"),
        display_name="超级管理员",
        is_super_admin=True,
        is_active=True,
    )
    session.add(admin)
    logger.info("已初始化超级管理员账号: admin / admin123")


def is_available() -> bool:
    return _initialized and _engine is not None


# ── QuickQuery CRUD ──

def list_quick_queries() -> List[Dict[str, Any]]:
    if not init_meta_store():
        return []
    session = _get_session()
    try:
        rows = session.query(QuickQuery).order_by(QuickQuery.id).all()
        return [r.to_dict() for r in rows]
    finally:
        session.close()


def add_quick_query(data: Dict[str, Any]) -> Optional[str]:
    if not init_meta_store():
        return None
    session = _get_session()
    try:
        name = data.get("name", "").strip()
        if session.query(QuickQuery).filter_by(name=name).first():
            return None
        obj = QuickQuery.from_dict(data)
        session.add(obj)
        session.commit()
        return name
    except Exception:
        session.rollback()
        return None
    finally:
        session.close()


def update_quick_query(old_name: str, data: Dict[str, Any]) -> bool:
    if not init_meta_store():
        return False
    session = _get_session()
    try:
        obj = session.query(QuickQuery).filter_by(name=old_name).first()
        if not obj:
            return False
        new_name = data.get("name", old_name)
        if new_name != old_name and session.query(QuickQuery).filter_by(name=new_name).first():
            return False
        obj.name = new_name
        obj.script_name = data.get("scriptName", obj.script_name)
        obj.conn_name = data.get("connName", obj.conn_name)
        obj.merge_names = data.get("mergeNames", obj.merge_names)
        obj.merge_mode = data.get("mergeMode", obj.merge_mode)
        obj.merge_key = data.get("mergeKey", obj.merge_key)
        obj.hide_fields = data.get("hideFields", obj.hide_fields)
        obj.dimension = data.get("dimension", obj.dimension)
        if "dpYear" in data:
            obj.dp_year = data["dpYear"]
        if "dpMonth" in data:
            obj.dp_month = data["dpMonth"]
        if "dpYearStart" in data:
            obj.dp_year_start = data["dpYearStart"]
        if "dpYearEnd" in data:
            obj.dp_year_end = data["dpYearEnd"]
        obj.custom_params = data.get("customParams", obj.custom_params)
        obj.layout_count = data.get("layoutCount", obj.layout_count)
        obj.chart_configs = data.get("chartConfigs", obj.chart_configs)
        obj.updated_at = datetime.now()
        session.commit()
        return True
    except Exception:
        session.rollback()
        return False
    finally:
        session.close()


def delete_quick_query(name: str) -> bool:
    if not init_meta_store():
        return False
    session = _get_session()
    try:
        obj = session.query(QuickQuery).filter_by(name=name).first()
        if not obj:
            return False
        session.delete(obj)
        session.commit()
        return True
    except Exception:
        session.rollback()
        return False
    finally:
        session.close()


# ── Script CRUD ──

def list_scripts() -> List[Dict[str, Any]]:
    if not init_meta_store():
        return []
    session = _get_session()
    try:
        rows = session.query(Script).order_by(Script.id).all()
        return [r.to_dict() for r in rows]
    finally:
        session.close()


def get_script(name: str) -> Optional[Dict[str, Any]]:
    if not init_meta_store():
        return None
    session = _get_session()
    try:
        obj = session.query(Script).filter_by(name=name).first()
        return obj.to_dict() if obj else None
    finally:
        session.close()


def add_script(data: Dict[str, Any]) -> Optional[str]:
    if not init_meta_store():
        return None
    session = _get_session()
    try:
        name = data.get("name", "").strip()
        if session.query(Script).filter_by(name=name).first():
            return None
        obj = Script.from_dict(data)
        session.add(obj)
        session.commit()
        return name
    except Exception:
        session.rollback()
        return None
    finally:
        session.close()


def update_script(old_name: str, data: Dict[str, Any]) -> bool:
    if not init_meta_store():
        return False
    session = _get_session()
    try:
        obj = session.query(Script).filter_by(name=old_name).first()
        if not obj:
            return False
        new_name = data.get("name", old_name)
        if new_name != old_name and session.query(Script).filter_by(name=new_name).first():
            return False
        obj.name = new_name
        obj.sql = data.get("sql", obj.sql)
        obj.chart_type = data.get("chart_type", obj.chart_type)
        obj.conn_name = data.get("conn_name", obj.conn_name)
        obj.merge_conn_names = data.get("merge_conn_names", obj.merge_conn_names)
        obj.description = data.get("description", obj.description)
        obj.updated_at = datetime.now()
        session.commit()
        return True
    except Exception:
        session.rollback()
        return False
    finally:
        session.close()


def delete_script(name: str) -> bool:
    if not init_meta_store():
        return False
    session = _get_session()
    try:
        obj = session.query(Script).filter_by(name=name).first()
        if not obj:
            return False
        session.delete(obj)
        session.commit()
        return True
    except Exception:
        session.rollback()
        return False
    finally:
        session.close()


# ── User CRUD ──

def authenticate_user(username: str, password: str) -> Optional[Dict[str, Any]]:
    if not init_meta_store():
        return None
    from werkzeug.security import check_password_hash
    session = _get_session()
    try:
        user = session.query(User).filter_by(username=username, is_active=True).first()
        if user and check_password_hash(user.password_hash, password):
            return user.to_dict()
        return None
    finally:
        session.close()


def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    if not init_meta_store():
        return None
    session = _get_session()
    try:
        user = session.query(User).filter_by(id=user_id).first()
        return user.to_dict() if user else None
    finally:
        session.close()


def get_user_permissions(user_id: int) -> List[str]:
    if not init_meta_store():
        return []
    session = _get_session()
    try:
        user = session.query(User).filter_by(id=user_id).first()
        if not user:
            return []
        if user.is_super_admin:
            return [p.code for p in session.query(Permission).all()]
        codes = set()
        for role in user.roles:
            for perm in role.permissions:
                codes.add(perm.code)
        return sorted(codes)
    finally:
        session.close()


def list_users() -> List[Dict[str, Any]]:
    if not init_meta_store():
        return []
    session = _get_session()
    try:
        rows = session.query(User).order_by(User.id).all()
        return [r.to_dict() for r in rows]
    finally:
        session.close()


def add_user(data: Dict[str, Any]) -> Optional[int]:
    if not init_meta_store():
        return None
    from werkzeug.security import generate_password_hash
    session = _get_session()
    try:
        username = data.get("username", "").strip()
        if not username:
            return None
        if session.query(User).filter_by(username=username).first():
            return None
        phone = data.get("phone", "").strip() or None
        email = data.get("email", "").strip() or None
        if phone and session.query(User).filter_by(phone=phone).first():
            return None
        if email and session.query(User).filter_by(email=email).first():
            return None
        user = User(
            username=username,
            password_hash=generate_password_hash(data.get("password", "")),
            display_name=data.get("displayName", ""),
            phone=phone,
            email=email,
            is_super_admin=data.get("isSuperAdmin", False),
            is_active=data.get("isActive", True),
        )
        session.add(user)
        session.flush()
        role_ids = data.get("roleIds", [])
        if role_ids:
            for rid in role_ids:
                role = session.query(Role).filter_by(id=rid).first()
                if role:
                    user.roles.append(role)
        script_names = data.get("authorizedScriptNames", [])
        if script_names:
            for name in script_names:
                script = session.query(Script).filter_by(name=name).first()
                if script:
                    user.authorized_scripts.append(script)
        session.commit()
        return user.id
    except Exception:
        session.rollback()
        return None
    finally:
        session.close()


def update_user(user_id: int, data: Dict[str, Any]) -> bool:
    if not init_meta_store():
        return False
    from werkzeug.security import generate_password_hash
    session = _get_session()
    try:
        user = session.query(User).filter_by(id=user_id).first()
        if not user:
            return False
        if "displayName" in data:
            user.display_name = data["displayName"]
        if "password" in data and data["password"]:
            user.password_hash = generate_password_hash(data["password"])
        if "isActive" in data:
            user.is_active = data["isActive"]
        if "isSuperAdmin" in data:
            user.is_super_admin = data["isSuperAdmin"]
        if "phone" in data:
            phone = data["phone"].strip() or None
            if phone:
                existing = session.query(User).filter(User.phone == phone, User.id != user_id).first()
                if existing:
                    return False
            user.phone = phone
        if "email" in data:
            email = data["email"].strip() or None
            if email:
                existing = session.query(User).filter(User.email == email, User.id != user_id).first()
                if existing:
                    return False
            user.email = email
        if "roleIds" in data:
            user.roles = []
            for rid in data["roleIds"]:
                role = session.query(Role).filter_by(id=rid).first()
                if role:
                    user.roles.append(role)
        if "authorizedScriptNames" in data:
            user.authorized_scripts = []
            for name in data["authorizedScriptNames"]:
                script = session.query(Script).filter_by(name=name).first()
                if script:
                    user.authorized_scripts.append(script)
        user.updated_at = datetime.now()
        session.commit()
        return True
    except Exception:
        session.rollback()
        return False
    finally:
        session.close()


def delete_user(user_id: int) -> bool:
    if not init_meta_store():
        return False
    session = _get_session()
    try:
        user = session.query(User).filter_by(id=user_id).first()
        if not user:
            return False
        session.delete(user)
        session.commit()
        return True
    except Exception:
        session.rollback()
        return False
    finally:
        session.close()


# ── Role CRUD ──

def list_roles() -> List[Dict[str, Any]]:
    if not init_meta_store():
        return []
    session = _get_session()
    try:
        rows = session.query(Role).order_by(Role.id).all()
        return [r.to_dict() for r in rows]
    finally:
        session.close()


def add_role(data: Dict[str, Any]) -> Optional[int]:
    if not init_meta_store():
        return None
    session = _get_session()
    try:
        name = data.get("name", "").strip()
        if not name:
            return None
        if session.query(Role).filter_by(name=name).first():
            return None
        role = Role(name=name, description=data.get("description", ""))
        session.add(role)
        session.flush()
        perm_ids = data.get("permissionIds", [])
        if perm_ids:
            for pid in perm_ids:
                perm = session.query(Permission).filter_by(id=pid).first()
                if perm:
                    role.permissions.append(perm)
        session.commit()
        return role.id
    except Exception:
        session.rollback()
        return None
    finally:
        session.close()


def update_role(role_id: int, data: Dict[str, Any]) -> bool:
    if not init_meta_store():
        return False
    session = _get_session()
    try:
        role = session.query(Role).filter_by(id=role_id).first()
        if not role:
            return False
        if "name" in data:
            new_name = data["name"].strip()
            if new_name != role.name and session.query(Role).filter_by(name=new_name).first():
                return False
            role.name = new_name
        if "description" in data:
            role.description = data["description"]
        if "permissionIds" in data:
            role.permissions = []
            for pid in data["permissionIds"]:
                perm = session.query(Permission).filter_by(id=pid).first()
                if perm:
                    role.permissions.append(perm)
        role.updated_at = datetime.now()
        session.commit()
        return True
    except Exception:
        session.rollback()
        return False
    finally:
        session.close()


def delete_role(role_id: int) -> bool:
    if not init_meta_store():
        return False
    session = _get_session()
    try:
        role = session.query(Role).filter_by(id=role_id).first()
        if not role:
            return False
        session.delete(role)
        session.commit()
        return True
    except Exception:
        session.rollback()
        return False
    finally:
        session.close()


# ── Permission ──

def list_permissions() -> List[Dict[str, Any]]:
    if not init_meta_store():
        return []
    session = _get_session()
    try:
        rows = session.query(Permission).order_by(Permission.id).all()
        return [r.to_dict() for r in rows]
    finally:
        session.close()


# ── Registration & Multi-auth ──

def register_user(data: Dict[str, Any]) -> Optional[int]:
    if not init_meta_store():
        return None
    from werkzeug.security import generate_password_hash
    session = _get_session()
    try:
        username = data.get("username", "").strip()
        password = data.get("password", "")
        if not username or not password:
            return None
        if session.query(User).filter_by(username=username).first():
            return None
        phone = data.get("phone", "").strip() or None
        email = data.get("email", "").strip() or None
        if phone and session.query(User).filter_by(phone=phone).first():
            return None
        if email and session.query(User).filter_by(email=email).first():
            return None
        user = User(
            username=username,
            password_hash=generate_password_hash(password),
            display_name=data.get("displayName", ""),
            phone=phone,
            email=email,
            is_super_admin=False,
            is_active=True,
        )
        session.add(user)
        session.commit()
        return user.id
    except Exception:
        session.rollback()
        return None
    finally:
        session.close()


def authenticate_user_multi(login_key: str, password: str) -> Optional[Dict[str, Any]]:
    if not init_meta_store():
        return None
    from werkzeug.security import check_password_hash
    session = _get_session()
    try:
        login_key = login_key.strip()
        if not login_key:
            return None
        user = session.query(User).filter_by(is_active=True).filter(
            (User.username == login_key) | (User.phone == login_key) | (User.email == login_key)
        ).first()
        if user and check_password_hash(user.password_hash, password):
            return user.to_dict()
        return None
    finally:
        session.close()


def check_unique_field(field: str, value: str, exclude_user_id: int = None) -> bool:
    if not init_meta_store():
        return False
    session = _get_session()
    try:
        col_map = {"username": User.username, "phone": User.phone, "email": User.email}
        col = col_map.get(field)
        if not col:
            return False
        q = session.query(User).filter(col == value.strip())
        if exclude_user_id:
            q = q.filter(User.id != exclude_user_id)
        return q.first() is None
    finally:
        session.close()


# ── Profile ──

def update_user_profile(user_id: int, data: Dict[str, Any]) -> bool:
    if not init_meta_store():
        return False
    session = _get_session()
    try:
        user = session.query(User).filter_by(id=user_id).first()
        if not user:
            return False
        if "displayName" in data:
            user.display_name = data["displayName"]
        if "phone" in data:
            phone = data["phone"].strip() or None
            if phone:
                existing = session.query(User).filter(User.phone == phone, User.id != user_id).first()
                if existing:
                    return False
            user.phone = phone
        if "email" in data:
            email = data["email"].strip() or None
            if email:
                existing = session.query(User).filter(User.email == email, User.id != user_id).first()
                if existing:
                    return False
            user.email = email
        user.updated_at = datetime.now()
        session.commit()
        return True
    except Exception:
        session.rollback()
        return False
    finally:
        session.close()


def change_user_password(user_id: int, old_password: str, new_password: str) -> bool:
    if not init_meta_store():
        return False
    from werkzeug.security import check_password_hash, generate_password_hash
    session = _get_session()
    try:
        user = session.query(User).filter_by(id=user_id).first()
        if not user:
            return False
        if not check_password_hash(user.password_hash, old_password):
            return False
        user.password_hash = generate_password_hash(new_password)
        user.updated_at = datetime.now()
        session.commit()
        return True
    except Exception:
        session.rollback()
        return False
    finally:
        session.close()


# ── User Script Authorization ──

def get_user_authorized_scripts(user_id: int) -> List[str]:
    if not init_meta_store():
        return []
    session = _get_session()
    try:
        user = session.query(User).filter_by(id=user_id).first()
        if not user:
            return []
        return [s.name for s in user.authorized_scripts]
    finally:
        session.close()


def set_user_authorized_scripts(user_id: int, script_names: List[str]) -> bool:
    if not init_meta_store():
        return False
    session = _get_session()
    try:
        user = session.query(User).filter_by(id=user_id).first()
        if not user:
            return False
        user.authorized_scripts = []
        for name in script_names:
            script = session.query(Script).filter_by(name=name).first()
            if script:
                user.authorized_scripts.append(script)
        session.commit()
        return True
    except Exception:
        session.rollback()
        return False
    finally:
        session.close()


def list_scripts_for_user(user_id: int, is_super_admin: bool, has_script_manage: bool) -> List[Dict[str, Any]]:
    if not init_meta_store():
        return []
    session = _get_session()
    try:
        if is_super_admin or has_script_manage:
            rows = session.query(Script).order_by(Script.id).all()
        else:
            user = session.query(User).filter_by(id=user_id).first()
            if not user:
                return []
            rows = user.authorized_scripts
        return [r.to_dict() for r in rows]
    finally:
        session.close()
