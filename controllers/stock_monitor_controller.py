# stock_monitor_controller.py — v3
import csv, io, os

import httpx
from fastapi import APIRouter, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from common.config.settings import settings
from common.util.mailer.stock_monitor_mailer import StockMonitorMailer
from common.util.std_in_out.root_locator import RootLocator
from data_access_layer.stock_monitor_manager import StockMonitorManager


RESEARCH_FIELD_LABELS = {
    'news': 'News', 'gpa_ratio': 'GPA Ratio (%)', 'pe_ratio': 'P/E Ratio',
    'debt_ratio': 'Debt Ratio', 'ta_situation': 'TA Situation',
    'mgmt_sentiment': 'Last Mgmt Sent.', 'earnings': 'Earning Transcript',
    'conclusion': 'Conclusion', 'latest_comments': 'Latest Comments',
}


class StockMonitorController:

    def __init__(self):
        self.router = APIRouter(prefix="/stock_monitor")
        templates_path = os.path.join(RootLocator.get_root(), "templates")
        self.templates = Jinja2Templates(directory=templates_path)
        self.mgr = StockMonitorManager(settings.research_connection_string)
        self.mailer = self._build_mailer()

        # ── Page ──────────────────────────────────────────────
        @self.router.get("/", response_class=HTMLResponse)
        async def page(request: Request):
            return self.templates.TemplateResponse("stock_monitor.html", {"request": request})

        # ── Portfolios ────────────────────────────────────────
        @self.router.get("/portfolios")
        async def get_portfolios():
            try: return JSONResponse([self._p(p) for p in self.mgr.get_portfolios()])
            except Exception as e: return JSONResponse({"status":"error","message":str(e)}, status_code=500)

        @self.router.post("/portfolios")
        async def create_portfolio(name: str = Form(...), description: str = Form(None)):
            try:
                new_id = self.mgr.create_portfolio(name.strip(), description)
                p = next((x for x in self.mgr.get_portfolios() if x.id == new_id), None)
                return JSONResponse({"status":"ok","portfolio":self._p(p)})
            except Exception as e: return JSONResponse({"status":"error","message":str(e)}, status_code=500)

        @self.router.put("/portfolios/{portfolio_id}")
        async def update_portfolio(portfolio_id: int, name: str = Form(...), description: str = Form(None)):
            try:
                self.mgr.update_portfolio(portfolio_id, name.strip(), description)
                return JSONResponse({"status":"ok"})
            except Exception as e: return JSONResponse({"status":"error","message":str(e)}, status_code=500)

        @self.router.delete("/portfolios/{portfolio_id}")
        async def delete_portfolio(portfolio_id: int):
            try: self.mgr.delete_portfolio(portfolio_id); return JSONResponse({"status":"ok"})
            except Exception as e: return JSONResponse({"status":"error","message":str(e)}, status_code=500)

        # ── Assets ────────────────────────────────────────────
        @self.router.get("/portfolios/{portfolio_id}/assets")
        async def get_assets(portfolio_id: int):
            try: return JSONResponse([self._a(a) for a in self.mgr.get_assets(portfolio_id)])
            except Exception as e: return JSONResponse({"status":"error","message":str(e)}, status_code=500)

        @self.router.post("/portfolios/{portfolio_id}/assets")
        async def add_assets(portfolio_id: int, symbols: str = Form(None), csv_file: UploadFile = File(None)):
            try:
                sym_list = []
                if symbols:
                    sym_list += [s.strip().upper() for s in symbols.replace(',','\n').split('\n') if s.strip()]
                if csv_file and csv_file.filename:
                    content = await csv_file.read()
                    for row in csv.reader(io.StringIO(content.decode('utf-8', errors='ignore'))):
                        if row:
                            v = row[0].strip().upper()
                            if v and len(v) <= 20: sym_list.append(v)
                seen, clean = set(), []
                for s in sym_list:
                    if s and s not in seen and len(s) <= 20: seen.add(s); clean.append(s)
                added = self.mgr.add_assets_bulk(portfolio_id, clean)
                if added and self.mailer:
                    recipients = self._get_emails(portfolio_id)
                    pname = self._get_portfolio_name(portfolio_id)
                    for asset in added:
                        ok = self.mailer.notify_asset_added(pname, asset.symbol, recipients)
                        self.mgr.log_notification(portfolio_id, 'asset_added',
                            f"symbol={asset.symbol}", ','.join(recipients), 'sent' if ok else 'failed')
                return JSONResponse({"status":"ok","assets":[self._a(a) for a in added]})
            except Exception as e: return JSONResponse({"status":"error","message":str(e)}, status_code=500)

        @self.router.delete("/portfolios/{portfolio_id}/assets/{symbol}")
        async def remove_asset(portfolio_id: int, symbol: str):
            try:
                self.mgr.remove_asset(portfolio_id, symbol)
                if self.mailer:
                    recipients = self._get_emails(portfolio_id)
                    ok = self.mailer.notify_asset_removed(self._get_portfolio_name(portfolio_id), symbol, recipients)
                    self.mgr.log_notification(portfolio_id, 'asset_removed', f"symbol={symbol}",
                        ','.join(recipients), 'sent' if ok else 'failed')
                return JSONResponse({"status":"ok"})
            except Exception as e: return JSONResponse({"status":"error","message":str(e)}, status_code=500)

        # ── Comments ──────────────────────────────────────────
        @self.router.get("/portfolios/{portfolio_id}/assets/{symbol}/comments")
        async def get_comments(portfolio_id: int, symbol: str):
            try: return JSONResponse([self._c(c) for c in self.mgr.get_comments(portfolio_id, symbol)])
            except Exception as e: return JSONResponse({"status":"error","message":str(e)}, status_code=500)

        @self.router.post("/portfolios/{portfolio_id}/assets/{symbol}/comments")
        async def add_comment(portfolio_id: int, symbol: str, comment: str = Form(...)):
            try:
                new_id = self.mgr.add_comment(portfolio_id, symbol, comment)
                if self.mailer:
                    recipients = self._get_emails(portfolio_id)
                    ok = self.mailer.notify_comment_added(self._get_portfolio_name(portfolio_id),
                                                          symbol, comment, recipients)
                    self.mgr.log_notification(portfolio_id, 'comment_added', f"symbol={symbol}",
                        ','.join(recipients), 'sent' if ok else 'failed')
                return JSONResponse({"status":"ok","id":new_id})
            except Exception as e: return JSONResponse({"status":"error","message":str(e)}, status_code=500)

        @self.router.delete("/comments/{comment_id}")
        async def delete_comment(comment_id: int):
            try: self.mgr.delete_comment(comment_id); return JSONResponse({"status":"ok"})
            except Exception as e: return JSONResponse({"status":"error","message":str(e)}, status_code=500)

        # ── Asset Notes ───────────────────────────────────────
        @self.router.get("/portfolios/{portfolio_id}/assets/{symbol}/notes")
        async def get_notes(portfolio_id: int, symbol: str):
            try: return JSONResponse([self._n(n) for n in self.mgr.get_asset_notes(portfolio_id, symbol)])
            except Exception as e: return JSONResponse({"status":"error","message":str(e)}, status_code=500)

        @self.router.post("/portfolios/{portfolio_id}/assets/{symbol}/notes")
        async def add_note(portfolio_id: int, symbol: str,
                           note: str = Form(...),
                           priority: str = Form('green'),
                           notify: str = Form('false')):
            try:
                do_notify = notify.lower() in ('true','1','yes')
                new_id = self.mgr.add_asset_note(portfolio_id, symbol, note, priority, do_notify)
                if do_notify and self.mailer:
                    recipients = self._get_emails(portfolio_id)
                    ok = self.mailer.notify_asset_note(
                        self._get_portfolio_name(portfolio_id), symbol, note, priority, recipients)
                    self.mgr.log_notification(portfolio_id, 'note_added', f"symbol={symbol},priority={priority}",
                        ','.join(recipients), 'sent' if ok else 'failed')
                return JSONResponse({"status":"ok","id":new_id})
            except Exception as e: return JSONResponse({"status":"error","message":str(e)}, status_code=500)

        @self.router.delete("/notes/{note_id}")
        async def delete_note(note_id: int):
            try: self.mgr.delete_asset_note(note_id); return JSONResponse({"status":"ok"})
            except Exception as e: return JSONResponse({"status":"error","message":str(e)}, status_code=500)

        # ── Manual notification ───────────────────────────────
        @self.router.post("/portfolios/{portfolio_id}/notify")
        async def send_manual(portfolio_id: int, message: str = Form(...)):
            try:
                if not self.mailer: return JSONResponse({"status":"error","message":"Mailer not configured"})
                recipients = self._get_emails(portfolio_id)
                if not recipients: return JSONResponse({"status":"error","message":"No subscribers"})
                ok = self.mailer.notify_manual(self._get_portfolio_name(portfolio_id), message, recipients)
                self.mgr.log_notification(portfolio_id, 'manual', message,
                    ','.join(recipients), 'sent' if ok else 'failed')
                return JSONResponse({"status":"ok","sent_to":recipients})
            except Exception as e: return JSONResponse({"status":"error","message":str(e)}, status_code=500)

        # ── Email subscribers ──────────────────────────────────
        @self.router.get("/portfolios/{portfolio_id}/emails")
        async def get_emails(portfolio_id: int):
            try: return JSONResponse([self._e(e) for e in self.mgr.get_portfolio_emails(portfolio_id)])
            except Exception as e: return JSONResponse({"status":"error","message":str(e)}, status_code=500)

        @self.router.post("/portfolios/{portfolio_id}/emails")
        async def add_email(portfolio_id: int, email: str = Form(...), name: str = Form(None)):
            try:
                entry = self.mgr.add_portfolio_email(portfolio_id, email, name)
                return JSONResponse({"status":"ok","entry":self._e(entry)})
            except Exception as e: return JSONResponse({"status":"error","message":str(e)}, status_code=500)

        @self.router.delete("/emails/{email_id}")
        async def remove_email(email_id: int):
            try: self.mgr.remove_portfolio_email(email_id); return JSONResponse({"status":"ok"})
            except Exception as e: return JSONResponse({"status":"error","message":str(e)}, status_code=500)

        # ── Research Topics ───────────────────────────────────
        @self.router.get("/portfolios/{portfolio_id}/research_topics")
        async def get_research_topics(portfolio_id: int):
            try: return JSONResponse([self._t(t) for t in self.mgr.get_research_topics(portfolio_id)])
            except Exception as e: return JSONResponse({"status":"error","message":str(e)}, status_code=500)

        @self.router.post("/portfolios/{portfolio_id}/research_topics")
        async def create_research_topic(portfolio_id: int, name: str = Form(...)):
            try:
                topic = self.mgr.create_research_topic(portfolio_id, name.strip())
                return JSONResponse({"status":"ok","topic":self._t(topic)})
            except Exception as e: return JSONResponse({"status":"error","message":str(e)}, status_code=500)

        @self.router.delete("/research_topics/{topic_id}")
        async def delete_research_topic(topic_id: int):
            try: self.mgr.delete_research_topic(topic_id); return JSONResponse({"status":"ok"})
            except Exception as e: return JSONResponse({"status":"error","message":str(e)}, status_code=500)

        # ── Research Rows ─────────────────────────────────────
        @self.router.get("/research_topics/{topic_id}/rows")
        async def get_research_rows(topic_id: int):
            try: return JSONResponse([self._r(r) for r in self.mgr.get_research_rows(topic_id)])
            except Exception as e: return JSONResponse({"status":"error","message":str(e)}, status_code=500)

        @self.router.post("/research_topics/{topic_id}/rows/{symbol}")
        async def upsert_research_row(
            topic_id: int, symbol: str,
            news: str = Form(None), gpa_ratio: str = Form(None),
            pe_ratio: str = Form(None), debt_ratio: str = Form(None),
            ta_situation: str = Form(None), mgmt_sentiment: str = Form(None),
            earnings: str = Form(None), conclusion: str = Form(None),
            latest_comments: str = Form(None),
            # which field was edited (for the notification)
            edited_field: str = Form(None),
            notify_subscribers: str = Form('false'),
        ):
            def to_dec(v):
                if not v or not v.strip(): return None
                try: return float(v.replace('%','').strip())
                except: return None
            try:
                row = self.mgr.upsert_research_row(
                    topic_id=topic_id, symbol=symbol,
                    news=news, gpa_ratio=to_dec(gpa_ratio), pe_ratio=to_dec(pe_ratio),
                    debt_ratio=to_dec(debt_ratio), ta_situation=ta_situation,
                    mgmt_sentiment=mgmt_sentiment, earnings=earnings,
                    conclusion=conclusion, latest_comments=latest_comments,
                )
                # Notify subscribers when a cell is updated
                do_notify = notify_subscribers.lower() in ('true','1','yes')
                if self.mailer and edited_field:
                    # Always notify on research updates (auto)
                    recipients = self._get_emails(topic_id=topic_id)
                    if recipients:
                        field_label = RESEARCH_FIELD_LABELS.get(edited_field, edited_field)
                        # Get the new value from the request
                        field_values = {
                            'news': news, 'gpa_ratio': gpa_ratio, 'pe_ratio': pe_ratio,
                            'debt_ratio': debt_ratio, 'ta_situation': ta_situation,
                            'mgmt_sentiment': mgmt_sentiment, 'earnings': earnings,
                            'conclusion': conclusion, 'latest_comments': latest_comments,
                        }
                        new_val = field_values.get(edited_field, '')
                        ok = self.mailer.notify_research_updated(
                            self._get_portfolio_name_by_topic(topic_id),
                            symbol, field_label, new_val, recipients)
                        self.mgr.log_notification(
                            self._get_portfolio_id_by_topic(topic_id),
                            'research_updated', f"symbol={symbol},field={edited_field}",
                            ','.join(recipients), 'sent' if ok else 'failed')
                return JSONResponse({"status":"ok","row":self._r(row)})
            except Exception as e: return JSONResponse({"status":"error","message":str(e)}, status_code=500)

        @self.router.delete("/research_topics/{topic_id}/rows/{symbol}")
        async def delete_research_row(topic_id: int, symbol: str):
            try: self.mgr.delete_research_row(topic_id, symbol); return JSONResponse({"status":"ok"})
            except Exception as e: return JSONResponse({"status":"error","message":str(e)}, status_code=500)

        @self.router.get("/price")
        async def get_price(symbol: str):
            """
            Proxy for Yahoo Finance v8 quote endpoint.
            Returns: { symbol, price, change, change_pct, name }
            """
            try:
                url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
                       f"?interval=1d&range=1d")
                headers = {
                    "User-Agent": "Mozilla/5.0",
                    "Accept": "application/json",
                }
                async with httpx.AsyncClient(timeout=8.0) as client:
                    resp = await client.get(url, headers=headers)

                if resp.status_code != 200:
                    return JSONResponse({"symbol": symbol, "price": None,
                                         "change": None, "change_pct": None, "name": None})

                data = resp.json()
                meta = data.get("chart", {}).get("result", [{}])[0].get("meta", {})
                price = meta.get("regularMarketPrice")
                prev = meta.get("chartPreviousClose") or meta.get("previousClose")
                name = meta.get("longName") or meta.get("shortName") or symbol

                change = round(price - prev, 4) if price and prev else None
                change_pct = round((change / prev) * 100, 2) if change and prev else None

                return JSONResponse({
                    "symbol": symbol.upper(),
                    "price": price,
                    "change": change,
                    "change_pct": change_pct,
                    "name": name,
                })
            except Exception as e:
                return JSONResponse({"symbol": symbol, "price": None,
                                     "change": None, "change_pct": None, "name": None})


    # ── Helpers ───────────────────────────────────────────────
    def _build_mailer(self):
        try:
            if all([settings.smtp_host, settings.smtp_user, settings.smtp_password]):
                return StockMonitorMailer(host=settings.smtp_host, port=settings.smtp_port or 587,
                    user=settings.smtp_user, password=settings.smtp_password,
                    from_addr=settings.smtp_from or settings.smtp_user)
        except Exception: pass
        return None

    def _get_emails(self, portfolio_id=None, topic_id=None):
        try:
            pid = portfolio_id or self._get_portfolio_id_by_topic(topic_id)
            return [e.email for e in self.mgr.get_portfolio_emails(pid)]
        except: return []

    def _get_portfolio_name(self, portfolio_id):
        try:
            p = next((x for x in self.mgr.get_portfolios() if x.id == portfolio_id), None)
            return p.name if p else str(portfolio_id)
        except: return str(portfolio_id)

    def _get_portfolio_name_by_topic(self, topic_id):
        try:
            # We need to find which portfolio owns this topic — iterate all portfolios
            for p in self.mgr.get_portfolios():
                topics = self.mgr.get_research_topics(p.id)
                if any(t.id == topic_id for t in topics):
                    return p.name
        except: pass
        return ''

    def _get_portfolio_id_by_topic(self, topic_id):
        try:
            for p in self.mgr.get_portfolios():
                topics = self.mgr.get_research_topics(p.id)
                if any(t.id == topic_id for t in topics):
                    return p.id
        except: pass
        return 0

    # ── Serialisers ───────────────────────────────────────────
    def _p(self, p):
        return {"id":p.id,"name":p.name,"description":p.description,
                "created_at":str(p.created_at),"updated_at":str(p.updated_at)}
    def _a(self, a):
        return {"id":a.id,"portfolio_id":a.portfolio_id,"symbol":a.symbol,"added_at":str(a.added_at)}
    def _c(self, c):
        return {"id":c.id,"portfolio_id":c.portfolio_id,"symbol":c.symbol,
                "comment":c.comment,"created_at":str(c.created_at)}
    def _n(self, n):
        return {"id":n.id,"portfolio_id":n.portfolio_id,"symbol":n.symbol,
                "note":n.note,"priority":n.priority,"notify":n.notify,"created_at":str(n.created_at)}
    def _t(self, t):
        return {"id":t.id,"portfolio_id":t.portfolio_id,"name":t.name,"created_at":str(t.created_at)}
    def _e(self, e):
        return {"id":e.id,"portfolio_id":e.portfolio_id,"email":e.email,
                "name":e.name,"added_at":str(e.added_at)}
    def _r(self, r):
        return {"id":r.id,"topic_id":r.topic_id,"symbol":r.symbol,"news":r.news,
                "gpa_ratio": float(r.gpa_ratio)  if r.gpa_ratio  is not None else None,
                "pe_ratio":  float(r.pe_ratio)   if r.pe_ratio   is not None else None,
                "debt_ratio":float(r.debt_ratio) if r.debt_ratio is not None else None,
                "ta_situation":r.ta_situation,"mgmt_sentiment":r.mgmt_sentiment,
                "earnings":r.earnings,"conclusion":r.conclusion,
                "latest_comments":r.latest_comments,"updated_at":str(r.updated_at)}