"""
Monitor diário de entregas - Frenet + Melhor Envio.

Uso:
    python monitor_entregas.py codigos.json > relatorio.json

`codigos.json` é uma lista de objetos {"ref": "...", "codigo": "...", "carrier": "..."}
(ex.: códigos de rastreio das ocorrências abertas). Além deles, o script busca
automaticamente na Melhor Envio todos os envios ainda não entregues.

Classifica cada envio em:
  ENTREGUE, NA_CIDADE (saiu para entrega / unidade de entrega / aguardando retirada),
  PROBLEMA (extravio, devolução, avaria, tentativa sem sucesso, endereço...),
  PARADO (sem movimentação há N dias), EM_TRANSITO, SEM_DADOS.
"""
import json
import re
import sys
import unicodedata
from datetime import datetime

import requests

from server import FRENET_TOKEN, ME_TOKEN

FRENET_TRACK = 'https://api.frenet.com.br/tracking/trackinginfo'
ME_BASE = 'https://melhorenvio.com.br/api/v2/me'
DIAS_PARADO = 3

KW_ENTREGUE = ['entregue ao destinatario', 'objeto entregue', 'entrega realizada', 'entregue',
               'pacote foi assinado', 'foi assinad']
KW_NAO_POSTADO = ['etiqueta expirada', 'etiqueta cancelada', 'aguardando postagem']
KW_PROBLEMA = ['extravi', 'devolv', 'devoluc', 'avaria', 'roubo', 'sinistro', 'nao entregue',
               'ausente', 'endereco incorreto', 'endereco insuficiente', 'destinatario mudou',
               'recusad', 'tentativa', 'nao procurado', 'retido', 'fiscaliza', 'insucesso',
               'nao foi possivel', 'divergencia', 'bloqueado', 'atraso']
KW_NA_CIDADE = ['saiu para entrega', 'em rota de entrega', 'saida para entrega', 'rota de entrega',
                'aguardando retirada', 'disponivel para retirada', 'unidade de distribuicao',
                'chegada na unidade de entrega', 'base de entrega', 'em entrega',
                'esta enviando a encomenda', 'entregador']


def norm(s):
    s = unicodedata.normalize('NFKD', s or '').encode('ascii', 'ignore').decode()
    return s.lower()


def parse_dt(s):
    for fmt in ('%d/%m/%Y %H:%M', '%Y-%m-%d %H:%M:%S', '%d/%m/%Y %H:%M:%S', '%Y-%m-%dT%H:%M:%S'):
        try:
            return datetime.strptime(s[:19] if 'T' in s else s, fmt)
        except (ValueError, TypeError):
            continue
    return None


def servicos_para(codigo, carrier=''):
    c = codigo.upper()
    if re.fullmatch(r'[A-Z]{2}\d{9}BR', c):
        return ['03220', '03298']
    if re.fullmatch(r'[A-Z]{2}\d{9}BR', c) and c.startswith('AP'):
        return ['03298', '03301']
    if c.startswith('888'):
        return ['OPT_1']
    if c.isdigit() and len(c) <= 12:
        return ['F_3']
    return ['OPT_1', '03298', 'F_3']


def frenet_track(codigo, carrier=''):
    headers = {'token': FRENET_TOKEN, 'Content-Type': 'application/json', 'Accept': 'application/json'}
    for svc in servicos_para(codigo, carrier):
        try:
            r = requests.post(FRENET_TRACK, headers=headers, timeout=30,
                              json={'ShippingServiceCode': svc, 'TrackingNumber': codigo})
            d = r.json()
        except Exception as e:  # noqa: BLE001
            d = {'ErrorMessage': str(e)}
        if d.get('TrackingEvents'):
            return d
    return d


def classificar(eventos, agora):
    if not eventos:
        return 'SEM_DADOS', None
    ult = eventos[0]
    desc = norm(ult.get('EventDescription'))
    dt = parse_dt(ult.get('EventDateTime', ''))
    dias = (agora - dt).days if dt else None
    if any(k in desc for k in KW_NAO_POSTADO):
        return 'NAO_POSTADO', dias
    if any(k in desc for k in KW_PROBLEMA):
        return 'PROBLEMA', dias
    if any(k in desc for k in KW_ENTREGUE) and 'saiu' not in desc:
        return 'ENTREGUE', dias
    # Chegou à cidade (saiu para entrega antes) mas o último evento já não é de entrega:
    # pacote está voltando da cidade do cliente -> provável devolução.
    if any(any(k in norm(e.get('EventDescription')) for k in KW_NA_CIDADE) for e in eventos[1:]) \
            and not any(k in desc for k in KW_NA_CIDADE):
        return 'VOLTANDO_DA_CIDADE', dias
    if any(k in desc for k in KW_NA_CIDADE):
        return ('PARADO' if dias is not None and dias >= DIAS_PARADO else 'NA_CIDADE'), dias
    if dias is not None and dias >= DIAS_PARADO:
        return 'PARADO', dias
    return 'EM_TRANSITO', dias


def melhor_envio_pendentes():
    h = {'Authorization': f'Bearer {ME_TOKEN}', 'Accept': 'application/json',
         'User-Agent': 'CasaDoCafe Monitor'}
    out = []
    for status in ('posted', 'released', 'paused', 'undelivered'):
        page = 1
        while True:
            r = requests.get(f'{ME_BASE}/orders', headers=h, timeout=60,
                             params={'status': status, 'per_page': 100, 'page': page})
            if r.status_code != 200 or not r.content:
                break
            j = r.json()
            out += j.get('data', [])
            if page >= j.get('last_page', 1):
                break
            page += 1
    return out


def main():
    agora = datetime.now()
    codigos = json.load(open(sys.argv[1])) if len(sys.argv) > 1 else []
    resultado = []

    for o in melhor_envio_pendentes():
        to = o.get('to') or {}
        resultado.append({
            'fonte': 'melhorenvio', 'ref': o.get('reminder') or o.get('protocol'),
            'codigo': o.get('tracking'), 'status_me': o.get('status'),
            'destino': f"{to.get('city')}-{to.get('state_abbr')}",
            'postado': o.get('posted_at'), 'prazo_max_dias': o.get('delivery_max'),
            'classificacao': {'posted': 'EM_TRANSITO', 'released': 'NAO_POSTADO',
                              'paused': 'PROBLEMA', 'undelivered': 'PROBLEMA'}.get(o.get('status')),
        })

    vistos = set()
    for c in codigos:
        cod = c['codigo'].strip()
        if not cod or cod in vistos:
            continue
        vistos.add(cod)
        d = frenet_track(cod, c.get('carrier', ''))
        evs = d.get('TrackingEvents') or []
        cls, dias = classificar(evs, agora)
        ult = evs[0] if evs else {}
        resultado.append({
            'fonte': 'frenet', 'ref': c.get('ref'), 'codigo': cod,
            'classificacao': cls, 'dias_sem_mov': dias,
            'ultimo_evento': ult.get('EventDescription'), 'local': ult.get('EventLocation'),
            'data': ult.get('EventDateTime'), 'erro': d.get('ErrorMessage'),
        })

    json.dump(resultado, sys.stdout, ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()
