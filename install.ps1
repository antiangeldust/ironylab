<#
.SYNOPSIS
    Установка IronyLab: ядро + семантика (эмбеддинги) + локальная LLM.

.DESCRIPTION
    Скрипт идемпотентен: его можно запускать повторно, уже установленное не
    перекачивается. Что он делает:

      1. находит (или создаёт) виртуальное окружение проекта;
      2. обновляет pip;
      3. ставит CPU-сборку torch (экономит ~2 ГБ против CUDA-сборки);
      4. ставит sentence-transformers — семантический анализатор;
      5. ставит llama-cpp-python из готовых колёс (без компилятора):
         CPU или CUDA; для CUDA дополнительно ставит cudart/cublas из pip
         и подкладывает их к llama.dll — установка CUDA Toolkit не нужна;
      6. при желании скачивает GGUF-модель и модель эмбеддингов;
      7. проверяет импорты и печатает итог.

.PARAMETER Mode
    core — только программа (стандартный Python, сторонние пакеты не нужны);
    semantic — + эмбеддинги; llm — + локальная LLM; full — всё (по умолчанию).

.PARAMETER LlmWheel
    Какое колесо llama-cpp-python брать. auto — cu124 при видеокарте NVIDIA,
    иначе cpu. Если CUDA-запуск не заведётся, повторите с -LlmWheel cpu.

.PARAMETER Model
    Стартовая GGUF-модель: none | qwen0.5b | qwen1.5b | qwen3b.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File install.ps1
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File install.ps1 -Mode semantic
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File install.ps1 -LlmWheel cpu -Model qwen1.5b
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File install.ps1 -Embeddings
#>
#Requires -Version 5.1
[CmdletBinding()]
param(
    [ValidateSet('core', 'semantic', 'llm', 'full')]
    [string]$Mode = 'full',

    [ValidateSet('auto', 'cpu', 'cu121', 'cu122', 'cu123', 'cu124', 'cu125', 'metal')]
    [string]$LlmWheel = 'auto',

    [ValidateSet('none', 'qwen0.5b', 'qwen1.5b', 'qwen3b')]
    [string]$Model = 'none',

    # Заранее скачать модель эмбеддингов (~470 МБ) в models\ — пригодится офлайн
    [switch]$Embeddings,

    # Пересоздать окружение с нуля
    [switch]$Recreate,

    # Не ставить pytest и pyinstaller
    [switch]$NoDev
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$ModelsDir = Join-Path $Root 'models'
# Флаги pip: без кэша (он дублирует сотни мегабайт колёс и на некоторых
# системах приводит к зависанию), без проверки версии pip, без вопросов.
$PipCommon = @('--no-input', '--disable-pip-version-check', '--no-cache-dir')

function Write-Step([string]$Text) { Write-Host "`n==> $Text" -ForegroundColor Cyan }
function Write-Ok([string]$Text) { Write-Host "    $Text" -ForegroundColor Green }
function Write-Note([string]$Text) { Write-Host "    $Text" -ForegroundColor DarkGray }
function Write-Warn([string]$Text) { Write-Host "    $Text" -ForegroundColor Yellow }

function Get-ProjectPython {
    foreach ($candidate in @((Join-Path $Root 'Scripts\python.exe'), (Join-Path $Root '.venv\Scripts\python.exe'))) {
        if (Test-Path $candidate) { return $candidate }
    }
    return $null
}

function New-ProjectVenv {
    $venv = Join-Path $Root '.venv'
    $launcher = $null
    foreach ($name in 'py', 'python', 'python3') {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd) { $launcher = $cmd.Source; break }
    }
    if (-not $launcher) {
        throw 'Python не найден. Установите Python 3.12 с python.org и отметьте «Add python.exe to PATH».'
    }
    Write-Note "Создаю окружение: $venv"
    if ($launcher -like '*\py.exe') { & $launcher -3 -m venv $venv } else { & $launcher -m venv $venv }
    if ($LASTEXITCODE -ne 0) { throw 'Не удалось создать виртуальное окружение.' }
    return (Join-Path $venv 'Scripts\python.exe')
}

function Invoke-Pip {
    param([string[]]$Arguments, [string]$What)
    Write-Note "pip $($Arguments -join ' ')"
    & $script:Python -m pip @PipCommon @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Не удалось установить: $What" }
}

function Test-PythonModule([string]$Name) {
    & $script:Python -c "import importlib.util,sys; sys.exit(0 if importlib.util.find_spec('$Name') else 1)" 2>$null
    return ($LASTEXITCODE -eq 0)
}

function Resolve-LlmWheel([string]$Choice) {
    if ($Choice -ne 'auto') { return $Choice }
    $gpu = Get-CimInstance Win32_VideoController -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match 'NVIDIA' }
    if ($gpu) {
        Write-Note "Найдена видеокарта NVIDIA: $($gpu[0].Name) — беру CUDA-колесо (cu124)."
        return 'cu124'
    }
    if ($env:OS -eq 'Windows_NT') { Write-Note 'Видеокарта NVIDIA не найдена — беру CPU-колесо.' }
    return 'cpu'
}

function Connect-CudaRuntime {
    <# Колесо llama-cpp-python ищет cudart64_12/cublas64_12 только рядом с llama.dll,
       поэтому кладём их туда жёсткими ссылками (место на диске не тратится). #>
    $libDir = Join-Path $Root 'Lib\site-packages\llama_cpp\lib'
    if (-not (Test-Path $libDir)) { $libDir = Join-Path $Root '.venv\Lib\site-packages\llama_cpp\lib' }
    if (-not (Test-Path $libDir)) { Write-Warn 'Не найден каталог llama_cpp\lib — пропускаю подключение CUDA.'; return }
    $site = Split-Path -Parent (Split-Path -Parent $libDir)
    $sources = @{
        'cudart64_12.dll'   = Join-Path $site 'nvidia\cuda_runtime\bin\cudart64_12.dll'
        'cublas64_12.dll'   = Join-Path $site 'nvidia\cublas\bin\cublas64_12.dll'
        'cublasLt64_12.dll' = Join-Path $site 'nvidia\cublas\bin\cublasLt64_12.dll'
    }
    foreach ($name in $sources.Keys) {
        $src = $sources[$name]
        $dst = Join-Path $libDir $name
        if (-not (Test-Path $src)) { Write-Warn "Не найден $src"; continue }
        if (Test-Path $dst) { Remove-Item -Force $dst }
        try {
            New-Item -ItemType HardLink -Path $dst -Target (Resolve-Path $src).Path -ErrorAction Stop | Out-Null
            Write-Ok "$name — жёсткая ссылка"
        }
        catch {
            Copy-Item $src $dst -Force
            Write-Ok "$name — копия"
        }
    }
}

# ------------------------------------------------------------------ окружение
$python = Get-ProjectPython
if ($Recreate -and $python) {
    $dir = Split-Path -Parent (Split-Path -Parent $python)
    Write-Step "Удаляю прежнее окружение: $dir"
    Remove-Item -Recurse -Force $dir
    $python = $null
}
if (-not $python) {
    Write-Step 'Виртуальное окружение'
    $python = New-ProjectVenv
}
$script:Python = $python
Write-Step "Интерпретатор: $python"
& $python -c "import sys; print('    Python', sys.version.split()[0])"
if ($LASTEXITCODE -ne 0) { throw 'Интерпретатор не запускается.' }

Write-Step 'Обновляю pip'
Invoke-Pip -What 'pip' -Arguments @('install', '--upgrade', 'pip', 'wheel')

if ($Mode -eq 'core') {
    Write-Note 'Режим core: сторонние библиотеки не нужны, ядро работает на стандартном Python.'
}

if ($Mode -in @('semantic', 'full')) {
    Write-Step 'Семантический анализатор: torch (CPU) + sentence-transformers'
    if (Test-PythonModule 'torch') {
        Write-Ok 'torch уже установлен — пропускаю.'
    }
    else {
        # CPU-сборка: ~200 МБ вместо ~2,5 ГБ CUDA-сборки. Для эмбеддингов этого достаточно.
        Invoke-Pip -What 'torch (CPU)' -Arguments @(
            'install', 'torch', '--index-url', 'https://download.pytorch.org/whl/cpu'
        )
    }
    Invoke-Pip -What 'sentence-transformers' -Arguments @('install', 'sentence-transformers')
    Write-Ok 'Семантика готова.'
}

if ($Mode -in @('llm', 'full')) {
    if (Test-PythonModule 'llama_cpp') {
        Write-Step 'Локальная LLM: llama-cpp-python уже установлен — пропускаю.'
    }
    else {
        $wheel = Resolve-LlmWheel $LlmWheel
        $index = "https://abetlen.github.io/llama-cpp-python/whl/$wheel"
        Write-Step "Локальная LLM: llama-cpp-python ($wheel, ~$([math]::Round(511 / 1024, 2)) ГБ колесо)"
        Write-Note "Индекс готовых колёс: $index"
        Invoke-Pip -What 'llama-cpp-python' -Arguments @(
            'install', '--only-binary=:all:', '--extra-index-url', $index, 'llama-cpp-python'
        )
        if ($wheel -like 'cu*') {
            Write-Step 'CUDA-библиотеки для llama.cpp (cudart + cublas)'
            Write-Note 'Ставятся из pip: отдельный CUDA Toolkit не нужен.'
            Invoke-Pip -What 'CUDA runtime' -Arguments @('install', 'nvidia-cuda-runtime-cu12', 'nvidia-cublas-cu12')
            Connect-CudaRuntime
            Write-Warn 'Нужен драйвер NVIDIA 2024 года или новее. Если запуск упадёт — повторите с -LlmWheel cpu.'
        }
        Write-Ok 'Локальная LLM готова.'
    }
}

if (-not $NoDev) {
    Write-Step 'Инструменты разработки: pytest, pyinstaller'
    Invoke-Pip -What 'pytest/pyinstaller' -Arguments @('install', '-r', (Join-Path $Root 'requirements-dev.txt'))
}

# -------------------------------------------------------------------- модели
$modelFile = $null
if ($Model -ne 'none') {
    $repos = @{
        'qwen0.5b' = @('Qwen/Qwen2.5-0.5B-Instruct-GGUF', 'qwen2.5-0.5b-instruct-q4_k_m.gguf', '0,4')
        'qwen1.5b' = @('Qwen/Qwen2.5-1.5B-Instruct-GGUF', 'qwen2.5-1.5b-instruct-q4_k_m.gguf', '1,1')
        'qwen3b'   = @('Qwen/Qwen2.5-3B-Instruct-GGUF', 'qwen2.5-3b-instruct-q4_k_m.gguf', '2,0')
    }
    $repo, $modelFile, $size = $repos[$Model]
    New-Item -ItemType Directory -Force -Path $ModelsDir | Out-Null
    if (Test-Path (Join-Path $ModelsDir $modelFile)) {
        Write-Step "Модель уже скачана: $modelFile"
    }
    else {
        Write-Step "Скачиваю модель $modelFile (~$size ГБ)"
        Write-Note "Источник: https://huggingface.co/$repo"
        & $python -c @"
from huggingface_hub import hf_hub_download
print(hf_hub_download('$repo', '$modelFile', local_dir=r'$ModelsDir'))
"@
        if ($LASTEXITCODE -ne 0) {
            Write-Warn "Скачать не удалось. Возьмите файл вручную: https://huggingface.co/$repo"
            $modelFile = $null
        }
        else { Write-Ok "Модель: $(Join-Path $ModelsDir $modelFile)" }
    }
}

if ($Embeddings) {
    Write-Step 'Скачиваю модель эмбеддингов (~470 МБ)'
    New-Item -ItemType Directory -Force -Path $ModelsDir | Out-Null
    & $python -c @"
from huggingface_hub import snapshot_download
print(snapshot_download('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2',
                        local_dir=r'$ModelsDir\paraphrase-multilingual-MiniLM-L12-v2'))
"@
    if ($LASTEXITCODE -ne 0) { Write-Warn 'Не удалось скачать модель эмбеддингов.' }
    else { Write-Ok "Модель: $(Join-Path $ModelsDir 'paraphrase-multilingual-MiniLM-L12-v2')" }
}

# ------------------------------------------------------------------ проверка
Write-Step 'Проверка установки'
& $python -c @'
import importlib.util as u
checks = [("ядро (tkinter)", "tkinter"), ("семантика: torch", "torch"),
          ("семантика: sentence-transformers", "sentence_transformers"),
          ("локальная LLM: llama-cpp-python", "llama_cpp"),
          ("тесты: pytest", "pytest")]
for title, module in checks:
    mark = "OK  " if u.find_spec(module) else "--  "
    print(f"    [{mark}] {title}")
'@

if (Test-PythonModule 'llama_cpp') {
    $gguf = Get-ChildItem -Path $ModelsDir -Filter '*.gguf' -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($gguf) {
        Write-Step "Проверяю локальную LLM на модели $($gguf.Name)"
        & $python (Join-Path $Root 'check_llm.py') $gguf.FullName
        if ($LASTEXITCODE -ne 0) { Write-Warn 'Модель не загрузилась. Смотрите раздел «Диагностика» в INSTALL_RU.md.' }
    }
}

Write-Host ''
Write-Host 'Готово.' -ForegroundColor Green
Write-Host 'Дальше:' -ForegroundColor Cyan
Write-Host ("  1) Окно программы:   & '{0}' app.py" -f $python)
Write-Host ("  2) Проверка ядра:    & '{0}' cli.py --text 'Ну да, конечно, прекрасная погода — опять ливень.'" -f $python)
Write-Host ("  3) Включить модели:  & '{0}' configure_local_models.py" -f $python)
Write-Host '     (включает семантику и локальную LLM и подставляет пути к скачанным моделям)'
Write-Host ("  4) Проверка LLM:     & '{0}' check_llm.py" -f $python)
Write-Host ("  5) Тесты:            & '{0}' -m pytest -q" -f $python)
if ($modelFile) { Write-Host ("  Модель LLM:          {0}" -f (Join-Path $ModelsDir $modelFile)) }
Write-Host 'Подробности, разбор ошибок и офлайн-установка: INSTALL_RU.md' -ForegroundColor DarkGray
