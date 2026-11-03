"""Membuat notebook Kaggle sistem Learning Buddy (notebook eksperimen chunking
ada di proyek terpisah ../Eksperimen_Chunking/deploy/buat_notebook_eksperimen.py). Jalankan ulang bila isi sel diubah:
    python deploy/buat_notebook.py

  deploy/kaggle_latih.ipynb          uji pencarian + melatih 6 adapter Pancasila (PJOK memakai
                                     adapter G1 Recursive yang sudah ada). "Save & Run All".
  deploy/kaggle_uji_pencarian.ipynb  menguji pencarian konteks website (Recursive,
                                     3 potongan) dengan soal PJOK Merdeka, tanpa pelatihan.
  deploy/kaggle_server.ipynb         menyalakan sistem lengkap dan membukanya lewat Cloudflare
                                     Quick Tunnel, untuk disambungkan ke UI di laptop.
  deploy/kaggle_uji_sistem.ipynb     pengujian sistem S1-S4 atas seluruh data uji PJOK dan
                                     Pendidikan Pancasila (Bab IV). "Save & Run All".
"""
import copy
import json
import os

DI_SINI = os.path.dirname(os.path.abspath(__file__))


def simpan(nama, sel):
    nb = {"cells": sel,
          "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python",
                                      "name": "python3"},
                       "language_info": {"name": "python"},
                       "kaggle": {"accelerator": "nvidiaTeslaT4", "isInternetEnabled": True}},
          "nbformat": 4, "nbformat_minor": 5}
    # format standar nbformat 4.5: setiap sel ber-id dan isinya daftar baris;
    # tanpa itu Kaggle membaca seluruh notebook sebagai satu sel
    for i, c in enumerate(nb["cells"]):
        c["id"] = f"sel-{i:02d}"
        if isinstance(c["source"], str):
            c["source"] = c["source"].splitlines(keepends=True)
    path = os.path.join(DI_SINI, nama)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(nb, f, ensure_ascii=False, indent=1)
    print("tersimpan:", path)


def md(t):
    return {"cell_type": "markdown", "metadata": {}, "source": t.strip("\n")}


def kode(t):
    return {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [],
            "source": t.strip("\n")}


SEL_KODE = kode(r"""
# Salin kode ke folder kerja
import glob, os, shutil, subprocess, sys, time, re, json

# Matikan sisa server/tunnel dari jalankan sebelumnya. Proses latar itu TIDAK ikut mati saat
# kernel di-restart dan tetap memegang memori GPU (penyebab CUDA out of memory).
for nama in ('tb.server', 'cloudflared'):
    subprocess.run(['pkill', '-f', nama], check=False)
time.sleep(3)
os.environ.setdefault('PYTORCH_CUDA_ALLOC_CONF', 'expandable_segments:True')
# indeks FAISS disimpan di luar folder kerja agar tidak dibangun ulang setiap Run All
os.environ.setdefault('TB_FAISS', '/kaggle/working/faiss_cache')
print(subprocess.run(['nvidia-smi', '--query-gpu=index,memory.used,memory.total', '--format=csv'],
                     capture_output=True, text=True).stdout)

# dicari di mana pun dalam input: zip, folder LearningBuddy, atau isi foldernya langsung
hit = glob.glob('/kaggle/input/**/tb/agen.py', recursive=True)
assert hit, 'Dataset learning-buddy-kode belum ditambahkan sebagai input.'
# Bila ada lebih dari satu salinan kode (dataset lama ikut terpasang), pakai yang terbaru:
# yang sudah punya tb/validasi_recursive.py, lalu yang berkasnya paling baru.
calon = [h.rsplit('/tb/', 1)[0] for h in hit]
calon.sort(key=lambda d: (os.path.exists(d + '/tb/validasi_recursive.py'),
                          os.path.getmtime(d + '/tb/server.py')), reverse=True)
if len(calon) > 1:
    print('PERINGATAN: ada', len(calon), 'salinan kode di input; dipakai yang terbaru.')
    print('  Sebaiknya lepas dataset kode lama dari Input:', calon[1:])
SUMBER = calon[0]
assert os.path.exists(SUMBER + '/data/potongan.jsonl'),     'Folder data/ tidak ikut terunggah; unggah ulang seluruh folder LearningBuddy.'
KERJA = '/kaggle/working/LearningBuddy'
shutil.rmtree(KERJA, ignore_errors=True)
shutil.copytree(SUMBER, KERJA)
os.chdir(KERJA)
sys.path.insert(0, KERJA)
print('kode:', SUMBER, '->', KERJA)
""")

SEL_PUSTAKA = kode(r"""
# Pasang pustaka. Versi dicetak agar dapat dicatat di Bab IV.
subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', '-r', 'requirements.txt',
                '-r', 'requirements-gpu.txt'], check=True)
import importlib, importlib.metadata as md
importlib.invalidate_caches()
for p in ['torch', 'transformers', 'peft', 'bitsandbytes', 'accelerate',
          'sentence-transformers', 'faiss-cpu', 'langgraph', 'fastapi']:
    try: print(f'{p:22s}', md.version(p))
    except Exception: print(f'{p:22s} TIDAK ADA')
import torch
print('GPU:', [torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())])
""")

SEL_INDEKS = kode(r"""
# Indeks FAISS potongan Recursive (sudah dirapikan) per mapel per kelas, buku Kurikulum
# Merdeka, dengan penyandi pilihan (4.379 potongan, sekitar 5-8 menit).
# Ganti TB_MODEL_EMBEDDING bila hasil tb.uji_embedding memilih penyandi lain.
os.environ.setdefault('TB_MODEL_EMBEDDING', 'Qwen/Qwen3-Embedding-4B')
os.environ.setdefault('TB_DEVICE_CARI', 'cuda:1' if torch.cuda.device_count() > 1 else 'cuda')
print('penyandi', os.environ['TB_MODEL_EMBEDDING'], 'di', os.environ['TB_DEVICE_CARI'])
assert torch.cuda.device_count() > 1, 'Aktifkan Accelerator GPU T4 x2: penyandi 4B butuh GPU kedua'
from tb.pencarian import muat_potongan, bangun_indeks_faiss, folder_indeks, boleh_dicari, MODEL_EMBEDDING
ps = muat_potongan()
meta = os.path.join(folder_indeks(os.environ['TB_MODEL_EMBEDDING']), 'meta.json')
lama = json.load(open(meta)) if os.path.exists(meta) else {}
# dipakai ulang hanya bila indeks tersimpan dibangun dari potongan yang sama
if 'strategi' in lama and lama.get('potongan') == sum(boleh_dicari(p) for p in ps):
    print('indeks sudah ada, dipakai ulang:', lama)
else:
    bangun_indeks_faiss(ps, os.environ['TB_MODEL_EMBEDDING'])
import gc; gc.collect(); torch.cuda.empty_cache()
""")

SEL_EVALUASI = kode(r"""
# Uji pipeline website: 1.014 soal PJOK Merdeka (Validasi_Soal_PJOK), dicari seperti saat
# website berjalan (Recursive, reranker, 3 potongan). Dibandingkan dengan tanpa reranker,
# masing-masing 1 dan 3 potongan. Sekaligus mengkalibrasi ambang pengecekan 1
# (ambang_relevan.json). Sekitar 10-20 menit.
from tb.evaluasi_pencarian import evaluasi
hasil_cari = evaluasi()
os.makedirs('/kaggle/working/hasil', exist_ok=True)
for f in ['evaluasi_pencarian.json', 'Evaluasi_Pencarian.xlsx', 'Validasi_Soal_PJOK_Recursive.xlsx']:
    shutil.copy(f'hasil/{f}', f'/kaggle/working/hasil/{f}')
shutil.copy(os.path.join(folder_indeks(os.environ['TB_MODEL_EMBEDDING']), 'ambang_relevan.json'),
            '/kaggle/working/hasil/ambang_relevan.json')
print('ambang pengecekan 1:', hasil_cari['ambang_relevan']['ambang'], hasil_cari['ambang_relevan']['kinerja'])
import gc; gc.collect(); torch.cuda.empty_cache()
""")

# =============================================================================
# Notebook pelatihan
# =============================================================================
simpan("kaggle_latih.ipynb", [
    md(r"""
# Learning Buddy - uji pencarian + pelatihan adapter Pendidikan Pancasila

Notebook ini melakukan dua hal dalam satu kali jalan:
1. menguji pencarian website (Recursive, 3 potongan) dengan 1.014 soal PJOK Merdeka dan
   menghitung ambang pengecekan 1 (`hasil/`);
2. melatih 6 adapter LoRA **Pendidikan Pancasila** kelas 1-6 di atas Qwen2.5-7B-Instruct
   4-bit (Tabel 3.9), pembagian kanonik Pancasila 497/126/158 (Tabel 1.1).

Adapter **PJOK tidak dilatih ulang**: dipakai adapter G1 hasil chunking Recursive
(`D:\Skripsi\adapter-pjok\adapters_recursive`, Token F1 0,648 vs baseline 0,122), diunggah
sebagai dataset Kaggle **adapter-pjok**. Untuk melatih ulang PJOK juga, ubah MAPEL_LATIH.

Konteks latih dicari dengan layanan pencarian yang sama dengan saat menjawab (disaring
jenjang dan mata pelajaran) dan hanya disisipkan bila memuat
jawaban, sehingga adapter mengenal prompt tanpa konteks (S2) maupun berkonteks (S4).
Penyandi konteks: Qwen3-Embedding-4B di GPU kedua + FAISS + cross-encoder bge-reranker-v2-m3.

**Cara menjalankan**

1. Input: Dataset **learning-buddy-kode** (zip dari `python deploy/kemas.py`).
2. *Settings*: Accelerator **GPU T4 x2**, Internet **On**.
3. Tekan **Save Version > Save & Run All (Commit)**. Notebook berjalan sendiri di latar
   belakang (perkiraan 1,5-2 jam) dan browser boleh ditutup.
4. Setelah selesai, tab *Output* berisi `adapters/PKN/` dan `hasil/`. Notebook ini lalu
   ditambahkan sebagai input notebook server (*Add Input > Your Work*).
"""),
    SEL_KODE,
    SEL_PUSTAKA,
    SEL_INDEKS,
    SEL_EVALUASI,
    kode(r"""
# Pelatihan. Adapter yang sudah selesai dilewati, jadi sel ini aman dijalankan ulang.
MAPEL_LATIH = ('PKN',)          # PJOK memakai adapter G1 Recursive yang sudah ada
from tb.latih import latih
ringkasan = latih(MAPEL_LATIH, keluaran='/kaggle/working/adapters', cari='semantik')
"""),
    kode(r"""
# Ringkasan untuk Bab IV, dan pemeriksaan bahwa adapter benar-benar ada
import pandas as pd
r = json.load(open('/kaggle/working/adapters/ringkasan_latih.json'))
display(pd.DataFrame(r['adapter']))
kurang = [f'{m} kelas {k}' for m in MAPEL_LATIH for k in range(1, 7)
          if not os.path.exists(f'/kaggle/working/adapters/{m}/grade_{k}/adapter_model.safetensors')]
print('SEMUA ADAPTER LENGKAP' if not kurang else f'BELUM ADA: {kurang}')
shutil.rmtree('/kaggle/working/LearningBuddy', ignore_errors=True)   # output cukup adapters/
"""),
])

# =============================================================================
# Notebook uji pencarian (tanpa pelatihan)
# =============================================================================
simpan("kaggle_uji_pencarian.ipynb", [
    md(r"""
# Learning Buddy - uji pencarian konteks (buku Kurikulum Merdeka)

Menguji layanan pencarian persis seperti website: potongan **Recursive**, penyandi
Qwen3-Embedding-4B + FAISS, cross-encoder bge-reranker-v2-m3, dan **3 potongan** yang
dikirim ke Act Agent. Soal uji: 1.014 soal `Validasi_Soal_PJOK.xlsx`.

**Cara menjalankan**

1. Input: Dataset **learning-buddy-kode** (versi terbaru dari `python deploy/kemas.py`).
2. *Settings*: Accelerator **GPU T4 x2**, Internet **On**.
3. **Save Version > Save & Run All (Commit)**, sekitar 30-40 menit. Browser boleh ditutup.
4. Unduh tab *Output*: `hasil/Evaluasi_Pencarian.xlsx`, `hasil/evaluasi_pencarian.json`,
   `hasil/ambang_relevan.json`. Output notebook ini juga bisa ditambahkan sebagai input
   notebook server agar ambang pengecekan 1 tidak perlu dihitung ulang.
"""),
    SEL_KODE,
    SEL_PUSTAKA,
    SEL_INDEKS,
    SEL_EVALUASI,
    kode(r"""
shutil.rmtree('/kaggle/working/LearningBuddy', ignore_errors=True)   # output cukup hasil/
"""),
])

# =============================================================================
# Notebook server
# =============================================================================
SEL_SERVER = [
    md(r"""
# Learning Buddy - server penelitian di Kaggle

Menyalakan sistem lengkap (Qwen2.5-7B-Instruct 4-bit, 12 adapter jenjang, penyandi/FAISS,
cross-encoder, dan empat agen) lalu membukanya lewat **Cloudflare Quick Tunnel** yang gratis
dan tanpa akun. UI dijalankan di laptop dan menyambung ke sini.

**Persiapan**

1. Input (tiga-tiganya):
   - Dataset **learning-buddy-kode** (kode + potongan buku);
   - Dataset **adapter-pjok** (isi folder `D:\Skripsi\adapter-pjok\adapters_recursive`,
     adapter PJOK kelas 1-6);
   - output notebook pelatihan (*Add Input > Your Work*), berisi `adapters/PKN/` dan
     `hasil/ambang_relevan.json`.
2. *Settings*: Accelerator **GPU T4 x2**, Internet **On**.
3. *Add-ons > Secrets*: `TB_KUNCI` (kata sandi bebas untuk membatasi pemakai tautan).

Jalankan sel satu per satu atau **Run All** (sesi interaktif, bukan Commit). Sel tunnel
mencetak "Server GPU aktif di : https://...trycloudflare.com"; alamat itu dipakai di VS Code
(konfigurasi "3. Gerbang ke GPU Kaggle").
"""),
    SEL_KODE,
    kode(r"""
# Temukan adapter di semua input: output notebook pelatihan (adapters/PKN/grade_k) dan
# dataset adapter PJOK (mis. adapter-pjok/adapters_recursive/grade_k), apa pun nama foldernya.
SEMUA_ADAPTER = sorted(glob.glob('/kaggle/input/**/grade_1/adapter_config.json', recursive=True))
print('folder adapter yang ditemukan:', *SEMUA_ADAPTER, sep='\n  ')

def pola_adapter(mapel):
    lain = 'pkn' if mapel == 'PJOK' else 'pjok'
    def cocok(p):
        q = p.lower()
        if f'/{lain}/' in q or f'adapter-{lain}' in q:
            return False
        return f'/{mapel.lower()}/' in q or f'adapter-{mapel.lower()}' in q or \
            (mapel == 'PJOK' and 'adapters_recursive' in q)
    c = [p for p in SEMUA_ADAPTER if cocok(p)]
    return os.path.dirname(c[0])[:-1] + '{k}' if c else None

ADAPTER = {m: pola_adapter(m) for m in ('PJOK', 'PKN')}
for m, p in ADAPTER.items():
    n = sum(os.path.exists(p.format(k=k)) for k in range(1, 7)) if p else 0
    print(f'adapter {m}: {n}/6  {p or "(tidak ada - model dasar dipakai)"}')
"""),
    SEL_PUSTAKA,
    kode(r"""
# Rahasia
os.environ['TB_KUNCI'] = ''
try:
    from kaggle_secrets import UserSecretsClient
    s = UserSecretsClient()
    for nama in ['TB_KUNCI', 'HF_TOKEN']:
        try: os.environ[nama] = s.get_secret(nama)
        except Exception: pass
except Exception:
    pass
print('kunci akses aktif' if os.environ.get('TB_KUNCI') else
      'PERINGATAN: TB_KUNCI kosong, siapa pun yang tahu tautannya dapat memakai GPU ini')
"""),
    SEL_INDEKS,
    kode(r"""
# Ambang pengecekan 1 (apakah potongan buku memang membahas pertanyaannya), hasil kalibrasi
# notebook pelatihan. Bila tidak ada, kalibrasi di sini (sekitar 5-10 menit).
tujuan = os.path.join(folder_indeks(os.environ['TB_MODEL_EMBEDDING']), 'ambang_relevan.json')
# hanya ambang hasil kalibrasi korpus Merdeka (ambang lama dibuat dengan korpus campuran)
ada = [p for p in glob.glob('/kaggle/input/**/hasil/ambang_relevan.json', recursive=True)
       if 'Merdeka' in json.load(open(p)).get('metode', '')]
if ada:
    shutil.copy(ada[0], tujuan)
elif not os.path.exists(tujuan):
    from tb.evaluasi_pencarian import evaluasi
    evaluasi()
    os.makedirs('/kaggle/working/hasil', exist_ok=True)       # unduh dari panel Output
    for f in ['evaluasi_pencarian.json', 'Evaluasi_Pencarian.xlsx', 'Validasi_Soal_PJOK_Recursive.xlsx']:
        shutil.copy(f'hasil/{f}', f'/kaggle/working/hasil/{f}')
    import gc; gc.collect(); torch.cuda.empty_cache()
print('ambang pengecekan 1:', json.load(open(tujuan))['ambang'])
"""),
    kode(r"""
# Nyalakan server di latar belakang (memuat Qwen 7B dan 12 adapter, sekitar 5-8 menit)
import requests
perintah = [sys.executable, '-m', 'tb.server', '--qwen', '--host', '0.0.0.0', '--port', '8000',
            '--cari', 'semantik']
if ADAPTER['PJOK']: perintah += ['--adapter-pjok', ADAPTER['PJOK']]
if ADAPTER['PKN']:  perintah += ['--adapter-pkn', ADAPTER['PKN']]
log = open('server.log', 'w')
server = subprocess.Popen(perintah, stdout=log, stderr=subprocess.STDOUT, env=os.environ.copy())

for i in range(120):
    time.sleep(10)
    if server.poll() is not None:
        print(open('server.log').read()[-4000:])
        raise RuntimeError('server berhenti, lihat log di atas')
    try:
        s = requests.get('http://127.0.0.1:8000/api/sehat', timeout=5).json()
        print('SIAP:', json.dumps(s, indent=1))
        break
    except Exception:
        print(f'menunggu... {10 * (i + 1)} detik', end='\r')
"""),
    kode(r"""
# Buka ke internet lewat Cloudflare Quick Tunnel (gratis, tanpa akun)
if not os.path.exists('/kaggle/working/cloudflared'):
    subprocess.run(['wget', '-q', '-O', '/kaggle/working/cloudflared',
                    'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64'],
                   check=True)
    os.chmod('/kaggle/working/cloudflared', 0o755)
tlog = open('tunnel.log', 'w')
tunnel = subprocess.Popen(['/kaggle/working/cloudflared', 'tunnel', '--no-autoupdate',
                           '--url', 'http://127.0.0.1:8000'], stdout=tlog, stderr=subprocess.STDOUT)
URL = None
for _ in range(60):
    time.sleep(2)
    m = re.search(r'https://[a-z0-9-]+\.trycloudflare\.com', open('tunnel.log').read())
    if m:
        URL = m.group(0); break
print('=' * 78)
print('Server GPU aktif di :', URL)
print()
print('Tempel di terminal VS Code laptop (folder LearningBuddy):')
print(f'   python -m tb.server --remote {URL} --remote-kunci <isi TB_KUNCI Anda>')
print('lalu buka http://127.0.0.1:8000 (chat) dan http://127.0.0.1:8000/lab.html (lab)')
print('=' * 78)
"""),
    kode(r"""
# Uji keempat agen pada kedua mata pelajaran, termasuk pagar pengaruh adapter
h = {'X-Kunci': os.environ.get('TB_KUNCI', '')}
def tanya(q, mapel='PJOK', kelas=None, skenario='S4'):
    return requests.post('http://127.0.0.1:8000/api/tanya', headers=h, timeout=600,
                         json={'pertanyaan': q, 'mata_pelajaran': mapel,
                               'kelas': kelas, 'skenario': skenario}).json()

for q, m in [('napa hrs pemanasan dlu sblm olhraga?', 'PJOK'),
             ('apa arti gotong royong', 'PKN'), ('halo', 'PJOK')]:
    r = tanya(q, m)
    print(f'[{m}] {q}')
    print('  Perceive :', r['pertanyaan_bersih'], '| jelas', r['jelas'])
    print('  Plan     :', 'kelas', r['kelas'], r['sumber_kelas'], r['keyakinan_kelas'], '| topik', r['topik'])
    print('  Act      :', r['putaran'], 'putaran | adapter', r['adapter_aktif'],
          '| konteks', r['konteks'] and r['konteks']['id'])
    print('  Reflect  :', r['status'], r['ukuran'] and (r['ukuran']['pkr'], r['ukuran']['kld']))
    print('  jawaban  :', r['jawaban'], '\n')

for m, q in [('PJOK', 'Apa manfaat pemanasan?'), ('PKN', 'Apa arti musyawarah?')]:
    a = tanya(q, m, kelas=4, skenario='S1')['riwayat'][0]['jawaban']
    b = tanya(q, m, kelas=4, skenario='S2')['riwayat'][0]['jawaban']
    print(f'{m} S1: {a}\n{m} S2: {b}')
    print('  PERINGATAN: adapter tidak mengubah keluaran' if a == b else '  adapter berpengaruh')
"""),
    kode(r"""
# Penjaga sesi. Biarkan sel ini berjalan selama aplikasi dipakai.
try:
    while True:
        time.sleep(300)
        hidup = server.poll() is None and tunnel.poll() is None
        jejak = sorted(glob.glob('log/jejak_*.jsonl'))
        n = sum(1 for _ in open(jejak[-1])) if jejak else 0
        print(time.strftime('%H:%M'), 'server', 'hidup' if hidup else 'MATI', '| pertanyaan hari ini:', n)
        if not hidup:
            print(open('server.log').read()[-3000:]); break
except KeyboardInterrupt:
    print('dihentikan')
"""),
    md(r"""
**Catatan**

- Tautan `trycloudflare.com` berganti setiap kali notebook dijalankan ulang.
- Jejak setiap pertanyaan tersimpan di `/kaggle/working/LearningBuddy/log/`.
- Kuota GPU Kaggle 30 jam per minggu. Matikan sesi (*Stop Session*) bila tidak dipakai.
"""),
]
simpan("kaggle_server.ipynb", copy.deepcopy(SEL_SERVER))

# =============================================================================
# Notebook pengujian sistem S1-S4
# =============================================================================
# sel 1-7 notebook server: kode, adapter, pustaka, rahasia, indeks, ambang, server (tanpa tunnel)
simpan("kaggle_uji_sistem.ipynb", copy.deepcopy([
    md(r"""
# Learning Buddy - pengujian sistem S1 sampai S4

Menjalankan seluruh data uji PJOK (197 soal) dan Pendidikan Pancasila (158 soal) lewat siklus
agen penuh pada empat skenario, sama dengan Lab > Uji sistem, tetapi tanpa membuka website.

**Persiapan** sama dengan notebook server: input **learning-buddy-kode** (versi terbaru),
**adapter-pjok**, dan output notebook pelatihan; Accelerator **GPU T4 x2**; Internet **On**.

Jalankan dengan **Save Version > Save & Run All (Commit)** agar tetap berjalan walau laptop
dimatikan. Hasil ada di panel **Output**: `hasil/uji/uji_*_PJOK.json` dan `uji_*_PKN.json`.
"""),
] + SEL_SERVER[1:8] + [
    kode(r"""
# Pengujian S1-S4: satu mapel selesai, hasilnya langsung disalin ke Output
import requests
URL_LOKAL = 'http://127.0.0.1:8000'
h = {'X-Kunci': os.environ.get('TB_KUNCI', '')}
SKENARIO = ['S1', 'S2', 'S3', 'S4']
N_PER_KELAS = 0          # 0 = seluruh data uji
BATAS_JAM = 11           # sesi Commit Kaggle berhenti paksa pada 12 jam
KELUAR = '/kaggle/working/hasil/uji'
os.makedirs(KELUAR, exist_ok=True)
t_awal = time.time()

for mapel in ['PJOK', 'PKN']:
    r = requests.post(URL_LOKAL + '/api/uji/mulai', headers=h, timeout=60,
                      json={'mata_pelajaran': mapel, 'n_per_kelas': N_PER_KELAS,
                            'skenario': SKENARIO, 'kelas_dari': 'data'})
    r.raise_for_status()
    print(mapel, 'mulai:', r.json()['n_soal'], 'soal x', len(SKENARIO), 'skenario')
    while True:
        time.sleep(60)
        s = requests.get(URL_LOKAL + '/api/uji/status', headers=h, timeout=60).json()
        print(time.strftime('%H:%M'), mapel, f"{s['selesai']}/{s['total']}", '| galat', s['galat'],
              '|', s.get('pesan', '')[:70])
        if not s['berjalan']:
            break
        if time.time() - t_awal > BATAS_JAM * 3600:
            print('mendekati batas 12 jam: dihentikan, hasil yang sudah ada disimpan')
            requests.post(URL_LOKAL + '/api/uji/hentikan', headers=h, timeout=60)
    for f in glob.glob('hasil/uji/uji_*.json'):
        shutil.copy(f, KELUAR)
    for sk, v in (s.get('ringkasan') or {}).items():
        a = v['semua']
        print(f"  {sk}: n {a['n']} | F1 {a['f1']:.3f} | chrF++ {a['chrf']:.2f} | patuh {a['patuh']:.3f}"
              f" | putaran {a['putaran']:.2f} | detik {a['detik']:.1f}")
    if time.time() - t_awal > BATAS_JAM * 3600:
        break

shutil.copy('server.log', '/kaggle/working/hasil/server_uji.log')
print('berkas hasil:', *sorted(os.listdir(KELUAR)), sep='\n  ')
"""),
    kode(r"""
# Matikan server dan buang salinan kode agar Output hanya berisi hasil/
server.terminate()
os.chdir('/kaggle/working')
shutil.rmtree('/kaggle/working/LearningBuddy', ignore_errors=True)
shutil.rmtree('/kaggle/working/faiss_cache', ignore_errors=True)
print(sorted(glob.glob('/kaggle/working/hasil/**', recursive=True)))
"""),
]))
