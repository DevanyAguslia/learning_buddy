"""Layanan Basis Pengetahuan (Gambar 3.1) - berjalan sekali di awal.

    python -m tb.basis                 # potongan.jsonl saja (tanpa GPU, laptop)
    python -m tb.basis --vektor        # + indeks FAISS per strategi dengan penyandi TB_MODEL_EMBEDDING
    python -m tb.basis --potong-lama   # potongan dari tb.potong (pemotong versi proposal)

Potongan yang dipakai website adalah Recursive hasil Eksperimen_Chunking pada buku
Kurikulum Merdeka (tb.impor_potongan). Kolom konteks buatan manusia pada data tanya jawab
TIDAK pernah dimasukkan ke indeks, agar sistem tidak menemukan kunci jawabannya sendiri
(Subbab 3.1.3.1).
"""
from __future__ import annotations

import argparse
import json
import os
from collections import Counter

from .korpus import MAPEL, KELAS, baca_buku
from .potong import potong_buku
from .pencarian import PATH_POTONGAN, MODEL_EMBEDDING, bangun_indeks_faiss

AKAR = os.path.dirname(os.path.dirname(__file__))


def _halaman(mapel: str) -> list[dict]:
    path = os.path.join(AKAR, "data", f"halaman_{mapel}.jsonl")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return [json.loads(l) for l in f]
    return [h.dict() for k in KELAS for h in baca_buku(mapel, k)]


def bangun_potongan(path: str = PATH_POTONGAN) -> list[dict]:
    """Pemotong versi proposal (tb.potong), satu strategi. Tidak dipakai website lagi."""
    semua = []
    for mapel in MAPEL:
        hal = _halaman(mapel)
        for k in KELAS:
            semua += [p.dict() for p in potong_buku([h for h in hal if h["kelas"] == k])]
    with open(path, "w", encoding="utf-8") as f:
        for p in semua:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    c = Counter((p["mapel"], p["kelas"]) for p in semua)
    print(f"{len(semua)} potongan -> {path}")
    for (m, k), n in sorted(c.items()):
        print(f"  {m} kelas {k}: {n}")
    return semua


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--vektor", action="store_true", help="bangun indeks FAISS per strategi")
    ap.add_argument("--model", default=MODEL_EMBEDDING, help="penyandi, bawaan TB_MODEL_EMBEDDING")
    ap.add_argument("--device", default=None, help="bawaan: GPU bila ada, selain itu CPU")
    ap.add_argument("--ulang", action="store_true", help="ambil ulang potongan walau potongan.jsonl ada")
    ap.add_argument("--potong-lama", action="store_true", help="pakai pemotong tb.potong (proposal)")
    a = ap.parse_args()
    if a.vektor and os.path.exists(PATH_POTONGAN) and not a.ulang:
        from .pencarian import muat_potongan
        ps = muat_potongan()      # di Kaggle cukup memakai potongan hasil laptop
    elif a.potong_lama:
        ps = bangun_potongan()
    else:
        from .impor_potongan import impor
        ps = impor()
    if a.vektor:
        bangun_indeks_faiss(ps, a.model, device=a.device)
