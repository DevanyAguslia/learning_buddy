"use strict";

const simpan = {
  ambil(k) { try { return localStorage.getItem(k) || ""; } catch { return ""; } },
};
const qs = new URLSearchParams(location.search);
const API = (qs.get("api") || simpan.ambil("tb_api")).replace(/\/+$/, "");
const KUNCI = simpan.ambil("tb_kunci");
const kepala = () => Object.assign({ "Content-Type": "application/json" }, KUNCI ? { "X-Kunci": KUNCI } : {});

const $ = (s) => document.querySelector(s);
// S1-S4 di Lab: kode penelitian beserta artinya
const LABEL_S = { S1: "S1 (model dasar)", S2: "S2 (adapter per tingkat kelas)",
                  S3: "S3 (konteks buku)", S4: "S4 (gabungan adapter + buku)" };
const el = (tag, cls, teks) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (teks !== undefined && teks !== null) e.textContent = teks;
  return e;
};
const SVG = "http://www.w3.org/2000/svg";
const sv = (tag, atr = {}) => {
  const e = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(atr)) e.setAttribute(k, v);
  return e;
};
const angka = (x, d = 2) => (x === null || x === undefined || Number.isNaN(x)) ? "-" :
  Number(x).toLocaleString("id-ID", { minimumFractionDigits: d, maximumFractionDigits: d });
const persen = (x) => (x === null || x === undefined) ? "-" : angka(100 * x, 1) + "%";

const WARNA = { PJOK: "var(--seri-1)", PKN: "var(--seri-2)", S1: "var(--seri-1)",
                S2: "var(--seri-2)", S3: "var(--seri-3)", S4: "var(--seri-4)" };
const NAMA_MAPEL = { PJOK: "PJOK", PKN: "Pancasila" };

function pita(pesan, galat = false) {
  const p = $("#pita");
  p.hidden = !pesan; p.textContent = pesan || ""; p.classList.toggle("galat", galat);
}

// ---------------------------------------------------------------- tooltip
const tip = $("#tooltip");
function tampilTip(e, isi) {
  tip.replaceChildren(...isi);
  tip.hidden = false;
  const x = Math.min(e.clientX + 14, innerWidth - tip.offsetWidth - 8);
  const y = Math.min(e.clientY + 14, innerHeight - tip.offsetHeight - 8);
  tip.style.left = x + "px"; tip.style.top = y + "px";
}
function sembunyiTip() { tip.hidden = true; }
function barisTip(label, nilai) {
  const d = el("div"); d.append(el("b", "", label + ": "), nilai); return d;
}

// ---------------------------------------------------------------- tab
document.querySelectorAll('[role="tab"]').forEach((t) => t.addEventListener("click", () => {
  document.querySelectorAll('[role="tab"]').forEach((x) => {
    const pilih = x === t;
    x.setAttribute("aria-selected", String(pilih));
    $("#" + x.getAttribute("aria-controls")).hidden = !pilih;
  });
  if (t.id === "tab-evaluasi") muatEvaluasi();
  if (t.id === "tab-uji") { cekServer(); muatRiwayat(); }
  if (t.id === "tab-buku") muatBuku();
}));

function pengalih(id, saatGanti) {
  const g = $(id);
  g.querySelectorAll("button").forEach((b) => b.addEventListener("click", () => {
    g.querySelectorAll("button").forEach((x) => x.setAttribute("aria-checked", String(x === b)));
    saatGanti(b.dataset.mapel);
  }));
  return () => g.querySelector('[aria-checked="true"]').dataset.mapel;
}

// =================================================================== UKUR TEKS
const CONTOH_UKUR = [
  ["Kelas 1, mudah", "Pemanasan membuat otot siap bergerak. Tubuh jadi tidak mudah cedera."],
  ["Kalimat panjang", "Salah satu bentuk latihan yang dapat dilakukan untuk meningkatkan kemampuan kelentukan dan kelenturan tubuh adalah berlunjur sambil mencium lutut."],
  ["Kosakata sulit", "Aktivitas kardiorespirasi merupakan latihan yang bertujuan meningkatkan kapasitas sistem kardiovaskular."],
  ["Pancasila", "Gotong royong adalah bekerja bersama-sama untuk kepentingan bersama."],
];
const mapelUkur = pengalih("#ukur-mapel", () => ukur());
$("#ukur-contoh").append(...CONTOH_UKUR.map(([label, t]) => {
  const b = el("button", "", label); b.type = "button";
  b.addEventListener("click", () => { $("#ukur-teks").value = t; ukur(); });
  return b;
}));

let tundaUkur;
$("#ukur-teks").addEventListener("input", () => { clearTimeout(tundaUkur); tundaUkur = setTimeout(ukur, 350); });
$("#ukur-kelas").addEventListener("change", ukur);

async function ukur() {
  const teks = $("#ukur-teks").value.trim();
  if (!teks) return;
  try {
    const r = await fetch(`${API}/api/ukur`, { method: "POST", headers: kepala(), body: JSON.stringify({
      teks, mata_pelajaran: mapelUkur(), kelas: $("#ukur-kelas").value ? Number($("#ukur-kelas").value) : null }) });
    if (!r.ok) throw new Error(`server menjawab ${r.status}`);
    tampilUkur(await r.json());
    pita(null);
  } catch (e) { pita(`Ukur gagal: ${e.message}. Pastikan server lokal berjalan.`, true); }
}

function tampilUkur(h) {
  // pemeriksaan PKR/KLD Reflect Agent
  const p = h.pemeriksaan, box = $("#ukur-periksa");
  box.replaceChildren();
  if (p) {
    const k = el("div", "kotak");
    k.append(el("span", "chip " + (p.lolos ? "sesuai" : "belum"),
      p.lolos ? `Lolos sasaran kelas ${$("#ukur-kelas").value}` : `Belum sesuai kelas ${$("#ukur-kelas").value}`));
    k.append(el("span", "chip", `PKR ${angka(p.ukuran.pkr, 1)} / maks ${angka(p.sasaran.maks_pkr, 1)}`));
    k.append(el("span", "chip", `KLD ${angka(p.ukuran.kld, 1)}% / maks ${angka(p.sasaran.maks_kld, 1)}%`));
    box.append(k);
    if (p.arahan) box.append(el("div", "arahan", "Arahan Reflect Agent: " + p.arahan));
  }
  // sorotan
  const maks = p ? p.sasaran.maks_pkr : Infinity;
  $("#ukur-sorot").replaceChildren(...h.kalimat.map((k) => {
    const baris = el("div", "kalimat");
    const isi = el("div");
    k.kata.forEach((w, i) => {
      let n;
      if (w.luar) { n = el("mark", "luar" + (w.suku >= 3 ? " kompleks" : ""), w.w); }
      else n = el("span", w.suku >= 3 ? "kompleks" : "", w.w);
      n.title = `${w.suku} suku kata${w.luar ? " · di luar daftar" : ""}`;
      isi.append(n, i < k.kata.length - 1 ? " " : "");
    });
    baris.append(isi, el("span", "n" + (k.n_kata > maks ? " lewat" : ""), `${k.n_kata} kata`));
    return baris;
  }));
  // tabel rumus
  const t = $("#ukur-tabel");
  const kep = el("tr");
  ["Kode", "Alat ukur", "Peran", "Nilai", "Setara kelas", "Arah"].forEach((c, i) =>
    kep.append(el("th", i >= 3 ? "angka" : "", c)));
  const baris = Object.entries(h.rumus).map(([kode, r]) => {
    const tr = el("tr", kode === "PKR" || kode === "KLD" ? "baris-utama" : "");
    const td1 = el("td", "kode", kode);
    const td2 = el("td"); td2.append(r.nama, el("div", "redup", r.sumber));
    tr.append(td1, td2, el("td", "", r.peran === "kendali" ? "Kendali" : "Pembanding"), el("td", "angka", angka(r.nilai, 2)),
      el("td", "angka", r.kelas ?? "-"), el("td", "angka", r.arah > 0 ? "↑ sulit" : "↑ mudah"));
    return tr;
  });
  t.replaceChildren(el("thead"), el("tbody"));
  t.tHead.append(kep); t.tBodies[0].append(...baris);
  // integrasi
  const g = h.integrasi_classroom, box2 = $("#ukur-integrasi");
  if (!box2) { /* integrasi Classroom AI tidak ditampilkan lagi */ }
  else if (!g) { box2.replaceChildren(el("div", "catatan-kecil", "Acuan belum ada. Jalankan: python -m tb.evaluasi_rumus")); }
  else {
    const kelompok = { G1: "daftar kata (DC, Spache)", G2: "panjang kata-kalimat (FRES, FKGL, CLI)", G3: "suku kata (LW, Fog)" };
    box2.replaceChildren(...Object.entries(g.suara).map(([k, v]) => {
      const d = el("div", "suara"); d.append(el("b", "", `Kelas ${v}`), el("span", "", `${k}: ${kelompok[k]}`)); return d;
    }));
    const a = el("div", "suara akhir"); a.append(el("b", "", `Kelas ${g.kelas}`), el("span", "", `hasil akhir (${g.cara})`));
    box2.append(a);
  }
  const hc = h.hitungan;
  $("#ukur-hitungan").textContent =
    `kata ${hc.kata} · kalimat ${hc.kalimat} · suku kata ${hc.suku} · huruf ${hc.huruf}\n` +
    `kata >= 3 suku ${hc.kata_kompleks} · kata > 6 huruf ${hc.kata_panjang} · kata isi ${hc.kata_isi}\n` +
    `kata tidak akrab (Dale-Chall): ${hc.tak_akrab.join(", ") || "-"}`;
}

// =============================================================== EVALUASI RUMUS
let EVAL = null;
const mapelKonfusi = pengalih("#eval-mapel", () => gambarKonfusi());

async function muatEvaluasi() {
  if (EVAL) return;
  try {
    const r = await fetch(`${API}/api/evaluasi`);
    if (!r.ok) throw new Error((await r.json()).detail || r.status);
    EVAL = await r.json();
    const pilih = $("#eval-rumus");
    pilih.replaceChildren(...Object.entries(EVAL.rumus).map(([k, v]) => {
      const o = el("option", "", `${k} · ${v.nama}`); o.value = k; return o;
    }));
    pilih.value = "KLD";
    gambarEvaluasi();
  } catch (e) { pita(`Evaluasi belum tersedia: ${e.message}`, true); }
}
["#eval-tingkat", "#eval-ukuran"].forEach((s) => $(s).addEventListener("change", gambarEvaluasi));
$("#eval-rumus").addEventListener("change", () => { gambarSebaran(); gambarKonfusi(); });

function nilaiEval(mapel, tingkat, kode, ukuran) {
  const blok = EVAL.mapel[mapel]?.[tingkat]?.[kode];
  if (!blok) return null;
  if (ukuran === "rho") {
    const r = blok.rho;
    if (r === null || r === undefined) return null;
    const arah = EVAL.rumus[kode]?.arah ?? 1;   // FRES dibalik agar semua searah kesulitan
    return r * arah;
  }
  return blok[ukuran] ?? null;
}

function gambarEvaluasi() {
  if (!EVAL) return;
  const tingkat = $("#eval-tingkat").value;
  let ukuran = $("#eval-ukuran").value;
  if (tingkat === "buku" && ukuran !== "rho") { $("#eval-ukuran").value = ukuran = "rho"; }
  const mapel = Object.keys(EVAL.mapel);
  const n = mapel.map((m) => {
    const b = EVAL.mapel[m][tingkat]; const any = Object.values(b)[0];
    return `${NAMA_MAPEL[m]} n = ${tingkat === "buku" ? 6 : any.n}`;
  }).join(", ");
  $("#eval-keterangan").textContent = (ukuran === "rho"
    ? "Korelasi Spearman antara nilai rumus dan tingkat kelas, disearahkan: makin panjang ke kanan, makin sesuai dengan naiknya tingkat kelas "
    : "Proporsi sampel yang tingkat kelasnya ditebak benar dari nilai rumus. Garis putus-putus = tebakan acak. ") + `(${n})`;

  const kode = Object.keys(EVAL.mapel[mapel[0]][tingkat]);
  const baris = kode.map((k) => ({ k, v: mapel.map((m) => nilaiEval(m, tingkat, k, ukuran)) }))
    .sort((a, b) => avg(b.v) - avg(a.v));
  $("#eval-legenda").replaceChildren(...mapel.map((m) => {
    const s = el("span"); const i = el("i"); i.style.background = WARNA[m]; s.append(i, NAMA_MAPEL[m]); return s;
  }));
  const acak = ukuran === "tepat" ? 1 / 6 : ukuran === "tepat_1" ? 16 / 36 : null;
  barHorizontal($("#eval-grafik"), baris, mapel, ukuran === "rho" ? [-0.2, 1] : [0, 1], acak,
    (k) => (EVAL.rumus[k]?.nama || k.replace("_", " ").toLowerCase()), ukuran === "rho" ? (x) => angka(x, 3) : persen);
  // tabel
  const t = $("#eval-tabel");
  const kep = el("tr"); ["Kode", "Alat ukur", ...mapel.map((m) => NAMA_MAPEL[m])].forEach((c, i) => kep.append(el("th", i > 1 ? "angka" : "", c)));
  t.replaceChildren(el("thead"), el("tbody")); t.tHead.append(kep);
  t.tBodies[0].append(...baris.map((b) => {
    const tr = el("tr", b.k === "PKR" || b.k === "KLD" ? "baris-utama" : "");
    tr.append(el("td", "kode", b.k), el("td", "", EVAL.rumus[b.k]?.nama || "Integrasi"),
      ...b.v.map((v) => el("td", "angka", ukuran === "rho" ? angka(v, 3) : persen(v))));
    return tr;
  }));
  gambarSebaran(); gambarKonfusi();
}
const avg = (xs) => { const v = xs.filter((x) => x !== null); return v.length ? v.reduce((a, b) => a + b, 0) / v.length : -9; };

function barHorizontal(wadah, baris, seri, domain, garisAcak, namaPanjang, fmt) {
  const W = 760, kiri = 190, kanan = 24, atas = 24, tinggiBaris = 30, tb = 10, sela = 2;
  const H = atas + baris.length * tinggiBaris + 26;
  const x = (v) => kiri + (v - domain[0]) / (domain[1] - domain[0]) * (W - kiri - kanan);
  const s = sv("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Grafik batang per rumus" });
  // kisi dan sumbu
  const langkah = domain[0] < 0 ? [-0.2, 0, 0.2, 0.4, 0.6, 0.8, 1] : [0, 0.2, 0.4, 0.6, 0.8, 1];
  for (const t of langkah) {
    s.append(sv("line", { x1: x(t), x2: x(t), y1: atas - 6, y2: H - 22, stroke: t === 0 ? "var(--sumbu)" : "var(--kisi)", "stroke-width": 1 }));
    const tx = sv("text", { x: x(t), y: H - 6, "text-anchor": "middle" });
    tx.textContent = fmt === persen ? `${Math.round(t * 100)}%` : angka(t, 1); s.append(tx);
  }
  if (garisAcak) {
    s.append(sv("line", { x1: x(garisAcak), x2: x(garisAcak), y1: atas - 6, y2: H - 22, stroke: "var(--teks-lembut)", "stroke-dasharray": "4 4" }));
    const tx = sv("text", { x: x(garisAcak) + 4, y: atas - 10 }); tx.textContent = "acak"; s.append(tx);
  }
  baris.forEach((b, i) => {
    const y0 = atas + i * tinggiBaris;
    const lab = sv("text", { x: kiri - 10, y: y0 + tinggiBaris / 2 + 1, "text-anchor": "end", class: "label-sumbu", "dominant-baseline": "middle" });
    lab.textContent = b.k.replace("INTEGRASI_CLASSROOM", "Integrasi (paper)").replace("INTEGRASI_PLUS", "Integrasi + PKR/KLD");
    if (b.k === "PKR" || b.k === "KLD") lab.setAttribute("font-weight", "700");
    s.append(lab);
    const tinggiGrup = seri.length * tb + (seri.length - 1) * sela;
    b.v.forEach((v, j) => {
      if (v === null) return;
      const y = y0 + (tinggiBaris - tinggiGrup) / 2 + j * (tb + sela);
      const a = x(Math.max(Math.min(0, v), domain[0])), z = x(Math.max(v, domain[0]));
      const kiriX = Math.min(a, z), lebar = Math.max(Math.abs(z - a), 1.5);
      s.append(sv("rect", { x: kiriX, y, width: lebar, height: tb, rx: 2, fill: WARNA[seri[j]] }));
    });
    // area sentuh sebaris penuh
    const sentuh = sv("rect", { x: 0, y: y0, width: W, height: tinggiBaris, fill: "transparent" });
    sentuh.addEventListener("mousemove", (e) => tampilTip(e, [el("div", "", namaPanjang(b.k)),
      ...seri.map((m, j) => barisTip(NAMA_MAPEL[m], fmt(b.v[j])))]));
    sentuh.addEventListener("mouseleave", sembunyiTip);
    s.append(sentuh);
  });
  wadah.replaceChildren(s);
}

function gambarSebaran() {
  if (!EVAL) return;
  const kode = $("#eval-rumus").value;
  const wadah = $("#eval-sebaran");
  wadah.replaceChildren(...Object.keys(EVAL.mapel).map((m) => {
    const d = EVAL.mapel[m].halaman[kode]?.sebaran;
    const box = el("div");
    const h = el("h4"); const i = el("i"); i.style.background = WARNA[m]; h.append(i, NAMA_MAPEL[m]);
    box.append(h);
    if (!d) return box;
    const W = 320, H = 210, kiri = 44, bawah = 28, atas = 10;
    const nilai = Object.values(d).flat();
    let lo = Math.min(...nilai), hi = Math.max(...nilai);
    const pad = (hi - lo) * 0.1 || 1; lo -= pad; hi += pad;
    const x = (k) => kiri + (k - 0.5) / 6 * (W - kiri - 8);
    const y = (v) => atas + (1 - (v - lo) / (hi - lo)) * (H - atas - bawah);
    const s = sv("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": `Sebaran ${kode} per kelas, ${NAMA_MAPEL[m]}` });
    for (let t = 0; t <= 4; t++) {
      const v = lo + (hi - lo) * t / 4;
      s.append(sv("line", { x1: kiri, x2: W - 8, y1: y(v), y2: y(v), stroke: "var(--kisi)" }));
      const tx = sv("text", { x: kiri - 6, y: y(v) + 4, "text-anchor": "end" }); tx.textContent = angka(v, 1); s.append(tx);
    }
    for (let k = 1; k <= 6; k++) {
      const [q1, med, q3] = d[k];
      const tx = sv("text", { x: x(k), y: H - 8, "text-anchor": "middle" }); tx.textContent = `Kls ${k}`; s.append(tx);
      s.append(sv("line", { x1: x(k), x2: x(k), y1: y(q1), y2: y(q3), stroke: WARNA[m], "stroke-width": 6, "stroke-linecap": "round", opacity: 0.45 }));
      s.append(sv("circle", { cx: x(k), cy: y(med), r: 5, fill: WARNA[m], stroke: "#fff", "stroke-width": 2 }));
      const sentuh = sv("rect", { x: x(k) - 22, y: atas, width: 44, height: H - atas - bawah, fill: "transparent" });
      sentuh.addEventListener("mousemove", (e) => tampilTip(e, [el("div", "", `${NAMA_MAPEL[m]} kelas ${k}`),
        barisTip("median", angka(med)), barisTip("kuartil 25-75", `${angka(q1)} - ${angka(q3)}`)]));
      sentuh.addEventListener("mouseleave", sembunyiTip);
      s.append(sentuh);
    }
    box.append(s);
    return box;
  }));
}

function gambarKonfusi() {
  if (!EVAL) return;
  const kode = $("#eval-rumus").value, m = mapelKonfusi();
  const b = EVAL.mapel[m].halaman[kode];
  const wadah = $("#eval-konfusi");
  if (!b) { wadah.replaceChildren(); return; }
  const mat = b.konfusi;
  const ramp = ["#f4f8fd", "#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"];
  const t = el("table");
  const kep = el("tr"); kep.append(el("th", "", ""));
  for (let k = 1; k <= 6; k++) kep.append(el("th", "", `tebak ${k}`));
  t.append(kep);
  mat.forEach((row, i) => {
    const tot = row.reduce((a, c) => a + c, 0) || 1;
    const tr = el("tr"); tr.append(el("th", "", `kelas ${i + 1}`));
    row.forEach((c, j) => {
      const f = c / tot, idx = Math.min(ramp.length - 1, Math.round(f * (ramp.length - 1)));
      const td = el("td", "", String(c));
      td.style.background = ramp[idx]; td.style.color = idx >= 4 ? "#fff" : "var(--teks)";
      if (i === j) td.style.outline = "2px solid var(--kuning)";
      td.addEventListener("mousemove", (e) => tampilTip(e, [el("div", "", `Buku kelas ${i + 1}, ditebak kelas ${j + 1}`),
        barisTip("halaman", String(c)), barisTip("porsi baris", persen(f))]));
      td.addEventListener("mouseleave", sembunyiTip);
      tr.append(td);
    });
    t.append(tr);
  });
  const ring = el("div", "ringkas", `${kode} · ${NAMA_MAPEL[m]}: tepat ${persen(b.tepat)}, +-1 tingkat kelas ${persen(b.tepat_1)}, rata-rata meleset ${angka(b.mae)} tingkat kelas`);
  wadah.replaceChildren(t, el("div", "sumbu-label", "baris = tingkat kelas buku, kolom = tingkat kelas tebakan"), ring);
}

// ================================================================== UJI SISTEM
let pantau = null;

async function cekServer() {
  try {
    const s = await fetch(`${API}/api/sehat`).then((r) => r.json());
    const tiruan = String(s.mode).includes("tiruan");
    $("#uji-server").textContent = `penjawab: ${s.mode}\nmodel    : ${s.model}\ncari     : ${s.pencarian}` +
      (s.remote ? `\nremote   : ${s.remote}` : "");
    pita(tiruan ? "Mode uji tampilan (AI belum dinyalakan): angka pengujian hanya membuktikan alurnya berjalan, bukan hasil penelitian. Sambungkan ke Kaggle dengan --remote." : null);
  } catch { $("#uji-server").textContent = "server tidak dapat dihubungi"; }
}

$("#uji-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const skenario = [...document.querySelectorAll("#uji-form fieldset input:checked")].map((x) => x.value);
  if (!skenario.length) { pita("Pilih minimal satu skenario.", true); return; }
  const r = await fetch(`${API}/api/uji/mulai`, { method: "POST", headers: kepala(), body: JSON.stringify({
    mata_pelajaran: $("#uji-mapel").value, n_per_kelas: Number($("#uji-n").value), skenario,
    kelas_dari: $("#uji-kelas-dari").value }) });
  if (!r.ok) { pita(`Gagal memulai: ${(await r.json()).detail}`, true); return; }
  mulaiPantau();
});
$("#uji-henti").addEventListener("click", () => fetch(`${API}/api/uji/hentikan`, { method: "POST", headers: kepala() }));

function mulaiPantau() {
  clearInterval(pantau);
  const tick = async () => {
    try {
      const s = await fetch(`${API}/api/uji/status`).then((r) => r.json());
      tampilStatus(s);
      if (!s.berjalan) { clearInterval(pantau); muatRiwayat(); }
    } catch (e) { clearInterval(pantau); pita(`Pemantauan uji gagal: ${e.message}`, true); }
  };
  tick(); pantau = setInterval(tick, 1500);
}

function tampilStatus(s) {
  if (!s.total) return;
  $("#uji-kemajuan").hidden = false;
  $("#uji-batang").style.width = `${100 * s.selesai / s.total}%`;
  $("#uji-pesan").textContent = `${s.selesai}/${s.total} jawaban` + (s.galat ? ` · ${s.galat} galat` : "") +
    (s.berjalan ? ` · ${s.pesan}` : ` · selesai${s.durasi ? " dalam " + angka(s.durasi, 0) + " detik" : ""}`);
  tampilRingkasan(s.ringkasan, `${NAMA_MAPEL[s.mapel]} · ${s.n_soal} soal · tingkat kelas ${s.kelas_dari === "data" ? "dari data" : "ditebak Plan Agent"}`);
  $("#uji-contoh").replaceChildren(...(s.contoh || []).slice().reverse().map((r) => {
    const d = el("div", "item");
    d.append(el("div", "meta", `${LABEL_S[r.skenario] || r.skenario} · kelas ${r.kelas}${r.kelas_sistem && r.kelas_sistem !== r.kelas ? " (ditebak " + r.kelas_sistem + ")" : ""} · ${r.putaran} putaran · ${r.lolos ? "patuh" : "tidak patuh"} · F1 ${angka(r.f1)}`));
    d.append(el("div", "", "T: " + r.pertanyaan), el("div", "redup", "Kunci: " + r.kunci), el("div", "", "Jawab: " + r.jawaban));
    return d;
  }));
}

const KOLOM_UJI = [["n", "n", (x) => x], ["em", "EM", persen], ["f1", "Token F1", (x) => angka(x, 3)],
  ["chrf", "chrF++", (x) => angka(x, 1)], ["patuh", "Patuh", persen], ["putaran", "Putaran", (x) => angka(x, 2)],
  ["perbaikan", "Diperbaiki", persen], ["batas", "Mentok batas", persen], ["kelas_tepat", "Tingkat kelas tepat", persen],
  ["PKR", "PKR", (x) => angka(x, 1)], ["KLD", "KLD %", (x) => angka(x, 1)], ["detik", "Detik", (x) => angka(x, 1)]];

function tampilRingkasan(rk, judul) {
  if (!rk || !Object.keys(rk).length) return;
  $("#uji-catatan").textContent = judul;
  const sk = Object.keys(rk);
  const t = $("#uji-tabel");
  const kolom = KOLOM_UJI.filter(([k]) => sk.some((s) => rk[s].semua[k] !== undefined));
  const kep = el("tr"); kep.append(el("th", "", "Skenario"));
  kolom.forEach(([, l]) => kep.append(el("th", "angka", l)));
  t.replaceChildren(el("thead"), el("tbody")); t.tHead.append(kep);
  t.tBodies[0].append(...sk.map((s) => {
    const tr = el("tr"); tr.append(el("td", "kode", LABEL_S[s] || s));
    kolom.forEach(([k, , f]) => tr.append(el("td", "angka", rk[s].semua[k] === undefined ? "-" : f(rk[s].semua[k]))));
    return tr;
  }));
  // grafik kepatuhan per tingkat kelas
  $("#uji-legenda").replaceChildren(...sk.map((s) => {
    const x = el("span"); const i = el("i"); i.style.background = WARNA[s]; x.append(i, s); return x;
  }));
  barPerKelas($("#uji-grafik"), rk, sk);
}

function barPerKelas(wadah, rk, sk) {
  const W = 720, H = 240, kiri = 44, bawah = 30, atas = 12;
  const lebarGrup = (W - kiri - 10) / 6, tb = Math.min(22, (lebarGrup - 18) / sk.length - 2);
  const y = (v) => atas + (1 - v) * (H - atas - bawah);
  const s = sv("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Kepatuhan keterbacaan per tingkat kelas" });
  for (const t of [0, 0.25, 0.5, 0.75, 1]) {
    s.append(sv("line", { x1: kiri, x2: W - 10, y1: y(t), y2: y(t), stroke: t === 0 ? "var(--sumbu)" : "var(--kisi)" }));
    const tx = sv("text", { x: kiri - 6, y: y(t) + 4, "text-anchor": "end" }); tx.textContent = `${t * 100}%`; s.append(tx);
  }
  for (let k = 1; k <= 6; k++) {
    const x0 = kiri + (k - 1) * lebarGrup, lebarIsi = sk.length * (tb + 2) - 2, mulai = x0 + (lebarGrup - lebarIsi) / 2;
    const tx = sv("text", { x: x0 + lebarGrup / 2, y: H - 8, "text-anchor": "middle" }); tx.textContent = `Kelas ${k}`; s.append(tx);
    sk.forEach((sc, j) => {
      const a = rk[sc].per_kelas[k];
      if (!a) return;
      const v = a.patuh, xb = mulai + j * (tb + 2);
      s.append(sv("rect", { x: xb, y: y(v), width: tb, height: Math.max(y(0) - y(v), 1.5), rx: 2, fill: WARNA[sc] }));
    });
    const sentuh = sv("rect", { x: x0, y: atas, width: lebarGrup, height: H - atas - bawah, fill: "transparent" });
    sentuh.addEventListener("mousemove", (e) => tampilTip(e, [el("div", "", `Kelas ${k}`),
      ...sk.filter((sc) => rk[sc].per_kelas[k]).map((sc) => barisTip(sc,
        `${persen(rk[sc].per_kelas[k].patuh)} patuh · n ${rk[sc].per_kelas[k].n} · F1 ${angka(rk[sc].per_kelas[k].f1, 3)}`))]));
    sentuh.addEventListener("mouseleave", sembunyiTip);
    s.append(sentuh);
  }
  wadah.replaceChildren(s);
}

async function muatRiwayat() {
  try {
    const daftar = await fetch(`${API}/api/uji/riwayat`).then((r) => r.json());
    $("#uji-riwayat").replaceChildren(...(daftar.length ? daftar : []).map((d) => {
      const li = el("li"); const b = el("button", "",
        `${d.berkas.replace("uji_", "").replace(".json", "")} · ${d.skenario.join(",")} · ${d.n_soal} soal · ${d.mode || "-"}`);
      b.addEventListener("click", () => tampilRingkasan(d.ringkasan, `${d.berkas} · ${NAMA_MAPEL[d.mapel]} · ${d.n_soal} soal · ${d.mode || ""}`));
      li.append(b); return li;
    }));
    if (!daftar.length) $("#uji-riwayat").replaceChildren(el("li", "catatan-kecil", "Belum ada hasil tersimpan."));
  } catch {}
}

// =================================================================== BUKU SEKOLAH
const STATUS_BUKU = { antre: ["chip abu", "menunggu"], diproses: ["chip abu", "diproses…"],
                      siap: ["chip sesuai", "siap dipakai"], gagal: ["chip belum", "gagal"] };
let pantauBuku = null;

async function kirimJson(alamat, badan) {
  const r = await fetch(`${API}${alamat}`, { method: "POST", headers: { "Content-Type": "application/json" },
                                             body: JSON.stringify(badan) });
  const isi = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(typeof isi.detail === "string" ? isi.detail : `server menjawab ${r.status}`);
  return isi;
}

function formSekolah() {
  const wadah = el("div", "sekolah-form");
  const buat = el("form", "baris-kendali");
  const nama = el("input"); nama.placeholder = "Nama sekolah"; nama.maxLength = 120; nama.required = true;
  const b1 = el("button", "tombol-kecil", "Buat sekolah"); b1.type = "submit";
  buat.append(nama, b1);
  buat.addEventListener("submit", async (e) => {
    e.preventDefault();
    try { await kirimJson("/api/sekolah", { nama: nama.value.trim() }); muatBuku(); }
    catch (err) { pita(err.message, true); }
  });
  const gabung = el("form", "baris-kendali");
  const kode = el("input"); kode.placeholder = "Kode sekolah"; kode.maxLength = 12; kode.required = true;
  const b2 = el("button", "tombol-kecil", "Gabung"); b2.type = "submit";
  gabung.append(kode, b2);
  gabung.addEventListener("submit", async (e) => {
    e.preventDefault();
    try { await kirimJson("/api/sekolah/gabung", { kode: kode.value.trim().toUpperCase() }); muatBuku(); }
    catch (err) { pita(err.message, true); }
  });
  wadah.append(el("p", "catatan-kecil", "Belum terdaftar di sekolah. Buat sekolah baru, atau gabung dengan kode dari guru lain."),
               buat, gabung);
  return wadah;
}

function barisBuku(b) {
  const tr = el("tr");
  const judul = el("td"); judul.append(b.judul, el("div", "redup", b.penerbit || "-"));
  const [cls, label] = STATUS_BUKU[b.status] || ["chip abu", b.status];
  const st = el("td"); st.append(el("span", cls, label));
  if (b.pesan) st.append(el("div", "redup", b.pesan));
  const aksi = el("td");
  if (b.status === "siap" || b.status === "gagal") {
    const h = el("button", "tombol-kecil", "Hapus"); h.type = "button";
    h.addEventListener("click", async () => {
      if (!confirm(`Hapus buku "${b.judul}"? Siswa tidak lagi mendapat jawaban dari buku ini.`)) return;
      const r = await fetch(`${API}/api/buku/${b.id}`, { method: "DELETE" });
      if (!r.ok) pita("Buku belum bisa dihapus.", true);
      muatBuku();
    });
    aksi.append(h);
  }
  tr.append(judul, el("td", "", NAMA_MAPEL[b.mapel] || b.mapel), el("td", "angka", String(b.kelas)), st,
            el("td", "angka", b.n_halaman ? `${b.n_halaman} hal · ${b.n_potongan} potongan` : "-"), aksi);
  return tr;
}

async function muatBuku() {
  clearTimeout(pantauBuku);
  let s;
  try {
    const r = await fetch(`${API}/api/sekolah`);
    if (r.status === 404) {
      $("#buku-sekolah").replaceChildren(el("p", "catatan-kecil", "Fitur buku sekolah membutuhkan database akun (login aktif)."));
      $("#buku-kirim").disabled = true; return;
    }
    s = await r.json();
  } catch { pita("Server tidak dapat dihubungi.", true); return; }
  if (s.sekolah) {
    const info = el("div");
    info.append(el("div", "sekolah-nama", s.sekolah.nama),
                el("div", "sekolah-kode", s.sekolah.kode),
                el("p", "catatan-kecil", "Bagikan kode ini ke siswa. Siswa memasukkannya saat mendaftar, atau lewat tombol 🏫 di halaman chat."));
    $("#buku-sekolah").replaceChildren(info);
  } else {
    $("#buku-sekolah").replaceChildren(formSekolah());
  }
  const bisa = !!s.sekolah && s.bisa_unggah;
  $("#buku-kirim").disabled = !bisa;
  if (s.sekolah && !s.bisa_unggah) $("#buku-pesan").textContent = "Server ini meneruskan pertanyaan ke server model lain, jadi unggah buku dilakukan di server model.";
  const t = $("#buku-tabel");
  const kep = el("tr");
  ["Buku", "Mapel", "Kelas", "Status", "Isi", ""].forEach((c, i) => kep.append(el("th", i === 2 || i === 4 ? "angka" : "", c)));
  t.replaceChildren(el("thead"), el("tbody"));
  t.tHead.append(kep);
  if (!s.buku.length) {
    const tr = el("tr"); const td = el("td", "catatan-kecil", "Belum ada buku sekolah."); td.colSpan = 6;
    tr.append(td); t.tBodies[0].append(tr);
  } else t.tBodies[0].append(...s.buku.map(barisBuku));
  if (s.buku.some((b) => b.status === "antre" || b.status === "diproses") && !$("#panel-buku").hidden)
    pantauBuku = setTimeout(muatBuku, 3000);
}

$("#form-buku").addEventListener("submit", async (e) => {
  e.preventDefault();
  const berkas = $("#buku-berkas").files[0];
  if (!berkas) return;
  const q = new URLSearchParams({ judul: $("#buku-judul").value.trim(), penerbit: $("#buku-penerbit").value.trim(),
                                  mapel: $("#buku-mapel").value, kelas: $("#buku-kelas").value });
  const tombol = $("#buku-kirim");
  tombol.disabled = true; tombol.textContent = "Mengunggah…";
  try {
    const r = await fetch(`${API}/api/buku?${q}`, { method: "POST", headers: { "Content-Type": "application/pdf" }, body: berkas });
    const isi = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(typeof isi.detail === "string" ? isi.detail : `server menjawab ${r.status}`);
    $("#form-buku").reset();
    pita(null);
  } catch (err) { pita(`Unggah gagal: ${err.message}`, true); }
  tombol.textContent = "Unggah"; tombol.disabled = false;
  muatBuku();
});

// awal
ukur();

// akun: Ukur teks untuk guru dan peneliti; Evaluasi rumus dan Uji sistem khusus peneliti
// (server juga menolak akun yang tidak berhak)
function aturTabPeneliti(boleh) {
  for (const id of ["evaluasi", "uji"]) {
    $(`#tab-${id}`).hidden = !boleh;
    if (!boleh) $(`#panel-${id}`).hidden = true;
  }
  if (boleh) fetch(`${API}/api/uji/status`).then((r) => r.json())
    .then((s) => { if (s.berjalan) mulaiPantau(); }).catch(() => {});
}
fetch(`${API}/api/saya`).then((r) => r.json()).then((s) => {
  if (!s.login_aktif) { aturTabPeneliti(true); return; }
  if (!s.masuk) { location.href = "masuk.html"; return; }
  if (!s.pengguna.boleh_lab) { location.href = "index.html"; return; }
  aturTabPeneliti(!!s.pengguna.boleh_lab_penuh);
  $("#akun-saya").hidden = false;
  $("#nama-saya").textContent = s.pengguna.username;
  $("#peran-saya").textContent = `· ${s.pengguna.nama_peran}`;
}).catch(() => aturTabPeneliti(true));
$("#tombol-keluar").addEventListener("click", async () => {
  await fetch(`${API}/api/keluar`, { method: "POST" }).catch(() => {});
  location.href = "masuk.html";
});
