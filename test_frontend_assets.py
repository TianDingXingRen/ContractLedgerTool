import os
import unittest

import app
import build_installer


class FrontendAssetTests(unittest.TestCase):
    def test_base_template_uses_local_vendor_assets(self):
        base_path = os.path.join(app.RESOURCE_DIR, 'templates', 'base.html')
        with open(base_path, 'r', encoding='utf-8') as f:
            html = f.read()

        external_refs = (
            'cdn.jsdelivr.net',
            'cdn.tailwindcss.com',
            'tailwindcss.com',
            'unpkg.com',
        )
        for ref in external_refs:
            self.assertNotIn(ref, html)

        local_assets = (
            'vendor/daisyui-full.min.css',
            'vendor/tailwindcss.js',
            'js/base.js',
            'vendor/alpine.min.js',
            'js/icons.js',
        )
        for asset in local_assets:
            self.assertIn(asset, html)

    def test_base_template_moves_shared_script_to_static_asset(self):
        base_path = os.path.join(app.RESOURCE_DIR, 'templates', 'base.html')
        script_path = os.path.join(app.RESOURCE_DIR, 'static', 'js', 'base.js')
        with open(base_path, 'r', encoding='utf-8') as f:
            html = f.read()
        with open(script_path, 'r', encoding='utf-8') as f:
            script = f.read()

        self.assertIn('js/base.js', html)
        self.assertNotIn('function toastCenter()', html)
        self.assertNotIn('tailwind.config =', html)
        self.assertIn('function toastCenter()', script)
        self.assertIn('window.showToast', script)
        self.assertIn('tailwind.config =', script)

    def test_local_vendor_assets_are_served(self):
        expected_min_sizes = {
            '/static/vendor/daisyui-full.min.css': 100_000,
            '/static/vendor/tailwindcss.js': 100_000,
            '/static/vendor/alpine.min.js': 10_000,
            '/static/vendor/lucide.min.js': 10_000,
        }

        with app.app.test_client() as client:
            for path, min_size in expected_min_sizes.items():
                response = client.get(path)
                try:
                    self.assertEqual(response.status_code, 200, path)
                    self.assertGreater(len(response.get_data()), min_size, path)
                finally:
                    response.close()

    def test_contract_detail_exposes_resizable_payment_columns(self):
        detail_path = os.path.join(app.RESOURCE_DIR, 'templates', 'contract_detail.html')
        style_path = os.path.join(app.RESOURCE_DIR, 'static', 'style.css')
        with open(detail_path, 'r', encoding='utf-8') as f:
            html = f.read()
        with open(style_path, 'r', encoding='utf-8') as f:
            css = f.read()

        self.assertIn('data-testid="payment-plan-table"', html)
        self.assertIn('<colgroup>', html)
        self.assertEqual(html.count('class="col-resize-handle"'), 13)
        self.assertIn("localStorage.setItem(storageKey", html)
        self.assertIn("handle.addEventListener('mousedown'", html)
        self.assertIn('.col-resize-handle', css)
        self.assertIn('cursor: col-resize', css)

    def test_windows_launcher_uses_fast_new_ui_probe(self):
        launcher_path = os.path.join(app.RESOURCE_DIR, 'installer_assets', 'start.ps1')
        with open(launcher_path, 'rb') as f:
            script = f.read().decode('ascii')

        self.assertIn('/static/style.css', script)
        self.assertIn('Apple-style GUI Theme', script)

    def test_offline_build_includes_nested_procurement_templates(self):
        manifest = build_installer.prepare_app_resources()
        nested_template = os.path.join(
            build_installer.APP_RES_DIR,
            'templates',
            'procurement',
            'history_prices.html',
        )

        self.assertTrue(os.path.isfile(nested_template))
        self.assertIn(
            os.path.join('procurement', 'history_prices.html'),
            manifest['html_templates'],
        )

    def test_offline_installer_enables_autostart_and_cleans_previous_versions(self):
        installer_path = os.path.join(app.RESOURCE_DIR, 'installer_assets', 'install.ps1')
        with open(installer_path, 'r', encoding='utf-8-sig') as f:
            script = f.read()

        self.assertIn('[switch]$NoAutostart', script)
        self.assertIn('if (-not $NoAutostart)', script)
        self.assertIn('setup_autostart.ps1', script)
        self.assertIn('-Port $Port', script)
        self.assertIn('Stop-PreviousVersions', script)
        self.assertIn('Get-NetTCPConnection -LocalPort $Port', script)
        self.assertIn('python.exe', script)
        self.assertIn('ContractLedgerTool.exe', script)

    def test_offline_installer_build_outputs_desktop_exe_only(self):
        build_script_path = os.path.join(app.RESOURCE_DIR, 'build_installer.py')
        with open(build_script_path, 'r', encoding='utf-8') as f:
            script = f.read()

        self.assertIn('desktop_exe', script)
        self.assertIn('DESKTOP / f', script)
        self.assertNotIn('zip_dir(stage', script)
        self.assertNotIn("'zip': str", script)


if __name__ == '__main__':
    unittest.main()
