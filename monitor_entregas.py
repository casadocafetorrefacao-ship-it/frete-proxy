"""
Monitor diário de entregas - Melhor Envio + Frenet.

Uso:
  python3 monitor_entregas.py                       # só Melhor Envio
  python3 monitor_entregas.py F_3:10081185810831 OPT_1:888030987602765 03298:AP650364565BR

Para a Frenet não existe endpoint de listagem de envios: os códigos são passados
como argumentos no formato SERVICO:CODIGO (F_3 = Jadlog, OPT_1 = Optimus,
03298 = PAC, 03220 = Sedex). Na Jadlog, use o número de remessa (CTe) do e-mail
"Confirmação de envio Jadlog".

Usa apenas a biblioteca padrão (sem requests) para rodar em qualquer ambiente.
"""
import json
import os
import re
import sys
import urllib.request
from datetime import datetime

# Reaproveita os tokens do server.py sem importar o Flask.
_cfg = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'server.py')).read()
FRENET_TOKEN = re.search(r"FRENET_TOKEN = '([^']+)'", _cfg).group(1)
ME_TOKEN = re.search(r"ME_TOKEN = '([^']+)'", _cfg).group(1)

ME_BASE = 'https://melhorenvio.com.br/api/v2/me'
FRENET_TRACK = 'https://api.frenet.com.br/tracking/trackinginfo'
PARADO_HORAS = 48  # sem movimentação por mais que isso => alerta


def _req(url, headers, data=None):
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, headers=headers, data=body)
    with urllib.request.urlopen(req, timeout=40) as r:
        raw = r.read()
        return json.loads(raw) if raw else None


def melhor_envio():
    h = {'Authorization': f'Bearer {ME_TOKEN}', 'Accept': 'application/json',
         'Content-Type': 'application/json', 'User-Agent': 'CasaDoCafe-Monitor'}
    pedidos, page = [], 1
    while True:
        d = _req(f'{ME_BASE}/orders?per_page=100&page={page}', h)
        pedidos += d['data']
        if page >= d['last_page'] or page >= 20:
            break
        page += 1
    alertas = []
    agora = datetime.now()
    for o in pedidos:
        st = o['status']
        to = o.get('to') or {}
        ref = f"{o.get('reminder') or o['protocol']} {o.get('tracking')} -> {to.get('city')}/{to.get('state_abbr')}"
        if st == 'posted' and o.get('posted_at'):
            dias = (agora - datetime.fromisoformat(o['posted_at'])).days
            if dias > (o.get('delivery_max') or 0):
                alertas.append(f'ATRASADO ({dias}d, prazo {o.get("delivery_max")}d): {ref}')
            else:
                alertas.append(f'em trânsito ({dias}d/{o.get("delivery_max")}d): {ref}')
        elif st in ('undelivered', 'paused', 'suspended'):
            alertas.append(f'{st.upper()}: {ref} postado {o.get("posted_at")}')
        elif st == 'released':
            alertas.append(f'ETIQUETA PAGA E NÃO POSTADA desde {o.get("paid_at")}: {ref}')
    return len(pedidos), alertas


def frenet(servico, codigo):
    h = {'token': FRENET_TOKEN, 'Accept': 'application/json', 'Content-Type': 'application/json'}
    d = _req(FRENET_TRACK, h, {'ShippingServiceCode': servico, 'TrackingNumber': codigo})
    ev = (d or {}).get('TrackingEvents') or []
    if not ev:
        return f'{codigo}: sem eventos'
    ult = ev[0]
    desc = ult['EventDescription']
    txt = f"{codigo}: {ult['EventDateTime']} {ult['EventLocation']} | {desc[:100]}"
    flags = [k for k in ('EXTRAVIO', 'INSUCESSO', 'AUSENTE', 'DEVOLU', 'AGUARDANDO RETIRADA')
             if k in desc.upper()]
    try:
        fmt = '%d/%m/%Y %H:%M' if '/' in ult['EventDateTime'] else '%Y-%m-%d %H:%M:%S'
        horas = (datetime.now() - datetime.strptime(ult['EventDateTime'], fmt)).total_seconds() / 3600
        if horas > PARADO_HORAS and 'ENTREGUE' not in desc.upper() and 'ASSINAD' not in desc.upper():
            flags.append(f'PARADO {horas / 24:.1f}d')
    except ValueError:
        pass
    return ('ALERTA ' + ','.join(flags) + ' - ' if flags else '') + txt


if __name__ == '__main__':
    total, alertas = melhor_envio()
    print(f'== Melhor Envio: {total} pedidos')
    for a in alertas:
        print('  ', a)
    if len(sys.argv) > 1:
        print('== Frenet')
        for arg in sys.argv[1:]:
            servico, codigo = arg.split(':', 1)
            print('  ', frenet(servico, codigo))
