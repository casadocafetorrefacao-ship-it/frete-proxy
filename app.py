"""Aplicação Railway: preserva o proxy de frete e adiciona a ponte do sistema de conferência."""
from flask import request, jsonify, Response
import requests

# Importa o app e todas as rotas atuais de frete sem alterar server.py.
from server import app

CONFERENCIA_APPS_SCRIPT = (
    "https://script.google.com/macros/s/"
    "AKfycbyYE3vU6wwy30egzUfvEQRhjkfTxZ-3Xg0NJUCLkvAqh98pHgPbzu-45my5pFlOpS52xA/exec"
)


def _forward_response(resp):
    """Normaliza a resposta do Apps Script para o navegador."""
    content_type = resp.headers.get("Content-Type", "application/json")
    response = Response(resp.content, status=resp.status_code, content_type=content_type)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response


@app.route('/api/conferencia', methods=['GET', 'POST', 'OPTIONS'])
def conferencia_proxy():
    """Ponte servidor-servidor para o Apps Script, evitando conflito de contas Google no celular."""
    if request.method == 'OPTIONS':
        return ('', 204)

    try:
        if request.method == 'GET':
            params = request.args.to_dict(flat=True)
            # JSONP não é necessário aqui: o Railway devolve JSON normal com CORS.
            params.pop('callback', None)
            upstream = requests.get(
                CONFERENCIA_APPS_SCRIPT,
                params=params,
                timeout=35,
                allow_redirects=True,
                headers={'User-Agent': 'CafeDaCasa-Conferencia/1.0'}
            )
        else:
            payload = request.get_json(silent=True) or {}
            upstream = requests.post(
                CONFERENCIA_APPS_SCRIPT,
                json=payload,
                timeout=35,
                allow_redirects=True,
                headers={'User-Agent': 'CafeDaCasa-Conferencia/1.0'}
            )

        return _forward_response(upstream)
    except requests.RequestException as exc:
        return jsonify({
            'ok': False,
            'erro': 'PROXY_INDISPONIVEL',
            'detalhe': str(exc)
        }), 502


@app.route('/api/conferencia/health', methods=['GET'])
def conferencia_health():
    return jsonify({'ok': True, 'service': 'conferencia-proxy'})
