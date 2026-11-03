"use strict";

// ---------------------------------------------------------------------------
// Pengaturan server. Kosong berarti server yang sama dengan halaman ini.
// Bisa diisi lewat ?api=https://... atau dialog "Atur alamat server".
// ---------------------------------------------------------------------------
const simpan = {
  ambil(k) { try { return localStorage.getItem(k) || ""; } catch { return ""; } },
  taruh(k, v) { try { v ? localStorage.setItem(k, v) : localStorage.removeItem(k); } catch {} },
};
const qs = new URLSearchParams(location.search);
if (qs.get("api")) simpan.taruh("tb_api", qs.get("api").replace(/\/+$/, ""));
let API = simpan.ambil("tb_api");
let KUNCI = simpan.ambil("tb_kunci");

const CONTOH = {
  PJOK: ["napa hrs pemanasan dlu sblm olhraga?", "Bagaimana cara melakukan gerakan menekuk?",
         "Sepak bola dimainkan oleh berapa orang?"],
  PKN: ["apa arti gotong royong", "Apa saja sila dalam Pancasila?", "Apa yang dimaksud dengan hak?"],
};
// Empat cara menjawab = skenario S1-S4 penelitian, dengan nama yang mudah dipahami
const CARA = {
  S1: { ikon: "⚡", nama: "Jawab Cepat", ket: "langsung dijawab" },
  S2: { ikon: "🎒", nama: "Sesuai Kelasku", ket: "bahasanya pas untuk kelasmu" },
  S3: { ikon: "📖", nama: "Lihat Buku", ket: "dicari dulu di buku pelajaran" },
  S4: { ikon: "⭐", nama: "Paling Lengkap", ket: "lihat buku + sesuai kelasku" },
};
const URUTAN_CARA = ["S4", "S3", "S2", "S1"];
// Empat agen yang ditampilkan saat Learning Buddy bekerja
const AGEN = [
  { kunci: "perceive", ikon: "👂", nama: "Memahami", warna: "biru" },
  { kunci: "plan", ikon: "🧭", nama: "Menentukan kelas", warna: "ungu" },
  { kunci: "act", ikon: "📚", nama: "Menyusun jawaban", warna: "hijau" },
  { kunci: "reflect", ikon: "✅", nama: "Memeriksa bahasa", warna: "kuning" },
];
// maskot: burung hantu bertopi wisuda dengan buku dan pensil (web/maskot.svg)
function gambarMaskot() {
  const img = el("img"); img.src = "maskot.svg"; img.alt = ""; return img;
}

const $ = (s) => document.querySelector(s);
const el = (tag, cls, teks) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (teks !== undefined && teks !== null) e.textContent = teks;
  return e;
};
const angka = (x, d = 1) => (x === null || x === undefined) ? "-" :
  Number(x).toLocaleString("id-ID", { minimumFractionDigits: d, maximumFractionDigits: d });

const keadaan = { mapel: "PJOK", sibuk: false, info: null, sehat: null, saya: null,
                  loginAktif: false, percakapan: null, tanyaBalik: 0 };
// sesudah 3 kali bertanya balik berturut-turut, pertanyaan berikutnya langsung dijawab
const MAKS_TANYA_BALIK = 3;

// ---------------------------------------------------------------------------
// Akun: siapa yang masuk, hak akses, keluar
// ---------------------------------------------------------------------------
async function cekAkun() {
  try {
    const s = await fetch(`${API}/api/saya`, { credentials: "include" }).then((r) => r.json());
    keadaan.loginAktif = s.login_aktif;
    if (s.login_aktif && !s.masuk) { location.href = "masuk.html"; return false; }
    keadaan.saya = s.pengguna;
    keadaan.sekolah = s.sekolah;
  } catch { /* server tidak terjangkau: ditangani sapaServer */ }
  const p = keadaan.saya;
  const bolehLab = !keadaan.loginAktif || p?.boleh_lab;
  $("#tautan-lab").hidden = !bolehLab;
  $("#panel-peneliti").hidden = !bolehLab;
  $("#panel-riwayat").hidden = !keadaan.loginAktif;
  if (p) {
    $("#akun-saya").hidden = false;
    $("#nama-saya").textContent = p.username;
    $("#peran-saya").textContent = `· ${p.nama_peran}`;
    $("#sekolah-saya").textContent = keadaan.sekolah ? `· 🏫 ${keadaan.sekolah.nama}` : "";
    $("#tombol-sekolah").hidden = !!keadaan.sekolah;
  }
  return true;
}

// siswa yang belum memasukkan kode sekolah saat mendaftar: buku sekolahnya ikut dicari
$("#tombol-sekolah").addEventListener("click", async () => {
  const kode = (prompt("Masukkan kode sekolah dari gurumu:") || "").trim().toUpperCase();
  if (!kode) return;
  const r = await fetch(`${API}/api/sekolah/gabung`, {
    method: "POST", credentials: "include", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ kode }) }).catch(() => null);
  const isi = r ? await r.json().catch(() => ({})) : {};
  if (!r || !r.ok) { alert(typeof isi.detail === "string" ? isi.detail : "Kode sekolah belum bisa dipakai."); return; }
  keadaan.sekolah = isi.sekolah;
  $("#sekolah-saya").textContent = `· 🏫 ${isi.sekolah.nama}`;
  $("#tombol-sekolah").hidden = true;
});

$("#tombol-keluar").addEventListener("click", async () => {
  await fetch(`${API}/api/keluar`, { method: "POST", credentials: "include" }).catch(() => {});
  location.href = "masuk.html";
});

// ---------------------------------------------------------------------------
// Pilihan cara menjawab
// ---------------------------------------------------------------------------
function pasangCara() {
  const tersimpan = simpan.ambil("tb_cara");
  const pilih = CARA[tersimpan] ? tersimpan : "S4";
  const wadah = $("#cara-jawab");
  for (const s of URUTAN_CARA) {
    const c = CARA[s];
    const l = el("label", "pil-cara");
    const r = el("input");
    r.type = "radio"; r.name = "cara"; r.value = s; r.checked = s === pilih;
    r.addEventListener("change", () => simpan.taruh("tb_cara", s));
    l.append(r, el("span", "ikon-cara", c.ikon), el("span", "", c.nama), el("span", "ket-cara", `(${c.ket})`));
    l.title = c.ket;
    wadah.append(l);
  }
}
const caraTerpilih = () => document.querySelector("input[name=cara]:checked")?.value || "S4";
const namaCara = (s) => CARA[s] ? `${CARA[s].ikon} ${CARA[s].nama}` : s;

// ---------------------------------------------------------------------------
// Koneksi
// ---------------------------------------------------------------------------
function kepalaHttp() {
  const h = { "Content-Type": "application/json" };
  if (KUNCI) h["X-Kunci"] = KUNCI;
  return h;
}

async function sapaServer() {
  const titik = $("#titik-status");
  try {
    const [s, i] = await Promise.all([
      fetch(`${API}/api/sehat`).then((r) => r.json()),
      fetch(`${API}/api/info`).then((r) => r.json()),
    ]);
    keadaan.sehat = s; keadaan.info = i;
    titik.className = "titik hidup";
    $("#info-server").textContent =
      `server : ${API || location.origin}\nmode   : ${s.mode}\nmodel  : ${s.model}\n` +
      `cari   : ${s.pencarian}\nadapter: ${s.adapter.length ? s.adapter.length + " tingkat kelas" : "tidak ada"}` +
      `\ndaftar : pencocokan ${i.pencocokan}`;
    if (s.mode === "tiruan") {
      pita("Mode uji tampilan: AI belum dinyalakan, jadi jawaban disalin dari kalimat buku. Gunakan untuk mencoba tampilan saja.");
    } else pita(null);
  } catch (e) {
    titik.className = "titik mati";
    $("#info-server").textContent = `Server ${API || location.origin} tidak dapat dihubungi.`;
    pita("Server belum tersambung. Coba muat ulang halaman, atau hubungi guru/peneliti.", true);
  }
}

function pita(pesan, galat = false) {
  const p = $("#pita");
  p.hidden = !pesan;
  p.textContent = pesan || "";
  p.classList.toggle("galat", galat);
}

// ---------------------------------------------------------------------------
// Mata pelajaran dan tingkat kelas
// ---------------------------------------------------------------------------
function gantiMapel(m) {
  keadaan.mapel = m;
  document.querySelectorAll(".pengalih button").forEach((b) =>
    b.setAttribute("aria-checked", String(b.dataset.mapel === m)));
  $("#label-mapel").textContent = m === "PKN" ? "Pancasila" : "PJOK";
  const sm = $("#sambutan-mapel");
  if (sm) sm.textContent = m === "PKN" ? "Pancasila" : "PJOK";
  isiContoh();
}

function isiContoh() {
  const c = $("#contoh");
  if (!c) return;
  c.replaceChildren(...CONTOH[keadaan.mapel].map((t) => {
    const b = el("button", "", t);
    b.type = "button";
    b.addEventListener("click", () => { $("#tanya").value = t; kirim(); });
    return b;
  }));
}

function tampilkanJenjang(kelas, sumber) {
  const pilih = $("#pilih-kelas");
  const otomatis = pilih.value === "";
  $("#jenjang-label").textContent = otomatis ? (kelas ? "Terdeteksi" : "Kelas") : "Dipilih";
  pilih.options[0].textContent = otomatis && kelas ? `Kelas ${kelas}` : "Otomatis";
  pilih.title = sumber === "Plan Agent"
    ? "Tingkat kelas ditebak otomatis dari pertanyaan. Pilih kelas lain bila keliru."
    : "Tingkat kelas dipilih sendiri.";
}

// ---------------------------------------------------------------------------
// Percakapan
// ---------------------------------------------------------------------------
function gulirBawah() { const p = $("#pesan"); p.scrollTop = p.scrollHeight; }

function tambahTanya(teks) {
  $("#sambutan")?.remove();
  const w = el("div", "tanya-siswa");
  w.append(el("div", "gelembung", teks));
  const dibaca = el("div", "dibaca");
  w.append(dibaca);
  $("#pesan").append(w);
  gulirBawah();
  return dibaca;
}

// ---------------------------------------------------------------------------
// Alur kerja agen: gambaran langsung apa yang sedang dikerjakan setiap agen
// ---------------------------------------------------------------------------
const pakaiBuku = (s) => ["S3", "S4"].includes(s);

function buatAlur(skenario) {
  const box = el("details", "alur");
  box.open = true;
  const ringkas = el("summary", "alur-ringkas");
  const judul = el("span", "alur-judul", "Learning Buddy sedang berpikir…");
  const ikon = el("span", "alur-ikon"); ikon.append(gambarMaskot());
  ringkas.append(ikon, judul);
  const jalur = el("ol", "alur-jalur");
  const node = {};
  for (const a of AGEN) {
    const li = el("li", `agen ${a.warna}`);
    const ket = el("span", "agen-ket", "menunggu");
    li.append(el("span", "agen-bulat", a.ikon), el("span", "agen-nama", a.nama), ket);
    jalur.append(li);
    node[a.kunci] = { li, ket, warna: a.warna };
  }
  const log = el("ul", "alur-log");
  box.append(ringkas, jalur, log);
  $("#pesan").append(box);
  const alur = { box, judul, node, log, mulai: performance.now(), skenario, putaran: 0 };
  setelAgen(alur, "perceive", "jalan", "membaca pertanyaanmu…");
  gulirBawah();
  return alur;
}

function setelAgen(alur, kunci, status, ket) {
  const n = alur.node[kunci];
  n.li.className = `agen ${n.warna} ${status}`;
  if (ket) n.ket.textContent = ket;
}

function catatAlur(alur, ikon, teks) {
  const li = el("li");
  li.append(el("span", "log-ikon", ikon), el("span", "", teks));
  alur.log.append(li);
  gulirBawah();
}

function alurPerceive(alur, isi) {
  setelAgen(alur, "perceive", "beres", "sudah dipahami");
  catatAlur(alur, "👂", `Pertanyaan dibaca sebagai: “${isi.pertanyaan_bersih}”`);
  if (isi.jelas === false) {
    setelAgen(alur, "perceive", "ulang", "belum jelas");
    return;
  }
  setelAgen(alur, "plan", "jalan", "mencari kelas yang pas…");
}

function alurPlan(alur, isi) {
  const otomatis = isi.sumber_kelas === "Plan Agent";
  setelAgen(alur, "plan", "beres", `kelas ${isi.kelas}`);
  catatAlur(alur, "🧭", otomatis
    ? `Tingkat kelas ditebak: kelas ${isi.kelas} (yakin ${Math.round(100 * (isi.keyakinan_kelas || 0))}%)`
    : `Tingkat kelas dipilih sendiri: kelas ${isi.kelas}`);
  if (isi.perlu_konfirmasi) {
    setelAgen(alur, "plan", "ulang", "perlu kamu pilih");
    return;
  }
  setelAgen(alur, "act", "jalan", pakaiBuku(alur.skenario) ? "membuka buku pelajaran…" : "menulis jawaban…");
}

function alurAct(alur, isi) {
  if (isi.tidak_ada_materi) {
    setelAgen(alur, "act", "ulang", "materi tidak ada di buku");
    catatAlur(alur, "📚", "Materinya tidak ditemukan di buku pelajaranmu, jadi aku tidak mengarang jawaban.");
    return;
  }
  alur.putaran = isi.putaran || alur.putaran + 1;
  const kon = isi.konteks;
  if (alur.putaran === 1 && kon) {
    const n = kon.potongan?.length || 1;
    catatAlur(alur, "📖", `Membaca ${n} potongan dari ${kon.buku}`);
  } else if (alur.putaran === 1 && !pakaiBuku(alur.skenario)) {
    catatAlur(alur, "💭", "Menjawab tanpa membuka buku (sesuai cara yang kamu pilih)");
  }
  setelAgen(alur, "act", "beres", alur.putaran > 1 ? `ditulis ulang (ke-${alur.putaran})` : "jawaban ditulis");
  catatAlur(alur, "✏️", alur.putaran > 1 ? `Jawaban ditulis ulang, putaran ${alur.putaran}`
                                         : "Jawaban pertama selesai ditulis");
  setelAgen(alur, "reflect", "jalan", "mengecek bahasanya…");
}

function alurReflect(alur, isi) {
  const p = isi.pemeriksaan || {};
  const u = p.ukuran || {}, s = p.sasaran || {};
  const angkaUkur = `${angka(u.pkr)} kata/kalimat (batas ${angka(s.maks_pkr)}), ${angka(u.kld, 0)}% kata sulit (batas ${angka(s.maks_kld, 0)}%)`;
  if (p.lolos) {
    setelAgen(alur, "reflect", "beres", "bahasanya pas");
    catatAlur(alur, "✅", `Bahasanya pas: ${angkaUkur}`);
    return;
  }
  const alasan = p.relevan === false ? "jawaban belum menjawab pertanyaan" : `masih agak sulit: ${angkaUkur}`;
  const maks = keadaan.info?.maks_putaran || 3;
  if (alur.putaran < maks) {
    setelAgen(alur, "reflect", "ulang", "perlu disederhanakan");
    catatAlur(alur, "🔁", `Putaran ${alur.putaran}: ${alasan}, jadi ditulis ulang`);
    setelAgen(alur, "act", "jalan", `menulis ulang (ke-${alur.putaran + 1})…`);
  } else {
    setelAgen(alur, "reflect", "ulang", "batas putaran habis");
    catatAlur(alur, "⏱️", `Putaran ${alur.putaran}: ${alasan}. Dipilih jawaban yang paling mendekati.`);
  }
}

function tutupAlur(alur, h) {
  const detik = ((performance.now() - alur.mulai) / 1000).toLocaleString("id-ID", { maximumFractionDigits: 1 });
  const judul = {
    tolak: "Pertanyaannya belum jelas",
    tanya_balik: "Learning Buddy bertanya balik dulu",
    konfirmasi_kelas: "Learning Buddy menanyakan kelasmu dulu",
    tidak_ada_materi: "Materinya tidak ada di buku",
  }[h.status] || `Selesai · ${h.putaran || alur.putaran || 1} putaran · ${detik} detik`;
  alur.judul.textContent = judul;
  alur.box.classList.add("selesai");
  for (const a of AGEN) {
    const n = alur.node[a.kunci];
    if (n.li.classList.contains("jalan")) setelAgen(alur, a.kunci, "", "dilewati");
  }
  alur.box.open = false;
}

// Bubble Learning Buddy: avatar maskot + kartu
function denganAvatar(kartu) {
  const w = el("div", "baris-jawaban");
  const av = el("div", "avatar"); av.append(gambarMaskot());
  w.append(av, kartu);
  return w;
}

function kartuJawaban(h) {
  const tanpa = h.status === "tidak_ada_materi";
  const k = el("div", "jawaban" + (h.status === "tolak" || tanpa ? " tolak" : ""));
  k.append(el("p", "jawaban-teks", h.jawaban || "(jawaban kosong)"));
  if (h.status === "tolak") return k;
  if (tanpa) {
    k.append(el("div", "chip-chip", ""));
    k.lastChild.append(el("span", "chip abu", "Act Agent: tidak ada potongan buku yang cocok, jadi tidak menebak jawaban"));
    return k;
  }

  const chip = el("div", "chip-chip");
  if (String(keadaan.sehat?.mode || "").includes("tiruan")) {
    k.classList.add("tiruan");
    chip.append(el("span", "chip belum", "Mode uji tampilan: kalimat ini disalin dari buku, belum disusun AI"));
  }
  const u = h.ukuran || {};
  // siswa melihat label sederhana; angka keterbacaan untuk guru/peneliti (dan di Jejak pemeriksaan)
  const teknis = !keadaan.saya || keadaan.saya.peran !== "siswa";
  if (h.relevan === false) chip.append(el("span", "chip belum", "Reflect: jawaban belum tentu menjawab pertanyaan, periksa lagi"));
  if (h.konteks_lintas_kelas) chip.append(el("span", "chip abu", `materi diambil dari buku kelas ${h.konteks?.kelas}`));
  chip.append(h.lolos
    ? el("span", "chip sesuai", `✅ Sesuai kelas ${h.kelas}`)
    : el("span", "chip belum", `⚠️ Belum sesuai kelas ${h.kelas}`));
  const kon = h.konteks;
  if (kon) {
    const p0 = kon.potongan?.[0] || kon;
    const hal = p0.halaman_buku ?? p0.halaman;
    chip.append(el("span", "chip buku", `📚 ${kon.buku}${hal != null ? `, hal. ${hal}` : ""}`));
  }
  if (teknis) {
    chip.append(el("span", "chip", `${angka(u.pkr)} kata/kalimat`));
    chip.append(el("span", "chip", `${angka(u.kld, 0)}% kata di luar daftar dasar`));
    const ulang = (h.putaran || 1) - 1;
    chip.append(el("span", "chip", ulang ? `${ulang} putaran penyederhanaan` : "tanpa penyederhanaan"));
    const pakaiAdapter = ["S2", "S4"].includes(h.skenario);
    if (pakaiAdapter && !h.adapter_aktif) chip.append(el("span", "chip abu", `latihan khusus kelas ${h.kelas} belum ada, AI biasa yang menjawab`));
  }
  if (h.skenario) chip.append(el("span", "chip abu", namaCara(h.skenario)));
  k.append(chip);
  return k;
}

// ---------------------------------------------------------------------------
// Panel samping
// ---------------------------------------------------------------------------
// Panel lipat: lencana kecil memberi tahu ada isi baru walau panel tertutup
function lencana(id, teks) {
  const l = $(`#lencana-${id}`);
  l.textContent = teks || "";
  const d = $(`#lipat-${id}`);
  d.classList.remove("baru");
  if (teks && !d.open) { void d.offsetWidth; d.classList.add("baru"); }
}

function tampilkanSumber(h) {
  const s = $("#sumber");
  s.className = "";
  const daftarPotongan = h.konteks ? (h.konteks.potongan?.length || 1) : 0;
  lencana("sumber", daftarPotongan ? `${daftarPotongan} potongan` : "");
  if (["tolak", "tanya_balik", "konfirmasi_kelas"].includes(h.status)) {
    s.className = "kosong"; s.textContent = "Pertanyaan belum dijawab."; return;
  }
  if (h.status === "tidak_ada_materi") {
    s.className = "kosong";
    s.textContent = "Potongan buku teratas tidak cukup mirip dengan pertanyaan (pengecekan 1), di kelas ini maupun kelas lain.";
    return;
  }
  const kon = h.konteks;
  if (!kon) {
    s.className = "kosong";
    s.textContent = ["S1", "S2"].includes(h.skenario)
      ? `Cara "${CARA[h.skenario].nama}" menjawab tanpa membuka buku.`
      : "Tidak ada potongan buku yang cocok untuk pertanyaan ini.";
    return;
  }
  const buku = el("div", "buku");
  buku.append(el("div", "buku-judul", kon.buku));
  // riwayat lama hanya punya satu potongan tanpa daftar "potongan"
  const daftar = kon.potongan?.length ? kon.potongan
    : [{ id: kon.id, kelas: kon.kelas, halaman: kon.halaman, halaman_buku: kon.halaman_buku,
         bab: kon.bab, strategi: kon.strategi, skor: h.skor_konteks, teks: kon.teks }];
  buku.append(el("div", "buku-meta",
    `Kelas ${kon.kelas} · ${daftar.length} potongan buku dipakai untuk menjawab`));
  const isi = [buku];
  daftar.forEach((p, i) => {
    const hal = p.halaman_buku != null ? `halaman ${p.halaman_buku} (PDF ${p.halaman})` : `halaman PDF ${p.halaman}`;
    const meta = [`Potongan ${i + 1}`, hal];
    if (p.bab) meta.push(p.bab);
    isi.push(el("div", "buku-meta", meta.join(" · ")));
    isi.push(el("blockquote", "kutipan", `"${p.teks}"`));
    const skor = p.skor != null ? ` · skor ${angka(p.skor, 2)}` : "";
    isi.push(el("div", "metode", `${p.strategi || "-"} · ${p.id}${skor}`));
  });
  isi.push(el("div", "metode", h.metode_cari || ""));
  if (h.konteks_lintas_kelas) isi.unshift(el("div", "catatan",
    `Materi ini tidak ditemukan di buku kelas ${h.kelas}, jadi diambil dari buku kelas ${kon.kelas}.`));
  s.replaceChildren(...isi);
}

// Asal-usul penetapan kelas oleh Plan Agent: tebakan model dan letak materi di buku
function liPlan(h) {
  if (!h.kelas) return null;
  const li = el("li", "plan");
  li.append(el("span", "nomor", "P"));
  const isi = el("div");
  if (h.sumber_kelas === "pengguna") {
    isi.append(el("div", "jejak-judul", `Kelas ${h.kelas}, dipilih siswa`));
  } else {
    isi.append(el("div", "jejak-judul", `Plan Agent: kelas ${h.kelas} (yakin ${Math.round(100 * (h.keyakinan_kelas || 0))}%)`));
    const teratas = (p) => p && Object.keys(p).length
      ? Object.entries(p).sort((a, b) => b[1] - a[1]).slice(0, 2).map(([k, v]) => `kelas ${k} ${Math.round(100 * v)}%`).join(", ")
      : "-";
    const u = el("div", "jejak-ukur");
    u.append(`tebakan model: ${teratas(h.sebaran_llm)}`, document.createElement("br"),
      `letak materi di buku: ${teratas(h.sebaran_buku)}`);
    isi.append(u);
    if (h.bukti_kelas?.length) isi.append(el("div", "jejak-jawab",
      "bukti: " + h.bukti_kelas.map((b) => b.id).join(", ")));
  }
  li.append(isi);
  return li;
}

function tampilkanJejak(h) {
  const ol = $("#jejak");
  ol.className = "jejak";
  lencana("jejak", h.riwayat?.length ? `${h.riwayat.length} putaran` : "");
  const plan = liPlan(h);
  if (!h.riwayat?.length) {
    const pesan = {
      tolak: "Perceive Agent menilai masukan ini belum berupa pertanyaan yang jelas.",
      tanya_balik: "Perceive Agent belum yakin maksudnya, jadi bertanya balik dulu.",
      konfirmasi_kelas: "Plan Agent ragu menentukan kelas, jadi bertanya dulu sebelum menjawab.",
      tidak_ada_materi: "Act Agent tidak menemukan materi yang cocok di buku, jadi tidak membuat jawaban.",
    }[h.status] || "Belum ada putaran.";
    ol.replaceChildren(...[plan, el("li", "kosong", pesan)].filter(Boolean));
    return;
  }
  ol.replaceChildren(...[plan].filter(Boolean), ...h.riwayat.map((r) => {
    const li = el("li", (r.lolos ? "lolos" : "") + (r.putaran === h.putaran_terpilih ? " terpilih" : ""));
    li.append(el("span", "nomor", String(r.putaran)));
    const isi = el("div");
    let judul = r.lolos ? "Lolos, jawaban ditampilkan"
      : r.relevan === false ? "Tidak menjawab pertanyaan, ditulis ulang dari buku"
      : "Belum sesuai tingkat kelas";
    if (!r.lolos && ["batas", "tidak_relevan"].includes(h.status) && r.putaran === h.putaran_terpilih)
      judul = h.status === "tidak_relevan"
        ? "Batas putaran habis, tidak ada jawaban yang jelas menjawab pertanyaan"
        : "Batas putaran habis, dipilih yang paling dekat sasaran";
    isi.append(el("div", "jejak-judul", judul));
    const u = r.ukuran || {}, s = r.sasaran || {};
    const ukur = el("div", "jejak-ukur");
    const a = el("span", r.lolos_pkr ? "" : "lewat", `${angka(u.pkr)} kata/kalimat, batas ${angka(s.maks_pkr)}`);
    const b = el("span", r.lolos_kld ? "" : "lewat", `${angka(u.kld, 0)}% kata sulit, batas ${angka(s.maks_kld)}%`);
    ukur.append(a, document.createElement("br"), b);
    if (r.relevan != null) ukur.append(document.createElement("br"), el("span", r.relevan ? "" : "lewat",
      `menjawab pertanyaan: ${r.relevan ? "ya" : "tidak"} (${Math.round(100 * (r.p_relevan || 0))}%)`));
    isi.append(ukur, el("div", "jejak-jawab", r.jawaban));
    li.append(isi);
    return li;
  }));
}

// ---------------------------------------------------------------------------
// Pengiriman: dialirkan per agen, dengan cadangan permintaan biasa
// ---------------------------------------------------------------------------
async function* bacaAliran(respon) {
  const pembaca = respon.body.getReader();
  const dek = new TextDecoder();
  let sisa = "";
  for (;;) {
    const { value, done } = await pembaca.read();
    if (done) break;
    sisa += dek.decode(value, { stream: true });
    let i;
    while ((i = sisa.indexOf("\n\n")) >= 0) {
      const blok = sisa.slice(0, i); sisa = sisa.slice(i + 2);
      const ev = /^event: (.*)$/m.exec(blok)?.[1];
      const data = /^data: (.*)$/m.exec(blok)?.[1];
      if (ev && data) yield [ev, JSON.parse(data)];
    }
  }
}

async function kirim(e) {
  e?.preventDefault();
  const kotak = $("#tanya");
  const teks = kotak.value.trim();
  if (!teks || keadaan.sibuk) return;
  kotak.value = ""; aturTinggi();
  await jalankan(teks);
}

// Kartu Perceive Agent: masukan kabur, sistem menawarkan pertanyaan lengkap
function kartuTanyaBalik(h) {
  const k = el("div", "jawaban tanya-balik");
  k.append(el("p", "jawaban-teks", "Aku belum yakin maksudmu. Apakah maksudmu:"));
  const pilih = el("div", "pilihan-balik");
  const ya = el("button", "tombol-pilihan utama", h.saran_pertanyaan);
  ya.type = "button";
  ya.addEventListener("click", () => jalankan(h.saran_pertanyaan));
  const tidak = el("button", "tombol-pilihan", "Bukan, aku tulis ulang");
  tidak.type = "button";
  tidak.addEventListener("click", () => $("#tanya").focus());
  pilih.append(ya, tidak);
  k.append(pilih);
  return k;
}

// Kartu Plan Agent: ragu menentukan kelas, siswa diminta memilih
function kartuKonfirmasi(h, teksAsli) {
  const k = el("div", "jawaban tanya-balik");
  k.append(el("p", "jawaban-teks", "Supaya jawabanku pas, kamu kelas berapa?"));
  const kandidat = h.kandidat_kelas || [];
  if (kandidat.length) k.append(el("div", "jejak-ukur",
    `Tebakanku kelas ${kandidat.join(" atau ")}, tapi aku belum yakin (${Math.round(100 * (h.keyakinan_kelas || 0))}%).`));
  const pilih = el("div", "pilihan-kelas");
  for (let n = 1; n <= 6; n++) {
    const b = el("button", "tombol-kelas" + (kandidat.includes(n) ? " disarankan" : ""), `Kelas ${n}`);
    b.type = "button";
    b.addEventListener("click", () => {
      $("#pilih-kelas").value = String(n);          // dipakai juga untuk pertanyaan berikutnya
      simpan.taruh("tb_kelas", String(n));          // dan diingat walau halaman dimuat ulang
      tampilkanJenjang(n, "pengguna");
      jalankan(teksAsli, n);
    });
    pilih.append(b);
  }
  k.append(pilih);
  return k;
}

async function jalankan(teks, kelasPilihan = null) {
  if (!teks || keadaan.sibuk) return;
  keadaan.sibuk = true;
  $("#tombol-tanya").disabled = true;
  const kotak = $("#tanya");

  const dibaca = tambahTanya(teks);
  const skenario = caraTerpilih();
  const alur = buatAlur(skenario);
  const kelasUI = $("#pilih-kelas").value ? Number($("#pilih-kelas").value) : null;
  const badan = JSON.stringify({
    pertanyaan: teks, mata_pelajaran: keadaan.mapel,
    kelas: kelasPilihan ?? kelasUI,
    skenario,
    percakapan_id: keadaan.percakapan,
    paksa_jawab: keadaan.tanyaBalik >= MAKS_TANYA_BALIK,
  });

  let hasil = null;
  try {
    const r = await fetch(`${API}/api/tanya/alir`, { method: "POST", headers: kepalaHttp(), body: badan,
                                                     credentials: "include" });
    if (r.status === 401 && keadaan.loginAktif) { location.href = "masuk.html"; return; }
    if (r.status === 401) { bukaDialog("Server meminta kunci akses."); throw new Error("kunci akses dibutuhkan"); }
    if (!r.ok || !r.body) throw new Error(`server menjawab ${r.status}`);
    for await (const [ev, isi] of bacaAliran(r)) {
      if (ev === "galat") throw new Error(isi.pesan);
      if (ev === "perceive") {
        dibaca.replaceChildren("Dibaca sebagai ", el("b", "", isi.pertanyaan_bersih));
        alurPerceive(alur, isi);
      } else if (ev === "plan") {
        tampilkanJenjang(isi.kelas, isi.sumber_kelas);
        alurPlan(alur, isi);
      } else if (ev === "act") {
        alurAct(alur, isi);
      } else if (ev === "reflect") {
        alurReflect(alur, isi);
      } else if (ev === "selesai") {
        hasil = isi;
      } else if (ev === "tersimpan") {
        keadaan.percakapan = isi.percakapan_id;
        muatRiwayat();
      }
    }
    if (!hasil) throw new Error("aliran terputus sebelum selesai");
  } catch (err) {
    alur.box.remove();
    const g = el("div", "jawaban tolak");
    g.append(el("p", "jawaban-teks", "Maaf, ada gangguan saat menghubungi server."));
    g.append(el("div", "jejak-ukur", String(err.message || err)));
    $("#pesan").append(denganAvatar(g));
    pita(`Gagal: ${err.message || err}`, true);
  }

  if (hasil) {
    keadaan.tanyaBalik = ["tanya_balik", "konfirmasi_kelas"].includes(hasil.status)
      ? keadaan.tanyaBalik + 1 : 0;
    tutupAlur(alur, hasil);
    alur.box.after(kartuHasil(hasil, teks));
    if (hasil.pertanyaan_bersih) dibaca.replaceChildren("Dibaca sebagai ", el("b", "", hasil.pertanyaan_bersih));
    if (hasil.kelas && hasil.status !== "konfirmasi_kelas") tampilkanJenjang(hasil.kelas, hasil.sumber_kelas);
    tampilkanSumber(hasil);
    tampilkanJejak(hasil);
  }
  gulirBawah();
  keadaan.sibuk = false;
  $("#tombol-tanya").disabled = false;
  kotak.focus();
}

function kartuHasil(hasil, teks) {
  return denganAvatar(hasil.status === "tanya_balik" ? kartuTanyaBalik(hasil)
    : hasil.status === "konfirmasi_kelas" ? kartuKonfirmasi(hasil, teks)
    : kartuJawaban(hasil));
}

// ---------------------------------------------------------------------------
// Riwayat chat (tersimpan di database, milik akun yang sedang masuk)
// ---------------------------------------------------------------------------
const waktuPendek = (iso) => new Date(iso).toLocaleString("id-ID",
  { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

async function muatRiwayat() {
  if (!keadaan.loginAktif) return;
  const ul = $("#riwayat");
  try {
    const daftar = await fetch(`${API}/api/percakapan`, { credentials: "include" }).then((r) => r.json());
    if (!Array.isArray(daftar) || !daftar.length) {
      ul.replaceChildren(el("li", "kosong", "Belum ada chat."));
      return;
    }
    ul.replaceChildren(...daftar.map((c) => {
      const li = el("li");
      const b = el("button");
      b.type = "button";
      if (c.id === keadaan.percakapan) b.setAttribute("aria-current", "true");
      b.append(el("span", "judul-riwayat", c.judul),
        el("span", "meta-riwayat", `${c.mapel === "PKN" ? "Pancasila" : "PJOK"} · ${waktuPendek(c.diperbarui)}`));
      b.addEventListener("click", () => bukaPercakapan(c.id));
      li.append(b);
      return li;
    }));
  } catch {
    ul.replaceChildren(el("li", "kosong", "Riwayat belum bisa dimuat."));
  }
}

async function bukaPercakapan(id) {
  if (keadaan.sibuk) return;
  const r = await fetch(`${API}/api/percakapan/${id}`, { credentials: "include" });
  if (!r.ok) { pita("Riwayat chat tidak ditemukan.", true); return; }
  const c = await r.json();
  keadaan.percakapan = c.id;
  gantiMapel(c.mapel);
  const wadah = $("#pesan");
  wadah.replaceChildren();
  let akhir = null;
  for (const m of c.pesan) {
    const dibaca = tambahTanya(m.pertanyaan);
    if (m.hasil.pertanyaan_bersih) dibaca.replaceChildren("Dibaca sebagai ", el("b", "", m.hasil.pertanyaan_bersih));
    wadah.append(kartuHasil(m.hasil, m.pertanyaan));
    akhir = m.hasil;
  }
  if (akhir) { tampilkanSumber(akhir); tampilkanJejak(akhir); }
  gulirBawah();
  muatRiwayat();
}

// ---------------------------------------------------------------------------
// Dialog server
// ---------------------------------------------------------------------------
function bukaDialog(pesan) {
  const d = $("#dialog-server");
  $("#isian-api").value = API;
  $("#isian-kunci").value = KUNCI;
  if (pesan) d.querySelector("p").textContent = pesan;
  d.showModal();
}

$("#dialog-server").addEventListener("close", () => {
  if ($("#dialog-server").returnValue !== "simpan") return;
  API = $("#isian-api").value.trim().replace(/\/+$/, "");
  KUNCI = $("#isian-kunci").value.trim();
  simpan.taruh("tb_api", API); simpan.taruh("tb_kunci", KUNCI);
  sapaServer();
});

// ---------------------------------------------------------------------------
// Pemasangan
// ---------------------------------------------------------------------------
function aturTinggi() {
  const t = $("#tanya");
  t.style.height = "auto";
  t.style.height = Math.min(t.scrollHeight, 160) + "px";
}

$("#form").addEventListener("submit", kirim);
$("#tanya").addEventListener("input", aturTinggi);
$("#tanya").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); kirim(); }
});
document.querySelectorAll(".pengalih button").forEach((b) =>
  b.addEventListener("click", () => gantiMapel(b.dataset.mapel)));
// Kelas yang sudah dipilih diingat per perangkat, supaya siswa tidak ditanya kelas lagi
// setiap kali menekan "Baru" (halaman dimuat ulang). "Otomatis" berarti Plan Agent menebak.
$("#pilih-kelas").addEventListener("change", () => {
  simpan.taruh("tb_kelas", $("#pilih-kelas").value);
  tampilkanJenjang(null, "pengguna");
});
{
  const k = simpan.ambil("tb_kelas");
  if (/^[1-6]$/.test(k)) { $("#pilih-kelas").value = k; tampilkanJenjang(null, "pengguna"); }
}
$("#tombol-server").addEventListener("click", () => bukaDialog());
$("#tombol-baru").addEventListener("click", () => location.reload());

// panel lipat Sumber dan Jejak: tertutup bawaan, keadaan buka/tutup diingat per perangkat
for (const id of ["sumber", "jejak"]) {
  const d = $(`#lipat-${id}`);
  d.open = simpan.ambil(`tb_lipat_${id}`) === "1";
  d.addEventListener("toggle", () => {
    simpan.taruh(`tb_lipat_${id}`, d.open ? "1" : "");
    if (d.open) d.classList.remove("baru");
  });
}

pasangCara();
gantiMapel("PJOK");
cekAkun().then((lanjut) => { if (lanjut) { sapaServer(); muatRiwayat(); } });
