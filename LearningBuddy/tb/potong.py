"""Pemotongan teks yang menyesuaikan fungsi teks (Subbab 3.1.3.1, Lampiran 1).

Aturannya:
  1. setiap kalimat ditandai sebagai uraian konsep, langkah instruksi, butir evaluasi,
     atau narasi;
  2. kalimat berurutan yang sejenis membentuk satu blok; blok pendek (di bawah
     BLOK_MIN karakter, misalnya ajakan "Ayo pelajari sungguh-sungguh!") dilebur ke
     blok tetangganya agar satu satuan penjelasan tidak tercerai;
  3. blok sejenis digabung sampai mendekati BATAS karakter, blok berlainan jenis tidak
     pernah digabung;
  4. potongan hanya dipotong pada batas kalimat, sehingga setiap potongan dapat
     ditelusuri ke halaman PDF asalnya;
  5. LANTAI: potongan di bawah 300 karakter dilebur ke tetangganya di halaman yang sama,
     atau ke halaman berikutnya bila satu halaman penuh pun kurang dari 300 karakter.
     Alasannya empiris: pada data PJOK, Token-F1 potongan terambil terhadap konteks acuan
     hanya 0,31 untuk potongan < 300 karakter lawan 0,59 untuk >= 300, dan median konteks
     acuan buatan manusia 495 karakter. Batas atas 1.200 tidak berpengaruh berarti.

Nomor potongan mengikuti Tabel L1.2: PJOK-K1-016-01 (halaman awal potongan).
Potongan berjenis evaluasi (halaman soal latihan) tetap disimpan tetapi tidak dicari,
sebab berisi pertanyaan, bukan jawaban - lihat tb.pencarian.boleh_dicari.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, asdict

BATAS = 1200
LANTAI = 300
BLOK_MIN = 150
POTONGAN_MIN = 40      # potongan lebih pendek dari ini hanyalah sisa judul

_EVALUASI = re.compile(
    r"\b(evaluasi|uji kompetensi|ulangan|latihan soal|pilihlah|jawablah|kerjakan soal|"
    r"isilah|jodohkan|benar atau salah|berilah tanda|refleksi|releksi|"
    # halaman refleksi diri: berisi pertanyaan untuk siswa, bukan materi.
    # "releksi" = "refleksi" yang huruf f-nya hilang karena ligatur PDF
    r"materi yang sudah kamu kuasai|apa yang ingin kamu pelajari|bagaimana perasaan)\b", re.I)
_KONSEP = re.compile(
    r"\b(adalah|merupakan|yaitu|yakni|ialah|disebut|artinya|berarti|berfungsi|bermanfaat|"
    r"bertujuan|manfaat|tujuan|contoh|terdiri)\b", re.I)
_INSTRUKSI_AWAL = re.compile(
    r"^(sikap awal|sikap akhir|cara melakukan|caranya|langkah|gerakan|lakukan|ayo,? lakukan|"
    r"ulangi|angkat|tekuk|buka|letakkan|rentangkan|luruskan|putar|ayunkan|berdiri|duduk|"
    r"jongkok|lompat|loncat|lari|jalan|tolak|pukul|tangkap|lempar|tendang|pantulkan|"
    r"pegang|tarik|dorong|hitung|bungkukkan|condongkan|kembali)\b", re.I)


def pisah_kalimat_utuh(teks: str) -> list[str]:
    """Memecah teks menjadi kalimat dengan tanda bacanya tetap melekat."""
    bagian = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])", teks.strip())
    return [b.strip() for b in bagian if b.strip()]


def jenis_kalimat(kalimat: str, dalam_evaluasi: bool) -> str:
    if dalam_evaluasi or _EVALUASI.search(kalimat):
        return "evaluasi"
    kata_pertama = kalimat.split()[0].lower() if kalimat.split() else ""
    if _INSTRUKSI_AWAL.match(kalimat) or (kata_pertama.endswith(("kan", "lah"))
                                         and len(kata_pertama) > 5):
        return "instruksi"
    if _KONSEP.search(kalimat):
        return "konsep"
    return "narasi"


@dataclass
class Potongan:
    id: str
    mapel: str
    kelas: int
    halaman: int
    bab: str
    jenis: str
    teks: str
    halaman_akhir: int = 0      # > halaman bila potongan menyambung ke halaman berikutnya

    def dict(self):
        d = asdict(self)
        d["halaman_akhir"] = self.halaman_akhir or self.halaman
        return d


def _blok(kalimat: list[str]) -> list[tuple[str, list[str]]]:
    blok, evaluasi = [], False
    for k in kalimat:
        if _EVALUASI.search(k):
            evaluasi = True          # sesudah penanda evaluasi, sisa halaman adalah soal
        j = jenis_kalimat(k, evaluasi)
        if blok and blok[-1][0] == j:
            blok[-1][1].append(k)
        else:
            blok.append((j, [k]))
    # lebur blok pendek ke tetangga yang lebih panjang
    berubah = True
    while berubah and len(blok) > 1:
        berubah = False
        for i, (j, ks) in enumerate(blok):
            if sum(len(k) for k in ks) >= BLOK_MIN:
                continue
            if i + 1 < len(blok):
                blok[i + 1] = (blok[i + 1][0], ks + blok[i + 1][1])
            else:
                blok[i - 1] = (blok[i - 1][0], blok[i - 1][1] + ks)
            del blok[i]
            berubah = True
            break
    # gabungkan blok sejenis yang kini bersebelahan
    rapat = []
    for j, ks in blok:
        if rapat and rapat[-1][0] == j:
            rapat[-1][1].extend(ks)
        else:
            rapat.append((j, list(ks)))
    return rapat


def _kemas(kalimat: list[str]) -> list[str]:
    """Mengemas kalimat menjadi potongan <= BATAS, hanya dipotong di batas kalimat."""
    out, cur = [], ""
    for k in kalimat:
        if len(k) > BATAS:                     # kalimat raksasa: dipotong di spasi
            if cur:
                out.append(cur)
                cur = ""
            while len(k) > BATAS:
                cut = k.rfind(" ", 0, BATAS)
                cut = cut if cut > 0 else BATAS
                out.append(k[:cut])
                k = k[cut:].strip()
        if cur and len(cur) + 1 + len(k) > BATAS:
            out.append(cur)
            cur = k
        else:
            cur = f"{cur} {k}".strip()
    if cur:
        out.append(cur)
    return out


def potong_halaman(h: dict) -> list[Potongan]:
    """h: satu baris data/halaman_<MAPEL>.jsonl (bagian isi saja yang dipotong)."""
    if h["bagian"] != "isi" or not h["teks"].strip():
        return []
    hasil = []
    for jenis, ks in _blok(pisah_kalimat_utuh(h["teks"])):
        for teks in _kemas(ks):
            if len(teks) < POTONGAN_MIN:
                continue
            nomor = f"{h['mapel']}-K{h['kelas']}-{h['halaman']:03d}-{len(hasil) + 1:02d}"
            hasil.append(Potongan(nomor, h["mapel"], h["kelas"], h["halaman"],
                                  h.get("bab", ""), jenis, teks))
    return hasil


def _gabung(a: Potongan, b: Potongan) -> Potongan:
    """b disambung ke belakang a; jenis mengikuti bagian yang lebih panjang."""
    return Potongan(a.id, a.mapel, a.kelas, a.halaman, a.bab or b.bab,
                    a.jenis if len(a.teks) >= len(b.teks) else b.jenis,
                    f"{a.teks} {b.teks}", max(a.halaman_akhir or a.halaman,
                                               b.halaman_akhir or b.halaman))


def _angkat_lantai(ps: list[Potongan]) -> list[Potongan]:
    """Di dalam satu halaman: potongan < LANTAI dilebur ke tetangga terpendek yang muat."""
    ps = list(ps)
    berubah = True
    while berubah and len(ps) > 1:
        berubah = False
        for i, p in enumerate(ps):
            if len(p.teks) >= LANTAI:
                continue
            calon = [j for j in (i - 1, i + 1) if 0 <= j < len(ps)
                     and len(ps[j].teks) + 1 + len(p.teks) <= BATAS]
            if not calon:
                continue
            j = min(calon, key=lambda j: len(ps[j].teks))
            a, b = (ps[j], p) if j < i else (p, ps[j])
            ps[min(i, j)] = _gabung(a, b)
            del ps[max(i, j)]
            berubah = True
            break
    return ps


def potong_buku(halaman: list[dict]) -> list[Potongan]:
    """Memotong seluruh halaman isi satu buku (urut halaman) dengan lantai 300 karakter.
    Potongan yang masih di bawah lantai sesudah dilebur di halamannya sendiri dibawa
    ke potongan pertama halaman berikutnya."""
    keluar: list[Potongan] = []
    bawaan: Potongan | None = None
    for h in sorted(halaman, key=lambda x: x["halaman"]):
        ps = _angkat_lantai(potong_halaman(h))
        if bawaan is not None:
            if ps and len(bawaan.teks) + 1 + len(ps[0].teks) <= BATAS \
                    and ps[0].halaman - (bawaan.halaman_akhir or bawaan.halaman) <= 1:
                ps[0] = _gabung(bawaan, ps[0])
            else:
                keluar.append(bawaan)
            bawaan = None
        if ps and len(ps[-1].teks) < LANTAI:
            bawaan = ps.pop()
        keluar.extend(ps)
    if bawaan is not None:
        keluar.append(bawaan)
    # nomori ulang per halaman awal: PJOK-K1-016-01
    hitung: dict[tuple, int] = {}
    for p in keluar:
        kunci = (p.mapel, p.kelas, p.halaman)
        hitung[kunci] = hitung.get(kunci, 0) + 1
        p.id = f"{p.mapel}-K{p.kelas}-{p.halaman:03d}-{hitung[kunci]:02d}"
    return keluar
