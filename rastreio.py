"""Rotas de rastreio (Frenet + Melhor Envio) para o acompanhamento diário de entregas."""
import hmac
import os

import requests
from flask import Blueprint, jsonify, request

from server import FRENET_TOKEN, ME_TOKEN

rastreio = Blueprint('rastreio', __name__)

FRENET_TRACKING_API = 'https://api.frenet.com.br/tracking/trackinginfo'
ME_ORDERS_API = 'https://melhorenvio.com.br/api/v2/me/orders'
ME_STATUSES = ('posted', 'undelivered', 'released')


def _autorizado():
    """Exige a chave RASTREIO_KEY (header X-Rastreio-Key); sem a variável configurada, bloqueia."""
    chave = os.environ.get('RASTREIO_KEY', '')
    enviada = request.headers.get('X-Rastreio-Key', '')
    return bool(chave) and hmac.compare_digest(chave, enviada)


@rastreio.before_request
def _checa_chave():
    if request.method != 'OPTIONS' and not _autorizado():
        return jsonify({'ok': False, 'erro': 'NAO_AUTORIZADO'}), 401


@rastreio.route('/api/rastreio/frenet', methods=['POST'])
def rastreio_frenet():
    """Body: {"envios": [{"codigo": "<rastreio>", "servico": "<ShippingServiceCode>"}]}"""
    envios = (request.get_json(silent=True) or {}).get('envios') or []
    resultados = []
    for e in envios[:50]:
        try:
            resp = requests.post(
                FRENET_TRACKING_API,
                json={'ShippingServiceCode': e.get('servico', ''), 'TrackingNumber': e.get('codigo', '')},
                headers={'token': FRENET_TOKEN, 'Accept': 'application/json'},
                timeout=20,
            )
            resultados.append({'codigo': e.get('codigo'), 'http': resp.status_code, 'dados': resp.json()})
        except (requests.RequestException, ValueError) as exc:
            resultados.append({'codigo': e.get('codigo'), 'erro': str(exc)})
    return jsonify({'ok': True, 'resultados': resultados})


@rastreio.route('/api/rastreio/melhorenvio', methods=['GET'])
def rastreio_melhor_envio():
    """Envios em trânsito ou com problema (postados, não entregues, liberados)."""
    headers = {
        'Authorization': f'Bearer {ME_TOKEN}',
        'Accept': 'application/json',
        'User-Agent': 'CafeDaCasa-Rastreio/1.0',
    }
    envios = []
    try:
        for status in ME_STATUSES:
            resp = requests.get(ME_ORDERS_API, params={'status': status, 'per_page': 100},
                                headers=headers, timeout=25)
            resp.raise_for_status()
            for o in resp.json().get('data', []):
                destino = o.get('to') or {}
                envios.append({
                    'id': o.get('id'),
                    'status': o.get('status'),
                    'rastreio': o.get('tracking'),
                    'nf': o.get('reminder'),
                    'cliente': destino.get('name'),
                    'cidade': destino.get('city'),
                    'postado_em': o.get('posted_at'),
                    'prazo_max_dias': o.get('delivery_max'),
                    'chamados': len(o.get('tickets') or []),
                })
    except (requests.RequestException, ValueError) as exc:
        return jsonify({'ok': False, 'erro': 'ME_INDISPONIVEL', 'detalhe': str(exc)}), 502
    return jsonify({'ok': True, 'envios': envios})
