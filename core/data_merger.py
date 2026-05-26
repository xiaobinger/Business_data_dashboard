from typing import List, Optional, Dict, Any
import pandas as pd
from core.db_manager import DatabaseManager
from core.query_engine import QueryEngine


class DataMerger:
    def __init__(self, query_engine: QueryEngine):
        self.query_engine = query_engine

    def merge_from_sources(self, conn_names: List[str], sql: str,
                           params: Optional[Dict[str, Any]] = None,
                           merge_mode: str = "concat",
                           merge_keys: Optional[List[str]] = None,
                           merge_key: Optional[str] = None) -> pd.DataFrame:
        frames = []
        for conn_name in conn_names:
            try:
                df = self.query_engine.execute_query(conn_name, sql, params)
                if df is not None and not df.empty:
                    df["_source"] = conn_name
                    frames.append(df)
            except Exception as e:
                print(f"Merge: skip '{conn_name}' due to error: {e}")

        if not frames:
            return pd.DataFrame()

        if merge_mode == "concat":
            return pd.concat(frames, ignore_index=True)
        elif merge_mode == "merge" and merge_keys:
            result = frames[0]
            suffix_counter = 1
            for i in range(1, len(frames)):
                suffix = f"_{suffix_counter}"
                suffix_counter += 1
                result = result.merge(
                    frames[i],
                    on=merge_keys,
                    how="outer",
                    suffixes=("", suffix),
                )
            return result
        elif merge_mode == "sum":
            for f in frames:
                if "_source" in f.columns:
                    f.drop(columns=["_source"], inplace=True)
            combined = pd.concat(frames, ignore_index=True)
            numeric_cols = combined.select_dtypes(include="number").columns.tolist()
            if merge_key:
                group_cols = [merge_key]
            else:
                group_cols = [c for c in combined.columns if c not in numeric_cols]
            if group_cols:
                agg_dict = {c: "sum" for c in numeric_cols}
                result = combined.groupby(group_cols, as_index=False).agg(agg_dict)
                return result
            return combined
        else:
            return pd.concat(frames, ignore_index=True)

    @staticmethod
    def auto_detect_merge_keys(frames: List[pd.DataFrame]) -> List[str]:
        if not frames:
            return []
        common = set(frames[0].columns)
        for df in frames[1:]:
            common &= set(df.columns)
        return [c for c in common if c != "_source"]
