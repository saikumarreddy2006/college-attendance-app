import unittest
import json
from io import BytesIO
import openpyxl
from datetime import date, timedelta
import app as flask_app

class TestEndToEndFlows(unittest.TestCase):
    def setUp(self):
        import os
        flask_app.app.config['TESTING'] = True
        flask_app.app.config['DATABASE'] = os.path.join(os.path.dirname(__file__), 'test_e2e.db')
        self.client = flask_app.app.test_client()
        with flask_app.app.app_context():
            flask_app.init_db()
        reg = self.client.post('/api/auth/signup', json={
            'name': 'E2E User',
            'email': 'e2e@college.edu',
            'password': 'Password123!',
            'confirm_password': 'Password123!'
        })
        if reg.status_code == 201:
            self.token = reg.get_json()['token']
        else:
            login = self.client.post('/api/auth/login', json={
                'email': 'e2e@college.edu',
                'password': 'Password123!'
            })
            self.token = login.get_json()['token']
        self.headers = {'Authorization': f'Bearer {self.token}'}

    def tearDown(self):
        import os
        db_path = os.path.join(os.path.dirname(__file__), 'test_e2e.db')
        if os.path.exists(db_path):
            try:
                os.remove(db_path)
            except Exception:
                pass

    def test_flow_1_create_subjects_timetable_mark_today_verify_dashboard(self):
        # 1. Reset all data
        res = self.client.post('/api/backup/reset-all', headers=self.headers)
        self.assertEqual(res.status_code, 200)

        # 2. Create subject
        sub_res = self.client.post('/api/subjects', json={
            'name': 'Operating Systems',
            'code': 'CS303',
            'faculty': 'Dr. Alan Turing',
            'room': 'Room 305',
            'color': '#8B5CF6'
        }, headers=self.headers)
        self.assertEqual(sub_res.status_code, 201)
        sub_id = sub_res.get_json()['id']

        # 3. Create timetable period for Thursday (today)
        today_date = date.today().isoformat()
        today_day = date.today().strftime('%A')

        tt_res = self.client.post('/api/timetable', json={
            'day': today_day,
            'period_number': 1,
            'start_time': '09:00',
            'end_time': '09:50',
            'subject_id': sub_id,
            'room': 'Room 305',
            'faculty': 'Dr. Alan Turing'
        }, headers=self.headers)
        self.assertEqual(tt_res.status_code, 201)
        period_id = tt_res.get_json()['id']

        # 4. Mark today's attendance as Present
        att_res = self.client.post('/api/attendance', json={
            'date': today_date,
            'period_id': period_id,
            'subject_id': sub_id,
            'status': 'Present'
        }, headers=self.headers)
        self.assertEqual(att_res.status_code, 201)

        # 5. Verify Dashboard summary
        sum_res = self.client.get('/api/attendance/summary', headers=self.headers)
        self.assertEqual(sum_res.status_code, 200)
        data = sum_res.get_json()
        self.assertEqual(data['overall']['total'], 1)
        self.assertEqual(data['overall']['attended'], 1)
        self.assertEqual(data['overall']['percentage'], 100.0)
        self.assertEqual(data['overall']['status_badge'], 'Good')
        self.assertEqual(data['subjects'][0]['name'], 'Operating Systems')
        self.assertEqual(data['subjects'][0]['percentage'], 100.0)

    def test_flow_2_and_3_present_and_absent_percentage_adjustments(self):
        # Reset and seed initial subject
        self.client.post('/api/backup/reset-all', headers=self.headers)
        sub = self.client.post('/api/subjects', json={
            'name': 'Mathematics',
            'code': 'MA301'
        }, headers=self.headers).get_json()
        sid = sub['id']

        # Add 3 Present records -> 3/3 = 100%
        for i in range(1, 4):
            d = (date.today() - timedelta(days=i)).isoformat()
            self.client.post('/api/attendance', json={
                'date': d, 'subject_id': sid, 'status': 'Present'
            }, headers=self.headers)
        
        sum1 = self.client.get(f'/api/subjects/{sid}', headers=self.headers).get_json()
        self.assertEqual(sum1['attended'], 3)
        self.assertEqual(sum1['total'], 3)
        self.assertEqual(sum1['percentage'], 100.0)

        # Flow 3: Mark Absent -> 3 attended / 4 total = 75.0%
        d4 = (date.today() - timedelta(days=4)).isoformat()
        self.client.post('/api/attendance', json={
            'date': d4, 'subject_id': sid, 'status': 'Absent'
        }, headers=self.headers)
        sum2 = self.client.get(f'/api/subjects/{sid}', headers=self.headers).get_json()
        self.assertEqual(sum2['attended'], 3)
        self.assertEqual(sum2['absent'], 1)
        self.assertEqual(sum2['total'], 4)
        self.assertEqual(sum2['percentage'], 75.0)

        # Another Absent -> 3 attended / 5 total = 60.0% (< 65% -> Critical)
        d5 = (date.today() - timedelta(days=5)).isoformat()
        self.client.post('/api/attendance', json={
            'date': d5, 'subject_id': sid, 'status': 'Absent'
        }, headers=self.headers)
        sum3 = self.client.get(f'/api/subjects/{sid}', headers=self.headers).get_json()
        self.assertEqual(sum3['attended'], 3)
        self.assertEqual(sum3['total'], 5)
        self.assertEqual(sum3['percentage'], 60.0)
        self.assertEqual(sum3['status_badge'], 'Critical')

        # Flow 2: Mark 5 consecutive Presents -> (3+5) / (5+5) = 8/10 = 80.0%
        for i in range(6, 11):
            d = (date.today() - timedelta(days=i)).isoformat()
            self.client.post('/api/attendance', json={
                'date': d, 'subject_id': sid, 'status': 'Present'
            }, headers=self.headers)
        sum4 = self.client.get(f'/api/subjects/{sid}', headers=self.headers).get_json()
        self.assertEqual(sum4['attended'], 8)
        self.assertEqual(sum4['total'], 10)
        self.assertEqual(sum4['percentage'], 80.0)
        self.assertEqual(sum4['status_badge'], 'Good')

    def test_flow_4_custom_date_range_filtering(self):
        # Reset and seed full sample dataset
        self.client.post('/api/backup/seed', headers=self.headers)
        
        # Test range strictly within a 5-day window
        start = (date.today() - timedelta(days=10)).isoformat()
        end = (date.today() - timedelta(days=5)).isoformat()

        res = self.client.get(f'/api/attendance/summary?from_date={start}&to_date={end}', headers=self.headers)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        
        # All records returned by attendance query for this range must be >= start and <= end
        records = self.client.get(f'/api/attendance?from_date={start}&to_date={end}', headers=self.headers).get_json()
        for r in records:
            self.assertGreaterEqual(r['date'], start)
            self.assertLessEqual(r['date'], end)

    def test_flow_5_subject_specific_statistics_and_calculator(self):
        self.client.post('/api/backup/seed', headers=self.headers)
        subjects = self.client.get('/api/subjects', headers=self.headers).get_json()
        self.assertGreater(len(subjects), 0)
        sub_id = subjects[0]['id']

        sub_details = self.client.get(f'/api/subjects/{sub_id}', headers=self.headers).get_json()
        self.assertIn('monthly', sub_details)
        self.assertIn('history', sub_details)
        self.assertIn('can_miss', sub_details)
        self.assertIn('need_to_attend', sub_details)

    def test_flow_6_change_required_attendance_threshold(self):
        # Change required attendance from 75% to 80%
        set_res = self.client.post('/api/settings', json={
            'required_attendance': 80.0,
            'warning_threshold': 80.0,
            'critical_threshold': 70.0
        }, headers=self.headers)
        self.assertEqual(set_res.status_code, 200)
        settings = set_res.get_json()['settings']
        self.assertEqual(settings['required_attendance'], 80.0)

        # Summary should reflect updated settings
        summary = self.client.get('/api/attendance/summary', headers=self.headers).get_json()
        self.assertEqual(summary['settings']['required_attendance'], 80.0)

    def test_flow_7_excel_export_and_content_verification(self):
        self.client.post('/api/backup/seed', headers=self.headers)
        subs = self.client.get('/api/subjects', headers=self.headers).get_json()
        target_sub = subs[0]
        sub_id = target_sub['id']
        sub_name = target_sub['name']

        # 1. Scope: Complete Attendance
        res_all = self.client.get('/api/export/excel?scope=all', headers=self.headers)
        self.assertEqual(res_all.status_code, 200)
        wb_all = openpyxl.load_workbook(BytesIO(res_all.data))
        self.assertIn('Summary Report', wb_all.sheetnames)
        self.assertIn('Detailed Records', wb_all.sheetnames)
        self.assertGreater(wb_all['Detailed Records'].max_row, 5)

        # 2. Scope: Individual Subject (MUST ONLY contain that subject's records)
        res_sub = self.client.get(f'/api/export/excel?scope=subject&subject_id={sub_id}', headers=self.headers)
        self.assertEqual(res_sub.status_code, 200)
        self.assertIn(f"Attendance_{target_sub['code']}", res_sub.headers.get('Content-Disposition', ''))
        wb_sub = openpyxl.load_workbook(BytesIO(res_sub.data))
        ws_sub_detail = wb_sub['Detailed Records']
        # Verify every row in column G is strictly the target subject
        for r in range(2, ws_sub_detail.max_row + 1):
            self.assertEqual(ws_sub_detail.cell(row=r, column=7).value, sub_name)
        # Verify Summary report table has exactly 1 subject row
        ws_sub_summary = wb_sub['Summary Report']
        self.assertEqual(ws_sub_summary.cell(row=16, column=2).value, sub_name)
        self.assertIsNone(ws_sub_summary.cell(row=17, column=2).value)

        # 3. Scope: Date Range (MUST ONLY contain records within that date range)
        start_d = (date.today() - timedelta(days=5)).isoformat()
        end_d = date.today().isoformat()
        res_range = self.client.get(f'/api/export/excel?scope=range&from_date={start_d}&to_date={end_d}', headers=self.headers)
        self.assertEqual(res_range.status_code, 200)
        wb_range = openpyxl.load_workbook(BytesIO(res_range.data))
        ws_range_detail = wb_range['Detailed Records']
        for r in range(2, ws_range_detail.max_row + 1):
            row_date = str(ws_range_detail.cell(row=r, column=1).value)
            self.assertGreaterEqual(row_date, start_d)
            self.assertLessEqual(row_date, end_d)

    def test_flow_8_and_9_persistence_and_backup_import(self):
        self.client.post('/api/backup/seed', headers=self.headers)
        # 1. Export backup
        backup = self.client.get('/api/backup/export', headers=self.headers).get_json()
        self.assertGreater(len(backup['subjects']), 0)
        self.assertGreater(len(backup['attendance']), 0)

        # 2. Clear attendance
        self.client.post('/api/backup/clear-attendance', headers=self.headers)
        cleared_sum = self.client.get('/api/attendance/summary', headers=self.headers).get_json()
        self.assertEqual(cleared_sum['overall']['total'], 0)

        # 3. Restore backup
        restore_res = self.client.post('/api/backup/import', json=backup, headers=self.headers)
        self.assertEqual(restore_res.status_code, 200)
        
        restored_sum = self.client.get('/api/attendance/summary', headers=self.headers).get_json()
        self.assertEqual(restored_sum['overall']['total'], len(backup['attendance']))

    def test_export_monthly_analytics_excel(self):
        # Seed test data
        self.client.post('/api/backup/seed', headers=self.headers)
        
        # Test dedicated Monthly Analytics export
        res = self.client.get('/api/export/analytics', headers=self.headers)
        self.assertEqual(res.status_code, 200)
        self.assertIn('Monthly_Analytics_Report', res.headers.get('Content-Disposition', ''))
        
        wb = openpyxl.load_workbook(BytesIO(res.data))
        self.assertIn('Monthly Trends & KPIs', wb.sheetnames)
        self.assertIn('Subject Performance', wb.sheetnames)
        self.assertIn('Subject Monthly Matrix', wb.sheetnames)
        
        ws_trends = wb['Monthly Trends & KPIs']
        self.assertGreater(ws_trends.max_row, 15)
        
        ws_matrix = wb['Subject Monthly Matrix']
        self.assertGreater(ws_matrix.max_row, 4)
        self.assertGreater(ws_matrix.max_column, 2)

    def test_export_logs_filtered_excel(self):
        # Seed test data
        self.client.post('/api/backup/seed', headers=self.headers)
        
        # Test dedicated Filtered Attendance Logs export with status='Absent'
        res = self.client.get('/api/export/logs?status=Absent', headers=self.headers)
        self.assertEqual(res.status_code, 200)
        self.assertIn('Attendance_Logs', res.headers.get('Content-Disposition', ''))
        
        wb = openpyxl.load_workbook(BytesIO(res.data))
        self.assertIn('Attendance Logs', wb.sheetnames)
        self.assertIn('Log Summary', wb.sheetnames)
        
        ws_logs = wb['Attendance Logs']
        # Header is row 4, records start row 5
        self.assertGreaterEqual(ws_logs.max_row, 5)
        # All filtered rows must be strictly Absent
        for r in range(5, ws_logs.max_row + 1):
            status_val = ws_logs.cell(row=r, column=11).value
            self.assertEqual(status_val, 'Absent')
            
        ws_summary = wb['Log Summary']
        # Check absent count metric
        self.assertGreater(ws_summary.max_row, 5)

    def test_delete_saved_period(self):
        # 1. Create a subject
        sub_res = self.client.post('/api/subjects', json={
            'name': 'Cloud Computing',
            'code': 'CS401'
        }, headers=self.headers)
        sub_id = sub_res.get_json()['id']
        
        # 2. Create period
        p_res = self.client.post('/api/timetable', json={
            'day': 'Friday',
            'period_number': 3,
            'start_time': '11:00',
            'end_time': '11:50',
            'subject_id': sub_id,
            'room': 'Lab 2',
            'faculty': 'Prof. Davis'
        }, headers=self.headers)
        period_id = p_res.get_json()['id']
        
        # 3. Confirm period exists in Friday timetable
        tt_friday = self.client.get('/api/timetable?day=Friday', headers=self.headers).get_json()
        self.assertTrue(any(p['id'] == period_id for p in tt_friday))
        
        # 4. Delete saved period
        del_res = self.client.delete(f'/api/timetable/{period_id}', headers=self.headers)
        self.assertEqual(del_res.status_code, 200)
        self.assertTrue(del_res.get_json()['success'])
        
        # 5. Confirm period is gone from timetable
        tt_friday_after = self.client.get('/api/timetable?day=Friday', headers=self.headers).get_json()
        self.assertFalse(any(p['id'] == period_id for p in tt_friday_after))

if __name__ == '__main__':
    unittest.main()
