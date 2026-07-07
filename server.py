"""
Proxy de Cotação de Frete - Frenet + Melhor Envio (Loggi)
Deploy: Railway.app
"""
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import os

app = Flask(__name__)
CORS(app)

# ===== CONFIGURAÇÃO =====
FRENET_TOKEN = '7880AFB8R5BC1R489ERA8C2R79AE973FE2B5'
FRENET_API = 'https://api.frenet.com.br/shipping/quote'
SELLER_CEP = '37701746'

ME_TOKEN = 'eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9.eyJhdWQiOiIxIiwianRpIjoiNDVhOTY1NTk2OWFiZTcxZjQ4MmFlOGM3OWZmNzJmMjI2YWYxODc1NDM4YmZlZGNkNzc2ZDA5YjAzNzZiYTg1OGExYzllYTgwOGVmMjI0MDMiLCJpYXQiOjE3ODM0NTcwOTMuMjYwNzQyLCJuYmYiOjE3ODM0NTcwOTMuMjYwNzQ0LCJleHAiOjE4MTQ5OTMwOTMuMjM0OTU3LCJzdWIiOiI4NTAyYzEwMS1mZDA3LTQ1Y2QtODM2Mi0zYzU5Nzk3ZmVhY2QiLCJzY29wZXMiOlsiY2FydC1yZWFkIiwiY2FydC13cml0ZSIsImNvbXBhbmllcy1yZWFkIiwiY29tcGFuaWVzLXdyaXRlIiwiY291cG9ucy1yZWFkIiwiY291cG9ucy13cml0ZSIsIm5vdGlmaWNhdGlvbnMtcmVhZCIsIm9yZGVycy1yZWFkIiwicHJvZHVjdHMtcmVhZCIsInByb2R1Y3RzLWRlc3Ryb3kiLCJwcm9kdWN0cy13cml0ZSIsInB1cmNoYXNlcy1yZWFkIiwic2hpcHBpbmctY2FsY3VsYXRlIiwic2hpcHBpbmctY2FuY2VsIiwic2hpcHBpbmctY2hlY2tvdXQiLCJzaGlwcGluZy1jb21wYW5pZXMiLCJzaGlwcGluZy1nZW5lcmF0ZSIsInNoaXBwaW5nLXByZXZpZXciLCJzaGlwcGluZy1wcmludCIsInNoaXBwaW5nLXNoYXJlIiwic2hpcHBpbmctdHJhY2tpbmciLCJlY29tbWVyY2Utc2hpcHBpbmciLCJ0cmFuc2FjdGlvbnMtcmVhZCIsInVzZXJzLXJlYWQiLCJ1c2Vycy13cml0ZSIsIndlYmhvb2tzLXJlYWQiLCJ3ZWJob29rcy13cml0ZSIsIndlYmhvb2tzLWRlbGV0ZSIsInRkZWFsZXItd2ViaG9vayJdfQ.vOPo5lpXOHNaWus4-EmelWxeiBtg4yicOeqV15pvwUk9wCBQefLOaIp9hIlXtzSPW5qIHVdZ7KuSBM16LzdibVXUp97nM8omTqUni0faAXGruXXBquYOGF4GWvkw5EgvjxVIv_1VIImCLRJGbRa5XZsDq10KzwkdYhjNG59K8D3H8-GjIcbTU4dAP_O8dySCV5tsEMwOQYs0otnrwbwvgJkDxBrIvpMCxQE1AhxxULZrvMMaF6FPIbaYXuVLFOz0S4NFLFWLnYx5wFhfeE2QOx2zuTHBKZM6bCr-J5Evcg2aR7s7dtJpn2KEvLqmw8CsxJ0WiJIJhujVkF6mR9Fw43qCfpwLC1wQHO1QjJUXbko4XxDm08in9JJJTA8On5ZIR02szzSw0Mk5jtBLnVTHtt5_cgYLmaPr3CMl-qO4tBDnuQBexIx7KULPwVig-Emp7AnnqB9hG3r6ZdzZzVBslMsiVDEKo5vVdjRmByCIjQNfzl17WCixvktGT5HHrxU2mS5kpGBT9VoTeOlQQkGESDApOII9Nnr3R6WubYtPoS1Gj_EEq9WtfQa73e3TqdokqJjVoB-Hxq5W_FnDd5MzgPtIhxJghbHLPmJgi3SliR2lI8XCL2KWwqBKYco73qATpMqs3UvplXiaZyFzcAZO9tnAmjFrzFjdEtCTsh3T7zI'
ME_API = 'https://melhorenvio.com.br/api/v2/me/shipment/calculate'


def fetch_frenet(cep, weight, invoice_value):
    """Consulta a API da Frenet"""
    try:
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'token': FRENET_TOKEN
        }
        payload = {
            'SellerCEP': SELLER_CEP,
            'RecipientCEP': cep,
            'ShipmentInvoiceValue': invoice_value,
            'ShippingServiceCode': None,
            'ShippingItemArray': [{
                'Height': 10,
                'Length': 20,
                'Quantity': 1,
                'Weight': weight if weight > 0 else 0.5,
                'Width': 15
            }],
            'RecipientCountry': 'BR'
        }
        resp = requests.post(FRENET_API, json=payload, headers=headers, timeout=15)
        if resp.status_code != 200:
            return []
        data = resp.json()
        services = data.get('ShippingSevicesArray', [])
        results = []
        for s in services:
            if s.get('Error'):
                continue
            results.append({
                'name': s.get('ServiceDescription', ''),
                'carrier': (s.get('Carrier', '')).upper(),
                'price': float(s.get('ShippingPrice', 0)),
                'days': int(s.get('DeliveryTime', 0)),
                'source': 'frenet'
            })
        return results
    except Exception as e:
        print(f'Frenet error: {e}')
        return []


def fetch_melhor_envio(cep, weight, invoice_value):
    """Consulta a API da Melhor Envio (apenas Loggi)"""
    try:
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Authorization': f'Bearer {ME_TOKEN}',
            'User-Agent': 'CasaDoCafe (casadocafetorrefacao@gmail.com)'
        }
        payload = {
            'from': {'postal_code': SELLER_CEP},
            'to': {'postal_code': cep},
            'products': [{
                'id': '1',
                'width': 15,
                'height': 10,
                'length': 20,
                'weight': weight if weight > 0 else 0.5,
                'insurance_value': invoice_value,
                'quantity': 1
            }]
        }
        resp = requests.post(ME_API, json=payload, headers=headers, timeout=15)
        if resp.status_code != 200:
            return []
        data = resp.json()
        if not isinstance(data, list):
            return []
        results = []
        for s in data:
            if s.get('company', {}).get('name') == 'Loggi' and not s.get('error') and s.get('price'):
                results.append({
                    'name': s.get('name', 'Loggi'),
                    'carrier': 'LOGGI',
                    'price': float(s.get('custom_price') or s.get('price', 0)),
                    'days': int(s.get('custom_delivery_time') or s.get('delivery_time', 0)),
                    'source': 'melhorenvio'
                })
        return results
    except Exception as e:
        print(f'Melhor Envio error: {e}')
        return []


@app.route('/api/shipping/quote', methods=['POST'])
def shipping_quote():
    """Endpoint principal de cotação de frete"""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Dados inválidos'}), 400

    cep = data.get('recipientCEP', '').replace('-', '').strip()
    if len(cep) != 8:
        return jsonify({'error': 'CEP inválido'}), 400

    weight = float(data.get('weight', 0.5))
    invoice_value = float(data.get('shipmentInvoiceValue', 100.0))

    frenet_services = fetch_frenet(cep, weight, invoice_value)
    me_services = fetch_melhor_envio(cep, weight, invoice_value)

    all_services = frenet_services + me_services

    if not all_services:
        return jsonify({'error': 'Nenhuma opção de frete encontrada para este CEP.'}), 200

    return jsonify({
        'success': True,
        'services': all_services
    })


@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
