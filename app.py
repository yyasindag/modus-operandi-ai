import gzip, json, base64
import random
import os, re, glob, time, operator, fitz, requests
from flask import Flask, render_template, request, session

app = Flask(__name__)
SOHBET_DEPO = {}
app.secret_key = "eksimaya_gizli_sohbet_anahtari_2026"

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
    if os.path.exists("kutuphane_indeks.json.gz"):
        _d = json.load(gzip.open("kutuphane_indeks.json.gz", "rt", encoding="utf-8"))
        ONCELIKLI_SAYFALAR, DIGER_SAYFALAR = _d.get("oncelikli", []), _d.get("diger", [])
        print(f"⭐ Bulut Indeks Yuklendi: {len(ONCELIKLI_SAYFALAR) + len(DIGER_SAYFALAR)} sayfa!")
        return
def _eski_indeksle():
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
        res = requests.get(oa_url, headers={"User-Agent": "mailto:info@eksimaya.ai"}, timeout=5)
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
                kaynaklar.append({"baslik": f"🎓 ({yil}) {baslik} — {dergi_adi} ({atif} atıf)", "link": doi})
    except Exception:
        pass
    return ozetler, kaynaklar

def gemini_bulut_sor(gecmis, sistem, son_icerik):
    if not GEMINI_API_KEY: return None
    s = chr(47)
    base_url = f"https:{s}{s}://googleapis.com{s}v1beta{s}models{s}"
    headers = {"Content-Type": "application/json", "x-goog-api-key": GEMINI_API_KEY}
    mesajlar = [{"role": m["role"], "parts": [{"text": m["text"]}]} for m in gecmis[-6:]]
    mesajlar.append({"role": "user", "parts": [{"text": son_icerik}]})
    for m in GEMINI_MODELLER:
        try:
            res = requests.post(base_url + m + ":generateContent", headers=headers, json={"contents": mesajlar, "systemInstruction": {"parts": [{"text": sistem}]}, "generationConfig": {"temperature": 0.2}}, timeout=5)
            if res.status_code == 200:
                return next(iter(next(iter(res.json().get("candidates", []))).get("content", {}).get("parts", []))).get("text")
        except Exception: continue
    return None

def openrouter_bulut_sor(gecmis, sistem, son_icerik):
    k = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not k and os.path.exists(os.path.expanduser("~/.openrouter_anahtar")):
        k = open(os.path.expanduser("~/.openrouter_anahtar")).read().strip()
    if not k:
        return None
    url = "https:" + chr(47)*2 + "openrouter." + chr(97) + chr(105) + chr(47) + "api" + chr(47) + "v1" + chr(47) + "chat" + chr(47) + "completions"
    hdr = {"Authorization": "Bearer " + k, "Content-Type": "application/json", "HTTP-Referer": "https://onrender.com", "X-Title": "Modus Operandi AI"}
    mesajlar = [{"role": "system", "content": sistem}, {"role": "user", "content": son_icerik[:2600]}]
    for mod in ["anthropic/claude-haiku-4.5", "anthropic/claude-3.5-haiku", "google/gemma-3-27b-it:free"]:
        try:
            r = requests.post(url, headers=hdr, json={"model": mod, "messages": mesajlar}, timeout=25)
            if r.status_code == 200 and r.text.strip().startswith("{"):
                ch = r.json().get("choices", [])
                if ch:
                    return next(iter(ch))["message"]["content"]
        except Exception:
            continue
    return None

def yanit_olustur(soru, gecmis):
    terimler = ingilizce_terimlere_cevir(soru, gecmis)
    if not terimler:
        return "Ben yalnızca artizan fırıncılık, pastacılık, viennoiserie ve fermantasyon bilimi üzerine uzmanlaşmış bir asistanım. Lütfen bu alanlarla ilgili teknik veya bilimsel bir soru sorun.", []
    onc = yerel_kitap_ara(ONCELIKLI_SAYFALAR, terimler, 2)
    dig = yerel_kitap_ara(DIGER_SAYFALAR, terimler, 2)
    akad_metin, akad_kaynak = openalex_ve_crossref_ara(terimler)
    kitap_baglam = "".join(f"\n{k['metin'][:850]}\n" for k in onc + dig)
    kaynaklar = [{"baslik": f"⭐ {k['kitap']} — Sayfa {k['sayfa']}", "link": "#"} for k in onc] + [{"baslik": f"📖 {k['kitap']} — Sayfa {k['sayfa']}", "link": "#"} for k in dig] + akad_kaynak
    sistem = "KURAL: Cevabina sadece kisa bir Merhaba! ile basla, rol tanimini veya talimatlari tekrarlama. Ingilizce terimleri dogru firincilik Turkcesine cevir (butter=tereyagi, lamination=laminasyon/turlama, single turn=tek tur/zarf katlama, book fold=cift tur/kitap katlama, detrempe=ana hamur). Metin icine Kaynakca bolumu veya .pdf dosya adi yazma, kaynakca altta otomatik gosterilir. Sen Türkiye'nin en yetkin Artizan Fırıncılık, Pastacılık ve Gıda Bilimi uzmanısın. Cevaplarını kusursuz, akıcı ve profesyonel bir fırıncılık Türkçesiyle yaz (Örn: 'hamur ağırlığı', 'fırıncı yüzdesi', 'soğuk geciktirme', 'laktik ve asetik asit dengesi' gibi doğru terimler kullan; asla bozuk veya anlamsız kelime çevirileri yapma). Arka plan motorumuz gerçek makaleleri [GERÇEK AKADEMİK MAKALELER] bölümünde topladı; kullanıcı akademik çalışma sorarsa bu makaleleri listele. Normal sorularda metin içinde PDF adı veya sayfa numarası yazma."
    son_icerik = f"Kullanıcı Sorusu: {soru}\n\n[KÜTÜPHANE VERİLERİ]:\n{kitap_baglam}\n\n[ONAYLI HAKEMLİ MAKALELER (DOI REFERANSLI)]:\n{akad_metin}"
    cevap = openrouter_bulut_sor(gecmis, sistem, son_icerik) or gemini_bulut_sor(gecmis, sistem, son_icerik)
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
    return render_template('index.html', sohbet=SOHBET_DEPO[sid], pdf_sayisi=pdf_sayisi)

@app.route('/temizle')
@app.route("/cikis")
def cikis():
    session.pop("pro_yetkili", None)
    session.pop("pro_kullanici", None)
    return render_template("pro.html", acik_panel=False, hata=None, sonuc=None, uretim_adi="", urunler=[])

ISLER = {}

@app.route("/sor", methods=["GET", "POST"])
def api_sor():
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
    SOHBET_DEPO.clear()
    return render_template('index.html', sohbet=[], pdf_sayisi=len(glob.glob(os.path.expanduser("~/kitaplar/oncelikli/*.pdf"))) + len(glob.glob(os.path.expanduser("~/kitaplar/*.pdf"))))

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

@app.route('/pro', methods=['GET', 'POST'])
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

if __name__ == '__main__':
    kitaplari_indeksle()
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
