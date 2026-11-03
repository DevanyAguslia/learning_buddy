"""Model bahasa yang dipakai keempat agen.

ModelQwen   : jalur penelitian. Qwen2.5-7B-Instruct 4-bit NF4 + double quantization,
              compute dtype 16 bit, enam adapter LoRA per mata pelajaran dipasang
              sebagai named adapter di atas SATU model dasar (Subbab 3.1.3.3).
ModelTiruan : pengganti deterministik tanpa GPU, hanya untuk menguji alur dan
              antarmuka di laptop. Keluarannya bukan hasil penelitian.

Keduanya punya antarmuka yang sama:
    pasang_adapter(mapel, kelas) -> bool     True bila adapter jenjang itu tersedia
    lepas_adapter()
    hasilkan(pesan, maks_token, tugas) -> str        penyandian greedy
    probe(pesan, pilihan, tugas) -> {pilihan: peluang}
        membaca logit token pertama setiap pilihan pada posisi jawaban, jadi
        deterministik dan mustahil keluar dari pilihan. Probe selalu memakai model
        dasar (adapter dinonaktifkan), sebab penilai tidak boleh model yang dinilai.
"""
from __future__ import annotations

import contextlib
import math
import os
import re

MODEL_DASAR = "Qwen/Qwen2.5-7B-Instruct"

# Aksara yang boleh keluar dari model: huruf Latin (ASCII, Latin-1, Latin Extended A/B),
# spasi, dan tanda baca umum (“ ” – … dsb). Instruksi "WAJIB Bahasa Indonesia" di prompt
# saja tidak cukup: Qwen kadang tetap menyelipkan huruf Mandarin atau Arab (kuesioner
# 28 Okt: "keterampilان在中文中的翻译是："). Token di luar daftar ini dilarang saat penyandian.
AKSARA_ASING = re.compile(r"[^\s\x20-\x7E -ɏ‐-‧‰-⁞]")


def token_asing(teks: str) -> bool:
    """Token memuat aksara non-Latin, atau hanya sepotong byte UTF-8 (didekode menjadi
    '\\ufffd'; potongan seperti ini adalah bahan huruf Mandarin/Arab/emoji)."""
    return "�" in teks or bool(AKSARA_ASING.search(teks))


def buang_aksara_asing(teks: str) -> str:
    """Pengaman terakhir pada teks keluaran: aksara non-Latin dibuang."""
    return re.sub(r"[ \t]{2,}", " ", AKSARA_ASING.sub("", teks)).strip()


# =============================================================================
# Jalur penelitian (GPU)
# =============================================================================
def muat_model_dasar(model_dasar: str = MODEL_DASAR, dtype: str = "float16",
                     hf_token: str | None = None, kuantisasi: bool | None = None):
    """Memuat tokenizer dan model dasar dengan cara yang SAMA saat melatih dan saat
    menjawab, agar adapter tidak dinilai di atas model dasar yang berbeda.

    GPU  : 4-bit NF4 + double quantization, compute dtype 16 bit (Tabel 3.9).
    CPU  : tanpa kuantisasi, float32 - hanya untuk verifikasi alur dengan model kecil.
    """
    import torch
    from transformers import AutoTokenizer, AutoModelForCausalLM
    ada_gpu = torch.cuda.is_available()
    kuantisasi = ada_gpu if kuantisasi is None else (kuantisasi and ada_gpu)
    tok = AutoTokenizer.from_pretrained(model_dasar, token=hf_token)
    if kuantisasi:
        from transformers import BitsAndBytesConfig
        dt = {"float16": torch.float16, "bfloat16": torch.bfloat16}[dtype]
        bnb = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                                 bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=dt)
        # Sama dengan notebook tgar-g1-*-real: tanpa dtype tambahan, perhatian bawaan
        # sdpa. G3 rusak (keluaran penuh '!') ketika memakai attn_implementation="eager".
        model = AutoModelForCausalLM.from_pretrained(
            model_dasar, quantization_config=bnb, device_map={"": 0}, token=hf_token)
    else:
        import transformers
        from packaging.version import Version
        kunci_dtype = "dtype" if Version(transformers.__version__) >= Version("4.56") else "torch_dtype"
        model = AutoModelForCausalLM.from_pretrained(
            model_dasar, device_map={"": 0} if ada_gpu else None, token=hf_token,
            **{kunci_dtype: torch.float16 if ada_gpu else torch.float32})
    return tok, model, kuantisasi


class ModelQwen:
    def __init__(self, adapter: dict[str, str | None], model_dasar: str = MODEL_DASAR,
                 dtype: str = "float16", hf_token: str | None = None,
                 kuantisasi: bool | None = None):
        """adapter: {"PJOK": pola, "PKN": pola}. Pola memuat {k} untuk jenjang, berupa
        folder lokal ("adapters/PJOK/grade_{k}") atau repo Hub ("hf:akun/repo:grade_{k}").
        Pola None berarti mata pelajaran itu belum punya adapter."""
        import torch
        self.torch = torch
        self.tok, self.model, q = muat_model_dasar(model_dasar, dtype, hf_token, kuantisasi)
        self.nama = model_dasar.split("/")[-1] + (" 4-bit" if q else
                                                  (" fp16 GPU" if torch.cuda.is_available()
                                                   else " CPU"))
        self.tersedia: dict[tuple[str, int], str] = {}
        self._muat_adapter(adapter, hf_token)
        self.model.eval()
        self.aktif: str | None = None
        self.saring = self._saringan_aksara()

    def _saringan_aksara(self):
        """LogitsProcessor yang memberi skor -inf pada setiap token beraksara asing, jadi
        model MUSTAHIL menulis huruf Mandarin/Arab/Korea dsb. Berbeda dengan
        repetition_penalty, saringan ini tidak menyentuh token Latin dari prompt."""
        from transformers import LogitsProcessor, LogitsProcessorList
        torch = self.torch
        n_vocab = self.model.get_output_embeddings().weight.shape[0]
        teks = self.tok.batch_decode([[i] for i in range(len(self.tok))])
        larang = torch.ones(n_vocab, dtype=torch.bool)     # id di luar tokenizer: dilarang
        for i, t in enumerate(teks[:n_vocab]):
            larang[i] = token_asing(t)
        larang[[i for i in self.tok.all_special_ids if i < n_vocab]] = False   # <|im_end|> dll.
        larang = larang.to(self.model.device)
        print(f"  saringan aksara: {int(larang.sum())} dari {n_vocab} token dilarang")

        class SaringAksara(LogitsProcessor):
            def __call__(self, input_ids, scores):
                return scores.masked_fill(larang[:scores.shape[-1]], float("-inf"))

        return LogitsProcessorList([SaringAksara()])

    def _muat_adapter(self, adapter, hf_token):
        from peft import PeftModel
        for mapel, pola in adapter.items():
            if not pola:
                continue
            for k in range(1, 7):
                nama = f"{mapel}_k{k}"
                sumber, kw = pola.format(k=k), {}
                if sumber.startswith("hf:"):
                    repo, _, sub = sumber[3:].partition(":")
                    sumber, kw = repo, {"subfolder": sub, "token": hf_token} if sub else {"token": hf_token}
                elif not os.path.exists(sumber):
                    print(f"  adapter {nama} tidak ditemukan: {sumber}")
                    continue
                if isinstance(self.model, PeftModel):
                    self.model.load_adapter(sumber, adapter_name=nama, **kw)
                else:
                    self.model = PeftModel.from_pretrained(self.model, sumber, adapter_name=nama, **kw)
                self.tersedia[(mapel, k)] = nama
                print(f"  adapter {nama} dimuat")

    # --- adapter -----------------------------------------------------------------
    def pasang_adapter(self, mapel: str, kelas: int) -> bool:
        self.aktif = self.tersedia.get((mapel, int(kelas)))
        return self.aktif is not None

    def lepas_adapter(self):
        self.aktif = None

    def _konteks_adapter(self, pakai_adapter: bool):
        if not self.tersedia:
            return contextlib.nullcontext()
        if pakai_adapter and self.aktif:
            self.model.set_adapter(self.aktif)
            return contextlib.nullcontext()
        return self.model.disable_adapter()

    # --- pembangkitan ------------------------------------------------------------
    def _masukan(self, pesan):
        teks = self.tok.apply_chat_template(pesan, tokenize=False, add_generation_prompt=True)
        return self.tok(teks, return_tensors="pt").to(self.model.device)

    def hasilkan(self, pesan: list[dict], maks_token: int = 128, tugas: str = "") -> str:
        inp = self._masukan(pesan)
        # Sengaja TANPA repetition_penalty / no_repeat_ngram_size: di HF keduanya ikut menghukum
        # token prompt, sehingga model menghindari kata dari potongan buku dan ejaannya rusak
        # (uji 28 Okt: "telur" -> "telor", "Senin" -> "Senins", huruf Mandarin). Kata berulang
        # ditangani saat memilih jawaban (agen.jawaban_rusak).
        with self.torch.inference_mode(), self._konteks_adapter(tugas == "jawab"):
            out = self.model.generate(**inp, max_new_tokens=maks_token, do_sample=False,
                                      temperature=None, top_p=None, top_k=None,
                                      logits_processor=self.saring,
                                      pad_token_id=self.tok.eos_token_id)
        teks = self.tok.decode(out[0, inp["input_ids"].shape[1]:], skip_special_tokens=True)
        return buang_aksara_asing(teks)

    def _id_awal(self, kata: str) -> list[int]:
        ids = set()
        for v in {kata, kata.lower(), kata.capitalize(), " " + kata}:
            t = self.tok(v, add_special_tokens=False)["input_ids"]
            if t:
                ids.add(t[0])
        return sorted(ids)

    def probe(self, pesan: list[dict], pilihan: list[str], tugas: str = "") -> dict[str, float]:
        inp = self._masukan(pesan)
        with self.torch.inference_mode(), self._konteks_adapter(False):
            lg = self.model(**inp).logits[0, -1].float()
        ids = [set(self._id_awal(p)) for p in pilihan]
        # token awal yang dimiliki dua pilihan sekaligus dibuang agar probe tidak berat sebelah
        bersama = {t for i, a in enumerate(ids) for b in ids[i + 1:] for t in a & b}
        ids = [sorted(a - bersama) or sorted(a) for a in ids]
        skor = [self.torch.logsumexp(lg[i], 0) for i in ids]
        prob = self.torch.softmax(self.torch.stack(skor), 0).tolist()
        return dict(zip(pilihan, prob))

    def periksa_sehat(self):
        """Pagar mutu keluaran (pagar ke-5, Subbab 3.1.3.5): logit sah dan kalimat wajar."""
        pesan = [{"role": "user", "content": "Sebutkan satu manfaat olahraga."}]
        inp = self._masukan(pesan)
        with self.torch.inference_mode(), self._konteks_adapter(False):
            lg = self.model(**inp).logits[0, -1].float()
        assert not (self.torch.isnan(lg).any() or self.torch.isinf(lg).any()), "logit rusak"
        teks = self.hasilkan(pesan, 32)
        rasio = teks.count("!") / max(len(teks), 1)
        assert teks and rasio < 0.2, f"keluaran tidak wajar: {teks[:80]!r}"
        return teks


# =============================================================================
# Pengganti tanpa GPU
# =============================================================================
_SINONIM = {"merupakan": "adalah", "melakukan": "membuat", "dilakukan": "dibuat",
            "bertujuan": "berguna", "meningkatkan": "menambah", "memperoleh": "mendapat",
            "individu": "orang", "sehingga": "jadi", "apabila": "kalau", "namun": "tetapi",
            "senantiasa": "selalu", "beberapa": "banyak", "tertentu": "", "suatu": "satu"}


class ModelTiruan:
    """Deterministik. Menjawab dengan mengutip kalimat konteks yang paling mirip
    pertanyaan, lalu menyederhanakan secara mekanis bila Reflect Agent menolaknya."""
    nama = "tiruan (tanpa GPU)"

    def __init__(self, adapter_tersedia: tuple[str, ...] = ("PJOK",)):
        self.tersedia = {(m, k): f"{m}_k{k}" for m in adapter_tersedia for k in range(1, 7)}
        self.aktif = None

    def pasang_adapter(self, mapel, kelas):
        self.aktif = self.tersedia.get((mapel, int(kelas)))
        return self.aktif is not None

    def lepas_adapter(self):
        self.aktif = None

    @staticmethod
    def _kata(t):
        return {w for w in re.findall(r"[a-z]+", t.lower()) if len(w) > 3}

    def hasilkan(self, pesan, maks_token=128, tugas=""):
        isi = pesan[-1]["content"]
        if tugas == "rapikan":
            t = isi.strip().rstrip("?").strip()
            return (t[:1].upper() + t[1:] + "?") if t else t
        if tugas == "saran":
            kata = [w for w in re.findall(r"[A-Za-z]+", isi) if len(w) > 3]
            return f"Apa yang dimaksud dengan {max(kata, key=len).lower()}?" if kata else ""
        if tugas == "topik":
            q = isi.split("Pertanyaan:")[-1]
            kata = [w for w in re.findall(r"[A-Za-z]+", q) if len(w) > 4][:2]
            return " ".join(kata).lower() or "umum"
        if tugas == "tulis_ulang":
            jawaban = isi.split("Jawaban sebelumnya: ", 1)[1].split("\n")[0]
            arahan = isi.split("Tugas: ", 1)[1].split("\n")[0]
            if "belum menjawab" not in arahan:                    # perbaikan keterbacaan
                return self._sederhanakan(jawaban, arahan)
            if "Potongan buku:" not in isi:
                return jawaban
            konteks = isi.split("Potongan buku:\n", 1)[1].split("\n\n")[0]
            tanya = isi.split("Pertanyaan siswa: ", 1)[1].split("\n")[0]
            return self._kutip(konteks, tanya, jawaban)
        if tugas != "jawab":
            return ""
        pertama = next(p["content"] for p in pesan if p["role"] == "user")
        if "Konteks:" not in pertama:
            return ("Cara menjawab ini butuh AI, tetapi AI belum dinyalakan (mode uji tampilan). "
                    "Pilih Lihat Buku atau Paling Lengkap untuk mencoba.")
        return self._kutip(pertama.split("Konteks:\n", 1)[1].split("\n\n")[0],
                           pertama.split("Pertanyaan:")[-1], "")

    def _kutip(self, konteks, tanya, dipakai):
        kal = [k.strip() for k in re.split(r"(?<=[.!?])\s+", konteks) if len(k.split()) >= 4]
        if not kal:
            return konteks[:200]
        q = self._kata(tanya)
        urut = sorted(range(len(kal)), key=lambda i: -len(q & self._kata(kal[i])))
        # perbaikan karena tidak menjawab: kalimat yang belum dipakai jawaban sebelumnya
        urut = [i for i in urut if kal[i] not in dipakai] or urut
        return " ".join(kal[i] for i in sorted(urut[:2]))

    def _sederhanakan(self, jawaban, arahan):
        m = re.search(r"paling banyak (\d+) kata", arahan)
        batas = int(m.group(1)) if m else 12
        for a, b in _SINONIM.items():
            jawaban = re.sub(rf"\b{a}\b", b, jawaban, flags=re.I)
        keluar = []
        for k in re.split(r"(?<=[.!?])\s+", jawaban):
            kata = k.rstrip(".!?").replace(",", "").split()
            for i in range(0, len(kata), max(batas - 1, 3)):
                bag = kata[i:i + max(batas - 1, 3)]
                if bag:
                    keluar.append(bag[0][:1].upper() + " ".join(bag)[1:] + ".")
        return re.sub(r"\s+", " ", " ".join(keluar[:4])).strip()

    def probe(self, pesan, pilihan, tugas=""):
        isi = pesan[-1]["content"]
        if tugas == "jelas":
            t = isi.split("Masukan:")[-1].split("\n")[0].strip().lower()
            tanya = bool(re.search(r"\?|\b(apa|apakah|siapa|mengapa|kenapa|bagaimana|kapan|"
                                   r"berapa|di mana|sebutkan|jelaskan|adalah|yaitu)\b", t))
            ya = 0.9 if (len(t.split()) >= 3 and tanya) else 0.1
            return {"YA": ya, "TIDAK": 1 - ya}
        if tugas == "kelas":
            t = isi.split("Pertanyaan:")[-1]
            kata = re.findall(r"[A-Za-z]+", t)
            rata = sum(map(len, kata)) / max(len(kata), 1)
            pusat = min(6, max(1, round((rata - 4.0) * 1.4)))
            skor = [math.exp(-abs(int(p) - pusat)) for p in pilihan]
            return {p: s / sum(skor) for p, s in zip(pilihan, skor)}
        if tugas == "relevan":     # tiruan kasar: jawaban memuat kata isi pertanyaan?
            q = self._kata(isi.split("Pertanyaan:")[-1].split("\n")[0])
            j = self._kata(isi.split("Jawaban:")[-1].split("\n")[0])
            ya = 0.8 if len(q & j) >= max(1, len(q) // 3) else 0.2
            return {"YA": ya, "TIDAK": 1 - ya}
        return {p: 1 / len(pilihan) for p in pilihan}

    def periksa_sehat(self):
        return "mode tiruan"
