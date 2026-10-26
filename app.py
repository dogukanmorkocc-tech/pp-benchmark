import os
import datetime as dt

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

st.set_page_config(page_title="Para Piyasası Fonu Benchmark Paneli", layout="wide")

EVDS_BASE = "https://evds3.tcmb.gov.tr/service/evds/"
# Seri kodlarını EVDS > Veri Kategorileri'nden doğrulayıp kenar çubuğundan değiştirebilirsin.
DEFAULT_TLREF = "TP.BISTTLREF.ORAN"
DEFAULT_DEPOSIT = "TP.TRY.MT02"  # TL mevduat ağırlıklı ort. faiz (3 aya kadar)


def get_key():
    try:
        return st.secrets["EVDS_API_KEY"]
    except Exception:
        return os.getenv("EVDS_API_KEY", "")


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def fetch_evds(series, start, end, key):
    url = (
        f"{EVDS_BASE}series={series}"
        f"&startDate={start:%d-%m-%Y}&endDate={end:%d-%m-%Y}&type=json"
    )
    r = requests.get(url, headers={"key": key}, timeout=30)
    r.raise_for_status()
    items = r.json().get("items", [])
    if not items:
        return pd.Series(dtype=float)
    df = pd.DataFrame(items)
    col = [c for c in df.columns if c not in ("Tarih", "UNIXTIME")][0]
    df["Tarih"] = pd.to_datetime(df["Tarih"], format="%d-%m-%Y")
    s = pd.to_numeric(df[col], errors="coerce")
    s.index = df["Tarih"]
    return s.dropna().sort_index()


@st.cache_data(ttl=3 * 3600, show_spinner=False)
def fetch_funds(codes, start, end):
    from tefas import Crawler

    crawler = Crawler()
    frames = []
    cur = start
    while cur <= end:  # TEFAS aralık sınırına karşı 90 günlük parçalar
        nxt = min(cur + dt.timedelta(days=89), end)
        for code in codes:
            d = crawler.fetch(
                start=cur.strftime("%Y-%m-%d"),
                end=nxt.strftime("%Y-%m-%d"),
                name=code,
                columns=["date", "code", "price"],
            )
            if d is not None and len(d):
                frames.append(d)
        cur = nxt + dt.timedelta(days=1)
    if not frames:
        return pd.DataFrame(columns=["date", "code", "price"])
    out = pd.concat(frames)
    out["date"] = pd.to_datetime(out["date"])
    return out.drop_duplicates(["date", "code"]).sort_values("date")


def accrual_index(rate, days):
    """Yıllık % faizden günlük tahakkuk endeksi (takvim günü, 365 gün bazı)."""
    r = rate.reindex(days).ffill().bfill()
    factor = 1 + r / 100 / 365
    idx = factor.cumprod()
    return 100 * idx / idx.iloc[0]


def metrics(idx):
    days = (idx.index[-1] - idx.index[0]).days
    total = idx.iloc[-1] / idx.iloc[0] - 1
    ann = (1 + total) ** (365 / days) - 1 if days > 0 else np.nan
    return total, ann


# ---------------- Arayüz ----------------
st.title("Para Piyasası Fonu Benchmark Paneli")
st.caption("Fon getirisi, TLREF ve TL mevduat faizi ile karşılaştırılır. Kaynak: TCMB EVDS, TEFAS.")

with st.sidebar:
    st.header("Ayarlar")
    codes = [
        c.strip().upper()
        for c in st.text_input("Fon kodları (virgülle)", "TLY, AFA").split(",")
        if c.strip()
    ]
    end = st.date_input("Bitiş", dt.date.today())
    start = st.date_input("Başlangıç", end - dt.timedelta(days=180))
    tlref_code = st.text_input("TLREF seri kodu", DEFAULT_TLREF)
    dep_code = st.text_input("Mevduat seri kodu", DEFAULT_DEPOSIT)
    csv = st.file_uploader("TEFAS veri yedeği (CSV: date, code, price)", type="csv")

key = get_key()
if not key:
    st.error("EVDS API anahtarı bulunamadı. Secrets bölümüne EVDS_API_KEY ekle.")
    st.stop()

try:
    tlref = fetch_evds(tlref_code, start, end, key)
    dep = fetch_evds(dep_code, start, end, key)
except Exception as e:
    st.error(f"EVDS verisi alınamadı: {e}")
    st.stop()

if csv is not None:
    funds = pd.read_csv(csv, parse_dates=["date"])
else:
    try:
        funds = fetch_funds(tuple(codes), start, end)
    except Exception as e:
        st.error(f"TEFAS verisi alınamadı: {e}. Kenar çubuğundan CSV yükleyebilirsin.")
        st.stop()

if funds.empty or tlref.empty:
    st.warning("Seçilen aralık için veri bulunamadı.")
    st.stop()

days = pd.date_range(start, end, freq="D")
bench = pd.DataFrame({"TLREF": accrual_index(tlref, days)})
if not dep.empty:
    bench["Mevduat"] = accrual_index(dep, days)

series = {}
vols = {}
for code, g in funds.groupby("code"):
    p = g.set_index("date")["price"].astype(float)
    p = p[~p.index.duplicated()].sort_index()
    vols[code] = p.pct_change().std() * np.sqrt(252)
    full = p.reindex(days).ffill().dropna()
    series[code] = 100 * full / full.iloc[0]

all_idx = pd.concat([pd.DataFrame(series), bench], axis=1).dropna(how="all")
all_idx = all_idx.ffill().dropna()
all_idx = 100 * all_idx / all_idx.iloc[0]

# Getiri tablosu
_, tlref_ann = metrics(all_idx["TLREF"])
rows = []
for c in all_idx.columns:
    tot, ann = metrics(all_idx[c])
    rows.append(
        {
            "Seri": c,
            "Dönem getirisi %": round(tot * 100, 2),
            "Yıllık bileşik %": round(ann * 100, 2),
            "TLREF'e göre fark (puan)": round((ann - tlref_ann) * 100, 2),
            "Yıllık volatilite %": round(vols[c] * 100, 2) if c in vols else None,
        }
    )
st.subheader("Özet")
st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

# Grafik 1: endeks
fig = go.Figure()
for c in all_idx.columns:
    dash = "dash" if c in bench.columns else "solid"
    fig.add_trace(go.Scatter(x=all_idx.index, y=all_idx[c], name=c, line=dict(dash=dash)))
fig.update_layout(
    title="Başlangıç = 100", template="plotly_white", height=420,
    font=dict(color="black"), legend=dict(orientation="h"),
)
st.plotly_chart(fig, use_container_width=True)

# Grafik 2: 30 günlük yıllıklandırılmış getiri
roll = (all_idx / all_idx.shift(30)) ** (365 / 30) - 1
fig2 = go.Figure()
for c in roll.columns:
    fig2.add_trace(go.Scatter(x=roll.index, y=roll[c] * 100, name=c))
fig2.update_layout(
    title="30 günlük hareketli getiri (yıllıklandırılmış, %)",
    template="plotly_white", height=380, font=dict(color="black"),
    legend=dict(orientation="h"),
)
st.plotly_chart(fig2, use_container_width=True)

# Grafik 3: TLREF'e göre fazla getiri
fund_cols = [c for c in all_idx.columns if c in series]
if fund_cols:
    fig3 = go.Figure()
    for c in fund_cols:
        fig3.add_trace(go.Scatter(x=roll.index, y=(roll[c] - roll["TLREF"]) * 100, name=c))
    fig3.add_hline(y=0, line_color="black")
    fig3.update_layout(
        title="TLREF'e göre fazla getiri (30 günlük, yıllık puan)",
        template="plotly_white", height=360, font=dict(color="black"),
        legend=dict(orientation="h"),
    )
    st.plotly_chart(fig3, use_container_width=True)

st.caption(
    "Yöntem: tüm seriler takvim günü bazında, 365 gün esasıyla tahakkuk ettirilir; "
    "yıllık getiri bileşiktir; volatilite iş günü getirilerinden √252 ile hesaplanır. "
    "Yatırım tavsiyesi değildir."
)
