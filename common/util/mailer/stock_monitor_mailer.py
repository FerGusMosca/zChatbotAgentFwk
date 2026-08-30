# stock_monitor_mailer.py  — v4
#
# Novedades v4:
#   - Logo BIAS embebido en el mail (imagen inline, no depende de internet).
#   - Formato del mail rearmado con tablas -> se ve bien en Gmail, Outlook y celular.
#   - Los mails de "informe" (nota de activo y alarmas de precio) viajan ademas
#     con el reporte adjunto en HTML, listo para abrir, imprimir o guardar en PDF
#     desde el navegador.
#
# Las firmas de los metodos notify_* NO cambiaron: el controller queda igual.

import smtplib, logging, base64, re
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.mime.application import MIMEApplication

log = logging.getLogger(__name__)

# Etiquetas de prioridad — deben coincidir con las de la UI (stock_monitor.js)
PRIORITY_META = {
    'red':    {'emoji': '🔴', 'color': '#F85149', 'bg': '#1A0A0A', 'label': 'NEGATIVO',
               'print_color': '#B3261E', 'print_bg': '#FDECEA'},
    'yellow': {'emoji': '🟡', 'color': '#D29922', 'bg': '#1A1400', 'label': 'ALERTA',
               'print_color': '#8A6100', 'print_bg': '#FDF3D7'},
    'green':  {'emoji': '🟢', 'color': '#3FB950', 'bg': '#0A1F10', 'label': 'POSITIVO',
               'print_color': '#0A7A3D', 'print_bg': '#E7F6EC'},
}

ALERT_META = {
    'target':    {'emoji': '🎯', 'color': '#3FB950', 'bg': '#0A1F10', 'label': 'TARGET ALCANZADO',
                  'print_color': '#0A7A3D', 'print_bg': '#E7F6EC'},
    'stop_loss': {'emoji': '🛑', 'color': '#F85149', 'bg': '#1A0A0A', 'label': 'STOP LOSS ALCANZADO',
                  'print_color': '#B3261E', 'print_bg': '#FDECEA'},
}

# Logo BIAS (PNG 160x160) embebido en base64 — se manda inline con el mail
# y como data URI dentro del reporte adjunto.
LOGO_PNG_B64 = (
    "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"
    "AAAASUVORK5CYII="
)


class StockMonitorMailer:

    def __init__(self, host, port, user, password, from_addr=None):
        self.host = host; self.port = int(port)
        self.user = user; self.password = password
        self.from_addr = from_addr or user

    # ------------------------------------------------------------------ #
    #  Avisos simples (sin adjunto)                                       #
    # ------------------------------------------------------------------ #

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

    # ------------------------------------------------------------------ #
    #  Informes (van con el reporte adjunto en HTML)                      #
    # ------------------------------------------------------------------ #

    def notify_asset_note(self, portfolio_name, symbol, note, priority, recipients,
                          report_html=None, file_name=None, embed=True, attach=True):
        """Fired when a note with notify=True is saved."""
        m = PRIORITY_META.get(priority, PRIORITY_META['green'])

        cuerpo_mail = f"""<div style='margin-bottom:12px;'>
              <span style='display:inline-block;background:{m['bg']};border:1px solid {m['color']};
                color:{m['color']};border-radius:5px;padding:3px 10px;font-size:11px;
                font-family:monospace;font-weight:600;'>{m['label']}</span></div>
            <blockquote style='margin:0;padding:14px 18px;border-left:4px solid {m['color']};
              background:{m['bg']};border-radius:0 8px 8px 0;color:#C9D1D9;
              font-size:14px;line-height:1.6;'>{note}</blockquote>
            <p style='margin:14px 0 0;color:#6E7681;font-size:12px;'>
              Portfolio: <b style='color:#C9D1D9;'>{portfolio_name}</b></p>"""

        # Si se cargo un reporte desde la pantalla, va junto con la nota.
        if report_html and embed and isinstance(report_html, str):
            cuerpo_mail += f"""
              <div style='margin-top:18px;padding:16px;background:#FFFFFF;
                   border:1px solid #21262D;border-radius:10px;color:#1A1A1A;'>
                {self._inner_body(report_html)}
              </div>"""
        elif report_html:
            cuerpo_mail += """
              <p style='margin-top:16px;color:#6E7681;font-size:12px;'>
                El reporte completo va adjunto a este mail.</p>"""

        html = self._base(f"{m['emoji']} Note on <span class='chip'>{symbol}</span>", cuerpo_mail)
        html, imagenes = self._cid_images(html)

        adjuntos = []
        if report_html and attach:
            nombre = file_name or self._file_name(f"BIAS_{symbol}_reporte")
            if not nombre.lower().endswith(('.html', '.htm', '.pdf')):
                nombre = f"{nombre}.pdf" if isinstance(report_html, bytes) else f"{nombre}.html"
            adjuntos.append((nombre, report_html))
        elif not report_html:
            cuerpo_reporte = f"""
                <table class="ficha">
                  <tr><td class="et">Portfolio</td><td class="va">{portfolio_name}</td></tr>
                  <tr><td class="et">Activo</td><td class="va"><b>{symbol}</b></td></tr>
                  <tr><td class="et">Prioridad</td><td class="va">
                    <span class="badge" style="color:{m['print_color']};background:{m['print_bg']};
                      border:1px solid {m['print_color']};">{m['emoji']} {m['label']}</span></td></tr>
                </table>
                <h2>Nota</h2>
                <div class="cita" style="border-left:4px solid {m['print_color']};
                     background:{m['print_bg']};">{note}</div>"""
            adjuntos.append((self._file_name(f"BIAS_{symbol}_nota"),
                             self._report_document(f"Nota de research — {symbol}",
                                                   portfolio_name, cuerpo_reporte)))

        return self._send(recipients,
            f"[BIAS] {m['emoji']} {symbol} — {portfolio_name}",
            html, attachments=adjuntos, inline_images=imagenes)

    def notify_price_alerts(self, portfolio_name, events, recipients):
        """Informe consolidado de niveles de precio alcanzados.

        `events` es una lista de dicts:
            {symbol, event_type ('target'|'stop_loss'), level, price, prev_price}
        """
        if not events:
            return True

        rows, rows_print = [], []
        for ev in events:
            m = ALERT_META.get(ev.get('event_type'), ALERT_META['target'])
            level = ev.get('level')
            price = ev.get('price')
            prev = ev.get('prev_price')
            nuevo = " · NUEVO" if ev.get('is_new') else ""
            f_level = '' if level is None else f'{level:,.2f}'
            f_price = '' if price is None else f'{price:,.2f}'
            f_prev = '—' if prev is None else f'{prev:,.2f}'

            rows.append(f"""
              <tr>
                <td style='padding:10px 12px;border-bottom:1px solid #21262D;'>
                  <span class='chip'>{ev.get('symbol','')}</span></td>
                <td style='padding:10px 12px;border-bottom:1px solid #21262D;
                    color:{m['color']};font-size:12px;font-family:monospace;
                    white-space:nowrap;'>{m['emoji']} {m['label']}{nuevo}</td>
                <td style='padding:10px 12px;border-bottom:1px solid #21262D;
                    color:#8B949E;font-size:12px;font-family:monospace;
                    text-align:right;'>{f_level}</td>
                <td style='padding:10px 12px;border-bottom:1px solid #21262D;
                    color:#E6EDF3;font-size:13px;font-family:monospace;
                    text-align:right;font-weight:600;'>{f_price}</td>
                <td style='padding:10px 12px;border-bottom:1px solid #21262D;
                    color:#484F58;font-size:11px;font-family:monospace;
                    text-align:right;'>{f_prev}</td>
              </tr>""")

            rows_print.append(f"""
              <tr>
                <td><b>{ev.get('symbol','')}</b></td>
                <td><span class="badge" style="color:{m['print_color']};
                    background:{m['print_bg']};border:1px solid {m['print_color']};">
                    {m['emoji']} {m['label']}{nuevo}</span></td>
                <td class="num">{f_level}</td>
                <td class="num"><b>{f_price}</b></td>
                <td class="num tenue">{f_prev}</td>
              </tr>""")

        encabezados = ['Activo', 'Evento', 'Nivel', 'Precio', 'Previo']
        th_mail = ''.join(
            f"""<th style='padding:8px 12px;text-align:{'right' if i > 1 else 'left'};
                color:#484F58;font-size:10px;text-transform:uppercase;letter-spacing:0.1em;
                border-bottom:1px solid #21262D;'>{h}</th>""" for i, h in enumerate(encabezados))

        body = f"""
          <p>Se detectaron <b>{len(events)}</b> nivel(es) de precio alcanzado(s) en
             <b>{portfolio_name}</b>.</p>
          <table style='width:100%;border-collapse:collapse;margin-top:10px;
                        background:#0D1117;border:1px solid #21262D;border-radius:8px;'>
            <tr>{th_mail}</tr>
            {''.join(rows)}
          </table>
          <p style='margin-top:16px;color:#6E7681;font-size:12px;'>
            El informe completo va adjunto a este mail.</p>"""

        cuerpo_reporte = f"""
            <p>Se detectaron <b>{len(events)}</b> nivel(es) de precio alcanzado(s) en el portfolio
               <b>{portfolio_name}</b>.</p>
            <h2>Detalle</h2>
            <table class="datos">
              <tr><th>Activo</th><th>Evento</th><th class="num">Nivel</th>
                  <th class="num">Precio</th><th class="num">Previo</th></tr>
              {''.join(rows_print)}
            </table>"""

        adjunto = self._report_document(
            "Alarmas de precio", portfolio_name, cuerpo_reporte)

        return self._send(recipients,
            f"[BIAS] {portfolio_name} — 🔔 {len(events)} alarma(s) de precio",
            self._base(f"🔔 Alarmas de precio · <b>{portfolio_name}</b>", body),
            attachments=[(self._file_name(f"BIAS_{portfolio_name}_alarmas"), adjunto)])

    # ------------------------------------------------------------------ #
    #  Reporte cargado a mano desde la pantalla                           #
    # ------------------------------------------------------------------ #

    def build_report_email(self, portfolio_name, title, message,
                           report_html=None, embed=True):
        """Arma el cuerpo del mail del reporte. Se usa igual para la vista previa."""
        partes = []
        if message:
            texto = str(message).strip().replace('\r\n', '\n')
            for parrafo in [p for p in texto.split('\n\n') if p.strip()]:
                partes.append(f"<p>{parrafo.strip().replace(chr(10), '<br>')}</p>")

        if report_html and embed and isinstance(report_html, str):
            partes.append(f"""
              <div style='margin-top:18px;padding:16px;background:#FFFFFF;
                   border:1px solid #21262D;border-radius:10px;color:#1A1A1A;'>
                {self._inner_body(report_html)}
              </div>""")

        if report_html and (not embed or not isinstance(report_html, str)):
            partes.append("""
              <p style='margin-top:16px;color:#6E7681;font-size:12px;'>
                El reporte completo va adjunto a este mail.</p>""")

        if not partes:
            partes.append("<p>Sin contenido.</p>")

        titulo = (title or '').strip() or f"Reporte · {portfolio_name}"
        return self._base(f"{titulo} · <b>{portfolio_name}</b>", ''.join(partes))

    def notify_report(self, portfolio_name, title, message, recipients,
                      report_html=None, file_name=None, embed=True, attach=True):
        """Manda el reporte cargado desde la pantalla de subscribers."""
        html = self.build_report_email(portfolio_name, title, message, report_html, embed)

        # Las imagenes pegadas dentro del HTML no las muestra Gmail ni Outlook,
        # asi que se sacan del texto y se mandan como parte del mail.
        html, imagenes = self._cid_images(html)

        adjuntos = []
        if report_html and attach:
            nombre = file_name or self._file_name(f"BIAS_{portfolio_name}_reporte")
            if not nombre.lower().endswith(('.html', '.htm', '.pdf')):
                nombre = f"{nombre}.pdf" if isinstance(report_html, bytes) else f"{nombre}.html"
            adjuntos.append((nombre, report_html))

        asunto = (title or '').strip() or f"Reporte · {portfolio_name}"
        return self._send(recipients, f"[BIAS] {portfolio_name} — {asunto}",
                          html, attachments=adjuntos, inline_images=imagenes)

    def _cid_images(self, html):
        """Saca las imagenes pegadas en el texto y las deja como parte del mail.

        Devuelve (html_nuevo, [(id, bytes, tipo), ...]).
        """
        imagenes = []

        def reemplazar(m):
            comilla, subtipo, datos = m.group(1), m.group(2), m.group(3)
            try:
                crudo = base64.b64decode(re.sub(r'\s+', '', datos))
            except Exception:
                return m.group(0)
            if not crudo:
                return m.group(0)
            cid = f"rep{len(imagenes) + 1}@bias"
            imagenes.append((cid, crudo, subtipo.lower()))
            return f'src={comilla}cid:{cid}{comilla}'

        patron = re.compile(
            r'src\s*=\s*(["\'])data:image/([A-Za-z0-9.+-]+);base64,([A-Za-z0-9+/=\s]+?)\1')
        nuevo = patron.sub(reemplazar, html or '')
        return nuevo, imagenes

    def _inner_body(self, html):
        """Saca lo que esta adentro de <body> del archivo cargado.

        Se dejan los estilos (para que se parezca al original) y se sacan los
        scripts, que en un mail no corren y solo molestan.
        """
        texto = html or ''
        estilos = ''.join(re.findall(r'<style\b.*?</style>', texto, re.S | re.I))
        cuerpo = re.search(r'<body\b[^>]*>(.*?)</body>', texto, re.S | re.I)
        cuerpo = cuerpo.group(1) if cuerpo else texto
        cuerpo = re.sub(r'<script\b.*?</script>', '', cuerpo, flags=re.S | re.I)
        cuerpo = re.sub(r'<style\b.*?</style>', '', cuerpo, flags=re.S | re.I)
        return estilos + cuerpo

    # ------------------------------------------------------------------ #
    #  Envio                                                              #
    # ------------------------------------------------------------------ #

    def _send(self, recipients, subject, html, attachments=None, inline_images=None):
        """`attachments` es una lista de tuplas (nombre_de_archivo, texto_html).
        `inline_images` es una lista de tuplas (id, bytes, tipo)."""
        if not recipients: return True
        try:
            msg = self._build_message(recipients, subject, html, attachments, inline_images)
            with smtplib.SMTP(self.host, self.port) as s:
                s.ehlo(); s.starttls(); s.login(self.user, self.password)
                s.sendmail(self.from_addr, recipients, msg.as_string())
            log.info(f"Mail OK: {subject} → {recipients}"); return True
        except Exception as e:
            log.error(f"Mail FAIL: {e}"); return False

    def _build_message(self, recipients, subject, html, attachments=None, inline_images=None):
        raiz = MIMEMultipart('mixed')
        raiz['Subject'] = subject
        raiz['From'] = self.from_addr
        raiz['To'] = ', '.join(recipients)

        # cuerpo + logo inline
        contenido = MIMEMultipart('related')
        alternativas = MIMEMultipart('alternative')
        alternativas.attach(MIMEText(html, 'html', 'utf-8'))
        contenido.attach(alternativas)

        logo = MIMEImage(base64.b64decode(LOGO_PNG_B64), 'png')
        logo.add_header('Content-ID', '<bias_logo>')
        logo.add_header('Content-Disposition', 'inline', filename='bias.png')
        contenido.attach(logo)

        # imagenes del reporte, que viajan adentro del mail
        for i, (cid, crudo, subtipo) in enumerate(inline_images or [], start=1):
            try:
                img = MIMEImage(crudo, _subtype=subtipo)
            except Exception:
                continue
            img.add_header('Content-ID', f'<{cid}>')
            img.add_header('Content-Disposition', 'inline', filename=f'imagen_{i}.{subtipo}')
            contenido.attach(img)

        raiz.attach(contenido)

        for nombre, contenido in (attachments or []):
            if isinstance(contenido, bytes):
                # PDF u otro archivo que no es texto
                parte = MIMEApplication(contenido, _subtype='pdf')
            else:
                parte = MIMEText(contenido, 'html', 'utf-8')
            parte.add_header('Content-Disposition', 'attachment', filename=nombre)
            raiz.attach(parte)

        return raiz

    # ------------------------------------------------------------------ #
    #  Plantillas                                                         #
    # ------------------------------------------------------------------ #

    def _file_name(self, base):
        limpio = re.sub(r'[^A-Za-z0-9_\-]+', '_', base).strip('_') or 'BIAS_reporte'
        return f"{limpio}_{datetime.now():%Y-%m-%d}.html"

    def _base(self, title, body):
        """Cuerpo del mail. Armado con tablas para que no se rompa en Outlook."""
        fecha = f"{datetime.now():%d/%m/%Y %H:%M}"
        return f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{{margin:0;padding:0;background:#080C10;
  font-family:'IBM Plex Sans',Segoe UI,Arial,sans-serif;}}
.body b{{color:#E6EDF3;}}
.chip{{display:inline-block;background:#0D2040;border:1px solid rgba(31,111,235,0.4);
  color:#58A6FF;border-radius:5px;padding:2px 9px;font-family:monospace;
  font-size:13px;font-weight:600;}}
p{{margin:0 0 12px 0;}}
@media (max-width:620px){{ .wrap{{width:100% !important;}} }}
</style></head>
<body style="margin:0;padding:0;background:#080C10;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
       bgcolor="#080C10" style="background:#080C10;">
<tr><td align="center" style="padding:28px 12px;">

  <table role="presentation" class="wrap" width="600" cellpadding="0" cellspacing="0" border="0"
         style="width:600px;max-width:600px;background:#0D1117;border:1px solid #21262D;
                border-radius:12px;overflow:hidden;">

    <tr><td style="background:#0F2847;background:linear-gradient(135deg,#0F2847,#1F6FEB);
                   padding:20px 26px;">
      <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">
        <tr>
          <td width="46" valign="middle" style="width:46px;">
            <img src="cid:bias_logo" width="40" height="40" alt="BIAS"
                 style="display:block;border:0;border-radius:10px;"></td>
          <td valign="middle" style="padding-left:14px;">
            <div style="font-size:11px;color:rgba(255,255,255,0.65);letter-spacing:0.15em;
                        text-transform:uppercase;margin-bottom:4px;">
              BIAS · AI Investment Intelligence</div>
            <div style="font-size:18px;color:#ffffff;font-weight:600;line-height:1.3;">
              {title}</div></td>
        </tr>
      </table>
    </td></tr>

    <tr><td class="body" style="padding:24px 26px;color:#C9D1D9;font-size:14px;
             line-height:1.6;font-family:'IBM Plex Sans',Segoe UI,Arial,sans-serif;">
      {body}
    </td></tr>

    <tr><td style="border-top:1px solid #161B22;padding:14px 26px;color:#484F58;
             font-size:11px;text-align:center;
             font-family:'IBM Plex Sans',Segoe UI,Arial,sans-serif;">
      Generado el {fecha} · You're subscribed to this portfolio on BIAS.
    </td></tr>

  </table>

</td></tr></table>
</body></html>"""

    def _report_document(self, titulo, subtitulo, cuerpo):
        """Reporte que viaja adjunto: hoja clara, lista para imprimir o guardar en PDF."""
        fecha = f"{datetime.now():%d de %B de %Y · %H:%M}"
        return f"""<!DOCTYPE html><html lang="es"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>BIAS — {titulo}</title>
<style>
  :root{{ --tinta:#101828; --texto:#344054; --suave:#667085; --azul:#1F6FEB;
          --azul-osc:#0F2847; --borde:#E4E7EC; --papel:#ffffff; --fondo:#F7F9FC; }}
  *{{ box-sizing:border-box; }}
  body{{ margin:0; padding:0 18px 60px; background:var(--fondo); color:var(--texto);
         font-family:'Segoe UI',system-ui,-apple-system,sans-serif;
         font-size:15px; line-height:1.65; }}
  .hoja{{ max-width:820px; margin:0 auto; background:var(--papel);
          border:1px solid var(--borde); border-radius:14px;
          padding:0 0 34px; overflow:hidden; }}
  header{{ background:var(--azul-osc);
           background:linear-gradient(135deg,#0F2847,#1F6FEB);
           padding:26px 34px; color:#fff; }}
  .marca{{ display:flex; align-items:center; gap:13px; margin-bottom:16px; }}
  .marca img{{ width:38px; height:38px; border-radius:10px; display:block; }}
  .marca span{{ font-size:11px; letter-spacing:.16em; text-transform:uppercase;
                color:rgba(255,255,255,.7); }}
  header h1{{ margin:0; font-size:25px; font-weight:600; line-height:1.25; }}
  header .sub{{ margin-top:6px; font-size:14px; color:rgba(255,255,255,.78); }}
  .contenido{{ padding:26px 34px 0; }}
  h2{{ font-size:13px; letter-spacing:.1em; text-transform:uppercase;
       color:var(--suave); margin:30px 0 12px; font-weight:600; }}
  p{{ margin:0 0 12px; }}
  b{{ color:var(--tinta); }}
  .badge{{ display:inline-block; border-radius:999px; padding:3px 12px;
           font-size:12px; font-weight:600; white-space:nowrap; }}
  table{{ width:100%; border-collapse:collapse; }}
  .ficha td{{ padding:9px 0; border-bottom:1px solid var(--borde); vertical-align:top; }}
  .ficha .et{{ width:150px; color:var(--suave); font-size:13px; }}
  .ficha .va{{ color:var(--tinta); }}
  .datos th{{ text-align:left; font-size:11px; letter-spacing:.08em;
              text-transform:uppercase; color:var(--suave);
              border-bottom:2px solid var(--borde); padding:8px 10px; }}
  .datos td{{ padding:11px 10px; border-bottom:1px solid var(--borde);
              font-size:14px; color:var(--tinta); }}
  .datos .num{{ text-align:right; font-variant-numeric:tabular-nums; }}
  .datos .tenue{{ color:var(--suave); }}
  .cita{{ padding:14px 18px; border-radius:0 10px 10px 0;
          color:var(--tinta); font-size:15px; }}
  footer{{ max-width:820px; margin:16px auto 0; color:var(--suave);
           font-size:12px; text-align:center; }}
  @media print{{
    body{{ background:#fff; padding:0; font-size:12.5px; }}
    .hoja{{ border:0; border-radius:0; max-width:none; }}
    header{{ -webkit-print-color-adjust:exact; print-color-adjust:exact; }}
    .badge{{ -webkit-print-color-adjust:exact; print-color-adjust:exact; }}
  }}
</style></head>
<body>
<div class="hoja">
  <header>
    <div class="marca">
      <img src="data:image/png;base64,{LOGO_PNG_B64}" alt="BIAS">
      <span>BIAS · AI Investment Intelligence</span>
    </div>
    <h1>{titulo}</h1>
    <div class="sub">{subtitulo} · {fecha}</div>
  </header>
  <div class="contenido">
    {cuerpo}
  </div>
</div>
<footer>Reporte generado automaticamente por BIAS Stock Monitor.</footer>
</body></html>"""
