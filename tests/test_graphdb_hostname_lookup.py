from unittest.mock import MagicMock

from modules.graphdb import GraphDB


def test_get_hostname_by_ip_matches_stored_cidr_interface():
    db = GraphDB.__new__(GraphDB)
    session = MagicMock()
    result = MagicMock()
    record = {"hostname": "machine2_useasjumphost"}
    result.single.return_value = record
    session.run.return_value = result
    db.driver = MagicMock()
    db.driver.session.return_value.__enter__.return_value = session

    assert db.get_hostname_by_ip("172.19.0.2") == "machine2_useasjumphost"

    query, params = session.run.call_args[0][0], session.run.call_args.kwargs
    assert "split(interface, '/')" in query
    assert params == {"ip": "172.19.0.2"}
