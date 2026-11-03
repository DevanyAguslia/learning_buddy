"""Akun pengguna, sesi login, dan riwayat percakapan (PostgreSQL).

Alamat database dibaca dari TB_DATABASE_URL (variabel lingkungan atau berkas .env di folder
proyek), misalnya:
    TB_DATABASE_URL=postgresql+psycopg://learningbuddy:SANDI@127.0.0.1:5433/learningbuddy
Tanpa alamat itu server berjalan tanpa login (dipakai server GPU di Kaggle dan pengujian).

Peran:
    siswa     chat saja
    guru      chat + Lab: Ukur teks dan Buku sekolah
    peneliti  chat + seluruh Lab (Evaluasi rumus dan Uji sistem)

Sekolah: guru membuat sekolah dan mendapat kode sekolah; siswa memasukkan kode itu saat
mendaftar, sehingga buku yang diunggah guru sekolahnya ikut dicari (tb.buku_sekolah).

Kata sandi disimpan sebagai hash scrypt (hashlib bawaan Python), token sesi disimpan sebagai
hash SHA-256 sehingga isi database tidak cukup untuk masuk sebagai pengguna lain.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import os
import re
import secrets

from sqlalchemy import (JSON, DateTime, ForeignKey, Integer, String, Text, create_engine,
                        func, inspect, or_, select, text)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship

AKAR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PERAN = {"siswa": "Siswa/Siswi SD", "guru": "Guru", "peneliti": "Peneliti"}
PERAN_LAB = {"guru", "peneliti"}          # Lab: Ukur teks
PERAN_PENELITI = {"peneliti"}             # Lab: Evaluasi rumus dan Uji sistem
UMUR_SESI = dt.timedelta(days=7)
NAMA_COOKIE = "lb_sesi"
_USERNAME = re.compile(r"^[A-Za-z0-9_.]{3,30}$")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _sekarang() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def alamat_database() -> str | None:
    """TB_DATABASE_URL dari lingkungan, atau dari berkas .env di folder proyek."""
    url = os.environ.get("TB_DATABASE_URL")
    p = os.path.join(AKAR, ".env")
    if not url and os.path.exists(p):
        for baris in open(p, encoding="utf-8"):
            k, _, v = baris.strip().partition("=")
            if k.strip() == "TB_DATABASE_URL" and v.strip():
                url = v.strip()
    # alamat salinan Neon/Supabase ("postgresql://..." atau "postgres://...") memakai psycopg 3
    if url and url.startswith(("postgresql://", "postgres://")):
        url = "postgresql+psycopg://" + url.split("://", 1)[1]
    return url or None


# --------------------------------------------------------------------------- tabel
class Dasar(DeclarativeBase):
    type_annotation_map = {dict: JSON, list: JSON}


class Sekolah(Dasar):
    __tablename__ = "sekolah"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nama: Mapped[str] = mapped_column(String(120))
    kode: Mapped[str] = mapped_column(String(8), unique=True, index=True)
    dibuat: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_sekarang)


class BukuSekolah(Dasar):
    """Buku unggahan guru. Berkasnya di tb.buku_sekolah.folder_buku(id)."""
    __tablename__ = "buku_sekolah"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sekolah_id: Mapped[int] = mapped_column(ForeignKey("sekolah.id", ondelete="CASCADE"), index=True)
    judul: Mapped[str] = mapped_column(String(200))
    penerbit: Mapped[str] = mapped_column(String(120), default="")
    mapel: Mapped[str] = mapped_column(String(10))
    kelas: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="antre")   # antre/diproses/siap/gagal
    pesan: Mapped[str | None] = mapped_column(Text, nullable=True)
    n_halaman: Mapped[int | None] = mapped_column(Integer, nullable=True)
    n_potongan: Mapped[int | None] = mapped_column(Integer, nullable=True)
    diunggah_oleh: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dibuat: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_sekarang)


class Pengguna(Dasar):
    __tablename__ = "pengguna"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    sandi: Mapped[str] = mapped_column(String(200))
    peran: Mapped[str] = mapped_column(String(20))
    sekolah_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    dibuat: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_sekarang)
    percakapan: Mapped[list["Percakapan"]] = relationship(back_populates="pengguna",
                                                          cascade="all, delete-orphan")


class Sesi(Dasar):
    __tablename__ = "sesi"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    pengguna_id: Mapped[int] = mapped_column(ForeignKey("pengguna.id", ondelete="CASCADE"), index=True)
    kedaluwarsa: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))


class Percakapan(Dasar):
    __tablename__ = "percakapan"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pengguna_id: Mapped[int] = mapped_column(ForeignKey("pengguna.id", ondelete="CASCADE"), index=True)
    judul: Mapped[str] = mapped_column(String(120))
    mapel: Mapped[str] = mapped_column(String(10))
    dibuat: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_sekarang)
    diperbarui: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_sekarang)
    pengguna: Mapped[Pengguna] = relationship(back_populates="percakapan")
    pesan: Mapped[list["Pesan"]] = relationship(back_populates="percakapan", order_by="Pesan.id",
                                                cascade="all, delete-orphan")


class Pesan(Dasar):
    """Satu pertanyaan beserta hasil lengkap sistem (dipakai ulang untuk menampilkan riwayat
    dan sebagai jejak pemakaian untuk analisis)."""
    __tablename__ = "pesan"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    percakapan_id: Mapped[int] = mapped_column(ForeignKey("percakapan.id", ondelete="CASCADE"), index=True)
    pertanyaan: Mapped[str] = mapped_column(Text)
    jawaban: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    skenario: Mapped[str] = mapped_column(String(4))
    kelas: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hasil: Mapped[dict] = mapped_column(JSON)
    dibuat: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_sekarang)
    percakapan: Mapped[Percakapan] = relationship(back_populates="pesan")


# --------------------------------------------------------------------------- sandi & token
def hash_sandi(sandi: str) -> str:
    garam = secrets.token_bytes(16)
    h = hashlib.scrypt(sandi.encode(), salt=garam, n=2 ** 14, r=8, p=1)
    return f"scrypt${garam.hex()}${h.hex()}"


def cocok_sandi(sandi: str, tersimpan: str) -> bool:
    try:
        _, garam, h = tersimpan.split("$")
    except ValueError:
        return False
    uji = hashlib.scrypt(sandi.encode(), salt=bytes.fromhex(garam), n=2 ** 14, r=8, p=1)
    return hmac.compare_digest(uji.hex(), h)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class GalatAkun(ValueError):
    """Pesan galat yang aman ditampilkan ke pengguna."""


# --------------------------------------------------------------------------- layanan
class Akun:
    def __init__(self, url: str):
        kw = {"connect_args": {"check_same_thread": False}} if url.startswith("sqlite") else \
            {"pool_pre_ping": True}
        self.engine = create_engine(url, **kw)
        Dasar.metadata.create_all(self.engine)
        # database lama (sebelum fitur buku sekolah) belum punya kolom pengguna.sekolah_id
        if "sekolah_id" not in {c["name"] for c in inspect(self.engine).get_columns("pengguna")}:
            with self.engine.begin() as c:
                c.execute(text("ALTER TABLE pengguna ADD COLUMN sekolah_id INTEGER"))

    def sesi(self) -> Session:
        return Session(self.engine, expire_on_commit=False)

    @staticmethod
    def publik(p: Pengguna) -> dict:
        return {"id": p.id, "username": p.username, "email": p.email, "peran": p.peran,
                "nama_peran": PERAN[p.peran], "boleh_lab": p.peran in PERAN_LAB,
                "boleh_lab_penuh": p.peran in PERAN_PENELITI, "sekolah_id": p.sekolah_id}

    # --- daftar / masuk / keluar
    def daftar(self, username: str, email: str, sandi: str, peran: str,
               kode_sekolah: str = "") -> Pengguna:
        username, email = username.strip(), email.strip().lower()
        if not _USERNAME.match(username):
            raise GalatAkun("Username 3-30 karakter, hanya huruf, angka, titik, atau garis bawah.")
        if not _EMAIL.match(email):
            raise GalatAkun("Alamat email belum benar.")
        if len(sandi) < 8:
            raise GalatAkun("Password paling sedikit 8 karakter.")
        if peran not in PERAN:
            raise GalatAkun("Pilih salah satu: Siswa/Siswi SD, Guru, atau Peneliti.")
        with self.sesi() as s:
            ada = s.scalars(select(Pengguna).where(or_(func.lower(Pengguna.username) == username.lower(),
                                                       Pengguna.email == email))).first()
            if ada:
                raise GalatAkun("Username sudah dipakai." if ada.username.lower() == username.lower()
                                else "Email sudah terdaftar.")
            sekolah = self._sekolah_kode(s, kode_sekolah) if kode_sekolah.strip() else None
            p = Pengguna(username=username, email=email, sandi=hash_sandi(sandi), peran=peran,
                         sekolah_id=sekolah.id if sekolah else None)
            s.add(p)
            s.commit()
            return p

    def masuk(self, identitas: str, sandi: str) -> tuple[Pengguna, str]:
        """identitas = username ATAU email. Mengembalikan pengguna dan token sesi baru."""
        identitas = identitas.strip()
        with self.sesi() as s:
            p = s.scalars(select(Pengguna).where(or_(func.lower(Pengguna.username) == identitas.lower(),
                                                     Pengguna.email == identitas.lower()))).first()
            if not p or not cocok_sandi(sandi, p.sandi):
                raise GalatAkun("Username/email atau password salah.")
            token = secrets.token_urlsafe(32)
            s.add(Sesi(token_hash=_hash_token(token), pengguna_id=p.id,
                       kedaluwarsa=_sekarang() + UMUR_SESI))
            s.commit()
            return p, token

    def pengguna_dari_token(self, token: str | None) -> Pengguna | None:
        if not token:
            return None
        with self.sesi() as s:
            ss = s.get(Sesi, _hash_token(token))
            if not ss:
                return None
            kd = ss.kedaluwarsa if ss.kedaluwarsa.tzinfo else ss.kedaluwarsa.replace(tzinfo=dt.timezone.utc)
            if kd < _sekarang():
                s.delete(ss)
                s.commit()
                return None
            return s.get(Pengguna, ss.pengguna_id)

    def keluar(self, token: str | None) -> None:
        if not token:
            return
        with self.sesi() as s:
            ss = s.get(Sesi, _hash_token(token))
            if ss:
                s.delete(ss)
                s.commit()

    # --- sekolah
    @staticmethod
    def _sekolah_kode(s: Session, kode: str) -> Sekolah:
        sk = s.scalars(select(Sekolah).where(Sekolah.kode == kode.strip().upper())).first()
        if not sk:
            raise GalatAkun("Kode sekolah tidak ditemukan. Tanyakan kode yang benar ke guru.")
        return sk

    @staticmethod
    def _sekolah_dict(sk: Sekolah | None) -> dict | None:
        return {"id": sk.id, "nama": sk.nama, "kode": sk.kode} if sk else None

    def buat_sekolah(self, pengguna_id: int, nama: str) -> dict:
        nama = re.sub(r"\s+", " ", nama).strip()
        if not 3 <= len(nama) <= 120:
            raise GalatAkun("Nama sekolah 3-120 karakter.")
        huruf = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"        # tanpa 0/O dan 1/I yang mirip
        with self.sesi() as s:
            while True:
                kode = "".join(secrets.choice(huruf) for _ in range(6))
                if not s.scalars(select(Sekolah).where(Sekolah.kode == kode)).first():
                    break
            sk = Sekolah(nama=nama, kode=kode)
            s.add(sk)
            s.flush()
            s.get(Pengguna, pengguna_id).sekolah_id = sk.id
            s.commit()
            return self._sekolah_dict(sk)

    def gabung_sekolah(self, pengguna_id: int, kode: str) -> dict:
        with self.sesi() as s:
            sk = self._sekolah_kode(s, kode)
            s.get(Pengguna, pengguna_id).sekolah_id = sk.id
            s.commit()
            return self._sekolah_dict(sk)

    def sekolah(self, sekolah_id: int | None) -> dict | None:
        if not sekolah_id:
            return None
        with self.sesi() as s:
            return self._sekolah_dict(s.get(Sekolah, sekolah_id))

    # --- buku sekolah
    @staticmethod
    def _buku_dict(b: BukuSekolah) -> dict:
        return {"id": b.id, "sekolah": b.sekolah_id, "judul": b.judul, "penerbit": b.penerbit,
                "mapel": b.mapel, "kelas": b.kelas, "status": b.status, "pesan": b.pesan,
                "n_halaman": b.n_halaman, "n_potongan": b.n_potongan,
                "dibuat": b.dibuat.isoformat() if b.dibuat else None}

    def tambah_buku(self, sekolah_id: int, pengguna_id: int, judul: str, penerbit: str,
                    mapel: str, kelas: int) -> dict:
        with self.sesi() as s:
            b = BukuSekolah(sekolah_id=sekolah_id, judul=judul, penerbit=penerbit, mapel=mapel,
                            kelas=kelas, diunggah_oleh=pengguna_id)
            s.add(b)
            s.commit()
            return self._buku_dict(b)

    def ubah_buku(self, buku_id: int, **kolom) -> None:
        with self.sesi() as s:
            b = s.get(BukuSekolah, buku_id)
            if b:
                for k, v in kolom.items():
                    setattr(b, k, v)
                s.commit()

    def buku(self, buku_id: int) -> dict | None:
        with self.sesi() as s:
            b = s.get(BukuSekolah, buku_id)
            return self._buku_dict(b) if b else None

    def daftar_buku(self, sekolah_id: int | None = None, status: str | None = None) -> list[dict]:
        with self.sesi() as s:
            q = select(BukuSekolah).order_by(BukuSekolah.id)
            if sekolah_id is not None:
                q = q.where(BukuSekolah.sekolah_id == sekolah_id)
            if status:
                q = q.where(BukuSekolah.status == status)
            return [self._buku_dict(b) for b in s.scalars(q).all()]

    def hapus_buku(self, buku_id: int, sekolah_id: int) -> bool:
        with self.sesi() as s:
            b = s.get(BukuSekolah, buku_id)
            if b is None or b.sekolah_id != sekolah_id:
                return False
            s.delete(b)
            s.commit()
            return True

    # --- riwayat percakapan
    def simpan_pesan(self, pengguna_id: int, percakapan_id: int | None, mapel: str,
                     pertanyaan: str, skenario: str, hasil: dict) -> int:
        with self.sesi() as s:
            c = s.get(Percakapan, percakapan_id) if percakapan_id else None
            if c is None or c.pengguna_id != pengguna_id:
                c = Percakapan(pengguna_id=pengguna_id, judul=pertanyaan[:120], mapel=mapel)
                s.add(c)
                s.flush()
            c.diperbarui = _sekarang()
            s.add(Pesan(percakapan_id=c.id, pertanyaan=pertanyaan, jawaban=hasil.get("jawaban"),
                        status=hasil.get("status"), skenario=skenario, kelas=hasil.get("kelas"),
                        hasil=hasil))
            s.commit()
            return c.id

    def daftar_percakapan(self, pengguna_id: int, batas: int = 50) -> list[dict]:
        with self.sesi() as s:
            rows = s.scalars(select(Percakapan).where(Percakapan.pengguna_id == pengguna_id)
                             .order_by(Percakapan.diperbarui.desc()).limit(batas)).all()
            return [{"id": c.id, "judul": c.judul, "mapel": c.mapel,
                     "diperbarui": c.diperbarui.isoformat()} for c in rows]

    def isi_percakapan(self, pengguna_id: int, percakapan_id: int) -> dict | None:
        with self.sesi() as s:
            c = s.get(Percakapan, percakapan_id)
            if c is None or c.pengguna_id != pengguna_id:
                return None
            return {"id": c.id, "judul": c.judul, "mapel": c.mapel,
                    "pesan": [{"pertanyaan": m.pertanyaan, "skenario": m.skenario, "hasil": m.hasil,
                               "dibuat": m.dibuat.isoformat()} for m in c.pesan]}

    def hapus_percakapan(self, pengguna_id: int, percakapan_id: int) -> bool:
        with self.sesi() as s:
            c = s.get(Percakapan, percakapan_id)
            if c is None or c.pengguna_id != pengguna_id:
                return False
            s.delete(c)
            s.commit()
            return True


def buka_akun() -> Akun | None:
    url = alamat_database()
    return Akun(url) if url else None
