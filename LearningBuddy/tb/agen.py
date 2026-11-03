"""Siklus multi-agentic Perceive - Plan - Act - Reflect (Subbab 2.1, Gambar 3.4).

Koordinasi antaragen tidak lewat pesan langsung, melainkan lewat SATU keadaan bersama
(`Keadaan`) yang dikelola orkestrator graf LangGraph. Setiap agen membaca bagian yang
dibutuhkannya lalu menulis hasilnya kembali ke keadaan yang sama.

Tiga percabangan (Subbab 3.1.3.4):
  1. sesudah Perceive : pertanyaan jelas?          tidak -> minta siswa mengulang
  2. di dalam Act     : skenario memakai konteks?  (S3, S4)
  3. sesudah Reflect  : keterbacaan sesuai?        tidak dan putaran < 3 -> kembali ke Act
Bila batas putaran habis tanpa jawaban yang lolos, dipilih jawaban dengan jarak
terkecil terhadap sasaran di antara seluruh putaran, bukan jawaban terakhir.
"""
from __future__ import annotations

import datetime as dt
import difflib
import json
import operator
import os
import re
import threading
import time
from typing import Annotated, Any, Iterator, TypedDict

from langgraph.graph import StateGraph, START, END

from .keterbacaan import KontrolKeterbacaan, kata_isi
from .korpus import MAPEL
from .model import AKSARA_ASING

MAKS_PUTARAN = 3
MAKS_TOKEN = 128

# Plan Agent: bobot bukti letak materi di buku terhadap tebakan Qwen, dan ambang keyakinan
# di bawahnya siswa diminta mengonfirmasi kelasnya. 0,4 dipilih dari data uji PJOK dengan
# bukti buku saja: 26% pertanyaan ditanyakan balik, sisanya tepat 75,2%. Kalibrasi ulang di
# Kaggle setelah probe Qwen ikut dihitung (Lab > Uji sistem, jenjang ditebak Plan Agent).
BOBOT_BUKU = 0.5
AMBANG_KONFIRMASI = 0.4
# Batas bertanya balik (Perceive) + konfirmasi kelas (Plan) berturut-turut dalam satu
# percakapan; sesudahnya pertanyaan langsung dijawab dengan tebakan terbaik.
MAKS_TANYA_BALIK = 3

# Pengecekan 2 (Reflect): jawaban dianggap menjawab pertanyaan bila peluang YA >= 0,5
AMBANG_RELEVAN_JAWABAN = 0.5

# Sapaan dan kata pengisi yang tidak dianggap isi pelajaran (Perceive tidak bertanya balik)
SAPAAN = frozenset("""halo hai hallo selamat pagi siang sore malam terima kasih makasih
tolong bantu dong deh nih tuh kak bu pak ibu bapak guru tes test coba""".split())

# Empat skenario pembanding (Tabel 3.11): (pakai adapter, pakai konteks)
SKENARIO = {"S1": (False, False), "S2": (True, False), "S3": (False, True), "S4": (True, True)}

# --- prompt Act Agent: sama persis dengan prompt pelatihan G1 (jangan diubah) --------
INSTR_CORE = ("WAJIB menjawab dalam Bahasa Indonesia. Dilarang menggunakan bahasa "
              "atau aksara lain. Jawab dalam 1-2 kalimat lengkap dengan bahasa yang "
              "mudah dipahami siswa sekolah dasar.")
INSTR_CTX = ("Jawab pertanyaan berikut HANYA berdasarkan konteks di atas. " + INSTR_CORE +
             " Jangan menambahkan informasi di luar konteks.")


def sys_prompt(mapel: str) -> str:
    nama = "PJOK" if mapel == "PJOK" else MAPEL[mapel]["nama"]
    return (f"Kamu asisten pembelajaran {nama} sekolah dasar. "
            "Kamu SELALU menjawab dalam Bahasa Indonesia.")


def pesan_jawab(mapel: str, pertanyaan: str, konteks: str | None) -> list[dict]:
    if konteks:
        user = f"Konteks:\n{konteks}\n\n{INSTR_CTX}\nPertanyaan: {pertanyaan}"
    else:
        user = f"{INSTR_CORE}\nPertanyaan: {pertanyaan}"
    return [{"role": "system", "content": sys_prompt(mapel)}, {"role": "user", "content": user}]


# --- prompt tulis ulang (putaran 2-3): model dasar tanpa adapter, karena adapter dilatih
# menjawab sangat ringkas dan tulisan ulangnya sering rusak atau bercampur bahasa Inggris
def pesan_tulis_ulang(mapel: str, kelas: int, pertanyaan: str, konteks: str | None,
                      jawaban: str, arahan: str) -> list[dict]:
    nama = "PJOK" if mapel == "PJOK" else MAPEL[mapel]["nama"]
    sistem = (f"Kamu guru {nama} sekolah dasar yang menulis ulang jawaban agar mudah dibaca "
              f"siswa kelas {kelas}. Kamu SELALU menulis dalam Bahasa Indonesia sederhana, "
              "tanpa kata bahasa Inggris atau bahasa asing lain.")
    user = ((f"Potongan buku:\n{konteks}\n\n" if konteks else "")
            + f"Pertanyaan siswa: {pertanyaan}\nJawaban sebelumnya: {jawaban}\n\n"
            + f"Tugas: {arahan}\n"
            + "Aturan: pertahankan isi yang benar"
            + (" dan hanya pakai informasi dari potongan buku" if konteks else "")
            + "; tulis 1-3 kalimat lengkap yang masing-masing diakhiri titik; jangan memotong "
            "kalimat; tulis jawabannya saja tanpa kata pengantar.")
    return [{"role": "system", "content": sistem}, {"role": "user", "content": user}]


KATA_GANTUNG = {"di", "ke", "dari", "pada", "dan", "atau", "yang", "dengan", "untuk", "karena",
                "agar", "supaya", "seperti", "adalah", "yaitu", "bahwa", "oleh", "sebagai"}


def jawaban_rusak(teks: str) -> bool:
    """Tulisan ulang yang tidak layak dipilih: kosong, beraksara asing (Mandarin, Arab, ...),
    kata yang sama tiga kali berturut-turut, atau kalimat menggantung (berakhir dengan kata
    depan/sambung)."""
    kata = re.findall(r"\w+", teks.lower())
    if not kata or AKSARA_ASING.search(teks):
        return True
    if any(kata[i] == kata[i + 1] == kata[i + 2] for i in range(len(kata) - 2)):
        return True
    return kata[-1] in KATA_GANTUNG


# --- perapian ejaan berbasis aturan, dijalankan sebelum model --------------------
SINGKATAN = {
    "yg": "yang", "dgn": "dengan", "dg": "dengan", "sblm": "sebelum", "sblum": "sebelum",
    "sdh": "sudah", "udh": "sudah", "udah": "sudah", "blm": "belum", "tdk": "tidak",
    "gak": "tidak", "ga": "tidak", "nggak": "tidak", "engga": "tidak", "knp": "kenapa",
    "napa": "mengapa", "gmn": "bagaimana", "gimana": "bagaimana", "bgmn": "bagaimana",
    "hrs": "harus", "dlu": "dulu", "dl": "dulu", "krn": "karena", "karna": "karena",
    "utk": "untuk", "jd": "jadi", "jdi": "jadi", "bs": "bisa", "bsa": "bisa", "org": "orang",
    "olhraga": "olahraga", "olahrga": "olahraga", "olhrg": "olahraga", "sm": "sama",
    "spt": "seperti", "kalo": "kalau", "klo": "kalau", "tp": "tapi", "aja": "saja",
    "dr": "dari", "pd": "pada", "dlm": "dalam", "msh": "masih", "lg": "lagi",
    "skrg": "sekarang", "tau": "tahu", "mksd": "maksud", "dpt": "dapat", "bnyk": "banyak",
    "byk": "banyak", "sy": "saya", "aq": "aku", "ap": "apa", "apaan": "apa", "brp": "berapa",
    "kpn": "kapan", "dmn": "di mana", "gt": "begitu", "emg": "memang", "trus": "terus",
}


def rapikan_aturan(teks: str) -> str:
    def ganti(m):
        w = m.group(0)
        return SINGKATAN.get(w.lower(), w)
    t = re.sub(r"[A-Za-z]+", ganti, teks.strip())
    t = re.sub(r"([?!.])\1+", r"\1", t)
    return re.sub(r"\s+", " ", t).strip()


_KATA_TANYA = re.compile(r"\b(apa|apakah|siapa|mengapa|kenapa|bagaimana|gimana|kapan|berapa|"
                         r"di ?mana|mana|sebutkan|jelaskan|bolehkah|bisakah|haruskah|"
                         r"perlukah|bukankah)\b", re.I)


def _mirip(a: str, b: str) -> bool:
    """Dua kata dianggap sama bila hanya beda salah ketik ("manfat"/"manfaat") atau singkatan
    ("sblm"/"sebelum": huruf awal sama dan hurufnya berurutan di kata panjangnya)."""
    a, b = a.lower(), b.lower()
    if a == b:
        return True
    pendek, panjang = sorted((a, b), key=len)
    if len(pendek) >= 2 and pendek[0] == panjang[0]:
        it = iter(panjang)
        if all(c in it for c in pendek):
            return True
    return difflib.SequenceMatcher(None, a, b).ratio() >= 0.75


def rapikan_sah(asli: str, hasil: str) -> bool:
    """Pagar Perceive: hasil perapian Qwen harus tetap PERTANYAAN YANG SAMA, hanya ejaan dan
    tanda bacanya yang dibetulkan. Ditolak bila Qwen malah menjawab, menambah isi, atau
    mengganti pertanyaannya; sistem lalu memakai hasil perapian berbasis aturan."""
    if not hasil:
        return False
    if len(hasil) > 1.5 * len(asli) + 15:                 # jauh lebih panjang: menjawab
        return False
    a, h = set(kata_isi(asli)), set(kata_isi(hasil))
    semua_h = set(re.findall(r"\w+", hasil.lower()))     # "knp" boleh menjadi "kenapa"
    if a and sum(any(_mirip(x, y) for y in semua_h) for x in a) / len(a) < 0.6:  # kata hilang
        return False
    if h and sum(not any(_mirip(x, y) for x in a) for y in h) / len(h) > 0.4:  # kata baru
        return False
    asli_bertanya = asli.rstrip().endswith("?") or bool(_KATA_TANYA.search(asli))
    hasil_bertanya = hasil.rstrip().endswith("?") or bool(_KATA_TANYA.search(hasil))
    return hasil_bertanya or not asli_bertanya


# --- keadaan bersama -------------------------------------------------------------
class Keadaan(TypedDict, total=False):
    # masukan
    pertanyaan_mentah: str
    mapel: str
    skenario: str
    kelas_paksa: int | None
    interaktif: bool        # True di UI; False saat pengujian otomatis (tanpa tanya balik)
    paksa_jawab: bool       # sudah MAKS_TANYA_BALIK kali bertanya balik: langsung jawab
    sekolah: int | None     # sekolah penanya: buku unggahan sekolahnya ikut dicari
    # Perceive
    pertanyaan_bersih: str
    jelas: bool
    p_jelas: float
    ada_isi: bool           # masukan memuat kata pelajaran walau belum jelas
    saran_pertanyaan: str   # usulan pertanyaan lengkap saat Perceive bertanya balik
    # Plan
    kelas: int
    keyakinan_kelas: float
    sebaran_kelas: dict     # gabungan, yang dipakai memutuskan
    sebaran_llm: dict       # dari probe Qwen
    sebaran_buku: dict      # dari letak materi di buku kelas 1-6
    bukti_kelas: list       # potongan buku terbaik per kelas
    kandidat_kelas: list    # dua kelas teratas, ditawarkan saat minta konfirmasi
    perlu_konfirmasi: bool
    sumber_kelas: str
    topik: str
    # Act
    konteks: dict | None
    calon_konteks: list
    metode_cari: str
    adapter_aktif: bool
    skor_konteks: float | None   # skor potongan terpilih (reranker)
    konteks_relevan: bool        # pengecekan 1: potongan memang relevan?
    konteks_lintas_kelas: int    # kelas buku asal potongan bila diambil dari kelas lain
    tidak_ada_materi: bool       # materi tidak ditemukan di buku kelas mana pun
    jawaban: str
    putaran: int
    # Reflect
    pemeriksaan: dict
    arahan: str | None
    riwayat: Annotated[list, operator.add]
    # keluaran
    jawaban_akhir: str
    pemeriksaan_akhir: dict | None
    putaran_terpilih: int
    status: str                                 # 'lolos' | 'batas' | 'tolak'
    jejak: Annotated[list, operator.add]        # catatan waktu tiap agen


class Sistem:
    """Merangkai empat agen dan tiga sumber daya bersama."""

    def __init__(self, llm, pencari, kontrol: KontrolKeterbacaan,
                 folder_log: str | None = None):
        self.llm, self.pencari, self.kontrol = llm, pencari, kontrol
        self.folder_log = folder_log
        self.kunci = threading.Lock()     # satu model di GPU: satu pertanyaan sekaligus
        self.graf = self._bangun_graf()

    # ---------------------------------------------------------------- agen 1
    def perceive(self, s: Keadaan) -> dict:
        t0 = time.perf_counter()
        aturan = rapikan_aturan(s["pertanyaan_mentah"])
        bersih = self.llm.hasilkan(
            [{"role": "system", "content":
              "Kamu merapikan tulisan siswa sekolah dasar. Perbaiki singkatan, salah ketik, "
              "dan tanda baca tanpa mengubah maksudnya. JANGAN menjawab pertanyaannya dan "
              "jangan menambah kata baru. Tulis ulang pertanyaan yang sama saja."},
             {"role": "user", "content": aturan}], maks_token=48, tugas="rapikan")
        bersih = bersih.strip().strip('"').splitlines()[0].strip() if bersih.strip() else ""
        # pagar: hasil yang kosong, menjawab, atau mengganti pertanyaan diabaikan
        if not rapikan_sah(aturan, bersih):
            bersih = aturan
        p = self.llm.probe(
            [{"role": "system", "content": "Kamu memeriksa masukan siswa sekolah dasar."},
             {"role": "user", "content":
              f"Masukan: {bersih}\n\nApakah masukan ini pertanyaan atau soal (termasuk "
              "kalimat rumpang) tentang pelajaran sekolah yang cukup jelas untuk dijawab? "
              "Jawab YA atau TIDAK."}], ["YA", "TIDAK"], tugas="jelas")
        jelas = p["YA"] >= 0.5 and len(bersih.split()) >= 2
        isi = [w for w in kata_isi(bersih) if w not in SAPAAN]
        # sudah bertanya balik MAKS_TANYA_BALIK kali: pertanyaan yang memuat kata pelajaran
        # langsung dijawab, tidak ditanya balik lagi
        if s.get("paksa_jawab") and isi:
            jelas = True
        keluar = {"pertanyaan_bersih": bersih, "jelas": jelas, "p_jelas": round(p["YA"], 3),
                  "ada_isi": bool(isi)}
        # Keputusan Perceive: masukan kabur tetapi memuat kata pelajaran -> tanya balik
        # dengan usulan pertanyaan lengkap, bukan langsung ditolak.
        if not jelas and isi and s.get("interaktif", True):
            nama = MAPEL[s["mapel"]]["nama"]
            saran = self.llm.hasilkan(
                [{"role": "system", "content":
                  f"Masukan siswa SD berikut belum berupa pertanyaan yang jelas. Tulis SATU "
                  f"pertanyaan pelajaran {nama} yang paling mungkin dimaksud siswa, singkat, "
                  "memakai kata-kata siswa itu, diakhiri tanda tanya. Tulis pertanyaannya saja."},
                 {"role": "user", "content": bersih}], maks_token=32, tugas="saran")
            saran = saran.strip().strip('"').splitlines()[0].strip() if saran.strip() else ""
            if not saran or len(saran) > 160:
                saran = f"Apa yang dimaksud dengan {max(isi, key=len)}?"
            keluar["saran_pertanyaan"] = saran if saran.endswith("?") else saran.rstrip(".") + "?"
        keluar["jejak"] = [{"agen": "Perceive", "detik": round(time.perf_counter() - t0, 2)}]
        return keluar

    # ---------------------------------------------------------------- agen 2
    def plan(self, s: Keadaan) -> dict:
        t0 = time.perf_counter()
        nama = MAPEL[s["mapel"]]["nama"]
        keluar: dict[str, Any] = {"perlu_konfirmasi": False}
        if s.get("kelas_paksa"):
            kelas, yakin, sebaran, sumber = int(s["kelas_paksa"]), 1.0, {}, "pengguna"
        else:
            # Bukti 1 - bahasa dan materi menurut Qwen: peluang token "1".."6"
            pil = [str(k) for k in range(1, 7)]
            p_llm = self.llm.probe(
                [{"role": "system", "content":
                  "Kamu guru sekolah dasar. Tentukan kelas (1 sampai 6) yang paling cocok "
                  "untuk pertanyaan siswa berikut, berdasarkan materi dan bahasanya. "
                  "Jawab dengan satu angka saja."},
                 {"role": "user", "content": f"Mata pelajaran: {nama}\nPertanyaan: "
                                             f"{s['pertanyaan_bersih']}"}], pil, tugas="kelas")
            # Bukti 2 - letak materi: pertanyaan dicari di buku kelas 1-6 sekaligus (alat).
            p_buku, bukti = None, []
            if hasattr(self.pencari, "sebaran_kelas"):
                sb = self.pencari.sebaran_kelas(s["pertanyaan_bersih"], s["mapel"])
                p_buku, bukti = sb["peluang"], sb["bukti"]
            w = BOBOT_BUKU if p_buku else 0.0
            sebaran = {k: (1 - w) * p_llm[k] + w * (p_buku[k] if p_buku else 0) for k in pil}
            kelas = int(max(sebaran, key=sebaran.get))
            yakin, sumber = sebaran[str(kelas)], "Plan Agent"
            sebaran = {k: round(v, 3) for k, v in sebaran.items()}
            keluar.update(sebaran_llm={k: round(v, 3) for k, v in p_llm.items()},
                          sebaran_buku=p_buku or {}, bukti_kelas=bukti,
                          kandidat_kelas=[int(k) for k in sorted(sebaran, key=lambda k: -sebaran[k])[:2]])
            # Keputusan Plan: ragu -> minta konfirmasi siswa, bukan menebak diam-diam
            if yakin < AMBANG_KONFIRMASI and s.get("interaktif", True) and not s.get("paksa_jawab"):
                keluar["perlu_konfirmasi"] = True
        topik = self.llm.hasilkan(
            [{"role": "system", "content": "Sebutkan topik pertanyaan dalam satu sampai tiga "
                                           "kata saja, tanpa kalimat lain."},
             {"role": "user", "content": f"Mata pelajaran: {nama}\nPertanyaan: "
                                         f"{s['pertanyaan_bersih']}"}], maks_token=12,
            tugas="topik")
        keluar.update(kelas=kelas, keyakinan_kelas=round(yakin, 3), sebaran_kelas=sebaran,
                      sumber_kelas=sumber, topik=topik.strip().strip(".").lower()[:40],
                      jejak=[{"agen": "Plan", "detik": round(time.perf_counter() - t0, 2)}])
        return keluar

    # ---------------------------------------------------------------- agen 3
    def _relevan(self, h) -> bool:
        f = getattr(self.pencari, "relevan", None)
        return f(h) if f else h.konteks is not None

    def act(self, s: Keadaan) -> dict:
        t0 = time.perf_counter()
        pakai_adapter, pakai_konteks = SKENARIO[s.get("skenario", "S4")]
        putaran = s.get("putaran", 0) + 1
        keluar: dict[str, Any] = {"putaran": putaran}

        # percabangan kedua: konteks dicari sekali, dipakai ulang di putaran berikutnya
        konteks = s.get("konteks")
        if pakai_konteks and putaran == 1:
            kw = {"sekolah": s["sekolah"]} if s.get("sekolah") else {}
            h = self.pencari.cari(s["pertanyaan_bersih"], s["mapel"], s["kelas"], **kw)
            konteks = h.konteks
            keluar.update(konteks=konteks, calon_konteks=h.calon, metode_cari=h.metode,
                          skor_konteks=getattr(h, "skor", None), konteks_relevan=self._relevan(h))
            # Pengecekan 1: materi tidak ada di buku kelas siswa -> cari di buku kelas lain
            # pada mapel yang sama. Hanya di UI; pengujian otomatis tetap memakai saringan
            # kelas apa adanya agar skenario S3/S4 sesuai rancangan percobaan.
            if (not keluar["konteks_relevan"] and s.get("interaktif", True)
                    and hasattr(self.pencari, "cari_lintas_kelas")):
                h2 = self.pencari.cari_lintas_kelas(s["pertanyaan_bersih"], s["mapel"])
                if self._relevan(h2):
                    konteks = h2.konteks
                    keluar.update(konteks=konteks, skor_konteks=h2.skor, konteks_relevan=True,
                                  konteks_lintas_kelas=int(konteks["kelas"]))
                else:
                    keluar.update(tidak_ada_materi=True, jejak=[{
                        "agen": "Act", "putaran": putaran,
                        "detik": round(time.perf_counter() - t0, 2)}])
                    return keluar
        elif putaran == 1:
            keluar.update(konteks=None, calon_konteks=[], metode_cari="-")

        aktif = self.llm.pasang_adapter(s["mapel"], s["kelas"]) if pakai_adapter else False
        if not pakai_adapter:
            self.llm.lepas_adapter()
        teks_konteks = konteks["teks"] if (pakai_konteks and konteks) else None
        if putaran == 1:
            jawaban = self.llm.hasilkan(pesan_jawab(s["mapel"], s["pertanyaan_bersih"], teks_konteks),
                                        MAKS_TOKEN, tugas="jawab")
        else:                      # arahan Reflect Agent dikerjakan model dasar (adapter mati)
            jawaban = self.llm.hasilkan(
                pesan_tulis_ulang(s["mapel"], s["kelas"], s["pertanyaan_bersih"], teks_konteks,
                                  s["jawaban"], s["arahan"]), MAKS_TOKEN, tugas="tulis_ulang")
        keluar.update(jawaban=jawaban, adapter_aktif=aktif,
                      jejak=[{"agen": "Act", "putaran": putaran,
                              "detik": round(time.perf_counter() - t0, 2)}])
        return keluar

    # ---------------------------------------------------------------- agen 4
    def reflect(self, s: Keadaan) -> dict:
        t0 = time.perf_counter()
        # Kendali keterbacaan: rumus deterministik (2.4), tidak berubah
        p = self.kontrol.periksa(s["jawaban"], s["mapel"], s["kelas"]).dict()
        # Pengecekan 2, terpisah dari kendali keterbacaan: apakah jawaban menjawab
        # pertanyaan dan sesuai isi buku? Model dasar (adapter mati) sebagai penilai.
        _, pakai_konteks = SKENARIO[s.get("skenario", "S4")]
        kon = s.get("konteks") if pakai_konteks else None
        isi = (f"Pertanyaan: {s['pertanyaan_bersih']}\n"
               + (f"Potongan buku: {kon['teks']}\n" if kon else "")
               + f"Jawaban: {s['jawaban']}\n\nApakah jawaban ini menjawab pertanyaan"
               + (" dan isinya sesuai dengan potongan buku" if kon else "")
               + "? Jawab YA atau TIDAK.")
        p_rel = self.llm.probe([{"role": "system", "content":
                                 "Kamu guru sekolah dasar yang memeriksa jawaban siswa."},
                                {"role": "user", "content": isi}], ["YA", "TIDAK"],
                               tugas="relevan")["YA"]
        relevan = p_rel >= AMBANG_RELEVAN_JAWABAN
        arahan = p["arahan"]
        if not relevan:
            arahan = (f"Jawabanmu belum menjawab pertanyaan \"{s['pertanyaan_bersih']}\". "
                      "Tulis ulang jawaban yang benar-benar menjawab pertanyaan itu"
                      + (", HANYA berdasarkan potongan buku di atas" if kon else "")
                      + f", dalam 1-2 kalimat sederhana untuk siswa kelas {s['kelas']}.")
        utuh = s["putaran"] == 1 or not jawaban_rusak(s["jawaban"])
        p = {**p, "lolos_keterbacaan": p["lolos"], "relevan": relevan, "utuh": utuh,
             "p_relevan": round(p_rel, 3), "lolos": p["lolos"] and relevan and utuh,
             "arahan": arahan}
        catatan = {"putaran": s["putaran"], "jawaban": s["jawaban"], **p}
        return {"pemeriksaan": p, "arahan": arahan, "riwayat": [catatan],
                "jejak": [{"agen": "Reflect", "putaran": s["putaran"],
                           "detik": round(time.perf_counter() - t0, 3)}]}

    # ---------------------------------------------------------------- penutup
    @staticmethod
    def pilih(s: Keadaan) -> dict:
        # tulisan ulang yang rusak (kata berulang, kalimat menggantung) tidak dipilih
        riwayat = [r for r in s["riwayat"] if r.get("utuh", True)] or s["riwayat"]
        # jawaban yang menjawab pertanyaan selalu didahulukan
        cocok = [r for r in riwayat if r.get("relevan", True)]
        kandidat = cocok or riwayat
        lolos = [r for r in kandidat if r["lolos"]]
        if lolos:
            akhir, status = lolos[-1], "lolos"
        else:   # jarak keterbacaan terkecil; bila seri, putaran yang lebih awal
            akhir = min(kandidat, key=lambda r: (r["jarak"], r["putaran"]))
            status = "batas" if cocok else "tidak_relevan"
        return {"jawaban_akhir": akhir["jawaban"], "pemeriksaan_akhir": akhir,
                "putaran_terpilih": akhir["putaran"], "status": status}

    @staticmethod
    def tanpa_materi(s: Keadaan) -> dict:
        return {"jawaban_akhir": "Maaf, materi ini belum ada di buku pelajaranmu. Coba tanyakan "
                                 "ke gurumu, atau tanyakan hal lain dari bukumu, ya.",
                "pemeriksaan_akhir": None, "status": "tidak_ada_materi"}

    @staticmethod
    def tolak(s: Keadaan) -> dict:
        return {"jawaban_akhir": "Maaf, aku belum paham maksudnya. Coba tulis pertanyaanmu "
                                 "lagi dengan lebih jelas, ya.",
                "pemeriksaan_akhir": None, "status": "tolak", "putaran": 0}

    @staticmethod
    def tanya_balik(s: Keadaan) -> dict:
        return {"jawaban_akhir": f"Aku belum yakin maksudmu. Apakah maksudmu: "
                                 f"\"{s['saran_pertanyaan']}\"",
                "pemeriksaan_akhir": None, "status": "tanya_balik", "putaran": 0}

    @staticmethod
    def konfirmasi(s: Keadaan) -> dict:
        kandidat = s.get("kandidat_kelas") or [s["kelas"]]
        tebak = " atau ".join(f"kelas {k}" for k in kandidat[:2])
        return {"jawaban_akhir": f"Supaya jawabanku pas, kamu kelas berapa? "
                                 f"Sepertinya pertanyaan ini untuk {tebak}.",
                "pemeriksaan_akhir": None, "status": "konfirmasi_kelas", "putaran": 0}

    def _bangun_graf(self):
        g = StateGraph(Keadaan)
        for nama, fn in [("perceive", self.perceive), ("plan", self.plan), ("act", self.act),
                         ("reflect", self.reflect), ("pilih", self.pilih), ("tolak", self.tolak),
                         ("tanya_balik", self.tanya_balik), ("konfirmasi", self.konfirmasi),
                         ("tanpa_materi", self.tanpa_materi)]:
            g.add_node(nama, fn)
        g.add_edge(START, "perceive")
        g.add_conditional_edges(
            "perceive",
            lambda s: "plan" if s["jelas"] else ("tanya_balik" if s.get("saran_pertanyaan")
                                                 else "tolak"),
            {"plan": "plan", "tanya_balik": "tanya_balik", "tolak": "tolak"})
        g.add_conditional_edges("plan", lambda s: "konfirmasi" if s.get("perlu_konfirmasi")
                                else "act", {"act": "act", "konfirmasi": "konfirmasi"})
        g.add_conditional_edges("act", lambda s: "tanpa_materi" if s.get("tidak_ada_materi")
                                else "reflect", {"reflect": "reflect",
                                                 "tanpa_materi": "tanpa_materi"})
        g.add_conditional_edges(
            "reflect",
            lambda s: "pilih" if (s["pemeriksaan"]["lolos"] or s["putaran"] >= MAKS_PUTARAN)
            else "act", {"pilih": "pilih", "act": "act"})
        for akhir in ("pilih", "tolak", "tanya_balik", "konfirmasi", "tanpa_materi"):
            g.add_edge(akhir, END)
        return g.compile()

    # ---------------------------------------------------------------- pemanggilan
    def _awal(self, pertanyaan, mapel, kelas=None, skenario="S4", interaktif=True,
              paksa_jawab=False, sekolah=None) -> Keadaan:
        if mapel not in MAPEL:
            raise ValueError(f"mata pelajaran tidak dikenal: {mapel}")
        if skenario not in SKENARIO:
            raise ValueError(f"skenario tidak dikenal: {skenario}")
        return {"pertanyaan_mentah": pertanyaan, "mapel": mapel, "skenario": skenario,
                "kelas_paksa": kelas, "interaktif": interaktif, "paksa_jawab": paksa_jawab,
                "sekolah": sekolah, "putaran": 0,
                "riwayat": [], "jejak": []}

    def alir(self, pertanyaan: str, mapel: str, kelas: int | None = None,
             skenario: str = "S4", interaktif: bool = True, paksa_jawab: bool = False,
             sekolah: int | None = None) -> Iterator[tuple[str, dict]]:
        """Menghasilkan (nama_agen, perubahan_keadaan) setiap kali satu agen selesai,
        lalu ('selesai', keadaan_akhir). interaktif=False dipakai pengujian otomatis:
        Perceive tidak bertanya balik dan Plan tidak meminta konfirmasi."""
        awal = self._awal(pertanyaan, mapel, kelas, skenario, interaktif, paksa_jawab, sekolah)
        with self.kunci:
            akhir = dict(awal)
            for langkah in self.graf.stream(awal, stream_mode="updates"):
                for simpul, ubah in langkah.items():
                    ubah = ubah or {}
                    for k, v in ubah.items():
                        akhir[k] = akhir.get(k, []) + v if k in ("riwayat", "jejak") else v
                    yield simpul, ubah
        akhir["waktu"] = dt.datetime.now().isoformat(timespec="seconds")
        self._catat(akhir)
        yield "selesai", akhir

    def tanya(self, pertanyaan: str, mapel: str, kelas: int | None = None,
              skenario: str = "S4", interaktif: bool = True, paksa_jawab: bool = False,
              sekolah: int | None = None) -> dict:
        akhir = {}
        for simpul, isi in self.alir(pertanyaan, mapel, kelas, skenario, interaktif,
                                     paksa_jawab, sekolah):
            if simpul == "selesai":
                akhir = isi
        return akhir

    def _catat(self, keadaan: dict):
        """Kebutuhan fungsional 8: seluruh jejak pemrosesan dicatat untuk evaluasi."""
        if not self.folder_log:
            return
        os.makedirs(self.folder_log, exist_ok=True)
        path = os.path.join(self.folder_log, f"jejak_{dt.date.today():%Y%m%d}.jsonl")
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(keadaan, ensure_ascii=False, default=str) + "\n")
