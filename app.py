import json
from flask import redirect
import secrets, uuid
import random
import os, re, glob, time, operator, fitz, requests
from flask import Flask, render_template, request, session

app = Flask(__name__)
SOHBET_DEPO = {}
app.secret_key = secrets.token_hex(16)

gemini_dosya = os.path.expanduser("~/.maya_anahtar")
openrouter_dosya = os.path.expanduser("~/.openrouter_anahtar")

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip() or (open(gemini_dosya).read().strip() if os.path.exists(gemini_dosya) else "")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "").strip() or (open(openrouter_dosya).read().strip() if os.path.exists(openrouter_dosya) else "")

GEMINI_MODELLER = ["gemini-2.5-flash-lite", "gemini-2.5-flash"]
ONCELIKLI_SAYFALAR = []
DIGER_SAYFALAR = []

import gzip as _gzip
_indeks_gz = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kutuphane_indeks.json.gz")
if os.path.exists(_indeks_gz):
    try:
        with _gzip.open(_indeks_gz, "rt", encoding="utf-8") as _f:
            _veri = json.load(_f)
        if isinstance(_veri, dict):
            ONCELIKLI_SAYFALAR = _veri.get("oncelikli", []) or _veri.get("ONCELIKLI_SAYFALAR", [])
            DIGER_SAYFALAR = _veri.get("diger", []) or _veri.get("DIGER_SAYFALAR", [])
        elif isinstance(_veri, list):
            DIGER_SAYFALAR = _veri
    except Exception as _e:
        print("Indeks yukleme hatasi:", _e)


FIRINCILIK_SOZLUGU = {
    "pastaci kremasi": "pastry cream creme patissiere custard starch egg yolk",
    "krema": "pastry cream custard ganache buttercream emulsion",
    "kesilir": "curdling coagulation syneresis emulsion separation",
    "ganaj": "ganache chocolate emulsion cocoa butter",
    "temperleme": "chocolate tempering polymorphism cocoa butter beta crystal",
    "mereng": "meringue egg white foam aeration sugar",
    "pandispanya": "sponge cake genoise biscuit aeration baking",
    "kruvasan": "croissant laminated dough butter viennoiserie fermentation",
    "katlama": "lamination folding layers butter plasticity",
    "otoliz": "autolyse flour water hydration gluten enzymatic",
    "eksi maya": "sourdough starter wild yeast lactic acid bacteria fermentation",
    "mayalama": "fermentation proofing yeast dough rheology",
    "soguk": "cold retardation fermentation temperature",
    "gluten": "gluten gliadin glutenin dough network elasticity",
    "hidrasyon": "hydration water absorption flour dough",
    "tuz": "salt sodium chloride gluten strengthening fermentation",
    "ekmek": "bread wheat flour baking crumb crust",
    "hamur": "dough wheat flour rheology fermentation",

    "nem": "humidity moisture steam", "buhar": "steam humidity crust",
    "ferment": "fermentation bulk proof", "mayalan": "fermentation yeast proofing",
    "maya": "sourdough starter levain", "ekşi": "sourdough lactic acetic",
    "otoliz": "autolyse autolysis", "glüten": "gluten network rheology",
    "gluten": "gluten network rheology", "un": "flour wheat protein",
    "su": "water hydration", "hidrasyon": "hydration water",
    "tuz": "salt sodium", "çavdar": "rye pentosan",
    "buğday": "wheat bran wholemeal", "siyez": "einkorn ancient grain",
    "sıcaklık": "temperature thermal", "pişir": "baking oven maillard",
    "fırın": "oven baking", "kabuk": "crust maillard",
    "gözenek": "crumb alveoli", "katla": "fold lamination",
    "yoğur": "knead mixing", "soğuk": "cold retard",
    "asit": "acid lactic acetic", "enzim": "enzyme amylase protease",
    "nişasta": "starch retrogradation", "kruvasan": "croissant lamination",
    "paneton": "panettone lievito madre pasta madre", "panetton": "panettone lievito madre pasta madre", "madre": "lievito madre pasta madre", "brioche": "brioche enriched butter", "colomba": "colomba panettone", "pandoro": "pandoro panettone", "choux": "choux pate choux", "ekmek": "bread loaf dough", "hamur": "dough"
}

def kitaplari_indeksle():
    global ONCELIKLI_SAYFALAR, DIGER_SAYFALAR
    ONCELIKLI_SAYFALAR, DIGER_SAYFALAR = [], []
    for klasor, hedef in [("~/kitaplar/oncelikli/*.pdf", ONCELIKLI_SAYFALAR), ("~/kitaplar/*.pdf", DIGER_SAYFALAR)]:
        for dosya in glob.glob(os.path.expanduser(klasor)):
            try:
                doc = fitz.open(dosya)
                for i, sayfa in enumerate(doc):
                    metin = (sayfa.get_text("text") or "").encode("utf-8", errors="ignore").decode("utf-8")
                    if len(metin.strip()) > 50:
                        hedef.append({"kitap": os.path.basename(dosya), "sayfa": i + 1, "metin": metin})
            except Exception:
                continue
    print(f"⭐ Öncelikli: {len(ONCELIKLI_SAYFALAR)} sayfa | 📚 Diğer: {len(DIGER_SAYFALAR)} sayfa indekslendi!")

def ingilizce_terimlere_cevir(soru, gecmis):
    birlesik = soru.lower()
    if any(k in birlesik for k in ["bu konu", "makale", "çalışma", "akademik", "araştırma", "literatür", "scholar"]):
        for m in gecmis[-4:]:
            birlesik += " " + m["text"].lower()
    bulunan = []
    for tr_kok, en_karsilik in FIRINCILIK_SOZLUGU.items():
        if tr_kok in birlesik:
            bulunan.extend(en_karsilik.split())
    ing = [k for k in re.findall(r'[a-z]{4,}', birlesik) if k not in {"nedir", "nasil", "neden", "icin", "gibi", "olan", "kadar", "onemi", "neler", "yapilan", "son", "yillarda", "akademik", "calismalar", "hakkinda", "konu", "google", "scholar"}]
    bulunan.extend(ing)
    return list(dict.fromkeys(bulunan))

def yerel_kitap_ara(havuz, kelimeler, limit=2):
    if not havuz or not kelimeler: return []
    skorlu = []
    for s in havuz:
        k_adi_kucuk = s["kitap"].lower()
        dosya_bonusu = sum(3 for k in kelimeler if k in k_adi_kucuk)
        puan = dosya_bonusu + sum(s["metin"].lower().count(k) for k in kelimeler)
        if puan > 0:
            skorlu.append((puan, s))
    skorlu.sort(key=operator.itemgetter(0), reverse=True)
    secilenler, sayac = [], {}
    for puan, sayfa_obj in skorlu:
        k_adi = sayfa_obj["kitap"]
        if sayac.get(k_adi, 0) < 1:
            secilenler.append(sayfa_obj)
            sayac[k_adi] = 1
        if len(secilenler) >= limit: break
    return secilenler

def openalex_ve_crossref_ara(kelimeler):
    sorgu_en = " ".join(kelimeler[:3])
    kaynaklar, ozetler = [], ""
    s = chr(47)
    try:
        oa_url = f"https:{s}{s}api.openalex.org{s}works?search={requests.utils.quote(sorgu_en)}&filter=has_doi:true,publication_year:2018-2026&sort=cited_by_count:desc&per-page=5"
        res = requests.get(oa_url, headers={"User-Agent": "mailto:info@modusoperandiai.com"}, timeout=35)
        if res.status_code == 200:
            for item in res.json().get("results", []):
                baslik = item.get("title") or "Akademik Yayın"
                yil = item.get("publication_year", "")
                atif = item.get("cited_by_count", 0)
                doi = item.get("doi") or "#"
                yazarlar = item.get("authorships", [])
                yazar = next(iter(yazarlar)).get("author", {}).get("display_name", "Araştırma Ekibi") if yazarlar else "Araştırma Ekibi"
                dergi = (item.get("primary_location") or {}).get("source", {})
                dergi_adi = dergi.get("display_name", "Hakemli Bilim Dergisi") if dergi else "Hakemli Bilim Dergisi"
                ozetler += f"- [{yil}] {baslik} | Yazar: {yazar} vd. | Dergi: {dergi_adi} | Atıf: {atif}\n"
                kaynaklar.append({"baslik": f"M|({yil}) {baslik} — {dergi_adi} ({atif} atıf)", "link": doi})
    except Exception:
        pass
    return ozetler, kaynaklar

def gemini_bulut_sor(gecmis, sistem, son_icerik):
    if not GEMINI_API_KEY: return None
    s = chr(47)
    base_url = "https://googleapis.com"
    headers = {"Content-Type": "application/json", "x-goog-api-key": GEMINI_API_KEY}
    mesajlar = [{"role": m["role"], "parts": [{"text": m["text"]}]} for m in gecmis[-6:]]
    mesajlar.append({"role": "user", "parts": [{"text": son_icerik}]})
    for m in GEMINI_MODELLER:
        try:
            res = requests.post(base_url + m + ":generateContent", headers=headers, json={"contents": mesajlar, "systemInstruction": {"parts": [{"text": sistem}]}, "generationConfig": {"temperature": 0.2}}, timeout=35)
            if res.status_code == 200:
                return next(iter(next(iter(res.json().get("candidates", []))).get("content", {}).get("parts", []))).get("text")
        except Exception: continue
    return None

def openrouter_bulut_sor(gecmis, sistem, son_icerik):
    if not OPENROUTER_API_KEY:
        return "⚠️ OPENROUTER_API_KEY tanımlı değil (Render Environment kontrol edin)."
    url = "/".join(["https:", "", "openrouter.ai", "api", "v1", "chat", "completions"])
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://modusoperandiai.com",
        "X-Title": "Modus Operandi AI"
    }
    mesajlar = [{"role": "system", "content": sistem}] + [{"role": "assistant" if m["role"] == "model" else "user", "content": m["text"]} for m in gecmis[-6:]] + [{"role": "user", "content": son_icerik}]
    son_hata = ""
    for m_or in ["google/gemini-2.5-flash", "openai/gpt-4o-mini", "openrouter/auto"]:
        try:
            res = requests.post(url, headers=headers, json={"model": m_or, "messages": mesajlar, "temperature": 0.2}, timeout=35)
            if res.status_code == 200:
                return next(iter(res.json().get("choices", []))).get("message", {}).get("content")
            son_hata = f"HTTP {res.status_code}: {res.text[:160]}"
        except Exception as ex:
            son_hata = str(ex)[:160]
    return f"⚠️ API Hatası: {son_hata}"

def yanit_olustur(soru, gecmis):
    terimler = ingilizce_terimlere_cevir(soru, gecmis)
    if not terimler:
        return "Ben yalnızca artizan fırıncılık, pastacılık, viennoiserie ve fermantasyon bilimi üzerine uzmanlaşmış bir asistanım. Lütfen bu alanlarla ilgili teknik veya bilimsel bir soru sorun.", []
    onc = yerel_kitap_ara(ONCELIKLI_SAYFALAR, terimler, 2)
    dig = yerel_kitap_ara(DIGER_SAYFALAR, terimler, 2)
    akad_metin, akad_kaynak = openalex_ve_crossref_ara(terimler)
    kitap_baglam = "".join(f"\n{k['metin'][:850]}\n" for k in onc + dig)
    kaynaklar = [{"baslik": f"K|{k['kitap']} — Sayfa {k['sayfa']}", "link": "#"} for k in onc] + [{"baslik": f"K|{k['kitap']} — Sayfa {k['sayfa']}", "link": "#"} for k in dig] + akad_kaynak
    sistem = "Sen Türkiye'nin en yetkin Artizan Fırıncılık, Pastacılık ve Gıda Bilimi uzmanısın. Cevaplarını kusursuz, akıcı ve profesyonel bir fırıncılık Türkçesiyle yaz (Örn: 'hamur ağırlığı', 'fırıncı yüzdesi', 'soğuk geciktirme', 'laktik ve asetik asit dengesi' gibi doğru terimler kullan; asla bozuk veya anlamsız kelime çevirileri yapma). Arka plan motorumuz gerçek makaleleri [GERÇEK AKADEMİK MAKALELER] bölümünde topladı; kullanıcı akademik çalışma sorarsa bu makaleleri listele. Metin içinde ayrıca 'Kaynakça' başlığı açma; kaynaklar sistem tarafından otomatik eklenecektir."
    son_icerik = f"Kullanıcı Sorusu: {soru}\n\n[KÜTÜPHANE VERİLERİ]:\n{kitap_baglam}\n\n[ONAYLI HAKEMLİ MAKALELER (DOI REFERANSLI)]:\n{akad_metin}"
    cevap = gemini_bulut_sor(gecmis, sistem, son_icerik) or openrouter_bulut_sor(gecmis, sistem, son_icerik)
    if cevap and "[GERÇEK AKADEMİK MAKALELER]" in cevap:
        cevap = cevap.split("[GERÇEK AKADEMİK MAKALELER]")[0].strip()
    # GERCEK_161_KAYNAK
    temiz_k = []
    for _it in (kaynaklar or []):
        _b = _it.get("baslik", "")
        _b = _b[2:] if (_b.startswith("K|") or _b.startswith("M|")) else _b
        _l = _it.get("link", "#")
        if _b:
            temiz_k.append({"baslik": _b, "link": _l})
    if not temiz_k:
        try:
            _, _yedek_akad = openalex_ve_crossref_ara(["bakery", "fermentation"])
            for _it in _yedek_akad:
                _b = _it.get("baslik", "")
                _b = _b[2:] if (_b.startswith("K|") or _b.startswith("M|")) else _b
                if _b:
                    temiz_k.append({"baslik": _b, "link": _it.get("link", "#")})
        except Exception:
            pass
    if not temiz_k:
        temiz_k = [
            {"baslik": "Modus Operandi Fırıncılık, Pastacılık ve Fermantasyon Kütüphanesi", "link": "#"},
            {"baslik": "OpenAlex Hakemli Gıda Bilimi Veritabanı (2018–2026)", "link": "https://openalex.org"}
        ]
    kaynaklar = temiz_k
    return (cevap, kaynaklar) if cevap else ("⚠️ Bulut sunucularında anlık yoğunluk var, lütfen birkaç saniye sonra tekrar deneyin.", [])

@app.route('/', methods=['GET', 'POST'])
def index():
    sid = session.setdefault("sid", str(random.randint(100000, 999999)))
    SOHBET_DEPO.setdefault(sid, [])
    pdf_sayisi = len(glob.glob(os.path.expanduser("~/kitaplar/oncelikli/*.pdf"))) + len(glob.glob(os.path.expanduser("~/kitaplar/*.pdf")))
    if request.method == 'GET':
        _sh = session.get('uye_eposta')
        _gc = _gecmis().get(_sh, []) if _sh else []
        if not session.pop('gecmis_yuklendi', False):
            SOHBET_DEPO[sid] = []
        return render_template('index.html', sohbet=SOHBET_DEPO.get(sid, []), pdf_sayisi=pdf_sayisi, gecmis_listesi=_gc)
    if "sohbet" not in session: SOHBET_DEPO[sid] = []
    soru = request.form.get('soru', '').strip()
    if soru:
        cevap, kaynaklar = yanit_olustur(soru, SOHBET_DEPO[sid])
        SOHBET_DEPO[sid].extend([{"role": "user", "text": soru}, {"role": "model", "text": cevap, "kaynaklar": kaynaklar}])
        pass
    session['sid'] = sid; _sh = session.get('uye_eposta'); _gc = _gecmis().get(_sh, []) if _sh else []; return render_template('index.html', sohbet=SOHBET_DEPO[sid], pdf_sayisi=pdf_sayisi, gecmis_listesi=_gc)

@app.route("/cikis")
def cikis():
    session.pop("pro_yetkili", None)
    session.pop("pro_kullanici", None)
    return render_template("pro.html", acik_panel=False, hata=None, sonuc=None, uretim_adi="", urunler=[])

ISLER = {}

@app.route("/sor", methods=["GET", "POST"])
def api_sor():
    import time
    if not session.get("sinirsiz") and not session.get("pro_yetkili"):
        simdi = time.time()
        if simdi - session.get("kota_baslangic", 0) >= 86400:
            session["kota_baslangic"] = simdi
            session["kota_sayi"] = 0
        if session.get("kota_sayi", 0) >= 5:
            if session.get("ek_soru_hakki", 0) > 0:
                session["ek_soru_hakki"] = session.get("ek_soru_hakki", 0) - 1
            else:
                return jsonify({"hata": "Günlük 5 ücretsiz soru hakkınız doldu.", "limit_doldu": True}), 429
        else:
            session["kota_sayi"] = session.get("kota_sayi", 0) + 1
    soru = (request.args.get("q") or "").strip()
    if not soru: return {"ok": False}
    _aktif_ep = session.get("uye_eposta", "")
    jid = str(random.randint(100000, 999999))
    ISLER[jid] = {"durum": "bekliyor"}
    def arka_plan():
        try:
            c, k = yanit_olustur(soru, [])
            ISLER[jid] = {"durum": "hazir", "cevap": c, "kaynaklar": k}
            if _aktif_ep and c:
                try:
                    _g = _gecmis()
                    _l = _g.get(_aktif_ep, [])
                    _baslik = (soru[:42] + "...") if len(soru) > 42 else soru
                    _l.insert(0, {"id": jid, "baslik": _baslik, "mesajlar": [{"role": "user", "text": soru}, {"role": "model", "text": c, "kaynaklar": k}]})
                    _g[_aktif_ep] = _l[:30]
                    _gecmis_kaydet(_g)
                except Exception:
                    pass
        except Exception as e:
            ISLER[jid] = {"durum": "hazir", "cevap": f"Hata: {e}", "kaynaklar": []}
    import threading
    threading.Thread(target=arka_plan, daemon=True).start()
    return {"ok": True, "jid": jid}

@app.route("/durum/<jid>")
def api_durum(jid):
    return ISLER.get(jid, {"durum": "bekliyor"})

def temizle():
    _sid = session.get('sid'); _m = SOHBET_DEPO.get(_sid, []) if _sid else []; _sh = session.get('uye_eposta');
    if _m and _sh:
        _g = _gecmis(); _l = _g.get(_sh, []); _b = next((x['text'][:42] for x in _m if x.get('role') == 'user'), 'Sohbet'); _l.insert(0, {'id': str(uuid.uuid4())[:8], 'baslik': _b, 'mesajlar': list(_m)}); _g[_sh] = _l[:25]; _gecmis_kaydet(_g)
    SOHBET_DEPO.clear()
    return redirect('/')

URUN_LISTE_DOSYASI = os.path.expanduser("~/gunluk_urun_listesi.json")

def urun_listesi_yukle():
    if os.path.exists(URUN_LISTE_DOSYASI):
        try: return json.load(open(URUN_LISTE_DOSYASI, "r", encoding="utf-8"))
        except Exception: pass
    return [
        {"id": 1, "ad": "Country Sourdough", "adet": 40, "gramaj": 900, "su": 75, "maya": 20, "tuz": 2.0, "ekstralar": [{"ad": "Tam Buğday Unu", "oran": 15}, {"ad": "Çavdar Unu", "oran": 5}], "yapilis": "1. Unları ve suyu karıştırıp 45 dk otoliz yapın.\n2. Aktif ekşi mayayı ekleyip 4 dk yoğurun, ardından tuzu ilave edin.\n3. 24°C ortamda 3.5 saat ana fermantasyon süresince 30 dk arayla 4 kez katlama yapın.\n4. 900g tartıp şekil verin, 4°C soğuk dolapta 14 saat dinlendirin.\n5. 240°C buharlı fırında 42 dk pişirin."},
        {"id": 2, "ad": "Artizan Baget", "adet": 20, "gramaj": 350, "su": 72, "maya": 18, "tuz": 2.0, "ekstralar": [{"ad": "Tam Buğday Unu", "oran": 10}], "yapilis": "1. Un ve suyun %65'ini karıştırıp 40 dk otoliz yapın.\n2. Maya, tuz ve kalan suyu kademeli ekleyerek orta-güçlü glüten geliştirin.\n3. 2.5 saat ana fermantasyonda 2 kez zarf katlama yapın.\n4. 350g bölüp ön şekil verin, 25 dk dinlendirip fitil formu verin.\n5. Jiletle çizip 245°C taş tabanda 24 dk pişirin."}
    ]

def urun_listesi_kaydet(liste):
    json.dump(liste, open(URUN_LISTE_DOSYASI, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

PRO_SIFRE = "modus2026"
UYELER_DOSYASI = os.path.expanduser("~/pro_uyeler.json")

def uyeleri_yukle():
    if os.path.exists(UYELER_DOSYASI):
        try: return json.load(open(UYELER_DOSYASI, "r", encoding="utf-8"))
        except Exception: pass
    return {}

def uye_kaydet(kullanici, eposta, sifre, plan, odeme_turu):
    uyeler = uyeleri_yukle()
    uyeler[kullanici.lower()] = {"ad": kullanici, "eposta": eposta, "sifre": sifre, "plan": plan, "odeme": odeme_turu, "tarih": time.strftime("%Y-%m-%d")}
    json.dump(uyeler, open(UYELER_DOSYASI, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

@app.route('/_eski_pro', methods=['GET', 'POST'])
def pro():
    if request.method == "POST":
        islem = request.form.get("islem", "")
        if islem == "kayit":
            k_ad = request.form.get("kullanici_adi", "").strip()
            eposta = request.form.get("eposta", "").strip()
            sifre = request.form.get("sifre", "").strip()
            plan = request.form.get("plan", "Yıllık ($190/yıl)")
            odeme = request.form.get("odeme_turu", "Kredi / Banka Kartı")
            if k_ad and sifre:
                uye_kaydet(k_ad, eposta, sifre, plan, odeme)
                session["pro_yetkili"] = True
                session["pro_kullanici"] = f"{k_ad} ({plan.split()[0]})"
        elif islem == "giris":
            k_ad = request.form.get("kullanici_adi", "").strip()
            sifre = request.form.get("sifre", "").strip()
            uyeler = uyeleri_yukle()
            kayitli = uyeler.get(k_ad.lower())
            if sifre == PRO_SIFRE or (kayitli and kayitli.get("sifre") == sifre):
                session["pro_yetkili"] = True
                session["pro_kullanici"] = kayitli["ad"] if kayitli else (k_ad or "PRO Üye")
            else:
                return render_template("pro.html", acik_panel=False, hata="Hatalı kullanıcı adı veya şifre!", sonuc=None, uretim_adi="", urunler=[])

    if not session.get("pro_yetkili"):
        return render_template("pro.html", acik_panel=False, hata=None, sonuc=None, uretim_adi="", urunler=[])
    liste = urun_listesi_yukle()
    sonuc, uretim_adi = None, "Artizan Ekşi Mayalı Ekmek"
    acik_panel = (request.args.get('panel') == '1') or (request.method == 'POST')

    if request.method == 'POST':
        islem = request.form.get('islem', 'hesapla')
        if islem == 'urun_ekle':
            yeni_ad = request.form.get('yeni_ad', '').strip()
            if yeni_ad:
                ek_adlar = request.form.getlist('ek_ad[]')
                ek_oranlar = request.form.getlist('ek_oran[]')
                ekstralar = [{"ad": a.strip(), "oran": float(o)} for a, o in zip(ek_adlar, ek_oranlar) if a.strip() and o]
                yeni_id = max([u.get("id", 0) for u in liste], default=0) + 1
                liste.append({
                    "id": yeni_id, "ad": yeni_ad,
                    "adet": int(request.form.get('yeni_adet', 20)),
                    "gramaj": float(request.form.get('yeni_gramaj', 850)),
                    "su": float(request.form.get('yeni_su', 75)),
                    "maya": float(request.form.get('yeni_maya', 20)),
                    "tuz": float(request.form.get('yeni_tuz', 2.0)),
                    "ekstralar": ekstralar,
                    "yapilis": request.form.get('yeni_yapilis', '1. Un ve suyu karıştırıp otoliz yapın.\n2. Maya ve tuzu ekleyip yoğurun.\n3. Fermantasyon ve şekillendirme sonrası pişirin.').strip()
                })
                urun_listesi_kaydet(liste)
        elif islem == 'urun_sil':
            sil_id = int(request.form.get('sil_id', 0))
            liste = [u for u in liste if u.get("id") != sil_id]
            urun_listesi_kaydet(liste)
        else:
            uretim_adi = request.form.get('uretim_adi', uretim_adi)
            adet = int(request.form.get('adet', 40))
            gram = float(request.form.get('birim_gramaj', 900))
            su_o = float(request.form.get('su', 75))
            maya_o = float(request.form.get('maya', 20))
            tuz_o = float(request.form.get('tuz', 2.0))
            oran = request.form.get('besleme_orani', '1:2:2')
            baslangic = request.form.get('baslangic_saati', '08:00')

            h_ek_ad = request.form.getlist('h_ek_ad[]')
            h_ek_oran = request.form.getlist('h_ek_oran[]')
            h_ekstralar = [{"ad": a.strip(), "oran": float(o)} for a, o in zip(h_ek_ad, h_ek_oran) if a.strip() and o]
            ek_toplam_oran = sum(e["oran"] for e in h_ekstralar)

            toplam_hamur = adet * gram
            un = (toplam_hamur / (100 + su_o + maya_o + tuz_o + ek_toplam_oran)) * 100
            maya = un * (maya_o / 100)
            p_maya, p_un, p_su = [int(x) for x in oran.split(":")]
            pay = (maya + 100) / (p_maya + p_un + p_su)

            saat, dk = [int(x) for x in baslangic.split(":")]
            def saat_ekle(ek_dk):
                tot = (saat * 60 + dk + ek_dk) % 1440
                return f"{tot // 60:02d}:{tot % 60:02d}"

            takvim = [
                {"saat": saat_ekle(0), "asama": "Maya Besleme Döngüsü", "detay": f"{round(pay*p_maya)}g ana maya + {round(pay*p_un)}g un + {round(pay*p_su)}g su"},
                {"saat": saat_ekle(240), "asama": "Otoliz", "detay": f"{round(un)}g un + {round(un*su_o/100)}g su (45 dk dinlendirme)"},
                {"saat": saat_ekle(285), "asama": "Yoğurma", "detay": f"{round(maya)}g aktif maya + {round(un*tuz_o/100)}g tuz ilavesi"},
                {"saat": saat_ekle(315), "asama": "Ana Fermantasyon & Katlama", "detay": "30 dk arayla 4 tur katlama (24°C)"},
                {"saat": saat_ekle(525), "asama": "Bölme & Şekillendirme", "detay": f"{adet} adet x {round(gram)}g porsiyonlama"},
                {"saat": saat_ekle(570), "asama": "Soğuk Geciktirme", "detay": "4°C dolapta 12-16 saat olgunlaştırma"},
                {"saat": saat_ekle(1350), "asama": "Fırınlama", "detay": "240°C buharlı 20 dk + 215°C kuru 22 dk"}
            ]

            sonuc = {
                "adet": adet, "birim_gramaj": round(gram), "toplam_hamur": round(toplam_hamur),
                "un": round(un), "su": round(un * su_o / 100), "aktif_maya": round(maya), "tuz": round(un * tuz_o / 100),
                "ekstralar": [{"ad": e["ad"], "oran": e["oran"], "gram": round(un * e["oran"] / 100)} for e in h_ekstralar],
                "oran": oran, "ana_maya": round(pay * p_maya), "besleme_un": round(pay * p_un), "besleme_su": round(pay * p_su),
                "takvim": takvim
            }

    for u in liste:
        ek_or = sum(e.get("oran", 0) for e in u.get("ekstralar", []))
        th = u["adet"] * u["gramaj"]
        un_gr = (th / (100 + u["su"] + u["maya"] + u["tuz"] + ek_or)) * 100
        u["hesap"] = {
            "toplam_hamur": round(th), "un": round(un_gr),
            "su": round(un_gr * u["su"] / 100), "maya": round(un_gr * u["maya"] / 100), "tuz": round(un_gr * u["tuz"] / 100),
            "ekstralar": [{"ad": e["ad"], "oran": e["oran"], "gram": round(un_gr * e["oran"] / 100)} for e in u.get("ekstralar", [])]
        }

    return render_template('pro.html', acik_panel=acik_panel, sonuc=sonuc, uretim_adi=uretim_adi, urunler=liste)

@app.after_request
def no_cache(r):
    r.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return r


UYELER_D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uyeler_eposta.json")
GECMIS_D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sohbet_gecmisi.json")

def _uyeler():
    try: return json.load(open(UYELER_D, "r", encoding="utf-8")) if os.path.exists(UYELER_D) else {}
    except Exception: return {}

def _gecmis():
    try:
        if "_kv_yukle" in globals():
            return _kv_yukle("gecmis", GECMIS_D)
    except Exception:
        pass
    try:
        return json.load(open(GECMIS_D, "r", encoding="utf-8")) if os.path.exists(GECMIS_D) else {}
    except Exception:
        return {}

def _gecmis_kaydet(veri):
    try:
        json.dump(veri, open(GECMIS_D, "w", encoding="utf-8"), ensure_ascii=False)
    except Exception:
        pass
    try:
        if "_kv_kaydet" in globals():
            _kv_kaydet("gecmis", veri, GECMIS_D)
    except Exception:
        pass

def apple_giris():
    import urllib.parse
    cid = os.environ.get("APPLE_CLIENT_ID", "").strip()
    if not cid:
        session["uye_mesaj"] = "Apple ile giriş şu anda yapılandırılıyor. Google veya e-posta ile giriş yapabilirsiniz."
        return redirect("/")
    redirect_uri = request.url_root.rstrip("/") + "/apple_callback"
    params = urllib.parse.urlencode({
        "client_id": cid,
        "redirect_uri": redirect_uri,
        "response_type": "code id_token",
        "scope": "name email",
        "response_mode": "form_post"
    })
    return redirect("https://apple.com?" + params)

@app.route("/apple_callback", methods=["POST"])
def apple_callback():
    import base64
    id_token = request.form.get("id_token", "")
    user_raw = request.form.get("user", "")
    if not id_token or "." not in id_token:
        session["uye_mesaj"] = "Apple hesabı doğrulanamadı."
        return redirect("/")
    try:
        payload_b64 = id_token.split(".")[1] + "=="
        claims = json.loads(base64.urlsafe_b64decode(payload_b64).decode("utf-8"))
        ep = claims.get("email", "").strip().lower()
        ad = ep.split("@") if "@" in ep else "Apple Üyesi"
        if user_raw:
            u_obj = json.loads(user_raw)
            nm = u_obj.get("name", {})
            tam_ad = f"{nm.get('firstName', '')} {nm.get('lastName', '')}".strip()
            if tam_ad: ad = tam_ad
        if ep:
            u = _uyeler()

            if ep not in u:
                u[ep] = {"ad": ad, "kullanici_adi": ep.split("@"), "eposta": ep, "sifre": secrets.token_hex(12)}
                json.dump(u, open(UYELER_D, "w", encoding="utf-8"), ensure_ascii=False)
            session["uye_eposta"] = ep
            session["uye_ad"] = u[ep].get("ad", ad)
            session.pop("uye_mesaj", None)
    except Exception:
        session["uye_mesaj"] = "Apple girişi tamamlanamadı."
    return redirect("/")

@app.route("/google_giris")
def google_giris():
    import urllib.parse
    cid = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
    if not cid:
        session["uye_mesaj"] = "Google giriş anahtarı henüz tanımlanmadı."
        return redirect("/")
    kok = request.url_root.rstrip("/")
    canli_cb = "/".join(["https:", "", "modusoperandiai.com", "google_callback"])
    yerel_cb = "/".join(["http:", "", "localhost:5000", "google_callback"])
    redirect_uri = yerel_cb if ("127.0.0.1" in kok or "localhost" in kok) else canli_cb
    params = urllib.parse.urlencode({
        "client_id": cid,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "prompt": "select_account"
    })
    auth_host = "accounts." + "google.com"
    auth_url = f"https://{auth_host}/o/oauth2/v2/auth?{params}"
    return redirect(auth_url)

@app.route("/google_callback")
def google_callback():
    import urllib.request, urllib.parse
    code = request.args.get("code", "")
    cid = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
    csec = os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()
    if not code or not cid or not csec:
        session["uye_mesaj"] = "Google girişi tamamlanamadı."
        return redirect("/")
    try:
        kok = request.url_root.rstrip("/")
        canli_cb = "/".join(["https:", "", "modusoperandiai.com", "google_callback"])
        yerel_cb = "/".join(["http:", "", "localhost:5000", "google_callback"])
        redirect_uri = yerel_cb if ("127.0.0.1" in kok or "localhost" in kok) else canli_cb
        data = urllib.parse.urlencode({
            "code": code, "client_id": cid, "client_secret": csec,
            "redirect_uri": redirect_uri, "grant_type": "authorization_code"
        }).encode("utf-8")
        tok_host = "oauth2." + "googleapis.com"
        req = urllib.request.Request(f"https://{tok_host}/token", data=data)
        token_res = json.loads(urllib.request.urlopen(req, timeout=10).read().decode("utf-8"))
        id_token = token_res.get("id_token", "")
        info_url = f"https://{tok_host}/tokeninfo?id_token=" + urllib.parse.quote(id_token)
        uinfo = json.loads(urllib.request.urlopen(info_url, timeout=10).read().decode("utf-8"))
        ep = str(uinfo.get("email", "")).strip().lower()
        kisa = ep.split("@")[0] if "@" in ep else ep
        ad = str(uinfo.get("name", kisa)).strip() or kisa
        if ep:
            u = _uyeler()
            if ep not in u:
                u[ep] = {"ad": ad, "kullanici_adi": kisa, "eposta": ep, "sifre": secrets.token_hex(12)}
                json.dump(u, open(UYELER_D, "w", encoding="utf-8"), ensure_ascii=False)
            session["uye_eposta"] = ep
            session["uye_ad"] = str(u[ep].get("ad", ad))
            session.pop("uye_mesaj", None)
    except Exception as err:
        session["uye_mesaj"] = f"Google girişi başarısız: {str(err)[:80]}"
    return redirect("/")

@app.route("/uye_islem", methods=["POST"])
def uye_islem():
    if request.form.get("eposta", "").strip().lower() in ("deneme", "deneme@modusoperandiai.com") and request.form.get("sifre", "") == "123456":
        session["uye_eposta"] = "deneme@modusoperandiai.com"
        session["uye_ad"] = "Deneme Üye"
        session.pop("sinirsiz", None)
        return redirect("/")
    if request.form.get("eposta", "").strip().lower() in ("modus", "admin@modusoperandiai.com") and request.form.get("sifre", "") == "modus2026":
        session["uye_eposta"] = "admin@modusoperandiai.com"
        session["uye_ad"] = "Modus Kurucu"
        session["sinirsiz"] = True
        return redirect("/")

    tur = request.form.get("tur", "giris")
    ep = request.form.get("eposta", "").strip().lower()
    k_ad = request.form.get("kullanici_adi", "").strip().lower()
    sf = request.form.get("sifre", "").strip()
    ad = request.form.get("ad", "").strip()
    u = _uyeler()
    if tur == "kayit":
        if not ad or not k_ad or "@" not in ep or not sf:
            session["uye_mesaj"] = "Lütfen Ad Soyad, Kullanıcı Adı, geçerli E-posta ve Şifre alanlarını eksiksiz doldurun."
            return redirect("/")
        if ep in u or any(str(v.get("kullanici_adi", "")).lower() == k_ad for v in u.values()):
            session["uye_mesaj"] = "Bu kullanıcı adı veya e-posta zaten kayıtlı."
            return redirect("/")
        u[ep] = {"ad": ad, "kullanici_adi": k_ad, "eposta": ep, "sifre": sf}
        json.dump(u, open(UYELER_D, "w", encoding="utf-8"), ensure_ascii=False)
        session["uye_eposta"] = ep
        session["uye_ad"] = f"{ad} (@{k_ad})"
        session.pop("uye_mesaj", None)
    elif tur == "giris":
        giris_id = ep
        bulunan_ep, bulunan_u = None, None
        for mail_key, veri in u.items():
            if mail_key == giris_id or str(veri.get("kullanici_adi", "")).lower() == giris_id:
                bulunan_ep, bulunan_u = mail_key, veri
                break
        if bulunan_u and str(bulunan_u.get("sifre", "")) == sf:
            session["uye_eposta"] = bulunan_ep
            session["uye_ad"] = f"{bulunan_u.get('ad', '')} (@{bulunan_u.get('kullanici_adi', '')})"
            session.pop("uye_mesaj", None)
        else:
            session["uye_mesaj"] = "Hatalı kullanıcı adı, e-posta veya şifre."
    elif tur == "cikis":
        session.clear()
    return redirect("/")

@app.route("/sifre_sifirla", methods=["POST"])
def sifre_sifirla():
    import random, smtplib
    from email.message import EmailMessage
    adim = request.form.get("adim", "kod_gonder")
    ep = request.form.get("eposta", "").strip().lower()
    u = _uyeler()
    if adim == "kod_gonder":
        if ep not in u:
            session["uye_mesaj"] = "Bu e-posta adresiyle kayıtlı bir hesap bulunamadı."
            return redirect("/")
        dogrulama_kodu = str(random.randint(100000, 999999))
        session["reset_eposta"] = ep
        session["reset_kod"] = dogrulama_kodu
        session["reset_adim"] = "kod_dogrula"
        smtp_user = os.environ.get("SMTP_EMAIL", "")
        smtp_pass = os.environ.get("SMTP_PASS", "")
        if smtp_user and smtp_pass:
            try:
                msg = EmailMessage()
                msg["Subject"] = "Modus Operandi AI — Hesap Bilgileri ve Şifre Sıfırlama"
                msg["From"] = smtp_user
                msg["To"] = ep
                msg.set_content(f"Merhaba {u[ep].get('ad','')},\n\nKayıtlı Kullanıcı Adınız: {u[ep].get('kullanici_adi', ep)} | E-posta: {ep}\nŞifre Sıfırlama Kodunuz: {dogrulama_kodu}\n\nModus Operandi AI")
                with smtplib.SMTP_SSL("://gmail.com", 465) as s:
                    s.login(smtp_user, smtp_pass)
                    s.send_message(msg)
                session["uye_bilgi"] = f"Doğrulama kodu ve kullanıcı adı bilginiz {ep} adresine gönderildi."
            except Exception:
                session["uye_bilgi"] = f"Sıfırlama kodunuz hazır (Test Kodu: {dogrulama_kodu})."
        else:
            session["uye_bilgi"] = f"Sıfırlama kodunuz oluşturuldu (Kod: {dogrulama_kodu})."
    elif adim == "yeni_sifre":
        girilen_kod = request.form.get("kod", "").strip()
        yeni_sf = request.form.get("yeni_sifre", "").strip()
        hedef_ep = session.get("reset_eposta", "")
        if girilen_kod != session.get("reset_kod") or not yeni_sf or hedef_ep not in u:
            session["uye_mesaj"] = "Doğrulama kodu hatalı veya eksik!"
            return redirect("/")
        u[hedef_ep]["sifre"] = yeni_sf
        json.dump(u, open(UYELER_D, "w", encoding="utf-8"), ensure_ascii=False)
        session["uye_eposta"] = hedef_ep
        session["uye_ad"] = u[hedef_ep].get("ad", hedef_ep)
        for k in ["reset_eposta", "reset_kod", "reset_adim", "uye_mesaj", "uye_bilgi"]:
            session.pop(k, None)
    return redirect("/")

@app.route("/gecmis_sil/<gid>", methods=["POST", "GET"])
def gecmis_sil(gid):
    sahip = session.get("uye_eposta")
    if not sahip:
        return redirect("/")
    g = _gecmis()
    g[sahip] = [it for it in g.get(sahip, []) if it.get("id") != gid]
    _gecmis_kaydet(g)
    if request.headers.get("X-Requested-With") == "fetch":
        return jsonify({"ok": True})
    return redirect("/")

@app.route("/gecmis_yukle/<gid>")
def gecmis_yukle(gid):
    sahip = session.get("uye_eposta")
    if not sahip: return redirect("/")
    sid = session.setdefault("sid", str(random.randint(100000, 999999)))
    for it in _gecmis().get(sahip, []):
        if it.get("id") == gid:
            SOHBET_DEPO[sid] = list(it.get("mesajlar", []))
            session["gecmis_yuklendi"] = True
            break
    return redirect("/")

TEK_KULLANIMLIK_KODLAR = {"MO25-DE2A09": 25, "MO25-F7CD81": 25, "MO25-EE4248": 25, "MO25-9631DA": 25, "MO25-4C2086": 25, "MO25-38689C": 25, "MO25-DB2E10": 25, "MO25-DC4784": 25, "MO25-5A97B6": 25, "MO25-1EE38B": 25, "MO25-2737DB": 25, "MO25-F1A0D9": 25, "MO25-D03E49": 25, "MO25-4CA891": 25, "MO25-C5102C": 25, "MO25-EBFB37": 25, "MO25-6EBD6B": 25, "MO25-0F2BFF": 25, "MO25-ED702E": 25, "MO25-2A2DF3": 25, "MO25-0F20FF": 25, "MO25-091A21": 25, "MO25-7AA4BC": 25, "MO25-ACA8CC": 25, "MO25-C6B6BE": 25, "MO25-D2BC2C": 25, "MO25-164C51": 25, "MO25-8C4BFA": 25, "MO25-EBC62F": 25, "MO25-FC6E20": 25, "MO25-85BA07": 25, "MO25-AD44CF": 25, "MO25-B4AA1D": 25, "MO25-D43095": 25, "MO25-32A0C7": 25, "MO25-9C9099": 25, "MO25-E569E3": 25, "MO25-462118": 25, "MO25-49E233": 25, "MO25-B8D59E": 25, "MO25-FC8354": 25, "MO25-6A7E51": 25, "MO25-A23861": 25, "MO25-1B6ED6": 25, "MO25-0CEAF9": 25, "MO25-898F86": 25, "MO25-B00BAB": 25, "MO25-DF4BC2": 25, "MO25-151D7D": 25, "MO25-E60623": 25, "MO25-85BAA5": 25, "MO25-42403D": 25, "MO25-5BA852": 25, "MO25-382760": 25, "MO25-2E3077": 25, "MO25-CDF5BC": 25, "MO25-8B6656": 25, "MO25-A01809": 25, "MO25-0AA8E1": 25, "MO25-81444D": 25, "MO25-E603E7": 25, "MO25-7102DC": 25, "MO25-74BCB9": 25, "MO25-099659": 25, "MO25-BD12AD": 25, "MO25-4A243B": 25, "MO25-F20271": 25, "MO25-AEC6FB": 25, "MO25-405F64": 25, "MO25-54163C": 25, "MO25-B359C4": 25, "MO25-350BA6": 25, "MO25-E119D4": 25, "MO25-E6AE0B": 25, "MO25-D9B711": 25, "MO25-F322C3": 25, "MO25-F1F692": 25, "MO25-057872": 25, "MO25-6A9EC0": 25, "MO25-5E90FF": 25, "MO25-8068A6": 25, "MO25-1A36BE": 25, "MO25-2488CD": 25, "MO25-D52108": 25, "MO25-EA3B30": 25, "MO25-7676B1": 25, "MO25-142FF8": 25, "MO25-49DC59": 25, "MO25-F85653": 25, "MO25-59E456": 25, "MO25-EDD044": 25, "MO25-9D408E": 25, "MO25-6AF0AF": 25, "MO25-12EE48": 25, "MO25-6B2BB5": 25, "MO25-F93E30": 25, "MO25-3F6F59": 25, "MO25-154687": 25, "MO25-9C2793": 25, "MO25-6B9803": 25, "MO50-071971": 50, "MO50-0D54F9": 50, "MO50-450D41": 50, "MO50-168B18": 50, "MO50-D57A89": 50, "MO50-BB7CD7": 50, "MO50-75A989": 50, "MO50-CA4196": 50, "MO50-987126": 50, "MO50-669100": 50, "MO50-6B77A5": 50, "MO50-11072D": 50, "MO50-49ED01": 50, "MO50-1B578C": 50, "MO50-113EEB": 50, "MO50-D66FE6": 50, "MO50-0BD46F": 50, "MO50-5626D2": 50, "MO50-92FAAE": 50, "MO50-33AFE5": 50, "MO50-0971AE": 50, "MO50-4CD140": 50, "MO50-316D9F": 50, "MO50-F780C0": 50, "MO50-B87A57": 50, "MO50-79C15A": 50, "MO50-CC9D53": 50, "MO50-6B8245": 50, "MO50-9FCFA9": 50, "MO50-E9FE91": 50, "MO50-22E2BC": 50, "MO50-9E6509": 50, "MO50-1685C8": 50, "MO50-B7315C": 50, "MO50-54212C": 50, "MO50-343151": 50, "MO50-DBA947": 50, "MO50-D87B79": 50, "MO50-CCB3BD": 50, "MO50-9D81E2": 50, "MO50-AEB367": 50, "MO50-E39828": 50, "MO50-D06EF0": 50, "MO50-1A68B7": 50, "MO50-DB5DC3": 50, "MO50-FA54D6": 50, "MO50-71828C": 50, "MO50-B1BD5B": 50, "MO50-6AAA90": 50, "MO50-1A9A2C": 50, "MO50-42174A": 50, "MO50-461E7C": 50, "MO50-1880E4": 50, "MO50-BFDB18": 50, "MO50-DA405B": 50, "MO50-51D2C2": 50, "MO50-68319C": 50, "MO50-640C20": 50, "MO50-4C38E5": 50, "MO50-16930D": 50, "MO50-5E6660": 50, "MO50-608347": 50, "MO50-26E9C0": 50, "MO50-28399C": 50, "MO50-32BC5D": 50, "MO50-8FDAC6": 50, "MO50-D72D23": 50, "MO50-5D0AFC": 50, "MO50-EC9275": 50, "MO50-46DBC8": 50, "MO50-90B3E0": 50, "MO50-CBEC28": 50, "MO50-CB5A1D": 50, "MO50-291156": 50, "MO50-2E5BBD": 50, "MO50-B0137D": 50, "MO50-515D71": 50, "MO50-79A608": 50, "MO50-AF09DF": 50, "MO50-71AE65": 50, "MO50-777CB0": 50, "MO50-4B9CD4": 50, "MO50-FBBBEF": 50, "MO50-0D2F72": 50, "MO50-99835C": 50, "MO50-6E8CF5": 50, "MO50-5307A6": 50, "MO50-FB3440": 50, "MO50-E79C7C": 50, "MO50-9A2F52": 50, "MO50-51EA0C": 50, "MO50-298568": 50, "MO50-EE4FE9": 50, "MO50-03E411": 50, "MO50-842358": 50, "MO50-75EA2F": 50, "MO50-6DBE52": 50, "MO50-887115": 50, "MO50-1F0BB0": 50, "MO50-F37171": 50, "MO100-D39439": 100, "MO100-480509": 100, "MO100-749696": 100, "MO100-10FDB2": 100, "MO100-41ED73": 100, "MO100-C66CE5": 100, "MO100-0AF6B4": 100, "MO100-5F070F": 100, "MO100-31C927": 100, "MO100-974EE6": 100, "MO100-39F5A6": 100, "MO100-75F35B": 100, "MO100-9F5415": 100, "MO100-265367": 100, "MO100-46FD02": 100, "MO100-A4183A": 100, "MO100-A0E9AB": 100, "MO100-2E7E4F": 100, "MO100-A3CD4C": 100, "MO100-2AC532": 100, "MO100-C87E34": 100, "MO100-95DCB1": 100, "MO100-F3F226": 100, "MO100-C089A4": 100, "MO100-3BD0D8": 100, "MO100-C54B76": 100, "MO100-C7CFCE": 100, "MO100-7FA091": 100, "MO100-002A11": 100, "MO100-7FA1E1": 100, "MO100-F0BEE3": 100, "MO100-2B17C6": 100, "MO100-EDA3CA": 100, "MO100-8F4C51": 100, "MO100-90E9E4": 100, "MO100-B7F69D": 100, "MO100-3470CC": 100, "MO100-4BE22B": 100, "MO100-A5060D": 100, "MO100-81EB60": 100, "MO100-B33570": 100, "MO100-F4CDA8": 100, "MO100-C7111D": 100, "MO100-9A43CE": 100, "MO100-183A89": 100, "MO100-7591CF": 100, "MO100-ACB49F": 100, "MO100-3FD698": 100, "MO100-CFBCC4": 100, "MO100-D5BA4B": 100, "MO100-701D61": 100, "MO100-64769B": 100, "MO100-3F0806": 100, "MO100-851F20": 100, "MO100-612309": 100, "MO100-89AED6": 100, "MO100-482A62": 100, "MO100-174572": 100, "MO100-80CB22": 100, "MO100-02F437": 100, "MO100-A6E440": 100, "MO100-A8F14E": 100, "MO100-3AA40F": 100, "MO100-E2DC70": 100, "MO100-99F1CB": 100, "MO100-0091A1": 100, "MO100-314C42": 100, "MO100-97E2D4": 100, "MO100-73BE12": 100, "MO100-71CA24": 100, "MO100-CB375D": 100, "MO100-7C9615": 100, "MO100-CFE92B": 100, "MO100-01E216": 100, "MO100-A72C46": 100, "MO100-28877A": 100, "MO100-E64F59": 100, "MO100-FBCE74": 100, "MO100-85B629": 100, "MO100-223781": 100, "MO100-0CB92F": 100, "MO100-7977D1": 100, "MO100-883F92": 100, "MO100-D1D48B": 100, "MO100-465ED5": 100, "MO100-81E92F": 100, "MO100-0E5CE6": 100, "MO100-1691FE": 100, "MO100-2A4A4F": 100, "MO100-F11DCE": 100, "MO100-18EAD5": 100, "MO100-E55566": 100, "MO100-C98619": 100, "MO100-B96BBF": 100, "MO100-C77454": 100, "MO100-1B7AC6": 100, "MO100-A7AA0F": 100, "MO100-2CB1BA": 100, "MO100-BBD075": 100, "MO100-38CDA1": 100}

@app.route("/paketler", methods=["GET", "POST"])
def paketler():
    mesaj = None
    if request.method == "POST":
        girilen = request.form.get("kod", "").strip().upper()
        # Neon PostgreSQL ve yerel dosyada global olarak kullanilmis kodlari kontrol et
        kullanilan_global = _kv_yukle("kullanilan_kodlar", os.path.join(os.path.dirname(os.path.abspath(__file__)), "kullanilan_kodlar.json")) if "_kv_yukle" in globals() else {}
        if girilen in kullanilan_global:
            mesaj = "⚠️ Bu aktivasyon kodu daha önce kullanılmış ve geçersiz kılınmıştır."
        elif girilen in TEK_KULLANIMLIK_KODLAR or girilen in (_kv_yukle("dinamik_kodlar", os.path.join(os.path.dirname(os.path.abspath(__file__)), "dinamik_kodlar.json")) if "_kv_yukle" in globals() else {}):
            _din = _kv_yukle("dinamik_kodlar", os.path.join(os.path.dirname(os.path.abspath(__file__)), "dinamik_kodlar.json")) if "_kv_yukle" in globals() else {}
            adet = TEK_KULLANIMLIK_KODLAR.get(girilen) or _din.get(girilen)
            session["ek_soru_hakki"] = session.get("ek_soru_hakki", 0) + adet
            kullanilan_global[girilen] = {"eposta": session.get("uye_eposta", "misafir"), "adet": adet}
            if "_kv_kaydet" in globals():
                _kv_kaydet("kullanilan_kodlar", kullanilan_global, os.path.join(os.path.dirname(os.path.abspath(__file__)), "kullanilan_kodlar.json"))
            mesaj = f"✅ {adet} ek soru hakkı hesabınıza tanımlandı! Toplam bakiyeniz: {session['ek_soru_hakki']} Hak"
        else:
            mesaj = "⚠️ Geçersiz aktivasyon kodu."
    l25 = os.environ.get("ODEME_LINK_25", "mailto:info@://modusoperandiai.com")
    l50 = os.environ.get("ODEME_LINK_50", "mailto:info@://modusoperandiai.com")
    l100 = os.environ.get("ODEME_LINK_100", "mailto:info@://modusoperandiai.com")
    return render_template("paketler.html", mesaj=mesaj, ek_hak=session.get("ek_soru_hakki", 0), link_25=l25, link_50=l50, link_100=l100)


@app.route("/pro", methods=["GET", "POST"])
def pro_kapali():
    return redirect("/")

@app.route("/temizle")
def temizle_kesin():
    import uuid
    sid = session.get("sid")
    m = SOHBET_DEPO.get(sid, []) if sid else []
    sh = session.get("uye_eposta")
    if m and sh:
        g = _gecmis()
        l = g.get(sh, [])
        b = next((x["text"][:42] for x in m if x.get("role") == "user"), "Sohbet")
        l.insert(0, {"id": str(uuid.uuid4())[:8], "baslik": b, "mesajlar": list(m)})
        g[sh] = l[:25]
        _gecmis_kaydet(g)
    SOHBET_DEPO.clear()
    return redirect("/")


@app.route("/gizlilik")
def gizlilik():
    return "<h2>Modus Operandi ai — Gizlilik Politikası</h2><p>Kullanıcı bilgileri yalnızca oturum açma ve sohbet geçmişini saklama amacıyla kullanılır; üçüncü taraflarla paylaşılmaz.</p>"


@app.route("/uyeler_yonetim")
def uyeler_yonetim():
    uretilen_kod = ""
    if request.args.get("uret") in ("25", "50", "100"):
        _adet = int(request.args.get("uret"))
        uretilen_kod = f"MO{_adet}-{secrets.token_hex(4).upper()}"
        _din_yol = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dinamik_kodlar.json")
        _din = _kv_yukle("dinamik_kodlar", _din_yol) if "_kv_yukle" in globals() else {}
        _din[uretilen_kod] = _adet
        if "_kv_kaydet" in globals():
            _kv_kaydet("dinamik_kodlar", _din, _din_yol)
    db_durum = "✅ Neon PostgreSQL Bağlı (Kalıcı)" if _pg_baglan() else f"⚠️ Bağlanamadı: {_SON_DB_HATA}"
    mail_durum = "✅ Resend Aktif" if os.environ.get("RESEND_API_KEY", "").strip() else "⚠️ RESEND_API_KEY bekleniyor"
    anahtar = os.environ.get("ADMIN_KEY", "modus2026").strip()
    if request.args.get("key", "") != anahtar:
        return "Yetkisiz erisim.", 403
    u = _uyeler()
    if request.args.get("indir") == "csv":
        satirlar = ["Ad Soyad,Kullanici Adi,E-posta"]
        for ep, d in u.items():
            satirlar.append(f'"{d.get("ad","")}","{d.get("kullanici_adi","")}","{ep}"')
        from flask import Response
        return Response("\n".join(satirlar), mimetype="text/csv", headers={"Content-Disposition": "attachment;filename=modus_uyeler.csv"})
    rows = "".join([f"<tr><td>{i+1}</td><td>{d.get('ad','')}</td><td>{d.get('kullanici_adi','')}</td><td>{ep}</td></tr>" for i, (ep, d) in enumerate(u.items())])
    return f"""<html><head><meta charset='utf-8'><title>Modus Operandi ai — Üyeler</title>
    <style>body{{font-family:sans-serif;background:#faf8f5;padding:30px;color:#1a1815}}table{{width:100%;border-collapse:collapse;background:#fff;margin-top:16px}}th,td{{border:1px solid #e5e0d8;padding:10px;text-align:left}}th{{background:#f3efe8}}.btn{{display:inline-block;padding:10px 16px;background:#b48228;color:#fff;text-decoration:none;border-radius:8px;font-weight:600}}</style></head>
    <body><div style='background:#fff;border:1px solid #e5e0d8;padding:10px 14px;border-radius:10px;margin-bottom:14px;font-size:13.5px'><b>Veritabanı Durumu:</b> {db_durum} &nbsp;|&nbsp; <b>E-posta Sistemi:</b> {mail_durum}</div><div style='background:#fff;border:1px solid #e5e0d8;padding:14px;border-radius:10px;margin-bottom:16px'>
    <b>Tek Kullanımlık Aktivasyon Kodu Üret (Her Tıklamada Yeni Benzersiz Kod):</b><br><br>
    <a class='btn' href='?key={anahtar}&uret=25'>+25 Soru Kodu Üret</a> &nbsp;
    <a class='btn' href='?key={anahtar}&uret=50'>+50 Soru Kodu Üret</a> &nbsp;
    <a class='btn' href='?key={anahtar}&uret=100'>+100 Soru Kodu Üret</a>
    {f"<div style='margin-top:12px;padding:10px;background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;font-size:15px'>✅ Yeni Kod Hazır: <b style='letter-spacing:1px'>{uretilen_kod}</b></div>" if uretilen_kod else ""}
    </div><h2>Kayıtlı Üyeler ({len(u)} Kişi)</h2><a class='btn' href='?key={anahtar}&indir=csv'>Excel / CSV İndir</a>
    <table><tr><th>#</th><th>Ad Soyad</th><th>Kullanıcı Adı</th><th>E-posta</th></tr>{rows}</table></body></html>"""



SOHBETLER_D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sohbetler.json")

def _sohbetleri_oku():
    return _kv_yukle("sohbetler", SOHBETLER_D)

def _sohbetleri_yaz(veri):
    _kv_kaydet("sohbetler", veri, SOHBETLER_D)

@app.route("/api/sohbetler", methods=["GET"])
def api_sohbetler():
    ep = session.get("uye_eposta", "")
    if not ep:
        return jsonify({"giris": False, "sohbetler": []})
    tum = _sohbetleri_oku().get(ep, [])
    ozet = [{"id": s["id"], "baslik": s["baslik"], "tarih": s.get("tarih", "")} for s in tum]
    return jsonify({"giris": True, "sohbetler": ozet})

@app.route("/api/sohbet/<sid>", methods=["GET", "DELETE"])
def api_sohbet_detay(sid):
    ep = session.get("uye_eposta", "")
    if not ep:
        return jsonify({"ok": False}), 401
    tum_veri = _sohbetleri_oku()
    liste = tum_veri.get(ep, [])
    if request.method == "DELETE":
        tum_veri[ep] = [s for s in liste if s["id"] != sid]
        _sohbetleri_yaz(tum_veri)
        return jsonify({"ok": True})
    for s in liste:
        if s["id"] == sid:
            return jsonify({"ok": True, "sohbet": s})
    return jsonify({"ok": False}), 404

@app.route("/api/sohbet_kaydet", methods=["POST"])
def api_sohbet_kaydet():
    ep = session.get("uye_eposta", "")
    if not ep:
        return jsonify({"ok": False})
    veri = request.get_json(silent=True) or {}
    sid = veri.get("id") or str(uuid.uuid4())[:8]
    soru = (veri.get("soru") or "").strip()
    cevap = (veri.get("cevap") or "").strip()
    if not soru:
        return jsonify({"ok": False})
    g = _gecmis()
    liste = g.get(ep, [])
    bulundu = None
    for s in liste:
        if s.get("id") == sid:
            bulundu = s
            break
    if not bulundu:
        baslik = (soru[:42] + "...") if len(soru) > 42 else soru
        bulundu = {"id": sid, "baslik": baslik, "mesajlar": []}
        liste.insert(0, bulundu)
    bulundu["mesajlar"].append({"role": "user", "text": soru})
    bulundu["mesajlar"].append({"role": "model", "text": cevap})
    g[ep] = liste[:30]
    _gecmis_kaydet(g)
    return jsonify({"ok": True, "id": sid, "baslik": bulundu["baslik"]})

if __name__ == '__main__':
    kitaplari_indeksle()
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
