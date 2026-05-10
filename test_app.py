
import unittest
import os
from dotenv import load_dotenv
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))
from app import app
import database as db

class APITestCase(unittest.TestCase):
    def setUp(self):
        self.app = app.test_client()
        db.init_db()

    def test_health(self):
        resp = self.app.get('/health')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('status', resp.get_json())

    def test_inventory_empty(self):
        resp = self.app.get('/api/inventory', headers={'X-API-Key': os.getenv('API_SECRET', 'testsecret')})
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn('items', data)

if __name__ == '__main__':
    unittest.main()
