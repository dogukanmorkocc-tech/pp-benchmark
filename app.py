import os, hashlib, datetime as dt
import numpy as np, pandas as pd, requests, streamlit as st
import plotly.graph_objects as go

st.set_page_config(page_title="Makro Risk Skoru", layout="wide")
BASE = "https://evds3.tcmb.gov.tr/igmevdsms-dis/"
INK, RED, AMB, GRN, BLU, GRY = "#111111", "#C8102E", "#D98E04", "#1B7F3B", "#0B3D91", "#6B7280"
# (ad, anahtar, yön: +1 yükseldikçe risk artar, -1 düştükçe risk artar, varsayılan ağırlık, açıklama)
COMP = [("Kur volatilitesi", "vol", 1, 20, "USD/TRY 30 günlük yıllıklandırılmış volatilite. Yükselirse kur riski artar."),
        ("Kur momentumu", "mom", 1, 15, "USD/TRY 1 aylık değişim. Hızlı yükseliş stres işaretidir."),
        ("Reel kur sapması", "reer", 1, 15, "Reel efektif kurun tarihsel ortalamadan sapması. Aşırı değerlenme, ileride düzeltme riski yaratır."),
        ("Reel faiz", "real", -1, 20, "TLREF − yıllık TÜFE. Düşük veya negatif reel faiz TL varlıkların cazibesini azaltır."),
        ("Enflasyon ivmesi", "infl", 1, 10, "TÜFE aylık değişiminin 3 aylık ortalaması."),
        ("Fonlama stresi", "fund", 1, 10, "TLREF − politika faizi. Pozitif ve genişleyen fark fonlama sıkışıklığıdır."),
        ("Rezerv gücü", "rez", -1, 10, "Rezervin 3 aylık değişimi. Düşüş savunma gücünü zayıflatır.")]
CODES = {"usd": "TP.DK.USD.A.YTL", "tlref": "TP.BISTTLREF.ORAN", "reer": "TP.RK.T1.Y", "cpi": "TP.FG.J0", "pol": "", "rez": ""}
LBL = {"usd": "USD/TRY alış", "tlref": "TLREF", "reer": "Reel efektif kur (TÜFE bazlı)", "cpi": "TÜFE endeksi", "pol": "Politika faizi (opsiyonel)", "rez": "Rezerv serisi (opsiyonel)"}
st.markdown(f"""<style>.block-container{{max-width:1300px;padding-top:1.2rem}}
.pg{{font-size:30px;font-weight:800;margin:0}} .pgs{{color:{GRY};font-size:13px;margin-bottom:12px}}
.sec{{border-bottom:3px solid {INK};padding-bottom:4px;font-weight:800;letter-spacing:1.5px;font-size:14px;margin-top:20px}} .sec i{{color:{RED};font-style:normal;margin-right:8px}}
.card{{border:1px solid {INK};padding:10px 14px;height:100%}} .card small{{font-size:10px;letter-spacing:1.5px;text-transform:uppercase;color:{GRY}}}
.card .v{{font:700 26px ui-monospace,monospace}} .card .s{{font:12px ui-monospace,monospace;color:{GRY}}}
.note{{border-left:4px solid {BLU};background:#F4F6FA;padding:12px 16px;font-size:15px}}</style>""", unsafe_allow_html=True)


def key():
    try: return st.secrets["EVDS_API_KEY"]
    except Exception: return os.getenv("EVDS_API_KEY", "")
K = key()


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def fetch(name, code, start, end, demo):
    if demo:
        rng = np.random.default_rng(int(hashlib.md5(name.encode()).hexdigest()[:6], 16)); n = (end - start).days + 1
        idx = pd.date_range(start, periods=n)
        v = {"usd": 18 * np.exp(np.cumsum(rng.normal(.0006, .008, n))), "tlref": 40 + np.cumsum(rng.normal(0, .1, n)), "reer": 100 + np.cumsum(rng.normal(.02, .5, n)),
             "cpi": 1500 * np.exp(np.cumsum(np.full(n, .016 / 30) + rng.normal(0, .0005, n))), "pol": 38 + np.cumsum(rng.normal(0, .05, n)),
             "rez": 100 + np.cumsum(rng.normal(.05, 1.2, n))}[name]
        return pd.Series(v, index=idx)
    if not code: return None
    r = requests.get(f"{BASE}series={code}&startDate={start:%d-%m-%Y}&endDate={end:%d-%m-%Y}&type=json", headers={"key": K}, timeout=40); r.raise_for_status()
    try: df = pd.DataFrame(r.json().get("items", []))
    except ValueError: raise RuntimeError(f"{code}: JSON dönmedi (HTTP {r.status_code}): {r.text[:100]}")
    if df.empty: return None
    col = [c for c in df.columns if c not in ("Tarih", "UNIXTIME")][0]
    d = pd.to_datetime(df["Tarih"], format="%d-%m-%Y", errors="coerce"); m = d.isna(); d[m] = pd.to_datetime(df["Tarih"][m] + "-1", errors="coerce")
    s = pd.to_numeric(df[col], errors="coerce"); s.index = d; return s.dropna().sort_index()


def zone(x): return ("DÜŞÜK", GRN) if x < 40 else ("ORTA", AMB) if x < 60 else ("YÜKSEK", "#E4572E") if x < 75 else ("KRİTİK", RED)
def card(l, v, s=""): return f'<div class="card"><small>{l}</small><div class="v">{v}</div><div class="s">{s}</div></div>'
def sec(n, t, info):
    a, b = st.columns([14, 1]); a.markdown(f'<div class="sec"><i>{n}</i>{t}</div>', unsafe_allow_html=True)
    with b.popover("ⓘ"): st.markdown(info)


with st.sidebar:
    st.markdown("### Ayarlar")
    demo = st.toggle("Demo veri", value=not K)
    end = st.date_input("Bitiş", dt.date.today()); yrs = st.slider("Geçmiş (yıl)", 3, 8, 5)
    with st.expander("EVDS seri kodları"):
        for k_ in CODES: CODES[k_] = st.text_input(LBL[k_], CODES[k_])
    with st.expander("Bileşen ağırlıkları"):
        W = {a[1]: st.slider(a[0], 0, 40, a[3]) for a in COMP}
if not K and not demo: st.error("EVDS_API_KEY yok. Secrets'a ekle veya Demo veriyi aç."); st.stop()
start = end - dt.timedelta(days=365 * yrs + 40)
try: raw = {n: fetch(n, c, start, end, demo) for n, c in CODES.items()}
except Exception as e: st.error(f"EVDS verisi alınamadı: {e}"); st.stop()
if raw["usd"] is None or raw["tlref"] is None: st.error("USD ve TLREF serileri zorunlu."); st.stop()
idx = raw["usd"].index; g = lambda n: raw[n].reindex(idx, method="ffill") if raw[n] is not None else None
usd, tl = raw["usd"], g("tlref"); X = {}
X["vol"] = usd.pct_change().rolling(30).std() * 252 ** .5 * 100; X["mom"] = usd.pct_change(21) * 100
if raw["reer"] is not None: X["reer"] = g("reer")
if raw["cpi"] is not None:
    cm = raw["cpi"].resample("MS").last(); yoy = (cm.pct_change(12) * 100).reindex(idx, method="ffill")
    X["infl"] = (cm.pct_change().rolling(3).mean() * 100).reindex(idx, method="ffill"); X["real"] = ((1 + tl / 100) / (1 + yoy / 100) - 1) * 100
if raw["pol"] is not None: X["fund"] = tl - g("pol")
if raw["rez"] is not None: X["rez"] = g("rez").pct_change(63) * 100
Z = pd.DataFrame({k: ((x - x.rolling(750, min_periods=250).mean()) / x.rolling(750, min_periods=250).std()).clip(-3, 3) for k, x in X.items()})
sign = {a[1]: a[2] for a in COMP}; names = {a[1]: a[0] for a in COMP}
w = pd.Series({k: W[k] for k in Z.columns}, dtype=float)
if w.sum() == 0: st.error("En az bir bileşenin ağırlığı > 0 olmalı."); st.stop()
Zs = Z.mul(pd.Series(sign)[Z.columns]); wm = Z.notna().mul(w); score = (50 + 16.67 * (Zs.mul(w).sum(axis=1, min_count=1) / wm.sum(axis=1))).dropna()
if score.empty: st.error("Skor için yeterli veri yok (en az 250 gün gerekir)."); st.stop()
now = score.iloc[-1]; d1w = now - score.iloc[-6] if len(score) > 5 else 0; d1m = now - score.iloc[-22] if len(score) > 21 else 0
last = Zs.iloc[-1]; contrib = (last * w / w[last.notna()].sum() * 16.67).dropna().sort_values(ascending=False)
lab, colr = zone(now)

st.markdown('<p class="pg">Makro Risk Skoru</p><p class="pgs">Birleşik erken uyarı endeksi ve günlük risk bülteni · kaynak: TCMB EVDS'
            + (' · <b style="color:#C8102E">DEMO VERİ, rakamlar gerçek değildir</b>' if demo else '') + f' · son veri {idx[-1]:%d.%m.%Y}</p>', unsafe_allow_html=True)
T1, T2, T3 = st.tabs(["Skor Paneli", "Günlük Risk Bülteni", "Metodoloji"])

with T1:
    a, b = st.columns([1, 2])
    f = go.Figure(go.Indicator(mode="gauge+number", value=now, number=dict(font=dict(color=colr)), gauge=dict(axis=dict(range=[0, 100]), bar=dict(color=INK, thickness=.25),
        steps=[dict(range=[0, 40], color="#CDE8D5"), dict(range=[40, 60], color="#F8E4B5"), dict(range=[60, 75], color="#F6C7B6"), dict(range=[75, 100], color="#F0A3AD")])))
    f.update_layout(height=260, margin=dict(l=20, r=20, t=30, b=0)); a.plotly_chart(f, use_container_width=True)
    with b:
        cs = st.columns(3)
        cs[0].markdown(card("Risk seviyesi", f'<span style="color:{colr}">{lab}</span>', f"skor {now:.0f} / 100"), unsafe_allow_html=True)
        cs[1].markdown(card("1 hafta değişim", f"{d1w:+.1f}", "puan"), unsafe_allow_html=True); cs[2].markdown(card("1 ay değişim", f"{d1m:+.1f}", "puan"), unsafe_allow_html=True)
        st.markdown(f'<div class="note"><b>En büyük risk katkıları:</b> {", ".join(f"{names[k]} ({v:+.1f})" for k, v in contrib.head(2).items())}. '
                    f'<b>En çok rahatlatan:</b> {names[contrib.index[-1]]} ({contrib.iloc[-1]:+.1f}).</div>', unsafe_allow_html=True)
    sec("01", "SKOR GEÇMİŞİ", "**Skor:** 50 = tarihsel ortalama risk. Bileşen z-skorlarının ağırlıklı ortalaması 0-100'e ölçeklenir. Bantlar: <40 düşük, 40-60 orta, 60-75 yüksek, 75+ kritik.")
    h = score.tail(750); f = go.Figure()
    for lo, hi, c_ in [(0, 40, "#CDE8D5"), (40, 60, "#F8E4B5"), (60, 75, "#F6C7B6"), (75, 100, "#F0A3AD")]: f.add_hrect(y0=lo, y1=hi, fillcolor=c_, opacity=.5, line_width=0)
    f.add_scatter(x=h.index, y=h, line=dict(color=INK, width=2.5), name="Skor"); f.update_layout(template="plotly_white", height=330, margin=dict(l=10, r=10, t=10, b=10), yaxis=dict(range=[0, 100]), font=dict(color=INK))
    st.plotly_chart(f, use_container_width=True)
    sec("02", "BİLEŞENLER", "**z-skoru:** göstergenin 3 yıllık ortalamasından kaç standart sapma uzak olduğu. Yön işareti uygulanır: pozitif katkı riski artırır. **Katkı** puan cinsindendir; toplamı skorun 50'den sapmasıdır.")
    rows = [{"Bileşen": names[k], "Güncel değer": X[k].iloc[-1], "Risk z-skoru": last[k], "Katkı (puan)": contrib.get(k), "Ağırlık %": w[k] / w[last.notna()].sum() * 100} for k in Z.columns if pd.notna(last[k])]
    a, b = st.columns([1.3, 1]); a.dataframe(pd.DataFrame(rows).round(2), hide_index=True, use_container_width=True)
    f = go.Figure(go.Bar(y=[names[k] for k in contrib.index][::-1], x=contrib.values[::-1], orientation="h", marker_color=[RED if v > 0 else GRN for v in contrib.values[::-1]]))
    f.update_layout(template="plotly_white", height=300, margin=dict(l=10, r=10, t=10, b=10), font=dict(color=INK)); b.plotly_chart(f, use_container_width=True)
    miss = [a[0] for a in COMP if a[1] not in Z.columns]
    if miss: st.caption("Veri olmadığı için skora dahil edilmeyen bileşenler: " + ", ".join(miss) + ". Kenar çubuğundan seri kodu girince devreye girer; ağırlıklar kalanlar üzerinden yeniden dağıtılır.")

with T2:
    sec("01", "OTOMATİK BÜLTEN", "**Günlük Risk Bülteni:** Skor, değişim, ana risk sürücüleri ve piyasa özeti tek metinde. İndirip e-postayla paylaşabilirsin.")
    ch = lambda s, n=1: (s.iloc[-1] / s.iloc[-1 - n] - 1) * 100
    drv = ", ".join(f"{names[k]} ({v:+.1f} puan)" for k, v in contrib.head(2).items()); rel = names[contrib.index[-1]]
    trend = "yükseldi" if d1w > 1 else "geriledi" if d1w < -1 else "yatay seyretti"
    txt = (f"GÜNLÜK RİSK BÜLTENİ · {idx[-1]:%d.%m.%Y}\n\nMakro risk skoru {now:.0f}/100 ({lab}). Son 1 haftada skor {trend} ({d1w:+.1f} puan), 1 aylık değişim {d1m:+.1f} puan.\n"
           f"Riski en çok artıran faktörler: {drv}. En olumlu katkı: {rel}.\n\nPİYASA ÖZETİ\n- USD/TRY {usd.iloc[-1]:.4f} (1G {ch(usd):+.2f}%, 1A {ch(usd, 21):+.2f}%)\n"
           f"- TLREF %{tl.iloc[-1]:.2f} (1G {(tl.iloc[-1]-tl.iloc[-2])*100:+.0f} bp)\n- Kur volatilitesi (30G, yıllık) %{X['vol'].iloc[-1]:.1f}\n"
           + (f"- Reel faiz %{X['real'].iloc[-1]:.1f}\n" if "real" in X else "") + "\nKaynak: TCMB EVDS. Yatırım tavsiyesi değildir." + ("\nNOT: DEMO VERİ." if demo else ""))
    st.markdown(f'<div class="note" style="white-space:pre-wrap;font-family:ui-monospace,monospace;font-size:13px">{txt}</div>', unsafe_allow_html=True)
    tb = "".join(f"<tr><td>{r['Bileşen']}</td><td align=right>{r['Risk z-skoru']:+.2f}</td><td align=right>{r['Katkı (puan)']:+.1f}</td></tr>" for r in rows)
    html = (f"<html><meta charset=utf-8><body style='font-family:Arial;max-width:720px;margin:24px auto;color:#111'><h2>Günlük Risk Bülteni · {idx[-1]:%d.%m.%Y}</h2>"
            f"<h1 style='color:{colr}'>{now:.0f} / 100 · {lab}</h1><pre style='font-family:Arial;white-space:pre-wrap'>{txt}</pre>"
            f"<table border=1 cellpadding=6 cellspacing=0 width=100%><tr><th>Bileşen</th><th>z-skoru</th><th>Katkı</th></tr>{tb}</table></body></html>")
    c1, c2 = st.columns(2)
    c1.download_button("Bülteni indir (HTML)", html, f"risk_bulteni_{idx[-1]:%Y%m%d}.html", "text/html"); c2.download_button("Metni indir (TXT)", txt, f"risk_bulteni_{idx[-1]:%Y%m%d}.txt")
    st.code(txt, language=None)

with T3:
    st.markdown("**Yöntem:** Her gösterge için son 3 yıllık ortalama ve standart sapmaya göre z-skoru hesaplanır (±3'te kırpılır), risk yönüne göre işaretlenir, ağırlıklı ortalaması alınıp `50 + 16,67 × z` ile 0-100'e dönüştürülür.")
    st.dataframe(pd.DataFrame([{"Bileşen": a[0], "Risk yönü": "yükselince risk ↑" if a[2] > 0 else "düşünce risk ↑", "Açıklama": a[4]} for a in COMP]), hide_index=True, use_container_width=True)
    st.markdown("**Sınırlar:** Skor bir erken uyarı göstergesidir, tahmin değildir. Seri kodlarını EVDS'den doğrulayın. Rezerv ve politika faizi kodları kenar çubuğundan girilir.")
