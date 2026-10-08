import unittest
import json
import os
import uuid
from datetime import date
import app as flask_app

class TestAuthAndCloudSync(unittest.TestCase):
    def setUp(self):
        self.db_name = f'test_auth_{uuid.uuid4().hex[:8]}.db'
        flask_app.app.config['TESTING'] = True
        flask_app.app.config['DATABASE'] = os.path.join(os.path.dirname(__file__), self.db_name)
        self.client = flask_app.app.test_client()
        with flask_app.app.app_context():
            flask_app.init_db()

    def tearDown(self):
        db_path = os.path.join(os.path.dirname(__file__), getattr(self, 'db_name', 'test_auth.db'))
        if os.path.exists(db_path):
            try:
                os.remove(db_path)
            except Exception:
                pass

    def test_signup_validation(self):
        # Empty fields
        res = self.client.post('/api/auth/signup', json={'name': '', 'email': '', 'password': '', 'confirm_password': ''})
        self.assertEqual(res.status_code, 400)

        # Invalid email
        res = self.client.post('/api/auth/signup', json={'name': 'User', 'email': 'not-an-email', 'password': 'password123', 'confirm_password': 'password123'})
        self.assertEqual(res.status_code, 400)

        # Mismatched passwords
        res = self.client.post('/api/auth/signup', json={'name': 'User', 'email': 'user@college.edu', 'password': 'password123', 'confirm_password': 'different'})
        self.assertEqual(res.status_code, 400)

        # Successful signup
        res = self.client.post('/api/auth/signup', json={'name': 'User A', 'email': 'userA@college.edu', 'password': 'password123', 'confirm_password': 'password123'})
        self.assertEqual(res.status_code, 201)
        data = res.get_json()
        self.assertTrue(data['success'])
        self.assertIn('token', data)

        # Duplicate account prevention
        res_dup = self.client.post('/api/auth/signup', json={'name': 'User A', 'email': 'userA@college.edu', 'password': 'password123', 'confirm_password': 'password123'})
        self.assertEqual(res_dup.status_code, 409)

    def test_complete_multi_user_isolation_and_device_sync_flow(self):
        # Step 1: Create Account A
        res_a = self.client.post('/api/auth/signup', json={
            'name': 'Student Alice',
            'email': 'alice@college.edu',
            'password': 'Password123!',
            'confirm_password': 'Password123!'
        })
        self.assertEqual(res_a.status_code, 201)
        token_a = res_a.get_json()['token']
        headers_a = {'Authorization': f'Bearer {token_a}'}

        # Step 2: Create subjects and timetable under Account A
        sub_a = self.client.post('/api/subjects', json={
            'name': 'Data Structures',
            'code': 'CS201',
            'faculty': 'Dr. Turing',
            'room': 'Lab 1'
        }, headers=headers_a).get_json()
        sub_a_id = sub_a['id']

        tt_a = self.client.post('/api/timetable', json={
            'day': 'Monday',
            'period_number': 1,
            'start_time': '09:00',
            'end_time': '09:50',
            'subject_id': sub_a_id
        }, headers=headers_a).get_json()
        period_a_id = tt_a['id']

        # Step 3: Mark attendance for Account A
        today_str = date.today().isoformat()
        att_res = self.client.post('/api/attendance', json={
            'date': today_str,
            'period_id': period_a_id,
            'subject_id': sub_a_id,
            'status': 'Present'
        }, headers=headers_a)
        self.assertEqual(att_res.status_code, 201)

        # Step 4: Logout Account A on Device 1
        logout_res = self.client.post('/api/auth/logout', headers=headers_a)
        self.assertEqual(logout_res.status_code, 200)

        # Verify token_a is invalidated
        check_res = self.client.get('/api/subjects', headers=headers_a)
        self.assertEqual(check_res.status_code, 401)

        # Step 5: Login again with Account A
        login_res = self.client.post('/api/auth/login', json={
            'email': 'alice@college.edu',
            'password': 'Password123!'
        })
        self.assertEqual(login_res.status_code, 200)
        token_a_dev1 = login_res.get_json()['token']
        headers_a_dev1 = {'Authorization': f'Bearer {token_a_dev1}'}

        # Verify all data remains
        summary_a = self.client.get('/api/attendance/summary', headers=headers_a_dev1).get_json()
        self.assertEqual(summary_a['overall']['total'], 1)
        self.assertEqual(summary_a['overall']['attended'], 1)
        self.assertEqual(summary_a['overall']['percentage'], 100.0)

        # Step 6: Simulate Device 2 login with Account A
        login_dev2 = self.client.post('/api/auth/login', json={
            'email': 'alice@college.edu',
            'password': 'Password123!'
        })
        self.assertEqual(login_dev2.status_code, 200)
        token_a_dev2 = login_dev2.get_json()['token']
        headers_a_dev2 = {'Authorization': f'Bearer {token_a_dev2}'}

        # Verify same data appears on Device 2
        summary_dev2 = self.client.get('/api/attendance/summary', headers=headers_a_dev2).get_json()
        self.assertEqual(summary_dev2['overall']['total'], 1)
        self.assertEqual(summary_dev2['subjects'][0]['code'], 'CS201')

        # Step 7: Modify attendance on Device 2 (mark absent for next class)
        att_dev2 = self.client.post('/api/attendance', json={
            'date': today_str,
            'subject_id': sub_a_id,
            'status': 'Absent'
        }, headers=headers_a_dev2)
        self.assertEqual(att_dev2.status_code, 201)

        # Step 8: Return to Device 1 and verify changes synchronized across devices!
        summary_dev1_updated = self.client.get('/api/attendance/summary', headers=headers_a_dev1).get_json()
        self.assertEqual(summary_dev1_updated['overall']['total'], 2)
        self.assertEqual(summary_dev1_updated['overall']['attended'], 1)
        self.assertEqual(summary_dev1_updated['overall']['absent'], 1)
        self.assertEqual(summary_dev1_updated['overall']['percentage'], 50.0)

        # Step 9: Create Account B
        res_b = self.client.post('/api/auth/signup', json={
            'name': 'Student Bob',
            'email': 'bob@college.edu',
            'password': 'BobPassword123!',
            'confirm_password': 'BobPassword123!'
        })
        self.assertEqual(res_b.status_code, 201)
        token_b = res_b.get_json()['token']
        headers_b = {'Authorization': f'Bearer {token_b}'}

        # Step 10: Verify Account B CANNOT see Account A's data (Data Security & RLS)
        subjects_b = self.client.get('/api/subjects', headers=headers_b).get_json()
        self.assertEqual(len(subjects_b), 0)  # Account B starts with 0 subjects!

        summary_b = self.client.get('/api/attendance/summary', headers=headers_b).get_json()
        self.assertEqual(summary_b['overall']['total'], 0)  # 0 classes for Bob!

        # Verify Account B cannot access or modify Alice's subject directly via ID
        tamper_get = self.client.get(f'/api/subjects/{sub_a_id}', headers=headers_b)
        self.assertEqual(tamper_get.status_code, 404)

        tamper_delete = self.client.delete(f'/api/subjects/{sub_a_id}', headers=headers_b)
        self.assertEqual(tamper_delete.status_code, 404)

        # Alice's subject is still intact
        alice_sub_check = self.client.get(f'/api/subjects/{sub_a_id}', headers=headers_a_dev1)
        self.assertEqual(alice_sub_check.status_code, 200)

    def test_offline_queue_sync_endpoint(self):
        # Create user
        signup_res = self.client.post('/api/auth/signup', json={
            'name': 'Charlie',
            'email': 'charlie@college.edu',
            'password': 'CharliePassword!',
            'confirm_password': 'CharliePassword!'
        })
        token = signup_res.get_json()['token']
        headers = {'Authorization': f'Bearer {token}'}

        sub = self.client.post('/api/subjects', json={'name': 'Networks', 'code': 'NET101'}, headers=headers).get_json()
        sid = sub['id']

        # Simulate flushing offline queued attendance actions
        queue = [
            {'date': '2026-10-01', 'subject_id': sid, 'status': 'Present'},
            {'date': '2026-10-02', 'subject_id': sid, 'status': 'Present'},
            {'date': '2026-10-03', 'subject_id': sid, 'status': 'Absent'}
        ]
        sync_res = self.client.post('/api/attendance/sync-offline', json={'actions': queue}, headers=headers)
        self.assertEqual(sync_res.status_code, 200)
        self.assertEqual(sync_res.get_json()['synced_count'], 3)

        # Verify in summary
        sum_res = self.client.get('/api/attendance/summary', headers=headers).get_json()
        self.assertEqual(sum_res['overall']['total'], 3)
        self.assertEqual(sum_res['overall']['attended'], 2)
        self.assertEqual(sum_res['overall']['absent'], 1)

    def test_password_reset_flow(self):
        # 1. Create account
        self.client.post('/api/auth/signup', json={
            'name': 'Dave',
            'email': 'dave@college.edu',
            'password': 'OldPassword123!',
            'confirm_password': 'OldPassword123!'
        })

        # 2. Forgot password request
        forgot_res = self.client.post('/api/auth/forgot-password', json={'email': 'dave@college.edu'})
        self.assertEqual(forgot_res.status_code, 200)
        reset_token = forgot_res.get_json()['reset_token']
        self.assertTrue(len(reset_token) > 0)

        # 3. Reset password with token
        reset_res = self.client.post('/api/auth/reset-password', json={
            'token': reset_token,
            'new_password': 'NewSecurePassword123!',
            'confirm_password': 'NewSecurePassword123!'
        })
        self.assertEqual(reset_res.status_code, 200)

        # 4. Old password should fail
        fail_login = self.client.post('/api/auth/login', json={
            'email': 'dave@college.edu',
            'password': 'OldPassword123!'
        })
        self.assertEqual(fail_login.status_code, 401)

        # 5. New password should succeed
        success_login = self.client.post('/api/auth/login', json={
            'email': 'dave@college.edu',
            'password': 'NewSecurePassword123!'
        })
        self.assertEqual(success_login.status_code, 200)
        self.assertIn('token', success_login.get_json())

if __name__ == '__main__':
    unittest.main()
