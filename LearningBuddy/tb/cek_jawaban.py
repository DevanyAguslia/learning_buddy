"""Memeriksa berkas jawaban hasil `python -m tb.kuesioner_guru ambil` sebelum dipakai.

    python -m tb.cek_jawaban hasil/kuesioner_guru/uji_saringan.json

Yang dihitung: jawaban beraksara asing (Mandarin, Arab, ...), tulisan rusak (kata berulang,
kalimat menggantung), jawaban sangat pendek, jawaban A = B, dan sebaran status.
"""
from __future__ import annotations

import argparse
import collections
import json

from .agen import jawaban_rusak
from .model import AKSARA_ASING


def periksa(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    asing, rusak, pendek = [], [], []
    for d in data:
        for kolom in ("tanpa_kontrol", "dengan_kontrol"):
            t = d.get(kolom) or ""
            if AKSARA_ASING.search(t):
                asing.append((d["no"], kolom, t))
            elif t and jawaban_rusak(t):
                rusak.append((d["no"], kolom, t))
        if len((d.get("dengan_kontrol") or "").split()) <= 3:
            pendek.append((d["no"], d.get("dengan_kontrol")))
    return {"n": len(data), "asing": asing, "rusak": rusak, "pendek": pendek,
            "sama": sum(d.get("tanpa_kontrol") == d.get("dengan_kontrol") for d in data),
            "status": collections.Counter(d.get("status") for d in data)}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("berkas")
    h = periksa(ap.parse_args().berkas)
    print(f"jumlah soal           : {h['n']}")
    print(f"beraksara asing       : {len(h['asing'])}   <- harus 0")
    for no, kolom, t in h["asing"][:5]:
        print(f"   no {no} {kolom}: {t[:100]}")
    print(f"tulisan rusak         : {len(h['rusak'])}")
    for no, kolom, t in h["rusak"][:5]:
        print(f"   no {no} {kolom}: {t[:100]}")
    print(f"jawaban <= 3 kata (B) : {len(h['pendek'])}")
    print(f"jawaban A = B         : {h['sama']}")
    print("status                :", dict(h["status"]))


if __name__ == "__main__":
    main()
