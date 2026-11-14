"""Monitor diário de entregas (Melhor Envio + Frenet/Jadlog).
Uso: python3 rastreio_diario.py [codigos_jadlog.txt]
Lê os tokens de server.py. Saída: JSON com cada envio classificado.
"""
import json, re, sys, os, datetime as dt
import requests

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
src = open(os.path.join(BASE, 'server.py')).read()
FRENET = re.search(r"FRENET_TOKEN = '([^']+)'", src).group(1)
ME = re.search(r"ME_TOKEN = '([^']+)'", src).group(1)
HOJE = dt.datetime.now()

PROBLEMA = re.compile(r'INSUCESSO|IMPOSSIBILIDADE|AUSENTE|DEVOLU|ENDERE|AVARI|EXTRAV|RETID|RECUS|ROUBO|SINISTRO|NAO ENTREG|NÃO ENTREG|BLOQUE|DESTINAT', re.I)

def frenet_track(code, svc='F_3'):
    r = requests.post('https://api.frenet.com.br/tracking/trackinginfo', timeout=30,
        headers={'token': FRENET, 'Content-Type': 'application/json', 'Accept': 'application/json'},
        json={'ShippingServiceCode': svc, 'TrackingNumber': code})
    return r.json()

def classificar(evs):
    if not evs:
        return 'SEM_EVENTOS', None
    evs = sorted(evs, key=lambda e: e['EventDateTime'])
    last = evs[-1]
    desc = last['EventDescription'].upper()
    t = dt.datetime.strptime(last['EventDateTime'][:19], '%Y-%m-%d %H:%M:%S')
    parado = (HOJE - t).days
    if 'ENTREGUE' in desc and 'NAO' not in desc and 'NÃO' not in desc:
        return 'ENTREGUE', last
    teve_problema = any(PROBLEMA.search(e['EventDescription']) for e in evs)
    if PROBLEMA.search(desc):
        return 'PROBLEMA', last
    # unidade de última milha (CO) depois de passar por hub (MT) = chegou na cidade
    passou_hub = any(e['EventLocation'].upper().startswith('MT') for e in evs)
    na_cidade = last['EventLocation'].upper().startswith('CO') and (passou_hub or 'ROTA' in desc)
    if 'ROTA' in desc:
        st = 'SAIU_PARA_ENTREGA'
    elif na_cidade:
        st = 'CHEGOU_NA_CIDADE'
    else:
        st = 'EM_TRANSITO'
    if teve_problema:
        st += '+TEVE_OCORRENCIA'
    if parado >= 3:
        st += f'+PARADO_{parado}D'
    return st, last

out = []
codes = []
if len(sys.argv) > 1:
    codes = [l.strip() for l in open(sys.argv[1]) if l.strip()]
for c in codes:
    try:
        d = frenet_track(c)
        st, last = classificar(d.get('TrackingEvents') or [])
        out.append({'origem': 'frenet/jadlog', 'codigo': c, 'status': st, 'ultimo': last,
                    'eventos': d.get('TrackingEvents'), 'url': d.get('TrackingUrl')})
    except Exception as e:
        out.append({'origem': 'frenet/jadlog', 'codigo': c, 'status': 'ERRO', 'erro': str(e)})

h = {'Authorization': f'Bearer {ME}', 'Accept': 'application/json', 'User-Agent': 'CasaDoCafe-Monitor'}
r = requests.get('https://melhorenvio.com.br/api/v2/me/orders', params={'status': 'posted', 'per_page': 100}, headers=h, timeout=90)
for o in r.json().get('data', []):
    posted = dt.datetime.strptime(o['posted_at'], '%Y-%m-%d %H:%M:%S')
    dias = (HOJE - posted).days
    out.append({'origem': 'melhorenvio/' + o['service']['company']['name'], 'codigo': o['tracking'],
                'nf': o.get('reminder'), 'cliente': o['to']['name'], 'cidade': f"{o['to']['city']}/{o['to']['state_abbr']}",
                'postado': o['posted_at'], 'prazo_max_dias_uteis': o['delivery_max'], 'dias_corridos_desde_postagem': dias,
                'status': 'EM_TRANSITO(ME)'})
json.dump(out, sys.stdout, ensure_ascii=False, indent=1, default=str)
