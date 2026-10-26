import os, math, hashlib, datetime as dt
import numpy as np, pandas as pd, requests, streamlit as st
import plotly.graph_objects as go

st.set_page_config(page_title="Hazine Yönetim Paneli", layout="wide")
BASE = "https://evds3.tcmb.gov.tr/igmevdsms-dis/"
# Kodları EVDS > Veri Kategorileri'nden doğrulayın; kenar çubuğundan değiştirilebilir.
SER = {"USD/TRY": "TP.DK.USD.A.YTL", "EUR/TRY": "TP.DK.EUR.A.YTL",
       "TLREF": "TP.BISTTLREF.ORAN", "TL Mevduat": "TP.TRY.MT02",
       "Reel Kur (TÜFE bazlı)": "TP.RK.T1.Y", "TÜFE endeksi": "TP.FG.J0"}
W = dict(template="plotly_white", font=dict(color="black"), height=340,
         margin=dict(l=10, r=10, t=40, b=10), legend=dict(orientation="h"))


def key():
    try:
        return st.secrets["EVDS_API_KEY"]
    except Exception:
        return os.getenv("EVDS_API_KEY", "")


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def evds(code, start, end, k, demo):
    if demo:
        seed = int(hashlib.md5(code.encode()).hexdigest()[:6], 16)
        rng = np.random.default_rng(seed)
        n = (end - start).days + 1
        base = 30 + seed % 40
        if "TP.RK" in code: base = 100
        if "FG.J0" in code: base = 2500
        steps = rng.normal(0.0004 if base > 90 else 0, 0.01 if base > 90 else 0.15, n)
        v = base * np.exp(np.cumsum(steps)) if base > 90 else base + np.cumsum(steps)
        return pd.Series(v, index=pd.date_range(start, periods=n))
    r = requests.get(f"{BASE}series={code}&startDate={start:%d-%m-%Y}&endDate={end:%d-%m-%Y}&type=json",
                     headers={"key": k}, timeout=30)
    r.raise_for_status()
    try:
        items = r.json().get("items", [])
    except ValueError:
        raise RuntimeError(f"{code}: JSON dönmedi (HTTP {r.status_code}): {r.text[:120]}")
    if not items:
        return pd.Series(dtype=float)
    df = pd.DataFrame(items)
    col = [c for c in df.columns if c not in ("Tarih", "UNIXTIME")][0]
    d = pd.to_datetime(df["Tarih"], format="%d-%m-%Y", errors="coerce")
    m = d.isna()
    d[m] = pd.to_datetime(df["Tarih"][m] + "-1", errors="coerce")
    s = pd.to_numeric(df[col], errors="coerce"); s.index = d
    return s.dropna().sort_index()


@st.cache_data(ttl=3 * 3600, show_spinner=False)
def tefas(codes, start, end):
    from tefas import Crawler
    c, out, cur = Crawler(), [], start
    while cur <= end:
        nxt = min(cur + dt.timedelta(days=89), end)
        for code in codes:
            d = c.fetch(start=str(cur), end=str(nxt), name=code, columns=["date", "code", "price"])
            if d is not None and len(d): out.append(d)
        cur = nxt + dt.timedelta(days=1)
    f = pd.concat(out) if out else pd.DataFrame(columns=["date", "code", "price"])
    f["date"] = pd.to_datetime(f["date"])
    return f.drop_duplicates(["date", "code"]).sort_values("date")


def kpi(col, name, s, unit="", pct=True):
    if s is None or s.empty:
        col.metric(name, "—"); return
    last, prev = s.iloc[-1], s.iloc[-2] if len(s) > 1 else s.iloc[-1]
    d = (last / prev - 1) * 100 if pct else last - prev
    col.metric(name, f"{last:,.2f}{unit}", f"{d:+.2f}{'%' if pct else ' puan'}")


def line(df, title, **kw):
    f = go.Figure([go.Scatter(x=df.index, y=df[c], name=c) for c in df.columns])
    f.update_layout(title=title, **{**W, **kw}); st.plotly_chart(f, use_container_width=True)


def price(face, cpn, T, y):
    t = np.arange(T, 0, -1.0)[::-1]
    t = t if len(t) else np.array([T])
    t = np.sort(np.unique(np.append(t, T)))
    cf = np.where(t == T, cpn + 100, cpn)
    pv = cf / (1 + y) ** t
    return pv.sum(), (pv * t).sum() / pv.sum() / (1 + y)


# ---------- Kenar çubuğu ----------
with st.sidebar:
    st.header("Ayarlar")
    demo = st.toggle("Demo veri (anahtarsız önizleme)", value=not key())
    end = st.date_input("Bitiş", dt.date.today())
    start = st.date_input("Başlangıç", end - dt.timedelta(days=365 * 2))
    with st.expander("EVDS seri kodları"):
        for n in SER: SER[n] = st.text_input(n, SER[n])
        c2 = st.text_input("Gösterge tahvil 2Y kodu (opsiyonel)")
        c10 = st.text_input("Gösterge tahvil 10Y kodu (opsiyonel)")
        cpol = st.text_input("Politika faizi kodu (opsiyonel)")
k = key()
if not k and not demo:
    st.error("EVDS_API_KEY bulunamadı. Secrets'a ekle veya Demo veriyi aç."); st.stop()
st.title("Hazine Yönetim Paneli")
st.caption("Piyasa monitörü, reel faiz/kur, faiz riski ve para piyasası fonu benchmark. Kaynak: TCMB EVDS, TEFAS."
           + ("  **DEMO VERİ: rakamlar gerçek değildir.**" if demo else ""))


def get(code):
    if not code: return None
    try: return evds(code, start, end, k, demo)
    except Exception as e:
        st.warning(f"{code}: {e}"); return None


T1, T2, T3, T4 = st.tabs(["Piyasa Monitörü", "Reel Faiz ve Reel Kur", "Faiz Riski Aracı", "PPF Benchmark"])

# ---------- 1. Piyasa Monitörü ----------
with T1:
    d = {n: get(SER[n]) for n in ["USD/TRY", "EUR/TRY", "TLREF", "TL Mevduat"]}
    pol, y2, y10 = get(cpol), get(c2), get(c10)
    cols = st.columns(5)
    kpi(cols[0], "USD/TRY", d["USD/TRY"]); kpi(cols[1], "EUR/TRY", d["EUR/TRY"])
    kpi(cols[2], "TLREF %", d["TLREF"], pct=False); kpi(cols[3], "Mevduat %", d["TL Mevduat"], pct=False)
    kpi(cols[4], "Politika faizi %", pol, pct=False)
    fx = pd.DataFrame({n: d[n] for n in ["USD/TRY", "EUR/TRY"] if d[n] is not None}).dropna(how="all")
    if not fx.empty:
        line(100 * fx / fx.bfill().iloc[0], "Kur sepeti (başlangıç = 100)")
    rt = pd.DataFrame({n: d[n] for n in ["TLREF", "TL Mevduat"] if d[n] is not None})
    if pol is not None: rt["Politika faizi"] = pol
    if not rt.empty:
        line(rt.ffill(), "Faiz seviyeleri (%)")
        if "TLREF" in rt and d["TL Mevduat"] is not None:
            sp = (rt["TL Mevduat"] - rt["TLREF"]).dropna().to_frame("Mevduat - TLREF (puan)")
            line(sp, "Mevduat–TLREF farkı")
    if y2 is not None and y10 is not None:
        cv = pd.concat([y2, y10], axis=1, keys=["2Y", "10Y"]).ffill().dropna()
        line((cv["10Y"] - cv["2Y"]).to_frame("10Y-2Y eğim (puan)"), "Verim eğrisi eğimi")

# ---------- 2. Reel Faiz ve Reel Kur ----------
with T2:
    reer, cpi, tl = get(SER["Reel Kur (TÜFE bazlı)"]), get(SER["TÜFE endeksi"]), get(SER["TLREF"])
    if reer is not None and len(reer) > 12:
        m, sd = reer.mean(), reer.std()
        f = go.Figure([go.Scatter(x=reer.index, y=reer, name="Reel kur")])
        for v, n in [(m, "Ortalama"), (m + sd, "+1σ"), (m - sd, "-1σ")]:
            f.add_hline(y=v, line_dash="dash", annotation_text=n)
        f.update_layout(title="Reel efektif döviz kuru (yüksek = TL reel değerli)", **W)
        st.plotly_chart(f, use_container_width=True)
        z = (reer.iloc[-1] - m) / sd
        st.metric("Ortalamadan sapma", f"{(reer.iloc[-1] / m - 1) * 100:+.1f}%", f"{z:+.2f}σ")
    if cpi is not None and tl is not None and len(cpi) > 13:
        yoy = cpi.resample("MS").last().pct_change(12).dropna()
        tm = tl.resample("MS").mean().reindex(yoy.index).ffill()
        real = ((1 + tm / 100) / (1 + yoy) - 1) * 100
        line(pd.DataFrame({"Yıllık TÜFE %": yoy * 100, "TLREF %": tm, "Reel faiz %": real}).dropna(),
             "Reel faiz = (1+TLREF)/(1+TÜFE) - 1 (geriye dönük)")

# ---------- 3. Faiz Riski Aracı ----------
with T3:
    st.write("Portföyü düzenle (satır ekleyebilirsin). Yıllık kuponlu varsayım, getiriler yıllık bileşik.")
    df = st.data_editor(pd.DataFrame({
        "Ad": ["DİBS 2Y", "DİBS 5Y", "DİBS 10Y", "TLREF FRN 3Y"],
        "Nominal (mn TL)": [500.0, 300.0, 200.0, 400.0],
        "Kupon %": [30.0, 28.0, 27.0, 0.0], "Vade (yıl)": [2.0, 5.0, 10.0, 3.0],
        "Getiri %": [38.0, 35.0, 33.0, 38.0]}), num_rows="dynamic", use_container_width=True)
    a, b = st.columns(2)
    short_bp = a.slider("Kısa uç şoku (bp)", -500, 500, 100, 25)
    long_bp = b.slider("Uzun uç şoku (bp)", -500, 500, 100, 25)
    rows = []
    for _, r in df.dropna().iterrows():
        y, T = r["Getiri %"] / 100, r["Vade (yıl)"]
        p0, md = price(100, r["Kupon %"], T, y)
        mv = r["Nominal (mn TL)"] * p0 / 100
        sh = (short_bp + (long_bp - short_bp) * min(T, 10) / 10) / 1e4
        p1, _ = price(100, r["Kupon %"], T, y + sh)
        rows.append({"Ad": r["Ad"], "Piyasa değeri": mv, "Mod. duration": md,
                     "DV01 (bin TL)": md * mv * 1e-4 * 1000, "Senaryo K/Z (mn TL)": r["Nominal (mn TL)"] * (p1 - p0) / 100})
    if rows:
        R = pd.DataFrame(rows)
        tot = R["Piyasa değeri"].sum()
        c = st.columns(4)
        c[0].metric("Toplam piyasa değeri (mn TL)", f"{tot:,.0f}")
        c[1].metric("Portföy duration", f"{(R['Mod. duration'] * R['Piyasa değeri']).sum() / tot:.2f}")
        c[2].metric("Toplam DV01 (bin TL)", f"{R['DV01 (bin TL)'].sum():,.0f}")
        c[3].metric("Senaryo K/Z (mn TL)", f"{R['Senaryo K/Z (mn TL)'].sum():,.1f}")
        st.dataframe(R.round(2), use_container_width=True, hide_index=True)
        grid = list(range(-300, 301, 100))
        pnl = []
        for s in grid:
            t_ = 0
            for _, r in df.dropna().iterrows():
                y, T = r["Getiri %"] / 100, r["Vade (yıl)"]
                p0, _ = price(100, r["Kupon %"], T, y); p1, _ = price(100, r["Kupon %"], T, y + s / 1e4)
                t_ += r["Nominal (mn TL)"] * (p1 - p0) / 100
            pnl.append(t_)
        f = go.Figure(go.Bar(x=[f"{g:+d}bp" for g in grid], y=pnl, marker_color=["#b71c1c" if v < 0 else "#2e7d32" for v in pnl]))
        f.update_layout(title="Paralel şok senaryoları, K/Z (mn TL)", **W)
        st.plotly_chart(f, use_container_width=True)

# ---------- 4. PPF Benchmark ----------
with T4:
    codes = [x.strip().upper() for x in st.text_input("Fon kodları (virgülle, örn. kendi PPF kodların)", "").split(",") if x.strip()]
    csv = st.file_uploader("TEFAS yedek CSV (date, code, price)", type="csv")
    tl, dep = get(SER["TLREF"]), get(SER["TL Mevduat"])
    if tl is None or not (codes or csv):
        st.info("Fon kodu gir veya CSV yükle.")
    else:
        try:
            fu = pd.read_csv(csv, parse_dates=["date"]) if csv else tefas(tuple(codes), start, end)
        except Exception as e:
            st.error(f"TEFAS verisi alınamadı: {e}"); st.stop()
        days = pd.date_range(start, end)
        def acc(r):
            x = (1 + r.reindex(days).ffill().bfill() / 100 / 365).cumprod(); return 100 * x / x.iloc[0]
        S = {"TLREF": acc(tl)}
        if dep is not None: S["Mevduat"] = acc(dep)
        for c_, g in fu.groupby("code"):
            p = g.set_index("date")["price"].astype(float).reindex(days).ffill().dropna(); S[c_] = 100 * p / p.iloc[0]
        A = pd.DataFrame(S).ffill().dropna(); A = 100 * A / A.iloc[0]
        n = (A.index[-1] - A.index[0]).days
        ann = (A.iloc[-1] / 100) ** (365 / n) - 1
        st.dataframe(pd.DataFrame({"Dönem %": (A.iloc[-1] - 100).round(2), "Yıllık bileşik %": (ann * 100).round(2),
                                   "TLREF'e fark (puan)": ((ann - ann["TLREF"]) * 100).round(2)}), use_container_width=True)
        line(A, "Başlangıç = 100")
