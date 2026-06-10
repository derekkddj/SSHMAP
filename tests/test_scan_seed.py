from modules.scan_seed import build_recursive_targets, get_previous_pivot_seed_plans


class TestScanSeed:
    def test_build_recursive_targets_filters_and_deduplicates(self):
        targets = build_recursive_targets(
            ["192.168.1.10/30", "192.168.1.11/30"],
            blacklist_ips=["192.168.1.2"],
            whitelist_ips=["192.168.1.1"],
        )

        assert targets == ["192.168.1.1"]

    def test_get_previous_pivot_seed_plans_uses_direct_graph_connections(self):
        class FakeGraph:
            def get_connections_from_host(self, hostname):
                assert hostname == "local-host"
                return [
                    {"to": "pivot-a"},
                    {"to": "pivot-a"},
                    {"to": "pivot-b"},
                    {"to": "pivot-missing"},
                ]

            def get_host(self, hostname):
                if hostname == "pivot-a":
                    return {"hostname": hostname, "interfaces": ["10.0.0.10/30"]}
                if hostname == "pivot-b":
                    return {"hostname": hostname, "interfaces": ["10.0.0.20/30"]}
                return None

        plans = get_previous_pivot_seed_plans(
            FakeGraph(),
            "local-host",
            3,
            blacklist_ips=["10.0.0.22"],
        )

        assert plans == [
            {"hostname": "pivot-a", "targets": ["10.0.0.9", "10.0.0.10"]},
            {"hostname": "pivot-b", "targets": ["10.0.0.21"]},
        ]

    def test_get_previous_pivot_seed_plans_disabled_for_depth_one(self):
        class FakeGraph:
            def get_connections_from_host(self, hostname):
                raise AssertionError("should not query graph when max depth is 1")

        assert get_previous_pivot_seed_plans(FakeGraph(), "local-host", 1) == []