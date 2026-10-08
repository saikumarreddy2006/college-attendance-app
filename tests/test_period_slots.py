import unittest
import os
import json
import uuid
import app as flask_app

class TestPeriodSlots(unittest.TestCase):
    def setUp(self):
        self.db_name = f'test_slots_{uuid.uuid4().hex[:8]}.db'
        flask_app.app.config['TESTING'] = True
        flask_app.app.config['DATABASE'] = os.path.join(os.path.dirname(__file__), self.db_name)
        self.client = flask_app.app.test_client()
        with flask_app.app.app_context():
            flask_app.init_db()

        # Create user A
        reg = self.client.post('/api/auth/signup', json={
            'name': 'Slot User A',
            'email': 'slot_a@college.edu',
            'password': 'Password123!',
            'confirm_password': 'Password123!'
        })
        self.token_a = reg.get_json()['token']
        self.headers_a = {'Authorization': f'Bearer {self.token_a}'}

        # Create user B
        reg_b = self.client.post('/api/auth/signup', json={
            'name': 'Slot User B',
            'email': 'slot_b@college.edu',
            'password': 'Password123!',
            'confirm_password': 'Password123!'
        })
        self.token_b = reg_b.get_json()['token']
        self.headers_b = {'Authorization': f'Bearer {self.token_b}'}

        # Subject for user A
        s = self.client.post('/api/subjects', json={'name': 'Computer Networks', 'code': 'CS301'}, headers=self.headers_a).get_json()
        self.sub_id = s['id']

    def tearDown(self):
        db_path = os.path.join(os.path.dirname(__file__), getattr(self, 'db_name', 'test_slots.db'))
        if os.path.exists(db_path):
            try:
                os.remove(db_path)
            except Exception:
                pass

    def test_default_slots_initialization(self):
        res = self.client.get('/api/period-slots', headers=self.headers_a)
        self.assertEqual(res.status_code, 200)
        slots = res.get_json()
        self.assertEqual(len(slots), 6)
        self.assertEqual(slots[0]['slot_number'], 1)
        self.assertEqual(slots[0]['start_time'], '09:00')
        self.assertEqual(slots[0]['end_time'], '09:50')

    def test_create_and_delete_period_slot(self):
        # Create Period 7
        res = self.client.post('/api/period-slots', json={
            'slot_number': 7,
            'label': 'Evening Tutorial',
            'start_time': '16:00',
            'end_time': '16:50'
        }, headers=self.headers_a)
        self.assertEqual(res.status_code, 201)
        slot_data = res.get_json()
        slot_id = slot_data['id']
        self.assertTrue(slot_data['success'])

        # Verify it appears in list
        slots = self.client.get('/api/period-slots', headers=self.headers_a).get_json()
        p7 = next((s for s in slots if s['id'] == slot_id), None)
        self.assertIsNotNone(p7)
        self.assertEqual(p7['label'], 'Evening Tutorial')

        # Delete Period 7
        del_res = self.client.delete(f'/api/period-slots/{slot_id}', headers=self.headers_a)
        self.assertEqual(del_res.status_code, 200)
        self.assertTrue(del_res.get_json()['success'])

        # Verify removed
        slots_after = self.client.get('/api/period-slots', headers=self.headers_a).get_json()
        self.assertIsNone(next((s for s in slots_after if s['id'] == slot_id), None))

    def test_update_period_slot(self):
        slots = self.client.get('/api/period-slots', headers=self.headers_a).get_json()
        s1 = slots[0]

        put_res = self.client.put(f'/api/period-slots/{s1["id"]}', json={
            'slot_number': 1,
            'label': 'Morning Kickoff',
            'start_time': '08:45',
            'end_time': '09:35'
        }, headers=self.headers_a)
        self.assertEqual(put_res.status_code, 200)

        updated = self.client.get('/api/period-slots', headers=self.headers_a).get_json()
        self.assertEqual(updated[0]['label'], 'Morning Kickoff')
        self.assertEqual(updated[0]['start_time'], '08:45')
        self.assertEqual(updated[0]['end_time'], '09:35')

    def test_timetable_integration_with_period_slot(self):
        slots = self.client.get('/api/period-slots', headers=self.headers_a).get_json()
        s2 = slots[1] # Period 2

        # Add timetable period using slot_id
        tt_res = self.client.post('/api/timetable', json={
            'day': 'Wednesday',
            'slot_id': s2['id'],
            'subject_id': self.sub_id,
            'room': 'LH-204',
            'faculty': 'Prof. Shannon'
        }, headers=self.headers_a)
        self.assertEqual(tt_res.status_code, 201)

        # Verify timetable entries
        tt = self.client.get('/api/timetable?day=Wednesday', headers=self.headers_a).get_json()
        self.assertEqual(len(tt), 1)
        self.assertEqual(tt[0]['period_number'], s2['slot_number'])
        self.assertEqual(tt[0]['start_time'], s2['start_time'])
        self.assertEqual(tt[0]['end_time'], s2['end_time'])
        self.assertEqual(tt[0]['effective_room'], 'LH-204')
        self.assertEqual(tt[0]['effective_faculty'], 'Prof. Shannon')

    def test_user_isolation(self):
        # User A slots
        slots_a = self.client.get('/api/period-slots', headers=self.headers_a).get_json()
        slot_a_id = slots_a[0]['id']

        # User B cannot update User A's slot
        put_res = self.client.put(f'/api/period-slots/{slot_a_id}', json={
            'label': 'Hacked'
        }, headers=self.headers_b)
        self.assertEqual(put_res.status_code, 404)

        # User B cannot delete User A's slot
        del_res = self.client.delete(f'/api/period-slots/{slot_a_id}', headers=self.headers_b)
        self.assertEqual(del_res.status_code, 404)

    def test_reset_defaults(self):
        # Delete all slots for user A
        slots = self.client.get('/api/period-slots', headers=self.headers_a).get_json()
        for s in slots:
            self.client.delete(f'/api/period-slots/{s["id"]}', headers=self.headers_a)

        empty_slots = self.client.get('/api/period-slots', headers=self.headers_a).get_json()
        self.assertEqual(len(empty_slots), 0)

        # Reset to defaults
        reset_res = self.client.post('/api/period-slots/reset-defaults', headers=self.headers_a)
        self.assertEqual(reset_res.status_code, 200)
        self.assertEqual(len(reset_res.get_json()['slots']), 6)

if __name__ == '__main__':
    unittest.main()
