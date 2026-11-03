"""Kuesioner usability website Learning Buddy (UAT): daftar tugas + System Usability Scale.

SUS 10 butir (Brooke, 1996) memakai terjemahan Indonesia Sharfina & Santoso (2016), "sistem ini"
diganti "website Learning Buddy". Versi siswa memakai kalimat yang lebih sederhana tetapi urutan dan
arah butirnya sama (ganjil positif, genap negatif), sehingga skor SUS tetap dihitung dengan cara
yang sama: ganjil (nilai - 1), genap (5 - nilai), jumlah x 2,5.

    python -m tb.kuesioner_usability --folder D:\\Skripsi\\UAT\\Kuesioner_Usability
"""
from __future__ import annotations

import argparse
import os

from tb.kuesioner_guru import ke_pdf

HASIL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "hasil", "kuesioner_usability")

SKALA_SUS = ["Sangat tidak setuju", "Tidak setuju", "Ragu-ragu", "Setuju", "Sangat setuju"]

SUS_DEWASA = [
    "Saya berpikir akan menggunakan website Learning Buddy lagi.",
    "Saya merasa website Learning Buddy rumit untuk digunakan.",
    "Saya merasa website Learning Buddy mudah digunakan.",
    "Saya membutuhkan bantuan dari orang lain atau teknisi dalam menggunakan website Learning Buddy.",
    "Saya merasa fitur-fitur website Learning Buddy berjalan dengan semestinya.",
    "Saya merasa ada banyak hal yang tidak konsisten (tidak serasi) pada website Learning Buddy.",
    "Saya merasa orang lain akan memahami cara menggunakan website Learning Buddy dengan cepat.",
    "Saya merasa website Learning Buddy membingungkan.",
    "Saya merasa tidak ada hambatan dalam menggunakan website Learning Buddy.",
    "Saya perlu membiasakan diri terlebih dahulu sebelum menggunakan website Learning Buddy.",
]

SUS_SISWA = [
    "Aku mau memakai Learning Buddy lagi.",
    "Learning Buddy susah dipakai.",
    "Learning Buddy mudah dipakai.",
    "Aku perlu dibantu orang lain untuk memakai Learning Buddy.",
    "Tombol dan menu di Learning Buddy bekerja dengan baik.",
    "Tampilan Learning Buddy tidak teratur dan membuatku bingung.",
    "Teman-temanku pasti cepat bisa memakai Learning Buddy.",
    "Learning Buddy membingungkan.",
    "Aku bisa memakai Learning Buddy sendiri tanpa kesulitan.",
    "Aku harus belajar banyak dulu sebelum bisa memakai Learning Buddy.",
]

TUGAS = {
    "siswa": ["Masuk atau membuat akun",
              "Memasukkan kode sekolah dari guru",
              "Memilih mata pelajaran dan kelas",
              "Mengirim pertanyaan dan membaca jawabannya",
              "Membuka 'Sumber jawaban'",
              "Membuka lagi percakapan lama di 'Riwayat chat'"],
    "guru": ["Membuat akun dengan kode pendaftaran guru",
             "Bertanya di halaman Chat dan membaca jawabannya",
             "Membuat sekolah dan mencatat kode sekolah",
             "Mengunggah buku PDF di Lab > Buku sekolah",
             "Mengukur teks di Lab > Ukur teks"],
}

HASIL_TUGAS = ["Berhasil sendiri", "Berhasil dengan bantuan", "Tidak berhasil"]


def buat_docx(path: str, versi: str) -> str:
    """versi 'guru' atau 'siswa'. Tabel tanpa warna, setiap kotak centang punya kolom sendiri."""
    from docx import Document
    from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Cm, Pt

    siswa = versi == "siswa"
    doc = Document()
    sek = doc.sections[0]
    sek.page_width, sek.page_height = Cm(21), Cm(29.7)
    for sisi in ("left_margin", "right_margin"):
        setattr(sek, sisi, Cm(1.8))
    sek.top_margin = sek.bottom_margin = Cm(1.4)
    gaya = doc.styles["Normal"]
    gaya.font.name, gaya.font.size = "Calibri", Pt(11)
    gaya.element.rPr.rFonts.set(qn("w:eastAsia"), "Calibri")

    def paragraf(teks, tebal=False, ukuran=11, sesudah=4):   # semua teks hitam
        p = doc.add_paragraph()
        r = p.add_run(teks)
        r.bold, r.font.size = tebal, Pt(ukuran)
        p.paragraph_format.space_after = Pt(sesudah)
        return p

    def isi(sel, teks, tebal=False, ukuran=10, tengah=False):
        sel.text = ""
        p = sel.paragraphs[0]
        r = p.add_run(teks)
        r.bold, r.font.size = tebal, Pt(ukuran)
        if tengah:
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        sel.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
        return sel

    def tabel(baris, lebar):
        t = doc.add_table(rows=baris, cols=len(lebar))
        t.style = "Table Grid"
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        t.autofit = False
        tata = OxmlElement("w:tblLayout")
        tata.set(qn("w:type"), "fixed")
        t._tbl.tblPr.append(tata)
        for kol, w in zip(t.columns, lebar):
            kol.width = w
        for r in t.rows:
            for sel, w in zip(r.cells, lebar):
                sel.width = w
            r._tr.get_or_add_trPr().append(OxmlElement("w:cantSplit"))
        return t

    judul = "Kuesioner Penggunaan Learning Buddy" + (" (Siswa)" if siswa else " (Guru)")
    paragraf(judul, True, 16)
    identitas = ([("Nama", 40), ("Kelas", 15), ("Sekolah", 40)] if siswa else
                 [("Nama", 40), ("Sekolah", 40), ("Mata pelajaran yang diajar", 25),
                  ("Tingkat kelas yang diajari", 25)])
    for label, titik in identitas:
        paragraf(f"{label} : " + "." * titik, sesudah=2)
    paragraf("Perangkat :   ☐ HP    ☐ Tablet    ☐ Laptop/PC        "
             "Browser :  ☐ Chrome   ☐ Edge   ☐ Safari   ☐ Lain", sesudah=6)
    if siswa:
        paragraf("Untuk siswa kelas 1 dan 2, guru atau peneliti boleh membacakan setiap kalimat dan "
                 "membantu mencentang sesuai jawaban siswa.", ukuran=9, sesudah=6)

    # bagian 1: tugas
    paragraf("Bagian 1. Tugas yang dicoba", True, 12)
    paragraf("Coba setiap kegiatan di bawah ini, lalu centang satu kotak yang paling sesuai." if not siswa else
             "Coba kegiatan di bawah ini satu per satu, lalu centang satu kotak.", ukuran=10)
    daftar = TUGAS[versi]
    lebar = [Cm(0.9), Cm(8.4)] + [Cm(2.6)] * 3
    t = tabel(len(daftar) + 1, lebar)
    for j, teks in enumerate(["No", "Kegiatan", *HASIL_TUGAS]):
        isi(t.cell(0, j), teks, True, 9, j != 1)
    for i, teks in enumerate(daftar, 1):
        isi(t.cell(i, 0), str(i), ukuran=10, tengah=True)
        isi(t.cell(i, 1), teks)
        for j in range(3):
            isi(t.cell(i, 2 + j), "☐", ukuran=13, tengah=True)

    # bagian 2: SUS
    paragraf("", ukuran=4, sesudah=0)
    paragraf("Bagian 2. Pendapat tentang website", True, 12)
    paragraf(("Baca setiap kalimat, lalu centang satu kotak yang paling sesuai dengan perasaanmu. "
              "Tidak ada jawaban benar atau salah.") if siswa else
             "Centang satu kotak pada setiap pernyataan sesuai pengalaman Bapak/Ibu memakai website "
             "Learning Buddy. Tidak ada jawaban benar atau salah.", ukuran=10)
    butir = SUS_SISWA if siswa else SUS_DEWASA
    lebar = [Cm(0.9), Cm(10.0)] + [Cm(1.3)] * 5
    t = tabel(len(butir) + 2, lebar)
    isi(t.cell(0, 0), "No", True, 9, True)
    isi(t.cell(0, 1), "Pernyataan", True, 9)
    isi(t.cell(1, 0), "", ukuran=8)
    isi(t.cell(1, 1), "", ukuran=8)
    for k, label in enumerate(SKALA_SUS):
        isi(t.cell(0, 2 + k), str(k + 1), True, 10, True)
        isi(t.cell(1, 2 + k), label, False, 7.5, True)
    for i, teks in enumerate(butir, 2):
        isi(t.cell(i, 0), str(i - 1), ukuran=10, tengah=True)
        isi(t.cell(i, 1), teks, ukuran=10.5 if siswa else 10)
        for k in range(5):
            isi(t.cell(i, 2 + k), "☐", ukuran=13, tengah=True)

    # bagian 3: saran
    paragraf("", ukuran=4, sesudah=0)
    paragraf("Bagian 3. Saran", True, 12)
    for tanya in (["Apa yang paling kamu suka dari Learning Buddy?",
                   "Apa yang membuatmu bingung atau susah?"] if siswa else
                  ["Bagian mana yang paling membantu?",
                   "Bagian mana yang membingungkan atau perlu diperbaiki?"]):
        paragraf(tanya, ukuran=10, sesudah=2)
        for _ in range(2):
            paragraf("." * 210, ukuran=8, sesudah=4)
    paragraf("Terima kasih atas bantuannya.", ukuran=10)
    doc.save(path)
    return path


def buat(folder: str = HASIL) -> list[str]:
    os.makedirs(folder, exist_ok=True)
    keluar = []
    for versi, nama in (("guru", "Guru"), ("siswa", "Siswa")):
        dx = buat_docx(os.path.join(folder, f"Kuesioner_Usability_{nama}.docx"), versi)
        keluar.append(dx)
        pdf = ke_pdf(dx)
        if pdf:
            keluar.append(pdf)
    return keluar


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--folder", default=HASIL, help="folder keluaran docx/pdf")
    for p in buat(ap.parse_args().folder):
        print("tersimpan:", p)
