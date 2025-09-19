import json
from test2 import main as load_data
from ss import process_one
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import os
import pytz
import time

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



def main():
    saida = run()
    caminho = salvar_json(saida)

    # opcional: imprime só um resumo/confirmacao no terminal
    print(f"JSON salvo em: {caminho}")

if __name__ == "__main__":
    main()
