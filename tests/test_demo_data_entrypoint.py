from scripts import demo_data


def test_demo_data_entrypoint_dispatches_without_importing_generators(monkeypatch):
    calls = []

    def fake_import(module_name):
        calls.append(module_name)

        class Module:
            @staticmethod
            def main():
                return f'ran:{module_name}'

        return Module

    monkeypatch.setattr(demo_data.importlib, 'import_module', fake_import)

    assert demo_data.run('sample-contracts') == 'ran:scripts.generate_sample_contracts'
    assert demo_data.run('demo-flow') == 'ran:demo_flow_data'
    assert calls == ['scripts.generate_sample_contracts', 'demo_flow_data']
