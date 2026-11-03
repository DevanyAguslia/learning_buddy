"""Pengujian sistem atas data uji kanonik, dapat dipantau dari UI Lab.

Setiap soal uji dijawab lewat siklus agen penuh pada skenario yang dipilih (S1-S4), lalu
dinilai dengan metrik yang bisa dihitung tanpa GPU:
    Exact Match, Token F1, chrF++           ketepatan terhadap kunci jawaban
    kepatuhan keterbacaan, putaran, batas    kerja Reflect Agent (Subbab 3.1.3.5)
    seluruh rumus pada tb/rumus.py           keterbacaan jawaban akhir
    ketepatan Plan Agent                     bila jenjang ditetapkan agen, bukan data
BERTScore dan probe logit memerlukan GPU dan dihitung di notebook evaluasi Kaggle.

Penjawab boleh lokal (model tiruan) atau jarak jauh (server Kaggle lewat tunnel), jadi
angka dari penjawab tiruan hanya menguji jalannya alur, bukan hasil penelitian.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import threading
import time
import traceback
from collections import Counter

import numpy as np

from .data_qa import bagi_data
from .rumus import RUMUS, hitung_semua

AKAR = os.path.dirname(os.path.dirname(__file__))
HASIL = os.path.join(AKAR, "hasil", "uji")


# --- metrik berbasis acuan --------------------------------------------------------
def _norm(t: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", str(t).lower())).strip()


def exact_match(pred: str, gold: str) -> float:
    return float(_norm(pred) == _norm(gold))


def token_f1(pred: str, gold: str) -> float:
    p, g = _norm(pred).split(), _norm(gold).split()
    if not p or not g:
        return float(p == g)
    sama = sum((Counter(p) & Counter(g)).values())
    if sama == 0:
        return 0.0
    pr, rc = sama / len(p), sama / len(g)
    return 2 * pr * rc / (pr + rc)


def _ngram(xs, n):
    return Counter(tuple(xs[i:i + n]) for i in range(len(xs) - n + 1))


def chrf_pp(pred: str, gold: str, n_char: int = 6, n_kata: int = 2, beta: float = 2.0) -> float:
    """chrF++ (Popovic 2017): rata-rata presisi dan recall n-gram karakter 1-6 (tanpa spasi)
    dan n-gram kata 1-2, digabung dengan F-beta, beta = 2. Skala 0-100."""
    pc, gc = list(pred.replace(" ", "")), list(gold.replace(" ", ""))
    pw, gw = str(pred).split(), str(gold).split()
    P, R = [], []
    for xs, ys, n_maks in ((pc, gc, n_char), (pw, gw, n_kata)):
        for n in range(1, n_maks + 1):
            a, b = _ngram(xs, n), _ngram(ys, n)
            if not a or not b:
                continue
            cocok = sum((a & b).values())
            P.append(cocok / sum(a.values()))
            R.append(cocok / sum(b.values()))
    if not P:
        return 0.0
    p, r = np.mean(P), np.mean(R)
    if p + r == 0:
        return 0.0
    return float(100 * (1 + beta ** 2) * p * r / (beta ** 2 * p + r))


# --- pekerjaan pengujian ----------------------------------------------------------
class Penguji:
    """Satu pekerjaan pengujian pada satu waktu, dijalankan di utas latar."""

    def __init__(self, penjawab, kontrol):
        self.penjawab, self.kontrol = penjawab, kontrol
        self.kunci = threading.Lock()
        self.keadaan = {"berjalan": False}

    def mulai(self, mapel: str, n_per_kelas: int, skenario: list[str],
              kelas_dari: str = "data", seed: int = 42) -> dict:
        with self.kunci:
            if self.keadaan.get("berjalan"):
                raise RuntimeError("masih ada pengujian yang berjalan")
            uji = bagi_data(mapel)["uji"]
            if n_per_kelas > 0:
                # tanpa groupby.apply: pandas 3 membuang kolom pengelompokan
                import pandas as pd
                uji = pd.concat([g.sample(min(n_per_kelas, len(g)), random_state=seed)
                                 for _, g in uji.groupby("kelas")])
            soal = uji.reset_index(drop=True).to_dict("records")
            self.keadaan = {
                "berjalan": True, "id": dt.datetime.now().strftime("%Y%m%d_%H%M%S"),
                "mapel": mapel, "skenario": skenario, "kelas_dari": kelas_dari,
                "n_soal": len(soal), "total": len(soal) * len(skenario), "selesai": 0,
                "galat": 0, "mulai": time.time(), "baris": [], "pesan": "",
                "info_penjawab": self.penjawab.sehat()}
        threading.Thread(target=self._jalan, args=(soal,), daemon=True).start()
        return self.status()

    def _jalan(self, soal):
        k = self.keadaan
        try:
            for sk in k["skenario"]:
                for s in soal:
                    if not k["berjalan"]:
                        break
                    k["pesan"] = f"{sk} - soal {s['pertanyaan'][:60]}"
                    t0 = time.perf_counter()
                    try:
                        # interaktif=False: tidak ada tanya balik maupun konfirmasi kelas,
                        # supaya setiap soal uji dijawab dan skenario tetap sebanding
                        r = self.penjawab.tanya(s["pertanyaan"], k["mapel"],
                                                s["kelas"] if k["kelas_dari"] == "data" else None,
                                                sk, interaktif=False)
                        k["baris"].append(self._nilai(s, r, sk, time.perf_counter() - t0))
                    except Exception as e:
                        k["galat"] += 1
                        k["pesan"] = f"galat: {e}"
                    k["selesai"] += 1
        except Exception:
            k["pesan"] = traceback.format_exc()[-500:]
        finally:
            # simpan dulu, baru tandai selesai, agar UI yang melihat "selesai" langsung
            # menemukan berkas hasilnya di riwayat
            k["durasi"] = round(time.time() - k["mulai"], 1)
            try:
                self._simpan()
            finally:
                k["berjalan"] = False

    def _nilai(self, s, r, sk, detik):
        jawab = r.get("jawaban") or ""
        daftar = self.kontrol.daftar[s["mapel"]]
        rm = hitung_semua(jawab, daftar) or {}
        riw = r.get("riwayat") or []
        baris = {
            "skenario": sk, "kelas": int(s["kelas"]), "kelas_sistem": r.get("kelas"),
            "pertanyaan": s["pertanyaan"], "kunci": s["jawaban"], "jawaban": jawab,
            "status": r.get("status"), "lolos": bool(r.get("lolos")),
            "putaran": r.get("putaran", 0), "adapter_aktif": r.get("adapter_aktif"),
            "konteks": (r.get("konteks") or {}).get("id"),
            "em": exact_match(jawab, s["jawaban"]), "f1": token_f1(jawab, s["jawaban"]),
            "chrf": chrf_pp(jawab, s["jawaban"]),
            "f1_putaran": [round(token_f1(x.get("jawaban", ""), s["jawaban"]), 3) for x in riw],
            "detik": round(detik, 2),
            # dua bukti Plan Agent disimpan terpisah agar bobot dan ambang konfirmasi dapat
            # dikalibrasi ulang sesudahnya tanpa menjalankan ulang model
            "keyakinan_kelas": r.get("keyakinan_kelas"),
            # pengecekan 2 (jawaban menjawab pertanyaan) dan pengecekan 1 (konteks relevan)
            "relevan": r.get("relevan"), "konteks_relevan": r.get("konteks_relevan"),
            "skor_konteks": r.get("skor_konteks"),
            "sebaran_llm": r.get("sebaran_llm"), "sebaran_buku": r.get("sebaran_buku"),
            **{f: (round(rm[f], 3) if f in rm else None) for f in RUMUS},
        }
        return baris

    def hentikan(self):
        self.keadaan["berjalan"] = False

    def status(self) -> dict:
        k = dict(self.keadaan)
        baris = k.pop("baris", [])
        k["ringkasan"] = ringkas(baris) if baris else {}
        k["contoh"] = baris[-8:]
        return k

    def _simpan(self):
        os.makedirs(HASIL, exist_ok=True)
        k = self.keadaan
        path = os.path.join(HASIL, f"uji_{k['id']}_{k['mapel']}.json")
        data = {c: v for c, v in k.items() if c != "baris"}
        data["ringkasan"] = ringkas(k["baris"])
        data["baris"] = k["baris"]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1, default=str)
        k["berkas"] = os.path.relpath(path, AKAR)


def ringkas(baris: list[dict]) -> dict:
    """Tabel capaian per skenario, dan per skenario x jenjang."""
    def agregat(rs):
        if not rs:
            return {}
        a = {"n": len(rs),
             "em": np.mean([r["em"] for r in rs]), "f1": np.mean([r["f1"] for r in rs]),
             "chrf": np.mean([r["chrf"] for r in rs]),
             "patuh": np.mean([r["lolos"] for r in rs]),
             "putaran": np.mean([r["putaran"] for r in rs]),
             "perbaikan": np.mean([r["putaran"] > 1 for r in rs]),
             "batas": np.mean([r["status"] == "batas" for r in rs]),
             "tidak_relevan": np.mean([r["status"] == "tidak_relevan" for r in rs]),
             "tanpa_materi": np.mean([r["status"] == "tidak_ada_materi" for r in rs]),
             "detik": np.mean([r["detik"] for r in rs])}
        tebak = [r for r in rs if r["kelas_sistem"]]
        if tebak:
            a["kelas_tepat"] = np.mean([r["kelas_sistem"] == r["kelas"] for r in tebak])
            a["kelas_tepat_1"] = np.mean([abs(r["kelas_sistem"] - r["kelas"]) <= 1 for r in tebak])
        for f in RUMUS:
            v = [r[f] for r in rs if r.get(f) is not None]
            if v:
                a[f] = np.mean(v)
        return {c: (round(float(v), 4) if isinstance(v, (float, np.floating)) else v)
                for c, v in a.items()}
    hasil = {}
    for sk in sorted({r["skenario"] for r in baris}):
        rs = [r for r in baris if r["skenario"] == sk]
        hasil[sk] = {"semua": agregat(rs),
                     "per_kelas": {k: agregat([r for r in rs if r["kelas"] == k])
                                   for k in range(1, 7) if any(r["kelas"] == k for r in rs)}}
    return hasil


def daftar_hasil() -> list[dict]:
    if not os.path.isdir(HASIL):
        return []
    out = []
    for n in sorted(os.listdir(HASIL), reverse=True):
        if n.endswith(".json"):
            with open(os.path.join(HASIL, n), encoding="utf-8") as f:
                d = json.load(f)
            out.append({"berkas": n, "mapel": d.get("mapel"), "skenario": d.get("skenario"),
                        "n_soal": d.get("n_soal"), "kelas_dari": d.get("kelas_dari"),
                        "mode": (d.get("info_penjawab") or {}).get("mode"),
                        "ringkasan": d.get("ringkasan")})
    return out
