# Learning Buddy — program

Implementasi rancangan Bab III skripsi *Arsitektur Multi-Agentic AI dengan Kontrol Keterbacaan Tingkat Kelas untuk Asisten Pembelajaran Sekolah Dasar Indonesia* (Devany Aguslia, 535230189).

Daftar isi
1. [Struktur folder](#1-struktur-folder)
2. [Cara menjalankan](#2-cara-menjalankan)
   - [A. Memakai website langsung (Hugging Face Space)](#a-memakai-website-langsung-hugging-face-space)
   - [B. Laptop tanpa GPU (model tiruan)](#b-menjalankan-di-laptop-tanpa-gpu-model-tiruan)
   - [C. Laptop tersambung ke GPU Kaggle](#c-laptop-tersambung-ke-gpu-kaggle)
   - [D. Menayangkan / memperbarui Space](#d-menayangkan-atau-memperbarui-hugging-face-space)
   - [E. Notebook Kaggle penelitian](#e-notebook-kaggle-penelitian-pelatihan-dan-pengujian)
3. [Tes otomatis](#3-tes-otomatis)
4. [Variabel lingkungan](#4-variabel-lingkungan)
5. [API server](#5-api-server)
6. [Pemetaan ke skripsi](#6-pemetaan-ke-skripsi)
7. [Membuat ulang data](#7-membuat-ulang-data)
8. [Hasil utama](#8-hasil-utama)
9. [Keterbatasan](#9-keterbatasan)
10. [Masalah umum](#10-masalah-umum)

---

## 1. Struktur folder

```
LearningBuddy/
├── tb/                    paket Python (logika)
│   ├── agen.py            4 agen Perceive-Plan-Act-Reflect + graph LangGraph
│   ├── model.py           Qwen2.5-7B 4-bit + 12 adapter LoRA; ModelTiruan untuk laptop
│   ├── pencarian.py       retrieval: Qwen3-Embedding-4B + FAISS + reranker; PencariBM25 untuk laptop
│   ├── keterbacaan.py     PKR, KLD, pemeriksaan & arahan Reflect Agent
│   ├── server.py          server FastAPI (chat, Lab, akun, uji)
│   ├── akun.py            akun, sesi, sekolah, riwayat chat (PostgreSQL)
│   ├── buku_sekolah.py    unggah PDF buku oleh guru
│   ├── korpus.py, impor_potongan.py, basis.py, potong.py, data_qa.py   data buku & soal
│   ├── rumus.py           12 rumus keterbacaan pembanding (Lab)
│   └── kalibrasi.py, evaluasi_rumus.py, evaluasi_pencarian.py, validasi_recursive.py,
│       latih.py, uji.py, kuesioner_guru.py, kuesioner_usability.py, cek_jawaban.py   penelitian
├── web/                   masuk.html/js, index.html + app.js (chat), lab.html/js/css (Lab), gaya.css
├── data/                  potongan.jsonl, kontrol_keterbacaan*.json, acuan_rumus.json, halaman_*.jsonl, qa/
├── hasil/evaluasi_rumus.json   dibaca tab Lab › Evaluasi rumus
├── tes/                   40 tes pytest
├── deploy/
│   ├── hf/                Dockerfile, mulai.sh, unggah_hf.py, panduan Space  ← yang dipakai
│   ├── server/            Docker untuk server kampus (web + GPU terpisah)
│   ├── kemas.py           mengemas kode + data untuk Kaggle / HF
│   ├── buat_notebook.py   pembuat keempat notebook Kaggle
│   └── kaggle_latih / kaggle_uji_pencarian / kaggle_server / kaggle_uji_sistem .ipynb
├── .vscode/launch.json    tombol Run/Debug VS Code
└── requirements.txt (laptop), requirements-gpu.txt (GPU)
```

Peran pengguna:

| Peran | Bisa apa | Daftar |
|---|---|---|
| Siswa | chat, riwayat, gabung sekolah | bebas, boleh isi kode sekolah |
| Guru | chat + Lab › Ukur teks, Buku sekolah | wajib **kode pendaftaran guru** |
| Peneliti | chat + seluruh Lab (Evaluasi rumus, Uji sistem) | wajib **kode pendaftaran peneliti** |

Empat cara menjawab di chat sama dengan skenario penelitian: **Jawab Cepat = S1** (model dasar), **Sesuai Kelasku = S2** (adapter), **Lihat Buku = S3** (retrieval), **Paling Lengkap = S4** (adapter + retrieval, bawaan).

---

## 2. Cara menjalankan

| | A. Space | B. Laptop tiruan | C. Laptop + Kaggle |
|---|---|---|---|
| Model | Qwen 7B + 12 adapter | tiruan (tanpa model) | Qwen 7B di Kaggle |
| GPU | L4 24 GB (berbayar) | tidak perlu | T4 ×2 Kaggle (gratis, 30 jam/minggu) |
| Jawaban bermakna | ya | **tidak** | ya |
| Dipakai untuk | UAT, sidang, pengguna | mencoba alur/UI, tes | pengembangan, ambil jawaban kuesioner |

### A. Memakai website langsung (Hugging Face Space)

Website ditayangkan **hanya di Hugging Face Space**.

Alamat aplikasi: **https://devany-learning-buddy.hf.space**
Halaman pengelola Space: **https://huggingface.co/spaces/Devany/learning-buddy** (login sebagai pemilik).

**Menyalakan (pemilik Space)**
1. Buka halaman Space. Bila statusnya *Paused* atau *Sleeping*, buka **Settings → Restart this Space**.
   Space juga tidur sendiri setelah 15 menit tanpa pengunjung.
2. Tunggu status **Running**. Pertama kali menyala butuh beberapa menit: mengunduh kode dan adapter, membangun indeks FAISS bila potongan berubah, lalu memuat model selama 2–5 menit. Pantau di tab **Logs**. Urutan yang benar:
   ```
   == 1/5 GPU            NVIDIA L4 ...
   == 2/5 unduh kode ... dan adapter ...
   == 3/5 indeks FAISS
   == 4/5 adapter        adapter PJOK: 6/6, adapter PKN: 6/6
   == 5/5 menyalakan Learning Buddy di port 7860
   ```
3. Kirim satu pertanyaan uji. Pertanyaan pertama paling lambat.
4. **Selesai dipakai: Settings → Pause this Space.** Biaya GPU L4 (±$0,80/jam) dihitung selama Space menyala. Cek pemakaian di *Settings → Billing*.

**Memakai (siswa / guru / peneliti)**
1. Buka alamat di atas → **Daftar**: isi username, email, password, dan peran. Guru/peneliti mengisi kode pendaftaran dari pemilik.
2. Di halaman chat pilih **mata pelajaran**, **kelas** (atau *Otomatis*), dan **cara menjawab**, lalu kirim pertanyaan.
3. Setiap jawaban menampilkan penanda kelas, PKR, KLD, label sesuai kelas, jumlah putaran, panel **Sumber** (buku, halaman, 3 kutipan), dan **Jejak pemeriksaan** per putaran.
4. **Riwayat chat** menampilkan percakapan lama. **Kode sekolah** dipakai untuk bergabung ke sekolah guru, sehingga buku unggahan guru ikut dicari.
5. **Lab** (guru/peneliti): *Ukur teks*, *Evaluasi rumus*, *Uji sistem*, *Buku sekolah*.

**Tentang Vercel:** Vercel **tidak dipakai** dan foldernya tidak ada di repo. `unggah_hf.py --bagian space` masih menulis `deploy/vercel/vercel.json` secara otomatis (isinya hanya penerusan ke alamat Space). Berkas itu boleh dihapus atau diabaikan, karena tanpa proyek di vercel.com berkas ini tidak berpengaruh apa pun.

### B. Menjalankan di laptop tanpa GPU (model tiruan)

Butuh Python 3.10 atau 3.11.

```powershell
cd LearningBuddy
py -m pip install -r requirements.txt
py -m tb.server --tiruan --tanpa-login
```

- Chat: http://127.0.0.1:8000 · Lab: http://127.0.0.1:8000/lab.html
- `--tiruan` memakai `ModelTiruan` dan `PencariBM25`. Alur keempat agen, tampilan, Lab › Ukur teks, dan Evaluasi rumus berjalan normal, tetapi **jawabannya bukan hasil model** (hanya kutipan kalimat buku).
- Di VS Code: *Run and Debug* → **"1. Server tiruan"**. Konfigurasi itu memakai `D:/tbenv/Scripts/python.exe`; ganti ke Python milikmu bila berbeda.

**Dengan login (opsional).** Tanpa database, server berjalan tanpa login. Untuk mencoba akun:
1. Buat database PostgreSQL (lokal atau Neon gratis).
2. Buat berkas `LearningBuddy/.env` (tidak ikut git):
   ```
   TB_DATABASE_URL=postgresql+psycopg://USER:SANDI@HOST:PORT/NAMA_DB
   TB_KODE_GURU=kode-guru-buatanmu
   TB_KODE_PENELITI=kode-peneliti-buatanmu
   ```
3. Jalankan `py -m tb.server --tiruan` (tanpa `--tanpa-login`). Tabel dibuat otomatis.

### C. Laptop tersambung ke GPU Kaggle

UI dan Lab berjalan di laptop; pertanyaan diteruskan ke model sungguhan di Kaggle.

```
Laptop (VS Code)                              Kaggle (GPU T4 ×2)
py -m tb.server --remote URL     HTTPS        python -m tb.server --qwen --cari semantik
  UI chat, Lab, penguji  ───────────────────► Qwen 7B + adapter, FAISS, reranker, 4 agen
  127.0.0.1:8000          header X-Kunci      Cloudflare Quick Tunnel (*.trycloudflare.com)
```

1. Kemas kode: `py deploy/kemas.py` → `dist/unggah_kaggle/LearningBuddy/`. Unggah folder itu sebagai Kaggle Dataset **`learning-buddy-kode`** (Private). Setiap kali `tb/` berubah, buat *New Version*.
2. Pastikan Dataset **`adapter-pjok`** (adapter PJOK `grade_1..6`) dan output notebook **`kaggle_latih`** (adapter PKN + `hasil/ambang_relevan.json`) tersedia di akun Kaggle.
3. Buat notebook dari `deploy/kaggle_server.ipynb` (*File → Import Notebook*). Tambahkan ketiga input di atas, lalu atur *Settings*: **GPU T4 x2**, **Internet On**. Di *Add-ons → Secrets* buat **`TB_KUNCI`** berisi kata sandi bebas.
4. **Run All** (sesi interaktif). Sel tunnel mencetak `Server GPU aktif di : https://….trycloudflare.com`.
5. Di laptop:
   ```powershell
   py -m tb.server --remote https://xxxx.trycloudflare.com --remote-kunci <isi TB_KUNCI>
   ```
   Atau di VS Code: *Run and Debug* → **"3. Gerbang ke GPU Kaggle"**, lalu tempel URL dan kuncinya.
6. Buka http://127.0.0.1:8000. Status penjawab di Lab › Uji sistem harus berbunyi *jarak jauh (penelitian)*.

Alamat tunnel berganti setiap sesi. Sesi Kaggle maksimal 12 jam. Biarkan sel "penjaga sesi" berjalan, dan tekan *Stop Session* bila selesai.

### D. Menayangkan atau memperbarui Hugging Face Space

Panduan langkah demi langkah (akun, saldo, Neon, secret): **[`deploy/hf/PANDUAN_HF_VERCEL.md`](deploy/hf/PANDUAN_HF_VERCEL.md)** Bagian A–C dan E–G. Bagian D (Vercel) boleh dilewati.

Ringkasnya, ada tiga repo Hugging Face:

| Repo | Jenis | Isi |
|---|---|---|
| `Devany/learning-buddy-kode` | dataset, **private** | hasil `deploy/kemas.py` (tb, web, deploy, data) |
| `Devany/learning-buddy-adapter` | model, **private** | adapter `PJOK/grade_1..6`, `PKN/grade_1..6`, `ambang_relevan.json` |
| `Devany/learning-buddy` | Space Docker, publik | `Dockerfile`, `mulai.sh`, requirements (tanpa kode) |

```powershell
py -m pip install "huggingface_hub>=0.34"
hf auth login                                        # token HF jenis Write
py deploy/hf/unggah_hf.py --akun Devany              # pertama kali: kode + adapter + Space
py deploy/hf/unggah_hf.py --akun Devany --bagian kode --mulai-ulang   # setelah kode berubah
```

Hasil yang benar di akhir perintah:
```
== Space: https://huggingface.co/spaces/Devany/learning-buddy
   alamat aplikasi: https://devany-learning-buddy.hf.space
   vercel.json ditulis: ...\deploy\vercel\vercel.json      ← abaikan / hapus, Vercel tidak dipakai
```

Isi di *Space → Settings → Variables and secrets*:
- **Secret**: `HF_TOKEN` (token Read), `TB_DATABASE_URL` (Neon), `TB_KODE_GURU`, `TB_KODE_PENELITI`;
- **Variable**: `TB_REPO_KODE`, `TB_REPO_ADAPTER` (diisi otomatis oleh `unggah_hf.py`).

Hardware Space: **Nvidia L4 1x (24 GB)**.

Folder adapter bawaan `unggah_hf.py` adalah `D:\Skripsi\Pegasus_kirim\adapters` dan ambangnya `D:\Skripsi\Pegasus_kirim\hasil\ambang_relevan.json`. Ganti dengan `--adapter` dan `--ambang` bila lokasinya lain.

### E. Notebook Kaggle penelitian (pelatihan dan pengujian)

Semua notebook dibuat oleh `deploy/buat_notebook.py`, jadi jangan mengedit `.ipynb` langsung. Notebook menyalin Dataset `learning-buddy-kode` lalu memanggil fungsi di `tb/`, sehingga **kodenya sama dengan repo ini**. Jalankan dengan *Save Version → Save & Run All (Commit)* agar tetap berjalan walau browser ditutup.

| Notebook | Input | Menjalankan | Output | Dipakai untuk |
|---|---|---|---|---|
| `kaggle_latih.ipynb` | learning-buddy-kode | FAISS → `tb.evaluasi_pencarian` → `tb.latih` (PKN) | `adapters/PKN/grade_1..6/`, `hasil/ambang_relevan.json`, `Evaluasi_Pencarian.xlsx` | adapter Pancasila & ambang 0,278 di Space; Tabel 4.8–4.10 |
| `kaggle_uji_pencarian.ipynb` | learning-buddy-kode | `tb.evaluasi_pencarian` saja | `hasil/` yang sama | Tabel 4.8–4.10 |
| `kaggle_server.ipynb` | kode + adapter-pjok + output latih | `tb.server --qwen` + tunnel | alamat trycloudflare | cara C; jawaban kuesioner A/B (`tb.kuesioner_guru ambil`) |
| `kaggle_uji_sistem.ipynb` | kode + adapter-pjok + output latih | server + `/api/uji/mulai` S1–S4 | `hasil/uji/uji_*_PJOK.json`, `uji_*_PKN.json`, `server_uji.log` | Tabel 4.20–4.23 |

Adapter **PJOK** dilatih lebih dahulu di notebook fine-tuning G1 (di luar repo ini). Hasilnya diunggah sebagai Dataset **`adapter-pjok`**. `tb/latih.py` memakai pembagian data dan prompt yang sama; tes `test_konteks_mendukung_sama_dengan_g1` memastikannya.

---

## 3. Tes otomatis

```powershell
cd LearningBuddy
py -m pip install -r requirements.txt faiss-cpu
py -m pytest -q tes
```

Hasil: **40 tes lolos**, ±20 detik setelah cache kata dasar terbentuk (pertama kali ±5 menit).

| Berkas | Jumlah | Yang diuji |
|---|---|---|
| `tes/test_sistem.py` | 34 | ukuran keterbacaan, pemecah kalimat, cabang graph, pemilihan jawaban, perapian ejaan, bertanya balik, konfirmasi kelas, pengecekan 1–2, saringan aksara, akun & riwayat, API |
| `tes/test_buku_sekolah.py` | 6 | chunking buku sekolah, penolakan PDF scan, akses buku per sekolah, unggah lewat API |

Tes memakai model dan pencari tiruan. Yang dibuktikan adalah **alur dan perhitungan**, bukan mutu jawaban model.

---

## 4. Variabel lingkungan

| Variabel | Bawaan | Gunanya |
|---|---|---|
| `TB_DATABASE_URL` | – | alamat PostgreSQL; tanpa ini server berjalan tanpa login |
| `TB_KODE_GURU`, `TB_KODE_PENELITI` | – | kode wajib saat mendaftar sebagai guru / peneliti |
| `TB_MODEL_DASAR` | Qwen/Qwen2.5-7B-Instruct | model dasar |
| `TB_ADAPTER_PJOK`, `TB_ADAPTER_PKN` | – | pola folder adapter, mis. `.../PJOK/grade_{k}` |
| `TB_MODEL_EMBEDDING` | Qwen/Qwen3-Embedding-4B | penyandi retrieval |
| `TB_MODEL_RERANKER` | BAAI/bge-reranker-v2-m3 | reranker |
| `TB_STRATEGI` | Recursive | strategi potongan yang dicari |
| `TB_KIRIM` | 3 | jumlah potongan yang dikirim ke Act Agent |
| `TB_AMBANG_RELEVAN` | dari `ambang_relevan.json` | ambang pengecekan 1 (hasil kalibrasi 0,278) |
| `TB_FAISS` | `data/faiss/<model>` | folder indeks FAISS |
| `TB_BUKU_SEKOLAH` | `data/buku_sekolah` | folder buku unggahan guru |
| `TB_KETERBACAAN` | `data/kontrol_keterbacaan.json` | daftar kata dasar + batas kelas |
| `TB_DEVICE_CARI`, `TB_DEVICE_RERANK` | otomatis | GPU untuk penyandi / reranker |
| `TB_REMOTE`, `TB_REMOTE_KUNCI` | – | sama dengan `--remote`, `--remote-kunci` |
| `TB_KUNCI` | – | kunci server GPU (header `X-Kunci`) |
| `TB_FORWARDED_IPS` | – | di balik proxy Hugging Face agar cookie login aman (`mulai.sh` mengisinya `*`) |
| `HF_TOKEN` | – | token Hugging Face untuk repo private |

Opsi `tb.server`: `--tiruan`, `--qwen`, `--remote URL`, `--remote-kunci`, `--adapter-pjok`, `--adapter-pkn`, `--cari {bm25,semantik}`, `--model-dasar`, `--dtype`, `--tanpa-kuantisasi`, `--tanpa-login`, `--host`, `--port`.

---

## 5. API server

| Metode | Endpoint | Isi |
|---|---|---|
| GET | `/api/sehat` | status, mode, adapter |
| GET | `/api/info` | mapel, skenario, batas per kelas |
| POST | `/api/tanya` | satu pertanyaan → jawaban lengkap + jejak |
| POST | `/api/tanya/alir` | sama, dialirkan per agen (`text/event-stream`) |
| POST | `/api/ukur` | semua rumus keterbacaan untuk sebuah teks |
| GET | `/api/evaluasi` | `hasil/evaluasi_rumus.json` |
| POST/GET | `/api/uji/mulai`, `/api/uji/status`, `/api/uji/hentikan`, `/api/uji/riwayat` | pengujian S1–S4 |
| POST | `/api/daftar`, `/api/masuk`, `/api/keluar`; GET `/api/saya` | akun |
| GET | `/api/percakapan`, `/api/percakapan/{id}` | riwayat chat |
| GET/POST | `/api/sekolah`, `/api/sekolah/gabung`, `/api/buku` | sekolah dan buku sekolah |

---

## 6. Pemetaan ke skripsi

| Bagian skripsi | Berkas | Fungsi utama |
|---|---|---|
| 3.2.1 Pembacaan & prapemrosesan korpus | `tb/korpus.py`, `tb/impor_potongan.py` | `baca_buku`, `rapikan_karakter`, `rapikan` |
| 3.2.2 Knowledge base | `tb/basis.py`, `tb/pencarian.py` | `bangun_indeks_faiss` |
| 3.2.3 Retrieval | `tb/pencarian.py` | `PencariSemantik.cari`, `pilih_beragam`, `cari_lintas_kelas` |
| 3.2.4 Model bahasa & adapter | `tb/model.py` | `muat_model_dasar`, `ModelQwen`, `pasang_adapter`, `probe`, `_saringan_aksara` |
| 3.2.5 Kontrol keterbacaan | `tb/keterbacaan.py`, `tb/kalibrasi.py`, `tb/rumus.py` | `ukur`, `KontrolKeterbacaan.periksa`, `jarak_ke_sasaran`, `hitung_semua` |
| 3.2.6 Empat agen | `tb/agen.py` | `perceive`, `plan`, `act`, `reflect`, `pilih`, `_bangun_graf` |
| 3.2.7 Server, akun, buku sekolah | `tb/server.py`, `tb/akun.py`, `tb/buku_sekolah.py` | `tanya_alir`, `Akun`, `proses_pdf` |
| 3.2.8 Antarmuka | `web/` | – |
| 3.2.9 Penayangan | `deploy/hf/` | – |
| 3.2.10 Evaluasi | `tb/evaluasi_pencarian.py`, `tb/uji.py`, `tb/kuesioner_guru.py`, `tb/kuesioner_usability.py`, `tb/cek_jawaban.py`, `tes/` | `evaluasi`, `Penguji`, `periksa` |
| 3.1.3.3 Fine-tuning | `tb/latih.py` | `latih` |

---

## 7. Membuat ulang data

Data di `data/` sudah final. Perintah di bawah hanya perlu dijalankan bila buku atau aturan berubah.

| Data | Perintah | Butuh |
|---|---|---|
| `kontrol_keterbacaan.json`, `halaman_*.jsonl` | `py -m tb.kalibrasi` | PDF 12 Buku Siswa (`tb/korpus.py`, `path_buku`) |
| `potongan.jsonl` | `py -m tb.impor_potongan` | folder proyek eksperimen chunking di `../Eksperimen_Chunking` (tidak ada di repo ini) |
| indeks FAISS | `py -m tb.basis --vektor --device cuda` | GPU (otomatis di Space dan Kaggle) |
| `acuan_rumus.json`, `hasil/evaluasi_rumus.json` | `py -m tb.evaluasi_rumus` | `halaman_*.jsonl` |
| adapter LoRA | notebook `kaggle_latih` | GPU Kaggle |
| ambang pengecekan 1 | notebook `kaggle_uji_pencarian` | GPU Kaggle |

---

## 8. Hasil utama

Batas keterbacaan (Buku Siswa × 1,15 untuk PKR, × 1,10 untuk KLD). Daftar kata dasar: PJOK 934 kata, Pancasila 783 kata.

| Kelas | PJOK PKR maks | PJOK KLD maks | Pancasila PKR maks | Pancasila KLD maks |
|---|---|---|---|---|
| 1 | 10,7 | 4,4% | 7,8 | 7,8% |
| 2 | 6,9 | 3,5% | 9,4 | 8,5% |
| 3 | 8,8 | 17,2% | 12,3 | 27,9% |
| 4 | 10,9 | 19,6% | 13,4 | 33,7% |
| 5 | 10,7 | 27,6% | 15,6 | 30,7% |
| 6 | 11,6 | 27,5% | 14,5 | 35,6% |

Ringkasan Bab IV:
- Fungsi: 15/15 skenario black box dan 40/40 tes unit lolos.
- Retrieval website (1.014 soal PJOK): konteks acuan termuat pada **96,5%** soal; pengecekan 1 ambang 0,278 (TPR 0,9747, FPR 0,0265).
- Fine-tuning PJOK: Token F1 0,122 → 0,648. Pada 20 soal bersih parafrasa, adapter tidak lebih baik.
- S1–S4 chrF++: PJOK 14,77 / **29,15** / 14,57 / 19,53; Pancasila 16,44 / 23,73 / 18,96 / **29,38**.
- Kontrol keterbacaan (60 soal, S4): KLD 27,96% → 20,70% (p = 0,007); BERTScore ke buku 0,739 → 0,785.

---

## 9. Keterbatasan

- Kenaikan adapter sebagian besar dibantu kemiripan data latih dan uji (51,5% soal uji mirip soal latih).
- 43,7% soal PJOK berupa kalimat rumpang dan ditolak Perceive sebagai tidak jelas.
- Kepatuhan keterbacaan masih rendah (PJOK 11,7–16,2%, Pancasila 21,5–25,3%).
- Ambang pengecekan 2 (0,5) belum dikalibrasi.
- Batas keterbacaan adalah parameter rancangan sampai divalidasi guru dan siswa.

---

## 10. Masalah umum

| Gejala | Penyebab / solusi |
|---|---|
| `ModuleNotFoundError` saat tes | `py -m pip install -r requirements.txt faiss-cpu` |
| `FileNotFoundError ... halaman_PJOK.jsonl` | file `data/halaman_*.jsonl` hilang; dibutuhkan tes |
| Login tidak muncul di laptop | `.env` tanpa `TB_DATABASE_URL`, atau server dijalankan dengan `--tanpa-login` |
| Space terus *Starting* | buka Logs. `adapter PJOK: 0/6` → unggah ulang adapter; `isi secret HF_TOKEN` → secret belum diisi |
| `CUDA out of memory` di Space | hardware bukan L4 |
| `CUDA out of memory` di Kaggle | sisa server/tunnel dari sesi sebelumnya; jalankan ulang sel pertama (mematikan proses lama) atau restart sesi |
| Jawaban "materi ini belum ada di buku pelajaranmu" | pengecekan 1 gagal di semua buku kelas mapel itu; materi memang di luar buku |
| Laptop tidak bisa memakai `--cari semantik` | butuh `requirements-gpu.txt` dan GPU; di laptop pakai `--tiruan` (BM25) |
