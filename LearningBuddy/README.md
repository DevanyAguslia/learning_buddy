# Learning Buddy

Asisten pembelajaran SD dengan kontrol keterbacaan tingkat kelas. Ini implementasi
rancangan Bab III proposal skripsi *Arsitektur Multi-Agentic AI dengan Kontrol
Keterbacaan Tingkat Kelas untuk Asisten Pembelajaran Sekolah Dasar Indonesia*
(Devany Aguslia, 535230189).

## Akun dan database (PostgreSQL)

Halaman `masuk.html`: daftar (username, email, password, peran Siswa/Siswi SD, Guru,
Peneliti) lalu langsung masuk; masuk dengan username ATAU email. Siswa hanya chat; guru dan
peneliti chat + Lab keterbacaan. Riwayat chat tersimpan per akun (`tb/akun.py`).

1. Sekali saja, buat database (perlu password superuser `postgres` milik Anda):

       "D:\PostgreSQL\bin\psql.exe" -U postgres -h 127.0.0.1 -p 5433 -f deploy\siapkan_database.local.sql

   Berkas `.local.sql` dan `.env` berisi sandi database aplikasi dan TIDAK ikut ke GitHub.
2. `.env` berisi `TB_DATABASE_URL=postgresql+psycopg://learningbuddy:...@127.0.0.1:5433/learningbuddy`.
   Di server kampus cukup ganti alamat ini. Tabel dibuat otomatis saat server menyala.
3. `python -m tb.server --tiruan` -> login aktif. `--tanpa-login` mematikannya (server GPU Kaggle
   tidak membaca `.env`, jadi tanpa login).

Empat cara menjawab di chat = skenario penelitian: Jawab Cepat (S1), Sesuai Kelasku (S2),
Lihat Buku (S3), Paling Lengkap (S4, bawaan).

## Pemetaan ke proposal

| Komponen proposal | Berkas |
|---|---|
| Keadaan bersama, orkestrator graf, Perceive/Plan/Act/Reflect (2.1, Gambar 3.4) | `tb/agen.py` |
| Kontrol keterbacaan, rumus (2.4), Gambar 3.5 | `tb/keterbacaan.py` |
| Pemilihan alat ukur dan sasaran per jenjang (3.1.3.4, Lampiran 4) | `tb/kalibrasi.py` |
| Rumus pembanding dan evaluasinya | `tb/rumus.py`, `tb/evaluasi_rumus.py` |
| Prapemrosesan korpus (3.1.3.1, Lampiran 1) | `tb/korpus.py`, `tb/potong.py` |
| Basis pengetahuan (Gambar 3.1) | `tb/basis.py` |
| Pencarian konteks dua tahap (3.1.3.2, Tabel 3.8) | `tb/pencarian.py` |
| Adapter per jenjang di atas satu model dasar (3.1.3.3) | `tb/model.py` |
| Empat skenario S1-S4 (Tabel 3.11), pembagian data kanonik (Tabel 1.1) | `tb/agen.py`, `tb/data_qa.py` |
| Pengujian atas data uji (3.1.3.5) | `tb/uji.py` |
| Antarmuka enam bagian (3.1.4, Gambar 3.7) dan Lab | `web/` |
| Jejak pemrosesan (kebutuhan fungsional 8) | `log/jejak_YYYYMMDD.jsonl` |

## Menjalankan di laptop (tanpa GPU)

```
pip install -r requirements.txt
python -m tb.kalibrasi          # daftar kata, Spearman, sasaran, garis dasar, lembar guru
python -m tb.basis              # data/potongan.jsonl
python -m tb.evaluasi_rumus     # evaluasi 12 alat ukur keterbacaan (~10 detik dengan cache)
python -m pytest -q tes         # 16 tes
python -m tb.server --tiruan    # chat: http://127.0.0.1:8000   lab: http://127.0.0.1:8000/lab.html
```

Mode tiruan memakai model pengganti dan BM25, jadi jawabannya tidak bermakna. Mode ini
hanya untuk mencoba alur agen dan antarmuka. Laptop tidak dapat menjalankan
sentence-transformers karena versi torch lokal terkunci di 2.4. Di VS Code, perintah
utama tersedia di panel *Run and Debug* (`.vscode/launch.json`).

## Lab keterbacaan (`/lab.html`)

| Tab | Isi | Butuh GPU? |
|---|---|---|
| Ukur teks | 12 alat ukur untuk teks apa pun, sorotan kata sulit dan panjang kalimat, keputusan Reflect Agent, integrasi Algoritma 1 Classroom AI | tidak |
| Evaluasi rumus | korelasi setiap rumus terhadap jenjang pada tingkat buku, halaman, dan kunci jawaban; sebaran per jenjang; matriks tebakan jenjang | tidak |
| Uji sistem | menjalankan data uji kanonik (PJOK 197, Pancasila 158) lewat siklus agen pada S1-S4; EM, Token F1, chrF++, kepatuhan keterbacaan, putaran, ketepatan Plan Agent | ya, untuk angka sungguhan |

Hasil uji tersimpan di `hasil/uji/`. BERTScore dan probe logit belum ada di Lab karena
memerlukan GPU.

## Menyambungkan laptop ke GPU Kaggle (disarankan selama pengembangan)

```
  Laptop (VS Code)                                     Kaggle (GPU T4)
  python -m tb.server --remote URL      HTTPS         python -m tb.server --qwen
  +- UI chat dan Lab         ------------------->     +- Qwen2.5-7B 4-bit + adapter
  +- ukur teks, evaluasi       /api/tanya             +- penyandi + FAISS + reranker 
  +- penguji data uji          /api/tanya/alir        +- empat agen
          127.0.0.1:8000       (header X-Kunci)       Cloudflare Quick Tunnel
```

1. Laptop: `python deploy/kemas.py`, lalu unggah `dist/learning-buddy-kode.zip` sebagai
   Kaggle Dataset **learning-buddy-kode**. Ulangi (*New Version*) setiap kali `tb/` berubah.
2. Unggah folder adapter PJOK (`grade_1` sampai `grade_6`) sebagai Dataset
   **adapter-pjok**. Adapter terbaru ada di `Downloads/results (2)/adapters_structure`.
3. Buat notebook dari `deploy/kaggle_server.ipynb`, tambahkan kedua Dataset, pilih GPU
   T4 x2, nyalakan Internet, isi Secret `TB_KUNCI` (kata sandi bebas).
4. Run All. Sel 6 mencetak alamat `https://....trycloudflare.com` beserta perintah laptop:
   `python -m tb.server --remote https://....trycloudflare.com --remote-kunci <TB_KUNCI>`.
   Di VS Code: *Run and Debug* > "gerbang ke GPU Kaggle", lalu tempel URL dan kuncinya.
5. Buka `http://127.0.0.1:8000` dan `http://127.0.0.1:8000/lab.html`. Status penjawab di
   tab Uji sistem harus berbunyi "jarak jauh (penelitian)".

Alamat tunnel berganti setiap sesi. Sesi GPU Kaggle paling lama 12 jam, kuotanya 30 jam
per minggu. Biarkan sel 8 berjalan selama dipakai.

## Hasil kalibrasi (korpus 12 Buku Siswa, mode pencocokan kata dasar)

Daftar kata dasar disusun dari Buku Siswa kelas 1-2, dengan syarat kata muncul minimal
3 kali: PJOK 976 kata, Pancasila 795 kata.

Korelasi Spearman terhadap jenjang (n = 6; uji buta hanya kelas 3-6, n = 4):

| Alat ukur | PJOK | PJOK uji buta | Pancasila | Pancasila uji buta |
|---|---|---|---|---|
| KLD (kata luar daftar) | +0,943 | +1,000 | +0,943 | +0,800 |
| PKR (panjang kalimat) | +0,543 | +0,800 | +0,943 | +0,800 |
| Fry, suku kata per 100 kata | +0,943 | +0,800 | +0,943 | +0,800 |

Sasaran per jenjang (nilai buku x 1,15 untuk PKR, x 1,10 untuk KLD):

| Kelas | PJOK PKR maks | PJOK KLD maks | Pancasila PKR maks | Pancasila KLD maks |
|---|---|---|---|---|
| 1 | 10,8 | 5,5% | 8,0 | 7,5% |
| 2 | 6,9 | 4,5% | 9,5 | 8,3% |
| 3 | 8,8 | 17,0% | 12,3 | 26,9% |
| 4 | 10,9 | 19,5% | 13,5 | 32,9% |
| 5 | 10,7 | 27,3% | 15,7 | 30,1% |
| 6 | 11,6 | 27,4% | 14,5 | 34,6% |

Garis dasar: 56,2% kunci jawaban PJOK (977) dan 44,6% kunci jawaban Pancasila (780)
lolos sasaran jenjangnya sendiri.

Tabel lengkap ada di `hasil/G4_Kontrol_Keterbacaan_v2_akar.xlsx`. Pembandingnya, versi
pencocokan bentuk kata persis sesuai bunyi rumus (2.4), ada di `..._bentuk.xlsx` dan
`data/kontrol_keterbacaan_bentuk.json`.

## Evaluasi dua belas alat ukur (`python -m tb.evaluasi_rumus`)

Sumber rumus: tujuh rumus dan ARI dari Classroom AI (Oh dkk., KAIST, Microsoft Research
Asia, dan William & Mary; arXiv 2601.06225), LIX sebagai rumus lintas bahasa, serta PKR
dan KLD dari proposal. EduAdapt tidak memakai rumus. Ia memakai LLM-as-a-judge dengan
enam kriteria bernilai 1-10: Vocabulary Alignment, Conceptual Alignment, Scientific
Language Alignment, Correctness, Clarity, dan Completeness.

Rho disearahkan sehingga positif berarti naik bersama jenjang (tanda FRES dibalik).
Halaman: 441 halaman uji PJOK dan 386 Pancasila, dengan acuan jenjang dari halaman
kalibrasi (halaman genap). Jawaban: 197 dan 157 kunci jawaban data uji.

| Alat ukur | PJOK buku | PJOK halaman | PJOK tepat +-1 | PJOK jawaban | Pancasila buku | Pancasila halaman | Pancasila tepat +-1 | Pancasila jawaban |
|---|---|---|---|---|---|---|---|---|
| CLI | +0,886 | +0,600 | 74,1% | +0,122 | +0,943 | +0,553 | 63,2% | +0,187 |
| ARI | +0,771 | +0,567 | 67,1% | +0,026 | +0,943 | +0,562 | 69,2% | +0,068 |
| Integrasi + PKR/KLD | - | +0,511 | 55,6% | +0,259 | - | +0,529 | 64,0% | +0,154 |
| Integrasi Classroom AI | - | +0,531 | 64,2% | +0,294 | - | +0,505 | 65,5% | +0,256 |
| FKGL | +0,886 | +0,541 | 68,7% | +0,054 | +0,943 | +0,482 | 64,5% | +0,006 |
| Dale-Chall | +0,886 | +0,522 | 71,4% | +0,291 | +0,886 | +0,476 | 65,5% | +0,072 |
| Spache | +0,086 | +0,449 | 62,4% | +0,301 | +0,886 | +0,530 | 72,8% | +0,087 |
| **KLD** | +0,886 | +0,470 | 68,9% | +0,277 | +0,886 | +0,502 | 58,8% | +0,005 |
| Linsear Write | +0,429 | +0,438 | 55,8% | +0,239 | +0,429 | +0,525 | 70,7% | +0,270 |
| FRES | +0,886 | +0,505 | 68,7% | +0,028 | +0,943 | +0,404 | 59,8% | -0,026 |
| **PKR** | +0,771 | +0,381 | 56,9% | +0,265 | +0,943 | +0,527 | 71,5% | +0,290 |
| LIX | +0,771 | +0,441 | 67,6% | -0,014 | +0,943 | +0,430 | 62,2% | +0,095 |
| Gunning Fog | +0,886 | +0,435 | 58,5% | +0,051 | +0,943 | +0,435 | 57,3% | +0,020 |
| Fry | +0,943 | +0,440 | 63,9% | +0,022 | +0,943 | +0,297 | 53,9% | -0,060 |

Tebakan acak menghasilkan ketepatan +-1 sebesar 44,4%. Nilai "buku" di tabel ini memakai
daftar kata dari halaman kalibrasi saja, jadi sedikit berbeda dari tabel kalibrasi.

## Keputusan yang perlu dibahas dengan pembimbing

1. **Grafik Fry tidak lagi berkorelasi negatif.** Angka lama -0,100 berasal dari korpus
   lama yang memuat Buku Guru. Pada 12 Buku Siswa yang benar, suku kata per 100 kata
   berkorelasi +0,943 di tingkat buku. Argumen di 2.2.6 dan Tabel L4.3 ("imbuhan membuat
   Fry gagal") tidak didukung data baru. Di tingkat halaman Fry memang paling lemah
   (0,30-0,44), jadi argumen yang lebih jujur adalah "Fry lemah pada teks pendek".
2. **Pencocokan kata dasar.** Dengan bentuk persis, "mengubah" dianggap sulit walau
   "ubah" ada di daftar. Hal ini bertentangan dengan argumen skripsi sendiri. Mode kata
   dasar (stemmer Sastrawi) menaikkan korelasi KLD PJOK dari +0,886 ke +0,943 dan garis
   dasar dari 51,3% ke 56,2%. Bila dipakai, rumus (2.4) perlu tambahan: kata dikenal
   bila bentuknya atau kata dasarnya ada di daftar.
3. **Kata isi.** Kata tugas (untuk, dan, yang, ...) tidak dihitung, sesuai contoh
   Lampiran 4. Keterangan rumus (2.4) yang hanya menyebut "minimal tiga huruf" perlu
   disesuaikan.
4. **Pemecahan kalimat buku.** Butir pilihan ganda dan titik-titik isian dijadikan batas,
   dan penggalan di bawah tiga kata tidak dihitung sebagai kalimat. Tanpa aturan ini 22%
   "kalimat" di buku kelas 2 adalah pecahan soal.
5. **Sasaran PJOK tidak monoton.** PKR buku kelas 1 (9,4) lebih panjang dari kelas 2
   (6,0) karena edisinya berbeda (Merdeka lawan BSE 2010). Sasaran kelas 2 menjadi yang
   paling ketat.
6. **Angka Lampiran 4 lama** (10,4; 6,6; 1.324 kata) harus diganti angka di atas.
7. **Pada tingkat halaman, rumus berbasis jumlah huruf (CLI, ARI) sedikit lebih kuat**
   daripada PKR dan KLD, dan tidak membutuhkan penghitung suku kata maupun daftar kata.
   Selisihnya kecil (rho 0,55-0,60 lawan 0,38-0,53), jadi layak dibahas sebagai kendali
   pendamping, bukan pengganti. KLD tetap unggul karena bisa menunjuk kata yang harus
   diganti, dan itulah yang membuat arahan Reflect Agent terarah.
8. **Pada teks satu-dua kalimat, semua rumus lemah** (rho paling tinggi sekitar 0,30).
   Padahal itulah bentuk teks yang diperiksa Reflect Agent. Sebagian penyebabnya kunci
   jawaban memang tidak ditulis berjenjang (garis dasar kepatuhan hanya 44-56%). Ini perlu
   disebut sebagai batasan dan menjadi alasan kuat untuk validasi guru.
9. **Integrasi Algoritma 1 Classroom AI tidak lebih baik** daripada rumus tunggal terbaik
   pada tingkat halaman, tetapi paling stabil pada tingkat jawaban (0,26-0,29 di kedua
   mata pelajaran).
10. **Konstanta rumus Inggris tidak berlaku untuk bahasa Indonesia.** Kalimat "Ani berlari.
    Budi melompat tinggi sekali." dinilai FKGL 15 (setara mahasiswa) dan FRES negatif.
    Karena itu jenjang dari rumus asing hanya sah dibaca lewat pemetaan ke buku.

## Yang belum dikerjakan atau belum diverifikasi

- Jalur GPU (`ModelQwen`, `PencariSemantik`, notebook Kaggle) **belum pernah dijalankan**.
  Kodenya ditulis mengikuti notebook pelatihan yang berhasil, tetapi baru benar-benar
  teruji saat notebook Kaggle dijalankan pertama kali. Sel 5 dan sel 7 berisi pagar mutu.
  Mode gerbang (`--remote`) sudah diuji terhadap server tiruan berkunci di laptop.
- Adapter Pendidikan Pancasila belum dilatih. Tanpa adapter itu, S2/S4 Pancasila
  memakai model dasar dan antarmuka menampilkan keterangannya. Pelatihannya harus memakai
  prompt sistem "Kamu asisten pembelajaran Pendidikan Pancasila sekolah dasar. ..." agar
  cocok dengan `sys_prompt()` di `tb/agen.py`.
- Adapter PJOK yang tersedia adalah hasil eksperimen *structure* untuk makalah IEEE.
  Konteks latihnya berasal dari potongan Structure lama, bukan dari `tb/potong.py`.
- Rubrik LLM-as-a-judge EduAdapt belum diimplementasikan (butuh GPU).
- BERTScore, probe logit, dan uji Wilcoxon antarskenario belum masuk Lab.
