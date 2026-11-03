"""Mengambil potongan Recursive hasil Eksperimen_Chunking (korpus Merdeka) menjadi basis
pengetahuan website (data/potongan.jsonl).

Website memakai satu strategi, Recursive (500 karakter, tumpang 50). Pada 1.023 soal PJOK
Merdeka (Qwen3, tanpa reranker) Recursive memberi hit@1 tertinggi (0,794) dan hit@3 0,949;
karena itu setiap pertanyaan dijawab dengan 3 potongan teratas (tb.pencarian.KIRIM).
Strategi lain (mis. SDCS) dapat diimpor dengan --strategi untuk perbandingan.

Potongan dibuat oleh proyek ../Eksperimen_Chunking (eksperimen.chunking, korpus merdeka)
dari PDF yang sama dengan tb.korpus. Skrip ini menyalin, merapikan (rapikan()), dan
melengkapi metadata:
  halaman       nomor halaman PDF awal potongan (dimulai dari 1)
  halaman_buku  nomor halaman tercetak, dari eksperimen/soal/teks/<MAPEL>_K<k>.jsonl
  bab           judul bab halaman tersebut
  teks_indeks   teks yang disandikan (SDCS: judul bagian + isi), sama dengan eksperimen
  teks          teks yang dikirim ke Act Agent dan ditampilkan sebagai sumber jawaban

Perapian (hanya untuk website; potongan eksperimen tidak diubah):
  1. tumpang 50 karakter Recursive diambil per huruf, sehingga 1.678 dari 4.380 potongan
     (38%) diawali sisa kata ("ategi gerak ..."). Sisa kata itu dibuang: tumpang dimulai
     dari awal kata.
  2. kolofon buku yang lolos pembersihan halaman ("KEMENTERIAN PENDIDIKAN ... REPUBLIK
     INDONESIA, 2024 Pendidikan Jasmani ... untuk SD/MI Kelas II Penulis: ...") dibuang.
  3. teks hiasan berhuruf renggang ("U n i t P e m b e l a j a r a n", "B a b") dan
     kotak teka-teki huruf dibuang.
Potongan yang tersisa kurang dari POTONGAN_MIN karakter dibuang.

    python -m tb.impor_potongan
    python -m tb.impor_potongan --sumber D:/.../hasil/merdeka/draf/potongan
    python -m tb.impor_potongan --xlsx     # hasil/Potongan_Recursive_Rapi.xlsx untuk diperiksa
"""
from __future__ import annotations

import argparse
import json
import os
import re
from collections import Counter

AKAR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EKSPERIMEN = os.path.join(os.path.dirname(AKAR), "Eksperimen_Chunking", "eksperimen")
SUMBER = os.path.join(EKSPERIMEN, "hasil", "merdeka", "draf", "potongan")
TEKS_HALAMAN = os.path.join(EKSPERIMEN, "soal", "teks")
STRATEGI = ("Recursive",)
TUMPANG = 50            # tumpang Recursive di eksperimen.chunking.recursive
POTONGAN_MIN = 40

# Penulis pada kolofon 12 buku Merdeka (nama ditulis lengkap agar teks materi sesudahnya,
# mis. "Tujuan Pembelajaran", tidak ikut terbuang).
_PENULIS = (r"Agung Sudaryono, Puji Rahayu|Puji Rahayu,? (?:dan )?Umi Hariyani|"
            r"Muhajir dan Umi Hariyani|Febrian Dwi Cahyono dan Alda Indrawan|"
            r"Alda Indrawan dan Tri Agus Prasetijo|"
            r"Shoia Nurun Alanur S, Resha Hadi Sucipto, Soeharti|"
            r"Ressi K\. Dewi, Kamala R\. C\. Sary, dan Hani H\w*|"
            r"Mohamad Alwi Lutfi, Listia, dan Khristina Antariningsih")
_KOLOFON = re.compile(
    r"KEMENTERIAN PENDIDIKAN[A-Z ,]*REPUBLIK INDONESIA,?\s*(?:\d{4})?"
    r"(?:\s*Buku Panduan Guru)?"
    r"(?:\s*(?:Pendidikan Jasmani, Olahraga, dan Kesehatan|Pendidikan Pancasila)"
    r"(?:\s+untuk SD/MI Kelas [IVX]+)?)?"
    rf"(?:\s*Penulis\s*:\s*(?:{_PENULIS}))?")
_PENULIS_SAJA = re.compile(rf"Penulis\s*:\s*(?:{_PENULIS})")
# >= 4 huruf tunggal berturut-turut yang dipisah spasi: judul hias "U n i t ..." dan
# kotak teka-teki huruf; tidak ada pada kalimat materi
_RENGGANG = re.compile(r"\b(?:[A-Za-z] ){3,}[A-Za-z]\b")


def rapikan(potongan: list[dict], dibuang: list | None = None) -> tuple[list[dict], Counter]:
    """potongan: satu strategi, urutan asli berkas (per buku berurutan). Mengembalikan
    potongan yang sudah dirapikan (kolom "teks_asli" dan "perapian" ditambahkan) dan
    hitungan perubahan per aturan. dibuang (opsional) diisi potongan yang dibuang."""
    hitung, out, sebelum = Counter(), [], {}
    for p in potongan:
        t, kunci, aturan = p["teks"], (p["mapel"], int(p["kelas"])), []
        prev = sebelum.get(kunci)
        sebelum[kunci] = p["teks"]
        # 1. tumpang: bila teks diawali 50 karakter terakhir potongan sebelumnya dan
        #    karakter pertamanya berada di tengah kata, buang sampai spasi pertama
        if prev and len(prev) > TUMPANG:
            ekor = prev[-TUMPANG:]
            if t.startswith(ekor) and prev[-TUMPANG - 1].isalnum() and ekor[0].isalnum():
                spasi = t.find(" ")
                if 0 < spasi < TUMPANG:
                    t = t[spasi + 1:]
                    aturan.append("sisa kata di awal dibuang")
        # 2. kolofon, 3. huruf renggang
        t2 = _PENULIS_SAJA.sub(" ", _KOLOFON.sub(" ", t))
        if t2 != t:
            aturan.append("kolofon dibuang")
        t3 = _RENGGANG.sub(" ", t2)
        if t3 != t2:
            aturan.append("huruf renggang dibuang")
        t3 = re.sub(r"\s+", " ", t3).strip()
        hitung.update(aturan)
        if len(t3) < POTONGAN_MIN:
            hitung["potongan terlalu pendek dibuang"] += 1
            if dibuang is not None:
                dibuang.append({**p, "teks_asli": p["teks"], "teks": t3,
                                "perapian": aturan + ["terlalu pendek, dibuang"]})
            continue
        out.append({**p, "teks": t3, "teks_asli": p["teks"], "perapian": aturan})
    return out, hitung


def ekspor_xlsx(path: str | None = None, sumber: str = SUMBER,
                teks_halaman: str = TEKS_HALAMAN) -> str:
    """Seluruh potongan Recursive website (sesudah dirapikan) ke Excel untuk diperiksa:
    lembar Keterangan, Ringkasan, PJOK, PKN, dan Dibuang."""
    import pandas as pd
    from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
    from openpyxl.styles import Alignment, Font, PatternFill
    path = path or os.path.join(AKAR, "hasil", "Potongan_Recursive_Rapi.xlsx")
    peta = _peta_halaman(teks_halaman)
    with open(os.path.join(sumber, "Recursive.jsonl"), encoding="utf-8") as f:
        asli = [json.loads(b) for b in f]
    dibuang = []
    rapi, hitung = rapikan(asli, dibuang)

    def baris(p):
        hb, bab = peta.get((p["mapel"], int(p["kelas"]), int(p["halaman"])), (None, ""))
        return {"id": p["id"], "mapel": p["mapel"], "kelas": int(p["kelas"]),
                "halaman PDF": int(p["halaman"]), "halaman buku": hb, "bab": bab,
                "panjang (karakter)": len(p["teks"]), "jumlah kata": len(p["teks"].split()),
                "dirapikan": ", ".join(p["perapian"]) or "-",
                "teks (dipakai website)": p["teks"], "teks asli eksperimen": p["teks_asli"]}

    df = pd.DataFrame([baris(p) for p in rapi])
    df["halaman buku"] = df["halaman buku"].astype("Int64")
    ringkas = (df.groupby(["mapel", "kelas"])
                 .agg(**{"jumlah potongan": ("id", "size"),
                         "median karakter": ("panjang (karakter)", "median"),
                         "terpendek": ("panjang (karakter)", "min"),
                         "terpanjang": ("panjang (karakter)", "max"),
                         "dirapikan": ("dirapikan", lambda s: int((s != "-").sum()))})
                 .reset_index())
    ket = pd.DataFrame({"Keterangan": [
        "Potongan buku (Kurikulum Merdeka) yang dicari website untuk skenario S3 dan S4.",
        "Strategi: Recursive, paling panjang 500 karakter, tumpang 50 karakter "
        "(Eksperimen_Chunking/eksperimen/chunking.py).",
        "Pemisah bertingkat: paragraf, baris, kalimat ('. '), spasi.",
        "Perapian untuk website (potongan eksperimen tidak diubah):",
        f"  1. sisa kata di awal dibuang: {hitung['sisa kata di awal dibuang']} potongan",
        f"  2. kolofon buku (KEMENTERIAN ... Penulis: ...) dibuang: {hitung['kolofon dibuang']} potongan",
        f"  3. huruf renggang hiasan (U n i t ..., B a b) dibuang: {hitung['huruf renggang dibuang']} potongan",
        f"  4. potongan < {POTONGAN_MIN} karakter sesudah dirapikan dibuang: "
        f"{hitung['potongan terlalu pendek dibuang']} potongan (lembar Dibuang)",
        f"Jumlah potongan dipakai website: {len(rapi)}",
        "Kolom 'teks (dipakai website)' = teks yang dicari dan dikirim ke AI (3 potongan teratas).",
        "Kolom 'teks asli eksperimen' = teks sebelum dirapikan, untuk perbandingan.",
        "Halaman PDF = nomor halaman berkas PDF; halaman buku = nomor tercetak di buku."]})

    def bersih(d):
        return d.map(lambda x: ILLEGAL_CHARACTERS_RE.sub("", x) if isinstance(x, str) else x)

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with pd.ExcelWriter(path, engine="openpyxl") as w:
        ket.to_excel(w, sheet_name="Keterangan", index=False)
        ringkas.to_excel(w, sheet_name="Ringkasan", index=False)
        for m in ("PJOK", "PKN"):
            bersih(df[df.mapel == m]).to_excel(w, sheet_name=m, index=False)
        bersih(pd.DataFrame([baris({**p, "teks": p["teks"] or "(kosong)"}) for p in dibuang]
                            or [{"id": "-"}])).to_excel(w, sheet_name="Dibuang", index=False)
        kuning = PatternFill("solid", fgColor="FDF6E3")
        for ws in w.book.worksheets:
            ws.freeze_panes = "A2"
            for c in ws[1]:
                c.font = Font(bold=True)
                c.fill = kuning
            lebar = {"Keterangan": 110, "bab": 28, "dirapikan": 26,
                     "teks (dipakai website)": 80, "teks asli eksperimen": 80}
            for c in ws[1]:
                ws.column_dimensions[c.column_letter].width = lebar.get(c.value, 14)
                if c.value in ("teks (dipakai website)", "teks asli eksperimen", "bab", "dirapikan"):
                    for sel in ws[c.column_letter][1:]:
                        sel.alignment = Alignment(wrap_text=True, vertical="top")
    print(f"tersimpan: {path} ({len(rapi)} potongan, {len(dibuang)} dibuang)")
    return path


def _peta_halaman(folder: str) -> dict:
    """(mapel, kelas, halaman_pdf) -> (halaman_buku, bab)."""
    peta = {}
    for nama in os.listdir(folder):
        if not nama.endswith(".jsonl"):
            continue
        with open(os.path.join(folder, nama), encoding="utf-8") as f:
            for baris in f:
                h = json.loads(baris)
                peta[(h["mapel"], int(h["kelas"]), int(h["halaman_pdf"]))] = (
                    h.get("halaman_buku"), (h.get("bab") or "").strip())
    return peta


def impor(sumber: str = SUMBER, teks_halaman: str = TEKS_HALAMAN,
          keluar: str | None = None, strategi=STRATEGI) -> list[dict]:
    from .pencarian import PATH_POTONGAN
    keluar = keluar or PATH_POTONGAN
    peta = _peta_halaman(teks_halaman)
    semua = []
    for s in strategi:
        with open(os.path.join(sumber, f"{s}.jsonl"), encoding="utf-8") as f:
            asli = [json.loads(baris) for baris in f]
        if s == "Recursive":
            asli, hitung = rapikan(asli)
            print(f"perapian {s}: {dict(hitung)}")
        for p in asli:
            hb, bab = peta.get((p["mapel"], int(p["kelas"]), int(p["halaman"])), (None, ""))
            semua.append({
                "id": p["id"], "strategi": s, "mapel": p["mapel"], "kelas": int(p["kelas"]),
                "halaman": int(p["halaman"]), "halaman_buku": hb, "bab": bab,
                "jenis": (p.get("kategori") or "narasi").lower(),
                "teks": p["teks"],
                # Recursive: teks_indeks = teks asli, jadi ikut teks yang sudah dirapikan
                "teks_indeks": p["teks"] if s == "Recursive" else (p.get("teks_indeks") or p["teks"])})
    with open(keluar, "w", encoding="utf-8") as f:
        for p in semua:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    c = Counter((p["strategi"], p["mapel"]) for p in semua)
    print(f"{len(semua)} potongan -> {keluar}")
    for (s, m), n in sorted(c.items()):
        print(f"  {s:9s} {m}: {n}")
    return semua


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--sumber", default=SUMBER, help="folder <Strategi>.jsonl hasil eksperimen")
    ap.add_argument("--teks", default=TEKS_HALAMAN, help="folder teks per halaman (nomor tercetak, bab)")
    ap.add_argument("--strategi", nargs="+", default=list(STRATEGI))
    ap.add_argument("--xlsx", action="store_true",
                    help="hanya ekspor potongan Recursive yang dirapikan ke hasil/Potongan_Recursive_Rapi.xlsx")
    a = ap.parse_args()
    if a.xlsx:
        ekspor_xlsx(sumber=a.sumber, teks_halaman=a.teks)
    else:
        impor(a.sumber, a.teks, strategi=a.strategi)
