import os
from typing import List, Dict, Optional
from io import StringIO

import pandas as pd
import matplotlib.pyplot as plt
import requests
from dotenv import load_dotenv

load_dotenv()

# Puedes ajustar desde .env
TICKERS = [t.strip() for t in os.getenv("STOCK_TICKERS", "^GSPC,NVDA,MSFT,TSLA,AMZN").split(",") if t.strip()]
FALLBACK_DAILY_DAYS = int(os.getenv("FALLBACK_DAILY_DAYS", "90"))

# Mapeo a símbolos de Stooq (diario)
# Stooq no tiene ^GSPC (índice); usamos SPY.US (ETF del S&P 500)
_STOOQ_MAP = {
    "^GSPC": "SPY.US",
    "NVDA": "NVDA.US",
    "MSFT": "MSFT.US",
    "TSLA": "TSLA.US",
    "AMZN": "AMZN.US",
}

def _stooq_symbol(ticker: str) -> str:
    if ticker in _STOOQ_MAP:
        return _STOOQ_MAP[ticker]
    # Para acciones USA, stooq usa sufijo .US
    return f"{ticker}.US" if ticker.isalpha() else ticker

def _stooq_download_csv(ticker: str, days: int) -> Optional[pd.DataFrame]:
    """
    Descarga CSV diario desde Stooq y devuelve DataFrame OHLCV ordenado ascendente.
    URL ejemplo: https://stooq.com/q/d/l/?s=nvda.us&i=d
    """
    sym = _stoq_symbol = _stooq_symbol(ticker).lower()
    url = f"https://stooq.com/q/d/l/?s={sym}&i=d"
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    if not r.text or r.text.strip().lower().startswith("<!doctype"):
        return None
    df = pd.read_csv(StringIO(r.text))
    if df.empty:
        return None
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce", utc=False)
    df = df.dropna(subset=["Date"]).sort_values("Date").set_index("Date")
    keep = ["Open", "High", "Low", "Close", "Volume"]
    df = df[keep].tail(days)
    return df

def fetch_prices(tickers: List[str] = TICKERS) -> Dict[str, pd.DataFrame]:
    """
    Solo Stooq (diario). Devuelve {ticker: DataFrame(OHLCV)} sin ruido de Yahoo.
    """
    out: Dict[str, pd.DataFrame] = {}
    for t in tickers:
        try:
            df = _stooq_download_csv(t, FALLBACK_DAILY_DAYS)
        except Exception:
            df = None
        if df is not None and not df.empty:
            out[t] = df.dropna()
    return out

def basic_stats(df: pd.DataFrame) -> Dict[str, float]:
    close = df["Close"]
    return {
        "last": float(close.iloc[-1]),
        "mean": float(close.mean()),
        "std": float(close.std()),
        "min": float(close.min()),
        "max": float(close.max()),
        "pct_change": float((close.iloc[-1] / close.iloc[0] - 1) * 100.0),
    }

def plot_prices(df: pd.DataFrame, ticker: str, save_path: str | None = None):
    fig, ax1 = plt.subplots(figsize=(8, 4))
    ax1.plot(df.index, df["Close"], label="Close", linewidth=2)
    ax1.set_title(f"{ticker} — {len(df)} pts ({df.index.min().date()} → {df.index.max().date()})")
    ax1.set_ylabel("Precio")
    ax1.legend(loc="upper left")

    ax2 = ax1.twinx()
    ax2.bar(df.index, df["Volume"], alpha=0.3, label="Volumen")
    ax2.set_ylabel("Volumen")

    fig.tight_layout()
    if save_path:
        plt.savefig(save_path)
    else:
        plt.show()
    plt.close(fig)
