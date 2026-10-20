"""Regression tests for global directed tree mode and selected-hop traversal."""

import pytest

import web_app
from test_web_interface import _FakeDB, _FakeResult, _FakeSession


def _edge(source, target, edge_id, time=1, disabled=False):
    return {
        'from_id': source, 'to_id': target, 'edge_id': edge_id,
        'from_hostname': 'pop-os' if source == 0 else f'host-{source}',
        'to_hostname': f'host-{target}', 'user': 'root', 'method': 'password',
        'creds': 'secret', 'ip': '10.0.0.1', 'port': 22,
        'time': time, 'disabled': disabled,
    }


class _TopologySession(_FakeSession):
    """Model the two global queries without requiring a live Neo4j instance."""

    def __init__(self, edges):
        super().__init__()
        self.edges = edges

    def run(self, query, **params):
        self.calls.append((query, params))
        if 'RETURN DISTINCT id(a)' in query:
            assert ('r.user IN $users' in query) == bool(params['users'])
            assert ('r.method IN $methods' in query) == bool(params['methods'])
            pairs = sorted({(e['from_id'], e['to_id']) for e in self.edges
                            if e['from_id'] != e['to_id']})
            return _FakeResult(records=[{'from_id': a, 'to_id': b}
                                        for a, b in pairs[:params['topology_limit']]])
        assert 'UNWIND $pairs' in query
        assert 'coalesce(r.disabled, false) ASC' in query
        assert 'LIMIT 1' in query
        records = []
        for pair in params['pairs']:
            candidates = [e for e in self.edges
                          if e['from_id'] == pair['from_id'] and
                          e['to_id'] == pair['to_id']]
            records.append(min(candidates, key=lambda e: (
                e['disabled'], -e['time'], e['edge_id'])))
        return _FakeResult(records=records)


def _forest_fixture():
    return [
        # Sink has a lower ID than its root; direction must not be reversed.
        _edge(10, 1, 1),
        _edge(0, 2, 2), _edge(0, 2, 3, time=9),
        _edge(0, 2, 4, time=20, disabled=True),
        _edge(0, 3, 5), _edge(2, 3, 6), _edge(3, 2, 7),
        # Disconnected cycle, plus a self-loop that must not become a parent.
        _edge(20, 21, 8), _edge(21, 20, 9), _edge(30, 30, 10),
    ]


def test_global_tree_api_without_selection(monkeypatch):
    session = _TopologySession(_forest_fixture())
    monkeypatch.setattr(web_app, 'db', _FakeDB(session))
    # Match counts retain their existing raw-relationship meaning globally.
    monkeypatch.setattr(web_app, '_get_graph_match_counts', lambda *args: (8, 10))
    response = web_app.app.test_client().get(
        '/api/graph?include_nodes=false&include_metadata=false'
        '&user=root&method=password&edge_mode=tree')
    assert response.status_code == 200
    body = response.get_json()
    assert {(e['from'], e['to']) for e in body['edges']} == {
        (0, 2), (0, 3), (10, 1), (20, 21),
    }
    assert len({e['to'] for e in body['edges']}) == len(body['edges'])
    assert next(e for e in body['edges'] if e['to'] == 2)['id'] == 3
    assert body['truncated'] is False
    assert len(session.calls) == 2
    assert session.calls[0][1]['topology_limit'] == web_app.MAX_GRAPH_EDGE_LIMIT + 1


@pytest.mark.parametrize('edge_limit,node_limit,expected', [(2, 20, 2), (20, 3, 2)])
def test_global_tree_collapses_before_display_limits(edge_limit, node_limit, expected):
    # Many recent parallel credentials must not crowd out the next destination.
    edges = [_edge(0, 2, i, time=i) for i in range(100)]
    edges += [_edge(0, 3, 100), _edge(10, 1, 101)]
    session = _TopologySession(edges)
    records, truncated = web_app._get_graph_edges(
        session, ['root'], ['password'], edge_limit, node_limit)
    assert len(records) == expected
    assert {(e['from_id'], e['to_id']) for e in records} == {(0, 2), (0, 3)}
    assert truncated is True


def test_global_tree_topology_budget_reports_truncation(monkeypatch):
    monkeypatch.setattr(web_app, 'MAX_GRAPH_EDGE_LIMIT', 3)
    session = _TopologySession([_edge(0, i, i) for i in range(1, 6)])
    records, truncated = web_app._get_graph_edges(
        session, ['root'], ['password'], 20, 20)
    assert len(records) == 3
    assert truncated is True
    assert session.calls[0][1]['topology_limit'] == 4


def test_global_tree_empty_topology():
    session = _TopologySession([_edge(0, 0, 1)])
    assert web_app._get_graph_edges(session, [], [], 20, 20) == ([], False)
    assert len(session.calls) == 1


@pytest.mark.parametrize('mode', ['tree', 'all'])
def test_selected_zero_root_preserves_outgoing_hop_layers(mode):
    # Results model outgoing Cypher queries for two BFS layers.
    first_layer = [_edge(0, 2, 1)]
    if mode == 'all':
        first_layer.append(_edge(0, 2, 2))
    session = _FakeSession([
        _FakeResult(records=first_layer),
        _FakeResult(records=[_edge(2, 3, 3)]),
    ])
    records, truncated = web_app._get_graph_edges(
        session, ['root'], ['password'], 20, 20,
        source_node_id=0, max_hops=2, edge_mode=mode)
    assert len(records) == (2 if mode == 'tree' else 3)
    assert truncated is False
    assert len(session.calls) == 2
    assert session.calls[0][1]['source_ids'] == [0]
    assert session.calls[1][1]['source_ids'] == [2]
    assert set(session.calls[1][1]['visited_node_ids']) == {0, 2}
    for query, _ in session.calls:
        assert 'id(a) IN $source_ids' in query
        assert ('head(collect' in query) == (mode == 'tree')
        assert ('NOT id(b) IN $visited_node_ids' in query) == (mode == 'tree')


def test_global_all_mode_still_returns_parallel_edges():
    edges = [_edge(0, 2, 1), _edge(0, 2, 2)]
    session = _FakeSession([_FakeResult(records=edges)])
    records, truncated = web_app._get_graph_edges(
        session, ['root'], ['password'], 20, 20, edge_mode='all')
    assert records == edges
    assert truncated is False
    assert len(session.calls) == 1
