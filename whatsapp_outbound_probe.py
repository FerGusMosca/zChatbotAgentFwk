# whatsapp_outbound_probe.py
"""
WhatsApp outbound probe (Twilio).
- Sends an outbound WhatsApp message (freeform if inside 24h; otherwise use a template).
- Standalone: run `python whatsapp_outbound_probe.py`
- Config via env: TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, WHATSAPP_FROM, WHATSAPP_TO,
  SALES_PRODUCT (optional), USE_TEMPLATE (0/1), TEMPLATE_BODY (text with {name} {product}),
  or CONTENT_TEMPLATE (pre-approved copy if you want to keep it simple).
"""

import os
from dataclasses import dataclass
from typing import Optional
from twilio.rest import Client

@dataclass
class ProbeCfg:
    account_sid: str
    auth_token: str
    wa_from: str       # e.g. 'whatsapp:+14155238886' (sandbox) or your BA number
    wa_to: str         # e.g. 'whatsapp:+54911XXXXXXXX'
    product: str = "seguro médico"
    customer_name: str = "Fernando"
    use_template: bool = False
    template_body: str = "Hola {name}, ¿cómo estás? Te llamo para ofrecerte un {product} con cobertura total. ¿Querés que te cuente rápido los beneficios?"

def load_cfg() -> ProbeCfg:
    return ProbeCfg(
        account_sid=os.getenv("TWILIO_ACCOUNT_SID", ""),#Poner twilio account id
        auth_token=os.getenv("TWILIO_AUTH_TOKEN", ""),#poner auth token
        wa_from=os.getenv("WHATSAPP_FROM", "whatsapp:+14155238886"),
        wa_to=os.getenv("WHATSAPP_TO", "whatsapp:+54911xxxx"),  # your WhatsApp number with whatsapp:+ prefix
        product=os.getenv("SALES_PRODUCT", "seguro médico"),
        customer_name=os.getenv("SALES_NAME", "Fernando"),
        use_template=os.getenv("USE_TEMPLATE", "0") == "1",
        template_body=os.getenv("TEMPLATE_BODY", "Hola {name}, vengo a contarte sobre un {product}. ¿Te interesa que te comparta beneficios y precio?"),
    )

def build_message(cfg: ProbeCfg) -> str:
    if cfg.use_template:
        return cfg.template_body.format(name=cfg.customer_name, product=cfg.product)
    # freeform: simple pitch
    return (f"Hola {cfg.customer_name}, ¿cómo estás? 👋\n\n"
            f"Te contacto para ofrecerte un *{cfg.product}* con excelente relación costo/beneficio. "
            f"¿Te cuento 3 ventajas clave y precio estimado en 30 segundos?")

def main() -> int:
    cfg = load_cfg()
    if not (cfg.account_sid and cfg.auth_token and cfg.wa_from and cfg.wa_to):
        print("CONFIG_ERROR: set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, WHATSAPP_FROM, WHATSAPP_TO")
        return 2

    client = Client(cfg.account_sid, cfg.auth_token)
    body = build_message(cfg)

    try:
        msg = client.messages.create(
            from_=cfg.wa_from,
            to=cfg.wa_to,
            body=body
            # Nota: Para plantillas “oficiales” vía Content API, usar contentSid/variables.
            # Este ejemplo usa body plano (válido si estás dentro de 24h desde último mensaje del usuario).
        )
        print(f"OK | sid={msg.sid}")
        return 0
    except Exception as e:
        print(f"SEND_ERROR | {e}")
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
