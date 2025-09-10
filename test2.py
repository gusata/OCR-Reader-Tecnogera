import os
from datetime import datetime, timedelta, timezone
import re
import sys
import dropbox
from dropbox.files import FileMetadata, SearchOrderBy, SearchOptions
from dotenv import load_dotenv
from dropbox.sharing import SharedLinkSettings
import json

# Carrega variáveis do arquivo .env
load_dotenv()

# --- CONFIG RÁPIDA ---
REFRESH_TOKEN = os.getenv("REFRESH_TOKEN")  # defina no ambiente
APP_KEY = os.getenv("APP_KEY")  # defina no ambiente
APP_SECRET = os.getenv("APP_SECRET")  # defina no ambiente
ROOT_PATH = "/Sisloc"         # pasta alvo
RECURSIVE = True        # varrer subpastas?
MAX_RESULTS = 14       # quantidade máxima de imagens a retornar
ALLOWED_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".webp", "/"}
HASH_FRAGMENT = None 
NAME_FILTER = "c57"          # str | list[str] | None  (ex.: "fatura" ou ["img_", "2025"])          # str | list[str] | None  (ex.: "fatura" ou ["img_", "2025"])
NAME_MODE = "contains"      # 'contains' | 'startswith' | 'endswith' | 'regex'
CASE_SENSITIVE = False   # ex.: "abc123" para filtrar por parte do hash (opcional)

# sempre ontem (D-1)
ONTEM = (datetime.now() - timedelta(days=1)).date()

# se quiser manter as variáveis, pode deixá-las None e usar ONTEM diretamente
START_DATE = ONTEM.strftime("%Y-%m-%d")
END_DATE = ONTEM.strftime("%Y-%m-%d")

#Config JSON
OUTPUT_JSON_ONLY = True        # ex.: "2025-08-31"

#config cursor
CURSOR_FILE = ".cursor.json"
SEEN_FILE = ".seen_yesterday.json" 


def load_state():
    cursor = None
    seen = set()
    try:
        if os.path.exists(CURSOR_FILE):
            with open(CURSOR_FILE, "r", encoding="utf-8") as f:
                cursor = json.load(f).get("cursor")
    except Exception:
        cursor = None
    try:
        if os.path.exists(SEEN_FILE):
            obj = json.load(open(SEEN_FILE, "r", encoding="utf-8"))
            if obj.get("date") == ONTEM.strftime("%Y-%m-%d"):
                seen = set(obj.get("seen", []))
            else:
                # data mudou; zera
                seen = set()
    except Exception:
        seen = set()
    return cursor, seen

def save_cursor(cursor: str):
    try:
        with open(CURSOR_FILE, "w", encoding="utf-8") as f:
            json.dump({"cursor": cursor}, f)
    except Exception:
        pass

def save_seen(seen: set):
    try:
        with open(SEEN_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "date": ONTEM.strftime("%Y-%m-%d"),
                "seen": sorted(list(seen)),
            }, f)
    except Exception:
        pass


def normalize_for_metadata(p: str) -> str | None:
    """
    Para files_get_metadata:
    - Retorna None para raiz (não chamar metadata na raiz).
    - Garante que caminhos não vazios comecem com "/".
    """
    p = (p or "").strip()
    if p in ("", "/"):
        return None
    return p if p.startswith("/") else f"/{p}"


def _normalize_shared_url_to_direct(url: str, mode: str = "dl") -> str:
    # remove dl e raw já existentes
    url = re.sub(r"[?&](dl=\d|raw=1)", "", url)
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}{'dl=1' if mode=='dl' else 'raw=1'}"

def get_or_create_shared_direct_link(dbx: dropbox.Dropbox, path_lower: str, mode: str = "dl") -> str:
    res = dbx.sharing_list_shared_links(path=path_lower, direct_only=True)
    if res.links:
        return _normalize_shared_url_to_direct(res.links[0].url, mode=mode)
    created = dbx.sharing_create_shared_link_with_settings(
        path=path_lower,
        settings=SharedLinkSettings(allow_download=True)
    )
    return _normalize_shared_url_to_direct(created.url, mode=mode)





def coletar_ontem_ordenado(dbx: dropbox.Dropbox, root_path: str, max_results: int) -> list[dict]:
    # 1) Listar toda a pasta (pode ser demorado em pastas gigantes; é o método mais compatível)
    list_path = normalize_for_list_folder(root_path)
    res = dbx.files_list_folder(path=list_path, recursive=RECURSIVE)

    arquivos = []
    def acumular(entries):
        for e in entries:
            if not isinstance(e, FileMetadata):
                continue
            # filtro por extensão/nome já aqui para reduzir memória
            if NAME_FILTER and "_c57_" not in e.name.lower():
                continue
            if not is_image(e.name):
                continue
            arquivos.append(e)

    acumular(res.entries)
    while res.has_more:
        res = dbx.files_list_folder_continue(res.cursor)
        acumular(res.entries)

    # 2) Ordenar por client_modified (descendente = mais novo → mais velho)
    arquivos.sort(key=lambda f: f.client_modified, reverse=True)

    # 3) Iterar em ordem, pegar somente "ontem" e parar quando ficar mais antigo
    resultados = []
    for e in arquivos:
        fdate = e.client_modified.date()
        if fdate > ONTEM:
            continue           # hoje → pula
        if fdate < ONTEM:
            break              # já ficou mais antigo do que ontem → encerra

        # é ontem: montar resultado
        try:
            link = get_or_create_shared_direct_link(dbx, e.path_lower, mode="dl")
            print("LINK DIRETO (OK):", link)
        except Exception as err:
            print("Falha ao obter link direto:", err)
            link = None

        m = re.search(r'checklist_(\d+)_c', e.name, flags=re.IGNORECASE)
        codigo = m.group(1) if m else None

        resultados.append({
            "content_hash": getattr(e, "content_hash", None),
            "temporary_link": link,   # já vem com ?dl=1
            "nome_link": e.name,
            "codigo": codigo,
        })
        if len(resultados) >= max_results:
            break

    return resultados





def normalize_for_list_folder(p: str) -> str:
    """
    Para files_list_folder:
    - Usa "" para raiz.
    - Caminhos não vazios devem começar com "/".
    """
    p = (p or "").strip()
    if p in ("", "/"):
        return ""
    return p if p.startswith("/Sisloc") else f"/{p}"


def is_image(name: str) -> bool:
    name = name.lower()
    return any(name.endswith(ext) for ext in ALLOWED_EXTS)


def print_json(payload: dict):
    """Imprime JSON 'bonitinho' e com UTF-8 no Windows."""
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # Windows-friendly
    except Exception:
        pass
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False))



def matches_name(filename: str) -> bool:
    if not NAME_FILTER:
        return True

    def norm(s): 
        return s if CASE_SENSITIVE else s.lower()

    name = norm(filename)
    patterns = NAME_FILTER if isinstance(NAME_FILTER, list) else [NAME_FILTER]

    if NAME_MODE == "regex":
        flags = 0 if CASE_SENSITIVE else re.IGNORECASE
        return any(re.search(p, filename, flags=flags) for p in patterns)

    if NAME_MODE == "startswith":
        return any(name.startswith(norm(p)) for p in patterns)

    if NAME_MODE == "endswith":
        return any(name.endswith(norm(p)) for p in patterns)

    # default: contains
    return any(norm(p) in name for p in patterns)



def main():
    if not REFRESH_TOKEN:
        raise SystemExit("Defina REFRESH_TOKEN no ambiente.")

    dbx = dropbox.Dropbox(
        app_key=APP_KEY,
        app_secret=APP_SECRET,
        oauth2_refresh_token=REFRESH_TOKEN
    )

    # Valida a conta (ok)
    acct = dbx.users_get_current_account()
    print("Conta:", acct.name.display_name)

    # (Opcional) validar que a pasta existe
    meta_path = normalize_for_metadata(ROOT_PATH)
    if meta_path is not None:
        dbx.files_get_metadata(meta_path)

    cursor, seen = load_state()
    results = []

    def process_entry(e):
        """Filtra ontem e adiciona ao results se ainda não visto."""
        nonlocal results, seen
        if not isinstance(e, FileMetadata):
            return
        fdate = e.client_modified.date()
        if fdate > ONTEM:
            return  # hoje
        if fdate < ONTEM:
            return  # mais antigo do que ontem
        # é ontem
        if NAME_FILTER and "_c57_" not in e.name.lower():
            return
        if not is_image(e.name):
            return

        # chave p/ deduplicar (path_lower é estável)
        key = getattr(e, "path_lower", None) or e.name
        if key in seen:
            return

        try:
            link = get_or_create_shared_direct_link(dbx, e.path_lower, mode="dl")
            print("LINK DIRETO (OK):", link)
        except Exception as err:
            print("Falha ao obter link direto:", err)
            link = None

        m = re.search(r'checklist_(\d+)_c', e.name, flags=re.IGNORECASE)
        codigo = m.group(1) if m else None

        results.append({
            "content_hash": getattr(e, "content_hash", None),
            "temporary_link": link,  # já vem ?dl=1
            "nome_link": e.name,
            "codigo": codigo,
        })
        seen.add(key)

    if cursor:
        # --------- MODO DELTA (rápido) ----------
        try:
            resp = dbx.files_list_folder_continue(cursor)
        except dropbox.exceptions.BadInputError:
            # cursor inválido? volta ao backfill uma única vez
            cursor = None
        else:
            # processa a página atual
            for e in resp.entries:
                process_entry(e)
                if len(results) >= MAX_RESULTS:
                    break
            # paginação delta
            while resp.has_more and len(results) < MAX_RESULTS:
                resp = dbx.files_list_folder_continue(resp.cursor)
                for e in resp.entries:
                    process_entry(e)
                    if len(results) >= MAX_RESULTS:
                        break
            # salva cursor novo
            save_cursor(resp.cursor)
            save_seen(seen)

    if not cursor:
        # --------- BACKFILL (apenas 1ª vez ou cursor inválido) ----------
        # usa sua função que lista tudo, ordena desc e para ao passar de ontem
        backfill = coletar_ontem_ordenado(dbx, ROOT_PATH, max_results=MAX_RESULTS)
        results.extend(backfill)
        # após backfill, crie cursor para futuras execuções rápidas
        # (pega um cursor novo do estado atual da pasta)
        res = dbx.files_list_folder(path=normalize_for_list_folder(ROOT_PATH), recursive=RECURSIVE)
        save_cursor(res.cursor)
        # marca vistos
        for item in backfill:
            seen.add(item.get("nome_link") or "")
        save_seen(seen)

    return results[:MAX_RESULTS]



if __name__ == "__main__":
    itens = main()
    # imprime um resumo “bonito” quando rodar diretamente
    print_json({
        "account": "Tecnogera Geradores",
        "root_path": ROOT_PATH,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(itens),
        "results": itens
    })