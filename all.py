import json
from LinkG import main as load_data
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

def run():
    dados = load_data()
    if not isinstance(dados, list):
        raise TypeError(f"Esperava lista de itens, recebi: {type(dados)}")

    resultados = []
    # percorre em blocos de 10
    for i in range(0, len(dados), 5):
        bloco = dados[i:i+5]
        for item in bloco:
            link = item.get("temporary_link")
            if not link:
                continue
            resultados.append(process_one(link))

        print(f"[ok] Bloco {i//5 + 1} processado ({len(resultados)} itens até agora)")

        # Delay de 2 minutos, exceto depois do último bloco
        if i + 5 < len(dados):
            print("Aguardando 2 minutos antes de processar o próximo bloco...")
            time.sleep(120)

    return {"resultados": resultados}


def salvar_json(saida: dict, base_dir: str = "out") -> str:
    """
    Cria uma pasta com a data de ontem (YYYY-MM-DD) dentro de base_dir
    e salva o JSON como 'resultado.json'. Retorna o caminho completo do arquivo.
    """
    agora = datetime.now(TZ)
    ontem = (agora - timedelta(days=1)).date()
    pasta = os.path.join(base_dir, ontem.strftime("%Y-%m-%d"))
    os.makedirs(pasta, exist_ok=True)

    # nome fixo; se preferir histórico, troque por um com timestamp
    arquivo = os.path.join(pasta, "resultado.json")
    with open(arquivo, "w", encoding="utf-8") as f:
        json.dump(saida, f, ensure_ascii=False, indent=2)
    return arquivo


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
    saida = run()
    caminho = salvar_json(saida)

    # opcional: imprime só um resumo/confirmacao no terminal
    print(f"JSON salvo em: {caminho}")
    enviar_para_banco(
        caminho_json=caminho,
        # Exemplo se o Django estiver em outro ambiente:
        # python_exec=r"C:\Users\gustavo.galeazzi\OCR-Database\.venv\Scripts\python.exe",
        # manage_py=r"C:\Users\gustavo.galeazzi\OCR-Database\manage.py",
    )

if __name__ == "__main__":
    main()
