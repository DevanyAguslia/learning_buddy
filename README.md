# learning-buddy
Website Chatbot Learning Buddy (Skripsi)

Asisten belajar siswa SD (PJOK dan Pendidikan Pancasila, kelas 1-6) dengan kontrol
keterbacaan per tingkat kelas. Skripsi Devany Aguslia (535230189), Teknik Informatika,
Universitas Tarumanagara.

| Folder | Isi |
|---|---|
| [`LearningBuddy/`](LearningBuddy/README.md) | program website: server + 4 agen (Perceive, Plan, Act, Reflect), halaman chat, Lab keterbacaan, login dan riwayat chat (PostgreSQL), notebook Kaggle latih/server |
| [`Eksperimen_Chunking/`](Eksperimen_Chunking/README.md) | eksperimen pemotongan buku (Fixed, Sentence, Recursive, Semantic, SDCS, Structure, Manual), dataset soal Kurikulum Merdeka, hasil eksperimen |

## Menjalankan website (laptop)

```
cd LearningBuddy
D:\tbenv\Scripts\python.exe -m tb.server --tiruan
```

Buka http://127.0.0.1:8000. Login memerlukan database PostgreSQL; langkah pembuatannya ada
di [`LearningBuddy/README.md`](LearningBuddy/README.md#akun-dan-database-postgresql).

## Yang sengaja tidak ada di repo

- `.env` dan `*.local.sql`: sandi database (dibuat di masing-masing komputer).
- PDF buku pelajaran, paket unggahan Kaggle (`dist/`), vektor dan potongan hasil eksperimen
  (dapat dibuat ulang dengan kode di repo ini).
