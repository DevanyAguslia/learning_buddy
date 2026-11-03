"""Mengunggah Learning Buddy ke Hugging Face (cadangan bila server kampus belum siap).

Tiga repo milik akun HF Devany:
    <akun>/learning-buddy-kode      dataset PRIVATE : kode + data (hasil deploy/kemas.py)
    <akun>/learning-buddy-adapter   model   PRIVATE : adapter PJOK/PKN grade_1..6 + ambang_relevan.json
    <akun>/learning-buddy           Space   publik  : Dockerfile, mulai.sh, requirements (tanpa kode)

Sekali saja, login dulu dengan token HF berizin "Write":
    hf auth login

Lalu dari folder LearningBuddy:
    python deploy/hf/unggah_hf.py --akun <akun_hf>                    # semua bagian
    python deploy/hf/unggah_hf.py --akun <akun_hf> --bagian kode --mulai-ulang   # perbarui kode saja

Bagian "space" juga menulis deploy/vercel/vercel.json dengan alamat Space yang benar.
Hardware GPU dan secret (HF_TOKEN, TB_DATABASE_URL, TB_KODE_GURU, TB_KODE_PENELITI) diisi
sendiri di halaman Settings Space; skrip ini tidak pernah menyentuh rahasia.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

AKAR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SINI = os.path.dirname(os.path.abspath(__file__))
PAKET = os.path.join(AKAR, "dist", "unggah_kaggle")
ADAPTER = r"D:\Skripsi\Pegasus_kirim\adapters"
AMBANG = r"D:\Skripsi\Pegasus_kirim\hasil\ambang_relevan.json"
VERCEL = os.path.join(AKAR, "deploy", "vercel", "vercel.json")


def unggah_kode(api, repo: str):
    print("== kode: mengemas ulang (deploy/kemas.py)")
    subprocess.run([sys.executable, os.path.join(AKAR, "deploy", "kemas.py")], check=True)
    api.create_repo(repo, repo_type="dataset", private=True, exist_ok=True)
    # delete_patterns: berkas lama yang tidak ada lagi di paket ikut dihapus
    api.upload_folder(folder_path=PAKET, repo_id=repo, repo_type="dataset",
                      delete_patterns="*", commit_message="Perbarui kode Learning Buddy")
    print(f"   terunggah: https://huggingface.co/datasets/{repo}")


def unggah_adapter(api, repo: str, folder: str, ambang: str):
    for m in ("PJOK", "PKN"):
        ada = [k for k in range(1, 7)
               if os.path.exists(os.path.join(folder, m, f"grade_{k}", "adapter_config.json"))]
        print(f"== adapter {m}: {len(ada)}/6")
        if len(ada) < 6:
            raise SystemExit(f"adapter {m} belum lengkap di {folder}\\{m}")
    if not os.path.exists(ambang):
        raise SystemExit(f"tidak ada {ambang}")
    api.create_repo(repo, private=True, exist_ok=True)
    api.upload_folder(folder_path=folder, repo_id=repo, allow_patterns=["PJOK/**", "PKN/**"],
                      commit_message="Adapter PJOK dan PKN kelas 1-6")
    api.upload_file(path_or_fileobj=ambang, path_in_repo="ambang_relevan.json", repo_id=repo,
                    commit_message="Ambang pengecekan 1")
    print(f"   terunggah: https://huggingface.co/{repo} (1,9 GB, bisa beberapa menit)")


RAHASIA = [("HF_TOKEN", "token HF jenis Read (space-baca)"),
           ("TB_DATABASE_URL", "connection string Neon (postgresql://...)"),
           ("TB_KODE_GURU", "kode pendaftaran guru (buatan sendiri)"),
           ("TB_KODE_PENELITI", "kode pendaftaran peneliti (buatan sendiri)")]


def buat_space(api, repo: str, repo_kode: str, repo_adapter: str, hardware: str, tidur: int):
    """Space Docker di cpu-basic gratis kini butuh langganan PRO (galat 402), jadi Space
    langsung dibuat di hardware berbayar (dibayar dari credits) beserta secret-nya.
    Secret diketik di terminal (tidak tampil) dan dikirim langsung ke Hugging Face."""
    import getpass
    print(f"== Space belum ada: dibuat dengan hardware {hardware}, tidur otomatis {tidur // 60} menit")
    print("   BIAYA GPU MULAI BERJALAN begitu Space dibuat (L4 $0,80/jam).")
    if input("   Lanjut? ketik YA: ").strip().upper() != "YA":
        raise SystemExit("dibatalkan, Space tidak dibuat")
    rahasia = []
    for kunci, ket in RAHASIA:
        nilai = getpass.getpass(f"   {kunci} ({ket}): ").strip()
        if not nilai:
            raise SystemExit(f"{kunci} kosong, dibatalkan")
        rahasia.append({"key": kunci, "value": nilai})
    api.create_repo(repo, repo_type="space", space_sdk="docker", private=False,
                    space_hardware=hardware, space_sleep_time=tidur, space_secrets=rahasia,
                    space_variables=[{"key": "TB_REPO_KODE", "value": repo_kode},
                                     {"key": "TB_REPO_ADAPTER", "value": repo_adapter}])
    print("   Space dibuat dengan secret HF_TOKEN, TB_DATABASE_URL, TB_KODE_GURU, TB_KODE_PENELITI")


def unggah_space(api, repo: str, repo_kode: str, repo_adapter: str, hardware: str = "l4x1",
                 tidur: int = 900):
    if not api.repo_exists(repo, repo_type="space"):
        buat_space(api, repo, repo_kode, repo_adapter, hardware, tidur)
    with tempfile.TemporaryDirectory() as tmp:
        for asal, nama in [("Dockerfile", "Dockerfile"), ("mulai.sh", "mulai.sh"),
                           ("README_SPACE.md", "README.md")]:
            shutil.copy(os.path.join(SINI, asal), os.path.join(tmp, nama))
        for b in ("requirements.txt", "requirements-gpu.txt"):
            shutil.copy(os.path.join(AKAR, b), os.path.join(tmp, b))
        # mulai.sh harus berakhir-baris LF agar bash di Linux tidak gagal
        p = os.path.join(tmp, "mulai.sh")
        with open(p, "rb") as f:
            isi = f.read().replace(b"\r\n", b"\n")
        with open(p, "wb") as f:
            f.write(isi)
        api.upload_folder(folder_path=tmp, repo_id=repo, repo_type="space",
                          commit_message="Berkas Space Learning Buddy")
    api.add_space_variable(repo, "TB_REPO_KODE", repo_kode)
    api.add_space_variable(repo, "TB_REPO_ADAPTER", repo_adapter)
    alamat = f"https://{api.space_info(repo).subdomain}.hf.space"
    os.makedirs(os.path.dirname(VERCEL), exist_ok=True)
    with open(VERCEL, "w", encoding="utf-8") as f:
        json.dump({"$schema": "https://openapi.vercel.sh/vercel.json",
                   "rewrites": [{"source": "/(.*)", "destination": f"{alamat}/$1"}]}, f, indent=2)
        f.write("\n")
    print(f"== Space: https://huggingface.co/spaces/{repo}")
    print(f"   alamat aplikasi: {alamat}")
    print(f"   vercel.json ditulis: {VERCEL}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--akun", required=True, help="nama akun (username) Hugging Face")
    ap.add_argument("--bagian", nargs="+", choices=["kode", "adapter", "space"],
                    default=["kode", "adapter", "space"])
    ap.add_argument("--space", default="learning-buddy", help="nama Space")
    ap.add_argument("--adapter", default=ADAPTER, help="folder berisi PJOK/ dan PKN/")
    ap.add_argument("--ambang", default=AMBANG, help="ambang_relevan.json")
    ap.add_argument("--hardware", default="l4x1", help="hardware Space saat pertama dibuat")
    ap.add_argument("--tidur", type=int, default=900,
                    help="detik tanpa pengunjung sebelum Space tidur sendiri (bawaan 15 menit)")
    ap.add_argument("--mulai-ulang", action="store_true",
                    help="restart Space sesudah unggah agar kode baru dipakai")
    a = ap.parse_args()

    from huggingface_hub import HfApi
    api = HfApi()
    print("masuk sebagai:", api.whoami()["name"])
    repo_kode = f"{a.akun}/learning-buddy-kode"
    repo_adapter = f"{a.akun}/learning-buddy-adapter"
    repo_space = f"{a.akun}/{a.space}"
    if "kode" in a.bagian:
        unggah_kode(api, repo_kode)
    if "adapter" in a.bagian:
        unggah_adapter(api, repo_adapter, a.adapter, a.ambang)
    if "space" in a.bagian:
        unggah_space(api, repo_space, repo_kode, repo_adapter, a.hardware, a.tidur)
    if a.mulai_ulang:
        api.restart_space(repo_space)
        print("== Space dinyalakan ulang; pantau tab Logs di halaman Space")


if __name__ == "__main__":
    main()
