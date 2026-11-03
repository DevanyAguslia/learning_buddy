"use strict";

const $ = (s) => document.querySelector(s);

function tampilkanPesan(teks, galat = true) {
  const p = $("#pesan-masuk");
  p.hidden = !teks;
  p.textContent = teks || "";
  p.classList.toggle("galat", galat);
}

function pilihTab(nama) {
  const daftar = nama === "daftar";
  $("#tab-masuk").setAttribute("aria-selected", String(!daftar));
  $("#tab-daftar").setAttribute("aria-selected", String(daftar));
  $("#form-masuk").hidden = daftar;
  $("#form-daftar").hidden = !daftar;
  tampilkanPesan(null);
  (daftar ? $("input[name=peran]") : $("#masuk-identitas")).focus();
}

async function kirimAkun(alamat, badan, tombol) {
  tombol.disabled = true;
  tampilkanPesan(null);
  try {
    const r = await fetch(alamat, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(badan),
    });
    const isi = await r.json().catch(() => ({}));
    if (!r.ok) {
      const d = isi.detail;
      throw new Error(Array.isArray(d) ? "Isian belum lengkap atau belum benar." : d || `server menjawab ${r.status}`);
    }
    location.href = "/";
  } catch (e) {
    tampilkanPesan(e.message);
    tombol.disabled = false;
  }
}

$("#form-masuk").addEventListener("submit", (e) => {
  e.preventDefault();
  kirimAkun("/api/masuk", {
    identitas: $("#masuk-identitas").value.trim(), password: $("#masuk-password").value,
  }, e.submitter);
});

$("#form-daftar").addEventListener("submit", (e) => {
  e.preventDefault();
  const peran = document.querySelector("input[name=peran]:checked");
  if (!peran) { tampilkanPesan("Pilih dulu: Siswa/Siswi SD, Guru, atau Peneliti."); return; }
  kirimAkun("/api/daftar", {
    username: $("#daftar-username").value.trim(), email: $("#daftar-email").value.trim(),
    password: $("#daftar-password").value, peran: peran.value,
    kode_sekolah: $("#daftar-kode-sekolah").value.trim().toUpperCase(),
    kode_peran: $("#daftar-kode-peran").value,
  }, e.submitter);
});

$("#tab-masuk").addEventListener("click", () => pilihTab("masuk"));
$("#tab-daftar").addEventListener("click", () => pilihTab("daftar"));
document.querySelectorAll("[data-ke]").forEach((b) => b.addEventListener("click", () => pilihTab(b.dataset.ke)));

// guru/peneliti perlu kode pendaftaran bila server memintanya
let perluKode = {};
function aturKodePeran() {
  const peran = document.querySelector("input[name=peran]:checked")?.value;
  $("#isian-kode-peran").hidden = !perluKode[peran];
}
document.querySelectorAll("input[name=peran]").forEach((r) => r.addEventListener("change", aturKodePeran));

// login belum aktif (database belum disambungkan): beri tahu dengan jelas
fetch("/api/saya").then((r) => r.json()).then((s) => {
  perluKode = s.perlu_kode_peran || {};
  aturKodePeran();
  if (!s.login_aktif) tampilkanPesan("Database akun belum tersambung, jadi login belum bisa dipakai. Hubungi peneliti.");
  else if (s.masuk) location.href = "/";
}).catch(() => tampilkanPesan("Server tidak dapat dihubungi."));
if (location.hash === "#daftar") pilihTab("daftar");
