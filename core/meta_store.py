import json
import logging
import threading
from datetime import datetime
from typing import Optional, List, Dict, Any

from sqlalchemy import create_engine, text, Column, Integer, String, Text, DateTime, JSON
from sqlalchemy.orm import declarative_base, sessionmaker, Session
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


def _seed_if_empty():
    session = _get_session()
    try:
        if session.query(QuickQuery).count() == 0:
            _seed_quick_queries(session)
        if session.query(Script).count() == 0:
            _seed_scripts(session)
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
