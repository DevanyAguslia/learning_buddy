#!/usr/bin/env bash
# Menyalakan Learning Buddy di Hugging Face Space (dipanggil Dockerfile).
#
# Secret Space (Settings > Variables and secrets > New secret):
#   HF_TOKEN            token HF "Read" milik Devany (untuk repo kode + adapter yang private)
#   TB_DATABASE_URL     postgresql+psycopg://...  (Neon/Supabase; login + riwayat chat)
#   TB_KODE_GURU, TB_KODE_PENELITI   kode pendaftaran guru / peneliti
# Variable Space (diisi otomatis oleh unggah_hf.py):
#   TB_REPO_KODE        mis. akun/learning-buddy-kode      (dataset private)
#   TB_REPO_ADAPTER     mis. akun/learning-buddy-adapter   (model private)
#
# Penyimpanan: bila Storage Bucket dipasang di /data, cache model, indeks FAISS, buku sekolah,
# dan log tersimpan permanen. Tanpa /data semuanya dibuat ulang setiap Space menyala.
set -euo pipefail
: "${HF_TOKEN:?isi secret HF_TOKEN di Settings Space}"
: "${TB_REPO_KODE:?isi variable TB_REPO_KODE}"
: "${TB_REPO_ADAPTER:?isi variable TB_REPO_ADAPTER}"

APP=$HOME/app
if [ -d /data ] && [ -w /data ]; then SIMPAN=/data; else SIMPAN=$HOME/simpan; fi
echo "== penyimpanan: $SIMPAN"
mkdir -p "$SIMPAN"/{hf_cache,faiss,buku_sekolah,log}
export HF_HOME=$SIMPAN/hf_cache TB_FAISS=$SIMPAN/faiss TB_BUKU_SEKOLAH=$SIMPAN/buku_sekolah
export TB_MODEL_EMBEDDING=${TB_MODEL_EMBEDDING:-Qwen/Qwen3-Embedding-4B}
export TB_STRATEGI=${TB_STRATEGI:-Recursive} TB_KIRIM=${TB_KIRIM:-3}
# di balik proxy HF (dan Vercel): percayai X-Forwarded-Proto agar cookie login bertanda Secure
export TB_FORWARDED_IPS=${TB_FORWARDED_IPS:-*}
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

echo "== 1/5 GPU"
nvidia-smi --query-gpu=name,memory.total,memory.used --format=csv || true

echo "== 2/5 unduh kode ($TB_REPO_KODE) dan adapter ($TB_REPO_ADAPTER)"
python - <<EOF
from huggingface_hub import snapshot_download
snapshot_download("$TB_REPO_KODE", repo_type="dataset", local_dir="$APP/kode")
snapshot_download("$TB_REPO_ADAPTER", local_dir="$APP/adapters")
EOF
cd "$APP/kode/LearningBuddy"
rm -rf log && ln -s "$SIMPAN/log" log

echo "== 3/5 indeks FAISS"
FOLDER=$(python -c "from tb.pencarian import folder_indeks; print(folder_indeks())")
# indeks dibangun ulang bila belum ada atau potongan.jsonl berubah sejak indeks dibuat
SIDIK=$(sha1sum data/potongan.jsonl | cut -c1-40)
if [ ! -f "$FOLDER/meta.json" ] || [ "$(cat "$FOLDER/sidik_potongan" 2>/dev/null)" != "$SIDIK" ]; then
  echo "   membangun di GPU (beberapa menit)"
  rm -rf "$FOLDER"
  python -m tb.basis --vektor --device cuda
  echo "$SIDIK" > "$FOLDER/sidik_potongan"
fi
if [ -f "$APP/adapters/ambang_relevan.json" ]; then
  cp "$APP/adapters/ambang_relevan.json" "$FOLDER/ambang_relevan.json"
else
  echo "   PERINGATAN: ambang_relevan.json tidak ada; pengecekan 1 mati"
fi

echo "== 4/5 adapter"
for m in PJOK PKN; do
  n=$(ls -d "$APP/adapters/$m"/grade_* 2>/dev/null | wc -l)
  echo "   adapter $m: $n/6"
done

echo "== 5/5 menyalakan Learning Buddy di port 7860 (memuat model 2-5 menit)"
exec python -m tb.server --qwen --cari semantik --host 0.0.0.0 --port 7860 \
  --adapter-pjok "$APP/adapters/PJOK/grade_{k}" --adapter-pkn "$APP/adapters/PKN/grade_{k}"
