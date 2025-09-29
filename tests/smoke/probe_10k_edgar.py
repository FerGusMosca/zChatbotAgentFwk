# probe_10k_edgar.py
# Minimal 10-K downloader from SEC EDGAR (official endpoints).
# Usage:
#   set SEC_ID="Fer Mosca (Seeking Bias) <email@dominio>"
#   python probe_10k_edgar.py AAPL                 # último 10-K (o 20-F si aplica)
#   python probe_10k_edgar.py AAPL --year 2024     # 10-K 2024 si existe
#   python probe_10k_edgar.py NVDA --save-index    # guarda también index.json
#
# Notas:
# - La SEC pide un User-Agent con contacto real (env SEC_ID).
# - Respeta rate limits; este probe hace 1 filing por ejecución.
# - Guarda en exports/k10/<TICKER>/<TICKER>_<YYYY>_<FORM>.<ext>

import os
import re
import json
import time
import argparse
import pathlib
import httpx

# Endpoints oficiales
SEC_FILES_BASE     = "https://www.sec.gov"          # /files/company_tickers*.json
SEC_DATA_BASE      = "https://data.sec.gov"         # /submissions/CIK##########.json
SEC_ARCHIVES_BASE  = "https://www.sec.gov/Archives" # /edgar/data/... (documentos)

UA = os.getenv("SEC_ID", "Your Name (Contact) email@example.com")

def http_client():
    return httpx.Client(
        headers={
            "User-Agent": UA,          # requerido por la SEC
            "Accept": "*/*",
            "Accept-Encoding": "gzip",
        },
        timeout=30.0,
        follow_redirects=True
    )

def load_ticker_map(c: httpx.Client) -> dict:
    """
    Devuelve dict TICKER -> CIK(int). Usa el JSON oficial de la SEC.
    """
    r = c.get(f"{SEC_FILES_BASE}/files/company_tickers.json")
    if r.status_code == 404:
        # Fallback alternativo con exchange incluido (por si cambia el primario)
        r = c.get(f"{SEC_FILES_BASE}/files/company_tickers_exchange.json")
    r.raise_for_status()
    data = r.json()
    return {v["ticker"].upper(): int(v["cik_str"]) for v in data.values()}

def cik10(n: int) -> str:
    return str(n).zfill(10)

def pick_recent_10k(subm: dict):
    """
    Del bloque 'recent' toma el primer 10-K (o 10-K/A).
    Para emisores extranjeros, cae a 20-F / 20-F/A.
    """
    rec   = subm.get("filings", {}).get("recent", {})
    forms = rec.get("form", [])
    accs  = rec.get("accessionNumber", [])
    prims = rec.get("primaryDocument", [])
    fdates= rec.get("filingDate", [])
    prefer = ("10-K", "10-K/A", "20-F", "20-F/A")
    for i, f in enumerate(forms):
        if f in prefer:
            return {"form": f, "acc": accs[i], "doc": prims[i], "filingDate": fdates[i]}
    return None

def pick_by_year(c: httpx.Client, subm: dict, year: int):
    """
    Busca 10-K/10-K(A) (o 20-F/20-F(A)) por año fiscal:
    1) Filtra 'recent' por reportDate (si existe) o filingDate.
    2) Si no lo encuentra, recorre JSONs históricos listados en 'files'.
    """
    prefer = ("10-K", "10-K/A", "20-F", "20-F/A")

    def scan_block(block: dict):
        forms = block.get("form", [])
        accs  = block.get("accessionNumber", [])
        prims = block.get("primaryDocument", [])
        fdates= block.get("filingDate", [])
        rdates= block.get("reportDate", fdates)
        rows = [
            dict(form=f, acc=a, doc=d, filingDate=fd, reportDate=rd)
            for f,a,d,fd,rd in zip(forms, accs, prims, fdates, rdates)
        ]
        # 1) por reportDate (fiscal)
        for wanted in prefer:
            cand = [r for r in rows if r["form"] == wanted and str(r["reportDate"]).startswith(str(year))]
            if cand:
                return cand[0]
        # 2) por filingDate (si no hay reportDate)
        for wanted in prefer:
            cand = [r for r in rows if r["form"] == wanted and str(r["filingDate"]).startswith(str(year))]
            if cand:
                return cand[0]
        return None

    # 1) recent
    rec = subm.get("filings", {}).get("recent", {})
    got = scan_block(rec)
    if got:
        return got

    # 2) históricos
    for f in subm.get("filings", {}).get("files", []):
        name = f.get("name")
        if not name:
            continue
        time.sleep(0.25)  # polite
        r = c.get(f"{SEC_DATA_BASE}/submissions/{name}")
        r.raise_for_status()
        blk = r.json().get("filings", {}).get("recent", {})
        got = scan_block(blk)
        if got:
            return got
    return None

def download_primary(c: httpx.Client, cik: int, acc: str, primary_doc: str, outdir: pathlib.Path) -> pathlib.Path:
    acc_nodash = acc.replace("-", "")
    url = f"{SEC_ARCHIVES_BASE}/edgar/data/{int(cik)}/{acc_nodash}/{primary_doc}"
    r = c.get(url)
    r.raise_for_status()
    outpath = outdir / primary_doc
    outpath.write_bytes(r.content)
    return outpath

def sanitize_filename(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", s)

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Probe: download latest (or yearly) 10-K from SEC EDGAR.")
    ap.add_argument("ticker", help="Stock ticker (e.g., AAPL)")
    ap.add_argument("--year", type=int, help="Target fiscal year (e.g., 2024)")
    ap.add_argument("--out", default="exports/k10", help="Output base folder")
    ap.add_argument("--save-index", action="store_true", help="Also save filing index.json if available")
    args = ap.parse_args()

    base_out = pathlib.Path(args.out)
    base_out.mkdir(parents=True, exist_ok=True)

    with http_client() as c:
        # 1) TICKER -> CIK
        tmap = load_ticker_map(c)
        tk = args.ticker.upper().strip()
        if tk not in tmap:
            raise SystemExit(f"[ERROR] Ticker not found in SEC map: {tk}")
        cik = tmap[tk]

        # 2) submissions JSON
        subm_url = f"{SEC_DATA_BASE}/submissions/CIK{cik10(cik)}.json"
        subm = c.get(subm_url).json()

        # 3) elegir filing
        if args.year:
            chosen = pick_by_year(c, subm, args.year)
            if not chosen:
                raise SystemExit(f"[ERROR] No 10-K/20-F found for year {args.year} (ticker {tk})")
        else:
            chosen = pick_recent_10k(subm)
            if not chosen:
                raise SystemExit(f"[ERROR] No recent 10-K/20-F found for ticker {tk}")

        form = chosen["form"]
        acc  = chosen["acc"]
        doc  = chosen["doc"]
        yyyy = (chosen.get("reportDate") or chosen.get("filingDate") or "")[:4]

        outdir = base_out / tk
        outdir.mkdir(parents=True, exist_ok=True)

        # 4) bajar documento primario
        fpath = download_primary(c, cik, acc, doc, outdir)

        # 5) opcional: index.json del filing
        index_path = None
        if args.save_index:
            try:
                acc_nodash = acc.replace("-", "")
                ix_url = f"{SEC_ARCHIVES_BASE}/edgar/data/{int(cik)}/{acc_nodash}/index.json"
                ix = c.get(ix_url).json()
                index_path = outdir / f"{sanitize_filename(tk + '_' + yyyy + '_index')}.json"
                index_path.write_text(json.dumps(ix, indent=2))
            except Exception:
                pass

        # 6) rename bonito
        pretty_name = f"{tk}_{yyyy}_{form}{pathlib.Path(doc).suffix or '.html'}"
        pretty_path = outdir / pretty_name
        try:
            if pretty_path.resolve() != fpath.resolve():
                if pretty_path.exists():
                    pretty_path.unlink()
                fpath.rename(pretty_path)
        except Exception:
            pretty_path = fpath  # fallback

        print(f"[OK] {form} saved → {pretty_path}")
        if index_path:
            print(f"[OK] index saved → {index_path}")
