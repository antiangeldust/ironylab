# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['torch', 'torchvision', 'torchaudio', 'functorch', 'transformers', 'sentence_transformers', 'llama_cpp', 'tokenizers', 'safetensors', 'huggingface_hub', 'hf_xet', 'sklearn', 'scipy', 'sympy', 'networkx', 'mpmath', 'numpy', 'joblib', 'threadpoolctl', 'regex', 'tqdm', 'PIL', 'pandas', 'matplotlib', 'yaml', 'rich', 'pygments', 'markdown_it', 'mdurl', 'typer', 'click', 'shellingham', 'httpx', 'httpcore', 'h11', 'anyio', 'filelock', 'fsspec', 'narwhals', 'cloudpickle', 'pytest', '_pytest', 'pluggy', 'iniconfig', 'setuptools', 'pip'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='IronyLab',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='IronyLab',
)
