"""Daftar buku ajar dan pengambilan teks per halaman.

Mengikuti Subbab 3.1.3.1 dan Lampiran 1:
  1. teks diambil halaman demi halaman dengan PyMuPDF,
  2. bagian yang bukan materi ajar (sampul, kata pengantar, daftar isi, glosarium,
     daftar pustaka, indeks, profil) dibuang,
  3. baris berjalan (judul buku, nomor halaman) dibuang, kata terpenggal disambung,
     pindah baris diubah menjadi spasi.

Nomor halaman yang dicatat adalah nomor halaman berkas PDF, bukan nomor cetak.
"""
from __future__ import annotations

import glob
import os
import re
from collections import Counter
from dataclasses import dataclass, asdict

import pymupdf

# ---------------------------------------------------------------------------
# Daftar buku. Satu Buku Siswa per jenjang per mata pelajaran (Tabel 3.5, 3.6).
# Folder dapat diganti lewat variabel lingkungan TB_KORPUS_PJOK / TB_KORPUS_PKN,
# atau berkas dicari otomatis di /kaggle/input bila dijalankan di Kaggle.
# ---------------------------------------------------------------------------
MAPEL = {
    "PJOK": {
        "nama": "Pendidikan Jasmani, Olahraga, dan Kesehatan",
        "singkat": "PJOK",
        # Kurikulum Merdeka, sama dengan buku sekolah UAT dan dataset Validasi_Soal_PJOK.
        # Buku Siswa PJOK kelas 3 Merdeka tidak tersedia, jadi kelas 3 memakai Buku Panduan
        # Guru. Korpus lama (kelas 2-4 BSE 2010, kelas 5-6 K-13 Revisi 2019) tetap dipakai
        # proyek Eksperimen_Chunking mode "campuran".
        "folder": os.environ.get("TB_KORPUS_PJOK", r"D:/Skripsi/PJOK Kurikulum Merdeka"),
        "buku": {
            1: ("PJOK_Kelas 1.pdf", "Buku Siswa PJOK Kelas I (Kurikulum Merdeka, 2024)"),
            2: ("PJOK_Kelas 2.pdf", "Buku Siswa PJOK Kelas II (Kurikulum Merdeka, 2024)"),
            3: ("PJOK_Kelas 3.pdf", "Buku Panduan Guru PJOK Kelas III (Kurikulum Merdeka, 2022)"),
            4: ("PJOK_Kelas 4.pdf", "Buku Siswa PJOK Kelas IV (Kurikulum Merdeka, 2024)"),
            5: ("PJOK_Kelas 5.pdf", "Buku Siswa PJOK Kelas V (Kurikulum Merdeka, 2024)"),
            6: ("PJOK_Kelas 6.pdf", "Buku Siswa PJOK Kelas VI (Kurikulum Merdeka, 2024)"),
        },
    },
    "PKN": {
        "nama": "Pendidikan Pancasila",
        "singkat": "Pancasila",
        "folder": os.environ.get("TB_KORPUS_PKN", r"D:/Skripsi/PKN"),
        "buku": {
            1: ("Pendidikan-Pancasila-BS-KLS-I.pdf", "Buku Siswa Pendidikan Pancasila Kelas I"),
            2: ("Pendidikan-Pancasila-BS-KLS-II.pdf", "Buku Siswa Pendidikan Pancasila Kelas II"),
            3: ("Pendidikan-Pancasila-BS-KLS-III.pdf", "Buku Siswa Pendidikan Pancasila Kelas III"),
            4: ("Pendidikan-Pancasila-BS-KLS-IV.pdf", "Buku Siswa Pendidikan Pancasila Kelas IV"),
            5: ("Pendidikan-Pancasila-BS-KLS-V.pdf", "Buku Siswa Pendidikan Pancasila Kelas V"),
            6: ("Pendidikan-Pancasila-BS-KLS-VI-Rev.pdf", "Buku Siswa Pendidikan Pancasila Kelas VI"),
        },
    },
}

KELAS = range(1, 7)


def path_buku(mapel: str, kelas: int) -> str:
    nama = MAPEL[mapel]["buku"][kelas][0]
    p = os.path.join(MAPEL[mapel]["folder"], nama)
    if os.path.exists(p):
        return p
    hit = glob.glob(f"/kaggle/input/**/{nama}", recursive=True)
    if hit:
        return hit[0]
    raise FileNotFoundError(f"Buku {mapel} kelas {kelas} tidak ditemukan: {p}")


# ---------------------------------------------------------------------------
# Pembersihan teks
# ---------------------------------------------------------------------------
# Ligatur PDF yang salah dipetakan dan karakter area pribadi Unicode.
_LIGATUR = {"\u6600": "f", "\u6900": "i", "\u6c00": "l", "\ufb01": "fi", "\ufb02": "fl"}
_PUA = re.compile(r"[\ue000-\uf8ff\ufffd]")


def _buka_kembar(t: str) -> str:
    """'KKaattaa PPeennggaannttaarr' -> 'Kata Pengantar' (teks ter-render dua kali)."""
    def satu(m):
        w = m.group(0)
        if len(w) >= 4 and len(w) % 2 == 0 and w[0::2] == w[1::2]:
            return w[0::2]
        return w
    return re.sub(r"[A-Za-z]+", satu, t)


_BUTIR = re.compile(r"[•●▪■✓✔✘√⁍➢❖]")


def rapikan_karakter(t: str) -> str:
    for k, v in _LIGATUR.items():
        t = t.replace(k, v)
    t = _PUA.sub(" ", t)
    t = _BUTIR.sub(" ", t.replace("\xad", ""))     # tanda butir dan tanda hubung lunak
    return _buka_kembar(t)


# Baris yang selalu dibuang, di mana pun letaknya.
_BARIS_SAMPAH = [
    r"^\d{1,4}$",                                   # nomor halaman
    r"^(di ?unduh dari|diunduh dari).*$",
    r"^.*bukupaket\.com.*$", r"^.*bse\.mahoni\.com.*$",
    r"^isbn\b.*$", r"^hak cipta\b.*$", r"^https?://\S+$",
    r"^s ?u ?m ?b ?e ?r\s*:.*$",                    # kredit gambar, juga "Sumb er:"
    r"^g ?a ?m ?b ?a ?r\s*\d+(\.\d+)*\b.*$",        # keterangan gambar, juga "Gam bar"
    r"^pindai aku\.?$",
]
_BARIS_SAMPAH = [re.compile(p, re.I) for p in _BARIS_SAMPAH]

# Penanda halaman depan dan belakang, dicari di bagian atas halaman.
_PENANDA_DEPAN = re.compile(
    r"(kata pengantar|daftar isi|prakata|petunjuk penggunaan buku|hak cipta|penafian|"
    r"ayo mengenal buku|ada apa di buku ini|tentang buku ini)", re.I)
_PENANDA_BELAKANG = re.compile(
    r"^\s*(?:\d{1,3}\s+)?(glosarium|daftar\s+pustaka|indeks|biodata|kunci\s+jawaban|"
    r"profil\s+(?:penulis|penelaah|editor|ilustrator|pelaku\s+perbukuan))", re.I | re.M)

_JUDUL_BAB = re.compile(r"^(bab|pelajaran|unit|tema)\s+\d+\b.{0,90}$", re.I)


_ISBN_ANGKA = re.compile(r"\d{3}-\d{3}-\d{3}-\d{3}-\d")
_KOLOFON = re.compile(r"kementerian pendidikan|penulis\s*:|republik indonesia,\s*20\d\d", re.I)
_BARIS_PUSTAKA = re.compile(r"^[A-Z][A-Za-z'\-]+,\s+[A-Z][^.]{0,60}\.?\s*\(?(19|20)\d\d\)?[.,]")


def _buang_kolofon(baris: list[str]) -> list[str]:
    """Membuang baris awal halaman sampai baris ISBN bila di atasnya ada penanda kolofon."""
    for j, b in enumerate(baris[:15]):
        if _ISBN_ANGKA.search(b) and any(_KOLOFON.search(x) for x in baris[:j + 1]):
            return baris[j + 1:]
    return baris


def _bernomor_romawi(baris: list[str]) -> bool:
    """Halaman depan buku bernomor romawi kecil (iii, viii, xii)."""
    tepi = baris[:1] + baris[-1:]
    return any(re.fullmatch(r"[ivxl]{1,6}", b.split()[0]) for b in tepi if b.split())


def _norm_baris(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"\d+", "#", s.lower())).strip()


def _mirip_daftar_isi(baris: list[str]) -> bool:
    """Halaman daftar isi, daftar tabel, atau daftar gambar: banyak baris bertitik tuntun."""
    if len(baris) < 4:
        return False
    bertitik = sum(bool(re.search(r"\.{4,}|…{2,}", b)) for b in baris)
    return bertitik / len(baris) > 0.2


# Baris berjalan hanya dibuang bila berada di tepi halaman DAN berbau judul buku atau
# nomor. Syarat kedua menjaga ajakan berulang seperti "Ayo pelajari sungguh-sungguh!"
# tetap dianggap isi materi, sebagaimana Tabel L1.1.
_CIRI_BERJALAN = re.compile(r"#|sd/mi|kelas|pendidikan|olahraga|buku siswa|pelajaran|bab", re.I)


def sambung_baris(baris: list[str]) -> str:
    """Menyambung kata terpenggal antarbaris lalu mengubah pindah baris jadi spasi."""
    out = ""
    for b in baris:
        if out.endswith("-") and b[:1].islower():
            kiri = re.search(r"(\w+)-$", out)
            kanan = re.match(r"\w+", b)
            # 'sungguh-' + 'sungguh' adalah kata ulang: tanda hubungnya dipertahankan
            if kiri and kanan and kiri.group(1).lower() == kanan.group(0).lower():
                out += b
            else:
                out = out[:-1] + b
        else:
            out = f"{out} {b}" if out else b
    return re.sub(r"\s+", " ", out).strip()


@dataclass
class Halaman:
    mapel: str
    kelas: int
    halaman: int          # nomor halaman berkas PDF, dimulai dari 1
    bagian: str           # 'depan' | 'isi' | 'belakang'
    bab: str              # judul bab terakhir yang terlihat, bila ada
    n_mentah: int         # panjang teks mentah hasil pengambilan
    teks: str             # teks bersih

    def dict(self):
        return asdict(self)


def baca_buku(mapel: str, kelas: int, path: str | None = None) -> list[Halaman]:
    path = path or path_buku(mapel, kelas)
    doc = pymupdf.open(path)
    n = len(doc)
    mentah = [rapikan_karakter(doc[i].get_text()) for i in range(n)]
    baris_hal = [[b.strip() for b in t.splitlines() if b.strip()] for t in mentah]

    # Baris berjalan: baris yang (setelah angka diganti #) muncul di banyak halaman.
    frek = Counter()
    for bs in baris_hal:
        tepi = bs[:2] + bs[-2:]
        frek.update({_norm_baris(b) for b in tepi if len(b) <= 100})
    ambang = max(5, int(0.08 * n))
    berjalan = {b for b, c in frek.items() if c >= ambang and _CIRI_BERJALAN.search(b)}

    # Batas halaman depan: penanda terakhir di 25% awal, lalu halaman daftar isi lanjutan.
    # Halaman bertitik tuntun hanya dihitung bila bersambung dengan halaman depan,
    # sebab lembar isian siswa juga penuh titik-titik.
    akhir_depan = -1
    for i in range(int(n * 0.25)):
        if _PENANDA_DEPAN.search(mentah[i][:400]):
            akhir_depan = i
        elif i <= akhir_depan + 1 and (_mirip_daftar_isi(baris_hal[i])
                                       or _bernomor_romawi(baris_hal[i])):
            akhir_depan = i
    # Batas halaman belakang: penanda pertama di 25% akhir.
    awal_belakang = n
    for i in range(int(n * 0.75), n):
        glosarium = sum(b == ":" for b in baris_hal[i]) >= 5     # "istilah / : / arti"
        # daftar pustaka tanpa judul di halaman itu: >= 3 baris "Nama, Nama. 2017."
        pustaka = sum(bool(_BARIS_PUSTAKA.match(b)) for b in baris_hal[i]) >= 3
        akhir = i >= int(n * 0.85)
        if (_PENANDA_BELAKANG.search(mentah[i][:300]) or pustaka
                or (akhir and (glosarium or re.search(r"riwayat pekerjaan", mentah[i], re.I)))):
            awal_belakang = i
            break

    hasil, bab = [], ""
    for i in range(n):
        bagian = "depan" if i <= akhir_depan else ("belakang" if i >= awal_belakang else "isi")
        bersih, bs = [], baris_hal[i]
        # Sampul bab Kurikulum Merdeka membawa blok kolofon (kementerian, judul buku,
        # penulis, ISBN). Blok itu dibuang sampai baris ISBN-nya.
        bs = _buang_kolofon(bs)
        for j, b in enumerate(bs):
            if _JUDUL_BAB.match(b) and bagian == "isi":
                bab = re.sub(r"\s+\d+$", "", b).strip()
            di_tepi = j < 2 or j >= len(bs) - 2
            if (di_tepi and _norm_baris(b) in berjalan) or any(p.match(b) for p in _BARIS_SAMPAH):
                continue
            bersih.append(b)
        hasil.append(Halaman(mapel, kelas, i + 1, bagian, bab if bagian == "isi" else "",
                             len(doc[i].get_text()), sambung_baris(bersih)))
    return hasil


def teks_isi(halaman: list[Halaman]) -> str:
    """Seluruh teks bagian isi buku, dipakai untuk mengukur keterbacaan buku."""
    return " ".join(h.teks for h in halaman if h.bagian == "isi" and h.teks)
