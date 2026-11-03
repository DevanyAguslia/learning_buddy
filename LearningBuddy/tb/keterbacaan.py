"""Kontrol keterbacaan tingkat kelas - rumus (2.4) proposal.

    PKR = N_kata / N_kalimat                       panjang kalimat rata-rata
    KLD = (100 / N_isi) * sum 1[w not in D]        persen kata isi di luar daftar dasar

Sebuah jawaban dinyatakan sesuai jenjang bila PKR <= sasaran PKR DAN KLD <= sasaran
KLD jenjang penanya. Bila salah satu melampaui, Reflect Agent menyusun alasan dan
arahan perbaikan (Subbab 3.1.3.4, Gambar 3.5). Grafik Fry ikut dihitung sebagai
pembanding tetapi tidak dipakai memutuskan.

Modul ini murni Python, tanpa GPU dan tanpa model bahasa.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field, asdict

MIN_PANJANG = 3   # kata isi paling sedikit tiga huruf

# Kata tugas tidak dihitung sebagai kata isi, walaupun panjangnya tiga huruf atau
# lebih. Contoh pada Lampiran 4: "untuk" dan "dan" tidak dihitung. Daftar ini sengaja
# sempit - hanya kata depan, kata sambung, kata ganti, kata tunjuk, partikel, kata
# tanya, dan kata bantu - agar kata isi seperti "merupakan" tetap terukur.
KATA_TUGAS = frozenset("""
yang dan atau untuk dengan dari pada dalam oleh kepada bagi tentang terhadap sejak
hingga sampai antara menuju seperti serta tetapi namun karena sebab agar supaya jika
kalau bila apabila ketika saat sehingga maka lalu kemudian bahwa walaupun meskipun
sedangkan sambil selama setelah sebelum sesudah daripada
saya aku kamu engkau dia kita kami mereka anda beliau kalian nya
ini itu tersebut para sang
pun lah kah tah dong kok
apa siapa mana bagaimana mengapa kenapa kapan berapa
akan sudah telah sedang masih belum juga tidak bukan dapat bisa harus boleh perlu
sangat lebih paling hanya saja pula
""".split())


def pisah_kata(teks: str) -> list[str]:
    return re.findall(r"[A-Za-z]+", str(teks))


_TITIK_ISIAN = re.compile(r"\.{2,}|…+")
_PENANDA_DAFTAR = re.compile(r"(?<![\w.])([a-eA-E]|\d{1,2})\.(?=\s)")
_SINGKATAN = re.compile(r"\b(dll|dsb|dst|dkk|hlm|no|tsb|yth|sdr|kg|cm|km|mm|misal|ket)\.(?=\s+[a-z]|,)")


def _rapikan_titik(teks: str) -> str:
    """Titik isian ("....") dan penanda butir ("a.", "3.") dijadikan batas kalimat,
    sedangkan titik singkatan ("dll.") dan angka desimal ("1.5") bukan batas."""
    t = _TITIK_ISIAN.sub(" . ", str(teks))
    t = _PENANDA_DAFTAR.sub(" . ", t)
    return _SINGKATAN.sub(lambda m: m.group(1), t)


def pisah_kalimat(teks: str, min_kata: int = 1) -> list[str]:
    """Kalimat dipecah pada tanda titik, tanda tanya, dan tanda seru (Tabel L1.3).

    min_kata=1 dipakai untuk jawaban, sebab jawaban satu kata ("Berjalan.") sah.
    Untuk mengukur buku dipakai min_kata=3: penggalan yang lebih pendek adalah butir
    pilihan ganda atau judul ("Rangkuman 1"), bukan kalimat. Tanpa saringan ini satu
    soal pilihan ganda terhitung sebagai empat kalimat satu kata.
    """
    kal = [k.strip() for k in re.split(r"[.!?]+(?=\s|$)", _rapikan_titik(teks))]
    return [k for k in kal if len(pisah_kata(k)) >= min_kata]


def kata_isi(teks: str) -> list[str]:
    return [w.lower() for w in pisah_kata(teks)
            if len(w) >= MIN_PANJANG and w.lower() not in KATA_TUGAS]


# --- Pencocokan terhadap daftar kata dasar -------------------------------------
# Mode "bentuk": kata dikenal bila bentuk persisnya ada di daftar (rumus 2.4 apa adanya).
# Mode "akar"  : kata juga dikenal bila kata dasarnya sama dengan kata dasar salah satu
#               anggota daftar, sehingga "mengubah" dikenal lewat "ubah". Mode ini
#               sejalan dengan alasan Subbab 2.2.6 bahwa imbuhan tidak membuat kata asing.
_STEMMER = None


def akar_kata(w: str) -> str:
    global _STEMMER
    if _STEMMER is None:
        from Sastrawi.Stemmer.StemmerFactory import StemmerFactory
        _STEMMER = StemmerFactory().create_stemmer()
    a = _akar_cache.get(w)
    if a is None:
        a = _akar_cache[w] = _STEMMER.stem(w) or w
    return a


_PATH_CACHE_AKAR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data",
                                "akar_cache.json")
try:
    with open(_PATH_CACHE_AKAR, encoding="utf-8") as _f:
        _akar_cache: dict[str, str] = json.load(_f)
except (OSError, ValueError):
    _akar_cache = {}


def simpan_cache_akar():
    """Stemmer Sastrawi lambat (~10 ms/kata); hasilnya disimpan agar tidak diulang."""
    try:
        with open(_PATH_CACHE_AKAR, "w", encoding="utf-8") as f:
            json.dump(_akar_cache, f, ensure_ascii=False)
    except OSError:
        pass


class Pencocok:
    def __init__(self, daftar, mode: str = "bentuk", akar=None):
        self.daftar = frozenset(daftar)
        self.mode = mode
        if mode != "akar":
            self.akar = frozenset()
        else:   # kata dasar daftar dapat disimpan saat kalibrasi agar pemuatan cepat
            self.akar = frozenset(akar) if akar else frozenset(akar_kata(w) for w in self.daftar)

    def __contains__(self, w: str) -> bool:
        return w in self.daftar or (self.mode == "akar" and akar_kata(w) in self.akar)

    def __len__(self):
        return len(self.daftar)


# --- Grafik Fry: dua koordinatnya, sebagai pembanding --------------------------------
_VOKAL = set("aeiou")
_DIFTONG = ("ai", "au", "oi", "ei")


def suku_kata(kata: str) -> int:
    """Diftong dihitung satu suku hanya di akhir kata: pan-tai (2), per-ma-in-an (4)."""
    k = re.sub(r"[^a-z]", "", str(kata).lower())
    if not k:
        return 0
    n = i = 0
    while i < len(k):
        if k[i] in _VOKAL:
            n += 1
            if i + 2 == len(k) and k[i:i + 2] in _DIFTONG:
                i += 2
                continue
        i += 1
    return max(n, 1)


@dataclass
class Ukuran:
    n_kata: int
    n_kalimat: int
    n_isi: int
    pkr: float                      # kata per kalimat
    kld: float                      # persen kata isi di luar daftar dasar
    kata_luar: list[str] = field(default_factory=list)
    fry_suku_100: float = 0.0       # suku kata per 100 kata (sumbu mendatar Grafik Fry)
    fry_kalimat_100: float = 0.0    # kalimat per 100 kata (sumbu tegak Grafik Fry)

    def dict(self):
        d = asdict(self)
        d["pkr"], d["kld"] = round(self.pkr, 2), round(self.kld, 1)
        d["fry_suku_100"] = round(self.fry_suku_100, 1)
        d["fry_kalimat_100"] = round(self.fry_kalimat_100, 2)
        return d


def ukur(teks: str, daftar_dasar: "Pencocok | set[str] | None" = None,
         min_kata_kalimat: int = 1) -> Ukuran | None:
    """Mengukur PKR, KLD, dan koordinat Fry atas kalimat yang sah saja."""
    kal = pisah_kalimat(teks, min_kata_kalimat)
    if not kal:
        return None
    kata = [w for k in kal for w in pisah_kata(k)]
    isi = [w for k in kal for w in kata_isi(k)]
    luar = [w for w in isi if daftar_dasar is not None and w not in daftar_dasar]
    kld = 100.0 * len(luar) / len(isi) if (isi and daftar_dasar is not None) else 0.0
    sk = sum(suku_kata(w) for w in kata)
    unik = list(dict.fromkeys(luar))    # urutan kemunculan, tanpa duplikat, untuk arahan
    return Ukuran(len(kata), len(kal), len(isi), len(kata) / len(kal), kld, unik,
                  100.0 * sk / len(kata), 100.0 * len(kal) / len(kata))


# --- Pemeriksaan oleh Reflect Agent ---------------------------------------------
@dataclass
class Sasaran:
    maks_pkr: float
    maks_kld: float
    pkr_buku: float | None = None
    kld_buku: float | None = None


@dataclass
class Pemeriksaan:
    lolos: bool
    lolos_pkr: bool
    lolos_kld: bool
    ukuran: dict | None
    sasaran: dict
    jarak: float                    # 0 bila lolos; makin besar makin jauh dari sasaran
    alasan: list[str]
    arahan: str | None

    def dict(self):
        return asdict(self)


def jarak_ke_sasaran(pkr: float, kld: float, s: Sasaran) -> float:
    """Jumlah kelebihan relatif kedua ukuran terhadap sasarannya.

    Dipakai memilih jawaban terbaik bila tiga putaran habis tanpa ada yang lolos
    (Subbab 3.1.3.4): bukan jawaban terakhir, melainkan yang paling dekat sasaran.
    """
    lebih_pkr = max(0.0, pkr / max(s.maks_pkr, 1e-9) - 1.0)
    lebih_kld = max(0.0, kld / max(s.maks_kld, 1e-9) - 1.0) if kld > 0 else 0.0
    return round(lebih_pkr + lebih_kld, 4)


class KontrolKeterbacaan:
    """Memuat daftar kata dasar dan sasaran per jenjang hasil kalibrasi."""

    def __init__(self, daftar: dict[str, "Pencocok"], sasaran: dict[str, dict[int, Sasaran]],
                 meta: dict | None = None):
        self.daftar = daftar
        self.sasaran = sasaran
        self.meta = meta or {}

    @classmethod
    def muat(cls, path: str | None = None) -> "KontrolKeterbacaan":
        path = path or os.environ.get("TB_KETERBACAAN") or os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "data", "kontrol_keterbacaan.json")
        with open(path, encoding="utf-8") as f:
            K = json.load(f)
        mode = K.get("meta", {}).get("pencocokan", "bentuk")
        daftar = {m: Pencocok(v["daftar_dasar"], mode, v.get("akar_dasar"))
                  for m, v in K["mapel"].items()}
        sasaran = {m: {int(k): Sasaran(**s) for k, s in v["sasaran"].items()}
                   for m, v in K["mapel"].items()}
        return cls(daftar, sasaran, K.get("meta"))

    def ukur(self, teks: str, mapel: str) -> Ukuran | None:
        return ukur(teks, self.daftar[mapel])

    def periksa(self, teks: str, mapel: str, kelas: int) -> Pemeriksaan:
        s = self.sasaran[mapel][int(kelas)]
        u = self.ukur(teks, mapel)
        if u is None:
            return Pemeriksaan(False, False, False, None, asdict(s), 99.0,
                               ["jawaban kosong"],
                               f"Tulis jawaban yang lengkap untuk siswa kelas {kelas}.")
        ok_pkr, ok_kld = u.pkr <= s.maks_pkr, u.kld <= s.maks_kld
        alasan, arahan = [], []
        if not ok_pkr:
            alasan.append(f"kalimat terlalu panjang: {u.pkr:.1f} kata per kalimat, "
                          f"batas {s.maks_pkr:.1f}")
            arahan.append(f"pecah menjadi kalimat pendek, paling banyak "
                          f"{int(s.maks_pkr)} kata per kalimat")
        if not ok_kld:
            contoh = ", ".join(u.kata_luar[:5])
            alasan.append(f"terlalu banyak kata sulit: {u.kld:.0f}% kata di luar daftar "
                          f"kata dasar, batas {s.maks_kld:.1f}%")
            arahan.append(f"ganti kata sulit dengan kata sehari-hari, yaitu: {contoh}")
        lolos = ok_pkr and ok_kld
        teks_arahan = None if lolos else (
            f"Tulis ulang jawabanmu untuk siswa kelas {kelas}: " + "; ".join(arahan)
            + ". Isi jawabannya jangan diubah.")
        return Pemeriksaan(lolos, ok_pkr, ok_kld, u.dict(), asdict(s),
                           0.0 if lolos else jarak_ke_sasaran(u.pkr, u.kld, s),
                           alasan, teks_arahan)
