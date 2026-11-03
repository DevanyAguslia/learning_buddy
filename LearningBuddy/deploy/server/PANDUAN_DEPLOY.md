# Panduan Deploy Learning Buddy di Server Kampus

Susunan yang dipakai (saran Jessen): **web** dibungkus Docker di server Linux, **model**
jadi layanan sendiri di server GPU. Cloudflare tidak dipakai; kedua server bicara lewat IP
internal kampus.

```
Siswa/Guru ──► Server LINUX (Docker)                       Server GPU (layanan MODEL)
               ├─ web  : halaman chat, Lab, akun   ─API─►  ├─ Qwen2.5-7B 4-bit + 12 adapter
               └─ db   : PostgreSQL (akun, riwayat)        ├─ Qwen3-Embedding-4B + FAISS + reranker
                                                           └─ 4 agen (Perceive-Plan-Act-Reflect)
```

| Berkas di `deploy/server/` | Untuk |
|---|---|
| `Dockerfile.web`, `docker-compose.web.yml`, `.env.web.contoh` | server web (Linux + Docker) |
| `Dockerfile.gpu`, `docker-compose.gpu.yml`, `.env.gpu.contoh`, `mulai_gpu.sh` | server GPU Linux + Docker |
| `mulai_gpu.ps1` | server GPU Windows tanpa Docker |

Kebutuhan server GPU: NVIDIA, VRAM minimal 16 GB (disarankan 24 GB), RAM 32 GB, disk
kosong 50 GB, bisa mengunduh dari HuggingFace (~20 GB sekali saja).

> Keamanan: kata sandi server, `DB_PASSWORD`, dan `TB_KUNCI` tidak boleh ditulis di chat,
> GitHub, atau dokumen skripsi. Berkas `.env.web` dan `.env.gpu` hanya ada di servernya.

---

## A. Persiapan di laptop

1. Kemas kode terbaru (folder LearningBuddy):
   ```
   D:\tbenv\Scripts\python.exe deploy\kemas.py
   ```
   Hasilnya folder `dist\unggah_kaggle\LearningBuddy` (kode + data + `deploy\server`).
2. Siapkan folder adapter dengan susunan PERSIS seperti ini:
   ```
   adapters\
     PJOK\grade_1 ... grade_6   <- isi D:\Skripsi\adapter-pjok\adapters_recursive
     PKN\grade_1  ... grade_6   <- isi D:\Skripsi\adapter-pkn\adapters\PKN
   hasil\
     ambang_relevan.json        <- D:\Skripsi\adapter-pkn\hasil\ambang_relevan.json
   ```
3. Buat dua nilai acak (simpan baik-baik, jangan dibagikan):
   ```
   D:\tbenv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(32))"
   ```
   Jalankan dua kali: satu untuk `TB_KUNCI`, satu untuk `DB_PASSWORD`.
4. Salin `LearningBuddy` ke server web dan server GPU, lalu `adapters` + `hasil` ke server GPU
   (lewat RDP salin-tempel, WinSCP, atau `scp`).

## B. Server GPU

Cek dulu GPU terlihat: `nvidia-smi` (harus menampilkan nama GPU dan VRAM).

### B1. Linux + Docker
1. Pastikan NVIDIA Container Toolkit terpasang:
   `docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi`
2. Di folder `LearningBuddy`:
   ```
   cp deploy/server/.env.gpu.contoh deploy/server/.env.gpu
   nano deploy/server/.env.gpu        # isi TB_KUNCI, FOLDER_ADAPTER, FOLDER_HASIL
   docker compose -f deploy/server/docker-compose.gpu.yml --env-file deploy/server/.env.gpu up -d --build
   docker compose -f deploy/server/docker-compose.gpu.yml logs -f
   ```
3. Jalan pertama mengunduh model dan membangun indeks (15-30 menit). Tunggu sampai log
   menampilkan `adapter PJOK: 6/6`, `adapter PKN: 6/6`, lalu `Uvicorn running on http://0.0.0.0:8000`.

### B2. Windows tanpa Docker
1. Pasang driver NVIDIA terbaru dan Python 3.11 (centang *Add to PATH*).
2. PowerShell di folder `LearningBuddy` (sekali saja):
   ```
   python -m venv .venv
   .venv\Scripts\python.exe -m pip install --upgrade pip
   .venv\Scripts\python.exe -m pip install torch --index-url https://download.pytorch.org/whl/cu124
   .venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-gpu.txt "transformers>=4.51"
   ```
3. Nyalakan layanan:
   ```
   $env:TB_KUNCI = "<TB_KUNCI>"
   powershell -ExecutionPolicy Bypass -File deploy\server\mulai_gpu.ps1 -FolderAdapter C:\learningbuddy\adapters -FolderHasil C:\learningbuddy\hasil
   ```
4. Buka port 8000 HANYA untuk IP server web:
   ```
   New-NetFirewallRule -DisplayName "Learning Buddy model" -Direction Inbound -Protocol TCP -LocalPort 8000 -RemoteAddress <IP-SERVER-WEB> -Action Allow
   ```
5. Agar menyala otomatis setelah restart: Task Scheduler > Create Task > *At startup*,
   jalankan perintah langkah 3 (dengan `TB_KUNCI` diisi sebagai variabel lingkungan sistem).

### B3. Cek layanan model
Dari server web: `curl http://<IP-SERVER-GPU>:8000/api/sehat`
Harus berisi `"mode": "penelitian"`, model `Qwen2.5-7B-Instruct`, dan 12 adapter.

## C. Server web (Linux + Docker)

1. Di folder `LearningBuddy`:
   ```
   cp deploy/server/.env.web.contoh deploy/server/.env.web
   nano deploy/server/.env.web     # DB_PASSWORD, TB_REMOTE=http://<IP-SERVER-GPU>:8000, TB_KUNCI (sama dengan server GPU)
   docker compose -f deploy/server/docker-compose.web.yml --env-file deploy/server/.env.web up -d --build
   docker compose -f deploy/server/docker-compose.web.yml logs -f web
   ```
2. Log harus menampilkan `login: AKTIF (database tersambung)` dan `Uvicorn running`.
   Tabel akun dan riwayat chat dibuat otomatis.
3. Buka `http://<IP-SERVER-WEB>:8000`, daftar akun Guru/Peneliti, lalu coba bertanya.
   Tulisan "Mode uji tampilan" TIDAK boleh muncul.

## D. Domain dan HTTPS (oleh TI kampus)

Contoh nginx di depan server web (jawaban dialirkan per agen, jadi buffering dimatikan):
```
server {
    listen 443 ssl;
    server_name learningbuddy.<domain-kampus>;
    # ssl_certificate ... ; ssl_certificate_key ... ;
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_buffering off;
        proxy_read_timeout 300s;
    }
}
```
Lewat HTTPS, cookie login otomatis bertanda *Secure*. Alamat akhirnya menggantikan tulisan
"server" di manual book.

## E. Perawatan

| Keperluan | Perintah (server web; untuk GPU ganti `web` -> `gpu` dan `.env.web` -> `.env.gpu`) |
|---|---|
| Lihat log | `docker compose -f deploy/server/docker-compose.web.yml logs -f` |
| Restart | `docker compose -f deploy/server/docker-compose.web.yml restart` |
| Perbarui kode | salin folder LearningBuddy baru, lalu `... up -d --build` |
| Cadangan database | `docker compose -f deploy/server/docker-compose.web.yml exec db pg_dump -U learningbuddy learningbuddy > cadangan.sql` |
| Matikan | `docker compose -f deploy/server/docker-compose.web.yml down` (data tetap tersimpan di volume) |

## F. Masalah umum

| Gejala | Penyebab dan solusi |
|---|---|
| Web: `Database akun tidak bisa dihubungi` | `DB_PASSWORD` berubah setelah database dibuat; samakan, atau hapus volume `pgdata` bila belum ada data penting |
| Jawaban: galat 401/403 | `TB_KUNCI` di `.env.web` dan server GPU berbeda |
| Jawaban: galat koneksi | `TB_REMOTE` salah, layanan model mati, atau port 8000 server GPU tertutup firewall |
| GPU: `CUDA out of memory` | VRAM kurang dari 16 GB atau dipakai proses lain (cek `nvidia-smi`) |
| GPU: `adapter PJOK: 0/6` | susunan folder adapter tidak seperti bagian A.2 |
| GPU: gagal unduh model | server tidak bisa mengakses huggingface.co; minta TI membuka akses atau salin cache model |
