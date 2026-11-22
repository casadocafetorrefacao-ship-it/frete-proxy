"""Monitor diário de entregas (Melhor Envio + Frenet/Jadlog).

Uso: python rastreio_diario.py [arquivo_com_codigos_jadlog.txt]
Tokens: lidos de ME_TOKEN / FRENET_TOKEN no ambiente ou, na falta, de server.py.
Sinaliza envios que chegaram na unidade de destino e travaram, rotas
recalculadas, entregas futuras e pedidos ME não entregues/não postados.
"""
import json, os, re, sys, datetime as dt
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(HERE, 'server.py'), encoding='utf-8').read()
ME = os.environ.get('ME_TOKEN') or re.search(r"ME_TOKEN = '([^']+)'", src).group(1)
FR = os.environ.get('FRENET_TOKEN') or re.search(r"FRENET_TOKEN = '([^']+)'", src).group(1)
UA = 'CasaDoCafe-Rastreio'
NOW = dt.datetime.now()
ALERTA = ('RECALCULANDO', 'ENTREGA FUTURA', 'AUSENTE', 'DEVOL', 'RECUS', 'AVARIA', 'EXTRAV', 'ENDERECO', 'ENDEREÇO', 'INSUCESSO')


def melhor_envio():
    out, page = [], 1
    while True:
        r = requests.get('https://melhorenvio.com.br/api/v2/me/orders',
                         params={'per_page': 100, 'page': page},
                         headers={'Authorization': f'Bearer {ME}', 'Accept': 'application/json', 'User-Agent': UA}, timeout=30)
        d = r.json(); out += d['data']
        if page >= d['last_page']: return out
        page += 1


def frenet(code, service='F_3'):
    r = requests.post('https://api.frenet.com.br/tracking/trackinginfo',
                      json={'ShippingServiceCode': service, 'TrackingNumber': code},
                      headers={'token': FR, 'Accept': 'application/json'}, timeout=30)
    return r.json()


def parse(s):
    for f in ('%Y-%m-%d %H:%M:%S', '%d/%m/%Y %H:%M'):
        try: return dt.datetime.strptime(s, f)
        except ValueError: pass


def main():
    print('== Melhor Envio')
    for o in melhor_envio():
        if o['status'] in ('posted',) or (o['status'] in ('undelivered', 'released', 'paused') and o['created_at'] >= (NOW - dt.timedelta(days=45)).strftime('%Y-%m-%d')):
            print(f"  [{o['status']}] {o['protocol']} {o.get('tracking')} {o['to'].get('city')}/{o['to'].get('state_abbr')} {o.get('reminder') or ''}")
    if len(sys.argv) > 1:
        print('== Jadlog via Frenet')
        for code in open(sys.argv[1]).read().split():
            ev = frenet(code).get('TrackingEvents') or []
            if not ev: print(f'  {code}: sem eventos'); continue
            last = ev[0]; desc = last['EventDescription'].upper()
            if 'ENTREGUE' in desc: continue
            dias = (NOW - parse(last['EventDateTime'])).days if parse(last['EventDateTime']) else '?'
            flag = 'ALERTA' if any(k in ' '.join(e['EventDescription'].upper() for e in ev) for k in ALERTA) or (isinstance(dias, int) and dias >= 3) else 'ok'
            print(f"  [{flag}] {code}: {last['EventDescription']} @ {last['EventLocation']} ({last['EventDateTime']}, {dias}d parado)")


if __name__ == '__main__':
    main()
