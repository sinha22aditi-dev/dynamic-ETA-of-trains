import json
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from config import XGB_DROP, XGB_TIME_COLUMNS, XGB_DERIVED_OUTPUTS

def add_time_features(df: pd.DataFrame) -> pd.DataFrame:
    df=df.copy()
    if "timestamp" in df:
        ts=pd.to_datetime(df["timestamp"], errors="coerce")
        df["hour"] = ts.dt.hour.fillna(df.get("hour", 0)).astype(float)
        df["minute"] = ts.dt.minute.fillna(0).astype(float)
        df["dayofweek_num"] = ts.dt.dayofweek.fillna(0).astype(float)
        df["is_night"] = ((df["hour"] < 6) | (df["hour"] >= 22)).astype(int)
    return df

def build_xgb_features(df: pd.DataFrame):
    df=add_time_features(df)
    drop=set(XGB_DROP)|set(XGB_TIME_COLUMNS)|set(XGB_DERIVED_OUTPUTS)
    # Remove direct target/helper columns if present.
    drop |= {"delay_reason", "delay_reason_category"}
    features=[c for c in df.columns if c not in drop]
    X=df[features].copy()
    # Convert boolean columns to integers.
    for c in X.columns:
        if X[c].dtype == bool:
            X[c]=X[c].astype(int)
    num=X.select_dtypes(include=[np.number]).columns.tolist()
    cat=[c for c in X.columns if c not in num]
    prep=ColumnTransformer([
        ("num", SimpleImputer(strategy="median"), num),
        ("cat", Pipeline([("imp",SimpleImputer(strategy="most_frequent")),
                           ("oh",OneHotEncoder(handle_unknown="ignore"))]), cat)
    ])
    return X, prep, features

def load_json(path: Path):
    return json.loads(path.read_text()) if path.exists() else {}
