import os
import re
import unittest

import app
import build_installer


class FrontendAssetTests(unittest.TestCase):
    def test_templates_have_no_executable_inline_scripts_or_dom_event_attributes(self):
        templates_dir = os.path.join(app.RESOURCE_DIR, 'templates')
        event_attribute = re.compile(r'\son(?:click|change|input|submit|focus|blur)\s*=', re.I)
        inline_script = re.compile(r'<script(?![^>]*\bsrc=)(?![^>]*type="application/json")[^>]*>', re.I)
        for root, _dirs, files in os.walk(templates_dir):
            for filename in files:
                if not filename.endswith('.html'):
                    continue
                path = os.path.join(root, filename)
                with open(path, encoding='utf-8') as handle:
                    source = handle.read()
                self.assertIsNone(event_attribute.search(source), path)
                self.assertIsNone(inline_script.search(source), path)

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
            'css/app.min.css',
            'brand/procurement-platform-icon.png',
            'js/app-shell.js',
            'vendor/alpine.min.js',
            'js/icons.js',
        )
        for asset in local_assets:
            self.assertIn(asset, html)
        self.assertNotIn('vendor/daisyui-full.min.css', html)
        self.assertNotIn('vendor/tailwindcss.js', html)
        self.assertIn('采购业务平台', html)
        self.assertNotIn('<div class="sli">CT</div>', html)

    def test_base_template_moves_shared_script_to_static_asset(self):
        base_path = os.path.join(app.RESOURCE_DIR, 'templates', 'base.html')
        script_path = os.path.join(app.RESOURCE_DIR, 'static', 'js', 'app-shell.js')
        with open(base_path, 'r', encoding='utf-8') as f:
            html = f.read()
        with open(script_path, 'r', encoding='utf-8') as f:
            script = f.read()

        self.assertIn('js/app-shell.js', html)
        self.assertNotIn('function toastCenter()', html)
        self.assertNotIn('tailwind.config =', html)
        self.assertIn('function toastCenter()', script)
        self.assertIn('window.showToast', script)
        self.assertIn('window.confirmAction', script)
        self.assertIn('window.showNotice', script)
        self.assertIn("dataset.appShell = 'ready'", script)
        self.assertNotIn('tailwind.config =', script)

    def test_shared_feedback_replaces_browser_native_prompts(self):
        roots = (
            os.path.join(app.RESOURCE_DIR, 'templates'),
            os.path.join(app.RESOURCE_DIR, 'static'),
        )
        offenders = []
        for root in roots:
            for dirpath, dirnames, filenames in os.walk(root):
                if os.path.normpath('static/vendor') in os.path.normpath(dirpath):
                    continue
                for filename in filenames:
                    if not filename.endswith(('.html', '.js')):
                        continue
                    path = os.path.join(dirpath, filename)
                    with open(path, 'r', encoding='utf-8') as f:
                        text = f.read()
                    if 'alert(' in text or 'confirm(' in text:
                        offenders.append(os.path.relpath(path, app.RESOURCE_DIR))

        self.assertEqual([], offenders)

        base_path = os.path.join(app.RESOURCE_DIR, 'static', 'js', 'app-shell.js')
        style_path = os.path.join(app.RESOURCE_DIR, 'static', 'style.css')
        with open(base_path, 'r', encoding='utf-8') as f:
            script = f.read()
        with open(style_path, 'r', encoding='utf-8') as f:
            css = f.read()

        self.assertIn('form[data-confirm]', script)
        self.assertIn('feedbackToastStack', script)
        self.assertIn('.feedback-dialog', css)
        self.assertIn('.feedback-toast', css)

    def test_local_vendor_assets_are_served(self):
        expected_min_sizes = {
            '/static/css/app.min.css': 50_000,
            '/static/brand/procurement-platform-icon.png': 20_000,
            '/static/vendor/alpine.min.js': 10_000,
            '/static/js/icons.js': 5_000,
        }

        with app.app.test_client() as client:
            for path, min_size in expected_min_sizes.items():
                response = client.get(path)
                try:
                    self.assertEqual(response.status_code, 200, path)
                    self.assertGreater(len(response.get_data()), min_size, path)
                finally:
                    response.close()

        css_path = os.path.join(app.RESOURCE_DIR, 'static', 'css', 'app.min.css')
        self.assertLess(os.path.getsize(css_path), 250_000)

    def test_static_assets_are_versioned_and_cacheable(self):
        with app.app.test_client() as client:
            page = client.get('/')
            html = page.get_data(as_text=True)
            page_cache_control = page.headers.get('Cache-Control')
            page.close()

            self.assertIn('/static/css/app.min.css?v=', html)
            self.assertEqual('no-store, max-age=0', page_cache_control)

            versioned = client.get('/static/css/app.min.css?v=test')
            direct = client.get('/static/css/app.min.css')
            try:
                self.assertEqual(
                    'public, max-age=31536000, immutable',
                    versioned.headers.get('Cache-Control'),
                )
                self.assertEqual(
                    'public, max-age=3600',
                    direct.headers.get('Cache-Control'),
                )
            finally:
                versioned.close()
                direct.close()

    def test_csp_matches_current_alpine_runtime(self):
        with app.app.test_client() as client:
            response = client.get('/')
            try:
                csp = response.headers.get('Content-Security-Policy', '')
            finally:
                response.close()

        self.assertIn("script-src 'self' 'unsafe-eval'", csp)
        self.assertNotIn("script-src 'self' 'unsafe-inline'", csp)
        self.assertIn("style-src 'self' 'unsafe-inline'", csp)

    def test_contract_detail_exposes_resizable_payment_columns(self):
        detail_path = os.path.join(app.RESOURCE_DIR, 'templates', 'contract_detail.html')
        style_path = os.path.join(app.RESOURCE_DIR, 'static', 'style.css')
        with open(detail_path, 'r', encoding='utf-8') as f:
            html = f.read()
        with open(style_path, 'r', encoding='utf-8') as f:
            css = f.read()
        behavior_path = os.path.join(app.RESOURCE_DIR, 'static', 'js', 'contract-detail.js')
        with open(behavior_path, 'r', encoding='utf-8') as f:
            behavior = f.read()

        self.assertIn('data-testid="payment-plan-table"', html)
        self.assertIn('<colgroup>', html)
        self.assertEqual(html.count('class="col-resize-handle"'), 13)
        self.assertIn("localStorage.setItem(storageKey", behavior)
        self.assertIn("handle.addEventListener('mousedown'", behavior)
        self.assertIn('.col-resize-handle', css)
        self.assertIn('cursor: col-resize', css)

    def test_windows_launcher_uses_fast_new_ui_probe(self):
        launcher_path = os.path.join(app.RESOURCE_DIR, 'installer_assets', 'start.ps1')
        with open(launcher_path, 'rb') as f:
            script = f.read().decode('ascii')

        self.assertIn('/static/style.css', script)
        self.assertIn('Apple-style GUI Theme', script)
        self.assertIn('[switch]$NoPrompt', script)
        self.assertIn('$StartupTimeoutSeconds = 120', script)
        self.assertIn('Stop-ConflictingToolListener', script)
        self.assertIn('Get-NetTCPConnection -LocalPort $ProbePort', script)
        self.assertIn('ContractLedgerTool.exe', script)
        self.assertIn('Resolve-LaunchPort', script)
        self.assertIn('Port $Port is busy; using port $LaunchPort instead.', script)
        self.assertIn('-PassThru', script)
        self.assertIn('Still waiting for the local service', script)

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
        self.assertIn('version', manifest)
        self.assertIn('source_commit', manifest)
        self.assertIn('source_dirty', manifest)
        version_path = os.path.join(build_installer.APP_RES_DIR, 'version.txt')
        self.assertTrue(os.path.isfile(version_path))
        self.assertTrue(os.path.isfile(os.path.join(
            build_installer.APP_RES_DIR, 'build-info.json',
        )))

    def test_offline_installer_uses_opt_in_autostart_and_cleans_previous_versions(self):
        installer_path = os.path.join(app.RESOURCE_DIR, 'installer_assets', 'install.ps1')
        with open(installer_path, 'r', encoding='utf-8-sig') as f:
            script = f.read()

        self.assertIn('[switch]$NoAutostart', script)
        self.assertIn('[switch]$EnableAutostart', script)
        self.assertIn('if ($EnableAutostart -and -not $NoAutostart)', script)
        self.assertIn('setup_autostart.ps1', script)
        self.assertIn('-Port $Port', script)
        self.assertIn('Stop-PreviousVersions', script)
        self.assertIn('Get-NetTCPConnection -LocalPort $Port', script)
        self.assertIn('Resolve-InstallPort', script)
        self.assertIn('Port $Port is busy; using port $ResolvedPort instead.', script)
        self.assertIn('python.exe', script)
        self.assertIn('ContractLedgerTool.exe', script)
        self.assertNotIn('$isToolExe = $name -eq "ContractLedgerTool.exe"', script)
        self.assertIn('(($name -eq "python.exe" -or $name -eq "pythonw.exe") -and $cmd', script)
        self.assertIn('$isInstalledApp -or $isUnderInstallDir -or $isLegacySourceCommand', script)
        self.assertIn('$cmd.IndexOf("app.py"', script)
        self.assertIn('Clear-ExistingAutostart', script)
        self.assertIn('Clear-LegacyProgramFiles', script)
        self.assertIn('Set-WritableIfExists', script)
        self.assertIn('Unregister-ScheduledTask', script)
        self.assertIn('New-DesktopLauncher', script)
        self.assertIn('Invoke-OptionalPowerShellFile', script)
        self.assertIn('Start-OptionalPowerShellFile', script)
        self.assertIn('Starting the contract management tool in the background', script)
        self.assertIn('Installation files are already in place', script)
        self.assertIn('Local URL:', script)
        self.assertIn('"-NoPrompt"', script)
        self.assertIn('.venv', script)
        self.assertIn('New-InstallRollbackSnapshot', script)
        self.assertIn('Restore-InstallRollbackSnapshot', script)
        self.assertIn('Invoke-InstalledAppSelfCheck', script)
        self.assertIn('Installation failed; restoring previous version', script)

    def test_offline_installer_build_outputs_single_release_exe_only(self):
        build_script_path = os.path.join(app.RESOURCE_DIR, 'build_installer.py')
        with open(build_script_path, 'r', encoding='utf-8') as f:
            script = f.read()

        self.assertIn('RELEASE_DIR', script)
        self.assertIn('clean_legacy_dist_outputs', script)
        self.assertIn('write_version=True', script)
        self.assertNotIn('DESKTOP / f', script)
        self.assertNotIn("'desktop_exe': str", script)
        self.assertNotIn('zip_dir(stage', script)
        self.assertNotIn("'zip': str", script)
        self.assertIn("'exe_sha256': file_sha256(exe_path)", script)
        self.assertIn("'app_exe_sha256': file_sha256(app_exe)", script)

    def test_release_signing_requires_sha256_timestamp_and_strict_verification(self):
        signing_path = os.path.join(
            app.RESOURCE_DIR,
            'scripts',
            'sign_installer.ps1',
        )
        with open(signing_path, 'r', encoding='utf-8') as f:
            script = f.read()

        self.assertIn('SIGNTOOL_PATH', script)
        self.assertIn('"/fd", "SHA256"', script)
        self.assertIn('@("/tr", $TimestampServer, "/td", "SHA256")', script)
        self.assertIn('& $signTool verify /pa /all /v $resolvedFile', script)
        self.assertIn('$signature.Status -ne "Valid"', script)
        self.assertIn('$signature.TimeStamperCertificate', script)
        self.assertNotIn('"UnknownError"', script)

    def test_offline_installer_preserves_runtime_database(self):
        installer_path = os.path.join(app.RESOURCE_DIR, 'installer_assets', 'install.ps1')
        with open(installer_path, 'r', encoding='utf-8-sig') as f:
            script = f.read()

        cleanup_block = script.split('function Clear-LegacyProgramFiles', 1)[1].split('function New-DesktopLauncher', 1)[0]
        self.assertNotIn('"data"', cleanup_block)
        self.assertNotIn('contracts.db', cleanup_block)
        self.assertIn('foreach ($dir in @("data", "output", "sessions", "uploads", "templates", "static", "logs"))', script)


if __name__ == '__main__':
    unittest.main()
