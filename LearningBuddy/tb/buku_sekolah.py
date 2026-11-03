"""Buku sekolah: guru mengunggah PDF buku yang dipakai sekolahnya (misalnya buku penerbit),
lalu buku itu ikut dicari saat siswa sekolah tersebut bertanya (S3/S4).

Buku Kemendikbud tetap menjadi acuan bersama semua sekolah. Potongan buku sekolah hanya
menambah calon konteks bagi siswa sekolah itu; reranker yang menentukan potongan mana
yang paling sesuai dengan pertanyaan.

Pemotongan sama persis dengan strategi penelitian (Recursive 500 karakter, tumpang 50,
pemisah paragraf > baris > kalimat > spasi; eksperimen/chunking.py di Eksperimen_Chunking),
lalu dirapikan dengan aturan yang sama (tb.impor_potongan.rapikan).

Berkas per buku: <TB_BUKU_SEKOLAH>/<id>/buku.pdf, potongan.jsonl, dan vektor_<model>.npy.
"""
from __future__ import annotations

import functools
import json
import os
import re
from collections import Counter

AKAR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FOLDER = os.environ.get("TB_BUKU_SEKOLAH", os.path.join(AKAR, "data", "buku_sekolah"))
STRATEGI = "Buku Sekolah"
UKURAN, TUMPANG = 500, 50
PEMISAH = ["\n\n", "\n", ". ", " "]
MAKS_MB = 300
MIN_KARAKTER_HALAMAN = 200       # rata-rata di bawah ini: PDF hasil scan tanpa lapisan teks


class GalatBuku(ValueError):
    """Pesan galat yang aman ditampilkan ke guru."""


def folder_buku(buku_id: int) -> str:
    return os.path.join(FOLDER, str(int(buku_id)))


# --------------------------------------------------------------------------- kata terpecah
@functools.lru_cache(maxsize=1)
def _kosakata() -> frozenset:
    """Kata yang dikenal: seluruh kata di potongan buku Kemendikbud (data/potongan.jsonl)."""
    from .pencarian import PATH_POTONGAN
    kata = set()
    if os.path.exists(PATH_POTONGAN):
        with open(PATH_POTONGAN, encoding="utf-8") as f:
            for baris in f:
                kata.update(w.lower() for w in re.findall(r"[A-Za-z]+", json.loads(baris)["teks"]))
    return frozenset(kata)


_TEPI = re.compile(r"^([^A-Za-z]*)([A-Za-z]+)([^A-Za-z]*)$")


def pulihkan_kata_terpecah(t: str) -> str:
    """Sebagian PDF menyisipkan spasi di dalam kata ("pesert a", "m em akai", "t angan").
    Dua atau tiga pecahan digabung bila gabungannya kata yang dikenal dan salah satu
    pecahannya bukan kata utuh, sehingga "di atas" tetap dua kata."""
    kenal = _kosakata()
    if not kenal:
        return t
    kata, out, i = t.split(" "), [], 0
    utuh = lambda w: len(w) >= 2 and w.lower() in kenal
    while i < len(kata):
        for n in (3, 2):
            bagian = kata[i:i + n]
            if len(bagian) < n:
                continue
            m = [_TEPI.match(b) for b in bagian]
            if not all(m) or m[0].group(3) or any(x.group(1) or x.group(3) for x in m[1:-1]) \
                    or m[-1].group(1):
                continue                          # tanda baca hanya boleh di tepi luar
            inti = [x.group(2) for x in m]
            if "".join(inti).lower() in kenal and not all(utuh(w) for w in inti):
                out.append(m[0].group(1) + "".join(inti) + m[-1].group(3))
                i += n
                break
        else:
            out.append(kata[i])
            i += 1
    return " ".join(out)


# --------------------------------------------------------------------------- membaca PDF
def baca_paragraf(path: str, mapel: str, kelas: int) -> tuple[list[tuple[int, str, str]], int]:
    """(halaman, bab, paragraf) dari halaman ISI buku. Paragraf = blok tata letak PDF yang
    sudah dibersihkan dari baris berjalan, kolofon, dan baris sampah (aturan tb.korpus)."""
    import pymupdf
    from .korpus import (_BARIS_SAMPAH, _CIRI_BERJALAN, _buang_kolofon, _norm_baris,
                         baca_buku, rapikan_karakter, sambung_baris)
    try:
        halaman = baca_buku(mapel, kelas, path)
        doc = pymupdf.open(path)
    except Exception as e:
        raise GalatBuku(f"PDF tidak dapat dibaca ({type(e).__name__}).") from e
    n = len(doc)
    if n == 0:
        raise GalatBuku("PDF kosong.")
    isi = [h for h in halaman if h.bagian == "isi"]
    if sum(len(h.teks) for h in isi) < MIN_KARAKTER_HALAMAN * max(1, len(isi)) * 0.5:
        raise GalatBuku("PDF ini tidak berisi teks yang bisa dibaca (kemungkinan hasil scan). "
                        "Gunakan PDF yang teksnya bisa diblok dan disalin.")

    per_hal = []
    for i in range(n):
        bloks = []
        for b in doc[i].get_text("blocks"):
            if len(b) >= 7 and b[6] != 0:                    # blok gambar
                continue
            baris = [rapikan_karakter(x).strip() for x in b[4].splitlines()]
            bloks.append([x for x in baris if x])
        per_hal.append(bloks)
    # baris berjalan (kepala/kaki halaman) seperti tb.korpus.baca_buku
    frek = Counter()
    for bloks in per_hal:
        bs = [x for bl in bloks for x in bl]
        frek.update({_norm_baris(x) for x in bs[:2] + bs[-2:] if len(x) <= 100})
    ambang = max(5, int(0.08 * n))
    berjalan = {x for x, c in frek.items() if c >= ambang and _CIRI_BERJALAN.search(x)}

    bab = {h.halaman: h.bab for h in halaman}
    keluar = []
    for h in isi:
        bloks = per_hal[h.halaman - 1]
        semua = [x for bl in bloks for x in bl]
        sisa = set(_buang_kolofon(semua)) if semua else set()
        tepi = set(semua[:2] + semua[-2:])
        for bl in bloks:
            bersih = [x for x in bl if x in sisa
                      and not (x in tepi and _norm_baris(x) in berjalan)
                      and not any(p.match(x) for p in _BARIS_SAMPAH)]
            t = pulihkan_kata_terpecah(sambung_baris(bersih))
            if t:
                keluar.append((h.halaman, bab.get(h.halaman, ""), t))
    return keluar, n


# --------------------------------------------------------------------------- Recursive
def _rekursif(t: str, ukuran: int, pemisah: list[str]) -> list[str]:
    if len(t) <= ukuran:
        return [t]
    if not pemisah:
        return [t[i:i + ukuran] for i in range(0, len(t), ukuran)]
    sep, sisa = pemisah[0], pemisah[1:]
    if sep not in t:
        return _rekursif(t, ukuran, sisa)
    out, buf = [], ""
    for bagian in t.split(sep):
        calon = f"{buf}{sep}{bagian}" if buf else bagian
        if len(calon) <= ukuran:
            buf = calon
            continue
        if buf:
            out.append(buf)
        if len(bagian) > ukuran:
            out.extend(_rekursif(bagian, ukuran, sisa))
            buf = ""
        else:
            buf = bagian
    if buf:
        out.append(buf)
    return out


def potong(paragraf: list[tuple[int, str, str]], ukuran: int = UKURAN,
           tumpang: int = TUMPANG) -> list[tuple[int, str, str]]:
    """(halaman, bab, teks potongan): paragraf digabung dengan baris kosong, dipotong
    bertingkat, lalu setiap potongan diawali 50 karakter terakhir potongan sebelumnya."""
    teks, peta, pos = [], [], 0
    for hal, bab, t in paragraf:
        peta.append((pos, hal, bab))
        teks.append(t)
        pos += len(t) + 2
    gabung = "\n\n".join(teks)

    def letak(off):
        hal, bab = (peta[0][1], peta[0][2]) if peta else (0, "")
        for p, h, b in peta:
            if p > off:
                break
            hal, bab = h, b
        return hal, bab

    out, pos, prev = [], 0, ""
    for p in _rekursif(gabung, ukuran, PEMISAH):
        off = gabung.find(p, pos)
        off = off if off >= 0 else pos
        pos = off + len(p)
        isi = (prev[-tumpang:] + " " + p) if (tumpang and prev) else p
        out.append((*letak(off), isi))
        prev = p
    return out


def proses_pdf(path: str, buku_id: int, sekolah_id: int, judul: str, mapel: str,
               kelas: int) -> tuple[list[dict], int]:
    """PDF -> potongan siap dicari (sudah dirapikan). Mengembalikan (potongan, jumlah halaman)."""
    from .impor_potongan import rapikan
    paragraf, n = baca_paragraf(path, mapel, kelas)
    mentah = []
    for i, (hal, bab, t) in enumerate(potong(paragraf)):
        t = re.sub(r"\s+", " ", t).strip()
        if len(t) < 20:
            continue
        mentah.append({"id": f"B{buku_id}-{len(mentah) + 1:04d}", "strategi": STRATEGI,
                       "mapel": mapel, "kelas": int(kelas), "halaman": hal, "halaman_buku": None,
                       "bab": bab, "teks": t, "buku": judul, "sekolah": int(sekolah_id),
                       "buku_id": int(buku_id)})
    rapi, _ = rapikan(mentah)
    for p in rapi:
        p.pop("teks_asli", None)
        p.pop("perapian", None)
        p["teks_indeks"] = p["teks"]
    if not rapi:
        raise GalatBuku("Tidak ada teks materi yang bisa diambil dari PDF ini.")
    return rapi, n


# --------------------------------------------------------------------------- penyimpanan
def simpan_pdf(buku_id: int, isi: bytes) -> str:
    if not isi.startswith(b"%PDF"):
        raise GalatBuku("Berkas bukan PDF.")
    d = folder_buku(buku_id)
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, "buku.pdf")
    with open(path, "wb") as f:
        f.write(isi)
    return path


def simpan_potongan(buku_id: int, potongan: list[dict]) -> None:
    with open(os.path.join(folder_buku(buku_id), "potongan.jsonl"), "w", encoding="utf-8") as f:
        for p in potongan:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")


def muat_potongan(buku_id: int) -> list[dict]:
    path = os.path.join(folder_buku(buku_id), "potongan.jsonl")
    with open(path, encoding="utf-8") as f:
        return [json.loads(x) for x in f]


def hapus_berkas(buku_id: int) -> None:
    import shutil
    shutil.rmtree(folder_buku(buku_id), ignore_errors=True)
