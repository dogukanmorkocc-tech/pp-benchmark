import os, hashlib, datetime as dt
from statistics import NormalDist
import numpy as np, pandas as pd, requests, streamlit as st
import plotly.graph_objects as go

st.set_page_config(page_title="Hazine ve Risk Konsolu", layout="wide")
BASE = "https://evds3.tcmb.gov.tr/igmevdsms-dis/"
CODES = {"USD": "TP.DK.USD.A.YTL", "EUR": "TP.DK.EUR.A.YTL", "TLREF": "TP.BISTTLREF.ORAN"}
INK, RED, AMB, GRN, BLU = "#111111", "#C8102E", "#D98E04", "#1B7F3B", "#0B3D91"

st.markdown(f"""<style>
.block-container{{padding-top:1rem;max-width:1400px}}
html,body,[class*="css"]{{color:{INK}}}
.band{{background:{INK};color:#fff;padding:14px 20px;display:flex;justify-content:space-between;align-items:baseline;border-left:10px solid {RED}}}
.band b{{font-size:22px;letter-spacing:3px}} .band span{{font:12px ui-monospace,monospace;opacity:.75}}
.tape{{display:flex;gap:0;border:1px solid {INK};border-top:0;margin-bottom:18px}}
.tape div{{flex:1;padding:8px 12px;border-right:1px solid {INK};font:13px ui-monospace,monospace}}
.tape div:last-child{{border-right:0}} .tape small{{display:block;font-size:10px;letter-spacing:1.5px;opacity:.6}}
.sec{{border-bottom:3px solid {INK};margin:26px 0 12px;font-weight:700;letter-spacing:2px;font-size:13px}}
.sec i{{color:{RED};font-style:normal;margin-right:8px}}
.card{{border:1px solid {INK};padding:10px 14px;height:100%}}
.card small{{font-size:10px;letter-spacing:1.5px;text-transform:uppercase;opacity:.65}}
.card .v{{font:600 26px ui-monospace,monospace;margin-top:2px}} .card .s{{font:12px ui-monospace,monospace;opacity:.7}}
.gau{{margin:7px 0}} .gau .t{{display:flex;justify-content:space-between;font:12px ui-monospace,monospace}}
.gau .bar{{height:12px;background:#ECECEC;position:relative}} .gau .bar div{{height:100%}}
.gau .bar:after{{content:"";position:absolute;left:70%;top:-2px;height:16px;border-left:1px dashed #888}}
.note{{border-left:4px solid {BLU};background:#F4F6FA;padding:10px 14px;font-size:14px}}
</style>""", unsafe_allow_html=True)


def key():
    try: return st.secrets["EVDS_API_KEY"]
    except Exception: return os.getenv("EVDS_API_KEY", "")


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def evds(code, start, end, k, demo):
    if demo:
        rng = np.random.default_rng(int(hashlib.md5(code.encode()).hexdigest()[:6], 16))
        n = (end - start).days + 1
        v = (40 + np.cumsum(rng.normal(0, .12, n))) if "TLREF" in code else 30 * np.exp(np.cumsum(rng.normal(.0005, .007, n)))
        return pd.Series(v, index=pd.date_range(start, periods=n))
    r = requests.get(f"{BASE}series={code}&startDate={start:%d-%m-%Y}&endDate={end:%d-%m-%Y}&type=json", headers={"key": k}, timeout=30)
    r.raise_for_status()
    try: items = r.json().get("items", [])
    except ValueError: raise RuntimeError(f"{code}: JSON dönmedi (HTTP {r.status_code}): {r.text[:100]}")
    df = pd.DataFrame(items)
    col = [c for c in df.columns if c not in ("Tarih", "UNIXTIME")][0]
    s = pd.to_numeric(df[col], errors="coerce"); s.index = pd.to_datetime(df["Tarih"], format="%d-%m-%Y")
    return s.dropna().sort_index()


def card(l, v, s=""): return f'<div class="card"><small>{l}</small><div class="v">{v}</div><div class="s">{s}</div></div>'
def sec(n, t): st.markdown(f'<div class="sec"><i>{n}</i>{t}</div>', unsafe_allow_html=True)
def cards(items):
    for c, it in zip(st.columns(len(items)), items): c.markdown(card(*it), unsafe_allow_html=True)


def gauge(name, used, limit, unit, minimum=False):
    p = (limit / used if used else 0) if minimum else (used / limit if limit else 0)
    col = GRN if p < .7 else AMB if p < .9 else RED
    lab = "AŞIM" if p >= 1 else "UYARI" if p >= .9 else "NORMAL" if p < .7 else "İZLE"
    st.markdown(f'<div class="gau"><div class="t"><span>{name}</span><span>{used:,.2f} / {limit:,.2f} {unit} · %{p*100:.0f} · <b style="color:{col}">{lab}</b></span></div>'
                f'<div class="bar"><div style="width:{min(p,1)*100:.0f}%;background:{col}"></div></div></div>', unsafe_allow_html=True)


def fig(title, h=300):
    f = go.Figure(); f.update_layout(title=title, template="plotly_white", font=dict(color=INK), height=h,
                                     margin=dict(l=10, r=10, t=40, b=10), legend=dict(orientation="h"), bargap=.35)
    return f


def bond(cpn, T, y):
    t = np.unique(np.append(np.arange(T, 0, -1.0), T)); cf = np.where(t == T, cpn + 100, cpn); pv = cf / (1 + y) ** t
    return pv.sum(), (pv * t).sum() / pv.sum() / (1 + y)


DEF = {
 "fx": pd.DataFrame({"Para birimi": ["USD", "EUR"], "Net pozisyon (mn TL eşd.)": [350.0, -120.0]}),
 "bd": pd.DataFrame({"Ad": ["DİBS 2Y", "DİBS 5Y", "DİBS 10Y", "FRN 3Y"], "Nominal (mn TL)": [500., 300., 200., 400.],
                     "Kupon %": [30., 28., 27., 38.], "Vade (yıl)": [2., 5., 10., 3.], "Getiri %": [38., 35., 33., 38.]}),
 "gap": pd.DataFrame({"Kova": ["≤1A", "1-3A", "3-6A", "6-12A", "1-3Y", ">3Y"], "Varlık": [800., 600, 400, 300, 500, 300],
                      "Yükümlülük": [1200., 700, 350, 250, 200, 100], "Orta nokta (yıl)": [.04, .17, .375, .75, 2, 5]}),
 "liq": pd.DataFrame({"Kova": ["1G", "1H", "1A", "3A"], "Giriş": [900., 400, 500, 900], "Çıkış": [1100., 550, 650, 800]}),
 "lim": {"var": 25., "eq": 2000., "nop": 15., "dv01": .8, "nii": 40., "lcr": 1.0, "hqla": 1500.}}
S = lambda k: st.session_state.get(k, DEF[k])

with st.sidebar:
    st.markdown("### KONSOL")
    page = st.radio("Ekran", ["A · Hazine Masası", "B · Piyasa Riski", "C · Pozisyon Girdileri"], label_visibility="collapsed")
    demo = st.toggle("Demo veri", value=not key())
    end = st.date_input("Bitiş", dt.date.today())
    win = st.slider("Tarihsel pencere (gün)", 120, 750, 500, 10)

k = key()
if not k and not demo: st.error("EVDS_API_KEY yok. Secrets'a ekle veya Demo veriyi aç."); st.stop()
try:
    raw = pd.concat({n: evds(c, end - dt.timedelta(days=int(win * 1.6) + 60), end, k, demo) for n, c in CODES.items()}, axis=1).ffill().dropna()
except Exception as e: st.error(f"EVDS verisi alınamadı: {e}"); st.stop()
rt = pd.DataFrame({"usd": raw["USD"].pct_change(), "eur": raw["EUR"].pct_change(), "bp": raw["TLREF"].diff() * 100}).dropna().tail(win)

fx, bd, gap, liq, L = S("fx"), S("bd"), S("gap"), S("liq"), S("lim")
pos = dict(zip(fx.iloc[:, 0], fx.iloc[:, 1])); pu, pe = pos.get("USD", 0.), pos.get("EUR", 0.)
b = bd.dropna().copy(); res = [bond(r["Kupon %"], r["Vade (yıl)"], r["Getiri %"] / 100) for _, r in b.iterrows()]
b["mv"] = [r["Nominal (mn TL)"] * p[0] / 100 for (_, r), p in zip(b.iterrows(), res)]; b["md"] = [p[1] for p in res]
b["dv01"] = b["md"] * b["mv"] * 1e-4; MV, DV = b["mv"].sum(), b["dv01"].sum()
pf = pd.DataFrame({"USD": pu * rt["usd"], "EUR": pe * rt["eur"], "Faiz": -DV * rt["bp"]}); pnl = pf.sum(axis=1)
nd = NormalDist()
def var_set(c):
    z = nd.inv_cdf(c); h = -pnl.quantile(1 - c); es = -pnl[pnl <= pnl.quantile(1 - c)].mean()
    return h, z * pnl.std(), z * (pnl.pow(2).ewm(alpha=.06).mean().iloc[-1]) ** .5, es
V99 = var_set(.99)
nop = (abs(pu) + abs(pe)) / L["eq"] * 100
g = gap.copy(); g["Açık"] = g["Varlık"] - g["Yükümlülük"]
g["nii100"] = g["Açık"] * .01 * (1 - g["Orta nokta (yıl)"]).clip(lower=0)
nii = g["nii100"].sum(); net1a = (liq["Çıkış"] - liq["Giriş"]).iloc[:3].sum(); lcr = L["hqla"] / net1a if net1a > 0 else 99.

st.markdown(f'<div class="band"><b>HAZİNE ▪ RİSK KONSOLU</b><span>{"DEMO VERİ — rakamlar gerçek değildir" if demo else "TCMB EVDS"} · veri tarihi {raw.index[-1]:%d.%m.%Y}</span></div>', unsafe_allow_html=True)
chg = lambda s: f"{(s.iloc[-1]/s.iloc[-2]-1)*100:+.2f}%"
st.markdown(f'<div class="tape"><div><small>USD/TRY</small>{raw.USD.iloc[-1]:.4f} {chg(raw.USD)}</div><div><small>EUR/TRY</small>{raw.EUR.iloc[-1]:.4f} {chg(raw.EUR)}</div>'
            f'<div><small>TLREF</small>%{raw.TLREF.iloc[-1]:.2f} ({(raw.TLREF.iloc[-1]-raw.TLREF.iloc[-2])*100:+.0f}bp)</div>'
            f'<div><small>VAR 99% 1G</small>{V99[0]:.1f} mn TL</div><div><small>DV01</small>{DV:.3f} mn TL/bp</div><div><small>LİKİDİTE ORANI</small>{lcr:.2f}x</div></div>', unsafe_allow_html=True)

# ================= A =================
if page.startswith("A"):
    br = [n for n, u, l, m in [("VaR", V99[0], L["var"], 0), ("Kur NOP", nop, L["nop"], 0), ("DV01", DV, L["dv01"], 0), ("NII", abs(nii), L["nii"], 0), ("LCR", lcr, L["lcr"], 1)] if (l / u if m else u / l) >= 1] if DV else []
    st.markdown(f'<div class="note"><b>Günün özeti:</b> USD/TRY {chg(raw.USD)}, TLREF %{raw.TLREF.iloc[-1]:.2f}. 1 günlük VaR(99%) {V99[0]:.1f} mn TL (limitin %{V99[0]/L["var"]*100:.0f}\'i). '
                f'{"Limit aşımı: " + ", ".join(br) + "." if br else "Aşılan limit yok."} Net açık kur pozisyonu özkaynağın %{nop:.1f}\'i, +100bp faiz şokunda NII etkisi {nii:+.1f} mn TL.</div>', unsafe_allow_html=True)
    sec("01", "LİMİT DURUMU")
    a, c = st.columns(2)
    with a: gauge("Piyasa riski VaR 99% 1G", V99[0], L["var"], "mn TL"); gauge("Net açık kur pozisyonu / özkaynak", nop, L["nop"], "%"); gauge("Faiz duyarlılığı DV01", DV, L["dv01"], "mn TL/bp")
    with c: gauge("NII duyarlılığı (+100bp)", abs(nii), L["nii"], "mn TL"); gauge("Likidite oranı (min)", lcr, L["lcr"], "x", True)
    sec("02", "LİKİDİTE MERDİVENİ")
    a, c = st.columns([2, 1])
    q = liq.copy(); q["Net"] = q["Giriş"] - q["Çıkış"]; q["Kümülatif"] = q["Net"].cumsum()
    f = fig("Nakit giriş/çıkış ve kümülatif net (mn TL)")
    f.add_bar(x=q["Kova"], y=q["Giriş"], name="Giriş", marker_color=GRN); f.add_bar(x=q["Kova"], y=-q["Çıkış"], name="Çıkış", marker_color=RED)
    f.add_scatter(x=q["Kova"], y=q["Kümülatif"], name="Kümülatif net", line=dict(color=INK, width=3)); f.update_layout(barmode="relative")
    a.plotly_chart(f, use_container_width=True)
    with c: cards([("HQLA", f"{L['hqla']:,.0f}", "mn TL")]); st.write(""); cards([("1A net çıkış", f"{net1a:,.0f}", f"oran {lcr:.2f}x")])
    sec("03", "FAİZ POZİSYONU · YENİDEN FİYATLAMA AÇIĞI")
    a, c = st.columns([2, 1])
    f = fig("Vade kovasına göre net açık (varlık − yükümlülük, mn TL)")
    f.add_bar(x=g["Kova"], y=g["Açık"], marker_color=[GRN if v >= 0 else RED for v in g["Açık"]]); a.plotly_chart(f, use_container_width=True)
    with c: st.dataframe(pd.DataFrame({"Şok": ["-200bp", "-100bp", "+100bp", "+200bp"], "NII etkisi (mn TL)": [-2 * nii, -nii, nii, 2 * nii]}).round(1), hide_index=True, use_container_width=True)
    sec("04", "KUR POZİSYONU")
    a, c = st.columns([1, 2])
    with a: cards([("Net açık pozisyon", f"{abs(pu)+abs(pe):,.0f}", f"özkaynağın %{nop:.1f}'i")])
    sh = [-20, -10, -5, 5, 10, 20]
    f = fig("TL değer kaybı/kazancı şoku: K/Z (mn TL)")
    f.add_bar(x=[f"{s:+d}%" for s in sh], y=[(pu + pe) * s / 100 for s in sh], marker_color=[RED if (pu + pe) * s < 0 else GRN for s in sh]); c.plotly_chart(f, use_container_width=True)

# ================= B =================
elif page.startswith("B"):
    sec("01", "RİSK ÖLÇÜLERİ · YÖNTEM KARŞILAŞTIRMASI (mn TL)")
    rows = []
    for cf in (.95, .99):
        h, p_, e, es = var_set(cf)
        rows += [{"Güven": f"%{cf*100:.0f}", "Yöntem": m, "1 gün": v, "10 gün (√t)": v * 10 ** .5} for m, v in [("Tarihsel", h), ("Parametrik", p_), ("EWMA (λ=0.94)", e), ("Beklenen Kayıp (ES)", es)]]
    a, c = st.columns([1.2, 1])
    a.dataframe(pd.DataFrame(rows).round(2), hide_index=True, use_container_width=True)
    with c: cards([("VaR 99% 1G (tarihsel)", f"{V99[0]:.1f}", f"limit {L['var']:.0f}"), ("ES 99% 1G", f"{V99[3]:.1f}", "")])
    sec("02", "RİSK KATKISI · BİLEŞEN VaR (99%, parametrik)")
    z = nd.inv_cdf(.99); comp = {n: z * np.cov(pf[n], pnl)[0, 1] / pnl.std() for n in pf}
    a, c = st.columns(2)
    f = fig("Faktör katkısı (mn TL)"); f.add_bar(x=list(comp), y=list(comp.values()), marker_color=BLU); a.plotly_chart(f, use_container_width=True)
    cr = rt.corr().round(2); cr.index = cr.columns = ["USD", "EUR", "Faiz(bp)"]
    f = go.Figure(go.Heatmap(z=cr.values, x=cr.columns, y=cr.index, zmin=-1, zmax=1, colorscale="RdBu_r", text=cr.values, texttemplate="%{text}"))
    f.update_layout(title="Faktör korelasyonu", height=300, margin=dict(l=10, r=10, t=40, b=10), template="plotly_white"); c.plotly_chart(f, use_container_width=True)
    sec("03", "BACKTEST · BASEL TRAFİK IŞIĞI (99%, 250 gün)")
    qv = pnl.rolling(250, min_periods=120).quantile(.01).shift(1); ex = pnl[pnl < qv].tail(250); n_ex = len(ex)
    zone, zc = ("YEŞİL", GRN) if n_ex <= 4 else ("SARI", AMB) if n_ex <= 9 else ("KIRMIZI", RED)
    a, c = st.columns([1, 3])
    with a: cards([("Aşım sayısı", str(n_ex), f"bölge: {zone}")])
    f = fig("Güncel pozisyonla hipotetik K/Z ve VaR eşiği (mn TL)")
    f.add_bar(x=pnl.index, y=pnl, marker_color="#9AA0A6", name="Günlük K/Z"); f.add_scatter(x=qv.index, y=qv, line=dict(color=RED, width=2), name="VaR 99%")
    f.add_scatter(x=ex.index, y=ex, mode="markers", marker=dict(color=INK, size=7), name="Aşım"); c.plotly_chart(f, use_container_width=True)
    sec("04", "STRES TESTLERİ")
    sc = [("Ilımlı kur şoku", 5, 5, 100), ("Sert kur şoku", 15, 15, 300), ("Faiz şoku", 0, 0, 500), ("Birleşik stres", 20, 20, 600), ("TL güçlenmesi", -8, -8, -300)]
    st_df = pd.DataFrame([{"Senaryo": n, "USD %": u, "EUR %": e, "Faiz bp": r, "K/Z (mn TL)": pu * u / 100 + pe * e / 100 - DV * r} for n, u, e, r in sc])
    st_df["K/Z / özkaynak %"] = st_df["K/Z (mn TL)"] / L["eq"] * 100
    a, c = st.columns([1.3, 1]); a.dataframe(st_df.round(1), hide_index=True, use_container_width=True)
    f = fig("Senaryo K/Z (mn TL)"); f.add_bar(x=st_df["Senaryo"], y=st_df["K/Z (mn TL)"], marker_color=[RED if v < 0 else GRN for v in st_df["K/Z (mn TL)"]]); c.plotly_chart(f, use_container_width=True)
    w1, w10 = pnl.min(), pnl.rolling(10).sum().min()
    cards([("Tarihsel en kötü 1G", f"{w1:.1f}", "mn TL"), ("Tarihsel en kötü 10G", f"{w10:.1f}", "mn TL"), ("Portföy duration", f"{(b.md*b.mv).sum()/MV:.2f}" if MV else "-", f"PV {MV:,.0f} mn TL")])
    st.caption("Not: Faiz faktörü TLREF günlük değişimiyle proxy edilir; kıymet bazlı getiri eğrisi verisi bağlandığında iyileştirilmelidir. K/Z, güncel pozisyonun geçmiş piyasa hareketleriyle yeniden fiyatlanmasıdır.")

# ================= C =================
else:
    st.markdown('<div class="note">Kurgusal örnek değerler yüklü. Kendi pozisyonlarınla değiştir (mn TL). Değişiklikler diğer ekranlara anında yansır.</div>', unsafe_allow_html=True)
    for k_, t_ in [("fx", "Net kur pozisyonu"), ("bd", "Menkul kıymet portföyü (yıllık kuponlu varsayım)"), ("gap", "Yeniden fiyatlama açığı"), ("liq", "Nakit merdiveni")]:
        sec("▪", t_.upper()); st.session_state[k_] = st.data_editor(S(k_), num_rows="dynamic", use_container_width=True, key=f"ed_{k_}_{len(S(k_))}")
    sec("▪", "LİMİTLER VE ÖZKAYNAK"); lm = dict(L)
    for c, (k_, t_) in zip(st.columns(4), [("var", "VaR limiti (mn TL)"), ("eq", "Özkaynak (mn TL)"), ("nop", "NOP/özkaynak limiti %"), ("dv01", "DV01 limiti")]): lm[k_] = c.number_input(t_, value=float(L[k_]))
    for c, (k_, t_) in zip(st.columns(3), [("nii", "NII limiti (mn TL)"), ("lcr", "Min likidite oranı (x)"), ("hqla", "HQLA (mn TL)")]): lm[k_] = c.number_input(t_, value=float(L[k_]))
    st.session_state["lim"] = lm
