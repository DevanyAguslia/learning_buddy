"""Evaluasi Layanan Pencarian Konteks dengan pipeline website yang sebenarnya (PJOK Merdeka).

Soal: data/qa/Validasi_Soal_PJOK.xlsx (1.014 soal PJOK Kurikulum Merdeka, jawaban dan
konteks = kutipan persis buku), bagian latih/validasi/uji dari data/qa/pembagian_merdeka.csv.
Setiap soal dicari seperti saat website berjalan: saringan mapel + kelas (kelas = label
soal), K_CALON calon potongan Recursive, cross-encoder menilai seluruh calon, lalu potongan
dipilih dengan pilih_beragam (tb.pencarian).

Dari kumpulan calon dan skor yang sama dibandingkan beberapa varian, supaya selisihnya murni
karena cara memilih:
  Website                  calon dinilai reranker              (yang dipakai website)
  Website-tanpa-reranker   calon diurutkan kesamaan kosinus saja
  <strategi>               hanya bila TB_STRATEGI berisi lebih dari satu strategi
masing-masing dengan 1 potongan dan KIRIM (bawaan 3) potongan.

Metrik per varian (kata isi, tb.keterbacaan.kata_isi):
  hit       ada potongan terkirim yang memuat >= 50% kata konteks acuan
  recall    proporsi kata konteks acuan yang termuat di gabungan potongan terkirim
  jawaban   proporsi kata kunci jawaban yang termuat di gabungan potongan terkirim
  karakter  panjang total teks yang dikirim ke Act Agent
Juga dicatat strategi potongan terkirim varian Website dan Recall@calon (konteks acuan ada
di antara seluruh calon, batas atas yang dapat dicapai reranker).

Kalibrasi pengecekan 1 (Act Agent): positif = soal PJOK di buku PJOK kelasnya sendiri,
negatif = soal Pendidikan Pancasila Merdeka (data/qa/Soal_PKN_Merdeka.xlsx) di buku PJOK
kelas yang sama. Skor = skor reranker potongan teratas varian Website. Ambang dipilih
dengan indeks Youden (J = TPR - FPR) pada latih+validasi, dilaporkan pada uji, dan disimpan
ke <folder indeks>/ambang_relevan.json untuk dibaca PencariSemantik.

Kaggle (GPU):  python -m tb.evaluasi_pencarian
Keluaran: hasil/evaluasi_pencarian.json, hasil/Evaluasi_Pencarian.xlsx, dan
hasil/Validasi_Soal_PJOK_Recursive.xlsx (tb.validasi_recursive: per soal potongan acuan
dan 3 potongan yang dikirim website)
"""
from __future__ import annotations

import json
import os
import time
from collections import Counter

import numpy as np
import pandas as pd

from .keterbacaan import kata_isi
from .pencarian import (K_CALON, KIRIM, MODEL_EMBEDDING, MODEL_RERANKER, PencariSemantik,
                        bangun_indeks_faiss, folder_indeks, muat_potongan, pilih_beragam,
                        strategi_dari)

AKAR = os.path.dirname(os.path.dirname(__file__))
QA = os.path.join(AKAR, "data", "qa")
PATH_SOAL = os.path.join(QA, "Validasi_Soal_PJOK.xlsx")
PATH_NEGATIF = os.path.join(QA, "Soal_PKN_Merdeka.xlsx")
PATH_BAGIAN = os.path.join(QA, "pembagian_merdeka.csv")
HASIL = os.path.join(AKAR, "hasil")
AMBANG_TERMUAT = 0.5


def muat_soal(path: str) -> pd.DataFrame:
    """Lembar "Kelas 1".."Kelas 6" format Validasi_Soal: id, kelas, pertanyaan, jawaban, konteks."""
    lembar = pd.read_excel(path, sheet_name=None)
    df = pd.concat([d for n, d in lembar.items() if n.lower().startswith("kelas")], ignore_index=True)
    df = df.rename(columns={"jawaban (kutipan buku)": "jawaban", "konteks (kutipan buku)": "konteks"})
    df = df.dropna(subset=["id", "pertanyaan"])
    bagian = pd.read_csv(PATH_BAGIAN).set_index("id")["bagian"]
    df["bagian"] = df["id"].map(bagian).fillna("latih")
    df["kelas"] = df["kelas"].astype(int)
    return df.reset_index(drop=True)


def _cakup(potongan: list[dict], acuan: str) -> float:
    """Proporsi kata isi acuan yang termuat di gabungan potongan."""
    y = Counter(kata_isi(acuan or ""))
    if not y:
        return float("nan")
    x = sum((Counter(kata_isi(p["teks"])) for p in potongan), Counter())
    return sum((x & y).values()) / sum(y.values())


def _ukur(pilih: list[dict], r) -> dict:
    return {"hit": float(any(_cakup([p], r.konteks) >= AMBANG_TERMUAT for p in pilih)),
            "recall": _cakup(pilih, r.konteks), "jawaban": _cakup(pilih, r.jawaban),
            "karakter": sum(len(p["teks"]) for p in pilih)}


def _varian(calon: list, ulang: list[float]) -> dict:
    """calon: [(potongan, kosinus)], ulang: skor reranker -> {nama varian: [(p, skor) terurut]}.
    "Website" = seluruh calon dinilai reranker (yang dipakai website); bila indeks berisi
    lebih dari satu strategi, setiap strategi juga dinilai sendiri."""
    def urut(idx, skor):
        return [(calon[i][0], skor[i]) for i in sorted(idx, key=lambda i: -skor[i])]
    semua = range(len(calon))
    kos = [s for _, s in calon]
    out = {"Website": urut(semua, ulang), "Website-tanpa-reranker": urut(semua, kos)}
    strategi = sorted({strategi_dari(p) for p, _ in calon})
    if len(strategi) > 1:
        for s in strategi:
            out[s] = urut([i for i in semua if strategi_dari(calon[i][0]) == s], ulang)
    return out


def evaluasi(nama: str = MODEL_EMBEDDING, kirim: int = KIRIM):
    t0 = time.time()
    soal = muat_soal(PATH_SOAL)
    folder = folder_indeks(nama)
    meta = os.path.join(folder, "meta.json")
    if not os.path.exists(meta) or "strategi" not in json.load(open(meta, encoding="utf-8")):
        bangun_indeks_faiss(muat_potongan(), nama)
    P = PencariSemantik(nama_model=nama)
    print(f"{P.metode} | {len(soal)} soal PJOK Merdeka | kirim {kirim}", flush=True)

    baris = []
    for i, r in enumerate(soal.itertuples()):
        calon = P._calon(P._kueri(r.pertanyaan), "PJOK", r.kelas, K_CALON)
        ulang = P._nilai(r.pertanyaan, calon)
        b = {"id": r.id, "bagian": r.bagian, "kelas": r.kelas, "pertanyaan": r.pertanyaan,
             "recall@calon": float(any(_cakup([p], r.konteks) >= AMBANG_TERMUAT for p, _ in calon)),
             "skor_reranker": float(max(ulang)) if ulang else float("nan")}
        for v, urut in _varian(calon, ulang).items():
            for n in (1, kirim):
                pasang = urut[:1] if n == 1 else pilih_beragam(urut, n)
                pilih = [p for p, _ in pasang]
                for m, x in _ukur(pilih, r).items():
                    b[f"{v}|{n}|{m}"] = x
                if v == "Website":
                    b[f"strategi|{n}"] = "+".join(strategi_dari(p) for p in pilih)
                    if n == kirim:          # potongan yang benar-benar dikirim website
                        b["kirim_ids"] = json.dumps([p["id"] for p in pilih])
                        b["kirim_skor"] = json.dumps([round(float(s), 4) for _, s in pasang])
        baris.append(b)
        if (i + 1) % 100 == 0:
            print(f"  {i + 1}/{len(soal)} soal ({(time.time() - t0) / 60:.1f} menit)", flush=True)
    df = pd.DataFrame(baris)

    kolom = [c for c in df.columns if c.count("|") == 2]

    def ringkas(d: pd.DataFrame) -> list[dict]:
        out = []
        for v in dict.fromkeys(c.split("|")[0] for c in kolom):
            for n in (1, kirim):
                out.append({"varian": v, "potongan": n, "n": len(d),
                            **{m: round(d[f"{v}|{n}|{m}"].mean(), 4)
                               for m in ("hit", "recall", "jawaban", "karakter")}})
        return out

    pilihan = df.groupby(["kelas", "strategi|1"]).size().unstack(fill_value=0)
    kal = kalibrasi_ambang(df, P)
    hasil = {"metode": P.metode, "model_embedding": nama, "model_reranker": MODEL_RERANKER,
             "kirim": kirim, "k_calon_per_strategi": K_CALON, "n_soal": len(df),
             "recall@calon": round(df["recall@calon"].mean(), 4),
             "uji": ringkas(df[df.bagian == "uji"]), "semua": ringkas(df),
             "strategi_teratas": df["strategi|1"].value_counts().to_dict(),
             "ambang_relevan": kal, "menit": round((time.time() - t0) / 60, 1)}
    os.makedirs(HASIL, exist_ok=True)
    with open(os.path.join(HASIL, "evaluasi_pencarian.json"), "w", encoding="utf-8") as f:
        json.dump(hasil, f, indent=1, ensure_ascii=False)
    with pd.ExcelWriter(os.path.join(HASIL, "Evaluasi_Pencarian.xlsx")) as w:
        pd.DataFrame(hasil["semua"]).to_excel(w, sheet_name="Ringkasan_Semua", index=False)
        pd.DataFrame(hasil["uji"]).to_excel(w, sheet_name="Ringkasan_Uji", index=False)
        pd.DataFrame([{"kelas": k, **r} for k, g in df.groupby("kelas") for r in ringkas(g)]) \
          .to_excel(w, sheet_name="Per_Kelas", index=False)
        pilihan.to_excel(w, sheet_name="Strategi_Teratas")
        df.to_excel(w, sheet_name="Per_Soal", index=False)
        pd.DataFrame([{"Bagian": b, **v} for b, v in kal["kinerja"].items()]) \
          .to_excel(w, sheet_name="Ambang_Relevan", index=False)
    with open(os.path.join(folder, "ambang_relevan.json"), "w", encoding="utf-8") as f:
        json.dump(kal, f, indent=1)
    # file Validasi dengan potongan acuan + 3 potongan pilihan website per soal
    from .validasi_recursive import tulis
    tulis({r["id"]: {"ids": json.loads(r["kirim_ids"]), "skor": json.loads(r["kirim_skor"])}
           for r in baris}, os.path.join(HASIL, "Validasi_Soal_PJOK_Recursive.xlsx"))
    print(pd.DataFrame(hasil["semua"]).to_string(index=False))
    print(json.dumps({k: hasil[k] for k in ("recall@calon", "strategi_teratas", "ambang_relevan",
                                            "menit")}, indent=1, ensure_ascii=False))
    return hasil


def kalibrasi_ambang(df: pd.DataFrame, P: PencariSemantik) -> dict:
    """Ambang skor reranker untuk pengecekan 1. df: hasil per soal PJOK (positif)."""
    pkn = muat_soal(PATH_NEGATIF)
    neg = []
    for r in pkn.itertuples():
        calon = P._calon(P._kueri(r.pertanyaan), "PJOK", r.kelas, K_CALON)
        neg.append({"bagian": r.bagian, "skor": float(max(P._nilai(r.pertanyaan, calon)))})
    neg = pd.DataFrame(neg)
    pos = df[["bagian", "skor_reranker"]].rename(columns={"skor_reranker": "skor"})

    def kinerja(a, p, n):
        tpr, fpr = float((p >= a).mean()), float((n >= a).mean())
        return {"n_positif": len(p), "n_negatif": len(n), "TPR": round(tpr, 4),
                "FPR": round(fpr, 4), "J": round(tpr - fpr, 4)}

    pl = pos[pos.bagian != "uji"]["skor"].to_numpy()
    nl = neg[neg.bagian != "uji"]["skor"].to_numpy()
    calon = np.unique(np.concatenate([pl, nl]))
    j = [(pl >= a).mean() - (nl >= a).mean() for a in calon]
    ambang = float(calon[int(np.argmax(j))])
    return {"ambang": round(ambang, 6), "skala": "reranker", "model_reranker": MODEL_RERANKER,
            "metode": "Youden J pada latih+validasi; positif PJOK Merdeka sekelas, "
                      "negatif Pancasila Merdeka di buku PJOK",
            "kinerja": {"latih+validasi": kinerja(ambang, pl, nl),
                        "uji": kinerja(ambang, pos[pos.bagian == "uji"]["skor"].to_numpy(),
                                       neg[neg.bagian == "uji"]["skor"].to_numpy())}}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=MODEL_EMBEDDING)
    ap.add_argument("--kirim", type=int, default=KIRIM)
    a = ap.parse_args()
    evaluasi(a.model, a.kirim)
