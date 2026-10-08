import unittest
import os
import json
import tempfile
from datetime import date, timedelta

# Import our app and helpers
import app as flask_app
from app import calculate_stats

class TestAttendanceCalculations(unittest.TestCase):
    def test_zero_classes(self):
        stats = calculate_stats(0, 0, 75.0)
        self.assertEqual(stats['total'], 0)
        self.assertEqual(stats['attended'], 0)
        self.assertEqual(stats['absent'], 0)
        self.assertEqual(stats['percentage'], 0.0)
        self.assertEqual(stats['can_miss'], 0)
        self.assertEqual(stats['need_to_attend'], 0)

    def test_prompt_example_can_miss(self):
        # From prompt: 41 attended / 50 total (82%), required 75% -> safe to miss 4 classes
        stats = calculate_stats(41, 50, 75.0)
        self.assertEqual(stats['percentage'], 82.0)
        self.assertEqual(stats['can_miss'], 4)
        self.assertEqual(stats['need_to_attend'], 0)
        # Verify: if 4 classes missed, 41 / 54 = 75.92% (>= 75%)
        pct_after_4 = (41 / 54) * 100
        self.assertGreaterEqual(pct_after_4, 75.0)
        # If 5 classes missed, 41 / 55 = 74.54% (< 75%)
        pct_after_5 = (41 / 55) * 100
        self.assertLess(pct_after_5, 75.0)

    def test_prompt_example_need_to_attend(self):
        # From prompt: 68% (e.g. 34 attended / 50 total), required 75% -> need 14 consecutive classes
        stats = calculate_stats(34, 50, 75.0)
        self.assertEqual(stats['percentage'], 68.0)
        self.assertEqual(stats['can_miss'], 0)
        self.assertEqual(stats['need_to_attend'], 14)
        # Verify: if 14 classes attended, (34+14)/(50+14) = 48/64 = 75.0%
        self.assertEqual((34 + 14) / (50 + 14) * 100, 75.0)

    def test_perfect_attendance(self):
        stats = calculate_stats(20, 20, 75.0)
        self.assertEqual(stats['percentage'], 100.0)
        # 20 / 0.75 - 20 = 26.666 - 20 = 6.666 -> 6
        self.assertEqual(stats['can_miss'], 6)
        self.assertEqual(stats['need_to_attend'], 0)

    def test_zero_attendance_non_zero_classes(self):
        stats = calculate_stats(0, 10, 75.0)
        self.assertEqual(stats['percentage'], 0.0)
        self.assertEqual(stats['can_miss'], 0)
        # Need to attend: ceil((0.75 * 10 - 0) / 0.25) = ceil(7.5 / 0.25) = 30 classes
        self.assertEqual(stats['need_to_attend'], 30)
        self.assertEqual((0 + 30) / (10 + 30) * 100, 75.0)

    def test_target_100_percent_impossible(self):
        # If missed 1 class, can never reach 100% in finite classes
        stats = calculate_stats(9, 10, 100.0)
        self.assertEqual(stats['need_to_attend'], -1)

    def test_threshold_update(self):
        # If target changed to 80%
        stats_75 = calculate_stats(41, 50, 75.0)
        stats_80 = calculate_stats(41, 50, 80.0)
        self.assertEqual(stats_75['can_miss'], 4)
        # 41 / 0.8 - 50 = 51.25 - 50 = 1.25 -> 1
        self.assertEqual(stats_80['can_miss'], 1)


class TestAppAPI(unittest.TestCase):
    def setUp(self):
        flask_app.app.config['TESTING'] = True
        flask_app.app.config['DATABASE'] = os.path.join(os.path.dirname(__file__), 'test_attendance_calc.db')
        self.client = flask_app.app.test_client()
        with flask_app.app.app_context():
            flask_app.init_db()
        
        # Create test user and auth headers
        reg = self.client.post('/api/auth/signup', json={
            'name': 'Calc User',
            'email': 'calc@college.edu',
            'password': 'Password123!',
            'confirm_password': 'Password123!'
        })
        if reg.status_code == 201:
            self.token = reg.get_json()['token']
        else:
            login = self.client.post('/api/auth/login', json={
                'email': 'calc@college.edu',
                'password': 'Password123!'
            })
            self.token = login.get_json()['token']
        self.headers = {'Authorization': f'Bearer {self.token}'}
        
        # Seed test data in test db before each test
        self.client.post('/api/backup/seed', headers=self.headers)

    def tearDown(self):
        db_path = os.path.join(os.path.dirname(__file__), 'test_attendance_calc.db')
        if os.path.exists(db_path):
            try:
                os.remove(db_path)
            except Exception:
                pass

    def test_seed_and_summary(self):
        # Get summary
        sum_res = self.client.get('/api/attendance/summary', headers=self.headers)
        self.assertEqual(sum_res.status_code, 200)
        data = sum_res.get_json()
        self.assertIn('overall', data)
        self.assertIn('subjects', data)
        self.assertGreater(data['overall']['total'], 0)
        self.assertGreater(len(data['subjects']), 0)

    def test_date_range_filtering(self):
        # Check summary with date range filter
        today = date.today().isoformat()
        seven_days_ago = (date.today() - timedelta(days=7)).isoformat()
        res = self.client.get(f'/api/attendance/summary?from_date={seven_days_ago}&to_date={today}', headers=self.headers)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data['filter']['from_date'], seven_days_ago)
        self.assertEqual(data['filter']['to_date'], today)

    def test_today_attendance(self):
        res = self.client.get('/api/attendance/today', headers=self.headers)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn('periods', data)
        self.assertIn('summary', data)

    def test_excel_export_endpoint(self):
        res = self.client.get('/api/export/excel?scope=all', headers=self.headers)
        self.assertEqual(res.status_code, 200)
        self.assertIn('spreadsheetml', res.content_type)
        self.assertGreater(len(res.data), 1000)

    def test_backup_export_and_import(self):
        # Export
        exp_res = self.client.get('/api/backup/export', headers=self.headers)
        self.assertEqual(exp_res.status_code, 200)
        backup_json = exp_res.get_json()
        self.assertIn('subjects', backup_json)
        self.assertIn('attendance', backup_json)
        self.assertGreater(len(backup_json['attendance']), 0)

        # Clear attendance
        clr_res = self.client.post('/api/backup/clear-attendance', headers=self.headers)
        self.assertEqual(clr_res.status_code, 200)
        sum_empty = self.client.get('/api/attendance/summary', headers=self.headers).get_json()
        self.assertEqual(sum_empty['overall']['total'], 0)

        # Re-import
        imp_res = self.client.post('/api/backup/import', json=backup_json, headers=self.headers)
        self.assertEqual(imp_res.status_code, 200)
        sum_restored = self.client.get('/api/attendance/summary', headers=self.headers).get_json()
        self.assertGreater(sum_restored['overall']['total'], 0)

if __name__ == '__main__':
    unittest.main()
