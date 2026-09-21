"""
Basic tests for the SSHMAP Web Interface.

These tests verify that the Flask app initializes correctly and that
the API endpoints are properly configured.
"""

import pytest
import sys
import os
import json
from io import BytesIO

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_web_app_imports():
    """Test that the web app can be imported without errors."""
    try:
        import web_app
        assert web_app.app is not None
    except ImportError as e:
        pytest.fail(f"Failed to import web_app: {e}")


def test_flask_app_exists():
    """Test that Flask app instance is created."""
    from web_app import app
    assert app is not None
    assert app.name == 'web_app'


def test_routes_registered():
    """Test that all expected routes are registered."""
    from web_app import app

    # Get all registered routes
    routes = [str(rule) for rule in app.url_map.iter_rules()]

    # Check for expected endpoints
    expected_routes = [
        '/',
        '/api/graph',
        '/api/export',
        '/api/import',
        '/api/search',
        '/api/path',
        '/api/node/<int:node_id>',
        '/api/edge/<int:edge_id>',
        '/api/edge/<int:edge_id>/disabled',
        '/api/hosts'
    ]

    for route in expected_routes:
        # Note: Flask adds some variations, so we check if the base path exists
        assert any(route.replace('<int:node_id>', '<node_id>') in r or
                   route.replace('<int:edge_id>', '<edge_id>') in r or
                   route in r for r in routes), f"Route {route} not found in {routes}"


class _FakeResult:
    def __init__(self, record=None, records=None):
        self._record = record
        self._records = records or []

    def single(self):
        return self._record

    def __iter__(self):
        return iter(self._records)


class _FakeSession:
    def __init__(self, results=None):
        self.calls = []
        self.results = list(results or [])

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def run(self, query, **params):
        self.calls.append((query, params))
        if self.results:
            return self.results.pop(0)
        return _FakeResult()


class _FakeDriver:
    def __init__(self, session):
        self._session = session

    def session(self):
        return self._session


class _FakeDB:
    def __init__(self, session, hosts=None):
        self.driver = _FakeDriver(session)
        self.hosts = hosts or []

    def get_all_hosts_detailed(self):
        return self.hosts


def test_import_endpoint_accepts_export_json(monkeypatch):
    import web_app

    fake_session = _FakeSession()
    monkeypatch.setattr(web_app, 'db', _FakeDB(fake_session))

    client = web_app.app.test_client()
    payload = {
        'nodes': [
            {'hostname': 'jumpbox', 'interfaces': ['10.0.0.10/24']},
            {'hostname': 'target', 'interfaces': ['10.0.0.20/24']},
        ],
        'edges': [
            {
                'from_hostname': 'jumpbox',
                'to_hostname': 'target',
                'user': 'root',
                'method': 'password',
                'creds': 'hunter2',
                'ip': '10.0.0.20',
                'port': 22,
                'time': 1710000000000,
            }
        ],
    }

    response = client.post(
        '/api/import',
        data={
            'file': (BytesIO(json.dumps(payload).encode('utf-8')), 'project.json'),
            'replace_existing': 'true',
        },
        content_type='multipart/form-data',
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body['success'] is True
    assert body['replace_existing'] is True
    assert body['nodes_imported'] == 2
    assert body['relationships_imported'] == 1
    assert len(fake_session.calls) == 3
    assert 'DETACH DELETE n' in fake_session.calls[0][0]
    assert fake_session.calls[1][1]['nodes'][0]['hostname'] == 'jumpbox'
    assert fake_session.calls[2][1]['edges'][0]['from_hostname'] == 'jumpbox'


def test_import_endpoint_rejects_invalid_payload():
    import web_app

    client = web_app.app.test_client()
    response = client.post('/api/import', json={'nodes': []})

    assert response.status_code == 400
    body = response.get_json()
    assert body['success'] is False
    assert 'nodes and edges arrays' in body['error']


def test_graph_endpoint_does_not_load_edges_without_filters(monkeypatch):
    import web_app

    metadata = {
        'node_count': 161,
        'edge_count': 400000,
        'users': ['root', 'admin'],
        'methods': ['password', 'keyfile'],
    }
    fake_session = _FakeSession([_FakeResult(record=metadata)])
    fake_db = _FakeDB(fake_session, hosts=[{
        'id': 1,
        'hostname': 'jumpbox',
        'interfaces': ['10.0.0.10/24'],
    }])
    monkeypatch.setattr(web_app, 'db', fake_db)

    response = web_app.app.test_client().get('/api/graph?include_edges=false')

    assert response.status_code == 200
    body = response.get_json()
    assert len(body['nodes']) == 1
    assert body['edges'] == []
    assert body['total_node_count'] == 161
    assert body['total_edge_count'] == 400000
    assert body['matched_node_count'] == 161
    assert body['matched_edge_count'] == 0
    assert len(fake_session.calls) == 1


def test_graph_endpoint_filters_and_caps_edges(monkeypatch):
    import web_app

    records = [
        {
            'from_id': 1,
            'to_id': index + 2,
            'edge_id': index + 10,
            'from_hostname': 'jumpbox',
            'to_hostname': f'target-{index}',
            'user': 'root',
            'method': 'password',
            'creds': 'secret',
            'ip': f'10.0.0.{index + 2}',
            'port': 22,
            'time': 1710000000000 + index,
            'disabled': False,
        }
        for index in range(3)
    ]
    count_records = [
        {'node_id': 2, 'edge_count': 2},
        {'node_id': 3, 'edge_count': 1},
    ]
    fake_session = _FakeSession([
        _FakeResult(records=count_records),
        _FakeResult(records=records),
    ])
    monkeypatch.setattr(web_app, 'db', _FakeDB(fake_session))

    response = web_app.app.test_client().get(
        '/api/graph?include_nodes=false&include_metadata=false&user=root&method=password'
        '&source_node_id=1&max_hops=1&edge_mode=tree&node_limit=3&limit=2'
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body['nodes'] == []
    assert len(body['edges']) == 2
    assert body['node_limit'] == 3
    assert body['matched_node_count'] == 3
    assert body['matched_edge_count'] == 2
    assert body['truncated'] is True
    assert fake_session.calls[1][1]['users'] == ['root']
    assert fake_session.calls[1][1]['methods'] == ['password']
    assert fake_session.calls[1][1]['query_limit'] == 3
    assert fake_session.calls[1][1]['visited_node_ids'] == [1]
    assert 'head(collect' in fake_session.calls[1][0]


def test_path_endpoint_includes_edge_id(monkeypatch):
    import web_app

    class _FakePathDB:
        def find_path(self, start, end):
            assert start == 'jumpbox'
            assert end == 'target'
            return [(
                'jumpbox',
                {
                    'id': 42,
                    'user': 'root',
                    'method': 'password',
                    'creds': 'secret',
                    'ip': '10.0.0.20',
                    'port': 22,
                    'time': 1710000000000,
                    'disabled': False,
                },
                'target',
            )]

    monkeypatch.setattr(web_app, 'db', _FakePathDB())

    response = web_app.app.test_client().post(
        '/api/path',
        json={'start': 'jumpbox', 'end': 'target'},
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body['paths'][0][0]['id'] == 42


def test_templates_directory_exists():
    """Test that templates directory exists."""
    templates_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'templates')
    assert os.path.exists(templates_dir), "templates directory does not exist"
    assert os.path.isdir(templates_dir), "templates is not a directory"


def test_static_directory_exists():
    """Test that static directory exists with required subdirectories."""
    static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static')
    assert os.path.exists(static_dir), "static directory does not exist"
    assert os.path.isdir(static_dir), "static is not a directory"

    # Check for subdirectories
    css_dir = os.path.join(static_dir, 'css')
    js_dir = os.path.join(static_dir, 'js')

    assert os.path.exists(css_dir), "css directory does not exist"
    assert os.path.exists(js_dir), "js directory does not exist"


def test_index_template_exists():
    """Test that index.html template exists."""
    template_file = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        'templates',
        'index.html'
    )
    assert os.path.exists(template_file), "index.html template does not exist"


def test_javascript_file_exists():
    """Test that app.js JavaScript file exists."""
    js_file = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        'static',
        'js',
        'app.js'
    )
    assert os.path.exists(js_file), "app.js file does not exist"


def test_css_file_exists():
    """Test that style.css file exists."""
    css_file = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        'static',
        'css',
        'style.css'
    )
    assert os.path.exists(css_file), "style.css file does not exist"


def test_launcher_script_exists():
    """Test that the launcher script exists and is executable."""
    launcher = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        'sshmap_web.py'
    )
    assert os.path.exists(launcher), "sshmap_web.py launcher does not exist"
    # Check if file is executable (on Unix-like systems)
    if os.name != 'nt':  # Not Windows
        assert os.access(launcher, os.X_OK), "sshmap_web.py is not executable"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
