import os
from openai import OpenAI
from dotenv import load_dotenv
import re
import json

with open("id.json", "r", encoding="utf-8") as f:
    dados = json.load(f)

# Carrega variáveis do arquivo .env

load_dotenv()

API_OPENAI = os.getenv("API_OPENAI")  # defina no ambiente

MAX_RETRIES = 3

client = OpenAI(api_key=API_OPENAI)

image_url = [
             
             "https://www.dropbox.com/scl/fi/fdvet3miugccpvtofhrrx/147020802_checklist_211175_c57_0_09_09_2025-20_40_54.jpeg?rlkey=8betak2curxfubsve6f0m15m1&dl=1",
             "https://www.dropbox.com/scl/fi/sqyzglo5h2zn6em0h8zrq/147017779_checklist_211135_c57_0_09_09_2025-20_24_30.jpeg?rlkey=kgmrzwzysbwup4gjidlprollg&dl=1",
             
             ]
             
             

def process_one(url: str) -> dict:
    try:
        resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages= [
                {
                    "role": "user",
                    "content":  [
                        {"type": "text", "text": "Extraia o texto desta imagem e retorne em JSON. quero que sempre retorne apenas o patrimonio."},
                        {"type": "text", "text": "Tennha como objetivo claro e principal a leitura desses códigos que irei te passar. Todas as máquinas terão código que começam com um desses códigos. Leia estritamente na imagem esses códigos, tudo que não começãr com um dos códigos passados pelo json, ignore, vasculhe a imagem inteira em busca dos códigos certos "},
                        {"type": "text", "text": json.dumps(dados, ensure_ascii=False)},
                        {"type":"image_url","image_url": {"url": url}}
                    ]
                }
            ],
        )
        return {"url": url, "saida": resp.choices[0].message.content}
    
    except Exception as e:
        # Loga o erro e retorna no JSON
        err_msg = str(e)
        print(f"❌ Erro ao processar {url}: {err_msg}")
        return {"url": url, "erro": err_msg}

def main():
    resultados = []
    for url in image_url:
        resultado = process_one(url)
        resultados.append(process_one(url))
    print(json.dumps({"resultados": resultados}, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
