import unittest
import os
import json
import uuid
import tempfile
from datetime import datetime, date, timedelta

import app as flask_app
from app import init_db, get_db

class TestHolidayFeature(unittest.TestCase):
    def setUp(self):
        # Create unique temp db for this test run
        self.db_name = f"test_holidays_{uuid.uuid4().hex[:8]}.db"
        self.db_path = os.path.join(tempfile.gettempdir(), self.db_name)
        flask_app.DATABASE = self.db_path
        flask_app.app.config['TESTING'] = True
        self.client = flask_app.app.test_client()

        with flask_app.app.app_context():
            init_db()

        # Sign up User A
        self.user_a_email = f"user_a_{uuid.uuid4().hex[:6]}@college.edu"
        res_a = self.client.post('/api/auth/signup', json={
            'name': 'Student A',
            'email': self.user_a_email,
            'password': 'Password123!',
            'confirm_password': 'Password123!'
        })
        self.token_a = res_a.get_json()['token']
        self.headers_a = {'Authorization': f'Bearer {self.token_a}'}

        # Sign up User B for multi-tenant isolation testing
        self.user_b_email = f"user_b_{uuid.uuid4().hex[:6]}@college.edu"
        res_b = self.client.post('/api/auth/signup', json={
            'name': 'Student B',
            'email': self.user_b_email,
            'password': 'Password123!',
            'confirm_password': 'Password123!'
        })
        self.token_b = res_b.get_json()['token']
        self.headers_b = {'Authorization': f'Bearer {self.token_b}'}

    def tearDown(self):
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except Exception:
                pass

    def test_mark_and_unmark_holiday(self):
        test_date = "2026-10-15"
        # 1. Mark as holiday
        res = self.client.post('/api/holidays', json={
            'date': test_date,
            'name': 'Diwali Festival'
        }, headers=self.headers_a)
        self.assertEqual(res.status_code, 201)
        data = res.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['holiday']['date'], test_date)
        self.assertEqual(data['holiday']['name'], 'Diwali Festival')

        # 2. Get holidays
        get_res = self.client.get(f'/api/holidays?date={test_date}', headers=self.headers_a)
        self.assertEqual(get_res.status_code, 200)
        hols = get_res.get_json()
        self.assertEqual(len(hols), 1)
        self.assertEqual(hols[0]['name'], 'Diwali Festival')

        # 3. Unmark holiday
        unmark_res = self.client.post('/api/holidays/unmark', json={'date': test_date}, headers=self.headers_a)
        self.assertEqual(unmark_res.status_code, 200)

        # 4. Verify no longer a holiday
        get_res2 = self.client.get(f'/api/holidays?date={test_date}', headers=self.headers_a)
        self.assertEqual(len(get_res2.get_json()), 0)

    def test_holiday_attendance_behavior_and_blocking(self):
        # Setup: Create a subject and timetable period on Monday for User A
        sub_res = self.client.post('/api/subjects', json={
            'name': 'Software Engineering',
            'code': 'CS301',
            'faculty': 'Dr. Smith',
            'room': 'Lab 1'
        }, headers=self.headers_a)
        sub_id = sub_res.get_json()['id']

        # Add timetable for Monday
        tt_res = self.client.post('/api/timetable', json={
            'day': 'Monday',
            'period_number': 1,
            'start_time': '09:00',
            'end_time': '09:50',
            'subject_id': sub_id
        }, headers=self.headers_a)
        period_id = tt_res.get_json()['id']

        # Choose a Monday: 2026-10-12 was a Monday
        monday_date = "2026-10-12"

        # Check today before marking holiday
        today_res = self.client.get(f'/api/attendance/today?date={monday_date}', headers=self.headers_a)
        today_data = today_res.get_json()
        self.assertFalse(today_data['is_holiday'])
        self.assertEqual(len(today_data['periods']), 1)

        # Mark Monday as a holiday
        self.client.post('/api/holidays', json={
            'date': monday_date,
            'name': 'National Holiday'
        }, headers=self.headers_a)

        # Check today after marking holiday: periods must be empty, conducted = 0, is_holiday = True
        today_res2 = self.client.get(f'/api/attendance/today?date={monday_date}', headers=self.headers_a)
        today_data2 = today_res2.get_json()
        self.assertTrue(today_data2['is_holiday'])
        self.assertEqual(today_data2['holiday_name'], 'National Holiday')
        self.assertEqual(len(today_data2['periods']), 0)
        self.assertEqual(today_data2['summary']['total'], 0)
        self.assertEqual(today_data2['summary']['present'], 0)
        self.assertEqual(today_data2['summary']['absent'], 0)
        self.assertEqual(today_data2['summary']['percentage'], 0.0)

        # Attempting to record attendance on holiday date must be rejected (400)
        att_res = self.client.post('/api/attendance', json={
            'date': monday_date,
            'period_id': period_id,
            'subject_id': sub_id,
            'status': 'Present'
        }, headers=self.headers_a)
        self.assertEqual(att_res.status_code, 400)
        self.assertIn('Holiday', att_res.get_json()['error'])

    def test_holiday_calculation_exclusion(self):
        # Create 2 subjects
        s1 = self.client.post('/api/subjects', json={'name': 'Math', 'code': 'MA101'}, headers=self.headers_a).get_json()['id']
        s2 = self.client.post('/api/subjects', json={'name': 'Physics', 'code': 'PH101'}, headers=self.headers_a).get_json()['id']

        # Add timetable for Monday (Math) and Tuesday (Physics)
        tt_m = self.client.post('/api/timetable', json={
            'day': 'Monday', 'period_number': 1, 'start_time': '09:00', 'end_time': '09:50', 'subject_id': s1
        }, headers=self.headers_a).get_json()['id']

        tt_t = self.client.post('/api/timetable', json={
            'day': 'Tuesday', 'period_number': 1, 'start_time': '09:00', 'end_time': '09:50', 'subject_id': s2
        }, headers=self.headers_a).get_json()['id']

        mon_date = "2026-10-12" # Monday
        tue_date = "2026-10-13" # Tuesday

        # Record attendance: Monday Present, Tuesday Absent
        self.client.post('/api/attendance', json={
            'date': mon_date, 'period_id': tt_m, 'subject_id': s1, 'status': 'Present'
        }, headers=self.headers_a)

        self.client.post('/api/attendance', json={
            'date': tue_date, 'period_id': tt_t, 'subject_id': s2, 'status': 'Absent'
        }, headers=self.headers_a)

        # Prior check: 1 Present, 1 Absent -> 50%
        sum_res1 = self.client.get('/api/attendance/summary', headers=self.headers_a).get_json()
        self.assertEqual(sum_res1['overall']['total'], 2)
        self.assertEqual(sum_res1['overall']['attended'], 1)
        self.assertEqual(sum_res1['overall']['percentage'], 50.0)

        # Now mark Tuesday as a Holiday
        self.client.post('/api/holidays', json={
            'date': tue_date,
            'name': 'Midterm Break'
        }, headers=self.headers_a)

        # Post check: Tuesday's absent class MUST be excluded!
        # Result must be: 1 conducted, 1 attended, 0 absent -> 100%!
        sum_res2 = self.client.get('/api/attendance/summary', headers=self.headers_a).get_json()
        self.assertEqual(sum_res2['overall']['total'], 1)
        self.assertEqual(sum_res2['overall']['attended'], 1)
        self.assertEqual(sum_res2['overall']['absent'], 0)
        self.assertEqual(sum_res2['overall']['percentage'], 100.0)
        self.assertEqual(sum_res2['total_holidays'], 1)

        # Physics (s2) which had absent on Tuesday must now have 0 total classes conducted!
        ph_details = self.client.get(f'/api/subjects/{s2}', headers=self.headers_a).get_json()
        self.assertEqual(ph_details['total'], 0)
        self.assertEqual(ph_details['attended'], 0)

        # Unmark Tuesday as Holiday -> Restores previous attendance!
        self.client.post('/api/holidays/unmark', json={'date': tue_date}, headers=self.headers_a)

        sum_res3 = self.client.get('/api/attendance/summary', headers=self.headers_a).get_json()
        self.assertEqual(sum_res3['overall']['total'], 2)
        self.assertEqual(sum_res3['overall']['attended'], 1)
        self.assertEqual(sum_res3['overall']['percentage'], 50.0)

    def test_multi_tenant_holiday_isolation(self):
        # Mark holiday for User A
        h_date = "2026-10-20"
        self.client.post('/api/holidays', json={
            'date': h_date,
            'name': 'User A Special Holiday'
        }, headers=self.headers_a)

        # User A has the holiday
        res_a = self.client.get(f'/api/holidays?date={h_date}', headers=self.headers_a).get_json()
        self.assertEqual(len(res_a), 1)

        # User B must NOT have this holiday
        res_b = self.client.get(f'/api/holidays?date={h_date}', headers=self.headers_b).get_json()
        self.assertEqual(len(res_b), 0)

        # User B today view is not a holiday
        today_b = self.client.get(f'/api/attendance/today?date={h_date}', headers=self.headers_b).get_json()
        self.assertFalse(today_b['is_holiday'])

    def test_calendar_and_monthly_with_holidays(self):
        h_date = "2026-10-05"
        self.client.post('/api/holidays', json={
            'date': h_date,
            'name': 'Gandhi Jayanti Observed'
        }, headers=self.headers_a)

        # Calendar endpoint
        cal_res = self.client.get('/api/attendance/calendar?month=2026-10', headers=self.headers_a)
        self.assertEqual(cal_res.status_code, 200)
        cal = cal_res.get_json()
        self.assertIn(h_date, cal)
        self.assertTrue(cal[h_date]['is_holiday'])
        self.assertEqual(cal[h_date]['status'], 'holiday')
        self.assertEqual(cal[h_date]['holiday_name'], 'Gandhi Jayanti Observed')

        # Monthly endpoint
        monthly_res = self.client.get('/api/attendance/monthly', headers=self.headers_a)
        self.assertEqual(monthly_res.status_code, 200)

    def test_attendance_records_holiday_filtering(self):
        h_date = "2026-10-02"
        self.client.post('/api/holidays', json={
            'date': h_date,
            'name': 'Gandhi Jayanti'
        }, headers=self.headers_a)

        # Query all records
        all_rec = self.client.get('/api/attendance', headers=self.headers_a).get_json()
        holiday_entries = [r for r in all_rec if r.get('status') == 'Holiday']
        self.assertEqual(len(holiday_entries), 1)
        self.assertEqual(holiday_entries[0]['date'], h_date)

        # Query filter status = Holiday
        hol_filter = self.client.get('/api/attendance?status=Holiday', headers=self.headers_a).get_json()
        self.assertEqual(len(hol_filter), 1)
        self.assertEqual(hol_filter[0]['status'], 'Holiday')

        # Query filter status = Present
        pres_filter = self.client.get('/api/attendance?status=Present', headers=self.headers_a).get_json()
        self.assertEqual(len(pres_filter), 0)

    def test_backup_export_and_import_with_holidays(self):
        h_date = "2026-10-31"
        self.client.post('/api/holidays', json={
            'date': h_date,
            'name': 'Semester End Holiday'
        }, headers=self.headers_a)

        # Export backup
        backup_res = self.client.get('/api/backup/export', headers=self.headers_a)
        self.assertEqual(backup_res.status_code, 200)
        backup_data = backup_res.get_json()
        self.assertIn('holidays', backup_data)
        self.assertEqual(len(backup_data['holidays']), 1)
        self.assertEqual(backup_data['holidays'][0]['date'], h_date)

        # Clear/Reset
        self.client.post('/api/backup/reset-all', headers=self.headers_a)
        hols_after_reset = self.client.get('/api/holidays', headers=self.headers_a).get_json()
        self.assertEqual(len(hols_after_reset), 0)

        # Import backup
        import_res = self.client.post('/api/backup/import', json=backup_data, headers=self.headers_a)
        self.assertEqual(import_res.status_code, 200)
        self.assertEqual(import_res.get_json()['imported']['holidays'], 1)

        # Verify holiday restored
        hols_restored = self.client.get('/api/holidays', headers=self.headers_a).get_json()
        self.assertEqual(len(hols_restored), 1)
        self.assertEqual(hols_restored[0]['date'], h_date)

if __name__ == '__main__':
    unittest.main()
