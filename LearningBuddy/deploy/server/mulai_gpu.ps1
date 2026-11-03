# Menyalakan layanan MODEL Learning Buddy di server GPU WINDOWS (tanpa Docker).
# Jalankan dari folder LearningBuddy di PowerShell:
#   $env:TB_KUNCI = "<kunci yang sama dengan .env.web>"
#   powershell -ExecutionPolicy Bypass -File deploy\server\mulai_gpu.ps1 `
#       -FolderAdapter C:\learningbuddy\adapters -FolderHasil C:\learningbuddy\hasil
# Pemasangan pertama (sekali saja), lihat PANDUAN_DEPLOY.md bagian C2.
param(
    [Parameter(Mandatory = $true)][string]$FolderAdapter,   # berisi PJOK\grade_1..6 dan PKN\grade_1..6
    [Parameter(Mandatory = $true)][string]$FolderHasil,     # berisi ambang_relevan.json
    [string]$Python = ".venv\Scripts\python.exe",
    [int]$Port = 8000
)
$ErrorActionPreference = "Stop"
if (-not $env:TB_KUNCI) { throw "Isi dulu `$env:TB_KUNCI agar hanya server web yang bisa memakai GPU ini." }

$model = if ($env:TB_MODEL_EMBEDDING) { $env:TB_MODEL_EMBEDDING } else { "Qwen/Qwen3-Embedding-4B" }
$folder = & $Python -c "from tb.pencarian import folder_indeks; print(folder_indeks('$model'))"
if (-not (Test-Path (Join-Path $folder "meta.json"))) {
    Write-Host "== indeks FAISS belum ada: membangun (sekali saja, beberapa menit)"
    & $Python -m tb.basis --vektor --model $model
    if ($LASTEXITCODE -ne 0) { throw "gagal membangun indeks FAISS" }
}
$ambang = Join-Path $FolderHasil "ambang_relevan.json"
if (Test-Path $ambang) { Copy-Item $ambang (Join-Path $folder "ambang_relevan.json") -Force }

foreach ($m in "PJOK", "PKN") {
    $n = (Get-ChildItem (Join-Path $FolderAdapter $m) -Directory -Filter "grade_*" -ErrorAction SilentlyContinue).Count
    Write-Host "adapter ${m}: $n/6"
}

& $Python -m tb.server --qwen --cari semantik --tanpa-login --host 0.0.0.0 --port $Port `
    --adapter-pjok (Join-Path $FolderAdapter "PJOK\grade_{k}") `
    --adapter-pkn (Join-Path $FolderAdapter "PKN\grade_{k}")
