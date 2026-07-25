# stock_monitor_mailer.py  — v3
import smtplib, logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

log = logging.getLogger(__name__)

# Etiquetas de prioridad — deben coincidir con las de la UI (stock_monitor.js)
PRIORITY_META = {
    'red':    {'emoji': '🔴', 'color': '#F85149', 'bg': '#1A0A0A', 'label': 'NEGATIVO'},
    'yellow': {'emoji': '🟡', 'color': '#D29922', 'bg': '#1A1400', 'label': 'ALERTA'},
    'green':  {'emoji': '🟢', 'color': '#3FB950', 'bg': '#0A1F10', 'label': 'POSITIVO'},
}

ALERT_META = {
    'target':    {'emoji': '🎯', 'color': '#3FB950', 'bg': '#0A1F10', 'label': 'TARGET ALCANZADO'},
    'stop_loss': {'emoji': '🛑', 'color': '#F85149', 'bg': '#1A0A0A', 'label': 'STOP LOSS ALCANZADO'},
}


class StockMonitorMailer:

    def __init__(self, host, port, user, password, from_addr=None):
        self.host = host; self.port = int(port)
        self.user = user; self.password = password
        self.from_addr = from_addr or user

    def notify_asset_added(self, portfolio_name, symbol, recipients):
        return self._send(recipients,
            f"[BIAS] {portfolio_name} — New asset: {symbol}",
            self._base(f"New asset added to <b>{portfolio_name}</b>",
                f"<p>Symbol <span class='chip'>{symbol}</span> has been added to the portfolio.</p>"))

    def notify_asset_removed(self, portfolio_name, symbol, recipients):
        return self._send(recipients,
            f"[BIAS] {portfolio_name} — Asset removed: {symbol}",
            self._base(f"Asset removed from <b>{portfolio_name}</b>",
                f"<p>Symbol <span class='chip'>{symbol}</span> has been removed.</p>"))

    def notify_comment_added(self, portfolio_name, symbol, comment, recipients):
        return self._send(recipients,
            f"[BIAS] {portfolio_name} — New comment on {symbol}",
            self._base(f"New comment on <span class='chip'>{symbol}</span>",
                f"<blockquote style='margin:16px 0;padding:12px 16px;border-left:3px solid #1F6FEB;"
                f"background:#0D2040;border-radius:0 6px 6px 0;color:#C9D1D9;'>{comment}</blockquote>"))

    def notify_manual(self, portfolio_name, message, recipients):
        return self._send(recipients,
            f"[BIAS] {portfolio_name} — Portfolio update",
            self._base(f"Update on <b>{portfolio_name}</b>", f"<p>{message}</p>"))

    def notify_research_updated(self, portfolio_name, symbol, field_label, new_value, recipients):
        """Fired when any research cell is saved."""
        return self._send(recipients,
            f"[BIAS] {portfolio_name} — Research updated: {symbol}",
            self._base(
                f"Research update · <span class='chip'>{symbol}</span> · <b>{portfolio_name}</b>",
                f"""<table style='width:100%;border-collapse:collapse;margin-top:8px;'>
                  <tr>
                    <td style='padding:10px 14px;background:#161B22;border:1px solid #21262D;
                      border-radius:6px 0 0 6px;color:#6E7681;font-size:12px;
                      white-space:nowrap;width:160px;'>{field_label}</td>
                    <td style='padding:10px 14px;background:#0D1117;border:1px solid #21262D;
                      border-left:none;border-radius:0 6px 6px 0;color:#C9D1D9;font-size:13px;'>
                      {new_value or '<em style="color:#484F58">cleared</em>'}</td>
                  </tr></table>"""))

    def notify_asset_note(self, portfolio_name, symbol, note, priority, recipients):
        """Fired when a note with notify=True is saved."""
        m = PRIORITY_META.get(priority, PRIORITY_META['green'])
        return self._send(recipients,
            f"[BIAS] {m['emoji']} {symbol} — {portfolio_name}",
            self._base(
                f"{m['emoji']} Note on <span class='chip'>{symbol}</span>",
                f"""<div style='margin-bottom:12px;'>
                  <span style='display:inline-block;background:{m['bg']};border:1px solid {m['color']};
                    color:{m['color']};border-radius:5px;padding:3px 10px;font-size:11px;
                    font-family:monospace;font-weight:600;'>{m['label']}</span></div>
                <blockquote style='margin:0;padding:14px 18px;border-left:4px solid {m['color']};
                  background:{m['bg']};border-radius:0 8px 8px 0;color:#C9D1D9;
                  font-size:14px;line-height:1.6;'>{note}</blockquote>
                <p style='margin:14px 0 0;color:#6E7681;font-size:12px;'>
                  Portfolio: <b style='color:#C9D1D9;'>{portfolio_name}</b></p>"""))

    def notify_price_alerts(self, portfolio_name, events, recipients):
        """Informe consolidado de niveles de precio alcanzados.

        `events` es una lista de dicts:
            {symbol, event_type ('target'|'stop_loss'), level, price, prev_price}
        """
        if not events:
            return True

        rows = []
        for ev in events:
            m = ALERT_META.get(ev.get('event_type'), ALERT_META['target'])
            level = ev.get('level')
            price = ev.get('price')
            prev = ev.get('prev_price')
            nuevo = " · NUEVO" if ev.get('is_new') else ""
            rows.append(f"""
              <tr>
                <td style='padding:10px 12px;border-bottom:1px solid #21262D;'>
                  <span class='chip'>{ev.get('symbol','')}</span></td>
                <td style='padding:10px 12px;border-bottom:1px solid #21262D;
                    color:{m['color']};font-size:12px;font-family:monospace;
                    white-space:nowrap;'>{m['emoji']} {m['label']}{nuevo}</td>
                <td style='padding:10px 12px;border-bottom:1px solid #21262D;
                    color:#8B949E;font-size:12px;font-family:monospace;
                    text-align:right;'>{'' if level is None else f'{level:,.2f}'}</td>
                <td style='padding:10px 12px;border-bottom:1px solid #21262D;
                    color:#E6EDF3;font-size:13px;font-family:monospace;
                    text-align:right;font-weight:600;'>{'' if price is None else f'{price:,.2f}'}</td>
                <td style='padding:10px 12px;border-bottom:1px solid #21262D;
                    color:#484F58;font-size:11px;font-family:monospace;
                    text-align:right;'>{'—' if prev is None else f'{prev:,.2f}'}</td>
              </tr>""")

        body = f"""
          <p>Se detectaron <b>{len(events)}</b> nivel(es) de precio alcanzado(s) en
             <b>{portfolio_name}</b>.</p>
          <table style='width:100%;border-collapse:collapse;margin-top:10px;
                        background:#0D1117;border:1px solid #21262D;border-radius:8px;'>
            <tr>
              <th style='padding:8px 12px;text-align:left;color:#484F58;font-size:10px;
                  text-transform:uppercase;letter-spacing:0.1em;
                  border-bottom:1px solid #21262D;'>Activo</th>
              <th style='padding:8px 12px;text-align:left;color:#484F58;font-size:10px;
                  text-transform:uppercase;letter-spacing:0.1em;
                  border-bottom:1px solid #21262D;'>Evento</th>
              <th style='padding:8px 12px;text-align:right;color:#484F58;font-size:10px;
                  text-transform:uppercase;letter-spacing:0.1em;
                  border-bottom:1px solid #21262D;'>Nivel</th>
              <th style='padding:8px 12px;text-align:right;color:#484F58;font-size:10px;
                  text-transform:uppercase;letter-spacing:0.1em;
                  border-bottom:1px solid #21262D;'>Precio</th>
              <th style='padding:8px 12px;text-align:right;color:#484F58;font-size:10px;
                  text-transform:uppercase;letter-spacing:0.1em;
                  border-bottom:1px solid #21262D;'>Previo</th>
            </tr>
            {''.join(rows)}
          </table>"""

        return self._send(recipients,
            f"[BIAS] {portfolio_name} — 🔔 {len(events)} alarma(s) de precio",
            self._base(f"🔔 Alarmas de precio · <b>{portfolio_name}</b>", body))

    def _send(self, recipients, subject, html):
        if not recipients: return True
        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject; msg['From'] = self.from_addr
            msg['To'] = ', '.join(recipients)
            msg.attach(MIMEText(html, 'html'))
            with smtplib.SMTP(self.host, self.port) as s:
                s.ehlo(); s.starttls(); s.login(self.user, self.password)
                s.sendmail(self.from_addr, recipients, msg.as_string())
            log.info(f"Mail OK: {subject} → {recipients}"); return True
        except Exception as e:
            log.error(f"Mail FAIL: {e}"); return False

    def _base(self, title, body):
        return f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><style>
body{{margin:0;padding:0;background:#080C10;font-family:'IBM Plex Sans',Arial,sans-serif;}}
.wrap{{max-width:560px;margin:32px auto;background:#0D1117;border:1px solid #21262D;border-radius:12px;overflow:hidden;}}
.hdr{{background:linear-gradient(135deg,#0F2847,#1F6FEB);padding:20px 28px;}}
.hdr-brand{{font-size:11px;color:rgba(255,255,255,0.6);letter-spacing:0.15em;text-transform:uppercase;margin-bottom:4px;}}
.hdr-title{{font-size:18px;color:#fff;font-weight:600;}}
.body{{padding:24px 28px;color:#C9D1D9;font-size:14px;line-height:1.6;}}
.body b{{color:#E6EDF3;}}
.chip{{display:inline-block;background:#0D2040;border:1px solid rgba(31,111,235,0.4);color:#58A6FF;border-radius:5px;padding:2px 9px;font-family:monospace;font-size:13px;font-weight:600;}}
.ftr{{border-top:1px solid #161B22;padding:14px 28px;color:#484F58;font-size:11px;text-align:center;}}
p{{margin:0 0 12px 0;}}
</style></head><body><div class="wrap">
<div class="hdr"><div class="hdr-brand">BIAS · AI Investment Intelligence</div>
<div class="hdr-title">{title}</div></div>
<div class="body">{body}</div>
<div class="ftr">You're subscribed to this portfolio on BIAS.</div>
</div></body></html>"""