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

FIRINCILIK_SOZLUGU = {
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
        dosya_bonusu = sum(500 for k in kelimeler if k in k_adi_kucuk)
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
    sorgu_en = " ".join(kelimeler[:2]) + " wheat sourdough bread"
    kaynaklar, ozetler = [], ""
    s = chr(47)
    try:
        oa_url = f"https:{s}{s}api.openalex.org{s}works?search={requests.utils.quote(sorgu_en)}&filter=has_doi:true,publication_year:2018-2026&sort=cited_by_count:desc&per-page=5"
        res = requests.get(oa_url, headers={"User-Agent": "mailto:info@eksimaya.ai"}, timeout=35)
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
    sistem = "Sen Türkiye'nin en yetkin Artizan Fırıncılık, Pastacılık ve Gıda Bilimi uzmanısın. Cevaplarını kusursuz, akıcı ve profesyonel bir fırıncılık Türkçesiyle yaz (Örn: 'hamur ağırlığı', 'fırıncı yüzdesi', 'soğuk geciktirme', 'laktik ve asetik asit dengesi' gibi doğru terimler kullan; asla bozuk veya anlamsız kelime çevirileri yapma). Arka plan motorumuz gerçek makaleleri [GERÇEK AKADEMİK MAKALELER] bölümünde topladı; kullanıcı akademik çalışma sorarsa bu makaleleri listele. Normal sorularda metin içinde PDF adı veya sayfa numarası yazma."
    son_icerik = f"Kullanıcı Sorusu: {soru}\n\n[KÜTÜPHANE VERİLERİ]:\n{kitap_baglam}\n\n[ONAYLI HAKEMLİ MAKALELER (DOI REFERANSLI)]:\n{akad_metin}"
    cevap = gemini_bulut_sor(gecmis, sistem, son_icerik) or openrouter_bulut_sor(gecmis, sistem, son_icerik)
    if cevap and "[GERÇEK AKADEMİK MAKALELER]" in cevap:
        cevap = cevap.split("[GERÇEK AKADEMİK MAKALELER]")[0].strip()
    return (cevap, kaynaklar) if cevap else ("⚠️ Bulut sunucularında anlık yoğunluk var, lütfen birkaç saniye sonra tekrar deneyin.", [])

@app.route('/', methods=['GET', 'POST'])
def index():
    sid = session.setdefault("sid", str(random.randint(100000, 999999)))
    SOHBET_DEPO.setdefault(sid, [])
    pdf_sayisi = len(glob.glob(os.path.expanduser("~/kitaplar/oncelikli/*.pdf"))) + len(glob.glob(os.path.expanduser("~/kitaplar/*.pdf")))
    if request.method == 'GET':
        SOHBET_DEPO[sid] = []
        return render_template('index.html', sohbet=[], pdf_sayisi=pdf_sayisi)
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
    if not session.get("pro_yetkili") and not session.get("uye_eposta"):
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
    jid = str(random.randint(100000, 999999))
    ISLER[jid] = {"durum": "bekliyor"}
    def arka_plan():
        try:
            c, k = yanit_olustur(soru, [])
            ISLER[jid] = {"durum": "hazir", "cevap": c, "kaynaklar": k}
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
        _g = _gecmis(); _l = _g.get(_sh, []); _b = next((x['text'][:42] for x in _m if x.get('role') == 'user'), 'Sohbet'); _l.insert(0, {'id': str(uuid.uuid4())[:8], 'baslik': _b, 'mesajlar': list(_m)}); _g[_sh] = _l[:25]; json.dump(_g, open(GECMIS_D, 'w', encoding='utf-8'), ensure_ascii=False)
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
    try: return json.load(open(GECMIS_D, "r", encoding="utf-8")) if os.path.exists(GECMIS_D) else {}
    except Exception: return {}


@app.route("/apple_giris")
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
    if "127.0.0.1" not in kok and "localhost" not in kok and kok.startswith("http://"):
        kok = "https://" + kok[7:]
    redirect_uri = kok + "/google_callback"
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
        if "127.0.0.1" not in kok and "localhost" not in kok and kok.startswith("http://"):
            kok = "https://" + kok[7:]
        redirect_uri = kok + "/google_callback"
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
        kisa = ep.split("@") if "@" in ep else ep
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

@app.route("/gecmis_yukle/<gid>")
def gecmis_yukle(gid):
    sahip = session.get("uye_eposta")
    if not sahip: return redirect("/")
    for it in _gecmis().get(sahip, []):
        if it.get("id") == gid and session.get("sid"):
            SOHBET_DEPO[session["sid"]] = list(it.get("mesajlar", []))
    return redirect("/")

@app.route("/paketler", methods=["GET", "POST"])
def paketler():
    mesaj = None
    if request.method == "POST":
        adet = int(request.form.get("adet", 0))
        if adet > 0:
            session["ek_soru_hakki"] = session.get("ek_soru_hakki", 0) + adet
            mesaj = f"✅ Paket tanımlandı! Mevcut ek soru bakiyeniz: {session['ek_soru_hakki']} Hak"
    return render_template("paketler.html", mesaj=mesaj)


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
        json.dump(g, open(GECMIS_D, "w", encoding="utf-8"), ensure_ascii=False)
    SOHBET_DEPO.clear()
    return redirect("/")


@app.route("/gizlilik")
def gizlilik():
    return "<h2>Modus Operandi ai — Gizlilik Politikası</h2><p>Kullanıcı bilgileri yalnızca oturum açma ve sohbet geçmişini saklama amacıyla kullanılır; üçüncü taraflarla paylaşılmaz.</p>"

if __name__ == '__main__':
    kitaplari_indeksle()
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
