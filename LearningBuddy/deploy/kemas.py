"""Mengemas kode + data siap pakai menjadi satu zip untuk diunggah sebagai Kaggle Dataset.

    python deploy/kemas.py      ->  dist/learning-buddy-kode.zip
                                    dist/unggah_kaggle/LearningBuddy/   (folder yang sama)

Folder dipakai bila Kaggle menolak zip: seret folder LearningBuddy ke halaman unggah.
Yang ikut: tb/, web/, deploy/, data/potongan.jsonl, data/kontrol_keterbacaan*.json,
data/qa/*.xlsx (pembagian kanonik, pelatihan, kalibrasi, soal uji Merdeka),
requirements*.txt, README.md.
PDF buku, log, dan hasil TIDAK ikut. Jadikan dataset Kaggle-nya Private.
"""
import os
import shutil
import zipfile

AKAR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IKUT_FOLDER = ["tb", "web", "deploy"]       # eksperimen chunking: proyek ../Eksperimen_Chunking
LEWATI = ("__pycache__", "hasil", "log_")
IKUT_BERKAS = ["data/potongan.jsonl", "data/kontrol_keterbacaan.json",
               "data/kontrol_keterbacaan_bentuk.json", "requirements.txt",
               "requirements-gpu.txt", "README.md", "data/qa/PJOK.xlsx",
               "data/qa/PKN.xlsx", "data/qa/PJOK_konteks_acuan.xlsx",
               "data/qa/Validasi_Soal_PJOK.xlsx", "data/qa/Soal_PKN_Merdeka.xlsx",
               "data/qa/pembagian_merdeka.csv", "data/qa/Soal_Validasi_Guru.csv",
               # deploy server kampus (deploy/server/Dockerfile.web)
               ".dockerignore", "data/acuan_rumus.json", "hasil/evaluasi_rumus.json"]


def main():
    os.makedirs(os.path.join(AKAR, "dist"), exist_ok=True)
    keluar = os.path.join(AKAR, "dist", "learning-buddy-kode.zip")
    folder_keluar = os.path.join(AKAR, "dist", "unggah_kaggle")
    shutil.rmtree(folder_keluar, ignore_errors=True)
    n = 0

    class _Ganda:
        """Menulis ke zip sekaligus menyalin ke folder unggah."""
        def __init__(self, z): self.z = z
        def write(self, p, nama):
            self.z.write(p, nama)
            tujuan = os.path.join(folder_keluar, nama)
            os.makedirs(os.path.dirname(tujuan), exist_ok=True)
            shutil.copy2(p, tujuan)

    with zipfile.ZipFile(keluar, "w", zipfile.ZIP_DEFLATED) as zz:
        z = _Ganda(zz)
        for folder in IKUT_FOLDER:
            for akar, _, berkas in os.walk(os.path.join(AKAR, folder)):
                if any(x in akar for x in LEWATI):
                    continue
                for b in berkas:
                    if (b.startswith("log_") or b.endswith(".local.sql")
                            or (b.startswith(".env") and not b.endswith(".contoh"))):
                        continue                 # rahasia lokal (sandi database, kunci) tidak ikut
                    p = os.path.join(akar, b)
                    z.write(p, os.path.join("LearningBuddy", os.path.relpath(p, AKAR)))
                    n += 1
        for b in IKUT_BERKAS:
            p = os.path.join(AKAR, b)
            if os.path.exists(p):
                z.write(p, os.path.join("LearningBuddy", b))
                n += 1
            else:
                print("  dilewati, tidak ada:", b)
    print(f"{n} berkas -> {keluar} ({os.path.getsize(keluar) / 1e6:.1f} MB)")
    print(f"folder untuk diunggah -> {os.path.join(folder_keluar, 'LearningBuddy')}")


if __name__ == "__main__":
    main()
