import os, hashlib, datetime as dt
from statistics import NormalDist
import numpy as np, pandas as pd, requests, streamlit as st
import plotly.graph_objects as go

st.set_page_config(page_title="Hazine ve Risk Konsolu", layout="wide")
BASE = "https://evds3.tcmb.gov.tr/igmevdsms-dis/"
CODES = {"USDA": "TP.DK.USD.A.YTL", "USDS": "TP.DK.USD.S.YTL", "EURA": "TP.DK.EUR.A.YTL", "EURS": "TP.DK.EUR.S.YTL", "TLREF": "TP.BISTTLREF.ORAN"}
INK, RED, AMB, GRN, BLU, GRY = "#111111", "#C8102E", "#D98E04", "#1B7F3B", "#0B3D91", "#6B7280"

st.markdown(f"""<style>
.block-container{{padding-top:1.2rem;max-width:1400px}}
.pg{{font-size:30px;font-weight:800;letter-spacing:.5px;margin:0}} .pgs{{color:{GRY};font-size:13px;margin-bottom:14px}}
.tile{{border:2px solid {INK};padding:14px 16px;position:relative;background:#fff}}
.tile .n{{font-size:12px;letter-spacing:2px;font-weight:700}} .tile .big{{font:700 38px ui-monospace,monospace;line-height:1.1;margin:4px 0}}
.tile .row{{display:flex;justify-content:space-between;font:13px ui-monospace,monospace}} .tile .chg{{font:700 15px ui-monospace,monospace}}
.tile svg{{width:100%;height:46px;margin-top:6px}}
.sec{{border-bottom:3px solid {INK};padding-bottom:4px;font-weight:800;letter-spacing:1.5px;font-size:14px;margin-top:22px}}
.sec i{{color:{RED};font-style:normal;margin-right:8px}} .sec small{{font-weight:400;color:{GRY};letter-spacing:0;margin-left:8px}}
.card{{border:1px solid {INK};padding:10px 14px;height:100%}} .card small{{font-size:10px;letter-spacing:1.5px;text-transform:uppercase;color:{GRY}}}
.card .v{{font:700 26px ui-monospace,monospace}} .card .s{{font:12px ui-monospace,monospace;color:{GRY}}}
.gau{{margin:8px 0}} .gau .t{{display:flex;justify-content:space-between;font:12px ui-monospace,monospace}}
.gau .bar{{height:12px;background:#ECECEC}} .gau .bar div{{height:100%}}
.note{{border-left:4px solid {BLU};background:#F4F6FA;padding:10px 14px;font-size:14px}}
.step{{border:1px solid {INK};padding:8px 12px;margin:6px 0;font-size:14px}} .step b{{color:{RED}}}
</style>""", unsafe_allow_html=True)

INFO = {
 "dealing": "**Dealing Board:** Dealerların kur ekranı. **Alış (Bid)** bankanın döviz aldığı, **Satış (Ask)** sattığı fiyattır; aradaki fark **spread**'dir. **Parite** EUR/USD çapraz kurudur. **TLREF** TL'nin gecelik referans faizidir. Oklar TL açısından okunur: ▲ kur artışı = TL değer kaybı.",
 "vol": "**Realized Vol (Gerçekleşen Volatilite):** Günlük getirilerin standart sapması × √252, yıllık %. Yükseldiğinde piyasa riski ve VaR artar.",
 "limit": "**Limit İzleme (Limit Monitoring):** Her risk ölçüsünün tanımlı limite oranı. %70 altı normal, %70-90 izle, %90+ uyarı, %100+ aşım. **VaR** (Value at Risk) belirli güvenle bir günde beklenen en kötü kayıp; **NOP** (Net Open Position) net açık döviz pozisyonudur.",
 "lcr": "**Likidite Merdiveni (Liquidity Ladder):** Vade kovalarında nakit giriş/çıkışı. **HQLA** (High Quality Liquid Assets) hızla nakde çevrilebilir varlıklar. **Likidite oranı** = HQLA / 1 aylık net nakit çıkışı; 1'in altı yetersizliktir.",
 "gap": "**Repricing Gap (Yeniden Fiyatlama Açığı):** Vade kovasında faizi yeniden belirlenecek varlık − yükümlülük. **NII / EaR** (Net Interest Income / Earnings at Risk) faiz şokunun 12 aylık net faiz gelirine etkisidir. Pozitif açık + faiz artışı = gelir artışı.",
 "var": "**VaR:** Belirli güvenle (örn. %99) bir günde aşılmaması beklenen kayıp. **Tarihsel:** geçmiş K/Z dağılımından; **Parametrik:** normal dağılım varsayımıyla; **EWMA:** yakın günlere daha çok ağırlık veren volatiliteyle. **ES** (Expected Shortfall) VaR aşıldığında ortalama kayıptır. 10 günlük VaR, 1 günlüğün √10 ile çarpılmasıdır.",
 "comp": "**Bileşen VaR (Component VaR):** Toplam riske her faktörün katkısı. Toplamı portföy VaR'ına eşittir. **Korelasyon:** faktörlerin birlikte hareketi; +1 aynı yön, −1 ters yön.",
 "bt": "**Backtesting:** VaR'ın doğruluğunu sınama. Günlük K/Z VaR'ı aşarsa **aşım (exception)** sayılır. **Basel trafik ışığı** (250 gün, %99): 0-4 aşım yeşil, 5-9 sarı, 10+ kırmızı.",
 "stress": "**Stress Testing:** Aşırı ama olası senaryolarda K/Z. **DV01 / PV01:** faizler 1 baz puan (0,01%) artınca değer kaybı. **Paralel şok:** tüm vadelerde aynı kayma.",
 "rafi": "**EVDS Veri Rafı:** TCMB'nin Elektronik Veri Dağıtım Sistemi'nde veriler Kategori → Veri Grubu (tablo) → Seri hiyerarşisindedir. Bir veri grubunu tablo olarak çekip serilerini risk faktörü olarak panele bağlayabilirsin."}

def key():
    try: return st.secrets["EVDS_API_KEY"]
    except Exception: return os.getenv("EVDS_API_KEY", "")
K = key()


def _get(path):
    r = requests.get(BASE + path, headers={"key": K}, timeout=40); r.raise_for_status()
    try: return r.json()
    except ValueError: raise RuntimeError(f"JSON dönmedi (HTTP {r.status_code}): {r.text[:100]}")


def _tidy(items):
    df = pd.DataFrame(items)
    if df.empty: return df
    d = pd.to_datetime(df["Tarih"], format="%d-%m-%Y", errors="coerce"); m = d.isna()
    d[m] = pd.to_datetime(df["Tarih"][m] + "-1", errors="coerce")
    df = df.drop(columns=[c for c in ("Tarih", "UNIXTIME") if c in df]).apply(pd.to_numeric, errors="coerce"); df.index = d
    return df.dropna(how="all").sort_index()


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def series(code, start, end, demo):
    if demo:
        base = code.replace(".S.", ".A.")
        rng = np.random.default_rng(int(hashlib.md5(base.encode()).hexdigest()[:6], 16)); n = (end - start).days + 1
        v = (40 + np.cumsum(rng.normal(0, .12, n))) if "TLREF" in code else (30 if "USD" in code else 35) * np.exp(np.cumsum(rng.normal(.0005, .007, n)))
        v = v * (1.004 if ".S." in code else 1)
        return pd.Series(v, index=pd.date_range(start, periods=n))
    return _tidy(_get(f"series={code}&startDate={start:%d-%m-%Y}&endDate={end:%d-%m-%Y}&type=json").get("items", [])).iloc[:, 0]


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def meta(path): return pd.DataFrame(_get(path))


@st.cache_data(ttl=3 * 3600, show_spinner=False)
def table(group, start, end):
    return _tidy(_get(f"datagroup={group}&startDate={start:%d-%m-%Y}&endDate={end:%d-%m-%Y}&type=json").get("items", []))


def sec(n, title, sub, ik):
    a, b = st.columns([14, 1]); a.markdown(f'<div class="sec"><i>{n}</i>{title}<small>{sub}</small></div>', unsafe_allow_html=True)
    with b.popover("ⓘ"): st.markdown(INFO[ik])


def card(l, v, s=""): return f'<div class="card"><small>{l}</small><div class="v">{v}</div><div class="s">{s}</div></div>'
def cards(items):
    for c, it in zip(st.columns(len(items)), items): c.markdown(card(*it), unsafe_allow_html=True)


def gauge(name, used, limit, unit, minimum=False):
    p = (limit / used if used else 0) if minimum else (used / limit if limit else 0)
    col = GRN if p < .7 else AMB if p < .9 else RED; lab = "AŞIM" if p >= 1 else "UYARI" if p >= .9 else "İZLE" if p >= .7 else "NORMAL"
    st.markdown(f'<div class="gau"><div class="t"><span>{name}</span><span>{used:,.2f} / {limit:,.2f} {unit} · %{p*100:.0f} · <b style="color:{col}">{lab}</b></span></div><div class="bar"><div style="width:{min(p,1)*100:.0f}%;background:{col}"></div></div></div>', unsafe_allow_html=True)


def fig(title, h=300):
    f = go.Figure(); f.update_layout(title=title, template="plotly_white", font=dict(color=INK), height=h, margin=dict(l=10, r=10, t=40, b=10), legend=dict(orientation="h"), bargap=.35); return f


def tile(name, big, sub, s, chg, fxcol=True):
    y = s.tail(60).values; lo, hi = y.min(), y.max(); pts = " ".join(f"{i*300/(len(y)-1):.1f},{44-(v-lo)/(hi-lo+1e-9)*40:.1f}" for i, v in enumerate(y))
    col = (RED if chg > 0 else GRN) if fxcol else INK
    return (f'<div class="tile" style="border-top:8px solid {col}"><div class="n">{name}</div><div class="big">{big}</div>'
            f'<div class="row"><span>{sub}</span><span class="chg" style="color:{col}">{"▲" if chg>0 else "▼"} {abs(chg):.2f}%</span></div>'
            f'<svg viewBox="0 0 300 46" preserveAspectRatio="none"><polyline fill="none" stroke="{col}" stroke-width="2" points="{pts}"/></svg></div>')


DEF = {"gap": pd.DataFrame({"Kova": ["≤1A", "1-3A", "3-6A", "6-12A", "1-3Y", ">3Y"], "Varlık": [800., 600, 400, 300, 500, 300], "Yükümlülük": [1200., 700, 350, 250, 200, 100], "Orta nokta (yıl)": [.04, .17, .375, .75, 2, 5]}),
       "liq": pd.DataFrame({"Kova": ["1G", "1H", "1A", "3A"], "Giriş": [900., 400, 500, 900], "Çıkış": [1100., 550, 650, 800]})}
S = lambda k: st.session_state.get(k, DEF[k])

with st.sidebar:
    st.markdown("### Konsol")
    page = st.radio("Ekran", ["Piyasa Ekranı · Dealing Board", "ALM · Likidite ve Faiz Gap", "Piyasa Riski · VaR ve Stres", "Veri Rafı · EVDS Tabloları"], label_visibility="collapsed")
    demo = st.toggle("Demo veri", value=not K)
    end = st.date_input("Bitiş", dt.date.today()); win = st.slider("Tarihsel pencere (gün)", 120, 750, 500, 10)
    with st.expander("Model portföy (mn TL)", expanded=False):
        pu = st.number_input("Net USD pozisyon", value=350.); pe = st.number_input("Net EUR pozisyon", value=-120.)
        DV = st.number_input("PV01 (mn TL / bp)", value=.42, step=.05); eq = st.number_input("Özkaynak", value=2000.)
        L = dict(var=st.number_input("VaR limiti", value=25.), nop=st.number_input("NOP/özkaynak limiti %", value=15.), dv01=st.number_input("PV01 limiti", value=.8),
                 nii=st.number_input("NII limiti", value=40.), lcr=st.number_input("Min likidite oranı (x)", value=1.0), hqla=st.number_input("HQLA", value=1500.))
if not K and not demo: st.error("EVDS_API_KEY yok. Secrets'a ekle veya Demo veriyi aç."); st.stop()
try:
    raw = pd.concat({n: series(c, end - dt.timedelta(days=int(win * 1.6) + 60), end, demo) for n, c in CODES.items()}, axis=1).ffill().dropna()
except Exception as e: st.error(f"EVDS verisi alınamadı: {e}"); st.stop()
rt = pd.DataFrame({"USD": raw["USDA"].pct_change(), "EUR": raw["EURA"].pct_change(), "Faiz(bp)": raw["TLREF"].diff() * 100}).dropna().tail(win)
pf = pd.DataFrame({"USD": pu * rt["USD"], "EUR": pe * rt["EUR"], "Faiz": -DV * rt["Faiz(bp)"]})
xf = st.session_state.get("xf")
if xf:
    x = xf["s"].reindex(raw.index, method="ffill"); xr = (x.diff() * 100 if xf["tur"] == "Faiz/Getiri (bp)" else x.pct_change()).reindex(rt.index)
    pf[xf["ad"]] = (-xf["pos"] * xr if xf["tur"] == "Faiz/Getiri (bp)" else xf["pos"] * xr)
pf = pf.fillna(0); pnl = pf.sum(axis=1); nd = NormalDist()
def var_set(c):
    z = nd.inv_cdf(c); q = pnl.quantile(1 - c); return -q, z * pnl.std(), z * (pnl.pow(2).ewm(alpha=.06).mean().iloc[-1]) ** .5, -pnl[pnl <= q].mean()
V99 = var_set(.99); nop = (abs(pu) + abs(pe)) / eq * 100
gp = S("gap").copy(); gp["Açık"] = gp["Varlık"] - gp["Yükümlülük"]; gp["n"] = gp["Açık"] * .01 * (1 - gp["Orta nokta (yıl)"]).clip(lower=0); nii = gp["n"].sum()
lq = S("liq"); net1a = (lq["Çıkış"] - lq["Giriş"]).iloc[:3].sum(); lcr = L["hqla"] / net1a if net1a > 0 else 99.
chg = lambda s, n=1: (s.iloc[-1] / s.iloc[-1 - n] - 1) * 100
st.caption(f"{'DEMO VERİ · rakamlar gerçek değildir' if demo else 'Kaynak: TCMB EVDS'} · son veri {raw.index[-1]:%d.%m.%Y}")

# ============ 1. DEALING BOARD ============
if page.startswith("Piyasa"):
    st.markdown('<p class="pg">Piyasa Ekranı</p><p class="pgs">Dealing Board · döviz ve para piyasası özeti</p>', unsafe_allow_html=True)
    par = raw["EURA"] / raw["USDA"]; c = st.columns(4)
    c[0].markdown(tile("USD / TRY", f"{raw.USDA.iloc[-1]:.4f}", f"Alış {raw.USDA.iloc[-1]:.4f} · Satış {raw.USDS.iloc[-1]:.4f}", raw.USDA, chg(raw.USDA)), unsafe_allow_html=True)
    c[1].markdown(tile("EUR / TRY", f"{raw.EURA.iloc[-1]:.4f}", f"Alış {raw.EURA.iloc[-1]:.4f} · Satış {raw.EURS.iloc[-1]:.4f}", raw.EURA, chg(raw.EURA)), unsafe_allow_html=True)
    c[2].markdown(tile("EUR / USD PARİTE", f"{par.iloc[-1]:.4f}", "çapraz kur", par, chg(par), False), unsafe_allow_html=True)
    c[3].markdown(tile("TLREF (GECELİK)", f"%{raw.TLREF.iloc[-1]:.2f}", f"1G değişim {(raw.TLREF.iloc[-1]-raw.TLREF.iloc[-2])*100:+.0f} bp", raw.TLREF, chg(raw.TLREF), False), unsafe_allow_html=True)
    sec("01", "KUR HAREKETİ", "performans ve volatilite", "dealing")
    t = pd.DataFrame({p: {"USD/TRY": chg(raw.USDA, n), "EUR/TRY": chg(raw.EURA, n)} for p, n in [("1G %", 1), ("1H %", 5), ("1A %", 21), ("3A %", 63)] if len(raw) > n}).round(2)
    a, b = st.columns([1, 2]); a.dataframe(t, use_container_width=True)
    f = fig("Başlangıç = 100"); [f.add_scatter(x=raw.index, y=100 * raw[k] / raw[k].iloc[0], name=n, line=dict(color=cl, width=2.5)) for k, n, cl in [("USDA", "USD/TRY", BLU), ("EURA", "EUR/TRY", RED)]]
    b.plotly_chart(f, use_container_width=True)
    sec("02", "REALIZED VOL", "30 günlük yıllıklandırılmış %", "vol")
    f = fig("Gerçekleşen volatilite %", 260); [f.add_scatter(x=rt.index, y=rt[k].rolling(30).std() * 252 ** .5 * 100, name=k) for k in ("USD", "EUR")]; st.plotly_chart(f, use_container_width=True)

# ============ 2. ALM ============
elif page.startswith("ALM"):
    st.markdown('<p class="pg">ALM · Likidite ve Faiz Gap</p><p class="pgs">Asset-Liability Management · fonlama, likidite ve faiz pozisyonu</p>', unsafe_allow_html=True)
    sec("01", "LİMİT İZLEME", "Limit Monitoring", "limit"); a, c = st.columns(2)
    with a: gauge("VaR 99% 1G", V99[0], L["var"], "mn TL"); gauge("NOP / özkaynak", nop, L["nop"], "%"); gauge("PV01", DV, L["dv01"], "mn TL/bp")
    with c: gauge("NII duyarlılığı (+100bp)", abs(nii), L["nii"], "mn TL"); gauge("Likidite oranı (min)", lcr, L["lcr"], "x", True)
    sec("02", "LİKİDİTE MERDİVENİ", "Liquidity Ladder", "lcr"); q = lq.copy(); q["Net"] = q["Giriş"] - q["Çıkış"]
    a, c = st.columns([2, 1]); f = fig("Nakit akışı (mn TL)")
    f.add_bar(x=q["Kova"], y=q["Giriş"], name="Giriş", marker_color=GRN); f.add_bar(x=q["Kova"], y=-q["Çıkış"], name="Çıkış", marker_color=RED)
    f.add_scatter(x=q["Kova"], y=q["Net"].cumsum(), name="Kümülatif net", line=dict(color=INK, width=3)); f.update_layout(barmode="relative"); a.plotly_chart(f, use_container_width=True)
    with c: cards([("Likidite oranı", f"{lcr:.2f}x", f"HQLA {L['hqla']:,.0f} / net çıkış {net1a:,.0f}")])
    sec("03", "REPRICING GAP VE NII", "Faiz pozisyonu", "gap"); a, c = st.columns([2, 1])
    f = fig("Net açık (mn TL)"); f.add_bar(x=gp["Kova"], y=gp["Açık"], marker_color=[GRN if v >= 0 else RED for v in gp["Açık"]]); a.plotly_chart(f, use_container_width=True)
    c.dataframe(pd.DataFrame({"Şok": ["-200bp", "-100bp", "+100bp", "+200bp"], "NII (mn TL)": [-2 * nii, -nii, nii, 2 * nii]}).round(1), hide_index=True, use_container_width=True)
    st.caption("Gap ve nakit merdiveni tabloları örnek değerlerdir. Veri Rafı ekranından düzenlenir.")

# ============ 3. PİYASA RİSKİ ============
elif page.startswith("Piyasa Riski"):
    st.markdown('<p class="pg">Piyasa Riski</p><p class="pgs">VaR, Expected Shortfall, backtest ve stres testi · faktörler EVDS verisinden</p>', unsafe_allow_html=True)
    sec("01", "VaR / ES", "yöntem karşılaştırması, mn TL", "var"); rows = []
    for cf in (.95, .99):
        h, p_, e, es = var_set(cf); rows += [{"Güven": f"%{cf*100:.0f}", "Yöntem": m, "1 gün": v, "10 gün": v * 10 ** .5} for m, v in [("Tarihsel", h), ("Parametrik", p_), ("EWMA", e), ("ES", es)]]
    a, c = st.columns([1.3, 1]); a.dataframe(pd.DataFrame(rows).round(2), hide_index=True, use_container_width=True)
    with c: cards([("VaR 99% 1G", f"{V99[0]:.1f}", f"limit {L['var']:.0f} · %{V99[0]/L['var']*100:.0f}"), ("ES 99% 1G", f"{V99[3]:.1f}", "")])
    sec("02", "BİLEŞEN VaR VE KORELASYON", "Risk katkısı", "comp"); z = nd.inv_cdf(.99); comp = {n: z * np.cov(pf[n], pnl)[0, 1] / pnl.std() for n in pf}
    a, c = st.columns(2); f = fig("Faktör katkısı (mn TL)"); f.add_bar(x=list(comp), y=list(comp.values()), marker_color=BLU); a.plotly_chart(f, use_container_width=True)
    cr = pf.corr().round(2).fillna(0); f = go.Figure(go.Heatmap(z=cr.values, x=cr.columns, y=cr.index, zmin=-1, zmax=1, colorscale="RdBu_r", text=cr.values, texttemplate="%{text}"))
    f.update_layout(title="Korelasyon", height=300, margin=dict(l=10, r=10, t=40, b=10), template="plotly_white"); c.plotly_chart(f, use_container_width=True)
    sec("03", "BACKTESTING", "Basel trafik ışığı", "bt"); qv = pnl.rolling(250, min_periods=120).quantile(.01).shift(1); ex = pnl[pnl < qv].tail(250); n = len(ex)
    zone, _ = ("YEŞİL", 0) if n <= 4 else ("SARI", 0) if n <= 9 else ("KIRMIZI", 0); a, c = st.columns([1, 3]); a.markdown(card("Aşım sayısı", str(n), f"bölge {zone}"), unsafe_allow_html=True)
    f = fig("Hipotetik K/Z ve VaR eşiği (mn TL)"); f.add_bar(x=pnl.index, y=pnl, marker_color="#9AA0A6", name="K/Z"); f.add_scatter(x=qv.index, y=qv, line=dict(color=RED), name="VaR 99%")
    f.add_scatter(x=ex.index, y=ex, mode="markers", marker=dict(color=INK, size=7), name="Aşım"); c.plotly_chart(f, use_container_width=True)
    sec("04", "STRES TESTİ", "Stress Testing", "stress")
    sc = [("Ilımlı kur şoku", 5, 5, 100), ("Sert kur şoku", 15, 15, 300), ("Faiz şoku", 0, 0, 500), ("Birleşik stres", 20, 20, 600), ("TL güçlenmesi", -8, -8, -300)]
    sd = pd.DataFrame([{"Senaryo": a_, "USD %": u, "EUR %": e, "Faiz bp": r, "K/Z (mn TL)": pu * u / 100 + pe * e / 100 - DV * r} for a_, u, e, r in sc]); sd["K/Z / özkaynak %"] = sd["K/Z (mn TL)"] / eq * 100
    a, c = st.columns([1.3, 1]); a.dataframe(sd.round(1), hide_index=True, use_container_width=True)
    f = fig("Senaryo K/Z (mn TL)"); f.add_bar(x=sd["Senaryo"], y=sd["K/Z (mn TL)"], marker_color=[RED if v < 0 else GRN for v in sd["K/Z (mn TL)"]]); c.plotly_chart(f, use_container_width=True)
    st.caption("K/Z, güncel model portföyün geçmiş EVDS hareketleriyle yeniden fiyatlanmasıdır. Faiz faktörü TLREF günlük değişimidir; Veri Rafı'ndan gösterge faiz serisi eklenebilir.")

# ============ 4. VERİ RAFI ============
else:
    st.markdown('<p class="pg">Veri Rafı</p><p class="pgs">EVDS tablolarını çek, risk faktörü olarak panele bağla</p>', unsafe_allow_html=True)
    sec("▪", "ÜÇ ADIMDA EVDS'DEN RİSK FAKTÖRÜ", "yol gösterici", "rafi")
    for t_ in ["<b>1.</b> Kategori ve veri grubunu seç (veya anahtar kelimeyle ara: repo, döviz, faiz, tahvil, altın, rezerv).", "<b>2.</b> Tabloyu çek, serileri incele (tarih ve değer sütunları).", "<b>3.</b> Bir seriyi faktör olarak ata (fiyat ise % getiri, faiz ise bp değişim). Piyasa Riski ekranı VaR ve stresi otomatik yeniler."]:
        st.markdown(f'<div class="step">{t_}</div>', unsafe_allow_html=True)
    if demo: st.info("Demo modunda EVDS kataloğu çekilemez. Gerçek anahtarla bu bölüm çalışır.")
    else:
        try:
            kw = st.text_input("Veri grubu ara (örn. repo, döviz, mevduat)")
            try: grp = meta("datagroups/mode=0&type=json")
            except Exception: grp = pd.concat([meta(f"datagroups/mode=2&code={i}&type=json") for i in meta("categories/type=json")["CATEGORY_ID"]])
            if kw: grp = grp[grp["DATAGROUP_NAME"].str.contains(kw, case=False, na=False)]
            pick = st.selectbox("Veri grubu", grp["DATAGROUP_CODE"] + " · " + grp["DATAGROUP_NAME"].fillna(""), index=None, placeholder="Seç")
            if pick:
                code = pick.split(" · ")[0]; tb = table(code, end - dt.timedelta(days=win), end)
                st.dataframe(tb.tail(30), use_container_width=True)
                a, b, c = st.columns(3); col = a.selectbox("Seri", tb.columns); tur = b.radio("Tür", ["Fiyat/Endeks (%)", "Faiz/Getiri (bp)"]); pos = c.number_input("Pozisyon (mn TL) / PV01", value=100.)
                if st.button("Risk faktörü olarak ekle"): st.session_state["xf"] = dict(s=tb[col].dropna(), ad="EVDS: " + col, tur=tur, pos=pos); st.success("Eklendi. Piyasa Riski ekranına geç.")
        except Exception as e: st.error(f"Katalog alınamadı: {e}")
    if xf: st.markdown(f'<div class="note">Aktif ek faktör: <b>{xf["ad"]}</b> ({xf["tur"]})</div>', unsafe_allow_html=True)
    sec("▪", "MODEL BİLANÇO (ÖRNEK)", "EVDS dışı, kurum verisi", "gap")
    for k_ in ("gap", "liq"): st.session_state[k_] = st.data_editor(S(k_), num_rows="dynamic", use_container_width=True, key=f"ed_{k_}_{len(S(k_))}")
