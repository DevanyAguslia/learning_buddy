"""Buku sekolah: PDF unggahan guru dipotong seperti strategi Recursive penelitian lalu dicari
hanya untuk siswa sekolah itu.  python -m pytest -q tes"""
import os
import sys
import time

import pytest

AKAR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, AKAR)

from tb.keterbacaan import KontrolKeterbacaan

MATERI = [
    "Pemanasan dilakukan sebelum berolahraga agar otot siap bergerak dan tubuh tidak mudah cedera.",
    "Lari estafet dimainkan oleh beberapa pelari yang bergantian membawa tongkat sampai garis akhir.",
    "Senam lantai melatih kelenturan tubuh. Gerakan guling depan dilakukan di atas matras.",
    "Bermain bola kecil seperti kasti melatih kerja sama regu dan ketepatan melempar bola.",
    "Menjaga kebersihan diri dilakukan dengan mandi dua kali sehari dan mencuci tangan.",
    "Renang gaya bebas dimulai dengan meluncur, lalu kaki menendang naik turun bergantian.",
    "Lompat jauh terdiri atas awalan, tolakan, melayang di udara, dan mendarat di bak pasir.",
    "Zumba ceria adalah senam aerobik berirama musik yang membuat jantung sehat dan hati gembira. "
    "Zumba ceria dilakukan bersama teman sambil mengikuti irama musik aerobik.",
]


def buat_pdf(paragraf_per_halaman: list[list[str]]) -> bytes:
    import pymupdf
    doc = pymupdf.open()
    for i, paragraf in enumerate(paragraf_per_halaman):
        hal = doc.new_page()
        y = 60
        for t in paragraf:
            hal.insert_textbox(pymupdf.Rect(60, y, 540, y + 120), t, fontsize=11)
            y += 140
        hal.insert_text((300, 800), str(i + 1), fontsize=9)
    return doc.tobytes()


def pdf_contoh() -> bytes:
    return buat_pdf([[MATERI[i % len(MATERI)], MATERI[(i + 3) % len(MATERI)] + " " + MATERI[(i + 5) % len(MATERI)]]
                     for i in range(8)])


@pytest.fixture
def folder_buku(tmp_path, monkeypatch):
    import tb.buku_sekolah as bs
    monkeypatch.setattr(bs, "FOLDER", str(tmp_path / "buku_sekolah"))
    return tmp_path


def test_proses_pdf_seperti_recursive(folder_buku):
    import tb.buku_sekolah as bs
    path = bs.simpan_pdf(7, pdf_contoh())
    ps, n = bs.proses_pdf(path, 7, 3, "PJOK Kelas III (Penerbit Contoh)", "PJOK", 3)
    assert n == 8 and ps
    assert all(p["id"].startswith("B7-") and p["strategi"] == "Buku Sekolah" for p in ps)
    assert all(p["sekolah"] == 3 and p["kelas"] == 3 and p["buku"].startswith("PJOK") for p in ps)
    assert all(1 <= p["halaman"] <= 8 for p in ps)
    assert max(len(p["teks"]) for p in ps) <= bs.UKURAN + bs.TUMPANG + 1
    assert any("Zumba ceria" in p["teks"] for p in ps)


def test_pdf_hasil_scan_ditolak(folder_buku):
    import pymupdf
    import tb.buku_sekolah as bs
    doc = pymupdf.open()
    for _ in range(6):
        doc.new_page()
    path = bs.simpan_pdf(8, doc.tobytes())
    with pytest.raises(bs.GalatBuku):
        bs.proses_pdf(path, 8, 1, "Buku", "PJOK", 1)
    with pytest.raises(bs.GalatBuku):
        bs.simpan_pdf(9, b"bukan pdf")


def _resmi():
    return [{"id": f"R-{i}", "strategi": "Recursive", "mapel": "PJOK", "kelas": 3, "halaman": i + 1,
             "teks": t} for i, t in enumerate(MATERI[:7])]


def test_bm25_buku_hanya_untuk_sekolahnya(folder_buku):
    import tb.buku_sekolah as bs
    from tb.pencarian import PencariBM25
    path = bs.simpan_pdf(1, pdf_contoh())
    ps, _ = bs.proses_pdf(path, 1, 5, "Buku Sekolah Contoh", "PJOK", 3)
    c = PencariBM25(_resmi())
    c.tambah_buku({"id": 1, "sekolah": 5, "mapel": "PJOK", "kelas": 3, "judul": "Buku Sekolah Contoh"}, ps)
    h = c.cari("apa itu zumba ceria aerobik", "PJOK", 3, sekolah=5)
    assert h.konteks["buku"] == "Buku Sekolah Contoh" and "Zumba" in h.konteks["teks"]
    for lain in (None, 6):                        # sekolah lain tidak melihat buku itu
        h = c.cari("apa itu zumba ceria aerobik", "PJOK", 3, sekolah=lain)
        assert h.konteks is None or "Zumba" not in h.konteks["teks"]
    assert c.cari("zumba ceria", "PJOK", 4, sekolah=5).konteks is None   # kelas lain: tidak ikut
    c.hapus_buku(1)
    h = c.cari("apa itu zumba ceria aerobik", "PJOK", 3, sekolah=5)
    assert h.konteks is None or "Zumba" not in h.konteks["teks"]


def test_api_unggah_buku_dan_siswa_sekolah(folder_buku, monkeypatch):
    from fastapi.testclient import TestClient
    from tb.agen import Sistem
    from tb.akun import Akun
    from tb.pencarian import PencariBM25
    from tb.server import PenjawabLokal, buat_app
    from test_sistem import ModelKaku, PENDEK
    monkeypatch.setenv("TB_KODE_GURU", "kode-guru-uji")
    kontrol = KontrolKeterbacaan.muat()
    sistem = Sistem(ModelKaku([PENDEK] * 6), PencariBM25(_resmi()), kontrol)
    info = {"mode": "uji", "model": "uji", "pencarian": "bm25", "adapter": []}
    app = buat_app(PenjawabLokal(sistem, info), kontrol, Akun(f"sqlite:///{folder_buku / 'akun.db'}"))
    guru, siswa, siswa_lain = TestClient(app), TestClient(app), TestClient(app)

    akun_guru = {"username": "bu_rina", "email": "rina@contoh.id", "password": "rahasia123", "peran": "guru"}
    r = guru.post("/api/daftar", json=akun_guru)
    assert r.status_code == 422 and "Kode pendaftaran" in r.json()["detail"]
    assert guru.post("/api/daftar", json={**akun_guru, "kode_peran": "kode-guru-uji"}).status_code == 200
    assert guru.get("/api/saya").json()["perlu_kode_peran"] == {"guru": True, "peneliti": False}

    kode = guru.post("/api/sekolah", json={"nama": "SD Contoh Jakarta"}).json()["sekolah"]["kode"]
    assert len(kode) == 6
    q = {"judul": "PJOK Kelas III", "penerbit": "Penerbit Contoh", "mapel": "PJOK", "kelas": 3}
    assert guru.post("/api/buku", params=q, content=b"bukan pdf").status_code == 422
    b = guru.post("/api/buku", params=q, content=pdf_contoh()).json()
    assert b["status"] == "antre"
    app.state.antrean_buku.join()
    daftar = guru.get("/api/sekolah").json()["buku"]
    assert daftar[0]["status"] == "siap" and daftar[0]["n_halaman"] == 8 and daftar[0]["n_potongan"] > 0

    # siswa dengan kode sekolah: buku sekolahnya ikut dicari
    r = siswa.post("/api/daftar", json={"username": "andi", "email": "andi@contoh.id", "password": "rahasia123",
                                        "peran": "siswa", "kode_sekolah": "XXXXXX"})
    assert r.status_code == 422 and "Kode sekolah" in r.json()["detail"]
    siswa.post("/api/daftar", json={"username": "andi", "email": "andi@contoh.id", "password": "rahasia123",
                                    "peran": "siswa", "kode_sekolah": kode.lower()})
    assert siswa.get("/api/saya").json()["sekolah"]["nama"] == "SD Contoh Jakarta"
    assert siswa.post("/api/buku", params=q, content=pdf_contoh()).status_code == 403
    tanya = {"pertanyaan": "apa itu zumba ceria aerobik?", "kelas": 3, "skenario": "S3"}
    h = siswa.post("/api/tanya", json=tanya).json()
    assert h["konteks"]["buku"] == "PJOK Kelas III (Penerbit Contoh)"

    # siswa tanpa sekolah tidak mendapat buku itu; boleh bergabung belakangan
    siswa_lain.post("/api/daftar", json={"username": "budi", "email": "budi@contoh.id", "password": "rahasia123",
                                         "peran": "siswa"})
    h = siswa_lain.post("/api/tanya", json=tanya).json()
    assert (h.get("konteks") or {}).get("buku") != "PJOK Kelas III (Penerbit Contoh)"
    assert siswa_lain.post("/api/sekolah/gabung", json={"kode": kode}).status_code == 200
    h = siswa_lain.post("/api/tanya", json=tanya).json()
    assert h["konteks"]["buku"] == "PJOK Kelas III (Penerbit Contoh)"

    # guru menghapus buku: berkas dan indeksnya ikut hilang
    assert guru.delete(f"/api/buku/{b['id']}").status_code == 200
    assert guru.get("/api/sekolah").json()["buku"] == []
    import tb.buku_sekolah as bs
    assert not os.path.exists(bs.folder_buku(b["id"]))
    h = siswa.post("/api/tanya", json=tanya).json()
    assert (h.get("konteks") or {}).get("buku") != "PJOK Kelas III (Penerbit Contoh)"


class _PenyandiKata:
    """Penyandi tiruan: kantong kata ber-hash, cukup untuk menguji jalur FAISS tanpa GPU."""
    def encode(self, teks, **kw):
        import numpy as np
        v = np.zeros((len(teks), 64), dtype="float32")
        for i, t in enumerate(teks):
            for w in t.lower().split():
                v[i, hash(w.strip(".,?")) % 64] += 1
        return v / np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-9)


def test_semantik_buku_sekolah_dan_cache_vektor(folder_buku):
    import faiss
    import tb.buku_sekolah as bs
    from tb.pencarian import PencariSemantik
    c = object.__new__(PencariSemantik)              # tanpa memuat model sungguhan
    c.nama_model, c.embed, c.rerank, c.strategi = "uji/penyandi-kata", _PenyandiKata(), None, ["Recursive"]
    c.indeks = {("Recursive", "PJOK", 3): (faiss.IndexFlatIP(64), [])}
    c._buku_awal()
    path = bs.simpan_pdf(2, pdf_contoh())
    ps, _ = bs.proses_pdf(path, 2, 9, "Buku Contoh", "PJOK", 3)
    meta = {"id": 2, "sekolah": 9, "mapel": "PJOK", "kelas": 3, "judul": "Buku Contoh"}
    c.tambah_buku(meta, ps, bs.folder_buku(2))
    cache = os.path.join(bs.folder_buku(2), "vektor_penyandi-kata.npy")
    assert os.path.exists(cache)
    v = c._kueri("zumba ceria aerobik")
    assert c._calon(v, "PJOK", 3, 5) == []                          # tanpa sekolah: tidak ada
    calon = c._calon(v, "PJOK", 3, 5, sekolah=9)
    assert calon and all(p["buku"] == "Buku Contoh" for p, _ in calon)
    assert "Zumba" in calon[0][0]["teks"]
    c.embed = None                                   # dimuat ulang dari cache tanpa menyandikan
    c.tambah_buku(meta, ps, bs.folder_buku(2))
    assert len(c.buku[2]["ps"]) == len(ps)


def test_pulihkan_kata_terpecah():
    from tb.buku_sekolah import pulihkan_kata_terpecah as f
    assert f("Gosok t elapak t angan dengan sabun.") == "Gosok telapak tangan dengan sabun."
    assert f("Manfaat m andi m em akai sabun") == "Manfaat mandi memakai sabun"
    assert f("sepert i: bagaimana t ubuh kamu") == "seperti: bagaimana tubuh kamu"
    assert f("berdiri di atas matras") == "berdiri di atas matras"     # dua kata utuh tidak digabung
