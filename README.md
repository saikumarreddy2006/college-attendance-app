# AcademiaTrack - Production-Quality College Attendance Management Web App

AcademiaTrack is a modern, responsive full-stack web application designed for college students to effortlessly track, analyze, predict, and export attendance records.

---

## 🌟 Core Features

1. **Intelligent Dashboard**:
   - Visual percentage indicator (dynamic SVG ring gauge with status color transitions).
   - Key KPIs: Classes Attended, Classes Absent, Total Conducted.
   - Status Badges: **Good** ($\ge$ warning threshold), **Warning** (between critical and warning), and **Critical** ($<$ critical threshold).
   - Smart Alert Banner highlighting subjects requiring immediate attention.
   - Safe-to-miss indicator & Catch-up required notification.
   - Today's Quick Summary widget with unmarked count.
   - Dual view for subjects: Interactive Cards and Detailed Table.

2. **Daily Attendance ("Today's Classes")**:
   - Automatically synchronizes with today's timetable based on the active day of the week.
   - Date Navigator: Jump to Today, Previous Day, Next Day, or pick any custom date.
   - One-click attendance marking: `[Present]` (Emerald), `[Absent]` (Rose), and `[↺ Unmark]`.
   - Batch operations: `Mark All Present`, `Mark All Absent`, and `Clear All`.
   - Immediate recalculation across all statistics and dashboard widgets.

3. **Weekly Timetable Management**:
   - Monday through Saturday schedule support.
   - Add, edit, and delete periods with custom timings, faculty, room/lab, and color tags.
   - Period reordering (Move Up / Move Down).
   - Day duplication (e.g., duplicate Monday's routine to Wednesday).
   - Clear individual day timetables with confirmation safety.

4. **Attendance History / Logs**:
   - Comprehensive tabular log view with status badges.
   - Multi-parameter filtering: Date Range (From/To), Subject, Status (Present/Absent).
   - Sorting by Date (Asc/Desc) and Period Number.
   - Inline status toggle and record deletion.
   - Live summary stats of filtered records.

5. **Custom Date Range Attendance Analysis**:
   - Dedicated date boundary analyzer.
   - Quick presets: "This Week", "This Month", "Last 30 Days", "Semester to Date".
   - Calculates attendance percentage, attended, and absent counts **strictly within the specified range**.
   - Subject-wise breakdown table for the selected range.
   - Attended vs Absent comparison stacked bar chart.
   - One-click range export to Excel.

6. **Subject Details & Attendance Calculator**:
   - Detailed modal displaying subject history, monthly distribution, and metadata.
   - **Interactive Calculator**:
     - Configurable target slider (50% to 100%).
     - **Safe-to-Miss Calculation**: $\max\left(0, \lfloor \frac{A}{r} - T \rfloor\right)$
     - **Catch-up Required Calculation**: $\max\left(0, \lceil \frac{rT - A}{1 - r} \rceil\right)$
     - Edge-case handling: detects mathematically impossible 100% targets if any class was missed.
   - **What-if Simulator**:
     - Enter upcoming classes attended ($X$) and missed ($Y$).
     - Real-time projected percentage with delta badge (+/- change).

7. **Monthly Analytics**:
   - Attendance percentage trend line chart.
   - Monthly Attended vs Absent bar chart.
   - Subject distribution horizontal bar chart with color-coded threshold status.
   - Monthly summary table.

8. **Interactive Monthly Calendar View**:
   - Monthly navigation (Previous / Next / Today).
   - Visual day indicators: Green (100% Present), Amber/Yellow (Partial), Red (Absent), Gray (No Classes).
   - Click any date to open the day's attendance sheet directly.

9. **Professional Excel Export (.xlsx)**:
   - Generated using `openpyxl` with styled headers, custom palette, auto-adjusted column widths, and borders.
   - Sheet 1: **Summary Report** (Overall KPIs, Thresholds, and Subject breakdown with percentages).
   - Sheet 2: **Detailed Records** (Date, Day, Period, Start/End Time, Subject Name, Faculty, Room, Status, Notes).
   - Configurable export scopes: Complete History, Date Range, or Individual Subject.

10. **Data Safety & Backup / Restore**:
    - Complete JSON backup export and import with structural validation.
    - Sample dataset generator (6 CS subjects, weekly timetable, and 30-day attendance history).
    - Clear attendance logs (preserves timetable and subjects).
11. **User Authentication & Cloud Data Sync**:
    - Complete Auth Flow: Sign up, Login, Logout, Forgot Password, and Reset Password.
    - Multi-Tenant Isolation: Every entity (`subjects`, `timetable`, `attendance`, `settings`) is strictly bound to `user_id`. User A can never view, mutate, or delete User B's records.
    - Multi-Device Synchronization: Mark attendance on laptop, immediately log in on phone or tablet to see live synced data.
    - Offline Resilience & Queue: When offline, actions are queued safely in local storage and synced automatically upon reconnection.
    - Data Migration: Automatically detects pre-existing unassigned browser data and prompts the user to import to their cloud account or start fresh.
    - Supabase PostgreSQL Architecture: Fully prepared cloud deployment schema (`supabase_schema.sql`) with strict PostgreSQL Row Level Security (RLS) policies and automatic profile triggers.

---

## 🛠️ Architecture & Tech Stack

- **Backend**: Python 3.13 + Flask 3.1 + SQLite3 (multi-tenant) + openpyxl + Werkzeug Security
- **Cloud DB / Supabase**: PostgreSQL with Row-Level Security (`supabase_schema.sql`)
- **Frontend**: Responsive Single-Page Application (HTML5, Tailwind CSS via CDN, Lucide Icons, Chart.js)
- **Authentication**: Token-based multi-device persistent sessions with secure hashing (scrypt / pbkdf2)
- **Database Schema**:
  - `users` (`id`, `name`, `email`, `password_hash`, `avatar_url`, `created_at`)
  - `user_sessions` (`id`, `user_id`, `token`, `expires_at`)
  - `password_resets` (`id`, `user_id`, `token`, `expires_at`, `used`)
  - `subjects` (`id`, `user_id`, `name`, `code`, `faculty`, `room`, `color`)
  - `timetable` (`id`, `user_id`, `day`, `period_number`, `start_time`, `end_time`, `subject_id`, `room`, `faculty`)
  - `attendance` (`id`, `user_id`, `date`, `period_id`, `subject_id`, `status`, `notes`)
  - `settings` (`id`, `user_id`, `required_attendance`, `warning_threshold`, `critical_threshold`, `theme`, `college_name`, `student_name`)

---

## 🚀 Running the Application

### 1. Start the Flask Server
```powershell
python app.py
```
The application will be live at:
```
http://127.0.0.1:5000/
```

### 2. Run Test Suite
```powershell
python -m unittest discover tests
```
All 23 unit calculation, multi-user cloud isolation, offline queue synchronization, and end-to-end integration tests will run and report status.
