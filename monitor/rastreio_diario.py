"""Monitor diário de entregas (Frenet + Melhor Envio).

Uso: python3 rastreio_diario.py codigos.json saida.json
codigos.json: lista de {ref, cliente, pedido, transportadora, codigo}
Tokens: env FRENET_TOKEN / ME_TOKEN, ou lidos de ../server.py.
"""
import json, os, re, sys, datetime as dt, concurrent.futures as cf
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
def _tok(name):
    if os.environ.get(name): return os.environ[name]
    src = open(os.path.join(HERE, '..', 'server.py')).read()
    return re.search(name + r" = '([^']+)'", src).group(1)

FRENET = 'https://api.frenet.com.br/tracking/trackinginfo'
ME = 'https://melhorenvio.com.br/api/v2/me'
HOJE = dt.datetime.now()

PROBLEMA = re.compile(r'ausente|endere[cç]o (incorreto|insuficiente|inexistente|incomplet)|necessita sua a[cç][aã]o|a[cç][aã]o necess|n[aã]o (encontrad|procurad|entregue|localizad)|recusad|aguardando retirada|dispon[ií]vel para retirada|devol|retorn|extravi|avaria|roub|sinistr|tentativa|retid|fiscaliz|pend[eê]ncia|problema|anormal|bloquead|mudou-se|cancelad', re.I)
NA_CIDADE = re.compile(r'saiu para entrega|rota de entrega|em rota|saco de entrega|unidade de distribui|out for delivery|para entrega|entregador|dispatch', re.I)
ENTREGUE = re.compile(r'entregue ao destinat|objeto entregue|entrega realizada|assinad|^entregue|delivered|foi entregue', re.I)
SO_ETIQUETA = re.compile(r'etiqueta emitida|aguardando postagem', re.I)

def parse_dt(s):
    for f in ('%d/%m/%Y %H:%M', '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%d/%m/%Y %H:%M:%S'):
        try: return dt.datetime.strptime(s[:19], f)
        except Exception: pass
    return None

def servicos(cod):
    if re.fullmatch(r'[A-Z]{2}\d{9}[A-Z]{2}', cod): return ['03298', '03220']
    if cod.startswith('888'): return ['OPT_1']
    if re.fullmatch(r'\d{8,12}', cod): return ['F_3', 'OPT_1']
    return ['OPT_1', 'F_3']

def frenet(cod, tok):
    for sc in servicos(cod):
        try:
            r = requests.post(FRENET, json={'ShippingServiceCode': sc, 'TrackingNumber': cod},
                              headers={'token': tok, 'Accept': 'application/json'}, timeout=25).json()
        except Exception as e:
            r = {'ErrorMessage': str(e)}
        ev = r.get('TrackingEvents') or []
        if ev: return sc, ev, r.get('TrackingUrl')
    return None, [], None

def classificar(ev):
    if not ev: return 'SEM_EVENTOS', None
    ev = sorted(ev, key=lambda e: parse_dt(e.get('EventDateTime', '')) or dt.datetime.min, reverse=True)
    ult = ev[0]; d = (ult.get('EventDescription') or '')
    quando = parse_dt(ult.get('EventDateTime', ''))
    dias = (HOJE - quando).days if quando else None
    if re.search(r'devolvid|entregue ao remetente', d, re.I): s = 'DEVOLVIDO'
    elif ENTREGUE.search(d) and not PROBLEMA.search(d): s = 'ENTREGUE'
    elif PROBLEMA.search(d): s = 'PROBLEMA'
    elif NA_CIDADE.search(d): s = 'NA_CIDADE'
    elif SO_ETIQUETA.search(d): s = 'NAO_POSTADO'
    else: s = 'EM_TRANSITO'
    if s in ('EM_TRANSITO', 'NA_CIDADE', 'NAO_POSTADO') and dias is not None and dias >= 5:
        s += '_PARADO'
    return s, {'data': ult.get('EventDateTime'), 'local': ult.get('EventLocation'), 'desc': d[:160], 'dias_sem_mov': dias}

def melhor_envio(tok):
    h = {'Authorization': 'Bearer ' + tok, 'Accept': 'application/json',
         'User-Agent': 'CasaDoCafe (casadocafetorrefacao@gmail.com)'}
    out = []
    for st in ('posted',):
        page = 1
        while True:
            d = requests.get(f'{ME}/orders', params={'status': st, 'per_page': 100, 'page': page}, headers=h, timeout=30).json()
            for o in d.get('data', []):
                post = parse_dt((o.get('posted_at') or '')[:19])
                dias = (HOJE - post).days if post else None
                out.append({'fonte': 'melhorenvio', 'ref': o['protocol'], 'pedido': o.get('reminder'),
                            'cliente': o['to']['name'], 'cidade': f"{o['to']['city']}/{o['to']['state_abbr']}",
                            'transportadora': o['service']['company']['name'] + ' ' + o['service']['name'],
                            'codigo': o.get('self_tracking') or o.get('tracking'),
                            'status': 'EM_TRANSITO' if (dias or 0) <= (o.get('delivery_max') or 99) + 1 else 'ATRASADO_ME',
                            'ultimo': {'data': o.get('posted_at'), 'desc': f"postado há {dias} dias; prazo {o.get('delivery_min')}-{o.get('delivery_max')} dias"},
                            'link': 'https://www.melhorrastreio.com.br/rastreio/' + (o.get('self_tracking') or '')})
            if not d.get('next_page_url'): break
            page += 1
    return out

def main(cods_path, out_path):
    ft, mt = _tok('FRENET_TOKEN'), _tok('ME_TOKEN')
    cods = json.load(open(cods_path))
    res = []
    def job(c):
        sc, ev, url = frenet(c['codigo'], ft)
        s, ult = classificar(ev)
        return {**c, 'fonte': 'frenet', 'servico': sc, 'status': s, 'ultimo': ult, 'link': url}
    with cf.ThreadPoolExecutor(6) as ex:
        res = list(ex.map(job, cods))
    res += melhor_envio(mt)
    json.dump({'gerado_em': HOJE.isoformat(timespec='minutes'), 'itens': res}, open(out_path, 'w'), ensure_ascii=False, indent=1)
    from collections import Counter
    print(Counter(r['status'] for r in res))

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
