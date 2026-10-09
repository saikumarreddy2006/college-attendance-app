/**
 * REST API Client with Multi-Device Auth, Offline Queue, and Cloud Sync
 */

export const API = {
    getToken() {
        return localStorage.getItem('auth_token') || '';
    },
    setToken(token) {
        if (token) {
            localStorage.setItem('auth_token', token);
        } else {
            localStorage.removeItem('auth_token');
        }
    },
    getUser() {
        try {
            return JSON.parse(localStorage.getItem('auth_user') || 'null');
        } catch {
            return null;
        }
    },
    setUser(user) {
        if (user) {
            localStorage.setItem('auth_user', JSON.stringify(user));
        } else {
            localStorage.removeItem('auth_user');
        }
    },

    async request(url, options = {}) {
        const token = this.getToken();
        const headers = {
            'Content-Type': 'application/json',
            ...(options.headers || {})
        };
        if (token) {
            headers['Authorization'] = `Bearer ${token}`;
        }

        try {
            const res = await fetch(url, {
                ...options,
                headers
            });

            if (res.status === 401) {
                // If unauthenticated on a protected route
                if (!url.startsWith('/api/auth/login') && !url.startsWith('/api/auth/signup') && !url.startsWith('/api/auth/me')) {
                    this.setToken(null);
                    this.setUser(null);
                    if (window.appShowAuthModal) {
                        window.appShowAuthModal('login', 'Your session has expired. Please log in.');
                    }
                }
                const errorData = await res.json().catch(() => ({}));
                throw new Error(errorData.error || 'Authentication required');
            }

            if (!res.ok) {
                const errorData = await res.json().catch(() => ({}));
                throw new Error(errorData.error || `HTTP error ${res.status}`);
            }

            const contentType = res.headers.get('content-type');
            if (contentType && contentType.includes('application/json')) {
                return await res.json();
            }
            return res;
        } catch (err) {
            // Check for network offline failure
            if (!navigator.onLine || err.message === 'Failed to fetch' || err.name === 'TypeError') {
                err.isOffline = true;
            }
            throw err;
        }
    },

    // --- Authentication ---
    async signup(name, email, password, confirmPassword) {
        const res = await this.request('/api/auth/signup', {
            method: 'POST',
            body: JSON.stringify({
                name,
                email,
                password,
                confirm_password: confirmPassword
            })
        });
        if (res.token) {
            this.setToken(res.token);
            this.setUser(res.user);
        }
        return res;
    },

    async login(email, password) {
        const res = await this.request('/api/auth/login', {
            method: 'POST',
            body: JSON.stringify({ email, password })
        });
        if (res.token) {
            this.setToken(res.token);
            this.setUser(res.user);
        }
        return res;
    },

    async logout() {
        try {
            await this.request('/api/auth/logout', { method: 'POST' });
        } catch (e) {
            // Ignore logout network errors
        } finally {
            this.setToken(null);
            this.setUser(null);
        }
        return { success: true };
    },

    async getMe() {
        return this.request('/api/auth/me');
    },

    async forgotPassword(email) {
        return this.request('/api/auth/forgot-password', {
            method: 'POST',
            body: JSON.stringify({ email })
        });
    },

    async resetPassword(token, newPassword, confirmPassword) {
        return this.request('/api/auth/reset-password', {
            method: 'POST',
            body: JSON.stringify({
                token,
                new_password: newPassword,
                confirm_password: confirmPassword
            })
        });
    },

    async migrateLocal(importExisting = true, localSubjects = []) {
        return this.request('/api/auth/migrate-local', {
            method: 'POST',
            body: JSON.stringify({
                import_existing: importExisting,
                subjects: localSubjects
            })
        });
    },

    // --- Offline Queue Handling ---
    getOfflineQueue() {
        try {
            return JSON.parse(localStorage.getItem('attendance_offline_queue') || '[]');
        } catch {
            return [];
        }
    },
    saveOfflineQueue(queue) {
        localStorage.setItem('attendance_offline_queue', JSON.stringify(queue));
    },
    queueOfflineAction(action) {
        const queue = this.getOfflineQueue();
        queue.push({ ...action, timestamp: new Date().toISOString() });
        this.saveOfflineQueue(queue);
    },
    async flushOfflineQueue() {
        const queue = this.getOfflineQueue();
        if (queue.length === 0) return 0;
        try {
            const res = await this.request('/api/attendance/sync-offline', {
                method: 'POST',
                body: JSON.stringify({ actions: queue })
            });
            this.saveOfflineQueue([]);
            return res.synced_count || queue.length;
        } catch (e) {
            console.warn("Failed to flush offline queue:", e);
            return 0;
        }
    },

    // --- Settings ---
    getSettings() {
        return this.request('/api/settings');
    },
    saveSettings(settings) {
        return this.request('/api/settings', {
            method: 'POST',
            body: JSON.stringify(settings)
        });
    },

    // --- Subjects ---
    getSubjects() {
        return this.request('/api/subjects');
    },
    getSubjectDetails(id) {
        return this.request(`/api/subjects/${id}`);
    },
    createSubject(subject) {
        return this.request('/api/subjects', {
            method: 'POST',
            body: JSON.stringify(subject)
        });
    },
    updateSubject(id, subject) {
        return this.request(`/api/subjects/${id}`, {
            method: 'PUT',
            body: JSON.stringify(subject)
        });
    },
    deleteSubject(id) {
        return this.request(`/api/subjects/${id}`, {
            method: 'DELETE'
        });
    },

    // --- Timetable ---
    getTimetable(day = null) {
        const url = day ? `/api/timetable?day=${encodeURIComponent(day)}` : '/api/timetable';
        return this.request(url);
    },
    addTimetablePeriod(period) {
        return this.request('/api/timetable', {
            method: 'POST',
            body: JSON.stringify(period)
        });
    },
    updateTimetablePeriod(id, period) {
        return this.request(`/api/timetable/${id}`, {
            method: 'PUT',
            body: JSON.stringify(period)
        });
    },
    deleteTimetablePeriod(id) {
        return this.request(`/api/timetable/${id}`, {
            method: 'DELETE'
        });
    },
    reorderTimetable(orderedIds) {
        return this.request('/api/timetable/reorder', {
            method: 'POST',
            body: JSON.stringify({ ordered_ids: orderedIds })
        });
    },
    duplicateDay(sourceDay, targetDays, replaceTarget = true) {
        const payload = {
            source_day: sourceDay,
            replace_target: replaceTarget
        };
        if (Array.isArray(targetDays)) {
            payload.target_days = targetDays;
            payload.target_day = targetDays[0] || '';
        } else {
            payload.target_day = targetDays;
            payload.target_days = [targetDays];
        }
        return this.request('/api/timetable/duplicate', {
            method: 'POST',
            body: JSON.stringify(payload)
        });
    },
    clearTimetableDay(day) {
        return this.request('/api/timetable/clear-day', {
            method: 'POST',
            body: JSON.stringify({ day })
        });
    },

    // --- Period Slots (Master Schedule Periods) ---
    getPeriodSlots() {
        return this.request('/api/period-slots');
    },
    addPeriodSlot(data) {
        return this.request('/api/period-slots', {
            method: 'POST',
            body: JSON.stringify(data)
        });
    },
    updatePeriodSlot(id, data) {
        return this.request(`/api/period-slots/${id}`, {
            method: 'PUT',
            body: JSON.stringify(data)
        });
    },
    deletePeriodSlot(id) {
        return this.request(`/api/period-slots/${id}`, {
            method: 'DELETE'
        });
    },
    resetPeriodSlots() {
        return this.request('/api/period-slots/reset-defaults', {
            method: 'POST'
        });
    },

    // --- Attendance ---
    getAttendance(filters = {}) {
        const params = new URLSearchParams();
        if (filters.date) params.append('date', filters.date);
        if (filters.from_date) params.append('from_date', filters.from_date);
        if (filters.to_date) params.append('to_date', filters.to_date);
        if (filters.subject_id) params.append('subject_id', filters.subject_id);
        if (filters.status) params.append('status', filters.status);
        if (filters.sort) params.append('sort', filters.sort);
        if (filters.order) params.append('order', filters.order);

        const qs = params.toString();
        return this.request(`/api/attendance${qs ? '?' + qs : ''}`);
    },
    async markAttendance(date, periodId, subjectId, status, notes = '') {
        try {
            return await this.request('/api/attendance', {
                method: 'POST',
                body: JSON.stringify({
                    date,
                    period_id: periodId,
                    subject_id: subjectId,
                    status,
                    notes
                })
            });
        } catch (err) {
            if (err.isOffline) {
                // Queue for later sync
                this.queueOfflineAction({ date, period_id: periodId, subject_id: subjectId, status, notes });
                return { action: 'queued_offline', status };
            }
            throw err;
        }
    },
    unmarkAttendance(date, periodId) {
        return this.request('/api/attendance/unmark', {
            method: 'POST',
            body: JSON.stringify({ date, period_id: periodId })
        });
    },
    deleteAttendanceRecord(id) {
        return this.request(`/api/attendance/${id}`, {
            method: 'DELETE'
        });
    },
    updateAttendanceRecord(id, status, notes = '') {
        return this.request(`/api/attendance/${id}`, {
            method: 'PUT',
            body: JSON.stringify({ status, notes })
        });
    },

    // --- Holidays ---
    getHolidays(filters = {}) {
        const params = new URLSearchParams();
        if (filters.month) params.append('month', filters.month);
        if (filters.date) params.append('date', filters.date);
        if (filters.from_date) params.append('from_date', filters.from_date);
        if (filters.to_date) params.append('to_date', filters.to_date);
        const qs = params.toString();
        return this.request(`/api/holidays${qs ? '?' + qs : ''}`);
    },
    markHoliday(date, name = '') {
        return this.request('/api/holidays', {
            method: 'POST',
            body: JSON.stringify({ date, name })
        });
    },
    unmarkHoliday(date) {
        return this.request('/api/holidays/unmark', {
            method: 'POST',
            body: JSON.stringify({ date })
        });
    },
    deleteHoliday(id) {
        return this.request('/api/holidays', {
            method: 'DELETE',
            body: JSON.stringify({ id })
        });
    },

    // Today's schedule
    getTodayAttendance(dateStr) {
        const url = dateStr ? `/api/attendance/today?date=${encodeURIComponent(dateStr)}` : '/api/attendance/today';
        return this.request(url);
    },

    // Summary
    getSummary(fromDate = null, toDate = null) {
        const params = new URLSearchParams();
        if (fromDate) params.append('from_date', fromDate);
        if (toDate) params.append('to_date', toDate);
        const qs = params.toString();
        return this.request(`/api/attendance/summary${qs ? '?' + qs : ''}`);
    },

    // Analytics
    getMonthlyAnalytics() {
        return this.request('/api/attendance/monthly');
    },
    getCalendarData(monthStr) {
        const url = monthStr ? `/api/attendance/calendar?month=${encodeURIComponent(monthStr)}` : '/api/attendance/calendar';
        return this.request(url);
    },

    getExcelExportUrl(scope = 'all', options = {}) {
        const params = new URLSearchParams();
        params.append('scope', scope);
        if (options.from_date) params.append('from_date', options.from_date);
        if (options.to_date) params.append('to_date', options.to_date);
        if (options.subject_id) params.append('subject_id', options.subject_id);
        const token = this.getToken();
        if (token) params.append('token', token);
        return `/api/export/excel?${params.toString()}`;
    },

    getAnalyticsExportUrl() {
        const params = new URLSearchParams();
        const token = this.getToken();
        if (token) params.append('token', token);
        const qs = params.toString();
        return `/api/export/analytics${qs ? '?' + qs : ''}`;
    },

    getLogsExportUrl(filters = {}) {
        const params = new URLSearchParams();
        if (filters.from_date) params.append('from_date', filters.from_date);
        if (filters.to_date) params.append('to_date', filters.to_date);
        if (filters.subject_id) params.append('subject_id', filters.subject_id);
        if (filters.status) params.append('status', filters.status);
        if (filters.sort) params.append('sort', filters.sort);
        if (filters.order) params.append('order', filters.order);
        const token = this.getToken();
        if (token) params.append('token', token);
        const qs = params.toString();
        return `/api/export/logs${qs ? '?' + qs : ''}`;
    },

    // Backup & Restore
    exportBackup() {
        return this.request('/api/backup/export');
    },
    importBackup(backupData) {
        return this.request('/api/backup/import', {
            method: 'POST',
            body: JSON.stringify(backupData)
        });
    },
    clearAttendance() {
        return this.request('/api/backup/clear-attendance', {
            method: 'POST'
        });
    },
    resetAll() {
        return this.request('/api/backup/reset-all', {
            method: 'POST'
        });
    }
};
