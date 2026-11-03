"""Kalibrasi kontrol keterbacaan - lanjutan notebook G4 dengan korpus yang benar.

Menjalankan Subbab 3.1.3.4 dan Lampiran 4 atas dua belas Buku Siswa:
  1. menyusun daftar kata dasar per mata pelajaran dari Buku Siswa jenjang terendah,
  2. mengukur tiga calon alat ukur pada keenam buku setiap mata pelajaran,
  3. menguji keselarasannya dengan jenjang memakai korelasi Spearman, termasuk uji
     buta atas kelas 3-6 untuk menutup kemelingkaran daftar kata (Lampiran 4 akhir),
  4. menurunkan sasaran setiap jenjang: nilai buku + 15% (PKR) dan + 10% (KLD),
  5. menguji garis dasar: berapa persen kunci jawaban lolos sasarannya sendiri,
  6. menyiapkan lembar penilaian guru.

Tanpa GPU. Jalankan dari folder LearningBuddy:
    python -m tb.kalibrasi
Keluaran:
    data/kontrol_keterbacaan.json          dibaca Reflect Agent
    data/halaman_<MAPEL>.jsonl             teks bersih per halaman, dipakai basis pengetahuan
    hasil/G4_Kontrol_Keterbacaan_v2.xlsx   seluruh tabel untuk Bab IV
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from collections import Counter

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from .korpus import MAPEL, KELAS, baca_buku, teks_isi
from .keterbacaan import (simpan_cache_akar, Pencocok, kata_isi, ukur, KontrolKeterbacaan, Sasaran, suku_kata,
                          pisah_kata, pisah_kalimat)
from .data_qa import muat_qa

AKAR = os.path.dirname(os.path.dirname(__file__))
DATA, HASIL = os.path.join(AKAR, "data"), os.path.join(AKAR, "hasil")

KELONGGARAN_PKR = 1.15
KELONGGARAN_KLD = 1.10
MIN_KATA_KALIMAT_BUKU = 3   # penggalan < 3 kata di buku adalah butir soal atau judul


def _spearman(x, y):
    if len(set(y)) < 2:
        return float("nan"), float("nan")
    r, p = spearmanr(x, y)
    return round(float(r), 3), round(float(p), 3)


def kalibrasi(kelas_dasar=(1, 2), min_muncul=3, n_lembar=5, seed=42, pencocokan="bentuk",
               path_json=None):
    os.makedirs(DATA, exist_ok=True)
    os.makedirs(HASIL, exist_ok=True)
    keluaran = {"meta": {
        "dibuat": dt.datetime.now().isoformat(timespec="seconds"),
        "kelas_dasar": list(kelas_dasar), "min_muncul": min_muncul,
        "min_panjang": 3, "pencocokan": pencocokan, "kelonggaran_pkr": KELONGGARAN_PKR,
        "kelonggaran_kld": KELONGGARAN_KLD,
        "catatan": "Sasaran berstatus parameter rancangan sampai divalidasi guru."},
        "mapel": {}}
    tb_korpus, tb_buku, tb_korelasi, tb_sasaran, tb_daftar = [], [], [], [], []
    tb_dasar, lembar, kunci = [], [], []

    for mapel in MAPEL:
        print(f"\n=== {mapel} ===")
        hal = {k: baca_buku(mapel, k) for k in KELAS}
        with open(os.path.join(DATA, f"halaman_{mapel}.jsonl"), "w", encoding="utf-8") as f:
            for k in KELAS:
                for h in hal[k]:
                    f.write(json.dumps(h.dict(), ensure_ascii=False) + "\n")
        teks = {k: teks_isi(hal[k]) for k in KELAS}
        for k in KELAS:
            bag = Counter(h.bagian for h in hal[k])
            tb_korpus.append({"Mata pelajaran": mapel, "Kelas": k,
                              "Buku": MAPEL[mapel]["buku"][k][1],
                              "Halaman": len(hal[k]), "Halaman depan": bag["depan"],
                              "Halaman isi": bag["isi"], "Halaman belakang": bag["belakang"],
                              "Kata dipakai": len(pisah_kata(teks[k]))})

        # 1. daftar kata dasar
        hitung = Counter()
        for k in kelas_dasar:
            hitung.update(kata_isi(teks[k]))   # daftar memuat seluruh kata isi buku
        daftar = {w for w, n in hitung.items() if n >= min_muncul}
        cocok = Pencocok(daftar, pencocokan)
        print(f"daftar kata dasar: {len(daftar)} kata (kelas {list(kelas_dasar)}, "
              f"muncul >= {min_muncul}x)")
        tb_daftar += [{"Mata pelajaran": mapel, "Kata": w, "Frekuensi": hitung[w]}
                      for w in sorted(daftar, key=lambda w: -hitung[w])]

        # 2. ukuran setiap buku
        nilai = {}
        for k in KELAS:
            u = ukur(teks[k], cocok, min_kata_kalimat=MIN_KATA_KALIMAT_BUKU)
            kata = [w for s in pisah_kalimat(teks[k], MIN_KATA_KALIMAT_BUKU) for w in pisah_kata(s)]
            nilai[k] = {"PKR": u.pkr, "KLD": u.kld, "Fry suku/100 kata": u.fry_suku_100,
                        "Fry kalimat/100 kata": u.fry_kalimat_100,
                        "Suku per kata": float(np.mean([suku_kata(w) for w in kata]))}
            tb_buku.append({"Mata pelajaran": mapel, "Kelas": k, "Kata": u.n_kata,
                            "Kalimat": u.n_kalimat, "Kata isi": u.n_isi,
                            **{c: round(v, 3) for c, v in nilai[k].items()}})
            print(f"  kelas {k}: PKR {u.pkr:5.2f}  KLD {u.kld:5.1f}%  "
                  f"Fry {u.fry_suku_100:5.1f} suku/100 kata")

        # 3. korelasi Spearman: enam jenjang dan uji buta kelas 3-6
        buta = [k for k in KELAS if k not in kelas_dasar]
        for c in ["KLD", "PKR", "Fry suku/100 kata", "Suku per kata"]:
            r6, p6 = _spearman(list(KELAS), [nilai[k][c] for k in KELAS])
            rb, pb = _spearman(buta, [nilai[k][c] for k in buta])
            tb_korelasi.append({"Mata pelajaran": mapel, "Alat ukur": c,
                                "rho (6 jenjang)": r6, "p (6 jenjang)": p6,
                                f"rho uji buta (kelas {buta[0]}-{buta[-1]})": rb,
                                f"p uji buta": pb})
            print(f"  Spearman {c:20s}: 6 jenjang {r6:+.3f} | uji buta {rb:+.3f}")

        # 4. sasaran per jenjang
        sasaran = {}
        for k in KELAS:
            s = Sasaran(maks_pkr=round(nilai[k]["PKR"] * KELONGGARAN_PKR, 1),
                        maks_kld=round(nilai[k]["KLD"] * KELONGGARAN_KLD, 1),
                        pkr_buku=round(nilai[k]["PKR"], 2), kld_buku=round(nilai[k]["KLD"], 1))
            sasaran[k] = s
            tb_sasaran.append({"Mata pelajaran": mapel, "Kelas": k,
                               "PKR buku": s.pkr_buku, "Sasaran PKR (maks)": s.maks_pkr,
                               "KLD buku (%)": s.kld_buku, "Sasaran KLD (maks %)": s.maks_kld})
        keluaran["mapel"][mapel] = {
            "daftar_dasar": sorted(daftar),
            "akar_dasar": sorted(cocok.akar),
            "sasaran": {str(k): s.__dict__ for k, s in sasaran.items()},
            "nilai_buku": {str(k): {c: round(v, 3) for c, v in nilai[k].items()} for k in KELAS},
        }

    # simpan dulu agar KontrolKeterbacaan bisa dipakai untuk garis dasar
    path_json = path_json or os.path.join(DATA, "kontrol_keterbacaan.json")
    with open(path_json, "w", encoding="utf-8") as f:
        json.dump(keluaran, f, ensure_ascii=False, indent=1)
    K = KontrolKeterbacaan.muat(path_json)

    # 5. garis dasar kunci jawaban dan 6. lembar guru
    for mapel in MAPEL:
        qa = muat_qa(mapel)
        hasil = []
        for r in qa.itertuples():
            p = K.periksa(r.jawaban, mapel, r.kelas)
            if p.ukuran is None:
                continue
            hasil.append({"kelas": r.kelas, "lolos": p.lolos, "gagal_pkr": not p.lolos_pkr,
                          "gagal_kld": not p.lolos_kld, "pkr": p.ukuran["pkr"],
                          "kld": p.ukuran["kld"]})
        G = pd.DataFrame(hasil)
        for k, g in G.groupby("kelas"):
            tb_dasar.append({"Mata pelajaran": mapel, "Kelas": k, "n": len(g),
                             "% lolos": round(100 * g.lolos.mean(), 1),
                             "% gagal PKR": round(100 * g.gagal_pkr.mean(), 1),
                             "% gagal KLD": round(100 * g.gagal_kld.mean(), 1),
                             "Rata PKR": round(g.pkr.mean(), 2),
                             "Rata KLD (%)": round(g.kld.mean(), 1)})
        tb_dasar.append({"Mata pelajaran": mapel, "Kelas": "semua", "n": len(G),
                         "% lolos": round(100 * G.lolos.mean(), 1),
                         "% gagal PKR": round(100 * G.gagal_pkr.mean(), 1),
                         "% gagal KLD": round(100 * G.gagal_kld.mean(), 1),
                         "Rata PKR": round(G.pkr.mean(), 2),
                         "Rata KLD (%)": round(G.kld.mean(), 1)})
        print(f"\ngaris dasar {mapel}: {100 * G.lolos.mean():.1f}% kunci jawaban lolos")

        sampel = pd.concat([g.sample(min(n_lembar, len(g)), random_state=seed)
                            for _, g in qa.groupby("kelas")])
        for r in sampel.itertuples():
            p = K.periksa(r.jawaban, mapel, r.kelas)
            lembar.append({"Mata pelajaran": mapel, "Kelas Target": r.kelas,
                           "Pertanyaan": r.pertanyaan, "Jawaban": r.jawaban,
                           "_sistem": "LOLOS" if p.lolos else "TIDAK LOLOS"})

    L = pd.DataFrame(lembar).sample(frac=1.0, random_state=seed).reset_index(drop=True)
    L.insert(0, "No", range(1, len(L) + 1))
    kunci = L[["No", "Mata pelajaran", "Kelas Target", "_sistem"]].rename(
        columns={"_sistem": "Penilaian sistem"})
    L = L.drop(columns=["_sistem", "Kelas Target"])
    L["Menurut Bapak/Ibu, bahasa jawaban ini cocok untuk kelas berapa? (1-6)"] = ""
    L["Yang menyulitkan (kalimat panjang / kata sulit / lainnya)"] = ""

    konfigurasi = pd.DataFrame([
        ("Tujuan", "Memilih alat ukur keterbacaan dan menurunkan sasaran per jenjang"),
        ("Korpus", "12 Buku Siswa: 6 PJOK dan 6 Pendidikan Pancasila, satu per jenjang"),
        ("Pengambilan teks", "PyMuPDF per halaman; halaman depan dan belakang dibuang"),
        ("Rumus", "PKR = kata/kalimat; KLD = 100 x kata isi di luar daftar / kata isi"),
        ("Kalimat buku", "dipecah pada . ? !; titik isian dan penanda butir jadi batas; "
                         f"penggalan < {MIN_KATA_KALIMAT_BUKU} kata tidak dihitung"),
        ("Kata isi", "minimal 3 huruf, bukan kata tugas"),
        ("Pencocokan daftar", "bentuk kata persis" if pencocokan == "bentuk"
                              else "bentuk kata atau kata dasar (stemmer Sastrawi)"),
        ("Daftar kata dasar", f"Buku Siswa kelas {list(kelas_dasar)} per mata pelajaran, "
                              f"muncul >= {min_muncul} kali"),
        ("Kelonggaran", f"PKR +{round((KELONGGARAN_PKR - 1) * 100)}%, "
                        f"KLD +{round((KELONGGARAN_KLD - 1) * 100)}%"),
        ("Pembanding", "Grafik Fry (suku kata per 100 kata), tidak dipakai memutuskan"),
        ("Uji buta", f"korelasi hanya atas jenjang di luar kelas {list(kelas_dasar)}"),
        ("Validasi", "penilaian guru (sheet 7) - belum dijalankan"),
        ("Dibuat", keluaran["meta"]["dibuat"]),
    ], columns=["Parameter", "Keterangan"])

    xlsx = os.path.join(HASIL, f"G4_Kontrol_Keterbacaan_v2_{pencocokan}.xlsx")
    with pd.ExcelWriter(xlsx, engine="openpyxl") as w:
        konfigurasi.to_excel(w, sheet_name="0_Konfigurasi", index=False)
        pd.DataFrame(tb_korpus).to_excel(w, sheet_name="1_Korpus", index=False)
        pd.DataFrame(tb_buku).to_excel(w, sheet_name="2_Ukuran_per_Buku", index=False)
        pd.DataFrame(tb_korelasi).to_excel(w, sheet_name="3_Korelasi_Spearman", index=False)
        pd.DataFrame(tb_sasaran).to_excel(w, sheet_name="4_Sasaran_per_Jenjang", index=False)
        pd.DataFrame(tb_daftar).to_excel(w, sheet_name="5_Daftar_Kata_Dasar", index=False)
        pd.DataFrame(tb_dasar).to_excel(w, sheet_name="6_Garis_Dasar_Kunci", index=False)
        L.to_excel(w, sheet_name="7_Lembar_Guru", index=False)
        kunci.to_excel(w, sheet_name="7b_Kunci_Lembar_Guru", index=False)
    simpan_cache_akar()
    print(f"\ntersimpan: {path_json}\ntersimpan: {xlsx}")
    return keluaran


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--kelas-dasar", type=int, nargs="+", default=[1, 2])
    ap.add_argument("--min-muncul", type=int, default=3)
    ap.add_argument("--pencocokan", choices=["bentuk", "akar"], default="akar")
    ap.add_argument("--keluaran", default=None, help="path JSON (bawaan data/kontrol_keterbacaan.json)")
    a = ap.parse_args()
    kalibrasi(tuple(a.kelas_dasar), a.min_muncul, pencocokan=a.pencocokan, path_json=a.keluaran)
