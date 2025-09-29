import json
import re
from linkG import main as load_data
from OCR import process_one
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import os
import pytz
import time
import subprocess
from pathlib import Path
import sys


""" Garante import do fuso hrário correto """
TZ = pytz.timezone("America/Sao_Paulo")

DATE_FROM_NAME = re.compile(
    r"_(\d{2})_(\d{2})_(\d{4})-(\d{2})_(\d{2})_(\d{2})"  # _DD_MM_YYYY-HH_MM_SS
)

CONTA = "Tecnogera Geradores"  # ajuda no agrupamento por conta

def _infer_data(dropbox_item: dict, arquivo: str, pasta_data: datetime) -> str:
    """
    Retorna string no formato YYYY-MM-DD para o campo `data`.
    Prioridade: client_modified -> nome arquivo -> pasta (ontem) -> hoje.
    """
    # 1) client_modified (ISO) -> YYYY-MM-DD
    cm = dropbox_item.get("client_modified")
    if cm:
        try:
            dt = datetime.fromisoformat(cm.replace("Z","+00:00")).astimezone(TZ)
            return dt.date().isoformat()
        except Exception:
            pass

    # 2) nome do arquivo
    m = DATE_FROM_NAME.search(arquivo or "")
    if m:
        dd, mm, yyyy, hh, mi, ss = m.groups()
        try:
            dt = datetime(int(yyyy), int(mm), int(dd), int(hh), int(mi), int(ss), tzinfo=TZ)
            return dt.date().isoformat()
        except Exception:
            pass

    # 3) data da pasta (ex.: 2025-09-28)
    if isinstance(pasta_data, datetime):
        return pasta_data.date().isoformat()

    # 4) fallback hoje
    return datetime.now(TZ).date().isoformat()


def _normalize_for_db(dropbox_item: dict, ocr_item: dict, pasta_data_dt: datetime) -> dict:

    agora_iso = datetime.now(TZ).isoformat()
    arquivo = dropbox_item.get("nome_link")

    return {

        "conta": "Tecnogera Geradores",
        "arquivo": arquivo,
        "dropbox_link": dropbox_item.get("temporary_link"),
        "filial": dropbox_item.get("path_lower"),
        "content_hash": dropbox_item.get("content_hash"),
        "client_modified": dropbox_item.get("client_modified"),
        "checklist": dropbox_item.get("codigo"),
        "cod_patrimonio": ocr_item.get("patrimonio"),
        "ocr_raw": ocr_item.get("raw"),
        "processado_em": agora_iso,
        # NOVO:
        "data": _infer_data(dropbox_item, arquivo, pasta_data_dt),

    }

def run():
    itens = load_data()
    if not isinstance(itens, list):
        raise TypeError(f"Esperava lista de itens, recebi: {type(itens)}")

    from datetime import datetime, timedelta
    import pytz
    TZ = pytz.timezone("America/Sao_Paulo")
    pasta_data_dt = datetime.now(TZ) - timedelta(days=1)

    registros_bd = []

    # processa em blocos de 10 (ajuste se quiser)
    for i in range(0, len(itens), 10):
        bloco = itens[i:i+10]

        for item in bloco:
            registro = None  # garante variável definida
            link = (item or {}).get("temporary_link")
            if not link:
                print("[warn] Item sem temporary_link, ignorando.")
                continue

            try:
                ocr = process_one(link)
                registro = _normalize_for_db(item, ocr, pasta_data_dt)
            except Exception as e:
                # não deixa explodir o loop — loga e segue
                nome = (item or {}).get("nome_link", "<sem nome>")
                print(f"[warn] Falha ao processar '{nome}': {e}")
                continue

            if registro:
                registros_bd.append(registro)

        print(f"[ok] Bloco {i//10 + 1} processado ({len(registros_bd)} itens até agora)")

        # se usa janela/limite de taxa, mantenha:
        if i + 10 < len(itens):
            # time.sleep(120)  # descomente se precisar do intervalo
            pass

    return {"records": registros_bd, "count": len(registros_bd)}


def salvar_json(saida: dict, base_dir: str = "out") -> tuple[str, str]:
    """
    Salva:
      - out/YYYY-MM-DD/resultado_db.json  -> objeto { records: [...], count: N }
      - out/YYYY-MM-DD/resultado.json     -> APENAS a lista de registros [...], compatível com o import
    """
    from datetime import datetime, timedelta
    import os, json, pytz
    TZ = pytz.timezone("America/Sao_Paulo")

    agora = datetime.now(TZ)
    ontem = (agora - timedelta(days=1)).date()
    pasta = os.path.join(base_dir, ontem.strftime("%Y-%m-%d"))
    os.makedirs(pasta, exist_ok=True)

    # garante a estrutura
    records = []
    if isinstance(saida, dict):
        records = saida.get("records", [])
    elif isinstance(saida, list):
        records = saida
        saida = {"records": records, "count": len(records)}
    else:
        raise TypeError(f"Formato inesperado de saída: {type(saida)}")

    # 1) objeto completo
    arquivo_db = os.path.join(pasta, "resultado_db.json")
    with open(arquivo_db, "w", encoding="utf-8") as f:
        json.dump(saida, f, ensure_ascii=False, indent=2)

    # 2) APENAS a lista (compatível com importar_patrimonios)
    arquivo_legacy = os.path.join(pasta, "resultado.json")
    with open(arquivo_legacy, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    print(f"[debug] Itens gravados no resultado.json: {len(records)}")
    return arquivo_db, arquivo_legacy

def enviar_para_banco(caminho_json: str,
                      python_exec: str = None,
                      manage_py: str = r"C:\Users\gustavo.galeazzi\OCR-Database\manage.py"):
    """
    Dispara o comando Django para importar o JSON gerado.
    - python_exec: caminho do python do ambiente do projeto Django. Se None, usa sys.executable.
    - manage_py: caminho absoluto para o manage.py do projeto Django.
    """
    python_exec = python_exec or sys.executable
    manage_py = str(Path(manage_py))

    cmd = [
        python_exec,
        manage_py,
        "importar_patrimonios",
        "--arquivo",
        caminho_json,
    ]
    try:
        print(f"[import] Executando: {' '.join(cmd)}")
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        print("[import] OK:", res.stdout.strip())
        if res.stderr:
            print("[import][warn]:", res.stderr.strip())
    except subprocess.CalledProcessError as e:
        print("[import][ERRO] Retorno:", e.returncode)
        print("[import][STDOUT]:", e.stdout)
        print("[import][STDERR]:", e.stderr)
        raise





def main():
    saida = run()  # deve ser {"records": [...], "count": N}
    arq_db, arq_legacy = salvar_json(saida)
    print(f"JSON salvo em: {arq_legacy}")

    enviar_para_banco(
        caminho_json=arq_db,  # use o arquivo compatível
        python_exec=r"C:\Users\gustavo.galeazzi\OCR-Database\.venv\Scripts\python.exe",
        manage_py=r"C:\Users\gustavo.galeazzi\OCR-Database\manage.py",
)


if __name__ == "__main__":
    main()
