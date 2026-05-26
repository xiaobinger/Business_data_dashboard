import re
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple
import pandas as pd
from sqlalchemy import text
from config import DIMENSION_DATE_FORMATS, DIMENSION_DAY,DIMENSION_MONTH,DIMENSION_YEAR
from core.db_manager import DatabaseManager
from core import meta_store


PARAM_PATTERN = re.compile(r"\{\{(\w+)\}\}")


class ScriptConfig:
    def __init__(self, name: str, sql: str, chart_type: str = "line",
                 conn_name: str = "", merge_conn_names: List[str] = None,
                 description: str = ""):
        self.name = name
        self.sql = sql
        self.chart_type = chart_type
        self.conn_name = conn_name
        self.merge_conn_names = merge_conn_names or []
        self.description = description

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "sql": self.sql,
            "chart_type": self.chart_type,
            "conn_name": self.conn_name,
            "merge_conn_names": self.merge_conn_names,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ScriptConfig":
        return cls(
            name=data.get("name", ""),
            sql=data.get("sql", ""),
            chart_type=data.get("chart_type", "line"),
            conn_name=data.get("conn_name", ""),
            merge_conn_names=data.get("merge_conn_names", []),
            description=data.get("description", ""),
        )

    def extract_params(self) -> List[str]:
        return list(set(PARAM_PATTERN.findall(self.sql)))


class QueryEngine:
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager

    def get_script(self, name: str) -> Optional[ScriptConfig]:
        data = meta_store.get_script(name)
        if data:
            return ScriptConfig.from_dict(data)
        return None

    def get_all_scripts(self) -> List[ScriptConfig]:
        data_list = meta_store.list_scripts()
        return [ScriptConfig.from_dict(d) for d in data_list]

    def get_script_names(self) -> List[str]:
        data_list = meta_store.list_scripts()
        return [d["name"] for d in data_list]

    @staticmethod
    def render_sql(sql: str, params: Dict[str, Any]) -> str:
        STRING_PARAMS = {
            "dimension", "date_format", "date", "start_date", "end_date",
        }

        def replacer(match):
            key = match.group(1)
            if key in params:
                value = params[key]
                if isinstance(value, str):
                    escaped = value.replace("'", "''")
                    if key in STRING_PARAMS:
                        return f"'{escaped}'"
                    return escaped
                return str(value)
            return match.group(0)

        rendered = PARAM_PATTERN.sub(replacer, sql)
        return rendered

    @staticmethod
    def build_dimension_params(dimension: str, date: Optional[str] = None,
                              start_year: Optional[int] = None,
                              end_year: Optional[int] = None) -> Dict[str, Any]:
        import calendar

        now = datetime.now()
        if date:
            try:
                now = datetime.strptime(date, "%Y-%m-%d")
            except ValueError:
                pass

        fmt = DIMENSION_DATE_FORMATS.get(dimension, "%Y-%m-%d")
        date_str = now.strftime(fmt)
        y, m = now.year, now.month

        if dimension == DIMENSION_DAY:
            start_date = datetime(y, m, 1)
            last_day = calendar.monthrange(y, m)[1]
            end_date = datetime(y, m, last_day)
        elif dimension == DIMENSION_MONTH:
            start_date = datetime(y, 1, 1)
            end_date = datetime(y, 12, 31)
        else:
            if start_year is not None and end_year is not None:
                start_date = datetime(start_year, 1, 1)
                end_date = datetime(end_year, 12, 31)
            elif start_year is not None:
                start_date = datetime(start_year, 1, 1)
                end_date = datetime(start_year, 12, 31)
            else:
                start_date = datetime(y, 1, 1)
                end_date = datetime(y, 12, 31)

        params = {
            "dimension": dimension,
            "date_format": fmt,
            "date": date_str,
            "start_date": start_date.strftime("%Y-%m-%d"),
            "end_date": end_date.strftime("%Y-%m-%d"),
            "year": y,
            "month": m,
            "day": now.day,
        }

        if start_year is not None:
            params["start_year"] = start_year
        if end_year is not None:
            params["end_year"] = end_year

        return params

    def execute_query(self, conn_name: str, sql: str,
                      params: Optional[Dict[str, Any]] = None) -> pd.DataFrame:
        conn = self.db_manager.get_connection(conn_name)
        if conn is None:
            raise ValueError(f"Connection '{conn_name}' not found")

        rendered_sql = self.render_sql(sql, params or {})
        engine = conn.get_engine()

        try:
            with engine.connect() as connection:
                df = pd.read_sql(text(rendered_sql), connection)
            return df
        except Exception as e:
            raise RuntimeError(f"Query execution failed: {e}")

    def execute_merge_query(self, conn_names: List[str], sql: str,
                            params: Optional[Dict[str, Any]] = None,
                            merge_mode: str = "concat") -> pd.DataFrame:
        frames = []
        for conn_name in conn_names:
            try:
                df = self.execute_query(conn_name, sql, params)
                if df is not None and not df.empty:
                    df["_source_db"] = conn_name
                    frames.append(df)
            except Exception as e:
                print(f"Warning: query on '{conn_name}' failed: {e}")

        if not frames:
            return pd.DataFrame()

        if merge_mode == "concat":
            return pd.concat(frames, ignore_index=True)
        elif merge_mode == "merge":
            result = frames[0]
            for i in range(1, len(frames)):
                common_cols = list(set(result.columns) & set(frames[i].columns))
                if common_cols:
                    result = result.merge(frames[i], on=common_cols, how="outer", suffixes=("", f"_{i}"))
                else:
                    result = pd.concat([result, frames[i]], axis=1)
            return result
        else:
            return pd.concat(frames, ignore_index=True)
