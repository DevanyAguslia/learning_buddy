"""Layanan Pencarian Konteks - sumber daya bersama, bukan agen (Subbab 3.1.3.2).

Basis pengetahuan berisi potongan Recursive buku Kurikulum Merdeka (tb.impor_potongan).
Pencarian dua tahap, disaring jenjang kelas DAN mata pelajaran:
  1. bi-encoder mengambil K_CALON = 20 potongan terdekat,
  2. cross-encoder menilai kedua puluh calon; KIRIM = 3 potongan terbaik dikirim ke Act
     Agent. Potongan yang isinya sudah tercakup potongan terpilih (>= 60% kata isi sama)
     dilewati agar tiga potongan itu tidak mengulang teks yang sama.
Bila TB_STRATEGI berisi lebih dari satu strategi (mis. "SDCS,Recursive"), K_CALON calon
diambil dari indeks setiap strategi dan cross-encoder memilih di antara semuanya; strategi
dicatat pada setiap potongan (kolom "strategi").

Basis data vektor memakai FAISS. FAISS tidak punya saringan metadata, jadi dibuat indeks
kecil per strategi per mata pelajaran per kelas: menyaring "PJOK kelas 4" berarti memilih
indeks Recursive_PJOK_k4. Pencarian di dalam indeks bersifat eksak (IndexFlatIP atas
vektor yang dinormalkan = kesamaan kosinus, rumus 2.3).

Penyandi (bi-encoder) dapat diganti lewat TB_MODEL_EMBEDDING. Setiap penyandi punya folder
indeksnya sendiri (data/faiss/<nama-model>), jadi beberapa penyandi dapat dibandingkan
tanpa saling menimpa (lihat tb.uji_embedding).

PencariBM25 adalah pengganti tanpa model untuk mencoba alur di laptop, BUKAN untuk angka
penelitian.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
from collections import Counter
from dataclasses import dataclass, field

import numpy as np

from .korpus import MAPEL
from .keterbacaan import kata_isi

AKAR = os.path.dirname(os.path.dirname(__file__))
PATH_POTONGAN = os.path.join(AKAR, "data", "potongan.jsonl")

STRATEGI = tuple(s.strip() for s in os.environ.get("TB_STRATEGI", "Recursive").split(",")
                 if s.strip())
K_CALON = 20       # calon per strategi
KIRIM = int(os.environ.get("TB_KIRIM", "3"))
TUMPANG = 0.6      # potongan dilewati bila >= 60% kata isinya sudah ada di potongan terpilih
N_SEBARAN = 3      # calon per kelas per strategi yang dibandingkan untuk Plan Agent
# Penyandi penelitian: Qwen3-Embedding-4B (dimensi 2.560), dijalankan fp16 di GPU kedua
# Kaggle T4 x2 sehingga tidak berebut memori dengan Qwen2.5-7B di GPU pertama.
MODEL_EMBEDDING = os.environ.get("TB_MODEL_EMBEDDING", "Qwen/Qwen3-Embedding-4B")
MODEL_RERANKER = os.environ.get("TB_MODEL_RERANKER", "BAAI/bge-reranker-v2-m3")

# Cara setiap penyandi diberi masukan. Beberapa model menuntut awalan atau instruksi
# khusus untuk kueri; tanpa itu kinerjanya turun tanpa pesan galat apa pun.
INSTRUKSI_QWEN = ("Instruct: Given a question from an Indonesian elementary school student, "
                  "retrieve the textbook passage that answers it\nQuery:")
PENYANDI = {
    "BAAI/bge-m3": {},
    "Alibaba-NLP/gte-multilingual-base": {
        "trust_remote_code": True,
        # bug unpad_inputs (G2) muncul saat jalur cepat xformers aktif; dimatikan
        "config_kwargs": {"unpad_inputs": False, "use_memory_efficient_attention": False}},
    "sentence-transformers/paraphrase-multilingual-mpnet-base-v2": {},
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2": {},
    "Qwen/Qwen3-Embedding-0.6B": {"kueri": INSTRUKSI_QWEN},
    "Qwen/Qwen3-Embedding-4B": {"kueri": INSTRUKSI_QWEN},
    "intfloat/multilingual-e5-large": {"kueri": "query: ", "dokumen": "passage: "},
}


def slug(nama: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", nama.split("/")[-1].lower()).strip("-")


def folder_indeks(nama: str = MODEL_EMBEDDING) -> str:
    akar = os.environ.get("TB_FAISS", os.path.join(AKAR, "data", "faiss"))
    return os.path.join(akar, slug(nama))


def boleh_dicari(p: dict) -> bool:
    """Halaman soal latihan berisi pertanyaan, bukan jawaban, jadi tidak dijadikan konteks."""
    return p.get("jenis") != "evaluasi"


def perangkat_cari(device: str | None = None) -> str:
    """Kaggle T4 x2: penyandi di GPU kedua agar tidak berebut memori dengan Qwen."""
    import torch
    if device or os.environ.get("TB_DEVICE_CARI"):
        return device or os.environ["TB_DEVICE_CARI"]
    if not torch.cuda.is_available():
        return "cpu"
    return "cuda:1" if torch.cuda.device_count() > 1 else "cuda"


def _kw_dtype(device: str) -> dict:
    import torch
    return {"model_kwargs": {"torch_dtype": torch.float16}} if device.startswith("cuda") else {}


def muat_penyandi(nama: str = MODEL_EMBEDDING, device: str | None = None):
    from sentence_transformers import SentenceTransformer
    device = perangkat_cari(device)
    cfg = PENYANDI.get(nama, {})
    kw = _kw_dtype(device)
    if cfg.get("trust_remote_code"):
        kw["trust_remote_code"] = True
    if cfg.get("config_kwargs"):
        kw["config_kwargs"] = cfg["config_kwargs"]
    return SentenceTransformer(nama, device=device, **kw)


def sandikan(model, nama: str, teks: list[str], kueri: bool, batch: int = 16):
    """Vektor float32 yang sudah dinormalkan, dengan awalan/instruksi sesuai model."""
    import numpy as np
    cfg = PENYANDI.get(nama, {})
    awalan = cfg.get("kueri" if kueri else "dokumen", "")
    if awalan and not awalan.endswith((" ", "\n", ":")):
        awalan += " "
    v = model.encode([awalan + t if awalan else t for t in teks], batch_size=batch,
                     normalize_embeddings=True, show_progress_bar=False,
                     convert_to_numpy=True)
    v = np.asarray(v, dtype="float32")
    # pagar mutu: model keluarga Qwen dapat meluap (inf/NaN) pada fp16 di T4
    if not np.isfinite(v).all():
        raise RuntimeError(f"{nama} menghasilkan vektor tak hingga/NaN; jalankan dengan "
                           "dtype float32 atau bfloat16")
    return v


def bangun_indeks_faiss(potongan: list[dict], nama: str = MODEL_EMBEDDING,
                        device: str | None = None, batch: int = 16, model=None,
                        vektor=None) -> str:
    """Menyandikan potongan yang boleh dicari lalu menyimpan indeks FAISS per strategi per
    mapel per kelas. vektor (opsional) dipakai ulang bila sudah dihitung (urutan = potongan
    yang boleh dicari)."""
    import faiss
    import numpy as np
    ps = [p for p in potongan if boleh_dicari(p)]
    if vektor is None:
        model = model or muat_penyandi(nama, device)
        vektor = sandikan(model, nama, [teks_sandi(p) for p in ps], kueri=False, batch=batch)
    folder = folder_indeks(nama)
    os.makedirs(folder, exist_ok=True)
    daftar = sorted({strategi_dari(p) for p in ps})
    for s in daftar:
        for m in MAPEL:
            for k in range(1, 7):
                idx = [i for i, p in enumerate(ps) if strategi_dari(p) == s
                       and p["mapel"] == m and int(p["kelas"]) == k]
                ix = faiss.IndexFlatIP(vektor.shape[1])
                if idx:
                    ix.add(np.ascontiguousarray(vektor[idx]))
                faiss.write_index(ix, os.path.join(folder, f"{s}_{m}_k{k}.index"))
                with open(os.path.join(folder, f"{s}_{m}_k{k}.json"), "w", encoding="utf-8") as f:
                    json.dump([ps[i]["id"] for i in idx], f)
    with open(os.path.join(folder, "meta.json"), "w", encoding="utf-8") as f:
        json.dump({"model": nama, "dimensi": int(vektor.shape[1]), "potongan": len(ps),
                   "strategi": daftar,
                   "dibuat": dt.datetime.now().isoformat(timespec="seconds")}, f, indent=1)
    print(f"indeks FAISS: {len(ps)} potongan ({', '.join(daftar)}), dimensi {vektor.shape[1]}, "
          f"{nama} -> {folder}")
    return folder


def strategi_dari(p: dict) -> str:
    return p.get("strategi") or "potong-lama"     # potongan tb.potong tanpa kolom strategi


def teks_sandi(p: dict) -> str:
    """Teks yang disandikan bi-encoder: SDCS memakai judul bagian + isi (sama dengan
    eksperimen chunking); cross-encoder dan Act Agent selalu memakai p["teks"]."""
    return p.get("teks_indeks") or p["teks"]


def pilih_beragam(urut: list, n: int = KIRIM) -> list:
    """urut: [(potongan, skor), ...] terurut skor menurun. Mengambil n teratas, melewati
    potongan yang >= TUMPANG kata isinya sudah ada di potongan terpilih."""
    pilih, tercakup = [], Counter()
    for p, s in urut:
        kata = Counter(kata_isi(p["teks"]))
        if pilih and kata and sum((kata & tercakup).values()) / sum(kata.values()) >= TUMPANG:
            continue
        pilih.append((p, s))
        tercakup |= kata
        if len(pilih) == n:
            break
    return pilih


def gabung_konteks(pilih: list) -> dict | None:
    """Potongan teratas menjadi kepala konteks (buku, kelas, halaman); "teks" berisi
    seluruh potongan terpilih yang dipisah baris kosong, itulah yang dibaca Act Agent."""
    if not pilih:
        return None
    k = _lengkapi(pilih[0][0])
    k.pop("teks_indeks", None)
    k["teks"] = "\n\n".join(p["teks"] for p, _ in pilih)
    k["potongan"] = [{"id": p["id"], "strategi": strategi_dari(p), "kelas": int(p["kelas"]),
                      "halaman": p.get("halaman"), "halaman_buku": p.get("halaman_buku"),
                      "bab": p.get("bab", ""), "skor": None if s is None else round(float(s), 4),
                      "teks": p["teks"]} for p, s in pilih]
    return k


@dataclass
class HasilCari:
    metode: str
    konteks: dict | None                  # potongan terpilih (gabung_konteks) beserta judul buku
    calon: list[dict] = field(default_factory=list)
    skor: float | None = None             # skor potongan teratas (reranker atau BM25)


def _baca_ambang(folder: str) -> float | None:
    """Ambang relevansi hasil kalibrasi tb.evaluasi_pencarian (None = belum dikalibrasi)."""
    p = os.path.join(folder, "ambang_relevan.json")
    if os.environ.get("TB_AMBANG_RELEVAN"):
        return float(os.environ["TB_AMBANG_RELEVAN"])
    if os.path.exists(p):
        return float(json.load(open(p, encoding="utf-8"))["ambang"])
    return None


class _Relevansi:
    """Pengecekan 1 (Act Agent): apakah potongan terpilih memang relevan?"""
    ambang: float | None = None

    def relevan(self, h: HasilCari) -> bool:
        if h.konteks is None:
            return False
        if self.ambang is None or h.skor is None:
            return True                  # belum dikalibrasi: dianggap relevan
        return h.skor >= self.ambang


def muat_potongan(path: str = PATH_POTONGAN) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f]


def _lengkapi(p: dict) -> dict:
    p = dict(p)
    if not p.get("buku"):                 # potongan buku sekolah sudah membawa judulnya
        p["buku"] = MAPEL[p["mapel"]]["buku"][int(p["kelas"])][1]
    return p


def _ke_sebaran(terbaik_per_kelas: dict[int, float], bukti: list | None = None) -> dict:
    """Plan Agent: "materi ini ada di buku kelas berapa?"

    Setiap kelas diwakili SATU nilai, yaitu kecocokan potongan terbaiknya. Bila memakai
    10 potongan teratas lintas kelas, buku yang tebal otomatis mendominasi; pada data uji
    PJOK cara itu hanya tepat 56,9%, sedangkan cara potongan-terbaik-per-kelas tepat 64,5%.
    Nilai keenam kelas lalu dibakukan dan dilewatkan softmax menjadi peluang.
    """
    import math
    if not terbaik_per_kelas:
        return {"peluang": {str(k): round(1 / 6, 3) for k in range(1, 7)}, "bukti": []}
    x = [terbaik_per_kelas.get(k, min(terbaik_per_kelas.values())) for k in range(1, 7)]
    rata = sum(x) / 6
    sd = math.sqrt(sum((v - rata) ** 2 for v in x) / 6) or 1.0
    e = [math.exp((v - max(x)) / sd) for v in x]
    return {"peluang": {str(k): round(v / sum(e), 3) for k, v in zip(range(1, 7), e)},
            "bukti": bukti or []}


class _BukuSekolah:
    """Buku unggahan guru (tb.buku_sekolah): dicari HANYA untuk siswa sekolah itu, pada mapel
    dan kelas yang sama, sebagai calon tambahan di samping buku Kemendikbud."""

    def _buku_awal(self):
        self.buku: dict[int, dict] = {}       # buku_id -> {"sekolah", "mapel", "kelas", ...}

    def _buku_untuk(self, sekolah: int | None, mapel: str, kelas: int) -> list[dict]:
        if not sekolah:
            return []
        return [b for b in self.buku.values()
                if b["sekolah"] == int(sekolah) and b["mapel"] == mapel and b["kelas"] == int(kelas)]

    def hapus_buku(self, buku_id: int) -> None:
        self.buku.pop(int(buku_id), None)


class PencariBM25(_Relevansi, _BukuSekolah):
    metode = "bm25"
    ambang = 3.0         # hanya untuk mode tiruan di laptop; skripsi tidak memakai BM25

    def __init__(self, potongan: list[dict] | None = None):
        from rank_bm25 import BM25Okapi
        self.potongan = [p for p in (potongan or muat_potongan()) if boleh_dicari(p)]
        self._buku_awal()
        self.indeks = {}
        self._resmi: dict[tuple, list[dict]] = {}
        for p in self.potongan:
            self._resmi.setdefault((p["mapel"], int(p["kelas"])), []).append(p)
        for kunci in self._resmi:
            self._bangun(kunci)
        # indeks lintas kelas per mapel, untuk Plan Agent: "materi ini ada di buku kelas berapa"
        self.indeks_mapel = {}
        for m in {p["mapel"] for p in self.potongan}:
            ps = [p for p in self.potongan if p["mapel"] == m]
            self.indeks_mapel[m] = (BM25Okapi([self._token(p["teks"]) for p in ps]), ps)

    @staticmethod
    def _token(teks: str) -> list[str]:
        return kata_isi(teks) or ["_"]

    def _bangun(self, kunci: tuple) -> None:
        """Satu indeks per (mapel, kelas) berisi buku Kemendikbud DAN buku sekolah, agar skor
        BM25 (yang bergantung pada idf korpus) setara; buku sekolah lain disaring saat mencari."""
        from rank_bm25 import BM25Okapi
        ps = self._resmi.get(kunci, []) + [p for b in self.buku.values()
                                           if (b["mapel"], b["kelas"]) == kunci for p in b["ps"]]
        if ps:
            self.indeks[kunci] = (BM25Okapi([self._token(p["teks"]) for p in ps]), ps)
        else:
            self.indeks.pop(kunci, None)

    def tambah_buku(self, meta: dict, potongan: list[dict], folder: str | None = None) -> None:
        b = {**meta, "kelas": int(meta["kelas"]), "ps": [p for p in potongan if boleh_dicari(p)]}
        self.buku[int(meta["id"])] = b
        self._bangun((b["mapel"], b["kelas"]))

    def hapus_buku(self, buku_id: int) -> None:
        b = self.buku.pop(int(buku_id), None)
        if b:
            self._bangun((b["mapel"], b["kelas"]))

    def cari(self, pertanyaan: str, mapel: str, kelas: int, sekolah: int | None = None) -> HasilCari:
        if (mapel, int(kelas)) not in self.indeks:
            return HasilCari(self.metode, None)
        bm, semua = self.indeks[(mapel, int(kelas))]
        skor_semua = bm.get_scores(self._token(pertanyaan))
        boleh = [i for i, p in enumerate(semua) if p.get("sekolah") in (None, sekolah)]
        if not boleh:
            return HasilCari(self.metode, None)
        ps, skor = [semua[i] for i in boleh], [float(skor_semua[i]) for i in boleh]
        urut = sorted(range(len(ps)), key=lambda i: -skor[i])[:K_CALON * max(1, len(STRATEGI))]
        calon = [{"id": ps[i]["id"], "strategi": strategi_dari(ps[i]), "halaman": ps[i]["halaman"],
                  "skor_awal": round(float(skor[i]), 4), "skor_ulang": None,
                  "cuplikan": ps[i]["teks"][:160]} for i in urut]
        pilih = pilih_beragam([(ps[i], float(skor[i])) for i in urut if skor[i] > 0])
        return HasilCari(self.metode, gabung_konteks(pilih), calon,
                         float(skor[urut[0]]) if urut else None)

    def cari_lintas_kelas(self, pertanyaan: str, mapel: str) -> HasilCari:
        bm, ps = self.indeks_mapel[mapel]
        skor = bm.get_scores(self._token(pertanyaan))
        i = int(max(range(len(ps)), key=lambda j: skor[j]))
        if skor[i] <= 0:
            return HasilCari(self.metode, None, [], float(skor[i]))
        k = int(ps[i]["kelas"])              # potongan pendamping dari buku kelas yang sama
        urut = sorted((j for j in range(len(ps)) if int(ps[j]["kelas"]) == k and skor[j] > 0),
                      key=lambda j: -skor[j])
        return HasilCari(self.metode, gabung_konteks(pilih_beragam([(ps[j], float(skor[j]))
                                                                     for j in urut])),
                         [], float(skor[i]))

    def sebaran_kelas(self, pertanyaan: str, mapel: str) -> dict:
        bm, ps = self.indeks_mapel[mapel]
        skor = bm.get_scores(self._token(pertanyaan))
        terbaik, bukti = {}, {}
        for i, p in enumerate(ps):
            k = int(p["kelas"])
            if k not in terbaik or skor[i] > terbaik[k]:
                terbaik[k], bukti[k] = float(skor[i]), p["id"]
        urut = sorted(terbaik, key=lambda k: -terbaik[k])
        return _ke_sebaran(terbaik, [{"kelas": k, "id": bukti[k], "skor": round(terbaik[k], 3)}
                                     for k in urut[:3]])


class PencariSemantik(_Relevansi, _BukuSekolah):
    """Jalur penelitian: penyandi + indeks FAISS per strategi + cross-encoder."""

    def __init__(self, device: str | None = None, nama_model: str = MODEL_EMBEDDING,
                 folder: str | None = None, pakai_reranker: bool = True):
        import faiss
        from sentence_transformers import CrossEncoder
        device = perangkat_cari(device)
        self.nama_model = nama_model
        folder = folder or folder_indeks(nama_model)
        meta_path = os.path.join(folder, "meta.json")
        if not os.path.exists(meta_path):
            raise RuntimeError(f"indeks FAISS belum ada di {folder}. Bangun dulu: "
                               f"python -m tb.basis --vektor")
        meta = json.load(open(meta_path, encoding="utf-8"))
        if meta["model"] != nama_model:
            raise RuntimeError(f"indeks {folder} dibangun dengan {meta['model']}, bukan {nama_model}")
        if "strategi" not in meta:
            raise RuntimeError(f"indeks {folder} masih format lama (tanpa strategi). Bangun ulang: "
                               f"python -m tb.basis --vektor")
        self.strategi = [s for s in STRATEGI if s in meta["strategi"]]
        if not self.strategi:
            raise RuntimeError(f"strategi {STRATEGI} tidak ada di indeks {folder} ({meta['strategi']})")
        teks = {p["id"]: p for p in muat_potongan()}
        self._buku_awal()
        self.indeks = {}
        for s in self.strategi:
            for m in MAPEL:
                for k in range(1, 7):
                    ix = faiss.read_index(os.path.join(folder, f"{s}_{m}_k{k}.index"))
                    ids = json.load(open(os.path.join(folder, f"{s}_{m}_k{k}.json"), encoding="utf-8"))
                    self.indeks[(s, m, k)] = (ix, [teks[i] for i in ids])
        self.embed = muat_penyandi(nama_model, device)
        # TB_DEVICE_RERANK: reranker boleh di GPU walau penyandi di CPU (server satu GPU 16 GB)
        dev_rr = os.environ.get("TB_DEVICE_RERANK") or device
        self.rerank = (CrossEncoder(MODEL_RERANKER, device=dev_rr, max_length=512,
                                    **_kw_dtype(dev_rr)) if pakai_reranker else None)
        self.metode = (f"{slug(nama_model)}+faiss[{'+'.join(self.strategi)}]"
                       + (f"+{slug(MODEL_RERANKER)}" if pakai_reranker else "") + f", {KIRIM} potongan")
        # ambang dikalibrasi pada skala skor reranker, jadi tak berlaku tanpa reranker
        self.ambang = _baca_ambang(folder) if pakai_reranker else None
        if self.ambang is None and pakai_reranker:
            print("PERINGATAN: ambang relevansi belum dikalibrasi; jalankan tb.evaluasi_pencarian")

    def _kueri(self, pertanyaan: str):
        return sandikan(self.embed, self.nama_model, [pertanyaan], kueri=True)

    def tambah_buku(self, meta: dict, potongan: list[dict], folder: str | None = None) -> None:
        """Menyandikan potongan buku sekolah (atau memakai vektor tersimpan di folder) lalu
        membuat indeks FAISS kecil khusus buku itu."""
        import faiss
        ps = [p for p in potongan if boleh_dicari(p)]
        cache = os.path.join(folder, f"vektor_{slug(self.nama_model)}.npy") if folder else None
        v = np.load(cache) if cache and os.path.exists(cache) else None
        if v is None or v.shape[0] != len(ps):
            v = sandikan(self.embed, self.nama_model, [teks_sandi(p) for p in ps], kueri=False)
            if cache:
                np.save(cache, v)
        ix = faiss.IndexFlatIP(v.shape[1])
        ix.add(np.ascontiguousarray(v))
        self.buku[int(meta["id"])] = {**meta, "ps": ps, "ix": ix}

    def _calon(self, v, mapel: str, kelas: int, n: int, sekolah: int | None = None):
        """n calon terdekat dari indeks SETIAP strategi (jadi n x jumlah strategi), ditambah
        n calon dari tiap buku sekolah siswa pada mapel dan kelas yang sama."""
        hasil = []
        kumpulan = [self.indeks[(s, mapel, int(kelas))] for s in self.strategi]
        kumpulan += [(b["ix"], b["ps"]) for b in self._buku_untuk(sekolah, mapel, kelas)]
        for ix, ps in kumpulan:
            if ix.ntotal == 0:
                continue
            skor, pos = ix.search(v, min(n, ix.ntotal))
            hasil += [(ps[j], float(x)) for x, j in zip(skor[0], pos[0]) if j >= 0]
        return hasil

    def _nilai(self, pertanyaan: str, calon: list) -> list[float]:
        if self.rerank is None:
            return [s for _, s in calon]
        return [float(x) for x in self.rerank.predict([(pertanyaan, p["teks"]) for p, _ in calon])]

    def cari(self, pertanyaan: str, mapel: str, kelas: int, sekolah: int | None = None) -> HasilCari:
        calon = self._calon(self._kueri(pertanyaan), mapel, kelas, K_CALON, sekolah)
        if not calon:
            return HasilCari(self.metode, None)
        ulang = self._nilai(pertanyaan, calon)
        urut = sorted(range(len(calon)), key=lambda i: -ulang[i])
        daftar = [{"id": calon[i][0]["id"], "strategi": strategi_dari(calon[i][0]),
                   "halaman": calon[i][0]["halaman"],
                   "skor_awal": round(calon[i][1], 4),           # kesamaan kosinus
                   "skor_ulang": round(ulang[i], 4) if self.rerank is not None else None,
                   "cuplikan": calon[i][0]["teks"][:160]} for i in urut]
        pilih = pilih_beragam([(calon[i][0], ulang[i]) for i in urut])
        return HasilCari(self.metode, gabung_konteks(pilih), daftar, ulang[urut[0]])

    def cari_lintas_kelas(self, pertanyaan: str, mapel: str) -> HasilCari:
        """Potongan terbaik di buku kelas mana pun pada mapel ini (dipakai bila materi
        tidak ada di buku kelas siswa); potongan pendampingnya dari buku kelas yang sama."""
        v = self._kueri(pertanyaan)
        calon = [c for k in range(1, 7) for c in self._calon(v, mapel, k, N_SEBARAN)]
        if not calon:
            return HasilCari(self.metode, None)
        skor = self._nilai(pertanyaan, calon)
        i = int(np.argmax(skor))
        k = int(calon[i][0]["kelas"])
        urut = sorted((j for j in range(len(calon)) if int(calon[j][0]["kelas"]) == k),
                      key=lambda j: -skor[j])
        pilih = pilih_beragam([(calon[j][0], skor[j]) for j in urut])
        return HasilCari(self.metode, gabung_konteks(pilih), [], skor[i])

    def sebaran_kelas(self, pertanyaan: str, mapel: str) -> dict:
        v = self._kueri(pertanyaan)
        calon = [(k, p, s) for k in range(1, 7) for p, s in self._calon(v, mapel, k, N_SEBARAN)]
        if not calon:
            return _ke_sebaran({})
        skor = self._nilai(pertanyaan, [(p, s) for _, p, s in calon])
        terbaik, bukti = {}, {}
        for (k, p, _), s in zip(calon, skor):
            if k not in terbaik or s > terbaik[k]:
                terbaik[k], bukti[k] = s, p["id"]
        urut = sorted(terbaik, key=lambda k: -terbaik[k])
        return _ke_sebaran(terbaik, [{"kelas": k, "id": bukti[k], "skor": round(terbaik[k], 3)}
                                     for k in urut[:3]])

    def tutup(self):
        """Melepas memori penyandi (dipakai sebelum melatih adapter di GPU yang sama)."""
        import gc
        import torch
        del self.embed, self.rerank
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
