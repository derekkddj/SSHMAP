"""Node sidebar API credentials and peer-IP regression coverage."""

import pytest

import web_app
from test_web_interface import _FakeDB, _FakeResult, _FakeSession


@pytest.mark.parametrize('creds,method', [('p\"<&\'ass', 'password'), ('/home/user/.ssh/id_ed25519', 'key'), (None, None)])
def test_node_connections_include_credentials_and_peer_interfaces(monkeypatch, creds, method):
    node = {'id': 0, 'hostname': 'selected', 'interfaces': ['10.0.0.1']}
    connection = {
        'edge_id': 2, 'user': 'root', 'method': method, 'creds': creds,
        'ip': '10.0.0.2', 'port': 22, 'disabled': True,
    }
    outgoing = {**connection, 'target': 'target', 'peer_interfaces': ['10.0.0.2', 'fe80::1']}
    incoming = {**connection, 'source': 'source', 'peer_interfaces': None}
    session = _FakeSession([
        _FakeResult(record=node), _FakeResult(records=[outgoing]),
        _FakeResult(records=[incoming]),
    ])
    monkeypatch.setattr(web_app, 'db', _FakeDB(session))
    response = web_app.app.test_client().get('/api/node/0')
    assert response.status_code == 200
    assert response.get_json() == {
        **node, 'outgoing_connections': [outgoing], 'incoming_connections': [incoming],
    }
    assert len(session.calls) == 3
    for (query, params), peer in zip(session.calls[1:], ['target', 'source']):
        assert 'r.creds AS creds' in query
        assert f'{peer}.interfaces AS peer_interfaces' in query
        assert 'coalesce(r.disabled, false) AS disabled' in query
        assert 'LIMIT 200' in query
        assert params == {'node_id': 0}


def test_missing_node_still_returns_404(monkeypatch):
    session = _FakeSession()
    monkeypatch.setattr(web_app, 'db', _FakeDB(session))
    response = web_app.app.test_client().get('/api/node/404')
    assert response.status_code == 404
    assert response.get_json() == {'error': 'Node not found'}
    assert len(session.calls) == 1
