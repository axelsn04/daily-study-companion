# src/finance.py
from __future__ import annotations

import io
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import pandas as pd
from dotenv import load_dotenv

load_dotenv()

# -------- Config --------
RAW_TICKERS = [
    t.strip()
    for t in os.getenv("STOCK_TICKERS", "SPY,NVDA,MSFT,TSLA,AMZN").split(",")
    if t.strip()
]
PRICE_WINDOW_DAYS = int(os.getenv("PRICE_WINDOW_DAYS", "14"))
CHARTS_DIR = os.getenv("CHARTS_DIR", "data/processed/charts")

# Alias (por si el .env trae índices como ^GSPC)
TICKER_ALIASES = {"^GSPC": "SPY"}

# -------- Helpers --------
def _start(days: int) -> datetime:
    # margen extra para asegurar puntos suficientes
    return datetime.utcnow() - timedelta(days=days * 2)

def _clean(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index, utc=True, errors="coerce")
    df = df.sort_index()
    return df.dropna(how="all")

def _select_close(df: pd.DataFrame) -> Optional[pd.Series]:
    """Devuelve la mejor serie de cierre disponible."""
    for c in ["Close", "Adj Close", "Adj Close*", "close"]:
        if c in df.columns:
            s = pd.to_numeric(df[c], errors="coerce").dropna()
            if not s.empty:
                return s
    num = df.select_dtypes(include="number")
    if not num.empty:
        s = pd.to_numeric(num.iloc[:, 0], errors="coerce").dropna()
        if not s.empty:
            return s
    return None

def _stooq_candidates(tk: str) -> List[str]:
    """
    Variantes aceptadas por Stooq. Para USA: TICKER.US
    """
    base = tk.upper()
    cands = [base]
    if ".US" not in base:
        cands.append(f"{base}.US")
    return cands

# -------- Fetchers --------
def _fetch_stooq_pdr(tk: str, start: datetime) -> Optional[pd.DataFrame]:
    """Intenta Stooq vía pandas-datareader."""
    try:
        from pandas_datareader import data as pdr  # type: ignore
    except Exception:
        return None

    for sym in _stooq_candidates(tk):
        try:
            df = pdr.DataReader(sym, "stooq", start=start.date())
            if isinstance(df, pd.DataFrame) and not df.empty:
                # Stooq llega descendente
                return _clean(df.sort_index())
        except Exception:
            continue
    return None

def _fetch_stooq_csv(tk: str, start: datetime, end: Optional[datetime] = None) -> Optional[pd.DataFrame]:
    """
    Descarga directa CSV de Stooq:
    https://stooq.com/q/d/l/?s=spy.us&i=d&d1=YYYYMMDD&d2=YYYYMMDD
    """
    import requests

    if end is None:
        end = datetime.utcnow()

    for sym in _stooq_candidates(tk):
        s = sym.lower()  # en la URL va en minúsculas, p.ej., spy.us
        d1 = start.strftime("%Y%m%d")
        d2 = end.strftime("%Y%m%d")
        url = f"https://stooq.com/q/d/l/?s={s}&i=d&d1={d1}&d2={d2}"
        text: Optional[str] = None
        try:
            r = requests.get(url, timeout=20)
            r.raise_for_status()
            text = r.text or ""
        except Exception:
            text = None

        if not text or text.strip().startswith("<!DOCTYPE") or text.strip().startswith("404"):
            continue

        try:
            df = pd.read_csv(io.StringIO(text))
        except Exception:
            continue

        if isinstance(df, pd.DataFrame) and not df.empty:
            # Esperamos columnas: Date, Open, High, Low, Close, Volume
            if "Date" in df.columns:
                df["Date"] = pd.to_datetime(df["Date"], utc=True, errors="coerce")
                df = df.set_index("Date")
            df = _clean(df)
            if not df.empty:
                return df
    return None

# -------- API --------
def fetch_prices(tickers: Optional[List[str]] = None) -> Dict[str, pd.DataFrame]:
    """
    Devuelve dict[ticker] -> DataFrame (OHLCV). Orden de intentos:
      1) pandas-datareader/Stooq
      2) descarga directa CSV de Stooq
    Omite tickers sin datos (silencioso).
    """
    if tickers is None:
        tickers = RAW_TICKERS
    start = _start(PRICE_WINDOW_DAYS)

    out: Dict[str, pd.DataFrame] = {}
    for raw in tickers:
        tk = TICKER_ALIASES.get(raw, raw)
        df = _fetch_stooq_pdr(tk, start) or _fetch_stooq_csv(tk, start)
        if df is not None and not df.empty:
            out[raw] = df
    return out

def basic_stats(prices: Dict[str, pd.DataFrame]) -> Dict[str, Dict[str, float]]:
    """
    Calcula estadísticas por ticker usando la serie de cierre seleccionada.
    Retorna: dict[ticker] -> {last, mean, std, min, max, pct_change}
    """
    stats: Dict[str, Dict[str, float]] = {}
    for t, df in prices.items():
        s = _select_close(df)
        if s is None or s.empty:
            continue
        s = s.iloc[-PRICE_WINDOW_DAYS:] if len(s) > PRICE_WINDOW_DAYS else s
        if s.empty:
            continue

        first, last = float(s.iloc[0]), float(s.iloc[-1])
        pct = ((last - first) / first * 100.0) if first else 0.0
        stats[t] = {
            "last": last,
            "mean": float(s.mean()),
            "std": float(s.std(ddof=0)),
            "min": float(s.min()),
            "max": float(s.max()),
            "pct_change": pct,
        }
    return stats

def plot_prices(prices: Dict[str, pd.DataFrame]) -> List[str]:
    """
    Genera PNG por ticker con la serie de cierre seleccionada.
    Devuelve lista de rutas a imágenes (absolutas).
    """
    import matplotlib  # type: ignore
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt  # type: ignore
    from pathlib import Path

    outdir = Path(CHARTS_DIR)
    outdir.mkdir(parents=True, exist_ok=True)
    imgs: List[str] = []

    for t, df in prices.items():
        s = _select_close(df)
        if s is None or s.empty:
            continue

        # recorta ventana
        s = s.iloc[-PRICE_WINDOW_DAYS:] if len(s) > PRICE_WINDOW_DAYS else s
        if s.empty:
            continue

        # normaliza índice y valores (silencia ArrayLike warnings)
        xs = pd.to_datetime(s.index, errors="coerce").to_pydatetime()
        ys = s.astype(float).values
        xs_list = list(xs)                         
        ys_list = [float(v) for v in ys.tolist()] 

        fig = plt.figure(figsize=(8, 3))
        plt.plot(xs_list, ys_list, linewidth=1.6)
        plt.title(f"{t} — {len(s)} pts ({xs[0].date()} → {xs[-1].date()})")
        plt.xlabel("")
        plt.ylabel("Close")
        plt.tight_layout()

        out_path = outdir / f"{t}_close.png"
        fig.savefig(out_path, dpi=140)
        plt.close(fig)

        report_out = os.getenv("REPORT_OUT_PATH", "data/processed/daily_report.html")
        report_dir = Path(report_out).parent
        rel = os.path.relpath(out_path, report_dir)
        imgs.append(rel.replace(os.sep, "/")) 

    return imgs
