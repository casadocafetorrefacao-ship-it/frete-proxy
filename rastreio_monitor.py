"""
Monitor diário de entregas - Melhor Envio + Frenet.

Uso:  python3 rastreio_monitor.py            (gera relatório no terminal + rastreio_status.json)

Tokens: lidos das variáveis de ambiente ME_TOKEN / FRENET_TOKEN; se ausentes,
usa as constantes de server.py (não adicione novos segredos neste arquivo).

Frenet não oferece endpoint para listar envios com o token de cotação, então os
códigos a acompanhar ficam em rastreio_frenet.txt (uma linha: SERVICO CODIGO).
"""
import datetime
import json
import os
import sys
import urllib.request

import re


def _const(nome):
    """Lê a constante de server.py sem importá-lo (evita depender do Flask)."""
    try:
        src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'server.py'), encoding='utf-8').read()
        m = re.search(nome + r"\s*=\s*'([^']+)'", src)
        return m.group(1) if m else ''
    except OSError:
        return ''


ME_TOKEN = os.environ.get('ME_TOKEN') or _const('ME_TOKEN')
FRENET_TOKEN = os.environ.get('FRENET_TOKEN') or _const('FRENET_TOKEN')
UA = 'CasaDoCafe-Rastreio/1.0'
HOJE = datetime.datetime.now()
PARADO_DIAS = 3  # sem movimentação há mais que isso = alerta

PROBLEMA = ('insucesso', 'ausente', 'extravi', 'devolu', 'timeout', 'avaria',
            'recusad', 'não entregue', 'nao entregue', 'aguardando retirada',
            'endereço incorreto', 'endereco incorreto', 'roubo', 'sinistro')
ENTREGUE = ('entregue ao destinat', 'foi assinado', 'delivered')


def _req(url, data=None, headers=None):
    body = json.dumps(data).encode() if data is not None else None
    r = urllib.request.Request(url, data=body, headers=headers or {})
    with urllib.request.urlopen(r, timeout=30) as resp:
        raw = resp.read()
        return json.loads(raw) if raw else None


def _dt(s):
    for f in ('%Y-%m-%d %H:%M:%S', '%d/%m/%Y %H:%M', '%d/%m/%Y %H:%M:%S'):
        try:
            return datetime.datetime.strptime(s or '', f)
        except ValueError:
            pass
    return None


def melhor_envio():
    h = {'Accept': 'application/json', 'Authorization': f'Bearer {ME_TOKEN}', 'User-Agent': UA}
    pedidos, page = [], 1
    while True:
        d = _req(f'https://melhorenvio.com.br/api/v2/me/orders?per_page=100&page={page}', headers=h) or {}
        pedidos += d.get('data', [])
        if page >= (d.get('last_page') or 1):
            break
        page += 1
    out = []
    for p in pedidos:
        st = p.get('status')
        if st in ('delivered', 'canceled'):
            continue
        ref = _dt(p.get('posted_at') or p.get('paid_at') or p.get('created_at'))
        out.append({
            'origem': 'melhorenvio', 'pedido': p.get('protocol'), 'rastreio': p.get('tracking'),
            'transportadora': (p.get('service') or {}).get('company', {}).get('name'),
            'cidade': f"{(p.get('to') or {}).get('city')}/{(p.get('to') or {}).get('state_abbr')}",
            'status': st, 'dias': (HOJE - ref).days if ref else None,
            'alerta': st in ('undelivered', 'paused') or (st == 'released' and ref and (HOJE - ref).days > 2)
                      or (st == 'posted' and ref and (HOJE - ref).days > 7),
        })
    return out, len(pedidos)


def frenet():
    arq = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'rastreio_frenet.txt')
    if not os.path.exists(arq):
        return []
    h = {'token': FRENET_TOKEN, 'Content-Type': 'application/json', 'Accept': 'application/json'}
    out = []
    for linha in open(arq, encoding='utf-8'):
        linha = linha.split('#')[0].strip()
        if not linha:
            continue
        svc, code = linha.split()[:2]
        try:
            d = _req('https://api.frenet.com.br/tracking/trackinginfo',
                     {'ShippingServiceCode': svc, 'TrackingNumber': code}, h) or {}
        except Exception as e:
            out.append({'origem': 'frenet', 'rastreio': code, 'status': f'ERRO {e}', 'alerta': True})
            continue
        ev = sorted(d.get('TrackingEvents') or [], key=lambda e: _dt(e.get('EventDateTime')) or datetime.datetime.min)
        ult = ev[-1] if ev else {}
        desc = (ult.get('EventDescription') or 'sem eventos')
        quando = _dt(ult.get('EventDateTime'))
        dias = (HOJE - quando).days if quando else None
        low = desc.lower()
        entregue = any(k in low for k in ENTREGUE) and 'devolu' not in low
        out.append({
            'origem': 'frenet', 'rastreio': code, 'servico': svc, 'status': desc,
            'local': ult.get('EventLocation'), 'ultima_mov': ult.get('EventDateTime'), 'dias': dias,
            'entregue': entregue,
            'alerta': (not entregue) and (any(k in low for k in PROBLEMA) or (dias or 0) > PARADO_DIAS or not ev),
        })
    return out


def main():
    me, total_me = melhor_envio()
    fr = frenet()
    todos = me + fr
    json.dump({'gerado_em': HOJE.isoformat(), 'itens': todos}, open('rastreio_status.json', 'w'),
              ensure_ascii=False, indent=1)
    print(f'Melhor Envio: {total_me} pedidos, {len(me)} em aberto | Frenet: {len(fr)} códigos acompanhados')
    for i in todos:
        if i.get('alerta'):
            print('ALERTA', json.dumps(i, ensure_ascii=False))
    return 1 if any(i.get('alerta') for i in todos) else 0


if __name__ == '__main__':
    sys.exit(main())
