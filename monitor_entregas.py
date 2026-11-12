"""Monitor diário de entregas (Melhor Envio + Frenet).

Uso:
    python3 monitor_entregas.py [SERVICO:CODIGO ...]

- Melhor Envio: lista automaticamente os pedidos com status posted/undelivered.
- Frenet: a API não lista envios; passe os códigos como argumentos
  (ex.: F_3:10081185780523  OPT_1:888031005809695  03298:AP...BR).
  Códigos de serviço: F_3=Jadlog, OPT_1=Optimus, 03298=PAC, 03220=Sedex.

Tokens: variáveis FRENET_TOKEN / ME_TOKEN, ou os valores de server.py.
Somente biblioteca padrão (sem requests).
"""
import json
import os
import re
import sys
import urllib.request
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))


def _token(name):
    if os.environ.get(name):
        return os.environ[name]
    src = open(os.path.join(HERE, 'server.py'), encoding='utf-8').read()
    return re.search(rf"{name} = '([^']+)'", src).group(1)


def _req(url, headers, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers,
                                 method='POST' if body is not None else 'GET')
    return json.load(urllib.request.urlopen(req, timeout=30))


def melhor_envio():
    h = {'Accept': 'application/json', 'Content-Type': 'application/json',
         'Authorization': 'Bearer ' + _token('ME_TOKEN'),
         'User-Agent': 'CasaDoCafe-Monitor'}
    print('=== MELHOR ENVIO ===')
    for status in ('posted', 'undelivered'):
        url = 'https://melhorenvio.com.br/api/v2/me/orders?' + urllib.parse.urlencode(
            {'status': status, 'per_page': 100})
        try:
            d = _req(url, h)
        except Exception as e:  # noqa: BLE001
            print(f'[{status}] erro: {e}')
            continue
        print(f'[{status}] total={d.get("total")}')
        for o in d.get('data', []):
            to = o.get('to') or {}
            svc = o.get('service') or {}
            print(f"  {o.get('protocol')} | {o.get('tracking')} | "
                  f"{(svc.get('company') or {}).get('name')} {svc.get('name')} | "
                  f"{to.get('city')}/{to.get('state_abbr')} | postado {o.get('posted_at')} | "
                  f"prazo {o.get('delivery_min')}-{o.get('delivery_max')}d | atualizado {o.get('updated_at')}")


def frenet(codes):
    if not codes:
        return
    h = {'Accept': 'application/json', 'Content-Type': 'application/json',
         'token': _token('FRENET_TOKEN')}
    print('=== FRENET ===')
    for item in codes:
        svc, code = item.split(':', 1)
        try:
            d = _req('https://api.frenet.com.br/tracking/trackinginfo', h,
                     {'ShippingServiceCode': svc, 'TrackingNumber': code})
        except Exception as e:  # noqa: BLE001
            print(f'  {svc}:{code} erro: {e}')
            continue
        ev = d.get('TrackingEvents') or []
        last = ev[0] if ev else None  # Frenet devolve o evento mais recente primeiro
        if last:
            print(f"  {svc}:{code} | {last['EventDateTime']} | {last['EventLocation']} | "
                  f"{last['EventDescription']}")
        else:
            print(f'  {svc}:{code} | sem eventos')


if __name__ == '__main__':
    melhor_envio()
    frenet(sys.argv[1:])
