import unittest
import os
import json
import app as flask_app

class TestDuplicateTimetable(unittest.TestCase):
    def setUp(self):
        import uuid
        self.db_name = f'test_dup_{uuid.uuid4().hex[:8]}.db'
        flask_app.app.config['TESTING'] = True
        flask_app.app.config['DATABASE'] = os.path.join(os.path.dirname(__file__), self.db_name)
        self.client = flask_app.app.test_client()
        with flask_app.app.app_context():
            flask_app.init_db()

        # Create authenticated user
        reg = self.client.post('/api/auth/signup', json={
            'name': 'Dup Tester',
            'email': 'dup@college.edu',
            'password': 'Password123!',
            'confirm_password': 'Password123!'
        })
        self.token = reg.get_json()['token']
        self.headers = {'Authorization': f'Bearer {self.token}'}

        # Create two test subjects
        s1 = self.client.post('/api/subjects', json={'name': 'Algorithms', 'code': 'CS201'}, headers=self.headers).get_json()
        s2 = self.client.post('/api/subjects', json={'name': 'Databases', 'code': 'CS202'}, headers=self.headers).get_json()
        self.s1_id = s1['id']
        self.s2_id = s2['id']

        # Add 2 periods to Monday
        self.client.post('/api/timetable', json={
            'day': 'Monday',
            'period_number': 1,
            'start_time': '09:00',
            'end_time': '09:50',
            'subject_id': self.s1_id,
            'room': 'Lab 1',
            'faculty': 'Dr. Turing'
        }, headers=self.headers)

        self.client.post('/api/timetable', json={
            'day': 'Monday',
            'period_number': 2,
            'start_time': '10:00',
            'end_time': '10:50',
            'subject_id': self.s2_id,
            'room': 'Lab 2',
            'faculty': 'Prof. Hopper'
        }, headers=self.headers)

    def tearDown(self):
        db_path = os.path.join(os.path.dirname(__file__), getattr(self, 'db_name', 'test_dup.db'))
        if os.path.exists(db_path):
            try:
                os.remove(db_path)
            except Exception:
                pass

    def test_duplicate_single_day(self):
        # Duplicate Monday to Tuesday
        res = self.client.post('/api/timetable/duplicate', json={
            'source_day': 'Monday',
            'target_day': 'Tuesday',
            'replace_target': True
        }, headers=self.headers)

        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['count'], 2)

        # Verify Tuesday now has the 2 periods
        tue_periods = self.client.get('/api/timetable?day=Tuesday', headers=self.headers).get_json()
        self.assertEqual(len(tue_periods), 2)
        self.assertEqual(tue_periods[0]['period_number'], 1)
        self.assertEqual(tue_periods[0]['subject_id'], self.s1_id)
        self.assertEqual(tue_periods[0]['start_time'], '09:00')
        self.assertEqual(tue_periods[1]['period_number'], 2)
        self.assertEqual(tue_periods[1]['subject_id'], self.s2_id)

    def test_duplicate_multi_target_days(self):
        # Duplicate Monday to Wednesday, Thursday, Friday
        res = self.client.post('/api/timetable/duplicate', json={
            'source_day': 'Monday',
            'target_days': ['Wednesday', 'Thursday', 'Friday'],
            'replace_target': True
        }, headers=self.headers)

        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['total_inserted'], 6)

        for day in ['Wednesday', 'Thursday', 'Friday']:
            periods = self.client.get(f'/api/timetable?day={day}', headers=self.headers).get_json()
            self.assertEqual(len(periods), 2)

    def test_duplicate_empty_source_fails_and_preserves_target(self):
        # Ensure Tuesday has 0 periods
        tue_before = self.client.get('/api/timetable?day=Tuesday', headers=self.headers).get_json()
        self.assertEqual(len(tue_before), 0)

        # Attempt to duplicate Tuesday (empty) into Monday
        res = self.client.post('/api/timetable/duplicate', json={
            'source_day': 'Tuesday',
            'target_day': 'Monday',
            'replace_target': True
        }, headers=self.headers)

        self.assertEqual(res.status_code, 400)
        self.assertIn('no scheduled periods', res.get_json()['error'])

        # Verify Monday was NOT wiped out!
        mon_after = self.client.get('/api/timetable?day=Monday', headers=self.headers).get_json()
        self.assertEqual(len(mon_after), 2)

    def test_duplicate_same_day_fails(self):
        res = self.client.post('/api/timetable/duplicate', json={
            'source_day': 'Monday',
            'target_day': 'Monday'
        }, headers=self.headers)
        self.assertEqual(res.status_code, 400)

    def test_duplicate_append_mode(self):
        # Add 1 period to Saturday
        self.client.post('/api/timetable', json={
            'day': 'Saturday',
            'period_number': 1,
            'start_time': '08:00',
            'end_time': '08:50',
            'subject_id': self.s1_id
        }, headers=self.headers)

        # Append Monday's 2 periods to Saturday
        res = self.client.post('/api/timetable/duplicate', json={
            'source_day': 'Monday',
            'target_day': 'Saturday',
            'replace_target': False
        }, headers=self.headers)
        self.assertEqual(res.status_code, 200)

        sat_periods = self.client.get('/api/timetable?day=Saturday', headers=self.headers).get_json()
        self.assertEqual(len(sat_periods), 3)
        self.assertEqual(sat_periods[0]['period_number'], 1)
        self.assertEqual(sat_periods[1]['period_number'], 2)
        self.assertEqual(sat_periods[2]['period_number'], 3)

    def test_duplicate_user_isolation(self):
        # User B registers
        reg_b = self.client.post('/api/auth/signup', json={
            'name': 'User B',
            'email': 'userb@college.edu',
            'password': 'Password123!',
            'confirm_password': 'Password123!'
        })
        token_b = reg_b.get_json()['token']
        headers_b = {'Authorization': f'Bearer {token_b}'}

        # User B attempts to duplicate Monday (where User A has periods, but User B has none)
        res = self.client.post('/api/timetable/duplicate', json={
            'source_day': 'Monday',
            'target_day': 'Tuesday'
        }, headers=headers_b)

        # User B has no periods on Monday, so it should fail for User B
        self.assertEqual(res.status_code, 400)
        self.assertIn('no scheduled periods', res.get_json()['error'])

        # User A's Monday is unchanged
        mon_a = self.client.get('/api/timetable?day=Monday', headers=self.headers).get_json()
        self.assertEqual(len(mon_a), 2)

if __name__ == '__main__':
    unittest.main()
