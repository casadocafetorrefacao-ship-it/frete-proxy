"""Monitor diário de entregas (Melhor Envio + Frenet).

Uso: python monitor_entregas.py [codigo_jadlog_frenet ...]
- Melhor Envio: lista automaticamente pedidos 'posted' e 'undelivered'.
- Frenet: não há endpoint de listagem; passe os códigos (ex.: das confirmações Jadlog no Gmail).
Classifica cada envio: ENTREGUE, PROBLEMA, SAIU_ENTREGA, NA_CIDADE, EM_TRANSITO, SEM_EVENTOS.
"""
import datetime
import re
import sys

import requests

from server import FRENET_TOKEN, ME_TOKEN

PROB = re.compile(r'INSUCESSO|AUSENTE|DEVOLU|AVARIA|EXTRAV|ROUBO|RECUSA|ENDERE|PROBLEMA|SINISTRO|RETID|IMPREVISTO|N[AÃ]O ENTREG', re.I)
ME_HEADERS = {'Authorization': f'Bearer {ME_TOKEN}', 'Accept': 'application/json', 'User-Agent': 'CasaDoCafe-Monitor'}


def melhor_envio(status):
    url = f'https://melhorenvio.com.br/api/v2/me/orders?status={status}&per_page=100'
    out = []
    while url:
        d = requests.get(url, headers=ME_HEADERS, timeout=30).json()
        out += d.get('data', [])
        url = d.get('next_page_url')
    return out


def frenet(code, service='F_3'):
    r = requests.post('https://api.frenet.com.br/tracking/trackinginfo',
                      json={'ShippingServiceCode': service, 'TrackingNumber': code},
                      headers={'token': FRENET_TOKEN, 'Accept': 'application/json'}, timeout=30)
    ev = r.json().get('TrackingEvents') or []
    if not ev:
        return 'SEM_EVENTOS', '', []
    last = ev[0]
    desc, loc = last['EventDescription'].upper(), last['EventLocation'].upper()
    if desc.startswith('ENTREGUE'):
        st = 'ENTREGUE'
    elif PROB.search(desc):
        st = 'PROBLEMA'
    elif desc.startswith('EM ROTA'):
        st = 'SAIU_ENTREGA'
    elif loc.startswith('CO ') and desc in ('ENTRADA', 'MOVIMENTAÇÃO INTERNA'):
        st = 'NA_CIDADE'
    else:
        st = 'EM_TRANSITO'
    probs = [f"{e['EventDateTime'][:16]} {e['EventLocation']}: {e['EventDescription']}" for e in ev if PROB.search(e['EventDescription'])]
    return st, f"{last['EventDateTime'][:16]} {last['EventLocation']}: {last['EventDescription']}", probs


def main(codes):
    print(f'== Relatório {datetime.date.today()} ==')
    for status in ('posted', 'undelivered'):
        for o in melhor_envio(status):
            print(f"ME {status:11} {o['tracking']} {o['service']['company']['name']} -> {o['to']['city']}/{o['to']['state_abbr']} "
                  f"postado {o['posted_at']} prazo {o['delivery_max']}d {o.get('reminder') or ''}")
    for c in codes:
        st, last, probs = frenet(c)
        print(f'FRENET {st:12} {c} | {last}' + (' | ALERTAS: ' + ' ; '.join(probs) if probs else ''))


if __name__ == '__main__':
    main(sys.argv[1:])
