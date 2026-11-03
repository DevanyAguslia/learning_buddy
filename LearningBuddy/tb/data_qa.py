"""Pemuat data tanya jawab kedua mata pelajaran dalam satu bentuk seragam."""
from __future__ import annotations

import os
import re

import pandas as pd

_AKAR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "qa")
SUMBER = {
    "PJOK": (os.environ.get("TB_QA_PJOK", os.path.join(_AKAR, "PJOK.xlsx")), "for-finetune"),
    "PKN": (os.environ.get("TB_QA_PKN", os.path.join(_AKAR, "PKN.xlsx")), "All"),
}


def _kelas(v) -> int | None:
    m = re.search(r"\d", str(v))
    return int(m.group(0)) if m else None


def muat_qa(mapel: str) -> pd.DataFrame:
    """Kolom keluaran: mapel, kelas, pertanyaan, jawaban (baris tak lengkap dibuang)."""
    path, sheet = SUMBER[mapel]
    df = pd.read_excel(path, sheet_name=sheet)
    df = df.dropna(subset=["Kelas", "Pertanyaan", "Jawaban"]).copy()
    out = pd.DataFrame({
        "mapel": mapel,
        "kelas": df["Kelas"].map(_kelas),
        "pertanyaan": df["Pertanyaan"].astype(str).str.strip(),
        "jawaban": df["Jawaban"].astype(str).str.strip(),
    })
    out = out[out["kelas"].between(1, 6) & out["pertanyaan"].ne("") & out["jawaban"].ne("")]
    return out.reset_index(drop=True)


def bagi_data(mapel: str, seed: int = 42) -> dict[str, pd.DataFrame]:
    """Pembagian kanonik, sama persis dengan notebook pelatihan (SEL 7 tgar-g1-*):
    per jenjang 80/20 latih+validasi lawan uji, lalu 80/20 latih lawan validasi.
    Hasilnya PJOK 622/158/197 dan Pancasila 497/126/158 (Tabel 1.1)."""
    from sklearn.model_selection import train_test_split
    df = muat_qa(mapel)
    bagian = {"latih": [], "validasi": [], "uji": []}
    for g in range(1, 7):
        sub = df[df["kelas"] == g]
        lv, uji = train_test_split(sub, test_size=0.2, random_state=seed)
        latih, val = train_test_split(lv, test_size=0.2, random_state=seed)
        bagian["latih"].append(latih); bagian["validasi"].append(val); bagian["uji"].append(uji)
    return {k: pd.concat(v).reset_index(drop=True) for k, v in bagian.items()}
