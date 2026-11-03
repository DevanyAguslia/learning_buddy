# Learning Buddy

Website asisten belajar siswa SD untuk **PJOK** dan **Pendidikan Pancasila** kelas 1–6. Jawaban diambil dari buku resmi Kurikulum Merdeka, dan bahasanya dikendalikan supaya sesuai dengan kelas siswa yang bertanya.

Skripsi: *Arsitektur Multi-Agentic AI dengan Kontrol Keterbacaan Tingkat Kelas untuk Asisten Pembelajaran Sekolah Dasar Indonesia*. Devany Aguslia (535230189), Teknik Informatika, Universitas Tarumanagara.

**Website:** https://devany-learning-buddy.hf.space, ditayangkan hanya di Hugging Face Space ([Devany/learning-buddy](https://huggingface.co/spaces/Devany/learning-buddy), GPU L4). Space hanya menyala saat dipakai; lihat [cara menyalakan](LearningBuddy/README.md#a-memakai-website-langsung-hugging-face-space).

---

## Cara kerja singkat

```
pertanyaan siswa
   │
   ▼
Perceive ──► Plan ──► Act ──► Reflect ──► jawaban + sumber buku
merapikan    menentukan  3 potongan buku   PKR & KLD sesuai kelas?
ejaan,       kelas &     + adapter LoRA    belum → arahan ke Act (maks. 3 putaran)
cek jelas    topik       kelas itu
```

- Model: **Qwen2.5-7B-Instruct** 4-bit dengan **12 adapter LoRA** (6 kelas × 2 mapel).
- Retrieval: **Qwen3-Embedding-4B + FAISS**, lalu **bge-reranker-v2-m3**; 4.379 potongan dari 12 buku.
- Kontrol keterbacaan: **PKR** (panjang kalimat rata-rata) dan **KLD** (persen kata di luar daftar kata dasar), dengan batas per kelas dari Buku Siswa.
- Orkestrasi: **LangGraph**. Server: **FastAPI**. Akun dan riwayat: **PostgreSQL (Neon)**.

## Isi repo

| Path | Isi |
|---|---|
| [`LearningBuddy/`](LearningBuddy/README.md) | seluruh program: `tb/` (agen, model, retrieval, keterbacaan, server, akun, evaluasi), `web/` (tampilan), `data/`, `tes/`, `deploy/` (Hugging Face Space, notebook Kaggle, Docker cadangan) |

Panduan lengkap ada di **[`LearningBuddy/README.md`](LearningBuddy/README.md)**:
- [A. Memakai website langsung di Hugging Face Space](LearningBuddy/README.md#a-memakai-website-langsung-hugging-face-space)
- [B. Menjalankan di laptop tanpa GPU (model tiruan)](LearningBuddy/README.md#b-menjalankan-di-laptop-tanpa-gpu-model-tiruan)
- [C. Laptop tersambung ke GPU Kaggle](LearningBuddy/README.md#c-laptop-tersambung-ke-gpu-kaggle)
- [D. Menayangkan atau memperbarui Space](LearningBuddy/README.md#d-menayangkan-atau-memperbarui-hugging-face-space)
- [E. Notebook Kaggle penelitian](LearningBuddy/README.md#e-notebook-kaggle-penelitian-pelatihan-dan-pengujian)

Mulai cepat di laptop:

```powershell
cd LearningBuddy
py -m pip install -r requirements.txt
py -m tb.server --tiruan --tanpa-login
```

Lalu buka http://127.0.0.1:8000. Mode tiruan hanya untuk mencoba alur dan tampilan; jawabannya bukan hasil penelitian.

## Yang sengaja tidak ada di repo

| Tidak ada | Alasan / di mana |
|---|---|
| `.env`, `*.local.sql`, token, kode guru | rahasia; diisi di tiap komputer atau sebagai *secret* Space |
| PDF 12 buku Kurikulum Merdeka | berkas besar; hasil olahannya sudah ada di `LearningBuddy/data/potongan.jsonl` |
| Adapter LoRA (`*.safetensors`) | ±1,9 GB; disimpan di repo model Hugging Face private dan Kaggle Dataset |
| Indeks FAISS, `dist/`, `log/` | dibuat ulang otomatis |
| Eksperimen chunking | proyek terpisah. Pilihan akhirnya (Recursive 500 karakter, overlap 50) sudah dibekukan di `data/potongan.jsonl`, jadi website tidak membutuhkannya |
| Naskah skripsi, kuesioner, manual book | dokumen, bukan program |
