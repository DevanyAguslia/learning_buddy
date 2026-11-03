"""File Validasi_Soal_PJOK dengan potongan Recursive (sudah dirapikan) untuk setiap soal.

Urutan lembar, baris, dan kolom asli tidak diubah; kolom baru ditambahkan di kanan:

  ACUAN (dibuat di laptop, tanpa model) - potongan yang SEHARUSNYA ditemukan:
    potongan Recursive buku kelas soal itu yang paling banyak memuat kata isi konteks
    acuan; bila konteks acuan terbelah ke dua potongan, potongan kedua ikut dicatat.
  WEBSITE (dari tb.evaluasi_pencarian di Kaggle) - 3 potongan yang benar-benar diambil
    website (Qwen3-Embedding + FAISS + reranker, pilih_beragam), beserta apakah potongan
    acuan ikut terkirim. Kosong bila evaluasi belum dijalankan.

    python -m tb.validasi_recursive                                  # kolom ACUAN saja
    python -m tb.validasi_recursive --evaluasi hasil/Evaluasi_Pencarian.xlsx
Keluaran: hasil/Validasi_Soal_PJOK_Recursive.xlsx
"""
from __future__ import annotations

import argparse
import json
import os
from collections import Counter

from .evaluasi_pencarian import AMBANG_TERMUAT, PATH_SOAL, _cakup
from .pencarian import muat_potongan

AKAR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KELUAR = os.path.join(AKAR, "hasil", "Validasi_Soal_PJOK_Recursive.xlsx")
TAMBAH_MIN = 0.2      # potongan kedua dicatat bila menambah cakupan >= 20 poin

KOLOM_ACUAN = ["acuan: id potongan", "acuan: halaman PDF", "acuan: cakupan konteks (%)",
               "acuan: memuat jawaban (%)", "acuan: teks potongan",
               "acuan: potongan kedua", "acuan: cakupan 2 potongan (%)"]
KOLOM_WEB = ["website: potongan 1", "website: skor 1", "website: teks 1",
             "website: potongan 2", "website: skor 2", "website: teks 2",
             "website: potongan 3", "website: skor 3", "website: teks 3",
             "website: potongan acuan ikut terkirim?",
             "website: cakupan konteks 3 potongan (%)", "website: memuat jawaban (%)"]


def acuan(konteks: str, jawaban: str, ps: list[dict]) -> dict:
    """Potongan yang paling banyak memuat konteks acuan, dan potongan kedua bila perlu."""
    if not ps:
        return {}
    cak = [_cakup([p], konteks) for p in ps]
    i = max(range(len(ps)), key=lambda j: cak[j])
    j2 = max((j for j in range(len(ps)) if j != i), key=lambda j: _cakup([ps[i], ps[j]], konteks),
             default=None)
    dua = _cakup([ps[i], ps[j2]], konteks) if j2 is not None else cak[i]
    out = {"id": ps[i]["id"], "halaman": ps[i]["halaman"], "cakupan": cak[i],
           "jawaban": _cakup([ps[i]], jawaban), "teks": ps[i]["teks"]}
    if j2 is not None and dua - cak[i] >= TAMBAH_MIN:
        out.update(kedua=ps[j2]["id"], cakupan2=dua)
    return out


def _persen(x):
    return None if x is None or x != x else round(100 * x, 1)


def tulis(pilihan: dict | None = None, keluar: str = KELUAR, sumber: str = PATH_SOAL) -> str:
    """pilihan: {id_soal: {"ids": [...3 id potongan...], "skor": [...]}} dari evaluasi."""
    import openpyxl
    from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
    from openpyxl.styles import Alignment, Font, PatternFill

    ps = [p for p in muat_potongan() if p["mapel"] == "PJOK"]
    per_kelas, per_id = {}, {p["id"]: p for p in ps}
    for p in ps:
        per_kelas.setdefault(int(p["kelas"]), []).append(p)

    wb = openpyxl.load_workbook(sumber)
    tebal, kuning, hijau = Font(bold=True), PatternFill("solid", fgColor="FDF6E3"), \
        PatternFill("solid", fgColor="E3F1E8")
    bungkus = Alignment(wrap_text=True, vertical="top")
    rekap = Counter()
    for ws in wb.worksheets:
        if not ws.title.lower().startswith("kelas"):
            continue
        kepala = [c.value for c in ws[1]]
        kol = {n: i for i, n in enumerate(kepala)}
        mulai = len(kepala) + 1
        baru = KOLOM_ACUAN + KOLOM_WEB
        for k, nama in enumerate(baru):
            c = ws.cell(row=1, column=mulai + k, value=nama)
            c.font, c.fill = tebal, (kuning if nama.startswith("acuan") else hijau)
            huruf = c.column_letter
            ws.column_dimensions[huruf].width = 60 if "teks" in nama else 16
        for r in range(2, ws.max_row + 1):
            id_soal = ws.cell(r, kol["id"] + 1).value
            if not id_soal:
                continue
            kelas = int(ws.cell(r, kol["kelas"] + 1).value)
            konteks = ws.cell(r, kol["konteks (kutipan buku)"] + 1).value or ""
            jawab = ws.cell(r, kol["jawaban (kutipan buku)"] + 1).value or ""
            a = acuan(konteks, jawab, per_kelas.get(kelas, []))
            nilai = [a.get("id"), a.get("halaman"), _persen(a.get("cakupan")),
                     _persen(a.get("jawaban")), a.get("teks"), a.get("kedua"),
                     _persen(a.get("cakupan2"))]
            rekap[(kelas, "soal")] += 1
            rekap[(kelas, "acuan")] += a.get("cakupan", 0) >= AMBANG_TERMUAT
            pil = (pilihan or {}).get(id_soal)
            if pil:
                ids = list(pil["ids"])[:3] + [None] * (3 - len(pil["ids"][:3]))
                skor = list(pil.get("skor") or [])[:3] + [None] * 3
                kirim = [per_id[i] for i in ids if i in per_id]
                ikut = bool(a.get("id")) and (a["id"] in ids or a.get("kedua") in ids)
                rekap[(kelas, "ikut")] += ikut
                for n in range(3):
                    nilai += [ids[n], None if skor[n] is None else round(float(skor[n]), 3),
                              per_id[ids[n]]["teks"] if ids[n] in per_id else None]
                nilai += ["Ya" if ikut else "Tidak", _persen(_cakup(kirim, konteks)),
                          _persen(_cakup(kirim, jawab))]
            for k, v in enumerate(nilai):
                c = ws.cell(r, mulai + k, value=ILLEGAL_CHARACTERS_RE.sub("", v) if isinstance(v, str) else v)
                if isinstance(v, str) and len(v) > 40:
                    c.alignment = bungkus
        ws.freeze_panes = "F2"

    if "Ringkasan Recursive" in wb.sheetnames:
        del wb["Ringkasan Recursive"]
    ws = wb.create_sheet("Ringkasan Recursive", 1)
    ws.append(["kelas", "soal", "potongan acuan memuat >= 50% konteks",
               "potongan acuan ikut terkirim website (dari 3)"])
    for k in sorted({k for k, _ in rekap}):
        ws.append([k, rekap[(k, "soal")], rekap[(k, "acuan")],
                   rekap[(k, "ikut")] if pilihan else "belum dijalankan"])
    ws.append([])
    ws.append(["Kolom acuan: potongan Recursive (sudah dirapikan) yang paling banyak memuat "
               "konteks acuan soal, yaitu yang seharusnya ditemukan."])
    ws.append(["Kolom website: 3 potongan yang benar-benar diambil website di Kaggle "
               "(tb.evaluasi_pencarian); kosong bila evaluasi belum dijalankan."])
    for c in ws[1]:
        c.font, c.fill = tebal, kuning
    for huruf, lebar in zip("ABCD", (8, 8, 36, 44)):
        ws.column_dimensions[huruf].width = lebar
    os.makedirs(os.path.dirname(keluar), exist_ok=True)
    wb.save(keluar)
    print(f"tersimpan: {keluar}")
    return keluar


def pilihan_dari_evaluasi(path: str) -> dict:
    import pandas as pd
    d = pd.read_excel(path, sheet_name="Per_Soal")
    return {r["id"]: {"ids": json.loads(r["kirim_ids"]), "skor": json.loads(r["kirim_skor"])}
            for _, r in d.iterrows() if isinstance(r.get("kirim_ids"), str)}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--evaluasi", default=None, help="hasil/Evaluasi_Pencarian.xlsx dari Kaggle")
    a = ap.parse_args()
    tulis(pilihan_dari_evaluasi(a.evaluasi) if a.evaluasi else None)
