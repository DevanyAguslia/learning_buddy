#!/usr/bin/env bash
# Menyalakan layanan MODEL Learning Buddy di server GPU (dipanggil oleh Dockerfile.gpu).
# Folder yang dipasang dari luar container:
#   /adapters/PJOK/grade_1..6   adapter G1 Recursive (D:\Skripsi\recursive\adapters_recursive)
#   /adapters/PKN/grade_1..6    adapter Pancasila (hasil_adapter/adapters/PKN)
#   /app/data/faiss             indeks FAISS (dibangun sekali saat pertama jalan)
#   /hasil/ambang_relevan.json  ambang pengecekan 1 hasil kaggle_latih (hasil_adapter/hasil)
set -euo pipefail
cd /app
: "${TB_KUNCI:?TB_KUNCI wajib diisi agar hanya server web yang bisa memakai GPU ini}"
MODEL="${TB_MODEL_EMBEDDING:-Qwen/Qwen3-Embedding-4B}"
FOLDER=$(python -c "from tb.pencarian import folder_indeks; print(folder_indeks('$MODEL'))")

if [ ! -f "$FOLDER/meta.json" ]; then
  echo "== indeks FAISS belum ada: membangun (sekali saja, beberapa menit)"
  python -m tb.basis --vektor --model "$MODEL"
fi
if [ -f /hasil/ambang_relevan.json ]; then
  cp /hasil/ambang_relevan.json "$FOLDER/ambang_relevan.json"
fi

for m in PJOK PKN; do
  n=$(ls -d /adapters/$m/grade_* 2>/dev/null | wc -l)
  echo "adapter $m: $n/6"
done

exec python -m tb.server --qwen --cari semantik --tanpa-login --host 0.0.0.0 --port 8000 \
  --adapter-pjok "/adapters/PJOK/grade_{k}" --adapter-pkn "/adapters/PKN/grade_{k}"
