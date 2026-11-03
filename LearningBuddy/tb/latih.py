"""Pelatihan adapter LoRA per jenjang untuk PJOK dan Pendidikan Pancasila (Subbab 3.1.3.3).

Mengikuti Tabel 3.9 dan notebook G1 (tgar-g1-*-real):
  - pembagian kanonik per jenjang (PJOK 622/158/197, Pancasila 497/126/158),
  - Qwen2.5-7B-Instruct 4-bit NF4 + double quantization, dimuat SEKALI untuk 12 adapter,
  - LoRA r=16, alpha=32, dropout=0,05, tujuh modul sasaran,
  - 3 epoch, lr 2e-4, batch efektif 4, panjang maksimum 512 token,
  - rugi hanya atas token jawaban (token prompt diberi label -100), target diakhiri EOS,
  - konteks disisipkan HANYA bila memuat jawaban (MODE_INJEKSI 'didukung'), sehingga
    adapter mengenal prompt tanpa konteks (S2) maupun berkonteks (S4).
Prompt dibentuk oleh tb.agen.pesan_jawab, fungsi yang sama dengan saat Act Agent menjawab,
jadi tidak mungkin ada selisih prompt antara pelatihan dan pemakaian.

Kaggle (GPU):    python -m tb.latih --mapel PJOK PKN --cari semantik
Uji asap (CPU):  python -m tb.latih --model-dasar Qwen/Qwen2.5-0.5B-Instruct --cari bm25 \
                     --maks-langkah 2 --maks-contoh 8 --keluaran adapters_uji
Keluaran: <keluaran>/<MAPEL>/grade_<k>/  (adapter_config.json, adapter_model.safetensors,
          riwayat_loss.json) dan <keluaran>/ringkasan_latih.json
"""
from __future__ import annotations

import argparse
import gc
import json
import math
import os
import re
import shutil
import time

from .agen import pesan_jawab
from .data_qa import bagi_data
from .korpus import MAPEL

SEED = 42
LORA = dict(r=16, lora_alpha=32, lora_dropout=0.05, bias="none", task_type="CAUSAL_LM",
            target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                            "gate_proj", "up_proj", "down_proj"])
EPOCH, LR, BATCH, AKUMULASI, MAKS_PANJANG = 3, 2e-4, 1, 4, 512


def _norm(t):
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", str(t).lower())).strip()


def mendukung(jawaban: str, konteks: str | None) -> bool:
    """Sama dengan _mendukung() notebook G1: jawaban muncul utuh, atau minimal 60% kata
    jawaban (lebih dari dua huruf) ada di konteks."""
    if not konteks or not konteks.strip():
        return False
    na, nc = _norm(jawaban), _norm(konteks)
    if na and na in nc:
        return True
    a = {w for w in na.split() if len(w) > 2}
    c = {w for w in nc.split() if len(w) > 2}
    return bool(a) and len(a & c) / len(a) >= 0.6


def siapkan_konteks(pencari, mapel: str, bagian: dict) -> dict:
    """Mencari konteks untuk setiap soal latih dan validasi dengan pencari yang SAMA
    seperti saat menjawab (kueri = pertanyaan saja, disaring jenjang dan mapel)."""
    hasil = {}
    for nama in ("latih", "validasi"):
        rows = []
        for r in bagian[nama].itertuples():
            kon = None
            if pencari is not None:
                h = pencari.cari(r.pertanyaan, mapel, int(r.kelas))
                kon = h.konteks["teks"] if h.konteks else None
            rows.append({"kelas": int(r.kelas), "pertanyaan": r.pertanyaan,
                         "jawaban": r.jawaban, "konteks": kon,
                         "mendukung": mendukung(r.jawaban, kon)})
        hasil[nama] = rows
    return hasil


def kodekan(tok, mapel: str, row: dict) -> dict:
    """Prompt chat template + jawaban + EOS; label -100 untuk seluruh token prompt."""
    for konteks in ([row["konteks"]] if row["mendukung"] else []) + [None]:
        pesan = pesan_jawab(mapel, row["pertanyaan"], konteks)
        prompt = tok.apply_chat_template(pesan, tokenize=True, add_generation_prompt=True)
        if hasattr(prompt, "keys"):            # transformers baru mengembalikan BatchEncoding
            prompt = prompt["input_ids"]
        target = tok(row["jawaban"], add_special_tokens=False)["input_ids"] + [tok.eos_token_id]
        if len(prompt) + len(target) <= MAKS_PANJANG:
            break                              # konteks terlalu panjang -> versi tanpa konteks
    ids = (prompt + target)[:MAKS_PANJANG]
    label = ([-100] * len(prompt) + target)[:MAKS_PANJANG]
    return {"input_ids": ids, "attention_mask": [1] * len(ids), "labels": label,
            "berkonteks": konteks is not None}


def latih(mapel_daftar=("PJOK", "PKN"), keluaran="adapters", cari="semantik",
          model_dasar=None, maks_langkah: int = -1, maks_contoh: int = 0, kelas=range(1, 7)):
    import torch
    from transformers import Trainer, TrainingArguments, DataCollatorForSeq2Seq, set_seed
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    from .model import muat_model_dasar, MODEL_DASAR

    set_seed(SEED)
    os.makedirs(keluaran, exist_ok=True)
    mulai = time.time()

    # 1. konteks dicari lebih dulu, lalu penyandi dilepas agar GPU lega untuk pelatihan
    pencari = None
    if cari == "semantik":
        from .pencarian import PencariSemantik
        pencari = PencariSemantik()
    elif cari == "bm25":
        from .pencarian import PencariBM25
        pencari = PencariBM25()
    data = {}
    for mapel in mapel_daftar:
        b = bagi_data(mapel)
        if maks_contoh:
            for n in ("latih", "validasi"):
                b[n] = b[n].groupby("kelas").head(maks_contoh)
        print(f"{mapel}: latih {len(b['latih'])}, validasi {len(b['validasi'])}, "
              f"uji {len(b['uji'])} (tidak disentuh)")
        data[mapel] = siapkan_konteks(pencari, mapel, b)
        with open(os.path.join(keluaran, f"konteks_latih_{mapel}.json"), "w", encoding="utf-8") as f:
            json.dump(data[mapel], f, ensure_ascii=False, indent=1)
    if hasattr(pencari, "tutup"):
        pencari.tutup()
    del pencari
    gc.collect()

    # 2. model dasar dimuat SEKALI untuk seluruh adapter
    tok, base, q = muat_model_dasar(model_dasar or MODEL_DASAR)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    if q:
        base = prepare_model_for_kbit_training(base, use_gradient_checkpointing=True)
    gpu = torch.cuda.is_available()
    collator = DataCollatorForSeq2Seq(tok, padding=True, label_pad_token_id=-100,
                                      return_tensors="pt")
    peft_model, ringkasan = None, []

    for mapel in mapel_daftar:
        for g in kelas:
            nama = f"{mapel}_grade_{g}"
            tujuan = os.path.join(keluaran, mapel, f"grade_{g}")
            if os.path.exists(os.path.join(tujuan, "adapter_model.safetensors")):
                print(f"=== {nama}: sudah ada, dilewati ===")
                continue
            latih_ds = [kodekan(tok, mapel, r) for r in data[mapel]["latih"] if r["kelas"] == g]
            val_ds = [kodekan(tok, mapel, r) for r in data[mapel]["validasi"] if r["kelas"] == g]
            if not latih_ds:
                continue
            cfg = LoraConfig(**LORA)
            if peft_model is None:
                peft_model = get_peft_model(base, cfg, adapter_name=nama)
            else:
                peft_model.add_adapter(nama, cfg)
            peft_model.set_adapter(nama)
            dilatih = sum(p.numel() for p in peft_model.parameters() if p.requires_grad)
            # pagar G1: bila adapter lain ikut dilatih, bobotnya rusak tanpa pesan apa pun
            batas = 60e6 if q else 0.2 * sum(p.numel() for p in peft_model.parameters())
            assert dilatih < batas, f"{dilatih / 1e6:.1f} M parameter dilatih, >1 adapter aktif"
            n_kon = sum(x["berkonteks"] for x in latih_ds)
            langkah = math.ceil(len(latih_ds) / (BATCH * AKUMULASI)) * EPOCH
            print(f"\n=== {nama}: {len(latih_ds)} contoh ({n_kon} berkonteks), validasi "
                  f"{len(val_ds)}, {dilatih / 1e6:.1f} M parameter, {langkah} langkah ===")
            t0 = time.time()
            args = TrainingArguments(
                output_dir=os.path.join(keluaran, "_tmp"), num_train_epochs=EPOCH,
                max_steps=maks_langkah, per_device_train_batch_size=BATCH,
                per_device_eval_batch_size=1, gradient_accumulation_steps=AKUMULASI,
                # warmup 3% ditulis sebagai jumlah langkah: warmup_ratio dihapus di transformers 5
                learning_rate=LR, lr_scheduler_type="linear",
                warmup_steps=math.ceil(0.03 * (maks_langkah if maks_langkah > 0 else langkah)),
                logging_steps=5, eval_strategy="epoch" if val_ds and maks_langkah < 0 else "no",
                save_strategy="no", report_to=[], seed=SEED, fp16=gpu,
                gradient_checkpointing=q, remove_unused_columns=False,
                dataloader_pin_memory=gpu)
            buang = lambda ds: [{k: v for k, v in x.items() if k != "berkonteks"} for x in ds]
            trainer = Trainer(model=peft_model, args=args, train_dataset=buang(latih_ds),
                              eval_dataset=buang(val_ds) or None, data_collator=collator)
            hasil = trainer.train()
            sementara = os.path.join(keluaran, "_simpan")
            peft_model.save_pretrained(sementara, selected_adapters=[nama])
            os.makedirs(os.path.dirname(tujuan), exist_ok=True)
            shutil.rmtree(tujuan, ignore_errors=True)
            shutil.move(os.path.join(sementara, nama), tujuan)
            shutil.rmtree(sementara, ignore_errors=True)
            riwayat = trainer.state.log_history
            with open(os.path.join(tujuan, "riwayat_loss.json"), "w") as f:
                json.dump(riwayat, f, indent=1)
            evals = [r["eval_loss"] for r in riwayat if "eval_loss" in r]
            ringkasan.append({"mapel": mapel, "kelas": g, "contoh": len(latih_ds),
                              "berkonteks": n_kon, "validasi": len(val_ds),
                              "parameter_dilatih": dilatih, "langkah": hasil.global_step,
                              "loss_latih": round(hasil.training_loss, 4),
                              "loss_validasi": round(evals[-1], 4) if evals else None,
                              "menit": round((time.time() - t0) / 60, 1)})
            print(f"    tersimpan {tujuan} | loss latih {hasil.training_loss:.4f}")
            del trainer
            peft_model.delete_adapter(nama)        # bebaskan memori, cegah adapter ganda
            gc.collect()
            if gpu:
                torch.cuda.empty_cache()

    shutil.rmtree(os.path.join(keluaran, "_tmp"), ignore_errors=True)
    lama = os.path.join(keluaran, "ringkasan_latih.json")
    sebelum = json.load(open(lama)) if os.path.exists(lama) else {"adapter": []}
    kunci = {(r["mapel"], r["kelas"]) for r in ringkasan}
    semua = [r for r in sebelum.get("adapter", []) if (r["mapel"], r["kelas"]) not in kunci] + ringkasan
    with open(lama, "w") as f:
        json.dump({"model_dasar": model_dasar or MODEL_DASAR, "kuantisasi_4bit": q,
                   "lora": LORA, "epoch": EPOCH, "lr": LR, "batch_efektif": BATCH * AKUMULASI,
                   "maks_panjang": MAKS_PANJANG, "pencarian_konteks": cari,
                   "maks_langkah": maks_langkah, "adapter": semua}, f, indent=1)
    print(f"\nselesai dalam {(time.time() - mulai) / 60:.1f} menit -> {keluaran}")
    return semua


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Latih adapter LoRA per jenjang")
    ap.add_argument("--mapel", nargs="+", default=list(MAPEL), choices=list(MAPEL))
    ap.add_argument("--keluaran", default="adapters")
    ap.add_argument("--cari", choices=["semantik", "bm25", "tanpa"], default="semantik")
    ap.add_argument("--model-dasar", default=None)
    ap.add_argument("--maks-langkah", type=int, default=-1, help="uji asap: batasi langkah")
    ap.add_argument("--maks-contoh", type=int, default=0, help="uji asap: contoh per jenjang")
    ap.add_argument("--kelas", type=int, nargs="+", default=list(range(1, 7)))
    a = ap.parse_args()
    latih(a.mapel, a.keluaran, None if a.cari == "tanpa" else a.cari, a.model_dasar,
          a.maks_langkah, a.maks_contoh, a.kelas)
