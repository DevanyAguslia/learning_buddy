"""Evaluasi alat ukur keterbacaan - rumus mana yang benar-benar membedakan jenjang SD.

Pengujian pendahuluan pada proposal hanya memakai enam titik data (satu nilai per buku),
sehingga satu pertukaran peringkat sudah mengubah rho sebesar 0,057. Skrip ini menguji
dua belas alat ukur pada tiga tingkat:

  A. BUKU      nilai atas seluruh teks setiap buku, Spearman n = 6 (seperti proposal)
               dan uji buta kelas 3-6.
  B. HALAMAN   setiap halaman isi (>= 40 kata) menjadi satu sampel berlabel jenjang.
               Halaman bernomor genap untuk kalibrasi, ganjil untuk uji. Daftar kata
               dasar disusun ulang HANYA dari halaman kalibrasi kelas 1-2 agar halaman uji
               tidak ikut membentuk daftarnya. Diukur: Spearman, ketepatan menebak jenjang
               (acuan = median per jenjang pada halaman kalibrasi), ketepatan +-1, MAE.
               Termasuk Algoritma 1 Classroom AI dan varian yang ditambah PKR dan KLD.
  C. JAWABAN   kunci jawaban data uji (PJOK 197, Pancasila 158): apakah rumus masih
               membedakan jenjang pada teks satu-dua kalimat, bentuk yang dinilai Reflect
               Agent.

    python -m tb.evaluasi_rumus
Keluaran: hasil/evaluasi_rumus.json (dibaca UI Lab) dan hasil/Evaluasi_Rumus.xlsx
"""
from __future__ import annotations

import json
import os
from collections import Counter

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from .data_qa import bagi_data
from .keterbacaan import Pencocok, kata_isi, pisah_kata, simpan_cache_akar
from .korpus import MAPEL, KELAS
from .rumus import RUMUS, KELOMPOK_CLASSROOM, hitung_semua, kelas_terdekat, integrasi_classroom

AKAR = os.path.dirname(os.path.dirname(__file__))
HASIL = os.path.join(AKAR, "hasil")
MIN_KATA_HALAMAN = 40
KELAS_DASAR = (1, 2)
KELOMPOK_PLUS = {"G1": ["DC", "SPACHE", "KLD"], "G2": ["FRES", "FKGL", "CLI", "PKR"],
                 "G3": ["LW", "FOG"]}
NAMA_METODE = list(RUMUS) + ["INTEGRASI_CLASSROOM", "INTEGRASI_PLUS"]


def _halaman(mapel):
    with open(os.path.join(AKAR, "data", f"halaman_{mapel}.jsonl"), encoding="utf-8") as f:
        return [json.loads(l) for l in f]


def _rho(x, y):
    if len(set(y)) < 2 or len(x) < 3:
        return None, None
    r, p = spearmanr(x, y)
    return round(float(r), 3), float(p)


def _tebak(nilai_per_rumus: dict, acuan: dict) -> dict[str, int]:
    k = {f: kelas_terdekat(nilai_per_rumus[f], acuan[f]) for f in RUMUS}
    k["INTEGRASI_CLASSROOM"] = integrasi_classroom(k)["kelas"]
    k["INTEGRASI_PLUS"] = integrasi_classroom(k, KELOMPOK_PLUS)["kelas"]
    return k


def _skor_tebakan(benar, tebak):
    b, t = np.array(benar), np.array(tebak)
    konf = pd.crosstab(pd.Series(b, name="benar"), pd.Series(t, name="tebak")) \
             .reindex(index=list(KELAS), columns=list(KELAS), fill_value=0)
    return {"tepat": round(float((b == t).mean()), 3),
            "tepat_1": round(float((abs(b - t) <= 1).mean()), 3),
            "mae": round(float(abs(b - t).mean()), 3),
            "konfusi": konf.values.tolist()}


def evaluasi():
    os.makedirs(HASIL, exist_ok=True)
    keluar = {"rumus": RUMUS, "kelompok_classroom": KELOMPOK_CLASSROOM,
              "kelompok_plus": KELOMPOK_PLUS, "mapel": {}}
    baris_xlsx = []

    for mapel in MAPEL:
        print(f"\n=== {mapel} ===")
        hal = [h for h in _halaman(mapel) if h["bagian"] == "isi"
               and len(pisah_kata(h["teks"])) >= MIN_KATA_HALAMAN]
        kal = [h for h in hal if h["halaman"] % 2 == 0]
        uji = [h for h in hal if h["halaman"] % 2 == 1]

        # daftar kata dasar dari halaman kalibrasi kelas 1-2 saja
        hitung = Counter()
        for h in kal:
            if h["kelas"] in KELAS_DASAR:
                hitung.update(kata_isi(h["teks"]))
        daftar = Pencocok({w for w, n in hitung.items() if n >= 3}, "akar")
        print(f"halaman: kalibrasi {len(kal)}, uji {len(uji)} | daftar kata {len(daftar)}")

        ukur = lambda t, m=3: hitung_semua(t, daftar, m)

        # --- A. tingkat buku -----------------------------------------------------
        buku = {k: ukur(" ".join(h["teks"] for h in hal if h["kelas"] == k)) for k in KELAS}
        A = {}
        for f in RUMUS:
            r6, p6 = _rho(list(KELAS), [buku[k][f] for k in KELAS])
            rb, pb = _rho([3, 4, 5, 6], [buku[k][f] for k in (3, 4, 5, 6)])
            A[f] = {"nilai": {k: round(buku[k][f], 3) for k in KELAS},
                    "rho": r6, "p": p6, "rho_buta": rb, "p_buta": pb}

        # --- B. tingkat halaman ---------------------------------------------------
        nilai_kal = [(h["kelas"], ukur(h["teks"])) for h in kal]
        acuan = {f: {k: float(np.median([v[f] for kk, v in nilai_kal if kk == k]))
                     for k in KELAS} for f in RUMUS}
        nilai_uji = [(h["kelas"], ukur(h["teks"])) for h in uji]
        label = [k for k, _ in nilai_uji]
        tebakan = [_tebak(v, acuan) for _, v in nilai_uji]
        B = {}
        for f in NAMA_METODE:
            if f in RUMUS:
                r, p = _rho(label, [v[f] for _, v in nilai_uji])
            else:
                r, p = _rho(label, [t[f] for t in tebakan])
            B[f] = {"rho": r, "p": p, "n": len(label),
                    **_skor_tebakan(label, [t[f] for t in tebakan])}
            if f in RUMUS:
                B[f]["sebaran"] = {k: [round(float(np.percentile([v[f] for kk, v in nilai_uji
                                                                    if kk == k], q)), 3)
                                       for q in (25, 50, 75)] for k in KELAS}

        # --- C. kunci jawaban data uji ---------------------------------------------
        qa = bagi_data(mapel)["uji"]
        nilai_qa = [(int(r.kelas), ukur(r.jawaban, 1)) for r in qa.itertuples()]
        nilai_qa = [(k, v) for k, v in nilai_qa if v is not None]
        label_qa = [k for k, _ in nilai_qa]
        teb_qa = [_tebak(v, acuan) for _, v in nilai_qa]
        C = {}
        for f in NAMA_METODE:
            if f in RUMUS:
                r, p = _rho(label_qa, [v[f] for _, v in nilai_qa])
            else:
                r, p = _rho(label_qa, [t[f] for t in teb_qa])
            C[f] = {"rho": r, "p": p, "n": len(label_qa),
                    **{c: v for c, v in _skor_tebakan(label_qa, [t[f] for t in teb_qa]).items()
                       if c != "konfusi"}}

        keluar["mapel"][mapel] = {"buku": A, "halaman": B, "jawaban": C,
                                  "acuan": {f: {str(k): round(v, 4) for k, v in a.items()}
                                            for f, a in acuan.items()},
                                  "daftar_kalibrasi": len(daftar),
                                  "n_halaman": {"kalibrasi": len(kal), "uji": len(uji)}}
        for f in NAMA_METODE:
            info = RUMUS.get(f, {"nama": f.replace("_", " ").title(), "kelompok": "Integrasi"})
            baris_xlsx.append({
                "Mata pelajaran": mapel, "Kode": f, "Alat ukur": info["nama"],
                "Kelompok": info["kelompok"],
                "Buku rho (n=6)": A.get(f, {}).get("rho"),
                "Buku rho uji buta (3-6)": A.get(f, {}).get("rho_buta"),
                "Halaman rho": B[f]["rho"], "Halaman tepat": B[f]["tepat"],
                "Halaman tepat +-1": B[f]["tepat_1"], "Halaman MAE": B[f]["mae"],
                "Jawaban rho": C[f]["rho"], "Jawaban tepat +-1": C[f]["tepat_1"]})
        urut = sorted(NAMA_METODE, key=lambda f: -(B[f]["rho"] or -9))
        for f in urut:
            print(f"  {f:20s} buku {A.get(f, {}).get('rho', '-')!s:>6} | halaman rho "
                  f"{B[f]['rho']!s:>6} tepat {B[f]['tepat']:.3f} +-1 {B[f]['tepat_1']:.3f} "
                  f"| jawaban rho {C[f]['rho']!s:>6}")

    simpan_cache_akar()
    with open(os.path.join(HASIL, "evaluasi_rumus.json"), "w", encoding="utf-8") as f:
        json.dump(keluar, f, ensure_ascii=False, indent=1, default=float)
    # Acuan untuk /api/ukur: median per jenjang atas SEMUA halaman, diukur dengan daftar
    # kata produksi (yang dipakai Reflect Agent), bukan daftar kalibrasi evaluasi, agar
    # nilai teks dan acuannya memakai penggaris yang sama.
    from .keterbacaan import KontrolKeterbacaan
    K = KontrolKeterbacaan.muat()
    acuan_produksi = {}
    for mapel in MAPEL:
        hal = [h for h in _halaman(mapel) if h["bagian"] == "isi"
               and len(pisah_kata(h["teks"])) >= MIN_KATA_HALAMAN]
        v = [(h["kelas"], hitung_semua(h["teks"], K.daftar[mapel], 3)) for h in hal]
        acuan_produksi[mapel] = {f: {str(k): round(float(np.median([x[f] for kk, x in v if kk == k])), 4)
                                     for k in KELAS} for f in RUMUS}
    simpan_cache_akar()
    with open(os.path.join(AKAR, "data", "acuan_rumus.json"), "w", encoding="utf-8") as f:
        json.dump(acuan_produksi, f, indent=1)
    pd.DataFrame(baris_xlsx).to_excel(os.path.join(HASIL, "Evaluasi_Rumus.xlsx"), index=False)
    print("\ntersimpan: hasil/evaluasi_rumus.json, hasil/Evaluasi_Rumus.xlsx, data/acuan_rumus.json")
    return keluar


if __name__ == "__main__":
    evaluasi()
