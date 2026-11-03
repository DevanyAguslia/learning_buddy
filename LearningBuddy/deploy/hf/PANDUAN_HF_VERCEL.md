# Menayangkan Learning Buddy di Hugging Face Space (GPU L4)

Cara utama menayangkan Learning Buddy. Kerjakan setelah tes lolos (`py -m pytest -q tes`)
dan adapter PJOK/PKN serta `ambang_relevan.json` sudah tersedia (notebook Kaggle, lihat README).

```
siswa/guru -> https://devany-learning-buddy.hf.space (GPU L4)
              program + Qwen + penyandi + reranker + login
              -> database akun di Neon (gratis)
```

Yang dipakai hanya Space. Langkah Vercel (A3 dan Bagian D) adalah cadangan dan **boleh
dilewati**. Website tetap berjalan penuh tanpa Vercel.

Biaya: GPU L4 $0,80 per jam (±Rp 13 rb), dihitung per menit **selama Space menyala**.
Rencana pemakaian ±7 jam (uji coba 3 + UAT 2 + sidang 1 + memuat model) ≈ $5,60.
Isi saldo $10. Vercel, Neon, dan repo HF private: gratis.

Rahasia (token, alamat database, kode guru) hanya diketik di halaman web layanan masing-masing.
Jangan ditulis di chat, GitHub, atau dokumen skripsi.

---

## Bagian A — Akun dan saldo (sekali saja)

### A1. Hugging Face
1. Daftar/masuk di https://huggingface.co. Catat **username** Anda (contoh di panduan ini: `devany`).
2. Saldo: *Settings* -> *Billing*.
   - Tambahkan kartu (Visa/Mastercard yang bisa transaksi online luar negeri dengan OTP/3D Secure;
     misalnya kartu debit Jenius/Jago atau kartu virtual).
   - Isi **credits $10**.
   - **Matikan automatic recharge** (isi ulang otomatis).
3. Token untuk laptop: *Settings* -> *Access Tokens* -> *Create new token* -> jenis **Write**,
   nama `laptop-unggah`. Salin (dimulai `hf_...`).
4. Token untuk Space: buat token kedua jenis **Read**, nama `space-baca`. Salin dan simpan
   sementara di Notepad (dipakai di langkah C3, lalu hapus dari Notepad).

### A2. Database akun (Neon, gratis)
1. Daftar di https://neon.tech (bisa pakai akun Google/GitHub).
2. *Create project*: nama `learning-buddy`, Postgres versi terbaru, region **AWS Asia Pacific
   (Singapore)**.
3. Di *Connection Details* / *Connect*, salin **connection string** (bentuknya
   `postgresql://...neon.tech/neondb?sslmode=require`). Simpan sementara di Notepad.
   Program otomatis mengubah awalan `postgresql://` menjadi yang dibutuhkan.
4. Tabel akun dan riwayat chat dibuat otomatis saat Space pertama menyala.

### A3. Vercel (cadangan, boleh dilewati)
Daftar di https://vercel.com dengan akun **GitHub** (paket Hobby, gratis).

---

## Bagian B — Unggah ke Hugging Face (laptop)

PowerShell, folder program:
```
cd D:\Skripsi\uji_program\LearningBuddy
```

### B1. Login HF di laptop (sekali saja)
```
python -m huggingface_hub.cli.hf auth login
```
Tempel token **Write** (`laptop-unggah`) saat diminta (tidak tampil saat diketik, itu normal).
Jawab `n` bila ditanya *Add token as git credential?*.

### B2. Unggah semuanya
Ganti `devany` dengan username HF Anda:
```
python deploy\hf\unggah_hf.py --akun devany
```
Skrip ini:
1. mengemas kode terbaru lalu mengunggahnya ke `devany/learning-buddy-kode` (dataset **private**);
2. mengunggah adapter PJOK + PKN kelas 1-6 dan `ambang_relevan.json` dari
   `D:\Skripsi\Pegasus_kirim` ke `devany/learning-buddy-adapter` (model **private**, 1,9 GB,
   bisa 10-30 menit tergantung internet);
3. membuat Space `devany/learning-buddy` (publik, hanya berisi Dockerfile + skrip mulai, tanpa kode);
4. menulis alamat Space ke `deploy\vercel\vercel.json`.

Di akhir tercetak `alamat aplikasi: https://devany-learning-buddy.hf.space`. Catat.

Belum ada biaya sampai GPU dipilih di langkah C2.

---

## Bagian C — Menyalakan Space

Buka `https://huggingface.co/spaces/devany/learning-buddy` -> tab **Settings**.

### C1. Secrets (bagian *Variables and secrets* -> **New secret**)
| Name | Value |
|---|---|
| `HF_TOKEN` | token **Read** (`space-baca`) |
| `TB_DATABASE_URL` | connection string Neon |
| `TB_KODE_GURU` | kode acak untuk mendaftar sebagai guru (bebas, panjang) |
| `TB_KODE_PENELITI` | kode acak untuk peneliti |

Variabel `TB_REPO_KODE` dan `TB_REPO_ADAPTER` sudah diisi otomatis oleh skrip (jangan dihapus).
Sesudah itu hapus token dan connection string dari Notepad.

### C2. Hardware
1. *Space hardware* -> pilih **Nvidia 1xL4** ($0,80/jam) -> konfirmasi. **Mulai sini biaya berjalan.**
2. *Sleep time* -> **15 minutes** (Space tidur sendiri bila tidak ada pengunjung; tidur = tidak bayar).

### C3. Pantau nyala pertama
1. Tab **Logs**: pertama *Build* (memasang pustaka, ±10-15 menit, hanya sekali), lalu *Container*.
2. Urutan yang benar di log Container:
   ```
   == penyimpanan: /home/user/simpan
   == 1/5 GPU            -> NVIDIA L4, 23034 MiB
   == 2/5 unduh kode ... dan adapter ...
   == 3/5 indeks FAISS   -> membangun di GPU (beberapa menit)
   == 4/5 adapter        -> adapter PJOK: 6/6, adapter PKN: 6/6
   == 5/5 menyalakan ...
   saringan aksara: 52290 dari ... token dilarang
   login: AKTIF (database tersambung)
   Uvicorn running on http://0.0.0.0:7860
   ```
3. Status Space berubah **Running**. Buka `https://devany-learning-buddy.hf.space`.

### C4. Uji di Space
1. Daftar akun Guru (pakai `TB_KODE_GURU`), akun Siswa, dan akun Peneliti.
2. Tanya 3-5 pertanyaan PJOK dan Pancasila di keempat mode jawab.
3. Lab: Ukur teks; unggah satu PDF buku sekolah (opsional).
4. Pastikan tidak ada huruf Mandarin/Arab dan tulisan "Mode uji tampilan" tidak muncul.

### C5. Selesai pakai -> **Pause**
*Settings* -> **Pause Space**. Saat di-pause, biaya berhenti. Menyalakan lagi: **Restart Space**
(menunggu ±5-10 menit sampai model siap; build tidak diulang).

---

## Bagian D — Alamat Vercel (cadangan, tidak dipakai)

1. Pastikan `deploy\vercel\vercel.json` sudah berisi alamat Space Anda (ditulis langkah B2).
2. Push ke GitHub.
3. vercel.com -> **Add New...** -> **Project** -> *Import* repo `learning_buddy`.
4. Di layar konfigurasi:
   - *Project Name*: `learningbuddy` (menjadi `learningbuddy.vercel.app`; bila sudah dipakai orang,
     pilih nama lain);
   - *Framework Preset*: **Other**;
   - *Root Directory*: **Edit** -> pilih `LearningBuddy/deploy/vercel`;
   - tidak perlu Environment Variables.
5. **Deploy**. Buka `https://learningbuddy.vercel.app`: harus tampil halaman masuk Learning Buddy
   (Space harus sedang Running).
6. Uji sekali lagi: masuk, bertanya, pastikan jawaban muncul bertahap per agen.
   Bila jawaban macet lewat Vercel tetapi lancar di alamat `hf.space`, pakai alamat `hf.space`
   untuk UAT.

Setiap push ke GitHub, Vercel memperbarui sendiri. Vercel tidak perlu dimatikan (gratis).

---

## Bagian E — Hari H (UAT / sidang)

| Kapan | Langkah |
|---|---|
| H-1 | cek saldo di *Settings -> Billing* (sisa minimal $3) |
| 30 menit sebelum | Space -> *Restart*; tunggu **Running**; tanya 1 pertanyaan uji |
| Selama sesi | biarkan menyala |
| Sesudah sesi | **Pause Space**; cek pemakaian di *Billing* |

## Bagian F — Memperbarui kode di Space

Setelah kode di laptop berubah (dan tes lolos):
```
python deploy\hf\unggah_hf.py --akun devany --bagian kode --mulai-ulang
```
Indeks FAISS dibangun ulang otomatis hanya bila `data/potongan.jsonl` berubah.

## Bagian G — Masalah umum

| Gejala di Logs | Solusi |
|---|---|
| `isi secret HF_TOKEN` / `TB_REPO_KODE` | secret/variable belum diisi (C1) |
| `401` / `Repository Not Found` saat unduh | token `HF_TOKEN` bukan milik akun pemilik repo, atau jenisnya salah |
| `adapter PJOK: 0/6` | ulangi `unggah_hf.py --bagian adapter` |
| `Database akun tidak bisa dihubungi` | connection string Neon salah/terpotong; salin ulang |
| `CUDA out of memory` | hardware bukan L4 (cek C2) |
| Space terus *Starting* > 30 menit | buka Logs, periksa 30 baris terakhir untuk mencari galat |
| Saldo habis | Space berhenti; isi credits lalu *Restart* |
