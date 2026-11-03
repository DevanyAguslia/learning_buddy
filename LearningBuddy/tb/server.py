"""Server HTTP Learning Buddy.

Tiga cara menjalankan:

  1. Laptop, model tiruan (mencoba alur dan UI, tanpa GPU):
        python -m tb.server --tiruan

  2. Laptop sebagai GERBANG ke GPU Kaggle (disarankan selama pengembangan):
        python -m tb.server --remote https://xxxx.trycloudflare.com --remote-kunci RAHASIA
     UI, Lab keterbacaan, evaluasi rumus, dan pengujian berjalan di laptop; hanya
     pertanyaan ke model yang diteruskan ke Kaggle.

  3. Di Kaggle/GPU (server penelitian):
        python -m tb.server --host 0.0.0.0 --cari semantik --adapter-pjok ".../grade_{k}"

Endpoint:
    GET  /api/sehat              status, mode, adapter
    GET  /api/info               mata pelajaran, skenario, sasaran per jenjang
    POST /api/tanya              satu pertanyaan, jawaban lengkap beserta jejak
    POST /api/tanya/alir         sama, dialirkan per agen (text/event-stream)
    POST /api/ukur               semua rumus keterbacaan atas sebuah teks (tanpa GPU)
    GET  /api/evaluasi           hasil evaluasi rumus (hasil/evaluasi_rumus.json)
    POST /api/uji/mulai          mulai pengujian sistem atas data uji
    GET  /api/uji/status         kemajuan dan ringkasan pengujian yang berjalan
    POST /api/uji/hentikan
    GET  /api/uji/riwayat        daftar hasil pengujian yang tersimpan
    POST /api/daftar  /api/masuk  /api/keluar   akun (bila database tersambung)
    GET  /api/saya               pengguna yang sedang masuk
    GET  /api/percakapan[/id]    riwayat chat milik pengguna;  DELETE /api/percakapan/id
    GET  /api/sekolah            sekolah pengguna + daftar buku sekolah
    POST /api/sekolah            guru membuat sekolah (mendapat kode sekolah)
    POST /api/sekolah/gabung     bergabung ke sekolah dengan kode
    POST /api/buku?judul=..&mapel=..&kelas=..   guru mengunggah PDF buku sekolah (badan = PDF)
    DELETE /api/buku/id          menghapus buku sekolah
    GET  /                       antarmuka chat;  /lab.html  Lab keterbacaan;  /masuk.html

Bila TB_KUNCI diisi, /api/tanya* dan /api/uji/* wajib membawa header X-Kunci.
Bila TB_DATABASE_URL tersedia (lihat tb/akun.py), semua halaman dan API wajib login:
siswa hanya chat; guru dan peneliti chat + Lab keterbacaan.
Bila TB_KODE_GURU / TB_KODE_PENELITI diisi, mendaftar sebagai guru / peneliti wajib memakai kode itu.
"""
from __future__ import annotations

import argparse
import hmac
import json
import os
import queue
import threading

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__
from . import buku_sekolah as bs
from .agen import SKENARIO, MAKS_PUTARAN, MAKS_TANYA_BALIK
from .akun import NAMA_COOKIE, PERAN_LAB, PERAN_PENELITI, UMUR_SESI, Akun, GalatAkun, buka_akun
from .keterbacaan import KontrolKeterbacaan, pisah_kalimat, pisah_kata, suku_kata, KATA_TUGAS
from .korpus import MAPEL
from .rumus import RUMUS, RUMUS_LAB, hitung_semua, kelas_terdekat
from .uji import Penguji, daftar_hasil

AKAR = os.path.dirname(os.path.dirname(__file__))


class Tanya(BaseModel):
    pertanyaan: str = Field(..., min_length=1, max_length=500)
    mata_pelajaran: str = "PJOK"
    kelas: int | None = Field(None, ge=1, le=6, description="kosong = ditetapkan Plan Agent")
    skenario: str = "S4"
    interaktif: bool = Field(True, description="False: tanpa tanya balik dan konfirmasi kelas")
    percakapan_id: int | None = Field(None, description="lanjutan percakapan tersimpan")
    paksa_jawab: bool = Field(False, description="sudah MAKS_TANYA_BALIK kali bertanya balik: langsung jawab")


class Daftar(BaseModel):
    username: str = Field(..., max_length=30)
    email: str = Field(..., max_length=200)
    password: str = Field(..., max_length=200)
    peran: str
    kode_sekolah: str = Field("", max_length=12, description="dari guru; siswa jadi anggota sekolah itu")
    kode_peran: str = Field("", max_length=200, description="kode pendaftaran guru/peneliti")


class BuatSekolah(BaseModel):
    nama: str = Field(..., min_length=3, max_length=120)


class GabungSekolah(BaseModel):
    kode: str = Field(..., min_length=4, max_length=12)


class Masuk(BaseModel):
    identitas: str = Field(..., max_length=200, description="username atau email")
    password: str = Field(..., max_length=200)


class Ukur(BaseModel):
    teks: str = Field(..., min_length=1, max_length=20000)
    mata_pelajaran: str = "PJOK"
    kelas: int | None = Field(None, ge=1, le=6)


class MulaiUji(BaseModel):
    mata_pelajaran: str = "PJOK"
    n_per_kelas: int = Field(3, ge=0, le=100, description="0 = seluruh data uji")
    skenario: list[str] = ["S4"]
    kelas_dari: str = Field("data", pattern="^(data|plan)$")


def ringkas(k: dict) -> dict:
    """Keadaan akhir siklus -> bentuk yang dibaca antarmuka."""
    p = k.get("pemeriksaan_akhir") or {}
    kon = k.get("konteks")
    return {
        "status": k.get("status"),
        "pertanyaan_mentah": k.get("pertanyaan_mentah"),
        "pertanyaan_bersih": k.get("pertanyaan_bersih"),
        "jelas": k.get("jelas"), "p_jelas": k.get("p_jelas"),
        "saran_pertanyaan": k.get("saran_pertanyaan"),
        "mapel": k.get("mapel"), "skenario": k.get("skenario"),
        "kelas": k.get("kelas"), "keyakinan_kelas": k.get("keyakinan_kelas"),
        "sumber_kelas": k.get("sumber_kelas"), "sebaran_kelas": k.get("sebaran_kelas"),
        "sebaran_llm": k.get("sebaran_llm"), "sebaran_buku": k.get("sebaran_buku"),
        "bukti_kelas": k.get("bukti_kelas"), "kandidat_kelas": k.get("kandidat_kelas"),
        "topik": k.get("topik"), "adapter_aktif": k.get("adapter_aktif"),
        "jawaban": k.get("jawaban_akhir"),
        "ukuran": p.get("ukuran"), "sasaran": p.get("sasaran"), "lolos": p.get("lolos"),
        "putaran": k.get("putaran", 0), "putaran_terpilih": k.get("putaran_terpilih"),
        "maks_putaran": MAKS_PUTARAN,
        "riwayat": [{c: r.get(c) for c in ("putaran", "jawaban", "lolos", "lolos_pkr",
                                           "lolos_kld", "ukuran", "sasaran", "jarak",
                                           "alasan", "arahan", "relevan", "p_relevan",
                                           "lolos_keterbacaan")}
                    for r in k.get("riwayat", [])],
        "konteks_relevan": k.get("konteks_relevan"), "skor_konteks": k.get("skor_konteks"),
        "konteks_lintas_kelas": k.get("konteks_lintas_kelas"),
        "relevan": p.get("relevan"),
        "konteks": ({c: kon.get(c) for c in ("id", "buku", "mapel", "kelas", "halaman",
                                             "halaman_buku", "bab", "jenis", "strategi",
                                             "teks", "potongan")} if kon else None),
        "calon_konteks": (k.get("calon_konteks") or [])[:5],
        "metode_cari": k.get("metode_cari"),
        "jejak": k.get("jejak", []), "waktu": k.get("waktu"),
    }


# --- penjawab: lokal atau jarak jauh ------------------------------------------------
class PenjawabLokal:
    """Model dan agen berjalan di mesin ini (tiruan di laptop, Qwen di Kaggle)."""

    def __init__(self, sistem, info: dict):
        self.sistem, self.info = sistem, info
        self.bisa_buku = hasattr(sistem.pencari, "tambah_buku")

    def sehat(self) -> dict:
        return self.info

    def tambah_buku(self, meta: dict, potongan: list[dict], folder: str) -> None:
        self.sistem.pencari.tambah_buku(meta, potongan, folder)

    def hapus_buku(self, buku_id: int) -> None:
        self.sistem.pencari.hapus_buku(buku_id)

    def tanya(self, pertanyaan, mapel, kelas=None, skenario="S4", interaktif=True,
              paksa_jawab=False, sekolah=None) -> dict:
        return ringkas(self.sistem.tanya(pertanyaan, mapel, kelas, skenario, interaktif,
                                         paksa_jawab, sekolah))

    def alir(self, pertanyaan, mapel, kelas=None, skenario="S4", interaktif=True,
             paksa_jawab=False, sekolah=None):
        for simpul, isi in self.sistem.alir(pertanyaan, mapel, kelas, skenario, interaktif,
                                            paksa_jawab, sekolah):
            yield simpul, (ringkas(isi) if simpul == "selesai" else
                           {c: v for c, v in isi.items() if c != "calon_konteks"})


class PenjawabJauh:
    """Meneruskan pertanyaan ke server GPU lain (mis. Kaggle lewat Cloudflare Tunnel).
    Buku sekolah tidak didukung: bukunya harus diindeks di server yang menjalankan model."""
    bisa_buku = False

    def __init__(self, url: str, kunci: str = "", batas_detik: float = 600):
        import httpx
        self.url = url.rstrip("/")
        self.klien = httpx.Client(timeout=httpx.Timeout(batas_detik, connect=20),
                                  headers={"X-Kunci": kunci} if kunci else {})

    def sehat(self) -> dict:
        try:
            s = self.klien.get(f"{self.url}/api/sehat", timeout=15).json()
            return {**s, "mode": f"jarak jauh ({s.get('mode')})", "remote": self.url}
        except Exception as e:
            return {"mode": "jarak jauh (TIDAK TERSAMBUNG)", "model": "-", "pencarian": "-",
                    "adapter": [], "remote": self.url, "galat": str(e)}

    def _badan(self, pertanyaan, mapel, kelas, skenario, interaktif=True, paksa_jawab=False):
        return {"pertanyaan": pertanyaan, "mata_pelajaran": mapel, "kelas": kelas,
                "skenario": skenario, "interaktif": interaktif, "paksa_jawab": paksa_jawab}

    def tanya(self, pertanyaan, mapel, kelas=None, skenario="S4", interaktif=True,
              paksa_jawab=False, sekolah=None) -> dict:
        r = self.klien.post(f"{self.url}/api/tanya",
                            json=self._badan(pertanyaan, mapel, kelas, skenario, interaktif,
                                             paksa_jawab))
        r.raise_for_status()
        return r.json()

    def alir(self, pertanyaan, mapel, kelas=None, skenario="S4", interaktif=True,
             paksa_jawab=False, sekolah=None):
        with self.klien.stream("POST", f"{self.url}/api/tanya/alir",
                               json=self._badan(pertanyaan, mapel, kelas, skenario,
                                                interaktif, paksa_jawab)) as r:
            r.raise_for_status()
            ev = None
            for baris in r.iter_lines():
                if baris.startswith("event: "):
                    ev = baris[7:]
                elif baris.startswith("data: ") and ev:
                    data = json.loads(baris[6:])
                    if ev == "galat":
                        raise RuntimeError(data.get("pesan"))
                    yield ev, data
                    ev = None


# --- Lab: ukur teks ---------------------------------------------------------------------
def _muat_acuan():
    try:
        with open(os.path.join(AKAR, "data", "acuan_rumus.json"), encoding="utf-8") as f:
            return {m: {r: {int(k): v for k, v in a.items()} for r, a in d.items()}
                    for m, d in json.load(f).items()}
    except OSError:
        return {}


def ukur_teks(teks: str, mapel: str, kelas: int | None, kontrol: KontrolKeterbacaan,
              acuan: dict) -> dict:
    daftar = kontrol.daftar[mapel]
    nilai = hitung_semua(teks, daftar)
    if nilai is None:
        raise HTTPException(422, "teks tidak memuat kata")
    hitungan = nilai.pop("_hitungan")
    per_rumus = {}
    kelas_rumus = {}
    for f, peran in RUMUS_LAB.items():           # lima alat ukur proposal v3
        d = {"nilai": round(nilai[f], 3), **RUMUS[f], "peran": peran}
        if mapel in acuan and f in acuan[mapel]:
            kelas_rumus[f] = d["kelas"] = kelas_terdekat(nilai[f], acuan[mapel][f])
        per_rumus[f] = d
    # anotasi kata untuk penyorotan di UI
    kalimat = []
    for k in pisah_kalimat(teks):
        kata = []
        for w in pisah_kata(k):
            wl = w.lower()
            isi = len(wl) >= 3 and wl not in KATA_TUGAS
            kata.append({"w": w, "isi": isi, "luar": isi and wl not in daftar,
                         "suku": suku_kata(w), "panjang": len(w) > 6})
        kalimat.append({"teks": k, "n_kata": len(kata), "kata": kata})
    out = {"rumus": per_rumus, "hitungan": hitungan, "kalimat": kalimat,
           "ada_acuan": bool(kelas_rumus)}
    if kelas:
        out["pemeriksaan"] = kontrol.periksa(teks, mapel, kelas).dict()
    return out


# --- aplikasi ---------------------------------------------------------------------------
def buat_app(penjawab, kontrol: KontrolKeterbacaan, akun: Akun | None = None) -> FastAPI:
    """akun=None: tanpa login (server GPU Kaggle, pengujian). Dengan akun: wajib login."""
    app = FastAPI(title="Learning Buddy", version=__version__)
    if akun is None:          # dengan login, cookie hanya untuk asal yang sama
        app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                           allow_headers=["*"])
    kunci = os.environ.get("TB_KUNCI", "")
    penguji = Penguji(penjawab, kontrol)
    acuan = _muat_acuan()

    def cek_kunci(req: Request):
        if kunci and req.headers.get("x-kunci") != kunci:
            raise HTTPException(401, "kunci akses salah atau belum diisi")

    # --- login ------------------------------------------------------------------
    def pengguna(req: Request):
        return akun.pengguna_dari_token(req.cookies.get(NAMA_COOKIE)) if akun else None

    def wajib_login(req: Request):
        """None bila login tidak aktif; selain itu pengguna yang masuk (atau 401)."""
        if akun is None:
            return None
        p = pengguna(req)
        if p is None:
            raise HTTPException(401, "silakan masuk dulu")
        return p

    def wajib_lab(req: Request):
        p = wajib_login(req)
        if p is not None and p.peran not in PERAN_LAB:
            raise HTTPException(403, "Lab keterbacaan hanya untuk guru dan peneliti")
        return p

    def wajib_peneliti(req: Request):
        """Evaluasi rumus dan Uji sistem: khusus peneliti (guru cukup Ukur teks)."""
        p = wajib_login(req)
        if p is not None and p.peran not in PERAN_PENELITI:
            raise HTTPException(403, "Evaluasi rumus dan Uji sistem hanya untuk peneliti")
        return p

    def pasang_cookie(resp: Response, req: Request, token: str):
        resp.set_cookie(NAMA_COOKIE, token, max_age=int(UMUR_SESI.total_seconds()), httponly=True,
                        samesite="lax", secure=req.url.scheme == "https", path="/")

    if akun is not None:
        @app.middleware("http")
        async def gerbang_halaman(req: Request, lanjut):
            jalur = req.url.path
            if jalur in ("/", "/index.html", "/lab.html", "/masuk.html"):
                p = pengguna(req)
                if jalur == "/masuk.html":
                    if p is not None:
                        return RedirectResponse("/", 303)
                elif p is None:
                    return RedirectResponse("/masuk.html", 303)
                elif jalur == "/lab.html" and p.peran not in PERAN_LAB:
                    return RedirectResponse("/", 303)
            return await lanjut(req)

    kode_peran = {"guru": os.environ.get("TB_KODE_GURU", ""),
                  "peneliti": os.environ.get("TB_KODE_PENELITI", "")}

    @app.get("/api/saya")
    def saya(req: Request):
        p = pengguna(req)
        return {"login_aktif": akun is not None, "masuk": p is not None,
                "pengguna": Akun.publik(p) if p else None,
                "sekolah": akun.sekolah(p.sekolah_id) if p and akun else None,
                "perlu_kode_peran": {r: bool(k) for r, k in kode_peran.items()}}

    @app.post("/api/daftar")
    def daftar(d: Daftar, req: Request, resp: Response):
        if akun is None:
            raise HTTPException(404, "database akun belum disambungkan")
        wajib = kode_peran.get(d.peran, "")
        if wajib and not hmac.compare_digest(d.kode_peran.strip().encode(), wajib.encode()):
            raise HTTPException(422, "Kode pendaftaran guru/peneliti salah. Mintalah ke peneliti.")
        try:
            akun.daftar(d.username, d.email, d.password, d.peran, d.kode_sekolah)
            p, token = akun.masuk(d.username, d.password)       # langsung masuk
        except GalatAkun as e:
            raise HTTPException(422, str(e))
        pasang_cookie(resp, req, token)
        return {"pengguna": Akun.publik(p)}

    @app.post("/api/masuk")
    def masuk(m: Masuk, req: Request, resp: Response):
        if akun is None:
            raise HTTPException(404, "database akun belum disambungkan")
        try:
            p, token = akun.masuk(m.identitas, m.password)
        except GalatAkun as e:
            raise HTTPException(401, str(e))
        pasang_cookie(resp, req, token)
        return {"pengguna": Akun.publik(p)}

    @app.post("/api/keluar")
    def keluar(req: Request, resp: Response):
        if akun is not None:
            akun.keluar(req.cookies.get(NAMA_COOKIE))
        resp.delete_cookie(NAMA_COOKIE, path="/")
        return {"keluar": True}

    @app.get("/api/percakapan")
    def daftar_percakapan(req: Request):
        p = wajib_login(req)
        return akun.daftar_percakapan(p.id) if p else []

    @app.get("/api/percakapan/{cid}")
    def isi_percakapan(cid: int, req: Request):
        p = wajib_login(req)
        isi = akun.isi_percakapan(p.id, cid) if p else None
        if isi is None:
            raise HTTPException(404, "percakapan tidak ditemukan")
        return isi

    @app.delete("/api/percakapan/{cid}")
    def hapus_percakapan(cid: int, req: Request):
        p = wajib_login(req)
        if not p or not akun.hapus_percakapan(p.id, cid):
            raise HTTPException(404, "percakapan tidak ditemukan")
        return {"terhapus": cid}

    def simpan(p, t: "Tanya", hasil: dict) -> int | None:
        if p is None:
            return None
        return akun.simpan_pesan(p.id, t.percakapan_id, t.mata_pelajaran, t.pertanyaan,
                                 t.skenario, hasil)

    def paksa(p, t: "Tanya") -> bool:
        """Sudah MAKS_TANYA_BALIK kali berturut-turut bertanya balik (tanya balik Perceive atau
        konfirmasi kelas Plan) di percakapan ini? Dihitung dari riwayat tersimpan bila ada."""
        if t.paksa_jawab:
            return True
        if p is None or not t.percakapan_id:
            return False
        isi = akun.isi_percakapan(p.id, t.percakapan_id) or {}
        n = 0
        for m in reversed(isi.get("pesan", [])):
            if (m.get("hasil") or {}).get("status") not in ("tanya_balik", "konfirmasi_kelas"):
                break
            n += 1
        return n >= MAKS_TANYA_BALIK

    def cek_mapel(m: str):
        if m not in MAPEL:
            raise HTTPException(422, f"mata pelajaran harus salah satu dari {list(MAPEL)}")

    def cek_skenario(s: str):
        if s not in SKENARIO:
            raise HTTPException(422, f"skenario harus salah satu dari {list(SKENARIO)}")

    @app.get("/api/sehat")
    def sehat():
        # kolom milik server ini ditulis terakhir agar tidak tertimpa status server jauh
        return {**penjawab.sehat(), "status": "siap", "versi": __version__,
                "perlu_kunci": bool(kunci)}

    @app.get("/api/info")
    def info():
        return {
            "mapel": {m: {"nama": v["nama"], "singkat": v["singkat"]} for m, v in MAPEL.items()},
            "skenario": {s: {"adapter": a, "konteks": c} for s, (a, c) in SKENARIO.items()},
            "maks_putaran": MAKS_PUTARAN,
            "sasaran": {m: {k: vars(s) for k, s in v.items()} for m, v in kontrol.sasaran.items()},
            "pencocokan": kontrol.meta.get("pencocokan", "bentuk"),
            "rumus": {f: {**RUMUS[f], "peran": p} for f, p in RUMUS_LAB.items()},
        }

    @app.post("/api/tanya")
    def tanya(t: Tanya, req: Request):
        p = wajib_login(req)
        cek_kunci(req); cek_mapel(t.mata_pelajaran); cek_skenario(t.skenario)
        try:
            hasil = penjawab.tanya(t.pertanyaan, t.mata_pelajaran, t.kelas, t.skenario,
                                   t.interaktif, paksa(p, t), p.sekolah_id if p else None)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(502, f"penjawab gagal: {e}")
        cid = simpan(p, t, hasil)
        return {**hasil, "percakapan_id": cid} if cid else hasil

    @app.post("/api/tanya/alir")
    def tanya_alir(t: Tanya, req: Request):
        p = wajib_login(req)
        cek_kunci(req); cek_mapel(t.mata_pelajaran); cek_skenario(t.skenario)

        def acara():
            try:
                for simpul, isi in penjawab.alir(t.pertanyaan, t.mata_pelajaran, t.kelas,
                                                 t.skenario, t.interaktif, paksa(p, t),
                                                 p.sekolah_id if p else None):
                    yield (f"event: {simpul}\ndata: "
                           f"{json.dumps(isi, ensure_ascii=False, default=str)}\n\n")
                    if simpul == "selesai":
                        cid = simpan(p, t, json.loads(json.dumps(isi, default=str)))
                        if cid:
                            yield f"event: tersimpan\ndata: {json.dumps({'percakapan_id': cid})}\n\n"
            except Exception as e:
                yield f"event: galat\ndata: {json.dumps({'pesan': str(e)})}\n\n"
        return StreamingResponse(acara(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    # --- sekolah dan buku sekolah -----------------------------------------------------
    antrean: "queue.Queue[int]" = queue.Queue()

    def meta_buku(b: dict) -> dict:
        return {"id": b["id"], "sekolah": b["sekolah"], "mapel": b["mapel"],
                "kelas": b["kelas"], "judul": b["judul"]}

    def proses_buku(buku_id: int):
        b = akun.buku(buku_id)
        if b is None:
            return
        folder = bs.folder_buku(buku_id)
        try:
            if b["status"] == "siap":               # server dinyalakan ulang: muat lagi
                penjawab.tambah_buku(meta_buku(b), bs.muat_potongan(buku_id), folder)
                return
            akun.ubah_buku(buku_id, status="diproses", pesan="membaca dan memotong PDF")
            judul = f"{b['judul']} ({b['penerbit']})" if b["penerbit"] else b["judul"]
            potongan, n = bs.proses_pdf(os.path.join(folder, "buku.pdf"), buku_id, b["sekolah"],
                                        judul, b["mapel"], b["kelas"])
            bs.simpan_potongan(buku_id, potongan)
            akun.ubah_buku(buku_id, pesan=f"mengindeks {len(potongan)} potongan", n_halaman=n,
                           n_potongan=len(potongan))
            penjawab.tambah_buku(meta_buku(b), potongan, folder)
            akun.ubah_buku(buku_id, status="siap", pesan=None)
        except bs.GalatBuku as e:
            akun.ubah_buku(buku_id, status="gagal", pesan=str(e))
        except Exception as e:                      # rincian hanya di log server
            print(f"buku {buku_id} gagal diproses:", repr(e))
            akun.ubah_buku(buku_id, status="gagal", pesan=f"gagal diproses ({type(e).__name__})")

    def pekerja_buku():
        while True:
            buku_id = antrean.get()
            try:
                proses_buku(buku_id)
            finally:
                antrean.task_done()

    if akun is not None and getattr(penjawab, "bisa_buku", False):
        threading.Thread(target=pekerja_buku, daemon=True, name="buku-sekolah").start()
        for b in akun.daftar_buku():                # buku siap dimuat, yang terputus diulang
            if b["status"] != "gagal":
                antrean.put(b["id"])
    app.state.antrean_buku = antrean

    def wajib_sekolah(req: Request):
        if akun is None:
            raise HTTPException(404, "database akun belum disambungkan")
        return wajib_login(req)

    @app.get("/api/sekolah")
    def sekolah_saya(req: Request):
        p = wajib_sekolah(req)
        sk = akun.sekolah(p.sekolah_id)
        return {"sekolah": sk, "bisa_unggah": getattr(penjawab, "bisa_buku", False),
                "buku": akun.daftar_buku(sk["id"]) if sk and p.peran in PERAN_LAB else []}

    @app.post("/api/sekolah")
    def buat_sekolah(b: BuatSekolah, req: Request):
        p = wajib_sekolah(req)
        if p.peran not in PERAN_LAB:
            raise HTTPException(403, "hanya guru yang dapat membuat sekolah")
        if p.sekolah_id:
            raise HTTPException(409, "akun ini sudah terdaftar di sebuah sekolah")
        try:
            return {"sekolah": akun.buat_sekolah(p.id, b.nama)}
        except GalatAkun as e:
            raise HTTPException(422, str(e))

    @app.post("/api/sekolah/gabung")
    def gabung_sekolah(g: GabungSekolah, req: Request):
        p = wajib_sekolah(req)
        try:
            return {"sekolah": akun.gabung_sekolah(p.id, g.kode)}
        except GalatAkun as e:
            raise HTTPException(422, str(e))

    @app.post("/api/buku")
    async def unggah_buku(req: Request, judul: str, mapel: str, kelas: int, penerbit: str = ""):
        p = wajib_sekolah(req)
        if p.peran not in PERAN_LAB:
            raise HTTPException(403, "hanya guru yang dapat mengunggah buku")
        if not p.sekolah_id:
            raise HTTPException(409, "buat atau gabung sekolah dulu")
        if not getattr(penjawab, "bisa_buku", False):
            raise HTTPException(409, "server ini meneruskan pertanyaan ke server lain; "
                                     "unggah buku di server yang menjalankan model")
        cek_mapel(mapel)
        judul, penerbit = judul.strip()[:200], penerbit.strip()[:120]
        if not judul or not 1 <= kelas <= 6:
            raise HTTPException(422, "judul wajib diisi dan kelas 1-6")
        if int(req.headers.get("content-length") or 0) > bs.MAKS_MB * 1024 * 1024:
            raise HTTPException(413, f"PDF paling besar {bs.MAKS_MB} MB")
        isi = await req.body()
        if len(isi) > bs.MAKS_MB * 1024 * 1024:
            raise HTTPException(413, f"PDF paling besar {bs.MAKS_MB} MB")
        if not isi.startswith(b"%PDF"):
            raise HTTPException(422, "berkas bukan PDF")
        b = akun.tambah_buku(p.sekolah_id, p.id, judul, penerbit, mapel, kelas)
        bs.simpan_pdf(b["id"], isi)
        antrean.put(b["id"])
        return b

    @app.delete("/api/buku/{buku_id}")
    def hapus_buku(buku_id: int, req: Request):
        p = wajib_sekolah(req)
        if p.peran not in PERAN_LAB or not p.sekolah_id:
            raise HTTPException(403, "hanya guru sekolah itu yang dapat menghapus bukunya")
        b = akun.buku(buku_id)
        if b is None or b["status"] in ("antre", "diproses"):
            raise HTTPException(409, "buku sedang diproses; tunggu sampai selesai")
        if not akun.hapus_buku(buku_id, p.sekolah_id):
            raise HTTPException(404, "buku tidak ditemukan")
        if getattr(penjawab, "bisa_buku", False):
            penjawab.hapus_buku(buku_id)
        bs.hapus_berkas(buku_id)
        return {"terhapus": buku_id}

    @app.post("/api/ukur")
    def ukur(u: Ukur, req: Request):
        wajib_lab(req)
        cek_mapel(u.mata_pelajaran)
        return ukur_teks(u.teks, u.mata_pelajaran, u.kelas, kontrol, acuan)

    @app.get("/api/evaluasi")
    def evaluasi(req: Request):
        wajib_peneliti(req)
        p = os.path.join(AKAR, "hasil", "evaluasi_rumus.json")
        if not os.path.exists(p):
            raise HTTPException(404, "jalankan dulu: python -m tb.evaluasi_rumus")
        with open(p, encoding="utf-8") as f:
            hasil = json.load(f)
        # Lab hanya menampilkan lima alat ukur proposal (tanpa rumus lain dan integrasi)
        hasil["rumus"] = {k: {**v, "peran": RUMUS_LAB[k]} for k, v in hasil["rumus"].items()
                          if k in RUMUS_LAB}
        for m in hasil.get("mapel", {}).values():
            for tingkat in ("buku", "halaman", "jawaban"):
                if isinstance(m.get(tingkat), dict):
                    m[tingkat] = {k: v for k, v in m[tingkat].items() if k in RUMUS_LAB}
        return hasil

    @app.post("/api/uji/mulai")
    def uji_mulai(m: MulaiUji, req: Request):
        wajib_peneliti(req)
        cek_kunci(req); cek_mapel(m.mata_pelajaran)
        for s in m.skenario:
            cek_skenario(s)
        try:
            return penguji.mulai(m.mata_pelajaran, m.n_per_kelas, m.skenario, m.kelas_dari)
        except RuntimeError as e:
            raise HTTPException(409, str(e))

    @app.get("/api/uji/status")
    def uji_status(req: Request):
        wajib_peneliti(req)
        return penguji.status()

    @app.post("/api/uji/hentikan")
    def uji_hentikan(req: Request):
        wajib_peneliti(req)
        cek_kunci(req)
        penguji.hentikan()
        return penguji.status()

    @app.get("/api/uji/riwayat")
    def uji_riwayat(req: Request):
        wajib_peneliti(req)
        return daftar_hasil()

    @app.middleware("http")
    async def cek_versi_tampilan(req: Request, lanjut):
        # tampilan (html/css/js/svg) selalu dicek ulang ke server, jadi pembaruan langsung
        # terlihat tanpa Ctrl+F5; berkas yang tidak berubah tetap dijawab 304 dari cache
        resp = await lanjut(req)
        if not req.url.path.startswith("/api/"):
            resp.headers.setdefault("Cache-Control", "no-cache")
        return resp

    web = os.path.join(AKAR, "web")
    if os.path.isdir(web):
        app.mount("/", StaticFiles(directory=web, html=True), name="web")
    return app


def siapkan(tiruan: bool = False, adapter_pjok=None, adapter_pkn=None, cari="bm25",
            dtype="float16", remote=None, remote_kunci="", folder_log=None,
            model_dasar=None, kuantisasi=None):
    kontrol = KontrolKeterbacaan.muat()
    if remote:
        return PenjawabJauh(remote, remote_kunci), kontrol
    from .agen import Sistem
    if cari == "semantik":
        from .pencarian import PencariSemantik
        pencari = PencariSemantik()
    else:
        from .pencarian import PencariBM25
        pencari = PencariBM25()
    if tiruan:
        from .model import ModelTiruan
        llm = ModelTiruan(("PJOK", "PKN"))
    else:
        from .model import ModelQwen, MODEL_DASAR
        llm = ModelQwen({"PJOK": adapter_pjok, "PKN": adapter_pkn},
                        model_dasar=model_dasar or MODEL_DASAR, dtype=dtype,
                        hf_token=os.environ.get("HF_TOKEN"), kuantisasi=kuantisasi)
        print("pagar mutu keluaran:", llm.periksa_sehat()[:80])
    info = {"mode": "tiruan" if tiruan else "penelitian", "model": llm.nama,
            "pencarian": pencari.metode,
            "adapter": sorted(f"{m} kelas {k}" for (m, k) in llm.tersedia)}
    sistem = Sistem(llm, pencari, kontrol, folder_log or os.path.join(AKAR, "log"))
    return PenjawabLokal(sistem, info), kontrol


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tiruan", action="store_true", help="model tiruan tanpa GPU")
    ap.add_argument("--qwen", action="store_true", help="Qwen di GPU (walau tanpa adapter)")
    ap.add_argument("--remote", default=os.environ.get("TB_REMOTE"),
                    help="URL server GPU, mis. https://xxxx.trycloudflare.com")
    ap.add_argument("--remote-kunci", default=os.environ.get("TB_REMOTE_KUNCI", ""))
    ap.add_argument("--adapter-pjok", default=os.environ.get("TB_ADAPTER_PJOK"))
    ap.add_argument("--adapter-pkn", default=os.environ.get("TB_ADAPTER_PKN"))
    ap.add_argument("--cari", choices=["bm25", "semantik"], default="bm25")
    ap.add_argument("--dtype", choices=["float16", "bfloat16"], default="float16")
    ap.add_argument("--model-dasar", default=os.environ.get("TB_MODEL_DASAR"),
                    help="bawaan Qwen/Qwen2.5-7B-Instruct; di CPU pakai yang kecil, mis. "
                         "Qwen/Qwen2.5-0.5B-Instruct")
    ap.add_argument("--tanpa-kuantisasi", action="store_true",
                    help="matikan 4-bit (otomatis mati bila tidak ada GPU)")
    ap.add_argument("--tanpa-login", action="store_true",
                    help="abaikan database akun (mis. server GPU di Kaggle)")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    a = ap.parse_args()
    if not (a.tiruan or a.remote or a.qwen or a.adapter_pjok or a.adapter_pkn):
        ap.error("pilih salah satu: --tiruan, --remote URL, atau --qwen (GPU)")
    import uvicorn
    penjawab, kontrol = siapkan(a.tiruan, a.adapter_pjok, a.adapter_pkn, a.cari, a.dtype,
                                a.remote, a.remote_kunci, model_dasar=a.model_dasar,
                                kuantisasi=False if a.tanpa_kuantisasi else None)
    print("siap:", penjawab.sehat())
    try:
        akun = None if a.tanpa_login else buka_akun()
    except Exception as e:                       # .env ada tetapi database belum siap
        raise SystemExit(f"\nDatabase akun tidak bisa dihubungi: {e}\n"
                         "Jalankan dulu deploy/siapkan_database.local.sql dengan psql (lihat README), "
                         "atau jalankan dengan --tanpa-login.")
    print("login:", "AKTIF (database tersambung)" if akun else
          "tidak aktif (TB_DATABASE_URL / .env belum ada)" if not a.tanpa_login else "dimatikan --tanpa-login")
    # Di belakang nginx/Docker: percayai X-Forwarded-Proto dari proxy agar cookie login
    # bertanda Secure saat situs diakses lewat HTTPS (TB_FORWARDED_IPS, mis. "*").
    uvicorn.run(buat_app(penjawab, kontrol, akun), host=a.host, port=a.port, proxy_headers=True,
                forwarded_allow_ips=os.environ.get("TB_FORWARDED_IPS", "127.0.0.1"))


if __name__ == "__main__":
    main()
