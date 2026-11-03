"""Kuesioner validasi guru (Tahap 2): jawaban tanpa vs dengan kontrol keterbacaan.

Setiap soal (data/qa/Soal_Validasi_Guru.csv: 30 PJOK + 30 Pancasila, 5 per kelas, buku
Kurikulum Merdeka) dijawab sistem lengkap S4 (adapter + buku). Dari satu jawaban diambil:
    tanpa kontrol  = jawaban putaran 1 (Act Agent, sebelum Reflect Agent menilai PKR/KLD)
    dengan kontrol = jawaban akhir sesudah kontrol keterbacaan (paling banyak 3 putaran)
Label tetap: A = tanpa kontrol, B = dengan kontrol, dan hal ini dijelaskan di petunjuk. Guru
menilai keduanya pada skala 1-4: ketepatan isi, kesesuaian bahasa dengan kelas, dan kejelasan,
lalu memilih yang lebih cocok dan memberi komentar. Lembar tersembunyi "Kunci" menyimpan ukuran
keterbacaan dan status sistem untuk peneliti.

Suntingan manual ejaan (dicatat di lembar Kunci, kolom disunting_manual):
    python -m tb.kuesioner_guru sunting --dasar hasil/kuesioner_guru/jawaban_sistem.ejaan_rusak.json

Soal yang ditolak sistem dapat diganti soal buku Merdeka lain dari mapel dan kelas yang sama:
    python -m tb.kuesioner_guru ganti --server https://xxxx.trycloudflare.com --no 3 7 34

Langkah 1, ke server yang menjalankan Qwen (Pegasus, atau langsung ke tautan Kaggle; kunci
server diambil dari TB_KUNCI). Bila terputus, jalankan ulang: soal yang sudah terjawab dilewati.
    python -m tb.kuesioner_guru ambil --server http://127.0.0.1:8000
    $env:TB_KUNCI = "<kunci>"; python -m tb.kuesioner_guru ambil --server https://xxxx.trycloudflare.com
Langkah 2, di laptop (PDF dibuat lewat Microsoft Word):
    python -m tb.kuesioner_guru buat --folder D:\\Skripsi\\UAT\\Kuesioner_Validasi_Guru
"""
from __future__ import annotations

import argparse
import json
import os
import random

AKAR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOAL = os.path.join(AKAR, "data", "qa", "Soal_Validasi_Guru.csv")
HASIL = os.path.join(AKAR, "hasil", "kuesioner_guru")
NAMA_MAPEL = {"PJOK": "PJOK", "PKN": "Pendidikan Pancasila"}
SKALA = {
    "isi": ("Ketepatan isi", "1 = salah, 2 = sebagian benar, 3 = benar tetapi kurang lengkap, "
                             "4 = benar dan lengkap"),
    "bahasa": ("Kesesuaian bahasa dengan siswa kelas tersebut", "1 = sangat tidak sesuai, "
               "2 = kurang sesuai, 3 = sesuai, 4 = sangat sesuai"),
    "jelas": ("Kejelasan: siswa dapat memahami sendiri tanpa dijelaskan ulang",
              "1 = sangat sulit dipahami, 2 = sulit, 3 = mudah, 4 = sangat mudah dipahami"),
}
PILIHAN = ["A", "B", "Sama baiknya"]
LABEL_PENDEK = ["Ketepatan isi", "Kesesuaian bahasa", "Kejelasan"]


# ------------------------------------------------------------------ langkah 1: ambil
def muat_soal() -> list[dict]:
    import pandas as pd
    return pd.read_csv(SOAL, encoding="utf-8").to_dict("records")


def _ringkas(no: int, s: dict, h: dict) -> dict:
    riwayat = h.get("riwayat") or []
    awal = riwayat[0] if riwayat else {}
    kon = h.get("konteks") or {}
    return {**s, "no": int(no), "status": h.get("status"), "putaran": h.get("putaran"),
            "tanpa_kontrol": awal.get("jawaban") or h.get("jawaban"),
            "dengan_kontrol": h.get("jawaban"),
            "ukuran_tanpa": awal.get("ukuran"), "lolos_tanpa": awal.get("lolos_keterbacaan"),
            "ukuran_dengan": h.get("ukuran"), "lolos_dengan": h.get("lolos"),
            "sasaran": h.get("sasaran"), "buku": kon.get("buku"), "halaman": kon.get("halaman")}


def _penanya(server: str | None, tiruan: bool):
    """Fungsi tanya(soal) -> hasil sistem S4 (kelas dari data, tanpa tanya balik)."""
    if tiruan:                              # hanya untuk mencoba bentuk berkas, tanpa GPU
        from .agen import Sistem
        from .keterbacaan import KontrolKeterbacaan
        from .model import ModelTiruan
        from .pencarian import PencariBM25
        from .server import ringkas
        sistem = Sistem(ModelTiruan(("PJOK", "PKN")), PencariBM25(), KontrolKeterbacaan.muat())
        tanya = lambda s: ringkas(sistem.tanya(s["pertanyaan"], s["mapel"], int(s["kelas"]),
                                               "S4", interaktif=False))
    else:
        import getpass
        import httpx
        klien = httpx.Client(base_url=server.rstrip("/"), timeout=900,
                             headers={"X-Kunci": os.environ.get("TB_KUNCI", "")})
        if klien.get("/api/saya").json().get("login_aktif"):
            print("Server memakai login. Masuk dengan akun peneliti:")
            r = klien.post("/api/masuk", json={"identitas": input("  username atau email: "),
                                               "password": getpass.getpass("  password: ")})
            if r.status_code != 200:
                raise SystemExit(f"gagal masuk: {r.text}")

        def tanya(s):
            r = klien.post("/api/tanya", json={"pertanyaan": s["pertanyaan"], "mata_pelajaran": s["mapel"],
                                               "kelas": int(s["kelas"]), "skenario": "S4",
                                               "interaktif": False})
            r.raise_for_status()
            return r.json()
    return tanya


def ambil(server: str | None, keluar: str, tiruan: bool = False, ulang: bool = False) -> str:
    """Menanyakan semua soal ke sistem (S4, kelas dari data, tanpa tanya balik).
    Jawaban yang sudah tersimpan di `keluar` (dari model yang sama) dipakai ulang, kecuali
    `ulang`: berkas lama disimpan sebagai *.lama.json lalu semua soal ditanyakan lagi."""
    soal = muat_soal()
    lama = {}
    if ulang and os.path.exists(keluar):
        os.replace(keluar, os.path.splitext(keluar)[0] + ".lama.json")
    if os.path.exists(keluar):
        with open(keluar, encoding="utf-8") as f:
            lama = {d["no"]: d for d in json.load(f)
                    if d.get("tiruan", False) == tiruan and d.get("dengan_kontrol")}
        if lama:
            print(f"melanjutkan: {len(lama)} soal sudah terjawab di {keluar}")
    hasil = []
    tanya = _penanya(server, tiruan)
    os.makedirs(os.path.dirname(keluar), exist_ok=True)
    for i, s in enumerate(soal, 1):
        if int(s["no"]) in lama:
            hasil.append(lama[int(s["no"])])
            continue
        h = tanya(s)
        hasil.append({**_ringkas(s["no"], s, h), "tiruan": tiruan})
        sama = hasil[-1]["tanpa_kontrol"] == hasil[-1]["dengan_kontrol"]
        print(f"[{i}/{len(soal)}] {s['mapel']} k{s['kelas']} {h.get('status')}, "
              f"putaran {h.get('putaran')}{' (A=B)' if sama else ''}", flush=True)
        with open(keluar, "w", encoding="utf-8") as f:   # disimpan tiap soal: aman bila terputus
            json.dump(hasil, f, ensure_ascii=False, indent=1)
    return keluar


GAGAL = {"tolak", "tidak_ada_materi"}       # sistem tidak menjawab isi pertanyaan
CADANGAN = {"PJOK": os.path.join(AKAR, "data", "qa", "Validasi_Soal_PJOK.xlsx"),
            "PKN": os.path.join(AKAR, "data", "qa", "Soal_PKN_Merdeka.xlsx")}


def muat_cadangan(mapel: str, kelas: int) -> list[dict]:
    """Soal buku Merdeka lain untuk mapel dan kelas yang sama (lembar 'Kelas k')."""
    import pandas as pd
    df = pd.read_excel(CADANGAN[mapel], sheet_name=f"Kelas {kelas}")
    return [{"pertanyaan": r["pertanyaan"], "kunci_buku": r["jawaban (kutipan buku)"],
             "sumber": f"Merdeka hal.{r['halaman buku (tercetak)']}"}
            for _, r in df.iterrows() if isinstance(r["pertanyaan"], str)]


def ganti(server: str, keluar: str, nomor: list[int], coba: int = 8, seed: int = 2026) -> str:
    """Mengganti soal bernomor `nomor` dengan soal lain dari mapel dan kelas yang sama.
    Soal pengganti tidak boleh ditolak sistem; dari paling banyak `coba` calon dipilih yang
    pertama dengan jawaban A berbeda dari B, kalau tidak ada dipakai calon pertama yang terjawab.
    Soal_Validasi_Guru.csv dan berkas jawaban ikut diperbarui."""
    import pandas as pd
    soal = pd.read_csv(SOAL, encoding="utf-8")
    with open(keluar, encoding="utf-8") as f:
        hasil = {d["no"]: d for d in json.load(f)}
    tanya = _penanya(server, False)
    rng = random.Random(seed)
    for no in nomor:
        s = soal.loc[soal["no"] == no].iloc[0].to_dict()
        dipakai = set(soal["pertanyaan"])
        calon = [c for c in muat_cadangan(s["mapel"], int(s["kelas"])) if c["pertanyaan"] not in dipakai]
        rng.shuffle(calon)
        cadang = None
        for c in calon[:coba]:
            baru = {**s, **c}
            h = _ringkas(no, baru, tanya(baru))
            sama = h["tanpa_kontrol"] == h["dengan_kontrol"]
            print(f"  no {no}: {h['status']}{' (A=B)' if sama else ''}  {c['pertanyaan'][:60]}", flush=True)
            if h["status"] in GAGAL:
                continue
            cadang = cadang or h
            if not sama:
                cadang = h
                break
        if not cadang:
            print(f"no {no}: tidak ada pengganti yang terjawab dari {coba} calon, soal lama dipertahankan")
            continue
        hasil[no] = {**cadang, "tiruan": False}
        for k in ("pertanyaan", "kunci_buku", "sumber"):
            soal.loc[soal["no"] == no, k] = cadang[k]
        print(f"no {no} diganti: {cadang['pertanyaan']}", flush=True)
        soal.to_csv(SOAL, index=False, encoding="utf-8")
        with open(keluar, "w", encoding="utf-8") as f:
            json.dump([hasil[k] for k in sorted(hasil)], f, ensure_ascii=False, indent=1)
    return keluar


def sunting(dasar: str, berkas: str, keluar: str) -> str:
    """Menerapkan suntingan manual (ejaan, aksara asing, kata rusak) dari `berkas`
    {"no": {"A": ..., "B": ..., "catatan": ...}} ke jawaban `dasar`. Teks asli sistem disimpan
    di tanpa_kontrol_sistem/dengan_kontrol_sistem dan ikut tercatat di lembar Kunci."""
    with open(dasar, encoding="utf-8") as f:
        data = json.load(f)
    with open(berkas, encoding="utf-8") as f:
        ubah = json.load(f)
    for d in data:
        e = ubah.get(str(d["no"]))
        if not e:
            continue
        asli_a, asli_b = d["tanpa_kontrol"], d["dengan_kontrol"]
        d["tanpa_kontrol_sistem"], d["dengan_kontrol_sistem"] = asli_a, asli_b
        d["tanpa_kontrol"] = e.get("A", asli_a)
        # jawaban B yang sama persis dengan A ikut suntingan A
        d["dengan_kontrol"] = e.get("B", d["tanpa_kontrol"] if asli_a.strip() == asli_b.strip() else asli_b)
        d["disunting"] = "".join(k for k, a, b in (("A", asli_a, d["tanpa_kontrol"]),
                                                     ("B", asli_b, d["dengan_kontrol"])) if a != b)
        d["catatan_suntingan"] = e.get("catatan", "perbaikan ejaan/aksara")
    with open(keluar, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print(f"{sum(bool(d.get('disunting')) for d in data)} soal disunting -> {keluar}")
    return keluar


# ------------------------------------------------------------------ langkah 2: buat
def beri_label(data: list[dict]) -> list[dict]:
    """A = jawaban umum tanpa kontrol keterbacaan, B = jawaban dengan kontrol keterbacaan.
    Label tetap (tidak diacak) dan dijelaskan di petunjuk, sesuai keputusan peneliti."""
    return [{**d, "A": d["tanpa_kontrol"], "B": d["dengan_kontrol"], "A_adalah": "tanpa kontrol"}
            for d in data]


def buat_excel(data: list[dict], path: str) -> str:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, Side
    from openpyxl.worksheet.datavalidation import DataValidation

    wb = Workbook()
    tipis = Side(style="thin", color="BFBFBF")
    kotak = Border(left=tipis, right=tipis, top=tipis, bottom=tipis)
    bungkus = Alignment(wrap_text=True, vertical="top")

    # --- petunjuk
    ws = wb.active
    ws.title = "Petunjuk"
    baris = [
        ("Validasi Guru: Jawaban Asisten Pembelajaran Learning Buddy", True),
        ("", False),
        ("Identitas penilai (isi pada kolom B)", True),
        ("Nama lengkap", False), ("Sekolah", False), ("Mata pelajaran yang diampu", False),
        ("Kelas yang diampu", False), ("Lama mengajar di SD", False),
        ("Buku pelajaran yang dipakai di sekolah", False),
        ("", False),
        ("Petunjuk", True),
        ("1. Setiap baris berisi satu pertanyaan siswa SD beserta dua jawaban dari sistem untuk siswa kelas "
         "yang tertulis. Jawaban A adalah jawaban umum tanpa kontrol keterbacaan. Jawaban B adalah jawaban "
         "yang sudah melalui kontrol keterbacaan, yaitu diperiksa panjang kalimat dan kata sulitnya, lalu "
         "ditulis ulang bila belum sesuai kelas. Bila sudah sesuai sejak awal, B sama dengan A.", False),
        ("2. Bayangkan jawaban dibaca sendiri oleh siswa kelas tersebut, tanpa didampingi guru.", False),
        ("3. Beri nilai 1-4 untuk setiap jawaban pada tiga aspek (kolom nilai, pilih angka dari daftar):", False),
        *[(f"   - {nama}: {ket}", False) for nama, ket in SKALA.values()],
        ("4. Pilih jawaban yang menurut Bapak/Ibu lebih cocok untuk siswa kelas tersebut: A, B, atau "
         "Sama baiknya. Bila kedua jawaban sama persis, pilih Sama baiknya.", False),
        ("5. Komentar boleh diisi bila ada bagian yang salah, sulit dipahami, atau saran perbaikan.", False),
        ("6. Soal disusun dari buku Kurikulum Merdeka terbitan Kemendikbud. Mohon nilai kebenaran isi "
         "menurut materi Capaian Pembelajaran, walaupun sekolah memakai buku penerbit lain.", False),
        ("", False),
        ("Terima kasih atas kesediaan Bapak/Ibu.", False),
    ]
    for i, (t, tebal) in enumerate(baris, 1):
        c = ws.cell(i, 1, t)
        c.font = Font(bold=tebal, size=13 if i == 1 else 11)
        c.alignment = Alignment(wrap_text=True, vertical="top")
        if 4 <= i <= 9:                     # kotak isian identitas (tanpa warna)
            ws.cell(i, 2).border = kotak
    ws.column_dimensions["A"].width = 95
    ws.column_dimensions["B"].width = 40

    # --- lembar penilaian per mapel
    kolom = [("No", 5), ("Kelas", 6), ("Pertanyaan siswa", 30), ("Jawaban A", 48),
             ("A: Ketepatan isi (1-4)", 11), ("A: Kesesuaian bahasa (1-4)", 11),
             ("A: Kejelasan (1-4)", 11), ("Jawaban B", 48), ("B: Ketepatan isi (1-4)", 11),
             ("B: Kesesuaian bahasa (1-4)", 11), ("B: Kejelasan (1-4)", 11),
             ("Lebih cocok untuk kelas tsb.", 14), ("Komentar (opsional)", 40)]
    for mapel in ("PJOK", "PKN"):
        ws = wb.create_sheet("PJOK" if mapel == "PJOK" else "Pancasila")
        for j, (nama, lebar) in enumerate(kolom, 1):
            c = ws.cell(1, j, nama)
            c.font, c.border = Font(bold=True), kotak
            c.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")
            ws.column_dimensions[c.column_letter].width = lebar
        ws.row_dimensions[1].height = 45
        dv_skala = DataValidation(type="list", formula1='"1,2,3,4"', allow_blank=True)
        dv_pilih = DataValidation(type="list", formula1='"' + ",".join(PILIHAN) + '"', allow_blank=True)
        ws.add_data_validation(dv_skala)
        ws.add_data_validation(dv_pilih)
        n = 0
        for d in data:
            if d["mapel"] != mapel:
                continue
            n += 1
            r = n + 1
            nilai = [n, int(d["kelas"]), d["pertanyaan"], d["A"], None, None, None, d["B"],
                     None, None, None, None, None]
            for j, v in enumerate(nilai, 1):
                c = ws.cell(r, j, v)
                c.alignment, c.border = bungkus, kotak
            for j in (5, 6, 7, 9, 10, 11):
                dv_skala.add(ws.cell(r, j))
            dv_pilih.add(ws.cell(r, 12))
            panjang = max(len(str(d["A"] or "")), len(str(d["B"] or "")))
            ws.row_dimensions[r].height = max(45, 15 * (panjang // 42 + 1))
        ws.freeze_panes = "D2"

    # --- kunci untuk peneliti (disembunyikan dari guru)
    ws = wb.create_sheet("Kunci")
    kep = ["mapel", "no_lembar", "no_soal", "kelas", "pertanyaan", "A_adalah", "tanpa_kontrol",
           "dengan_kontrol", "sama_persis", "status", "putaran", "pkr_tanpa", "kld_tanpa",
           "lolos_tanpa", "pkr_dengan", "kld_dengan", "lolos_dengan", "maks_pkr", "maks_kld",
           "buku", "halaman", "kunci_buku", "sumber_soal", "disunting_manual",
           "tanpa_kontrol_sistem", "dengan_kontrol_sistem", "catatan_suntingan"]
    ws.append(kep)
    for mapel in ("PJOK", "PKN"):
        for n, d in enumerate([x for x in data if x["mapel"] == mapel], 1):
            ut, ud, sas = d.get("ukuran_tanpa") or {}, d.get("ukuran_dengan") or {}, d.get("sasaran") or {}
            ws.append([mapel, n, d["no"], int(d["kelas"]), d["pertanyaan"], d["A_adalah"],
                       d["tanpa_kontrol"], d["dengan_kontrol"], d["tanpa_kontrol"] == d["dengan_kontrol"],
                       d.get("status"), d.get("putaran"), ut.get("pkr"), ut.get("kld"), d.get("lolos_tanpa"),
                       ud.get("pkr"), ud.get("kld"), d.get("lolos_dengan"), sas.get("maks_pkr"),
                       sas.get("maks_kld"), d.get("buku"), d.get("halaman"), d.get("kunci_buku"),
                       d.get("sumber"), d.get("disunting") or "", d.get("tanpa_kontrol_sistem"),
                       d.get("dengan_kontrol_sistem"), d.get("catatan_suntingan")])
    ws.sheet_state = "veryHidden"
    wb.save(path)
    return path


def buat_docx(data: list[dict], path: str, mapel: str) -> str:
    """Versi cetak: satu kartu per soal, kotak centang 1-4 untuk A dan B di kolom terpisah."""
    from docx import Document
    from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Cm, Pt

    doc = Document()
    sek = doc.sections[0]
    sek.page_width, sek.page_height = Cm(21), Cm(29.7)
    for sisi in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
        setattr(sek, sisi, Cm(1.8))
    gaya = doc.styles["Normal"]
    gaya.font.name, gaya.font.size = "Calibri", Pt(11)
    gaya.element.rPr.rFonts.set(qn("w:eastAsia"), "Calibri")

    def paragraf(teks, tebal=False, ukuran=11, sesudah=4):   # semua teks hitam
        p = doc.add_paragraph()
        r = p.add_run(teks)
        r.bold, r.font.size = tebal, Pt(ukuran)
        p.paragraph_format.space_after = Pt(sesudah)
        return p

    nama = NAMA_MAPEL[mapel]
    paragraf(f"Validasi Guru: Soal dan Jawaban Learning Buddy ({nama})", True, 16)
    paragraf("")
    for label, titik in (("Nama", 40), ("Sekolah", 40), ("Tingkat kelas yang diajari", 25),
                         ("Lama mengajar", 25), ("Buku yang dipakai (penerbit)", 24)):
        paragraf(f"{label} : " + "." * titik, sesudah=2)
    paragraf("")
    paragraf("Petunjuk", True, 12)
    for t in ["Setiap kartu berisi satu pertanyaan siswa dan dua jawaban dari sistem untuk siswa kelas yang "
              "tertulis. Bayangkan jawaban dibaca sendiri oleh siswa tersebut tanpa didampingi guru.",
              "Jawaban A = jawaban umum tanpa kontrol keterbacaan. Jawaban B = jawaban yang sudah melalui "
              "kontrol keterbacaan (panjang kalimat dan kata sulit diperiksa, lalu ditulis ulang bila belum "
              "sesuai kelas). Bila jawaban A sudah sesuai kelas sejak awal, jawaban B sama dengan A.",
              "Untuk setiap kriteria, centang satu kotak nilai 1-4 di kolom Jawaban A dan satu kotak di kolom "
              "Jawaban B:",
              *[f"• {n}: {k}" for n, k in SKALA.values()],
              "Pilih jawaban yang lebih cocok untuk siswa kelas tersebut (A, B, atau Sama baiknya), dan tulis "
              "komentar bila ada.",
              "Soal disusun dari buku Kurikulum Merdeka (Kemendikbud). Mohon nilai kebenaran isi menurut materi "
              "Capaian Pembelajaran, walaupun sekolah memakai buku penerbit lain."]:
        paragraf(t, ukuran=10, sesudah=2)

    def isi(sel, teks, tebal=False, ukuran=10, tengah=False):
        sel.text = ""
        p = sel.paragraphs[0]
        r = p.add_run(teks)
        r.bold, r.font.size = tebal, Pt(ukuran)
        if tengah:
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        sel.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
        return sel

    # kolom 0 = kriteria, kolom 1-4 = nilai 1-4 jawaban A, kolom 5-8 = nilai 1-4 jawaban B,
    # sehingga setiap kotak centang punya sel sendiri dan sejajar dari baris ke baris
    lebar = [Cm(7.0)] + [Cm(1.25)] * 8
    for n, d in enumerate([x for x in data if x["mapel"] == mapel], 1):
        doc.add_paragraph().paragraph_format.space_after = Pt(2)
        t = doc.add_table(rows=10, cols=9)
        t.style = "Table Grid"
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        t.autofit = False
        tata = OxmlElement("w:tblLayout")
        tata.set(qn("w:type"), "fixed")
        t._tbl.tblPr.append(tata)
        for kol, w in zip(t.columns, lebar):
            kol.width = w
        kepala = t.cell(0, 0).merge(t.cell(0, 8))
        kepala.text = ""
        r = kepala.paragraphs[0].add_run(f"No. {n}  ·  Kelas {int(d['kelas'])}  ·  Pertanyaan: ")
        r.bold = True
        kepala.paragraphs[0].add_run(d["pertanyaan"])
        for i, lab in ((1, "A"), (2, "B")):
            sel = t.cell(i, 0).merge(t.cell(i, 8))
            sel.text = ""
            sel.paragraphs[0].add_run(f"Jawaban {lab}:  ").bold = True
            sel.paragraphs[0].add_run(str(d[lab] or "(tidak ada jawaban)"))
        isi(t.cell(3, 0), "Kriteria", True)
        isi(t.cell(4, 0), "")
        for awal, lab in ((1, "A"), (5, "B")):
            isi(t.cell(3, awal).merge(t.cell(3, awal + 3)), f"Nilai Jawaban {lab}", True, 9, True)
            for k in range(4):
                isi(t.cell(4, awal + k), str(k + 1), True, 9, True)
                for i in range(3):
                    isi(t.cell(5 + i, awal + k), "☐", ukuran=13, tengah=True)
        for i, label in enumerate(LABEL_PENDEK):
            isi(t.cell(5 + i, 0), label)
        isi(t.cell(8, 0), "Lebih cocok untuk kelas ini")
        for (a, b), teks in (((1, 3), "☐  A"), ((4, 6), "☐  B"), ((7, 8), "☐  Sama")):
            isi(t.cell(8, a).merge(t.cell(8, b)), teks, ukuran=11, tengah=True)
        komen = t.cell(9, 0).merge(t.cell(9, 8))
        isi(komen, "Komentar:", ukuran=10)
        komen.vertical_alignment = WD_ALIGN_VERTICAL.TOP
        for _ in range(4):          # ruang menulis komentar
            komen.add_paragraph()
        for baris in t.rows:
            for sel, w in zip(baris.cells, lebar):
                sel.width = w
        # kartu tidak terpotong antarhalaman
        for baris in t.rows:
            trpr = baris._tr.get_or_add_trPr()
            cs = OxmlElement("w:cantSplit"); trpr.append(cs)
            for sel in baris.cells:
                for p in sel.paragraphs:
                    p.paragraph_format.keep_with_next = True
    doc.save(path)
    return path


def ke_pdf(docx: str) -> str | None:
    """PDF lewat Microsoft Word (Windows). Tanpa Word, berkas .docx tetap bisa dicetak."""
    pdf = os.path.splitext(docx)[0] + ".pdf"
    try:
        import win32com.client                                   # type: ignore
        w = win32com.client.Dispatch("Word.Application")
        d = w.Documents.Open(os.path.abspath(docx), False, True)
        d.ExportAsFixedFormat(os.path.abspath(pdf), 17)
        d.Close(False)
        w.Quit()
        return pdf
    except Exception:
        import subprocess
        cmd = (f"$w = New-Object -ComObject Word.Application; $d = $w.Documents.Open('{os.path.abspath(docx)}', "
               f"$false, $true); $d.ExportAsFixedFormat('{os.path.abspath(pdf)}', 17); $d.Close($false); "
               "try {{ $w.Quit() }} catch {{}}")
        r = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True)
        return pdf if r.returncode == 0 and os.path.exists(pdf) else None


def buat(sumber: str, folder: str = HASIL) -> list[str]:
    with open(sumber, encoding="utf-8") as f:
        data = beri_label(json.load(f))
    if any(d.get("tiruan") for d in data):
        print("PERINGATAN: jawaban berasal dari model tiruan (salinan kalimat buku), bukan Qwen.")
    os.makedirs(folder, exist_ok=True)
    keluar = [buat_excel(data, os.path.join(folder, "Kuesioner_Validasi_Guru.xlsx"))]
    for mapel, nama in (("PJOK", "PJOK"), ("PKN", "Pancasila")):
        dx = buat_docx(data, os.path.join(folder, f"Kuesioner_Validasi_Guru_{nama}.docx"), mapel)
        keluar.append(dx)
        pdf = ke_pdf(dx)
        if pdf:
            keluar.append(pdf)
    return keluar


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="langkah", required=True)
    a = sub.add_parser("ambil", help="tanyakan 60 soal ke sistem dan simpan jawabannya")
    a.add_argument("--server", default="http://127.0.0.1:8000")
    a.add_argument("--tiruan", action="store_true", help="model tiruan di laptop (uji bentuk berkas)")
    a.add_argument("--keluar", default=os.path.join(HASIL, "jawaban_sistem.json"))
    a.add_argument("--ulang", action="store_true", help="tanyakan semua soal lagi (sistem sudah diubah)")
    g = sub.add_parser("ganti", help="ganti soal tertentu dengan soal lain dari mapel dan kelas yang sama")
    g.add_argument("--server", required=True)
    g.add_argument("--no", type=int, nargs="+", required=True, help="nomor soal (1-60) yang diganti")
    g.add_argument("--coba", type=int, default=8, help="paling banyak calon yang ditanyakan per soal")
    g.add_argument("--keluar", default=os.path.join(HASIL, "jawaban_sistem.json"))
    s = sub.add_parser("sunting", help="terapkan suntingan manual ejaan ke jawaban sistem")
    s.add_argument("--dasar", required=True, help="berkas jawaban sistem yang disunting")
    s.add_argument("--berkas", default=os.path.join(HASIL, "suntingan_manual.json"))
    s.add_argument("--keluar", default=os.path.join(HASIL, "jawaban_sistem.json"))
    b = sub.add_parser("buat", help="buat Excel dan PDF kuesioner dari jawaban yang sudah diambil")
    b.add_argument("--sumber", default=os.path.join(HASIL, "jawaban_sistem.json"))
    b.add_argument("--folder", default=HASIL, help="folder tujuan Excel, docx, dan PDF")
    x = ap.parse_args()
    if x.langkah == "ambil":
        print("tersimpan:", ambil(x.server, x.keluar, x.tiruan, x.ulang))
    elif x.langkah == "ganti":
        print("tersimpan:", ganti(x.server, x.keluar, x.no, x.coba))
    elif x.langkah == "sunting":
        sunting(x.dasar, x.berkas, x.keluar)
    else:
        for p in buat(x.sumber, x.folder):
            print("tersimpan:", p)
