import os
import unittest

import app


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
            'vendor/alpine.min.js',
            'vendor/lucide.min.js',
        )
        for asset in local_assets:
            self.assertIn(asset, html)

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


if __name__ == '__main__':
    unittest.main()
