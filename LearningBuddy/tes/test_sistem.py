"""Pengujian tanpa GPU:  python -m pytest -q tes"""
import json
import os
import sys

import pytest

AKAR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, AKAR)

from tb.keterbacaan import KontrolKeterbacaan, pisah_kalimat, kata_isi, ukur, jarak_ke_sasaran, Sasaran
from tb.potong import potong_halaman


@pytest.fixture(scope="module")
def kontrol():
    return KontrolKeterbacaan.muat()


def _halaman(mapel, kelas, hal):
    with open(os.path.join(AKAR, "data", f"halaman_{mapel}.jsonl"), encoding="utf-8") as f:
        for l in f:
            h = json.loads(l)
            if h["kelas"] == kelas and h["halaman"] == hal:
                return h


# --- Lampiran 1: halaman PDF ke-16 Buku Siswa PJOK kelas 1 --------------------------
def test_lampiran1_pembersihan():
    h = _halaman("PJOK", 1, 16)
    assert h["n_mentah"] == 470
    assert len(h["teks"]) == 393
    assert len(h["teks"].split()) == 58
    assert len(pisah_kalimat(h["teks"])) == 5


def test_lampiran1_potongan():
    ps = potong_halaman(_halaman("PJOK", 1, 16))
    assert [p.id for p in ps] == ["PJOK-K1-016-01"]
    assert len(ps[0].teks) == 393


# --- rumus (2.4) dan Lampiran 4 -----------------------------------------------------
def test_kata_isi_lampiran4():
    assert kata_isi("Untuk melatih kekuatan otot kaki dan paha") == \
        ["melatih", "kekuatan", "otot", "kaki", "paha"]


def test_lampiran4_lolos(kontrol):
    p = kontrol.periksa("Untuk melatih kekuatan otot kaki dan paha.", "PJOK", 1)
    assert p.lolos and p.ukuran["pkr"] == 7.0 and p.ukuran["kld"] == 0.0 and p.arahan is None


def test_penolakan_beserta_arahan(kontrol):
    p = kontrol.periksa("Aktivitas kardiorespirasi merupakan latihan yang bertujuan meningkatkan "
                        "kapasitas sistem kardiovaskular sehingga memperbaiki daya tahan tubuh.",
                        "PJOK", 1)
    assert not p.lolos and not p.lolos_pkr and not p.lolos_kld
    assert "pecah" in p.arahan and "ganti kata sulit" in p.arahan and p.jarak > 0


def test_pemecah_kalimat():
    assert pisah_kalimat("Berjalan") == ["Berjalan"]
    assert len(pisah_kalimat("Jaraknya 1.5 meter, dll. Lalu lari!")) == 2
    assert pisah_kalimat("Bola, raket, dll. dipakai saat bermain.") ==         ["Bola, raket, dll dipakai saat bermain"]
    soal = "1. Menendang bola ada dalam permainan .... a. kasti b. sepak bola c. renang"
    assert pisah_kalimat(soal, min_kata=3) == ["Menendang bola ada dalam permainan"]


def test_jarak_nol_bila_di_bawah_sasaran():
    assert jarak_ke_sasaran(5, 3, Sasaran(10, 9)) == 0
    assert jarak_ke_sasaran(20, 18, Sasaran(10, 9)) == 2.0


def test_sasaran_lengkap(kontrol):
    for m in ("PJOK", "PKN"):
        assert set(kontrol.sasaran[m]) == {1, 2, 3, 4, 5, 6}
        for s in kontrol.sasaran[m].values():
            assert s.maks_pkr == pytest.approx(s.pkr_buku * 1.15, abs=0.15)
            assert s.maks_kld == pytest.approx(s.kld_buku * 1.10, abs=0.15)


# --- siklus agen dengan model tiruan ------------------------------------------------
class ModelKaku:
    """Model uji: jawaban ditentukan per putaran agar ketiga cabang dapat diuji."""
    nama = "uji"
    tersedia = {}

    def __init__(self, jawaban, jelas=0.9, yakin_kelas3=0.9, relevan=None):
        self.jawaban, self.jelas, self.n = jawaban, jelas, 0
        self.yakin = yakin_kelas3
        # relevan: daftar peluang "YA" per putaran untuk pengecekan 2 (bawaan: selalu relevan)
        self.relevan, self.n_rel = relevan or [0.9], 0
        self.arahan = []

    def pasang_adapter(self, *a): return False
    def lepas_adapter(self): pass

    def hasilkan(self, pesan, maks_token=128, tugas=""):
        if tugas == "rapikan":
            return pesan[-1]["content"]
        if tugas == "topik":
            return "uji"
        if tugas == "saran":
            return "Apa manfaat pemanasan"
        self.n += 1
        return self.jawaban[min(self.n, len(self.jawaban)) - 1]

    def probe(self, pesan, pilihan, tugas=""):
        if tugas == "jelas":
            return {"YA": self.jelas, "TIDAK": 1 - self.jelas}
        if tugas == "relevan":
            self.n_rel += 1
            p = self.relevan[min(self.n_rel, len(self.relevan)) - 1]
            return {"YA": p, "TIDAK": 1 - p}
        sisa = (1 - self.yakin) / 5
        return {p: (self.yakin if p == "3" else sisa) for p in pilihan}


class PencariKosong:
    metode = "uji"

    def __init__(self, skor=5.0, skor_lintas=5.0, ambang=1.0):
        self.skor, self.skor_lintas, self.ambang = skor, skor_lintas, ambang

    @staticmethod
    def _p(kelas, id_="X"):
        return {"id": id_, "teks": "konteks uji", "buku": "B", "mapel": "PJOK",
                "kelas": kelas, "halaman": 1, "bab": "", "jenis": "narasi"}

    def cari(self, *a):
        from tb.pencarian import HasilCari
        return HasilCari("uji", self._p(3), [], self.skor)

    def cari_lintas_kelas(self, *a):
        from tb.pencarian import HasilCari
        return HasilCari("uji", self._p(5, "Y"), [], self.skor_lintas)

    def relevan(self, h):
        return h.konteks is not None and h.skor >= self.ambang


PANJANG = ("Salah satu bentuk latihan yang dapat dilakukan untuk meningkatkan kemampuan "
           "kelentukan dan kelenturan tubuh adalah berlunjur sambil mencium lutut.")
PENDEK = "Salah satu latihan kelenturan adalah berlunjur mencium lutut."


def _sistem(model, kontrol, pencari=None):
    from tb.agen import Sistem
    return Sistem(model, pencari or PencariKosong(), kontrol)


def test_graf_tolak(kontrol):
    r = _sistem(ModelKaku([PENDEK], jelas=0.1), kontrol).tanya("halo", "PJOK")
    assert r["status"] == "tolak" and r["riwayat"] == []


def test_graf_lolos_setelah_perbaikan(kontrol):
    r = _sistem(ModelKaku([PANJANG, PENDEK]), kontrol).tanya("latihan kelentukan?", "PJOK")
    assert r["kelas"] == 3 and r["sumber_kelas"] == "Plan Agent"
    assert r["status"] == "lolos" and r["putaran"] == 2 and r["jawaban_akhir"] == PENDEK


def test_graf_batas_pilih_terdekat(kontrol):
    lebih_panjang = PANJANG + " " + PANJANG.replace(".", ",") + " dan seterusnya sampai selesai."
    m = ModelKaku([lebih_panjang, PANJANG, lebih_panjang])
    r = _sistem(m, kontrol).tanya("latihan kelentukan?", "PJOK", kelas=3)
    assert r["status"] == "batas" and r["putaran"] == 3
    assert r["putaran_terpilih"] == 2 and r["jawaban_akhir"] == PANJANG


def test_skenario_tanpa_konteks(kontrol):
    r = _sistem(ModelKaku([PENDEK]), kontrol).tanya("latihan kelentukan?", "PJOK", 3, "S2")
    assert r["konteks"] is None


# --- API ------------------------------------------------------------------------------
def test_api(kontrol):
    from fastapi.testclient import TestClient
    from tb.server import buat_app, PenjawabLokal
    info = {"mode": "uji", "model": "uji", "pencarian": "uji", "adapter": []}
    app = buat_app(PenjawabLokal(_sistem(ModelKaku([PENDEK]), kontrol), info), kontrol)
    c = TestClient(app)
    assert c.get("/api/sehat").json()["status"] == "siap"
    assert set(c.get("/api/info").json()["sasaran"]) == {"PJOK", "PKN"}
    r = c.post("/api/tanya", json={"pertanyaan": "latihan kelentukan?", "kelas": 3}).json()
    assert r["status"] == "lolos" and r["konteks"]["id"] == "X"
    assert c.post("/api/tanya", json={"pertanyaan": "x", "mata_pelajaran": "IPA"}).status_code == 422
    alir = c.post("/api/tanya/alir", json={"pertanyaan": "latihan kelentukan?", "kelas": 3}).text
    for ev in ("perceive", "plan", "act", "reflect", "pilih", "selesai"):
        assert f"event: {ev}" in alir
    u = c.post("/api/ukur", json={"teks": PANJANG, "mata_pelajaran": "PJOK", "kelas": 3}).json()
    assert set(u["rumus"]) == {"PKR", "KLD", "FRY", "DC", "FOG"}
    assert u["pemeriksaan"]["lolos"] is False and u["kalimat"][0]["n_kata"] == 19


# --- rumus pembanding dan metrik pengujian -----------------------------------------
def test_rumus_dan_integrasi():
    from tb.rumus import hitung_semua, integrasi_classroom
    r = hitung_semua("Ani berlari. Budi melompat tinggi sekali.")
    assert r["PKR"] == 3.0
    # Konstanta bahasa Inggris menilai kalimat semudah ini setara mahasiswa, karena kata
    # Indonesia rata-rata bersuku lebih banyak. Karena itu jenjang tidak dibaca langsung
    # dari angka rumus, melainkan dipetakan ulang lewat acuan buku.
    assert r["FKGL"] > 12 and r["FRES"] < 0
    # Algoritma 1: G1 sepakat 2, G2 tidak sepakat -> min 3, G3 sepakat 3 -> modus 3
    k = {"DC": 2, "SPACHE": 2, "FRES": 3, "FKGL": 4, "CLI": 5, "LW": 3, "FOG": 3}
    assert integrasi_classroom(k) == {"suara": {"G1": 2, "G2": 3, "G3": 3}, "kelas": 3,
                                      "cara": "modus"}
    k = {"DC": 1, "SPACHE": 1, "FRES": 3, "FKGL": 3, "CLI": 3, "LW": 5, "FOG": 5}
    assert integrasi_classroom(k)["cara"] == "median" and integrasi_classroom(k)["kelas"] == 3


def test_metrik_acuan():
    from tb.uji import exact_match, token_f1, chrf_pp
    assert exact_match("Berjalan.", "berjalan") == 1.0
    assert token_f1("dua regu sebelas pemain", "sebelas pemain") == pytest.approx(2 / 3)
    assert chrf_pp("berlari", "berlari") == pytest.approx(100.0)
    assert chrf_pp("berlari cepat", "melompat") < 50


def test_pembagian_kanonik():
    from tb.data_qa import bagi_data
    for mapel, n in (("PJOK", (622, 158, 197)), ("PKN", (497, 126, 158))):
        b = bagi_data(mapel)
        assert (len(b["latih"]), len(b["validasi"]), len(b["uji"])) == n


def test_konteks_mendukung_sama_dengan_g1():
    from tb.latih import mendukung
    assert mendukung("dua regu", "Sepak bola dimainkan oleh dua regu.")
    assert mendukung("otot kaki kuat", "Latihan ini membuat otot dan kaki menjadi kuat.")
    assert not mendukung("bulu tangkis", "Sepak bola dimainkan oleh dua regu.")
    assert not mendukung("apa saja", None)


# --- Perceive bertanya balik dan Plan meminta konfirmasi -------------------------------
def test_perceive_tanya_balik(kontrol):
    r = _sistem(ModelKaku([PENDEK], jelas=0.1), kontrol).tanya("pemanasan", "PJOK")
    assert r["status"] == "tanya_balik" and r["saran_pertanyaan"] == "Apa manfaat pemanasan?"
    assert r["riwayat"] == []                     # belum ada jawaban yang disusun


def test_perceive_tolak_bila_tanpa_isi_pelajaran(kontrol):
    r = _sistem(ModelKaku([PENDEK], jelas=0.1), kontrol).tanya("halo kak", "PJOK")
    assert r["status"] == "tolak"


def test_noninteraktif_tidak_bertanya_balik(kontrol):
    r = _sistem(ModelKaku([PENDEK], jelas=0.1), kontrol).tanya("pemanasan", "PJOK",
                                                               interaktif=False)
    assert r["status"] == "tolak"



def test_paksa_jawab_setelah_tiga_kali_bertanya(kontrol):
    # setelah 3 kali bertanya balik, pertanyaan yang ada isinya langsung dijawab
    r = _sistem(ModelKaku([PENDEK], jelas=0.1, yakin_kelas3=0.3), kontrol).tanya(
        "pemanasan", "PJOK", paksa_jawab=True)
    assert r["status"] == "lolos" and r["riwayat"]
    # sapaan tanpa isi pelajaran tetap ditolak
    r = _sistem(ModelKaku([PENDEK], jelas=0.1), kontrol).tanya("halo kak", "PJOK",
                                                               paksa_jawab=True)
    assert r["status"] == "tolak"


def test_rapikan_hanya_perbaikan_tulisan():
    from tb.agen import rapikan_sah
    assert rapikan_sah("apa manfat pemanasn sblm olahraga", "Apa manfaat pemanasan sebelum olahraga?")
    assert rapikan_sah("knp hrs minum air", "Kenapa harus minum air?")
    # jawaban yang menyamar sebagai "dibaca sebagai" ditolak
    assert not rapikan_sah("apa manfaat pemanasan?",
                           "Manfaat pemanasan adalah menyiapkan otot dan jantung agar tidak cedera "
                           "saat berolahraga sehingga tubuh lebih siap bergerak.")
    # mengganti pertanyaan menjadi pertanyaan lain ditolak
    assert not rapikan_sah("apa manfaat pemanasan?", "Bagaimana cara bermain sepak bola dengan benar?")

def test_plan_minta_konfirmasi_bila_ragu(kontrol):
    S = _sistem(ModelKaku([PENDEK], yakin_kelas3=0.3), kontrol)
    r = S.tanya("latihan kelentukan?", "PJOK")
    assert r["status"] == "konfirmasi_kelas" and r["kandidat_kelas"][0] == 3
    assert r["riwayat"] == []
    # siswa menjawab kelasnya -> pertanyaan yang sama langsung dijawab
    r = S.tanya("latihan kelentukan?", "PJOK", kelas=3)
    assert r["status"] == "lolos" and r["sumber_kelas"] == "pengguna"
    # pengujian otomatis tidak pernah berhenti untuk konfirmasi
    r = _sistem(ModelKaku([PENDEK], yakin_kelas3=0.3), kontrol).tanya(
        "latihan kelentukan?", "PJOK", interaktif=False)
    assert r["status"] == "lolos" and r["kelas"] == 3


def test_bukti_buku_letak_materi():
    from tb.agen import AMBANG_KONFIRMASI
    from tb.pencarian import PencariBM25
    P = PencariBM25()
    # "menekuk" muncul di buku kelas 1, 5, dan 6: bukti menyebar, jadi siswa ditanya kelasnya
    p = P.sebaran_kelas("Bagaimana cara melakukan gerakan menekuk?", "PJOK")["peluang"]
    assert abs(sum(p.values()) - 1) < 0.01
    assert "1" in sorted(p, key=p.get)[-2:]          # kelas 1 termasuk dua teratas
    assert max(p.values()) < 0.6                      # bukti menyebar, bukan yakin penuh


def test_tiga_potongan_recursive():
    from tb.pencarian import KIRIM, PencariBM25, pilih_beragam
    P = PencariBM25()
    assert KIRIM == 3
    assert {p["strategi"] for p in P.potongan} == {"Recursive"}
    kon = P.cari("Gerak lokomotor itu apa?", "PJOK", 3).konteks
    assert len(kon["potongan"]) == KIRIM
    assert kon["teks"] == "\n\n".join(p["teks"] for p in kon["potongan"])
    assert all(p["kelas"] == 3 for p in kon["potongan"])
    # potongan yang isinya sudah tercakup potongan terpilih dilewati
    a = {"teks": "Gerak lokomotor adalah gerak berpindah tempat seperti berjalan dan berlari."}
    b = {"teks": "Gerak lokomotor adalah gerak berpindah tempat."}
    c = {"teks": "Menjaga kebersihan gigi dengan menggosok gigi dua kali sehari."}
    assert [p for p, _ in pilih_beragam([(a, 3), (b, 2), (c, 1)], 3)] == [a, c]


def test_rapikan_recursive():
    from tb.impor_potongan import rapikan
    pertama = "Bab ini membahas gerak. Kamu mengatur strategi gerak yang dikuasai ke situasi yang berbeda."
    ekor = pertama[-50:]                                  # diawali sisa kata "ategi"
    kedua = (ekor + " Lalu KEMENTERIAN PENDIDIKAN, KEBUDAYAAN, RISET, DAN TEKNOLOGI "
             "REPUBLIK INDONESIA, 2024 Pendidikan Jasmani, Olahraga, dan Kesehatan untuk SD/MI "
             "Kelas II Penulis: Agung Sudaryono, Puji Rahayu Tujuan Pembelajaran U n i t lari.")
    ps = [{"mapel": "PJOK", "kelas": 2, "teks": pertama}, {"mapel": "PJOK", "kelas": 2, "teks": kedua}]
    out, hitung = rapikan(ps)
    assert ekor.startswith("ategi")
    assert out[1]["teks"] == ("gerak yang dikuasai ke situasi yang berbeda. Lalu Tujuan "
                              "Pembelajaran lari.")
    assert hitung["sisa kata di awal dibuang"] == 1 and hitung["kolofon dibuang"] == 1


# --- dua pengecekan ulang ---------------------------------------------------------------
def test_cek1_materi_dari_kelas_lain(kontrol):
    # buku kelas 3 tidak memuat materinya, buku kelas 5 memuat -> dipakai, dan ditandai
    r = _sistem(ModelKaku([PENDEK]), kontrol, PencariKosong(skor=0.1)).tanya(
        "latihan kelentukan?", "PJOK", kelas=3)
    assert r["status"] == "lolos" and r["konteks"]["id"] == "Y"
    assert r["konteks_lintas_kelas"] == 5 and r["konteks_relevan"] is True


def test_cek1_tidak_ada_materi(kontrol):
    m = ModelKaku([PENDEK])
    r = _sistem(m, kontrol, PencariKosong(skor=0.1, skor_lintas=0.2)).tanya(
        "latihan kelentukan?", "PJOK", kelas=3)
    assert r["status"] == "tidak_ada_materi" and r["riwayat"] == []
    assert m.n == 0                     # tidak ada jawaban yang dikarang tanpa buku


def test_cek2_jawaban_tidak_nyambung_ditulis_ulang(kontrol):
    from tb.agen import Sistem
    m = ModelKaku([PENDEK, PENDEK], relevan=[0.1, 0.9])
    asli = m.hasilkan
    def catat(pesan, maks_token=128, tugas=""):
        if tugas in ("", "jawab", "tulis_ulang"):
            m.arahan.append(pesan[-1]["content"])
        return asli(pesan, maks_token, tugas)
    m.hasilkan = catat
    r = Sistem(m, PencariKosong(), kontrol).tanya("latihan kelentukan?", "PJOK", kelas=3)
    assert r["putaran"] == 2 and r["status"] == "lolos"
    assert r["riwayat"][0]["relevan"] is False and r["riwayat"][1]["relevan"] is True
    assert "belum menjawab pertanyaan" in " ".join(str(x) for x in m.arahan)


def test_cek2_tidak_pernah_relevan(kontrol):
    r = _sistem(ModelKaku([PENDEK] * 3, relevan=[0.1]), kontrol).tanya(
        "latihan kelentukan?", "PJOK", kelas=3)
    assert r["status"] == "tidak_relevan" and r["putaran"] == 3


# --- akun: daftar, masuk, hak akses, riwayat (SQLite sementara; produksi PostgreSQL) ----
def test_login_peran_dan_riwayat(kontrol, tmp_path):
    from fastapi.testclient import TestClient
    from tb.akun import Akun
    from tb.server import buat_app, PenjawabLokal
    info = {"mode": "uji", "model": "uji", "pencarian": "uji", "adapter": []}
    app = buat_app(PenjawabLokal(_sistem(ModelKaku([PENDEK] * 6), kontrol), info), kontrol,
                   Akun(f"sqlite:///{tmp_path / 'akun.db'}"))
    siswa, guru = TestClient(app), TestClient(app)
    tanya = {"pertanyaan": "latihan kelentukan?", "kelas": 3}

    assert siswa.get("/", follow_redirects=False).headers["location"] == "/masuk.html"
    assert siswa.post("/api/tanya", json=tanya).status_code == 401
    r = siswa.post("/api/daftar", json={"username": "budi", "email": "Budi@Contoh.id",
                                        "password": "rahasia123", "peran": "siswa"})
    assert r.status_code == 200 and r.json()["pengguna"]["boleh_lab"] is False
    assert siswa.get("/", follow_redirects=False).status_code == 200
    assert siswa.get("/lab.html", follow_redirects=False).headers["location"] == "/"
    assert siswa.post("/api/ukur", json={"teks": PANJANG}).status_code == 403

    cid = siswa.post("/api/tanya", json=tanya).json()["percakapan_id"]
    alir = siswa.post("/api/tanya/alir", json={**tanya, "percakapan_id": cid}).text
    assert "event: tersimpan" in alir
    isi = siswa.get(f"/api/percakapan/{cid}").json()
    assert len(isi["pesan"]) == 2 and isi["pesan"][0]["hasil"]["status"] == "lolos"
    assert [c["id"] for c in siswa.get("/api/percakapan").json()] == [cid]

    siswa.post("/api/keluar")
    assert siswa.get("/api/saya").json()["masuk"] is False
    assert siswa.post("/api/masuk", json={"identitas": "budi", "password": "salah123"}).status_code == 401
    assert siswa.post("/api/masuk", json={"identitas": "budi@contoh.id", "password": "rahasia123"}).status_code == 200

    dobel = guru.post("/api/daftar", json={"username": "BUDI", "email": "lain@contoh.id",
                                           "password": "rahasia123", "peran": "guru"})
    assert dobel.status_code == 422 and "Username" in dobel.json()["detail"]
    assert guru.post("/api/daftar", json={"username": "bu_ani", "email": "ani@contoh.id",
                                          "password": "rahasia123", "peran": "guru"}).status_code == 200
    assert guru.get("/lab.html", follow_redirects=False).status_code == 200
    assert guru.post("/api/ukur", json={"teks": PANJANG}).status_code == 200
    # guru hanya Ukur teks; Evaluasi rumus dan Uji sistem khusus peneliti
    assert guru.get("/api/saya").json()["pengguna"]["boleh_lab_penuh"] is False
    assert guru.get("/api/evaluasi").status_code == 403
    assert guru.get("/api/uji/status").status_code == 403
    peneliti = TestClient(app)
    assert peneliti.post("/api/daftar", json={"username": "peneliti1", "email": "p@contoh.id",
                                              "password": "rahasia123", "peran": "peneliti"}).status_code == 200
    assert peneliti.get("/api/uji/status").status_code == 200
    assert guru.get(f"/api/percakapan/{cid}").status_code == 404      # milik siswa lain


def test_tulisan_ulang_rusak_tidak_dipilih():
    from tb.agen import jawaban_rusak
    assert jawaban_rusak("bekerja dan tidak membuat membuat membuat membuat")
    assert jawaban_rusak("upacara bendera diadakan di sekolah pada")
    assert not jawaban_rusak("Upacara bendera diadakan setiap hari Senin.")
    assert not jawaban_rusak("Lokomotor")
    assert jawaban_rusak("membentuk keterampilان在中文中的翻译是：")


def test_aksara_asing_disaring():
    from tb.model import buang_aksara_asing, token_asing
    for t in ["在", "中文", "ان", "한", "�", "：", "가"]:
        assert token_asing(t), t
    for t in [" olahraga", "Senin", ".", "\n\n", " “", "–", "…", "é", "<|im_end|>", " 10%"]:
        assert not token_asing(t), t
    assert buang_aksara_asing("keterampilan在中文 gerak.") == "keterampilan gerak."


def test_alamat_database_salinan_neon(monkeypatch):
    from tb.akun import alamat_database
    monkeypatch.setenv("TB_DATABASE_URL", "postgresql://u:p@ep-x.neon.tech/db?sslmode=require")
    assert alamat_database() == "postgresql+psycopg://u:p@ep-x.neon.tech/db?sslmode=require"
    monkeypatch.setenv("TB_DATABASE_URL", "postgresql+psycopg://u:p@127.0.0.1:5433/db")
    assert alamat_database() == "postgresql+psycopg://u:p@127.0.0.1:5433/db"
