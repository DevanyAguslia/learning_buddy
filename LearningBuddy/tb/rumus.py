"""Rumus keterbacaan pembanding untuk teks berbahasa Indonesia.

Sumber daftar rumus:
  Classroom AI (Oh, Whang, Evans, Wang; KAIST, Microsoft Research Asia, William & Mary;
  arXiv 2601.06225, npj AI 2026) memadukan tujuh rumus - FRES, FKGL, CLI, Linsear Write,
  Gunning Fog, Dale-Chall, Spache - dalam tiga kelompok, dan memakai ARI sebagai rumus
  uji luar (Lampiran B paper tersebut). Rumusnya disalin apa adanya di bawah.
  LIX (Bjornsson 1968) ditambahkan karena tidak memakai suku kata maupun daftar kata
  bahasa Inggris, sehingga lazim dipakai lintas bahasa.
  EduAdapt (Naeem dkk., EMNLP 2025) TIDAK memakai rumus; ia memakai LLM-as-a-judge
  dengan enam kriteria 1-10 (Listing 10 paper tersebut). Belum diimplementasikan di sini
  karena memerlukan GPU.

Penyesuaian ke bahasa Indonesia (harus ditulis di Bab III bila dipakai):
  - suku kata dihitung dengan penghitung suku kata Indonesia (tb.keterbacaan.suku_kata);
  - "kata akrab" Dale-Chall dan Spache diganti daftar kata dasar dari Buku Siswa kelas
    1-2 ditambah kata tugas, karena daftar 3.000 / 1.000 kata aslinya berbahasa Inggris;
  - konstanta setiap rumus tetap konstanta bahasa Inggris. Akibatnya angka "kelas" yang
    keluar TIDAK boleh dibaca sebagai kelas SD Indonesia. Yang sah dipakai hanyalah
    urutannya, yaitu apakah nilainya naik seiring jenjang. Karena itu evaluasi memakai
    korelasi Spearman dan pemetaan ulang ke jenjang lewat kalibrasi buku.
"""
from __future__ import annotations

import math
import re

from .keterbacaan import (KATA_TUGAS, Pencocok, kata_isi, pisah_kalimat, pisah_kata,
                          suku_kata)

# arah: +1 berarti nilai makin besar makin sulit; -1 berarti makin besar makin mudah
RUMUS = {
    "PKR":   {"nama": "Panjang kalimat rata-rata", "kelompok": "Kalimat", "arah": +1,
              "sumber": "proposal (2.4)"},
    "KLD":   {"nama": "Kata luar daftar (%)", "kelompok": "Daftar kata", "arah": +1,
              "sumber": "proposal (2.4)"},
    "FRES":  {"nama": "Flesch Reading Ease", "kelompok": "Panjang kata dan kalimat", "arah": -1,
              "sumber": "Classroom AI B.1.1"},
    "FKGL":  {"nama": "Flesch-Kincaid Grade Level", "kelompok": "Panjang kata dan kalimat",
              "arah": +1, "sumber": "Classroom AI B.1.2"},
    "CLI":   {"nama": "Coleman-Liau Index", "kelompok": "Panjang kata dan kalimat", "arah": +1,
              "sumber": "Classroom AI B.1.3"},
    "LW":    {"nama": "Linsear Write", "kelompok": "Suku kata", "arah": +1,
              "sumber": "Classroom AI B.1.4"},
    "FOG":   {"nama": "Gunning Fog Index", "kelompok": "Suku kata", "arah": +1,
              "sumber": "Classroom AI B.1.5"},
    "DC":    {"nama": "Dale-Chall", "kelompok": "Daftar kata", "arah": +1,
              "sumber": "Classroom AI B.1.6"},
    "SPACHE": {"nama": "Spache", "kelompok": "Daftar kata", "arah": +1,
               "sumber": "Classroom AI B.1.7"},
    "ARI":   {"nama": "Automated Readability Index", "kelompok": "Panjang kata dan kalimat",
              "arah": +1, "sumber": "Classroom AI B.1.8 (rumus uji luar)"},
    "SMOG":  {"nama": "SMOG", "kelompok": "Suku kata", "arah": +1,
              "sumber": "McLaughlin 1969 (tidak dipakai Classroom AI)"},
    "LIX":   {"nama": "LIX (Laesbarhedsindex)", "kelompok": "Panjang kata dan kalimat",
              "arah": +1, "sumber": "Bjornsson 1968, lintas bahasa"},
    "FRY":   {"nama": "Grafik Fry: suku kata per 100 kata", "kelompok": "Suku kata",
              "arah": +1, "sumber": "proposal, pembanding"},
}

# Lima alat ukur yang dipakai proposal v3 dan ditampilkan Lab: dua kendali (dipakai Reflect
# Agent memutuskan) dan tiga pembanding (dilaporkan saja). Rumus lain di RUMUS tetap dihitung
# untuk evaluasi rumus (tb.evaluasi_rumus) tetapi tidak ditampilkan.
RUMUS_LAB = {"PKR": "kendali", "KLD": "kendali", "FRY": "pembanding", "DC": "pembanding",
             "FOG": "pembanding"}

# Kelompok Algoritma 1 Classroom AI: G1 daftar kata, G2 panjang kata dan kalimat,
# G3 suku kata. PKR dan KLD tidak ikut, agar integrasinya sama dengan paper.
KELOMPOK_CLASSROOM = {"G1": ["DC", "SPACHE"], "G2": ["FRES", "FKGL", "CLI"],
                      "G3": ["LW", "FOG"]}


def _akrab(w: str, daftar: Pencocok | None) -> bool:
    """Kata akrab untuk Dale-Chall dan Spache: ada di daftar dasar, kata tugas, atau
    kata sangat pendek (di, ke, ya)."""
    w = w.lower()
    return len(w) < 3 or w in KATA_TUGAS or (daftar is not None and w in daftar)


def hitung_semua(teks: str, daftar: Pencocok | None = None, min_kata_kalimat: int = 1) -> dict | None:
    kal = pisah_kalimat(teks, min_kata_kalimat)
    kata = [w for k in kal for w in pisah_kata(k)]
    if not kata:
        return None
    W, S = len(kata), max(len(kal), 1)
    suku = [suku_kata(w) for w in kata]
    SY = sum(suku)
    huruf = sum(len(w) for w in kata)
    angka = sum(len(re.findall(r"\d", k)) for k in kal)
    kompleks = sum(1 for s in suku if s >= 3)
    panjang = sum(1 for w in kata if len(w) > 6)
    tak_akrab = [w.lower() for w in kata if not _akrab(w, daftar)]

    # Linsear Write dihitung atas 100 kata pertama, sesuai definisinya
    k100, sisa, s100 = [], 100, 0
    for k in kal:
        if sisa <= 0:
            break
        ks = pisah_kata(k)[:sisa]
        k100 += ks
        sisa -= len(ks)
        s100 += 1
    mudah = sum(1 for w in k100 if suku_kata(w) <= 2)
    i_lw = (mudah + 3 * (len(k100) - mudah)) / max(s100, 1)
    lw = i_lw / 2 if i_lw > 20 else (i_lw - 2) / 2

    p = 100 * len(tak_akrab) / W
    dc = 0.1579 * p + 0.0496 * W / S + (3.6365 if p > 5 else 0)
    unik_tak_akrab = 100 * len(set(tak_akrab)) / W
    isi = [w for k in kal for w in kata_isi(k)]
    kld = 100 * sum(1 for w in isi if daftar is not None and w not in daftar) / len(isi) if isi else 0.0

    L = 100 * huruf / W
    S100 = 100 * S / W
    return {
        "PKR": W / S,
        "KLD": kld,
        "FRES": 206.835 - 1.015 * W / S - 84.6 * SY / W,
        "FKGL": 0.39 * W / S + 11.8 * SY / W - 15.59,
        "CLI": 0.0588 * L - 0.296 * S100 - 15.8,
        "LW": lw,
        "FOG": 0.4 * (W / S + 100 * kompleks / W),
        "DC": dc,
        "SPACHE": 0.141 * W / S + 0.086 * unik_tak_akrab + 0.839,
        "ARI": 4.71 * (huruf + angka) / W + 0.5 * W / S - 21.43,
        # SMOG: 1,0430 x akar(kata >= 3 suku x 30 / kalimat) + 3,1291. Dirancang untuk
        # sampel 30 kalimat; pada jawaban 1-2 kalimat nilainya diekstrapolasi.
        "SMOG": 1.0430 * math.sqrt(kompleks * 30 / S) + 3.1291,
        "LIX": W / S + 100 * panjang / W,
        "FRY": 100 * SY / W,
        "_hitungan": {"kata": W, "kalimat": S, "suku": SY, "huruf": huruf,
                      "kata_kompleks": kompleks, "kata_panjang": panjang,
                      "kata_isi": len(isi), "tak_akrab": sorted(set(tak_akrab))},
    }


def kelas_terdekat(nilai: float, acuan: dict[int, float]) -> int:
    """Memetakan nilai rumus ke jenjang SD lewat nilai acuan per jenjang dari buku.
    Konstanta rumus bahasa Inggris tidak berarti untuk bahasa Indonesia, jadi jenjang
    tidak dibaca langsung dari angka rumus, melainkan dari buku jenjang mana nilainya
    paling dekat."""
    return min(acuan, key=lambda k: (abs(nilai - acuan[k]), k))


def integrasi_classroom(kelas_per_rumus: dict[str, int],
                        kelompok: dict[str, list[str]] = KELOMPOK_CLASSROOM) -> dict:
    """Algoritma 1 Classroom AI (Grade-level Integration), apa adanya:
    suara kelompok = irisan jenjang anggotanya bila tidak kosong, selain itu jenjang
    terkecil; jenjang akhir = modus bila dua kelompok atau lebih sepakat, selain itu
    median ketiga suara."""
    suara = {}
    for g, anggota in kelompok.items():
        nilai = {kelas_per_rumus[f] for f in anggota if f in kelas_per_rumus}
        if not nilai:
            continue
        suara[g] = nilai.pop() if len(nilai) == 1 else min(nilai)
    v = sorted(suara.values())
    if not v:
        return {"suara": {}, "kelas": None, "cara": "-"}
    for x in v:
        if v.count(x) >= 2:
            return {"suara": suara, "kelas": x, "cara": "modus"}
    return {"suara": suara, "kelas": v[len(v) // 2], "cara": "median"}
