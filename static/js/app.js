import { API } from './api.js';
import { AttendanceCalculator } from './calculator.js';

// Global application state
const state = {
    settings: {
        required_attendance: 75.0,
        warning_threshold: 75.0,
        critical_threshold: 65.0,
        theme: 'system',
        college_name: 'College of Engineering & Technology',
        student_name: 'Student'
    },
    subjects: [],
    timetable: [],
    periodSlots: [],
    currentView: 'dashboard',
    todayDate: new Date().toISOString().split('T')[0],
    selectedSubject: null,
    timetableSelectedDay: 'Monday',
    charts: {
        analyticsTrend: null,
        analyticsMonthly: null,
        analyticsSubjects: null,
        rangeChart: null
    },
    calendarMonth: new Date().toISOString().slice(0, 7) // YYYY-MM
};

// --- Toast System ---
export function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    const colors = {
        success: 'bg-emerald-600 text-white',
        error: 'bg-rose-600 text-white',
        warning: 'bg-amber-600 text-white',
        info: 'bg-indigo-600 text-white'
    };
    const icons = {
        success: 'check-circle',
        error: 'alert-circle',
        warning: 'alert-triangle',
        info: 'info'
    };

    toast.className = `toast flex items-center gap-3 px-4 py-3 rounded-xl shadow-lg text-sm font-medium ${colors[type] || colors.info}`;
    toast.innerHTML = `
        <i data-lucide="${icons[type] || 'info'}" class="w-5 h-5 flex-shrink-0"></i>
        <span>${message}</span>
        <button class="ml-auto p-1 hover:opacity-75 transition" onclick="this.parentElement.remove()">
            <i data-lucide="x" class="w-4 h-4"></i>
        </button>
    `;
    container.appendChild(toast);
    if (window.lucide) window.lucide.createIcons();

    setTimeout(() => {
        if (toast.parentElement) {
            toast.style.opacity = '0';
            toast.style.transform = 'translateY(10px)';
            toast.style.transition = 'all 0.2s ease';
            setTimeout(() => toast.remove(), 200);
        }
    }, 3500);
}

// --- Confirmation Dialog ---
export function confirmAction(title, message, confirmBtnText = 'Confirm', isDanger = false) {
    return new Promise((resolve) => {
        const modal = document.getElementById('modal-confirm');
        const titleEl = document.getElementById('confirm-title');
        const msgEl = document.getElementById('confirm-message');
        const btnConfirm = document.getElementById('confirm-btn-yes');
        const btnCancel = document.getElementById('confirm-btn-no');

        titleEl.textContent = title;
        msgEl.textContent = message;
        btnConfirm.textContent = confirmBtnText;

        if (isDanger) {
            btnConfirm.className = 'px-4 py-2 rounded-xl text-sm font-medium bg-rose-600 hover:bg-rose-700 text-white transition';
        } else {
            btnConfirm.className = 'px-4 py-2 rounded-xl text-sm font-medium bg-indigo-600 hover:bg-indigo-700 text-white transition';
        }

        modal.classList.remove('hidden');

        const cleanup = (result) => {
            modal.classList.add('hidden');
            btnConfirm.removeEventListener('click', onYes);
            btnCancel.removeEventListener('click', onNo);
            resolve(result);
        };

        const onYes = () => cleanup(true);
        const onNo = () => cleanup(false);

        btnConfirm.addEventListener('click', onYes);
        btnCancel.addEventListener('click', onNo);
    });
}

// --- Theme Management ---
function applyTheme(theme) {
    const html = document.documentElement;
    if (theme === 'dark' || (theme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
        html.classList.add('dark');
    } else {
        html.classList.remove('dark');
    }
}

// --- View Router ---
export function switchView(viewName) {
    if (!state.isAuthenticated && viewName !== 'auth') {
        viewName = 'auth';
    }

    state.currentView = viewName;
    document.querySelectorAll('.view-panel').forEach(el => el.classList.add('hidden'));
    const target = document.getElementById(`view-${viewName}`);
    if (target) {
        target.classList.remove('hidden');
    }

    // Toggle navigation UI visibility based on auth
    const sidebar = document.querySelector('aside');
    const mobileNav = document.querySelector('nav.md\\:hidden');
    const userContainer = document.getElementById('user-profile-container');
    const cloudPill = document.getElementById('cloud-sync-pill');

    if (viewName === 'auth') {
        if (sidebar) sidebar.classList.add('hidden');
        if (mobileNav) mobileNav.classList.add('hidden');
        if (userContainer) userContainer.classList.add('hidden');
        if (cloudPill) cloudPill.classList.add('hidden');
        return;
    } else {
        if (sidebar) sidebar.classList.remove('hidden');
        if (mobileNav) mobileNav.classList.remove('hidden');
        if (userContainer) userContainer.classList.remove('hidden');
        if (cloudPill) cloudPill.classList.remove('hidden');
    }

    // Update navigation active states
    document.querySelectorAll('[data-view-nav]').forEach(btn => {
        const v = btn.getAttribute('data-view-nav');
        if (v === viewName) {
            btn.classList.add('bg-indigo-50', 'dark:bg-indigo-950/60', 'text-indigo-600', 'dark:text-indigo-400', 'font-semibold');
            btn.classList.remove('text-slate-600', 'dark:text-slate-400');
        } else {
            btn.classList.remove('bg-indigo-50', 'dark:bg-indigo-950/60', 'text-indigo-600', 'dark:text-indigo-400', 'font-semibold');
            btn.classList.add('text-slate-600', 'dark:text-slate-400');
        }
    });

    // Mobile bottom nav active states
    document.querySelectorAll('[data-mobile-nav]').forEach(btn => {
        const v = btn.getAttribute('data-mobile-nav');
        if (v === viewName) {
            btn.classList.add('text-indigo-600', 'dark:text-indigo-400');
            btn.classList.remove('text-slate-400');
        } else {
            btn.classList.remove('text-indigo-600', 'dark:text-indigo-400');
            btn.classList.add('text-slate-400');
        }
    });

    // Close mobile drawer if open
    const drawer = document.getElementById('mobile-drawer');
    if (drawer && !drawer.classList.contains('hidden')) {
        drawer.classList.add('hidden');
    }

    // Trigger view-specific loads
    if (viewName === 'dashboard') loadDashboard();
    else if (viewName === 'today') loadTodayAttendance();
    else if (viewName === 'timetable') loadTimetable();
    else if (viewName === 'periods') loadPeriodSlots();
    else if (viewName === 'records') loadRecords();
    else if (viewName === 'daterange') initDateRangeView();
    else if (viewName === 'analytics') loadAnalytics();
    else if (viewName === 'calendar') loadCalendar();
    else if (viewName === 'settings') loadSettings();

    if (window.lucide) window.lucide.createIcons();
}
window.switchView = switchView;

// --- Dashboard View ---
async function loadDashboard() {
    try {
        const summary = await API.getSummary();
        state.settings = summary.settings;
        state.subjects = summary.subjects;

        const overall = summary.overall;
        const required = state.settings.required_attendance;
        const warning = state.settings.warning_threshold;
        const critical = state.settings.critical_threshold;

        // Visual Percentage Indicator (SVG Ring)
        const pctEl = document.getElementById('dash-pct-text');
        const ringEl = document.getElementById('dash-pct-ring');
        const badgeEl = document.getElementById('dash-overall-status');

        if (pctEl) pctEl.textContent = `${overall.percentage}%`;

        // Circumference for r=54 is 2 * PI * 54 = 339.29
        const circumference = 2 * Math.PI * 54;
        const offset = circumference - (overall.percentage / 100) * circumference;
        if (ringEl) {
            ringEl.style.strokeDasharray = `${circumference} ${circumference}`;
            ringEl.style.strokeDashoffset = offset;

            if (overall.total === 0) {
                ringEl.setAttribute('class', 'circle-progress-val stroke-slate-300 dark:stroke-slate-700');
            } else if (overall.percentage >= warning) {
                ringEl.setAttribute('class', 'circle-progress-val stroke-emerald-500');
            } else if (overall.percentage >= critical) {
                ringEl.setAttribute('class', 'circle-progress-val stroke-amber-500');
            } else {
                ringEl.setAttribute('class', 'circle-progress-val stroke-rose-500');
            }
        }

        // Overall status badge
        if (badgeEl) {
            if (overall.total === 0) {
                badgeEl.textContent = 'Fresh Start';
                badgeEl.className = 'px-3 py-1 rounded-full text-xs font-semibold bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400';
            } else {
                const badge = overall.status_badge;
                badgeEl.textContent = badge;
                if (badge === 'Good') {
                    badgeEl.className = 'px-3 py-1 rounded-full text-xs font-semibold bg-emerald-100 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-400';
                } else if (badge === 'Warning') {
                    badgeEl.className = 'px-3 py-1 rounded-full text-xs font-semibold bg-amber-100 dark:bg-amber-950/60 text-amber-700 dark:text-amber-400';
                } else {
                    badgeEl.className = 'px-3 py-1 rounded-full text-xs font-semibold bg-rose-100 dark:bg-rose-950/60 text-rose-700 dark:text-rose-400';
                }
            }
        }

        // Key stats
        document.getElementById('dash-total-classes').textContent = overall.total;
        document.getElementById('dash-attended-classes').textContent = overall.attended;
        document.getElementById('dash-absent-classes').textContent = overall.absent;

        // Safe to miss or Catch-up Indicator
        const safeMissEl = document.getElementById('dash-safe-miss-text');
        const safeMissDesc = document.getElementById('dash-safe-miss-desc');
        if (overall.total === 0) {
            safeMissEl.textContent = "0 classes recorded";
            safeMissDesc.textContent = "Add your timetable & mark attendance to begin";
        } else if (overall.percentage >= required) {
            safeMissEl.innerHTML = `<span class="text-emerald-600 dark:text-emerald-400">🟢 Can safely miss ${overall.can_miss} class${overall.can_miss === 1 ? '' : 'es'}</span>`;
            safeMissDesc.textContent = `Without dropping below required ${required}%`;
        } else {
            if (overall.need_to_attend === -1) {
                safeMissEl.innerHTML = `<span class="text-rose-600 dark:text-rose-400">🔴 Critical: Missed classes</span>`;
                safeMissDesc.textContent = `100% target cannot be achieved`;
            } else {
                safeMissEl.innerHTML = `<span class="text-rose-600 dark:text-rose-400">🔴 Need to attend ${overall.need_to_attend} class${overall.need_to_attend === 1 ? '' : 'es'}</span>`;
                safeMissDesc.textContent = `Consecutively to reach target ${required}%`;
            }
        }

        // Smart Alert Banner
        const alertBanner = document.getElementById('dash-alert-banner');
        const lowSubjects = summary.subjects.filter(s => s.total > 0 && s.percentage < warning);
        if (lowSubjects.length > 0) {
            alertBanner.classList.remove('hidden');
            const subNames = lowSubjects.map(s => `${s.name} (${s.percentage}%)`).join(', ');
            document.getElementById('dash-alert-text').innerHTML = `
                <strong>Action Needed:</strong> ${lowSubjects.length} subject${lowSubjects.length > 1 ? 's are' : ' is'} below your required ${required}% threshold: <em>${subNames}</em>.
            `;
        } else if (summary.subjects.length > 0 && overall.total > 0) {
            alertBanner.classList.remove('hidden');
            alertBanner.className = 'mb-6 p-4 rounded-2xl bg-emerald-50 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-800 text-emerald-800 dark:text-emerald-300 flex items-start gap-3';
            document.getElementById('dash-alert-text').innerHTML = `
                <strong>🎉 Excellent Work!</strong> All your subjects are currently meeting or exceeding your attendance target of ${required}%.
            `;
        } else {
            alertBanner.classList.add('hidden');
        }

        // Load today's quick summary on dashboard
        loadDashboardTodayQuick();

        // Render Subject Cards
        renderDashboardSubjects(summary.subjects);

    } catch (err) {
        console.error("Dashboard load failed:", err);
        showToast("Failed to load dashboard data", "error");
    }
}

async function loadDashboardTodayQuick() {
    try {
        const todayData = await API.getTodayAttendance(state.todayDate);
        const card = document.getElementById('dash-today-quick-card');
        if (!card) return;

        const s = todayData.summary;
        document.getElementById('dash-today-total').textContent = s.total;
        document.getElementById('dash-today-present').textContent = s.present;
        document.getElementById('dash-today-absent').textContent = s.absent;
        document.getElementById('dash-today-unmarked').textContent = s.unmarked;
        document.getElementById('dash-today-day-label').textContent = `${todayData.day}, ${formatDateDisplay(todayData.date)}`;
    } catch (err) {
        console.error("Failed to load today quick summary:", err);
    }
}

function renderDashboardSubjects(subjects) {
    const grid = document.getElementById('dash-subjects-grid');
    const tableBody = document.getElementById('dash-subjects-table-body');
    if (!grid || !tableBody) return;

    if (!subjects || subjects.length === 0) {
        grid.innerHTML = `
            <div class="col-span-full py-12 text-center bg-white dark:bg-slate-900 rounded-3xl border border-slate-200 dark:border-slate-800 p-8 shadow-sm">
                <div class="w-16 h-16 rounded-3xl bg-indigo-50 dark:bg-indigo-950/60 text-indigo-600 dark:text-indigo-400 flex items-center justify-center mx-auto mb-4">
                    <i data-lucide="book-plus" class="w-8 h-8"></i>
                </div>
                <h3 class="text-lg font-bold text-slate-900 dark:text-white">Start Fresh: Add Your First Subject</h3>
                <p class="text-sm text-slate-500 dark:text-slate-400 max-w-md mx-auto mt-1 mb-6">Your attendance tracker is clean with no mock data. Add your real college subjects and timetable to begin tracking your attendance.</p>
                <div class="flex flex-wrap gap-3 justify-center">
                    <button class="px-5 py-2.5 rounded-xl text-sm font-bold bg-indigo-600 hover:bg-indigo-700 text-white transition shadow-sm flex items-center gap-2" onclick="window.appOpenAddSubjectModal()">
                        <i data-lucide="plus" class="w-4 h-4"></i> Add Your First Subject
                    </button>
                    <button class="px-5 py-2.5 rounded-xl text-sm font-semibold bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 transition flex items-center gap-2" onclick="window.switchView('timetable')">
                        <i data-lucide="calendar" class="w-4 h-4"></i> Set Up Timetable
                    </button>
                </div>
            </div>
        `;
        tableBody.innerHTML = `<tr><td colspan="6" class="text-center py-8 text-slate-400">No subjects yet. Click "+ Add Your First Subject" above to get started.</td></tr>`;
        if (window.lucide) window.lucide.createIcons();
        return;
    }

    // Render Cards View
    grid.innerHTML = subjects.map(s => {
        const badgeClasses = {
            Good: 'bg-emerald-100 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-400 border-emerald-200 dark:border-emerald-800',
            Warning: 'bg-amber-100 dark:bg-amber-950/60 text-amber-700 dark:text-amber-400 border-amber-200 dark:border-amber-800',
            Critical: 'bg-rose-100 dark:bg-rose-950/60 text-rose-700 dark:text-rose-400 border-rose-200 dark:border-rose-800'
        }[s.status_badge] || 'bg-slate-100 text-slate-700';

        let adviceText = '';
        if (s.total === 0) {
            adviceText = 'No attendance recorded';
        } else if (s.percentage >= state.settings.required_attendance) {
            adviceText = `🟢 Safe to miss <strong>${s.can_miss}</strong> class${s.can_miss === 1 ? '' : 'es'}`;
        } else {
            adviceText = s.need_to_attend === -1 ? `🔴 100% impossible` : `🔴 Attend next <strong>${s.need_to_attend}</strong> class${s.need_to_attend === 1 ? '' : 'es'}`;
        }

        return `
            <div class="card-subtle bg-white dark:bg-slate-900 rounded-2xl p-5 border border-slate-200 dark:border-slate-800 shadow-sm cursor-pointer relative overflow-hidden group" onclick="window.appOpenSubjectDetails(${s.id})">
                <div class="absolute top-0 left-0 right-0 h-1" style="background-color: ${s.color || '#3B82F6'}"></div>
                
                <div class="flex items-start justify-between gap-2 mb-3">
                    <div>
                        <div class="flex items-center gap-2">
                            <span class="text-xs font-semibold px-2 py-0.5 rounded-md bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300">${s.code}</span>
                            <span class="text-xs px-2 py-0.5 rounded-md border font-medium ${badgeClasses}">${s.status_badge}</span>
                        </div>
                        <h4 class="font-bold text-base text-slate-900 dark:text-white mt-1 group-hover:text-indigo-600 dark:group-hover:text-indigo-400 transition">${s.name}</h4>
                    </div>
                    <div class="text-right">
                        <span class="text-2xl font-black text-slate-900 dark:text-white">${s.percentage}%</span>
                    </div>
                </div>

                <!-- Progress Bar -->
                <div class="w-full bg-slate-100 dark:bg-slate-800 h-2.5 rounded-full overflow-hidden mb-3">
                    <div class="h-full rounded-full transition-all duration-500 ${s.status_badge === 'Good' ? 'bg-emerald-500' : (s.status_badge === 'Warning' ? 'bg-amber-500' : 'bg-rose-500')}" style="width: ${s.percentage}%"></div>
                </div>

                <div class="grid grid-cols-3 gap-2 text-center text-xs py-2 bg-slate-50 dark:bg-slate-800/50 rounded-xl mb-3 text-slate-600 dark:text-slate-400">
                    <div>
                        <div class="text-slate-400 dark:text-slate-500">Attended</div>
                        <div class="font-bold text-slate-900 dark:text-slate-200 text-sm">${s.attended}</div>
                    </div>
                    <div>
                        <div class="text-slate-400 dark:text-slate-500">Absent</div>
                        <div class="font-bold text-slate-900 dark:text-slate-200 text-sm">${s.absent}</div>
                    </div>
                    <div>
                        <div class="text-slate-400 dark:text-slate-500">Total</div>
                        <div class="font-bold text-slate-900 dark:text-slate-200 text-sm">${s.total}</div>
                    </div>
                </div>

                <div class="text-xs text-slate-600 dark:text-slate-300 flex items-center justify-between">
                    <div>${adviceText}</div>
                    <span class="text-indigo-600 dark:text-indigo-400 font-medium group-hover:translate-x-0.5 transition-transform">Details &rarr;</span>
                </div>
            </div>
        `;
    }).join('');

    // Render Table View
    tableBody.innerHTML = subjects.map(s => {
        const badgeClasses = {
            Good: 'bg-emerald-100 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-400',
            Warning: 'bg-amber-100 dark:bg-amber-950/60 text-amber-700 dark:text-amber-400',
            Critical: 'bg-rose-100 dark:bg-rose-950/60 text-rose-700 dark:text-rose-400'
        }[s.status_badge] || 'bg-slate-100 text-slate-700';

        return `
            <tr class="hover:bg-slate-50 dark:hover:bg-slate-800/50 transition cursor-pointer" onclick="window.appOpenSubjectDetails(${s.id})">
                <td class="px-6 py-4">
                    <div class="flex items-center gap-3">
                        <span class="w-3 h-3 rounded-full flex-shrink-0" style="background-color: ${s.color || '#3B82F6'}"></span>
                        <div>
                            <div class="font-semibold text-slate-900 dark:text-white">${s.name}</div>
                            <div class="text-xs text-slate-500 dark:text-slate-400">${s.code} &bull; ${s.faculty || 'No faculty'}</div>
                        </div>
                    </div>
                </td>
                <td class="px-6 py-4 text-center font-medium text-slate-800 dark:text-slate-200">${s.attended}</td>
                <td class="px-6 py-4 text-center font-medium text-slate-800 dark:text-slate-200">${s.total}</td>
                <td class="px-6 py-4 text-center">
                    <span class="font-bold text-slate-900 dark:text-white">${s.percentage}%</span>
                </td>
                <td class="px-6 py-4 text-center">
                    <span class="px-2.5 py-1 rounded-full text-xs font-semibold ${badgeClasses}">${s.status_badge}</span>
                </td>
                <td class="px-6 py-4 text-right">
                    <button class="text-xs font-semibold text-indigo-600 dark:text-indigo-400 hover:underline">
                        Calculator &rarr;
                    </button>
                </td>
            </tr>
        `;
    }).join('');

    if (window.lucide) window.lucide.createIcons();
}

// --- Today's Attendance View ---
async function loadTodayAttendance() {
    try {
        const dateInput = document.getElementById('today-date-picker');
        if (dateInput && !dateInput.value) {
            dateInput.value = state.todayDate;
        }
        const activeDate = dateInput ? dateInput.value : state.todayDate;

        const data = await API.getTodayAttendance(activeDate);
        
        // Update header labels
        document.getElementById('today-display-day').textContent = data.day;
        document.getElementById('today-display-date').textContent = formatDateDisplay(data.date);

        // Update summary badges
        const s = data.summary;
        document.getElementById('today-stat-total').textContent = s.total;
        document.getElementById('today-stat-present').textContent = s.present;
        document.getElementById('today-stat-absent').textContent = s.absent;
        document.getElementById('today-stat-unmarked').textContent = s.unmarked;
        document.getElementById('today-stat-pct').textContent = `${s.percentage}%`;

        const container = document.getElementById('today-periods-list');
        if (!container) return;

        if (data.periods.length === 0) {
            container.innerHTML = `
                <div class="py-16 text-center bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 p-8">
                    <i data-lucide="calendar-x" class="w-12 h-12 text-slate-300 dark:text-slate-700 mx-auto mb-3"></i>
                    <h3 class="text-base font-semibold text-slate-800 dark:text-slate-200">No Classes Scheduled for ${data.day}</h3>
                    <p class="text-sm text-slate-500 dark:text-slate-400 mt-1 mb-4">You have no periods configured in your timetable for ${data.day}.</p>
                    <button class="px-4 py-2 rounded-xl text-sm font-medium bg-indigo-600 hover:bg-indigo-700 text-white transition shadow-sm" onclick="window.appGoToTimetableDay('${data.day}')">
                        + Edit ${data.day} Timetable
                    </button>
                </div>
            `;
            if (window.lucide) window.lucide.createIcons();
            return;
        }

        container.innerHTML = data.periods.map(p => {
            const isPresent = p.status === 'Present';
            const isAbsent = p.status === 'Absent';
            const isUnmarked = !p.status;

            return `
                <div class="bg-white dark:bg-slate-900 rounded-2xl p-4 sm:p-5 border ${isPresent ? 'border-emerald-300 dark:border-emerald-800/80 bg-emerald-50/20' : (isAbsent ? 'border-rose-300 dark:border-rose-800/80 bg-rose-50/20' : 'border-slate-200 dark:border-slate-800')} shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-4 transition-all">
                    
                    <div class="flex items-start gap-4">
                        <div class="w-12 h-12 rounded-2xl flex flex-col items-center justify-center font-bold flex-shrink-0 text-white shadow-sm" style="background-color: ${p.subject_color || '#3B82F6'}">
                            <span class="text-xs uppercase opacity-80">Per</span>
                            <span class="text-base leading-none">${p.period_number}</span>
                        </div>
                        <div>
                            <div class="flex items-center gap-2 flex-wrap">
                                <span class="text-xs font-semibold px-2 py-0.5 rounded-md bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300">${p.subject_code}</span>
                                <span class="text-xs text-slate-500 dark:text-slate-400 font-medium">🕒 ${p.start_time} - ${p.end_time}</span>
                                ${p.effective_room ? `<span class="text-xs text-slate-500 dark:text-slate-400">📍 ${p.effective_room}</span>` : ''}
                            </div>
                            <h4 class="font-bold text-base text-slate-900 dark:text-white mt-1">${p.subject_name}</h4>
                            ${p.effective_faculty ? `<p class="text-xs text-slate-500 dark:text-slate-400 mt-0.5">Faculty: ${p.effective_faculty}</p>` : ''}
                        </div>
                    </div>

                    <!-- Attendance Buttons -->
                    <div class="flex items-center gap-2 self-end md:self-center">
                        <button class="px-4 py-2 rounded-xl text-sm font-semibold flex items-center gap-1.5 transition ${isPresent ? 'bg-emerald-600 text-white ring-2 ring-emerald-500 ring-offset-2 dark:ring-offset-slate-900 shadow-sm' : 'bg-slate-100 dark:bg-slate-800 hover:bg-emerald-100 dark:hover:bg-emerald-950/50 text-slate-700 dark:text-slate-300 hover:text-emerald-700'}"
                                onclick="window.appMarkTodayPeriod(${p.id}, ${p.subject_id}, 'Present')">
                            <i data-lucide="check" class="w-4 h-4"></i>
                            <span>Present</span>
                        </button>

                        <button class="px-4 py-2 rounded-xl text-sm font-semibold flex items-center gap-1.5 transition ${isAbsent ? 'bg-rose-600 text-white ring-2 ring-rose-500 ring-offset-2 dark:ring-offset-slate-900 shadow-sm' : 'bg-slate-100 dark:bg-slate-800 hover:bg-rose-100 dark:hover:bg-rose-950/50 text-slate-700 dark:text-slate-300 hover:text-rose-700'}"
                                onclick="window.appMarkTodayPeriod(${p.id}, ${p.subject_id}, 'Absent')">
                            <i data-lucide="x" class="w-4 h-4"></i>
                            <span>Absent</span>
                        </button>

                        ${!isUnmarked ? `
                            <button class="p-2 rounded-xl text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition" title="Clear/Unmark"
                                    onclick="window.appUnmarkTodayPeriod(${p.id})">
                                <i data-lucide="rotate-ccw" class="w-4 h-4"></i>
                            </button>
                        ` : ''}
                    </div>

                </div>
            `;
        }).join('');

        if (window.lucide) window.lucide.createIcons();

    } catch (err) {
        console.error("Failed to load today attendance:", err);
        showToast("Failed to load daily attendance", "error");
    }
}

// Mark single period today
window.appMarkTodayPeriod = async function(periodId, subjectId, status) {
    try {
        const dateInput = document.getElementById('today-date-picker');
        const activeDate = dateInput ? dateInput.value : state.todayDate;
        await API.markAttendance(activeDate, periodId, subjectId, status);
        showToast(`Marked ${status}!`, status === 'Present' ? 'success' : 'warning');
        loadTodayAttendance();
    } catch (err) {
        showToast("Failed to record attendance", "error");
    }
};

window.appUnmarkTodayPeriod = async function(periodId) {
    try {
        const dateInput = document.getElementById('today-date-picker');
        const activeDate = dateInput ? dateInput.value : state.todayDate;
        await API.unmarkAttendance(activeDate, periodId);
        showToast("Attendance unmarked", "info");
        loadTodayAttendance();
    } catch (err) {
        showToast("Failed to unmark attendance", "error");
    }
};

// Batch actions for today
window.appMarkAllToday = async function(status) {
    try {
        const dateInput = document.getElementById('today-date-picker');
        const activeDate = dateInput ? dateInput.value : state.todayDate;
        const data = await API.getTodayAttendance(activeDate);

        for (const p of data.periods) {
            await API.markAttendance(activeDate, p.id, p.subject_id, status);
        }
        showToast(`All classes marked ${status}!`, 'success');
        loadTodayAttendance();
    } catch (err) {
        showToast("Batch update failed", "error");
    }
};

window.appClearAllToday = async function(status) {
    const ok = await confirmAction("Clear Today's Attendance?", "This will remove all attendance entries marked for this specific date.", "Clear All", true);
    if (!ok) return;

    try {
        const dateInput = document.getElementById('today-date-picker');
        const activeDate = dateInput ? dateInput.value : state.todayDate;
        const data = await API.getTodayAttendance(activeDate);

        for (const p of data.periods) {
            await API.unmarkAttendance(activeDate, p.id);
        }
        showToast("Cleared all attendance for this date", "info");
        loadTodayAttendance();
    } catch (err) {
        showToast("Clear failed", "error");
    }
};

// --- Timetable Management ---
const DAYS_OF_WEEK = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];

async function loadTimetable() {
    try {
        // Ensure subjects and master period slots are loaded
        state.subjects = await API.getSubjects();
        state.periodSlots = await API.getPeriodSlots();

        // Update badge
        const slotBadge = document.getElementById('timetable-period-slots-count');
        if (slotBadge) slotBadge.textContent = state.periodSlots.length;

        // Render Day Tabs
        const tabsContainer = document.getElementById('timetable-days-tabs');
        if (tabsContainer) {
            tabsContainer.innerHTML = DAYS_OF_WEEK.map(day => `
                <button class="px-4 py-2 rounded-xl text-sm font-semibold transition ${state.timetableSelectedDay === day ? 'bg-indigo-600 text-white shadow-sm' : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700'}"
                        onclick="window.appSelectTimetableDay('${day}')">
                    ${day}
                </button>
            `).join('');
        }

        const periods = await API.getTimetable(state.timetableSelectedDay);
        state.timetable = periods;

        const listContainer = document.getElementById('timetable-periods-list');
        if (!listContainer) return;

        if (periods.length === 0) {
            listContainer.innerHTML = `
                <div class="py-16 text-center bg-white dark:bg-slate-900 rounded-3xl border border-slate-200 dark:border-slate-800 p-8">
                    <i data-lucide="clock" class="w-12 h-12 text-slate-300 dark:text-slate-700 mx-auto mb-3"></i>
                    <h3 class="text-base font-bold text-slate-800 dark:text-slate-200">No Periods Scheduled for ${state.timetableSelectedDay}</h3>
                    <p class="text-xs text-slate-500 dark:text-slate-400 mt-1 mb-5">Assign subjects to your defined period slots or duplicate from another day.</p>
                    <div class="flex flex-wrap gap-3 justify-center mb-6">
                        <button class="px-5 py-2.5 rounded-xl text-xs font-bold bg-indigo-600 hover:bg-indigo-700 text-white transition shadow-sm flex items-center gap-2" onclick="window.appOpenAddPeriodModal()">
                            <i data-lucide="plus" class="w-4 h-4"></i> Add Period
                        </button>
                        <button class="px-4 py-2.5 rounded-xl text-xs font-bold bg-indigo-50 dark:bg-indigo-950/60 hover:bg-indigo-100 text-indigo-700 dark:text-indigo-300 transition flex items-center gap-2" onclick="window.switchView('periods')">
                            <i data-lucide="clock" class="w-4 h-4"></i> Manage Periods (${state.periodSlots.length})
                        </button>
                        <button class="px-4 py-2.5 rounded-xl text-xs font-bold bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 transition flex items-center gap-2" onclick="window.appOpenDuplicateDayModal('${state.timetableSelectedDay}')">
                            <i data-lucide="copy" class="w-4 h-4"></i> Duplicate Day
                        </button>
                    </div>

                    ${(state.periodSlots && state.periodSlots.length > 0) ? `
                        <div class="pt-5 border-t border-slate-100 dark:border-slate-800 max-w-lg mx-auto">
                            <span class="text-xs font-semibold text-slate-400 block mb-2.5">Click any created period slot to assign a subject for ${state.timetableSelectedDay}:</span>
                            <div class="flex flex-wrap gap-2 justify-center">
                                ${state.periodSlots.map(s => `
                                    <button class="px-3 py-1.5 rounded-xl bg-slate-50 dark:bg-slate-800/80 border border-slate-200 dark:border-slate-700 hover:border-indigo-500 text-xs font-bold text-slate-700 dark:text-slate-300 hover:text-indigo-600 transition flex items-center gap-1.5"
                                            onclick="window.appOpenAddPeriodModal(${s.id})" title="Assign subject to ${s.label}">
                                        <span>P${s.slot_number}:</span> <span class="font-normal text-slate-500">${s.start_time}-${s.end_time}</span>
                                    </button>
                                `).join('')}
                            </div>
                        </div>
                    ` : ''}
                </div>
            `;
            if (window.lucide) window.lucide.createIcons();
            return;
        }

        listContainer.innerHTML = periods.map((p, idx) => `
            <div class="bg-white dark:bg-slate-900 rounded-2xl p-4 sm:p-5 border border-slate-200 dark:border-slate-800 shadow-sm flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div class="flex items-start gap-4">
                    <div class="w-10 h-10 rounded-xl flex items-center justify-center font-bold text-white flex-shrink-0" style="background-color: ${p.subject_color || '#3B82F6'}">
                        ${p.period_number}
                    </div>
                    <div>
                        <div class="flex items-center gap-2">
                            <span class="text-xs font-semibold px-2 py-0.5 rounded-md bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300">${p.subject_code}</span>
                            <span class="text-xs font-semibold text-indigo-600 dark:text-indigo-400">🕒 ${p.start_time} - ${p.end_time}</span>
                        </div>
                        <h4 class="font-bold text-base text-slate-900 dark:text-white mt-1">${p.subject_name}</h4>
                        <div class="flex items-center gap-4 text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                            ${p.effective_faculty ? `<span>Faculty: ${p.effective_faculty}</span>` : ''}
                            ${p.effective_room ? `<span>Room: ${p.effective_room}</span>` : ''}
                        </div>
                    </div>
                </div>

                <div class="flex items-center gap-2 self-end sm:self-center">
                    <!-- Move Up / Down -->
                    <button class="p-2 rounded-xl bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white transition disabled:opacity-40"
                            ${idx === 0 ? 'disabled' : ''} onclick="window.appMovePeriod(${p.id}, -1)" title="Move Up">
                        <i data-lucide="arrow-up" class="w-4 h-4"></i>
                    </button>
                    <button class="p-2 rounded-xl bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white transition disabled:opacity-40"
                            ${idx === periods.length - 1 ? 'disabled' : ''} onclick="window.appMovePeriod(${p.id}, 1)" title="Move Down">
                        <i data-lucide="arrow-down" class="w-4 h-4"></i>
                    </button>
                    
                    <!-- Edit -->
                    <button class="p-2 rounded-xl bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:text-indigo-600 dark:hover:text-indigo-400 transition"
                            onclick="window.appOpenEditPeriodModal(${p.id})" title="Edit Period">
                        <i data-lucide="edit-2" class="w-4 h-4"></i>
                    </button>

                    <!-- Delete -->
                    <button class="p-2 rounded-xl bg-rose-50 dark:bg-rose-950/40 text-rose-600 dark:text-rose-400 hover:bg-rose-100 dark:hover:bg-rose-900/60 transition"
                            onclick="window.appDeletePeriod(${p.id})" title="Delete Saved Period" aria-label="Delete Period">
                        <i data-lucide="trash-2" class="w-4 h-4"></i>
                    </button>
                </div>
            </div>
        `).join('');

        if (window.lucide) window.lucide.createIcons();

    } catch (err) {
        console.error("Timetable load failed:", err);
        showToast("Failed to load timetable", "error");
    }
}

window.appSelectTimetableDay = function(day) {
    state.timetableSelectedDay = day;
    loadTimetable();
};

window.appMovePeriod = async function(periodId, direction) {
    const list = [...state.timetable];
    const index = list.findIndex(p => p.id === periodId);
    if (index === -1) return;

    const targetIndex = index + direction;
    if (targetIndex < 0 || targetIndex >= list.length) return;

    // Swap
    const temp = list[index];
    list[index] = list[targetIndex];
    list[targetIndex] = temp;

    const orderedIds = list.map(p => p.id);
    try {
        await API.reorderTimetable(orderedIds);
        loadTimetable();
    } catch (err) {
        showToast("Failed to reorder", "error");
    }
};

window.appDeletePeriod = async function(periodId) {
    const ok = await confirmAction("Delete Period?", "Are you sure you want to remove this period from the timetable?", "Delete", true);
    if (!ok) return;

    try {
        await API.deleteTimetablePeriod(periodId);
        showToast("Period removed", "success");
        loadTimetable();
    } catch (err) {
        showToast("Failed to delete period", "error");
    }
};

window.appClearTimetableDay = async function() {
    const ok = await confirmAction(`Clear all periods for ${state.timetableSelectedDay}?`, `This will remove all scheduled periods for ${state.timetableSelectedDay}.`, "Clear Day", true);
    if (!ok) return;

    try {
        await API.clearTimetableDay(state.timetableSelectedDay);
        showToast(`Cleared ${state.timetableSelectedDay}`, "info");
        loadTimetable();
    } catch (err) {
        showToast("Failed to clear day", "error");
    }
};

// --- Master Period Slots Management ---
function calcDurationMinutes(start, end) {
    if (!start || !end) return 50;
    try {
        const [sh, sm] = start.split(':').map(Number);
        const [eh, em] = end.split(':').map(Number);
        let diff = (eh * 60 + em) - (sh * 60 + sm);
        if (diff < 0) diff += 24 * 60;
        return diff > 0 ? diff : 50;
    } catch (e) {
        return 50;
    }
}

export async function loadPeriodSlots() {
    try {
        const slots = await API.getPeriodSlots();
        state.periodSlots = slots;

        // Update count badge on timetable view if present
        const badge = document.getElementById('timetable-period-slots-count');
        if (badge) badge.textContent = slots.length;

        const listContainer = document.getElementById('periods-slots-list');
        if (!listContainer) return;

        if (slots.length === 0) {
            listContainer.innerHTML = `
                <div class="col-span-full py-14 text-center bg-white dark:bg-slate-900 rounded-3xl border border-slate-200 dark:border-slate-800 p-8">
                    <i data-lucide="clock" class="w-12 h-12 text-slate-300 dark:text-slate-700 mx-auto mb-3"></i>
                    <h3 class="text-base font-bold text-slate-800 dark:text-slate-200">No Period Slots Defined</h3>
                    <p class="text-xs text-slate-500 dark:text-slate-400 mt-1 mb-5">Create your daily periods (e.g. Period 1: 09:00 - 09:50) or restore standard college defaults.</p>
                    <div class="flex flex-wrap gap-3 justify-center">
                        <button class="px-4 py-2.5 rounded-xl text-xs font-bold bg-indigo-600 hover:bg-indigo-700 text-white transition shadow-sm flex items-center gap-2" onclick="window.appOpenCreatePeriodSlotModal()">
                            <i data-lucide="plus" class="w-4 h-4"></i> Create First Period Slot
                        </button>
                        <button class="px-4 py-2.5 rounded-xl text-xs font-semibold bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 transition flex items-center gap-2" onclick="window.appResetPeriodSlotsDefaults()">
                            <i data-lucide="rotate-ccw" class="w-4 h-4"></i> Restore Standard 6 Periods
                        </button>
                    </div>
                </div>
            `;
            if (window.lucide) window.lucide.createIcons();
            return;
        }

        listContainer.innerHTML = slots.map(s => {
            const duration = calcDurationMinutes(s.start_time, s.end_time);
            return `
                <div class="bg-white dark:bg-slate-900 rounded-2xl p-5 border border-slate-200 dark:border-slate-800 shadow-sm flex flex-col justify-between hover:border-indigo-200 dark:hover:border-indigo-900/60 transition group">
                    <div class="flex items-start justify-between gap-3 mb-3">
                        <div class="flex items-center gap-3">
                            <div class="w-11 h-11 rounded-2xl bg-indigo-50 dark:bg-indigo-950/60 text-indigo-600 dark:text-indigo-400 font-black flex items-center justify-center text-sm shadow-sm group-hover:bg-indigo-600 group-hover:text-white transition">
                                P${s.slot_number}
                            </div>
                            <div>
                                <h4 class="font-bold text-sm text-slate-900 dark:text-white">${s.label || ('Period ' + s.slot_number)}</h4>
                                <span class="text-[11px] text-slate-400 font-medium">Slot #${s.slot_number} &bull; ${duration} mins</span>
                            </div>
                        </div>
                        <div class="flex items-center gap-1">
                            <button class="p-1.5 rounded-lg text-slate-400 hover:text-indigo-600 hover:bg-slate-100 dark:hover:bg-slate-800 transition"
                                    onclick="window.appOpenEditPeriodSlotModal(${s.id})" title="Edit Slot Timing">
                                <i data-lucide="edit-2" class="w-4 h-4"></i>
                            </button>
                            <button class="p-1.5 rounded-lg text-slate-400 hover:text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-950/40 transition"
                                    onclick="window.appDeletePeriodSlot(${s.id})" title="Delete This Slot">
                                <i data-lucide="trash-2" class="w-4 h-4"></i>
                            </button>
                        </div>
                    </div>

                    <div class="pt-3 border-t border-slate-100 dark:border-slate-800/80 flex items-center justify-between">
                        <div class="flex items-center gap-1.5 text-xs font-semibold text-slate-700 dark:text-slate-300">
                            <i data-lucide="clock" class="w-3.5 h-3.5 text-indigo-500"></i>
                            <span>${s.start_time} - ${s.end_time}</span>
                        </div>
                        <button class="text-[11px] font-bold text-indigo-600 dark:text-indigo-400 hover:underline flex items-center gap-1"
                                onclick="window.appAddSlotToTimetable(${s.id})">
                            <span>+ To Timetable</span>
                            <i data-lucide="arrow-right" class="w-3 h-3"></i>
                        </button>
                    </div>
                </div>
            `;
        }).join('');

        if (window.lucide) window.lucide.createIcons();

    } catch (err) {
        console.error("Failed to load period slots:", err);
        showToast("Failed to load period slots", "error");
    }
}
window.loadPeriodSlots = loadPeriodSlots;

window.appAddSlotToTimetable = function(slotId) {
    window.switchView('timetable');
    window.appOpenAddPeriodModal(slotId);
};

// --- Attendance Records (History) ---
async function loadRecords() {
    try {
        // Populate subject filter dropdown if empty
        const subSelect = document.getElementById('records-filter-subject');
        if (subSelect && subSelect.children.length <= 1) {
            state.subjects = await API.getSubjects();
            subSelect.innerHTML = `<option value="">All Subjects</option>` +
                state.subjects.map(s => `<option value="${s.id}">${s.code} - ${s.name}</option>`).join('');
        }

        const fromDate = document.getElementById('records-filter-from')?.value || '';
        const toDate = document.getElementById('records-filter-to')?.value || '';
        const subjectId = document.getElementById('records-filter-subject')?.value || '';
        const status = document.getElementById('records-filter-status')?.value || '';
        const sort = document.getElementById('records-filter-sort')?.value || 'date';
        const order = document.getElementById('records-filter-order')?.value || 'DESC';

        const records = await API.getAttendance({
            from_date: fromDate,
            to_date: toDate,
            subject_id: subjectId,
            status: status,
            sort: sort,
            order: order
        });

        // Summary stats for filtered records
        const total = records.length;
        const attended = records.filter(r => r.status === 'Present').length;
        const absent = total - attended;
        const pct = total > 0 ? Math.round((attended / total) * 1000) / 10 : 0;

        document.getElementById('records-stats-summary').innerHTML = `
            Showing <strong>${total}</strong> records &bull; 
            <span class="text-emerald-600 dark:text-emerald-400 font-semibold">${attended} Present (${pct}%)</span> &bull; 
            <span class="text-rose-600 dark:text-rose-400 font-semibold">${absent} Absent</span>
        `;

        const tbody = document.getElementById('records-table-body');
        if (!tbody) return;

        if (records.length === 0) {
            tbody.innerHTML = `<tr><td colspan="7" class="text-center py-12 text-slate-400">No attendance records match your filter criteria.</td></tr>`;
            return;
        }

        tbody.innerHTML = records.map(r => {
            const isPresent = r.status === 'Present';
            return `
                <tr class="hover:bg-slate-50 dark:hover:bg-slate-800/50 transition">
                    <td class="px-6 py-4 whitespace-nowrap">
                        <div class="font-semibold text-slate-900 dark:text-white">${formatDateDisplay(r.date)}</div>
                        <div class="text-xs text-slate-400">${r.period_day || getDayName(r.date)}</div>
                    </td>
                    <td class="px-6 py-4 text-center whitespace-nowrap">
                        <span class="px-2.5 py-1 rounded-lg text-xs font-bold bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300">
                            P${r.period_number || '-'}
                        </span>
                    </td>
                    <td class="px-6 py-4 whitespace-nowrap">
                        <div class="flex items-center gap-2">
                            <span class="w-2.5 h-2.5 rounded-full flex-shrink-0" style="background-color: ${r.subject_color || '#3B82F6'}"></span>
                            <div>
                                <span class="font-semibold text-slate-900 dark:text-white">${r.subject_name}</span>
                                <span class="text-xs text-slate-400 ml-1">(${r.subject_code})</span>
                            </div>
                        </div>
                    </td>
                    <td class="px-6 py-4 text-xs text-slate-500 dark:text-slate-400 whitespace-nowrap">
                        ${r.start_time && r.end_time ? `${r.start_time} - ${r.end_time}` : '-'}
                    </td>
                    <td class="px-6 py-4 text-center whitespace-nowrap">
                        <button class="px-3 py-1 rounded-full text-xs font-bold transition ${isPresent ? 'bg-emerald-100 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-400 hover:bg-emerald-200' : 'bg-rose-100 dark:bg-rose-950/60 text-rose-700 dark:text-rose-400 hover:bg-rose-200'}"
                                onclick="window.appToggleRecordStatus(${r.id}, '${r.status}')" title="Click to toggle status">
                            ${r.status}
                        </button>
                    </td>
                    <td class="px-6 py-4 text-right whitespace-nowrap">
                        <button class="p-1.5 rounded-lg text-slate-400 hover:text-rose-600 dark:hover:text-rose-400 transition"
                                onclick="window.appDeleteRecord(${r.id})" title="Delete Record">
                            <i data-lucide="trash-2" class="w-4 h-4"></i>
                        </button>
                    </td>
                </tr>
            `;
        }).join('');

        if (window.lucide) window.lucide.createIcons();

    } catch (err) {
        console.error("Records load failed:", err);
        showToast("Failed to load records", "error");
    }
}

window.appToggleRecordStatus = async function(recordId, currentStatus) {
    const newStatus = currentStatus === 'Present' ? 'Absent' : 'Present';
    try {
        await API.updateAttendanceRecord(recordId, newStatus);
        showToast(`Changed to ${newStatus}`, 'success');
        loadRecords();
    } catch (err) {
        showToast("Failed to update status", "error");
    }
};

window.appDeleteRecord = async function(recordId) {
    const ok = await confirmAction("Delete Attendance Record?", "This will remove this attendance entry permanently.", "Delete", true);
    if (!ok) return;

    try {
        await API.deleteAttendanceRecord(recordId);
        showToast("Record deleted", "info");
        loadRecords();
    } catch (err) {
        showToast("Failed to delete record", "error");
    }
};

// --- Custom Date Range Attendance ---
function initDateRangeView() {
    // Set default range to current month
    const fromInput = document.getElementById('range-from-date');
    const toInput = document.getElementById('range-to-date');

    if (fromInput && !fromInput.value) {
        const today = new Date();
        const firstDay = new Date(today.getFullYear(), today.getMonth(), 1);
        fromInput.value = firstDay.toISOString().split('T')[0];
    }
    if (toInput && !toInput.value) {
        toInput.value = new Date().toISOString().split('T')[0];
    }

    loadDateRangeAnalysis();
}

window.appApplyDateRangePreset = function(preset) {
    const fromInput = document.getElementById('range-from-date');
    const toInput = document.getElementById('range-to-date');
    const now = new Date();

    if (preset === 'week') {
        const d = new Date(now);
        const day = d.getDay();
        const diff = d.getDate() - day + (day === 0 ? -6 : 1); // Monday
        const monday = new Date(d.setDate(diff));
        fromInput.value = monday.toISOString().split('T')[0];
        toInput.value = now.toISOString().split('T')[0];
    } else if (preset === 'month') {
        const firstDay = new Date(now.getFullYear(), now.getMonth(), 1);
        fromInput.value = firstDay.toISOString().split('T')[0];
        toInput.value = now.toISOString().split('T')[0];
    } else if (preset === 'last30') {
        const past = new Date(now);
        past.setDate(now.getDate() - 30);
        fromInput.value = past.toISOString().split('T')[0];
        toInput.value = now.toISOString().split('T')[0];
    } else if (preset === 'semester') {
        // e.g. July 1 to now
        const yr = now.getFullYear();
        fromInput.value = `${yr}-07-01`;
        toInput.value = now.toISOString().split('T')[0];
    }
    loadDateRangeAnalysis();
};

async function loadDateRangeAnalysis() {
    const fromDate = document.getElementById('range-from-date').value;
    const toDate = document.getElementById('range-to-date').value;

    if (!fromDate || !toDate) {
        showToast("Please select both From and To dates", "warning");
        return;
    }

    try {
        const summary = await API.getSummary(fromDate, toDate);
        const overall = summary.overall;

        // Populate range KPI cards
        document.getElementById('range-pct-text').textContent = `${overall.percentage}%`;
        document.getElementById('range-total-classes').textContent = overall.total;
        document.getElementById('range-attended-classes').textContent = overall.attended;
        document.getElementById('range-absent-classes').textContent = overall.absent;

        // Range Subject breakdown
        const tbody = document.getElementById('range-subjects-table-body');
        if (tbody) {
            tbody.innerHTML = summary.subjects.map(s => {
                const badgeClasses = {
                    Good: 'bg-emerald-100 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-400',
                    Warning: 'bg-amber-100 dark:bg-amber-950/60 text-amber-700 dark:text-amber-400',
                    Critical: 'bg-rose-100 dark:bg-rose-950/60 text-rose-700 dark:text-rose-400'
                }[s.status_badge] || 'bg-slate-100 text-slate-700';

                return `
                    <tr class="hover:bg-slate-50 dark:hover:bg-slate-800/50 transition">
                        <td class="px-6 py-4">
                            <div class="flex items-center gap-2">
                                <span class="w-3 h-3 rounded-full flex-shrink-0" style="background-color: ${s.color || '#3B82F6'}"></span>
                                <div>
                                    <div class="font-semibold text-slate-900 dark:text-white">${s.name}</div>
                                    <div class="text-xs text-slate-400">${s.code}</div>
                                </div>
                            </div>
                        </td>
                        <td class="px-6 py-4 text-center font-medium">${s.attended}</td>
                        <td class="px-6 py-4 text-center font-medium">${s.absent}</td>
                        <td class="px-6 py-4 text-center font-medium">${s.total}</td>
                        <td class="px-6 py-4 text-center">
                            <div class="flex items-center justify-center gap-2">
                                <span class="font-bold text-slate-900 dark:text-white">${s.percentage}%</span>
                                <div class="w-16 bg-slate-100 dark:bg-slate-800 h-2 rounded-full overflow-hidden hidden sm:block">
                                    <div class="h-full rounded-full ${s.percentage >= 75 ? 'bg-emerald-500' : 'bg-rose-500'}" style="width: ${s.percentage}%"></div>
                                </div>
                            </div>
                        </td>
                        <td class="px-6 py-4 text-center">
                            <span class="px-2.5 py-1 rounded-full text-xs font-semibold ${badgeClasses}">${s.status_badge}</span>
                        </td>
                    </tr>
                `;
            }).join('');
        }

        // Render Date Range Comparison Chart
        renderDateRangeChart(summary.subjects);

    } catch (err) {
        console.error("Date range analysis failed:", err);
        showToast("Failed to compute date range analysis", "error");
    }
}
window.loadDateRangeAnalysis = loadDateRangeAnalysis;

function renderDateRangeChart(subjects) {
    const ctx = document.getElementById('chart-range-comparison');
    if (!ctx) return;

    if (state.charts.rangeChart) {
        state.charts.rangeChart.destroy();
    }

    const labels = subjects.map(s => s.code);
    const attendedData = subjects.map(s => s.attended);
    const absentData = subjects.map(s => s.absent);

    state.charts.rangeChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'Attended',
                    data: attendedData,
                    backgroundColor: '#10B981',
                    borderRadius: 6
                },
                {
                    label: 'Absent',
                    data: absentData,
                    backgroundColor: '#F43F5E',
                    borderRadius: 6
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: { stacked: true, grid: { display: false } },
                y: { stacked: true, beginAtZero: true }
            },
            plugins: {
                legend: { position: 'top' }
            }
        }
    });
}

// --- Subject Details & Attendance Calculator Modal ---
window.appOpenSubjectDetails = async function(subjectId) {
    try {
        const sub = await API.getSubjectDetails(subjectId);
        state.selectedSubject = sub;

        const modal = document.getElementById('modal-subject-details');
        modal.classList.remove('hidden');

        // Populate metadata
        document.getElementById('sub-modal-name').textContent = sub.name;
        document.getElementById('sub-modal-code').textContent = sub.code;
        document.getElementById('sub-modal-faculty').textContent = sub.faculty ? `Faculty: ${sub.faculty}` : '';
        document.getElementById('sub-modal-room').textContent = sub.room ? `Room: ${sub.room}` : '';

        // Stats
        document.getElementById('sub-modal-pct').textContent = `${sub.percentage}%`;
        document.getElementById('sub-modal-attended').textContent = sub.attended;
        document.getElementById('sub-modal-missed').textContent = sub.absent;
        document.getElementById('sub-modal-total').textContent = sub.total;

        // Calculator initial setup
        const targetSlider = document.getElementById('sub-calc-target-slider');
        const targetInput = document.getElementById('sub-calc-target-val');
        if (targetSlider && targetInput) {
            targetSlider.value = state.settings.required_attendance;
            targetInput.textContent = `${state.settings.required_attendance}%`;
            updateSubjectCalculator(sub, state.settings.required_attendance);
        }

        // Render monthly breakdown
        const monthlyContainer = document.getElementById('sub-modal-monthly');
        if (monthlyContainer) {
            if (!sub.monthly || sub.monthly.length === 0) {
                monthlyContainer.innerHTML = `<p class="text-xs text-slate-400 py-2">No monthly records.</p>`;
            } else {
                monthlyContainer.innerHTML = sub.monthly.map(m => `
                    <div class="flex items-center justify-between text-xs py-2 border-b border-slate-100 dark:border-slate-800">
                        <span class="font-medium text-slate-700 dark:text-slate-300">${m.month}</span>
                        <span class="text-slate-500">${m.attended} / ${m.total} classes</span>
                        <span class="font-bold ${m.percentage >= state.settings.required_attendance ? 'text-emerald-600' : 'text-rose-600'}">${m.percentage}%</span>
                    </div>
                `).join('');
            }
        }

        // Render recent history
        const historyContainer = document.getElementById('sub-modal-history');
        if (historyContainer) {
            if (!sub.history || sub.history.length === 0) {
                historyContainer.innerHTML = `<p class="text-xs text-slate-400 py-2">No history logs.</p>`;
            } else {
                historyContainer.innerHTML = sub.history.slice(0, 15).map(h => `
                    <div class="flex items-center justify-between text-xs py-2 border-b border-slate-100 dark:border-slate-800">
                        <div>
                            <span class="font-semibold text-slate-800 dark:text-slate-200">${formatDateDisplay(h.date)}</span>
                            ${h.period_number ? `<span class="text-slate-400 ml-1">(P${h.period_number})</span>` : ''}
                        </div>
                        <span class="px-2 py-0.5 rounded-full text-xs font-bold ${h.status === 'Present' ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-400' : 'bg-rose-100 text-rose-700 dark:bg-rose-950/60 dark:text-rose-400'}">
                            ${h.status}
                        </span>
                    </div>
                `).join('');
            }
        }

        if (window.lucide) window.lucide.createIcons();

    } catch (err) {
        console.error("Failed to load subject details:", err);
        showToast("Failed to load subject details", "error");
    }
};

function updateSubjectCalculator(sub, targetPercent) {
    const stats = AttendanceCalculator.calculateStats(sub.attended, sub.total, targetPercent);
    const canMissBox = document.getElementById('sub-calc-can-miss-box');
    const needAttendBox = document.getElementById('sub-calc-need-attend-box');

    if (stats.percentage >= targetPercent) {
        canMissBox.innerHTML = `
            <div class="text-xs text-emerald-700 dark:text-emerald-400 font-bold mb-1">SAFE TO MISS</div>
            <div class="text-2xl font-black text-emerald-600 dark:text-emerald-300">${stats.canMiss}</div>
            <div class="text-xs text-emerald-600/80 dark:text-emerald-400/80 mt-1">You can safely miss ${stats.canMiss} more class${stats.canMiss === 1 ? '' : 'es'} without dropping below ${targetPercent}%.</div>
        `;
        canMissBox.className = 'p-4 rounded-2xl bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-800';
    } else {
        canMissBox.innerHTML = `
            <div class="text-xs text-slate-500 font-bold mb-1">SAFE TO MISS</div>
            <div class="text-2xl font-black text-slate-400">0</div>
            <div class="text-xs text-slate-500 mt-1">Currently below target. Missing any class drops your percentage further.</div>
        `;
        canMissBox.className = 'p-4 rounded-2xl bg-slate-50 dark:bg-slate-800/40 border border-slate-200 dark:border-slate-800';
    }

    if (stats.percentage < targetPercent) {
        if (stats.isImpossible) {
            needAttendBox.innerHTML = `
                <div class="text-xs text-rose-700 dark:text-rose-400 font-bold mb-1">TARGET STATUS</div>
                <div class="text-lg font-black text-rose-600 dark:text-rose-300">Impossible</div>
                <div class="text-xs text-rose-600/80 dark:text-rose-400/80 mt-1">100% attendance cannot be achieved after missing a class.</div>
            `;
        } else {
            needAttendBox.innerHTML = `
                <div class="text-xs text-rose-700 dark:text-rose-400 font-bold mb-1">CATCH UP REQUIRED</div>
                <div class="text-2xl font-black text-rose-600 dark:text-rose-300">${stats.needToAttend}</div>
                <div class="text-xs text-rose-600/80 dark:text-rose-400/80 mt-1">You must attend approximately ${stats.needToAttend} consecutive class${stats.needToAttend === 1 ? '' : 'es'} to reach ${targetPercent}%.</div>
            `;
        }
        needAttendBox.className = 'p-4 rounded-2xl bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-800';
    } else {
        needAttendBox.innerHTML = `
            <div class="text-xs text-emerald-700 dark:text-emerald-400 font-bold mb-1">TARGET STATUS</div>
            <div class="text-lg font-black text-emerald-600 dark:text-emerald-300">Achieved!</div>
            <div class="text-xs text-emerald-600/80 dark:text-emerald-400/80 mt-1">Your attendance is already at or above ${targetPercent}%.</div>
        `;
        needAttendBox.className = 'p-4 rounded-2xl bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-800';
    }

    // Trigger simulator update
    runSimulator();
}

function runSimulator() {
    if (!state.selectedSubject) return;
    const simAttend = parseInt(document.getElementById('sim-input-attend')?.value || '0', 10);
    const simMiss = parseInt(document.getElementById('sim-input-miss')?.value || '0', 10);

    const sim = AttendanceCalculator.simulateFuture(
        state.selectedSubject.attended,
        state.selectedSubject.total,
        simAttend,
        simMiss
    );

    const resEl = document.getElementById('sim-result-pct');
    const diffEl = document.getElementById('sim-result-diff');

    if (resEl) resEl.textContent = `${sim.newPercentage}%`;
    if (diffEl) {
        const diff = Math.round((sim.newPercentage - state.selectedSubject.percentage) * 100) / 100;
        if (diff > 0) {
            diffEl.innerHTML = `<span class="text-emerald-600 font-semibold">+${diff}%</span>`;
        } else if (diff < 0) {
            diffEl.innerHTML = `<span class="text-rose-600 font-semibold">${diff}%</span>`;
        } else {
            diffEl.innerHTML = `<span class="text-slate-500">0% change</span>`;
        }
    }
}

// --- Monthly Analytics View ---
async function loadAnalytics() {
    try {
        const monthly = await API.getMonthlyAnalytics();
        const summary = await API.getSummary();

        // 1. Attendance Trend Line Chart
        const trendCtx = document.getElementById('chart-analytics-trend');
        if (trendCtx) {
            if (state.charts.analyticsTrend) state.charts.analyticsTrend.destroy();
            state.charts.analyticsTrend = new Chart(trendCtx, {
                type: 'line',
                data: {
                    labels: monthly.map(m => m.label),
                    datasets: [{
                        label: 'Attendance %',
                        data: monthly.map(m => m.percentage),
                        borderColor: '#4F46E5',
                        backgroundColor: 'rgba(79, 70, 229, 0.1)',
                        fill: true,
                        tension: 0.3,
                        pointBackgroundColor: '#4F46E5',
                        pointRadius: 5
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        y: { min: 0, max: 100, ticks: { callback: v => `${v}%` } }
                    }
                }
            });
        }

        // 2. Attended vs Absent Grouped Bar Chart
        const barCtx = document.getElementById('chart-analytics-monthly-bar');
        if (barCtx) {
            if (state.charts.analyticsMonthly) state.charts.analyticsMonthly.destroy();
            state.charts.analyticsMonthly = new Chart(barCtx, {
                type: 'bar',
                data: {
                    labels: monthly.map(m => m.label),
                    datasets: [
                        { label: 'Attended', data: monthly.map(m => m.attended), backgroundColor: '#10B981', borderRadius: 6 },
                        { label: 'Absent', data: monthly.map(m => m.absent), backgroundColor: '#F43F5E', borderRadius: 6 }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        x: { stacked: true },
                        y: { stacked: true, beginAtZero: true }
                    }
                }
            });
        }

        // 3. Subject-wise Comparison Horizontal Bar Chart
        const subCtx = document.getElementById('chart-analytics-subjects');
        if (subCtx) {
            if (state.charts.analyticsSubjects) state.charts.analyticsSubjects.destroy();
            state.charts.analyticsSubjects = new Chart(subCtx, {
                type: 'bar',
                data: {
                    labels: summary.subjects.map(s => s.code),
                    datasets: [{
                        label: 'Attendance %',
                        data: summary.subjects.map(s => s.percentage),
                        backgroundColor: summary.subjects.map(s => s.percentage >= state.settings.required_attendance ? '#10B981' : '#F43F5E'),
                        borderRadius: 6
                    }]
                },
                options: {
                    indexAxis: 'y',
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        x: { min: 0, max: 100, ticks: { callback: v => `${v}%` } }
                    }
                }
            });
        }

        // Monthly breakdown table
        const tbody = document.getElementById('analytics-monthly-table-body');
        if (tbody) {
            tbody.innerHTML = monthly.map(m => `
                <tr class="hover:bg-slate-50 dark:hover:bg-slate-800/50 transition">
                    <td class="px-6 py-4 font-semibold text-slate-900 dark:text-white">${m.label}</td>
                    <td class="px-6 py-4 text-center font-medium">${m.attended}</td>
                    <td class="px-6 py-4 text-center font-medium">${m.absent}</td>
                    <td class="px-6 py-4 text-center font-medium">${m.total}</td>
                    <td class="px-6 py-4 text-center">
                        <span class="font-bold ${m.percentage >= state.settings.required_attendance ? 'text-emerald-600' : 'text-rose-600'}">${m.percentage}%</span>
                    </td>
                </tr>
            `).join('');
        }

    } catch (err) {
        console.error("Failed to load analytics:", err);
        showToast("Failed to load analytics", "error");
    }
}

// --- Calendar View ---
async function loadCalendar() {
    try {
        const calData = await API.getCalendarData(state.calendarMonth);

        // Parse year & month
        const [year, month] = state.calendarMonth.split('-').map(Number);
        const monthDate = new Date(year, month - 1, 1);
        const monthName = monthDate.toLocaleString('default', { month: 'long', year: 'numeric' });

        document.getElementById('cal-month-label').textContent = monthName;

        const firstDayOfWeek = monthDate.getDay(); // 0 is Sunday
        const daysInMonth = new Date(year, month, 0).getDate();

        const grid = document.getElementById('calendar-days-grid');
        if (!grid) return;

        let html = '';

        // Empty cells before start of month
        for (let i = 0; i < firstDayOfWeek; i++) {
            html += `<div class="calendar-day-cell p-2 bg-slate-50/50 dark:bg-slate-900/30 border border-slate-100 dark:border-slate-800/50 rounded-xl opacity-40"></div>`;
        }

        // Days in month
        const todayStr = state.todayDate;
        for (let d = 1; d <= daysInMonth; d++) {
            const dateStr = `${year}-${String(month).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
            const info = calData[dateStr];
            const isToday = (dateStr === todayStr);

            let statusBadge = '';
            if (info && info.total > 0) {
                if (info.status === 'all_present') {
                    statusBadge = `<span class="inline-flex items-center gap-1 text-[11px] font-bold px-2 py-0.5 rounded-md bg-emerald-100 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-400">🟢 ${info.attended}/${info.total}</span>`;
                } else if (info.status === 'all_absent') {
                    statusBadge = `<span class="inline-flex items-center gap-1 text-[11px] font-bold px-2 py-0.5 rounded-md bg-rose-100 dark:bg-rose-950/60 text-rose-700 dark:text-rose-400">🔴 0/${info.total}</span>`;
                } else {
                    statusBadge = `<span class="inline-flex items-center gap-1 text-[11px] font-bold px-2 py-0.5 rounded-md bg-amber-100 dark:bg-amber-950/60 text-amber-700 dark:text-amber-400">🟡 ${info.attended}/${info.total}</span>`;
                }
            }

            html += `
                <div class="calendar-day-cell p-2.5 bg-white dark:bg-slate-900 border ${isToday ? 'border-indigo-500 ring-2 ring-indigo-500/30' : 'border-slate-200 dark:border-slate-800'} rounded-2xl hover:border-indigo-400 transition cursor-pointer flex flex-col justify-between"
                     onclick="window.appOpenCalendarDay('${dateStr}')">
                    <div class="flex items-center justify-between">
                        <span class="text-sm font-bold ${isToday ? 'text-indigo-600 dark:text-indigo-400' : 'text-slate-800 dark:text-slate-200'}">${d}</span>
                        ${isToday ? `<span class="text-[10px] font-extrabold uppercase px-1.5 py-0.2 bg-indigo-100 dark:bg-indigo-950 text-indigo-600 rounded">Today</span>` : ''}
                    </div>
                    <div class="mt-2 flex flex-wrap gap-1">
                        ${statusBadge}
                    </div>
                </div>
            `;
        }

        grid.innerHTML = html;

    } catch (err) {
        console.error("Calendar load failed:", err);
        showToast("Failed to load calendar", "error");
    }
}

window.appChangeCalendarMonth = function(delta) {
    const [year, month] = state.calendarMonth.split('-').map(Number);
    const d = new Date(year, month - 1 + delta, 1);
    state.calendarMonth = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
    loadCalendar();
};

window.appOpenCalendarDay = function(dateStr) {
    const dateInput = document.getElementById('today-date-picker');
    if (dateInput) {
        dateInput.value = dateStr;
    }
    switchView('today');
};

// --- Settings View ---
async function loadSettings() {
    try {
        const s = await API.getSettings();
        state.settings = s;

        document.getElementById('setting-required-att').value = s.required_attendance;
        document.getElementById('setting-warning-th').value = s.warning_threshold;
        document.getElementById('setting-critical-th').value = s.critical_threshold;
        document.getElementById('setting-college-name').value = s.college_name || '';
        document.getElementById('setting-student-name').value = s.student_name || '';
        document.getElementById('setting-theme').value = s.theme || 'system';

    } catch (err) {
        console.error("Settings load failed:", err);
    }
}

window.appSaveSettings = async function(e) {
    if (e) e.preventDefault();
    const payload = {
        required_attendance: parseFloat(document.getElementById('setting-required-att').value) || 75.0,
        warning_threshold: parseFloat(document.getElementById('setting-warning-th').value) || 75.0,
        critical_threshold: parseFloat(document.getElementById('setting-critical-th').value) || 65.0,
        college_name: document.getElementById('setting-college-name').value.trim(),
        student_name: document.getElementById('setting-student-name').value.trim(),
        theme: document.getElementById('setting-theme').value
    };

    try {
        const res = await API.saveSettings(payload);
        state.settings = res.settings;
        applyTheme(state.settings.theme);
        showToast("Settings saved successfully!", "success");
    } catch (err) {
        showToast("Failed to save settings", "error");
    }
};

// --- Excel Export Modal & Logic ---
window.appUpdateExportScopeUI = function() {
    const selected = document.querySelector('input[name="export-scope"]:checked')?.value || 'all';
    const rangeFields = document.getElementById('export-range-fields');
    const subFields = document.getElementById('export-subject-fields');

    if (rangeFields) {
        rangeFields.classList.toggle('hidden', selected !== 'range');
        if (selected === 'range') {
            const fromInput = document.getElementById('export-from-date');
            const toInput = document.getElementById('export-to-date');
            if (fromInput && !fromInput.value) {
                fromInput.value = state.rangeFromDate || new Date(new Date().getFullYear(), new Date().getMonth(), 1).toISOString().split('T')[0];
            }
            if (toInput && !toInput.value) {
                toInput.value = state.rangeToDate || new Date().toISOString().split('T')[0];
            }
        }
    }

    if (subFields) {
        subFields.classList.toggle('hidden', selected !== 'subject');
        if (selected === 'subject') {
            const subSelect = document.getElementById('export-sub-select');
            if (subSelect && (!subSelect.value || subSelect.options.length === 0)) {
                if (state.subjects && state.subjects.length > 0) {
                    subSelect.innerHTML = state.subjects.map(s => `<option value="${s.id}">${s.code} - ${s.name}</option>`).join('');
                }
            }
        }
    }
};

window.appOpenExportModal = async function(scopePreset = 'all', subjectId = null) {
    const modal = document.getElementById('modal-export-excel');
    if (!modal) return;

    // Load subjects
    try {
        if (!state.subjects || state.subjects.length === 0) {
            state.subjects = await API.getSubjects();
        }
    } catch (e) {
        console.error("Failed to load subjects for export modal:", e);
    }

    // Populate subjects in export dropdown
    const subSelect = document.getElementById('export-sub-select');
    if (subSelect && state.subjects) {
        subSelect.innerHTML = state.subjects.map(s => `<option value="${s.id}">${s.code} - ${s.name}</option>`).join('');
        const effectiveSubId = subjectId || (state.selectedSubject ? state.selectedSubject.id : null);
        if (effectiveSubId) {
            subSelect.value = effectiveSubId;
        }
    }

    // Prefill date range fields
    const fromInput = document.getElementById('export-from-date');
    const toInput = document.getElementById('export-to-date');
    if (fromInput) {
        fromInput.value = state.rangeFromDate || new Date(new Date().getFullYear(), new Date().getMonth(), 1).toISOString().split('T')[0];
    }
    if (toInput) {
        toInput.value = state.rangeToDate || new Date().toISOString().split('T')[0];
    }

    // Set scope radio
    const targetScope = (subjectId ? 'subject' : scopePreset) || 'all';
    const scopeRadio = document.querySelector(`input[name="export-scope"][value="${targetScope}"]`);
    if (scopeRadio) {
        scopeRadio.checked = true;
    }

    window.appUpdateExportScopeUI();
    modal.classList.remove('hidden');
    if (window.lucide) window.lucide.createIcons();
};

window.appExecuteExportExcel = function() {
    const scope = document.querySelector('input[name="export-scope"]:checked')?.value || 'all';
    let fromDate = document.getElementById('export-from-date')?.value || '';
    let toDate = document.getElementById('export-to-date')?.value || '';
    const subjectId = document.getElementById('export-sub-select')?.value || '';

    if (scope === 'range') {
        if (!fromDate && !toDate) {
            fromDate = state.rangeFromDate || new Date(new Date().getFullYear(), new Date().getMonth(), 1).toISOString().split('T')[0];
            toDate = state.rangeToDate || new Date().toISOString().split('T')[0];
            const fromInput = document.getElementById('export-from-date');
            const toInput = document.getElementById('export-to-date');
            if (fromInput) fromInput.value = fromDate;
            if (toInput) toInput.value = toDate;
        }
    }

    if (scope === 'subject') {
        if (!subjectId) {
            showToast("Please select a subject to export", "warning");
            return;
        }
    }

    const url = API.getExcelExportUrl(scope, {
        from_date: fromDate,
        to_date: toDate,
        subject_id: subjectId
    });

    // Close modal and trigger download
    document.getElementById('modal-export-excel')?.classList.add('hidden');
    showToast("Generating Excel file...", "info");
    window.location.href = url;
};

window.appExportAnalyticsExcel = function() {
    const url = API.getAnalyticsExportUrl();
    showToast("Exporting Monthly Analytics report...", "info");
    window.location.href = url;
};

window.appExportLogsExcel = function() {
    const fromDate = document.getElementById('records-filter-from')?.value || '';
    const toDate = document.getElementById('records-filter-to')?.value || '';
    const subjectId = document.getElementById('records-filter-subject')?.value || '';
    const status = document.getElementById('records-filter-status')?.value || '';
    const sort = document.getElementById('records-filter-sort')?.value || 'date';
    const order = document.getElementById('records-filter-order')?.value || 'DESC';

    const url = API.getLogsExportUrl({
        from_date: fromDate,
        to_date: toDate,
        subject_id: subjectId,
        status: status,
        sort: sort,
        order: order
    });
    showToast("Exporting filtered attendance logs...", "info");
    window.location.href = url;
};

// --- Backup & Restore Logic ---
window.appExportBackup = async function() {
    try {
        const data = await API.exportBackup();
        const jsonStr = JSON.stringify(data, null, 2);
        const blob = new Blob([jsonStr], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `attendance_backup_${new Date().toISOString().slice(0, 10)}.json`;
        a.click();
        URL.revokeObjectURL(url);
        showToast("Backup exported successfully!", "success");
    } catch (err) {
        showToast("Backup export failed", "error");
    }
};

window.appImportBackup = function() {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.json';
    input.onchange = async (e) => {
        const file = e.target.files[0];
        if (!file) return;

        try {
            const text = await file.text();
            const data = JSON.parse(text);

            if (!data.subjects || !data.attendance) {
                showToast("Invalid backup file format", "error");
                return;
            }

            const ok = await confirmAction("Restore Backup Data?", `This will overwrite existing data with ${data.subjects.length} subjects and ${data.attendance.length} attendance records.`, "Restore Now", false);
            if (!ok) return;

            await API.importBackup(data);
            showToast("Backup restored successfully!", "success");
            loadDashboard();
        } catch (err) {
            showToast("Failed to read backup file", "error");
        }
    };
    input.click();
};

window.appLoadSampleData = async function() {
    const ok = await confirmAction("Load Sample College Dataset?", "This will populate your schedule with 6 realistic CS courses, weekly timetable, and 30 days of attendance history.", "Load Sample Data", false);
    if (!ok) return;

    try {
        await API.seedSampleData();
        showToast("Sample data loaded successfully!", "success");
        loadDashboard();
    } catch (err) {
        showToast("Failed to seed sample data", "error");
    }
};

window.appClearAllAttendanceRecords = async function() {
    const ok = await confirmAction("Clear All Attendance Logs?", "This will delete all past attendance logs. Your subjects and timetable will be kept intact.", "Clear Attendance", true);
    if (!ok) return;

    try {
        await API.clearAttendance();
        showToast("Attendance history cleared", "info");
        loadDashboard();
    } catch (err) {
        showToast("Clear failed", "error");
    }
};

window.appResetFactory = async function() {
    const ok = await confirmAction("Factory Reset Application?", "Warning: This will permanently delete ALL subjects, timetable, attendance records, and restore default settings.", "Reset Everything", true);
    if (!ok) return;

    try {
        await API.resetAll();
        showToast("Application reset to factory state", "info");
        loadDashboard();
    } catch (err) {
        showToast("Reset failed", "error");
    }
};

// --- Add / Edit Subject Modal ---
window.appOpenAddSubjectModal = function() {
    const modal = document.getElementById('modal-subject-form');
    document.getElementById('subject-form-title').textContent = "Add New Subject";
    document.getElementById('subject-form-id').value = "";
    document.getElementById('sub-input-name').value = "";
    document.getElementById('sub-input-code').value = "";
    document.getElementById('sub-input-faculty').value = "";
    document.getElementById('sub-input-room').value = "";
    document.getElementById('sub-input-color').value = "#3B82F6";
    modal.classList.remove('hidden');
};

window.appOpenEditSubjectModal = function() {
    if (!state.selectedSubject) return;
    const s = state.selectedSubject;
    document.getElementById('modal-subject-details').classList.add('hidden');
    const modal = document.getElementById('modal-subject-form');
    document.getElementById('subject-form-title').textContent = "Edit Subject";
    document.getElementById('subject-form-id').value = s.id;
    document.getElementById('sub-input-name').value = s.name;
    document.getElementById('sub-input-code').value = s.code;
    document.getElementById('sub-input-faculty').value = s.faculty || "";
    document.getElementById('sub-input-room').value = s.room || "";
    document.getElementById('sub-input-color').value = s.color || "#3B82F6";
    modal.classList.remove('hidden');
};

window.appDeleteCurrentSubject = async function() {
    if (!state.selectedSubject) return;
    const ok = await confirmAction(`Delete ${state.selectedSubject.name}?`, "This will remove the subject and all its timetable periods and attendance records.", "Delete Subject", true);
    if (!ok) return;

    try {
        await API.deleteSubject(state.selectedSubject.id);
        document.getElementById('modal-subject-details').classList.add('hidden');
        showToast("Subject deleted", "info");
        loadDashboard();
    } catch (err) {
        showToast("Failed to delete subject", "error");
    }
};

window.appSaveSubjectForm = async function(e) {
    if (e) e.preventDefault();
    const id = document.getElementById('subject-form-id').value;
    const name = document.getElementById('sub-input-name').value.trim();
    const code = document.getElementById('sub-input-code').value.trim();
    const faculty = document.getElementById('sub-input-faculty').value.trim();
    const room = document.getElementById('sub-input-room').value.trim();
    const color = document.getElementById('sub-input-color').value;

    if (!name || !code) {
        showToast("Subject name and code are required", "warning");
        return;
    }

    try {
        if (id) {
            await API.updateSubject(id, { name, code, faculty, room, color });
            showToast("Subject updated", "success");
        } else {
            await API.createSubject({ name, code, faculty, room, color });
            showToast("Subject created", "success");
        }
        document.getElementById('modal-subject-form').classList.add('hidden');
        loadDashboard();
    } catch (err) {
        showToast("Failed to save subject", "error");
    }
};

// --- Add / Edit Timetable Period Modal & Master Slot Helpers ---
function populatePeriodSlotsDropdown(selectedSlotId = null) {
    const slotSelect = document.getElementById('period-select-slot');
    if (!slotSelect) return;

    const slots = state.periodSlots || [];
    let html = `<option value="">-- Choose a Defined Period Slot --</option>`;
    slots.forEach(s => {
        const isSelected = selectedSlotId && (String(s.id) === String(selectedSlotId));
        html += `<option value="${s.id}" ${isSelected ? 'selected' : ''}>P${s.slot_number}: ${s.start_time} - ${s.end_time} (${s.label || 'Period ' + s.slot_number})</option>`;
    });
    html += `<option value="custom" ${selectedSlotId === 'custom' ? 'selected' : ''}>✏️ Custom Timing (Free Entry)</option>`;

    slotSelect.innerHTML = html;
}

window.appOnPeriodSlotSelect = function(val) {
    if (!val || val === 'custom') {
        return;
    }
    const slot = (state.periodSlots || []).find(s => String(s.id) === String(val));
    if (slot) {
        const numInput = document.getElementById('period-input-num');
        const startInput = document.getElementById('period-input-start');
        const endInput = document.getElementById('period-input-end');
        if (numInput) numInput.value = slot.slot_number;
        if (startInput) startInput.value = slot.start_time;
        if (endInput) endInput.value = slot.end_time;
    }
};

window.appOpenAddPeriodModal = async function(preselectSlotId = null) {
    try {
        state.subjects = await API.getSubjects();
        if (state.subjects.length === 0) {
            showToast("Please add at least one subject first", "warning");
            window.appOpenAddSubjectModal();
            return;
        }

        if (!state.periodSlots || state.periodSlots.length === 0) {
            state.periodSlots = await API.getPeriodSlots();
        }

        const modal = document.getElementById('modal-period-form');
        document.getElementById('period-form-title').textContent = `Add Period for ${state.timetableSelectedDay}`;
        document.getElementById('period-form-id').value = "";
        document.getElementById('period-input-day').value = state.timetableSelectedDay;

        // Populate subjects dropdown
        const subSelect = document.getElementById('period-input-subject');
        subSelect.innerHTML = state.subjects.map(s => `<option value="${s.id}">${s.code} - ${s.name}</option>`).join('');

        // Clear room and faculty
        const roomInput = document.getElementById('period-input-room');
        const facultyInput = document.getElementById('period-input-faculty');
        if (roomInput) roomInput.value = "";
        if (facultyInput) facultyInput.value = "";

        // Hide delete button when adding new period
        const delBtn = document.getElementById('period-form-delete-btn');
        if (delBtn) delBtn.classList.add('hidden');

        // Determine preselected slot
        let targetSlot = null;
        if (preselectSlotId) {
            targetSlot = (state.periodSlots || []).find(s => String(s.id) === String(preselectSlotId));
        } else {
            const nextNum = (state.timetable?.length || 0) + 1;
            targetSlot = (state.periodSlots || []).find(s => s.slot_number === nextNum);
        }

        populatePeriodSlotsDropdown(targetSlot ? targetSlot.id : '');

        if (targetSlot) {
            document.getElementById('period-input-num').value = targetSlot.slot_number;
            document.getElementById('period-input-start').value = targetSlot.start_time;
            document.getElementById('period-input-end').value = targetSlot.end_time;
        } else {
            const nextNum = (state.timetable?.length || 0) + 1;
            document.getElementById('period-input-num').value = nextNum;
            document.getElementById('period-input-start').value = "09:00";
            document.getElementById('period-input-end').value = "09:50";
        }

        modal.classList.remove('hidden');
        if (window.lucide) window.lucide.createIcons();
    } catch (err) {
        console.error("Failed to open add period modal:", err);
        showToast("Failed to initialize period form", "error");
    }
};

window.appOpenEditPeriodModal = async function(periodId) {
    const period = state.timetable.find(p => p.id === periodId);
    if (!period) return;

    try {
        state.subjects = await API.getSubjects();
        if (!state.periodSlots || state.periodSlots.length === 0) {
            state.periodSlots = await API.getPeriodSlots();
        }

        const modal = document.getElementById('modal-period-form');
        document.getElementById('period-form-title').textContent = "Edit Timetable Period";
        document.getElementById('period-form-id').value = period.id;
        document.getElementById('period-input-day').value = period.day;
        document.getElementById('period-input-num').value = period.period_number;
        document.getElementById('period-input-start').value = period.start_time;
        document.getElementById('period-input-end').value = period.end_time;

        const roomInput = document.getElementById('period-input-room');
        const facultyInput = document.getElementById('period-input-faculty');
        if (roomInput) roomInput.value = period.room || "";
        if (facultyInput) facultyInput.value = period.faculty || "";

        const subSelect = document.getElementById('period-input-subject');
        subSelect.innerHTML = state.subjects.map(s => `<option value="${s.id}" ${s.id === period.subject_id ? 'selected' : ''}>${s.code} - ${s.name}</option>`).join('');

        // Match period with a slot
        const matchingSlot = (state.periodSlots || []).find(s => 
            (period.slot_id && s.id === period.slot_id) ||
            (s.slot_number === period.period_number && s.start_time === period.start_time && s.end_time === period.end_time)
        );

        populatePeriodSlotsDropdown(matchingSlot ? matchingSlot.id : 'custom');

        // Show delete button when editing saved period
        const delBtn = document.getElementById('period-form-delete-btn');
        if (delBtn) delBtn.classList.remove('hidden');

        modal.classList.remove('hidden');
        if (window.lucide) window.lucide.createIcons();
    } catch (err) {
        console.error("Failed to open edit period modal:", err);
        showToast("Failed to load period details", "error");
    }
};

window.appDeletePeriodFromForm = async function() {
    const id = document.getElementById('period-form-id').value;
    if (!id) return;

    const ok = await confirmAction("Delete Saved Period?", "Are you sure you want to permanently remove this period from your timetable?", "Delete Period", true);
    if (!ok) return;

    try {
        await API.deleteTimetablePeriod(id);
        showToast("Period removed from timetable", "success");
        document.getElementById('modal-period-form').classList.add('hidden');
        loadTimetable();
    } catch (err) {
        showToast("Failed to delete period", "error");
    }
};

window.appSavePeriodForm = async function(e) {
    if (e) e.preventDefault();
    const id = document.getElementById('period-form-id').value;
    const day = document.getElementById('period-input-day').value;
    const periodNumber = parseInt(document.getElementById('period-input-num').value, 10);
    const startTime = document.getElementById('period-input-start').value;
    const endTime = document.getElementById('period-input-end').value;
    const subjectId = parseInt(document.getElementById('period-input-subject').value, 10);
    const room = document.getElementById('period-input-room')?.value?.trim() || "";
    const faculty = document.getElementById('period-input-faculty')?.value?.trim() || "";

    const slotVal = document.getElementById('period-select-slot')?.value;
    const slotId = (slotVal && slotVal !== 'custom' && !isNaN(slotVal)) ? parseInt(slotVal, 10) : null;

    try {
        if (id) {
            await API.updateTimetablePeriod(id, {
                day, period_number: periodNumber, start_time: startTime, end_time: endTime, subject_id: subjectId,
                room, faculty, slot_id: slotId
            });
            showToast("Period updated", "success");
        } else {
            await API.addTimetablePeriod({
                day, period_number: periodNumber, start_time: startTime, end_time: endTime, subject_id: subjectId,
                room, faculty, slot_id: slotId
            });
            showToast("Period added", "success");
        }
        document.getElementById('modal-period-form').classList.add('hidden');
        loadTimetable();
    } catch (err) {
        showToast("Failed to save period", "error");
    }
};

// --- Period Slot Form & CRUD Operations ---
window.appOpenCreatePeriodSlotModal = function(fromTimetable = false) {
    state._createSlotFromTimetable = Boolean(fromTimetable);
    const modal = document.getElementById('modal-period-slot-form');
    if (!modal) return;

    document.getElementById('slot-form-title').textContent = "Create New Period Slot";
    document.getElementById('slot-form-id').value = "";

    const slots = state.periodSlots || [];
    const maxNum = slots.length > 0 ? Math.max(...slots.map(s => s.slot_number || 0)) : 0;
    const nextNum = maxNum + 1;

    document.getElementById('slot-input-number').value = nextNum;
    document.getElementById('slot-input-label').value = `Period ${nextNum}`;

    if (slots.length > 0) {
        const sorted = [...slots].sort((a, b) => (a.slot_number || 0) - (b.slot_number || 0));
        const lastSlot = sorted[sorted.length - 1];
        if (lastSlot && lastSlot.end_time) {
            document.getElementById('slot-input-start').value = lastSlot.end_time;
            const [h, m] = lastSlot.end_time.split(':').map(Number);
            let totalM = h * 60 + m + 50;
            let nh = Math.floor(totalM / 60) % 24;
            let nm = totalM % 60;
            document.getElementById('slot-input-end').value = `${String(nh).padStart(2, '0')}:${String(nm).padStart(2, '0')}`;
        } else {
            document.getElementById('slot-input-start').value = "09:00";
            document.getElementById('slot-input-end').value = "09:50";
        }
    } else {
        document.getElementById('slot-input-start').value = "09:00";
        document.getElementById('slot-input-end').value = "09:50";
    }

    const delBtn = document.getElementById('slot-form-delete-btn');
    if (delBtn) delBtn.classList.add('hidden');

    modal.classList.remove('hidden');
    if (window.lucide) window.lucide.createIcons();
};

window.appOpenEditPeriodSlotModal = function(slotId) {
    state._createSlotFromTimetable = false;
    const slot = (state.periodSlots || []).find(s => s.id === slotId);
    if (!slot) return;

    const modal = document.getElementById('modal-period-slot-form');
    if (!modal) return;

    document.getElementById('slot-form-title').textContent = `Edit Period Slot (P${slot.slot_number})`;
    document.getElementById('slot-form-id').value = slot.id;
    document.getElementById('slot-input-number').value = slot.slot_number;
    document.getElementById('slot-input-label').value = slot.label || `Period ${slot.slot_number}`;
    document.getElementById('slot-input-start').value = slot.start_time;
    document.getElementById('slot-input-end').value = slot.end_time;

    const delBtn = document.getElementById('slot-form-delete-btn');
    if (delBtn) delBtn.classList.remove('hidden');

    modal.classList.remove('hidden');
    if (window.lucide) window.lucide.createIcons();
};

window.appSavePeriodSlotForm = async function(e) {
    if (e) e.preventDefault();
    const id = document.getElementById('slot-form-id').value;
    const slotNumber = parseInt(document.getElementById('slot-input-number').value, 10);
    const label = document.getElementById('slot-input-label').value.trim() || `Period ${slotNumber}`;
    const startTime = document.getElementById('slot-input-start').value;
    const endTime = document.getElementById('slot-input-end').value;

    if (!startTime || !endTime) {
        showToast("Start time and end time are required", "warning");
        return;
    }
    if (!slotNumber || slotNumber < 1) {
        showToast("Period number must be 1 or higher", "warning");
        return;
    }

    try {
        let savedSlot = null;
        if (id) {
            const res = await API.updatePeriodSlot(id, {
                slot_number: slotNumber,
                label,
                start_time: startTime,
                end_time: endTime
            });
            savedSlot = res.slot || { id: parseInt(id, 10), slot_number: slotNumber, label, start_time: startTime, end_time: endTime };
            showToast("Period slot updated!", "success");
        } else {
            const res = await API.addPeriodSlot({
                slot_number: slotNumber,
                label,
                start_time: startTime,
                end_time: endTime
            });
            savedSlot = res.slot || { id: res.id, slot_number: slotNumber, label, start_time: startTime, end_time: endTime };
            showToast("New period slot created!", "success");
        }

        document.getElementById('modal-period-slot-form')?.classList.add('hidden');

        state.periodSlots = await API.getPeriodSlots();

        const badge = document.getElementById('timetable-period-slots-count');
        if (badge) badge.textContent = state.periodSlots.length;

        if (state._createSlotFromTimetable) {
            populatePeriodSlotsDropdown(savedSlot ? savedSlot.id : null);
            if (savedSlot) {
                document.getElementById('period-input-num').value = savedSlot.slot_number;
                document.getElementById('period-input-start').value = savedSlot.start_time;
                document.getElementById('period-input-end').value = savedSlot.end_time;
            }
        } else {
            loadPeriodSlots();
        }
    } catch (err) {
        console.error("Failed to save period slot:", err);
        showToast(err.message || "Failed to save period slot", "error");
    }
};

window.appDeletePeriodSlot = async function(slotId) {
    const ok = await confirmAction(
        "Delete Period Slot?",
        "Are you sure you want to permanently delete this period slot? Any existing timetable classes scheduled at this time will remain intact.",
        "Delete Slot",
        true
    );
    if (!ok) return;

    try {
        await API.deletePeriodSlot(slotId);
        showToast("Period slot deleted", "info");
        state.periodSlots = await API.getPeriodSlots();
        const badge = document.getElementById('timetable-period-slots-count');
        if (badge) badge.textContent = state.periodSlots.length;
        loadPeriodSlots();
    } catch (err) {
        console.error("Failed to delete period slot:", err);
        showToast("Failed to delete period slot", "error");
    }
};

window.appDeletePeriodSlotFromForm = async function() {
    const id = document.getElementById('slot-form-id').value;
    if (!id) return;
    document.getElementById('modal-period-slot-form')?.classList.add('hidden');
    await window.appDeletePeriodSlot(id);
};

window.appResetPeriodSlotsDefaults = async function() {
    const ok = await confirmAction(
        "Restore Standard Periods?",
        "This will reset your period slots to standard 6 college periods (09:00 - 15:10).",
        "Restore Defaults",
        false
    );
    if (!ok) return;

    try {
        const res = await API.resetPeriodSlots();
        state.periodSlots = res.slots || (await API.getPeriodSlots());
        showToast("Restored standard 6 periods", "success");
        const badge = document.getElementById('timetable-period-slots-count');
        if (badge) badge.textContent = state.periodSlots.length;
        loadPeriodSlots();
    } catch (err) {
        console.error("Failed to reset period slots:", err);
        showToast("Failed to restore standard periods", "error");
    }
};

// --- Duplicate Day Modal ---
let duplicateModalState = {
    allPeriods: [],
    dayMap: {}, // day -> array of periods
    sourceDay: 'Monday',
    preferTargetDay: null
};

window.appOpenDuplicateDayModal = async function(preferTargetDay = null) {
    const modal = document.getElementById('modal-duplicate-day');
    if (!modal) return;
    
    duplicateModalState.preferTargetDay = preferTargetDay;

    try {
        // Fetch all periods across all days to have fresh data
        const allPeriods = await API.getTimetable();
        duplicateModalState.allPeriods = allPeriods;
        
        // Build map
        const dayMap = {};
        DAYS_OF_WEEK.forEach(d => { dayMap[d] = []; });
        allPeriods.forEach(p => {
            if (dayMap[p.day]) dayMap[p.day].push(p);
        });
        duplicateModalState.dayMap = dayMap;

        // Check if any days have periods
        const daysWithPeriods = DAYS_OF_WEEK.filter(d => dayMap[d].length > 0);
        const warningEl = document.getElementById('dup-no-source-warning');
        const formContainer = document.getElementById('dup-form-container');
        const submitBtn = document.getElementById('dup-submit-btn');

        if (daysWithPeriods.length === 0) {
            if (warningEl) warningEl.classList.remove('hidden');
            if (formContainer) formContainer.classList.add('hidden');
            if (submitBtn) submitBtn.disabled = true;
            modal.classList.remove('hidden');
            if (window.lucide) window.lucide.createIcons();
            return;
        }

        if (warningEl) warningEl.classList.add('hidden');
        if (formContainer) formContainer.classList.remove('hidden');
        if (submitBtn) submitBtn.disabled = false;

        // Determine default source day
        let defaultSource = null;
        if (preferTargetDay && preferTargetDay !== '') {
            // User clicked duplicate on an empty day (target is preferTargetDay)
            // Source should be first day that HAS periods (excluding preferTargetDay if any)
            defaultSource = daysWithPeriods.find(d => d !== preferTargetDay) || daysWithPeriods[0];
        } else {
            // Clicked from header: if current selected day has periods, use it; else first day with periods
            if (dayMap[state.timetableSelectedDay]?.length > 0) {
                defaultSource = state.timetableSelectedDay;
            } else {
                defaultSource = daysWithPeriods[0];
            }
        }
        duplicateModalState.sourceDay = defaultSource;

        // Populate Source Day Dropdown
        const sourceSelect = document.getElementById('dup-source-day-select');
        if (sourceSelect) {
            sourceSelect.innerHTML = DAYS_OF_WEEK.map(d => {
                const count = dayMap[d]?.length || 0;
                const badge = count > 0 ? `(${count} ${count === 1 ? 'period' : 'periods'})` : `(empty)`;
                const isSelected = d === defaultSource ? 'selected' : '';
                const disabled = count === 0 ? 'disabled' : '';
                return `<option value="${d}" ${isSelected} ${disabled}>${d} ${badge}</option>`;
            }).join('');
        }

        // Render preview and target checkboxes
        window.appRenderDuplicateTargetsAndPreview();

        modal.classList.remove('hidden');
        if (window.lucide) window.lucide.createIcons();

    } catch (err) {
        console.error("Failed to load duplicate day data:", err);
        showToast("Failed to initialize duplicate modal", "error");
    }
};

window.appOnDuplicateSourceChanged = function() {
    const sourceSelect = document.getElementById('dup-source-day-select');
    if (!sourceSelect) return;
    duplicateModalState.sourceDay = sourceSelect.value;
    window.appRenderDuplicateTargetsAndPreview();
};

window.appRenderDuplicateTargetsAndPreview = function() {
    const { sourceDay, dayMap, preferTargetDay } = duplicateModalState;
    const sourcePeriods = dayMap[sourceDay] || [];

    // 1. Update source badge & preview snippet
    const badgeEl = document.getElementById('dup-source-count-badge');
    if (badgeEl) {
        badgeEl.textContent = `${sourcePeriods.length} ${sourcePeriods.length === 1 ? 'period' : 'periods'} scheduled`;
    }

    const previewEl = document.getElementById('dup-source-preview');
    if (previewEl) {
        if (sourcePeriods.length === 0) {
            previewEl.innerHTML = `<span class="text-amber-600 dark:text-amber-400">⚠️ No periods scheduled for ${sourceDay}.</span>`;
        } else {
            const listHtml = sourcePeriods.map(p => `
                <div class="flex items-center justify-between py-0.5">
                    <span class="font-semibold text-slate-800 dark:text-slate-200">P${p.period_number}: ${p.subject_name || p.subject_code}</span>
                    <span class="text-[11px] text-slate-400 font-mono">${p.start_time} - ${p.end_time}</span>
                </div>
            `).join('');
            previewEl.innerHTML = `
                <div class="font-bold text-[11px] text-slate-500 uppercase tracking-wider mb-1">Preview of periods to copy:</div>
                <div class="max-h-28 overflow-y-auto space-y-1 pr-1">${listHtml}</div>
            `;
        }
    }

    // 2. Render Target Checkboxes (exclude sourceDay)
    const container = document.getElementById('dup-target-checkboxes');
    if (container) {
        const availableTargets = DAYS_OF_WEEK.filter(d => d !== sourceDay);
        container.innerHTML = availableTargets.map(d => {
            const count = dayMap[d]?.length || 0;
            // Check if this is the preferred target day
            const isPreferred = preferTargetDay === d;
            const checkedAttr = isPreferred ? 'checked' : '';
            const statusLabel = count === 0 ? '<span class="text-emerald-600 dark:text-emerald-400 text-[10px]">empty</span>' : `<span class="text-amber-600 dark:text-amber-400 text-[10px]">${count} existing</span>`;

            return `
                <label class="flex items-center gap-2 p-2.5 rounded-xl border border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800 cursor-pointer transition select-none text-xs">
                    <input type="checkbox" name="dup-target-day-cb" value="${d}" ${checkedAttr} class="w-4 h-4 text-indigo-600 rounded border-slate-300 dark:border-slate-700 focus:ring-indigo-500">
                    <div class="flex flex-col">
                        <span class="font-semibold text-slate-900 dark:text-white">${d}</span>
                        ${statusLabel}
                    </div>
                </label>
            `;
        }).join('');
    }
};

window.appDupSelectEmptyTargets = function() {
    const { dayMap, sourceDay } = duplicateModalState;
    document.querySelectorAll('input[name="dup-target-day-cb"]').forEach(cb => {
        const d = cb.value;
        const count = dayMap[d]?.length || 0;
        cb.checked = (count === 0 && d !== sourceDay);
    });
};

window.appDupSelectAllTargets = function() {
    document.querySelectorAll('input[name="dup-target-day-cb"]').forEach(cb => {
        cb.checked = true;
    });
};

window.appDupClearTargets = function() {
    document.querySelectorAll('input[name="dup-target-day-cb"]').forEach(cb => {
        cb.checked = false;
    });
};

window.appExecuteDuplicateDay = async function() {
    const { sourceDay, dayMap } = duplicateModalState;
    const sourcePeriods = dayMap[sourceDay] || [];

    if (sourcePeriods.length === 0) {
        showToast(`Source day "${sourceDay}" has no periods to copy.`, "error");
        return;
    }

    const selectedCheckboxes = Array.from(document.querySelectorAll('input[name="dup-target-day-cb"]:checked'));
    const selectedTargetDays = selectedCheckboxes.map(cb => cb.value);

    if (selectedTargetDays.length === 0) {
        showToast("Please select at least one target day to copy to.", "warning");
        return;
    }

    const replaceTarget = document.getElementById('dup-replace-target')?.checked ?? true;

    // If any target day has existing periods and replaceTarget is true, ask confirmation
    const hasExistingOnTargets = selectedTargetDays.some(d => (dayMap[d]?.length || 0) > 0);
    if (hasExistingOnTargets && replaceTarget) {
        const daysWithPeriods = selectedTargetDays.filter(d => (dayMap[d]?.length || 0) > 0);
        const ok = await confirmAction(
            "Overwrite Existing Periods?",
            `Existing periods on ${daysWithPeriods.join(', ')} will be replaced with periods from ${sourceDay}. Do you wish to continue?`,
            "Yes, Overwrite",
            false
        );
        if (!ok) return;
    }

    const submitBtn = document.getElementById('dup-submit-btn');
    if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.innerHTML = `<span class="inline-block animate-spin mr-1">↻</span> Duplicating...`;
    }

    try {
        const res = await API.duplicateDay(sourceDay, selectedTargetDays, replaceTarget);
        document.getElementById('modal-duplicate-day')?.classList.add('hidden');
        
        const targetStr = selectedTargetDays.join(', ');
        showToast(`Copied ${res.count || sourcePeriods.length} periods from ${sourceDay} to ${targetStr}!`, "success");
        
        // If current selected day was one of the targets, keep it, else switch to the first target day
        if (selectedTargetDays.includes(state.timetableSelectedDay)) {
            // stay on current day
        } else {
            state.timetableSelectedDay = selectedTargetDays[0];
        }
        await loadTimetable();

    } catch (err) {
        console.error("Duplicate failed:", err);
        showToast(err.message || "Duplicate failed", "error");
    } finally {
        if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.innerHTML = `<i data-lucide="copy" class="w-4 h-4"></i> Duplicate Now`;
            if (window.lucide) window.lucide.createIcons();
        }
    }
};

window.appGoToTimetableDay = function(day) {
    state.timetableSelectedDay = day;
    switchView('timetable');
};

// --- Utility Helpers ---
function formatDateDisplay(dateStr) {
    if (!dateStr) return '';
    const parts = dateStr.split('-');
    if (parts.length !== 3) return dateStr;
    const d = new Date(parts[0], parts[1] - 1, parts[2]);
    return d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
}

function getDayName(dateStr) {
    if (!dateStr) return '';
    const parts = dateStr.split('-');
    const d = new Date(parts[0], parts[1] - 1, parts[2]);
    return d.toLocaleDateString('en-US', { weekday: 'long' });
}

// --- Setup Global Listeners on DOMContentLoaded ---
document.addEventListener('DOMContentLoaded', async () => {
    // 1. Load initial settings
    try {
        state.settings = await API.getSettings();
        applyTheme(state.settings.theme);
    } catch (err) {
        console.warn("Could not fetch settings on start, using defaults");
    }

    // 2. Navigation click handlers
    document.querySelectorAll('[data-view-nav]').forEach(btn => {
        btn.addEventListener('click', () => switchView(btn.getAttribute('data-view-nav')));
    });
    document.querySelectorAll('[data-mobile-nav]').forEach(btn => {
        btn.addEventListener('click', () => switchView(btn.getAttribute('data-mobile-nav')));
    });

    // Mobile drawer toggle
    const mobileMenuBtn = document.getElementById('btn-mobile-menu');
    const mobileDrawer = document.getElementById('mobile-drawer');
    const closeDrawerBtn = document.getElementById('btn-close-drawer');
    if (mobileMenuBtn && mobileDrawer) {
        mobileMenuBtn.addEventListener('click', () => mobileDrawer.classList.toggle('hidden'));
    }
    if (closeDrawerBtn && mobileDrawer) {
        closeDrawerBtn.addEventListener('click', () => mobileDrawer.classList.add('hidden'));
    }

    // Dark mode toggle in header
    const themeToggleBtn = document.getElementById('btn-theme-toggle');
    if (themeToggleBtn) {
        themeToggleBtn.addEventListener('click', () => {
            const isDark = document.documentElement.classList.contains('dark');
            const newTheme = isDark ? 'light' : 'dark';
            applyTheme(newTheme);
            state.settings.theme = newTheme;
            API.saveSettings(state.settings);
        });
    }

    // Modal Close buttons
    document.querySelectorAll('[data-modal-close]').forEach(btn => {
        btn.addEventListener('click', () => {
            btn.closest('.modal-overlay')?.classList.add('hidden');
        });
    });

    // Excel Export Scope radio change listener
    document.querySelectorAll('input[name="export-scope"]').forEach(radio => {
        radio.addEventListener('change', () => {
            if (window.appUpdateExportScopeUI) window.appUpdateExportScopeUI();
        });
    });

    // Today date picker listener
    const todayPicker = document.getElementById('today-date-picker');
    if (todayPicker) {
        todayPicker.value = state.todayDate;
        todayPicker.addEventListener('change', () => loadTodayAttendance());
    }

    const todayPrevBtn = document.getElementById('today-btn-prev');
    const todayNextBtn = document.getElementById('today-btn-next');
    const todayTodayBtn = document.getElementById('today-btn-today');

    if (todayPrevBtn && todayPicker) {
        todayPrevBtn.addEventListener('click', () => {
            const cur = new Date(todayPicker.value);
            cur.setDate(cur.getDate() - 1);
            todayPicker.value = cur.toISOString().split('T')[0];
            loadTodayAttendance();
        });
    }
    if (todayNextBtn && todayPicker) {
        todayNextBtn.addEventListener('click', () => {
            const cur = new Date(todayPicker.value);
            cur.setDate(cur.getDate() + 1);
            todayPicker.value = cur.toISOString().split('T')[0];
            loadTodayAttendance();
        });
    }
    if (todayTodayBtn && todayPicker) {
        todayTodayBtn.addEventListener('click', () => {
            todayPicker.value = new Date().toISOString().split('T')[0];
            loadTodayAttendance();
        });
    }

    // Subject Calculator Slider Listener
    const targetSlider = document.getElementById('sub-calc-target-slider');
    const targetInput = document.getElementById('sub-calc-target-val');
    if (targetSlider) {
        targetSlider.addEventListener('input', (e) => {
            const val = parseFloat(e.target.value);
            if (targetInput) targetInput.textContent = `${val}%`;
            if (state.selectedSubject) {
                updateSubjectCalculator(state.selectedSubject, val);
            }
        });
    }

    // Simulator input listeners
    document.getElementById('sim-input-attend')?.addEventListener('input', runSimulator);
    document.getElementById('sim-input-miss')?.addEventListener('input', runSimulator);

    // Records Filter Listeners
    ['records-filter-from', 'records-filter-to', 'records-filter-subject', 'records-filter-status', 'records-filter-sort', 'records-filter-order'].forEach(id => {
        document.getElementById(id)?.addEventListener('change', () => loadRecords());
    });
    document.getElementById('records-filter-reset')?.addEventListener('click', () => {
        document.getElementById('records-filter-from').value = '';
        document.getElementById('records-filter-to').value = '';
        document.getElementById('records-filter-subject').value = '';
        document.getElementById('records-filter-status').value = '';
        loadRecords();
    });

    // --- Authentication & User Management Handlers ---
    window.appSwitchAuthSubtab = function(subtab) {
        const loginForm = document.getElementById('form-auth-login');
        const signupForm = document.getElementById('form-auth-signup');
        const forgotForm = document.getElementById('form-auth-forgot');
        const resetForm = document.getElementById('form-auth-reset');
        const tabLoginBtn = document.getElementById('btn-auth-tab-login');
        const tabSignupBtn = document.getElementById('btn-auth-tab-signup');
        const alertBox = document.getElementById('auth-alert-box');

        if (alertBox) alertBox.classList.add('hidden');

        [loginForm, signupForm, forgotForm, resetForm].forEach(f => f?.classList.add('hidden'));

        if (subtab === 'login') {
            loginForm?.classList.remove('hidden');
            tabLoginBtn?.classList.add('bg-white', 'dark:bg-slate-900', 'text-indigo-600', 'dark:text-indigo-400', 'shadow-sm');
            tabLoginBtn?.classList.remove('text-slate-600', 'dark:text-slate-400');
            tabSignupBtn?.classList.remove('bg-white', 'dark:bg-slate-900', 'text-indigo-600', 'dark:text-indigo-400', 'shadow-sm');
            tabSignupBtn?.classList.add('text-slate-600', 'dark:text-slate-400');
        } else if (subtab === 'signup') {
            signupForm?.classList.remove('hidden');
            tabSignupBtn?.classList.add('bg-white', 'dark:bg-slate-900', 'text-indigo-600', 'dark:text-indigo-400', 'shadow-sm');
            tabSignupBtn?.classList.remove('text-slate-600', 'dark:text-slate-400');
            tabLoginBtn?.classList.remove('bg-white', 'dark:bg-slate-900', 'text-indigo-600', 'dark:text-indigo-400', 'shadow-sm');
            tabLoginBtn?.classList.add('text-slate-600', 'dark:text-slate-400');
        } else if (subtab === 'forgot') {
            forgotForm?.classList.remove('hidden');
        } else if (subtab === 'reset') {
            resetForm?.classList.remove('hidden');
        }
        if (window.lucide) window.lucide.createIcons();
    };

    function showAuthAlert(msg, type = 'error') {
        const alertBox = document.getElementById('auth-alert-box');
        if (!alertBox) return;
        alertBox.textContent = msg;
        alertBox.classList.remove('hidden', 'bg-rose-50', 'text-rose-700', 'bg-emerald-50', 'text-emerald-700');
        if (type === 'error') {
            alertBox.classList.add('bg-rose-50', 'text-rose-700', 'border', 'border-rose-200');
        } else {
            alertBox.classList.add('bg-emerald-50', 'text-emerald-700', 'border', 'border-emerald-200');
        }
    }

    window.appHandleLogin = async function(e) {
        if (e) e.preventDefault();
        const email = document.getElementById('auth-login-email').value.trim();
        const password = document.getElementById('auth-login-password').value;

        try {
            const res = await API.login(email, password);
            showToast(`Welcome back, ${res.user.name}!`, 'success');
            await checkAuthSession();
        } catch (err) {
            showAuthAlert(err.message || 'Login failed. Please check your credentials.', 'error');
        }
    };

    window.appHandleSignup = async function(e) {
        if (e) e.preventDefault();
        const name = document.getElementById('auth-signup-name').value.trim();
        const email = document.getElementById('auth-signup-email').value.trim();
        const password = document.getElementById('auth-signup-password').value;
        const confirm = document.getElementById('auth-signup-confirm').value;

        if (password.length < 6) {
            showAuthAlert('Password must be at least 6 characters.', 'error');
            return;
        }
        if (password !== confirm) {
            showAuthAlert('Passwords do not match.', 'error');
            return;
        }

        try {
            const res = await API.signup(name, email, password, confirm);
            showToast(`Account created! Welcome, ${res.user.name}.`, 'success');
            await checkAuthSession();
        } catch (err) {
            showAuthAlert(err.message || 'Signup failed.', 'error');
        }
    };

    window.appHandleForgotPassword = async function(e) {
        if (e) e.preventDefault();
        const email = document.getElementById('auth-forgot-email').value.trim();
        try {
            const res = await API.forgotPassword(email);
            if (res.reset_token) {
                showAuthAlert(`Reset token: ${res.reset_token} (Copy this token to reset your password)`, 'success');
                window.appSwitchAuthSubtab('reset');
                document.getElementById('auth-reset-token').value = res.reset_token;
            } else {
                showAuthAlert(res.message, 'success');
            }
        } catch (err) {
            showAuthAlert(err.message || 'Failed to request reset token.', 'error');
        }
    };

    window.appHandleResetPassword = async function(e) {
        if (e) e.preventDefault();
        const token = document.getElementById('auth-reset-token').value.trim();
        const newPass = document.getElementById('auth-reset-password').value;
        const confirm = document.getElementById('auth-reset-confirm').value;

        try {
            await API.resetPassword(token, newPass, confirm);
            showToast('Password reset successful! Please sign in.', 'success');
            window.appSwitchAuthSubtab('login');
        } catch (err) {
            showAuthAlert(err.message || 'Reset password failed.', 'error');
        }
    };

    window.appLogout = async function() {
        await API.logout();
        state.isAuthenticated = false;
        state.currentUser = null;
        showToast('Logged out successfully', 'info');
        switchView('auth');
    };

    window.appToggleUserMenu = function(force) {
        const menu = document.getElementById('user-profile-menu');
        if (!menu) return;
        if (typeof force === 'boolean') {
            menu.classList.toggle('hidden', !force);
        } else {
            menu.classList.toggle('hidden');
        }
    };

    window.appConfirmMigration = async function(importExisting) {
        try {
            const res = await API.migrateLocal(importExisting);
            document.getElementById('modal-data-migration')?.classList.add('hidden');
            showToast(res.message, 'success');
            loadDashboard();
        } catch (err) {
            showToast('Migration failed', 'error');
        }
    };

    // Close user menu on outside click
    document.addEventListener('click', (e) => {
        const container = document.getElementById('user-profile-container');
        const menu = document.getElementById('user-profile-menu');
        if (container && menu && !container.contains(e.target)) {
            menu.classList.add('hidden');
        }
    });

    // Check Auth Session
    async function checkAuthSession() {
        try {
            const res = await API.getMe();
            if (res.authenticated && res.user) {
                state.isAuthenticated = true;
                state.currentUser = res.user;

                // Update Header User Details
                const initials = (res.user.name || 'U').split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase();
                const avatarEl = document.getElementById('user-avatar-initials');
                const nameEl = document.getElementById('user-display-name');
                const menuNameEl = document.getElementById('menu-user-name');
                const menuEmailEl = document.getElementById('menu-user-email');

                if (avatarEl) avatarEl.textContent = initials;
                if (nameEl) nameEl.textContent = res.user.name;
                if (menuNameEl) menuNameEl.textContent = res.user.name;
                if (menuEmailEl) menuEmailEl.textContent = res.user.email;

                // Check for local data migration prompt
                if (res.has_unassigned_data) {
                    document.getElementById('modal-data-migration')?.classList.remove('hidden');
                }

                switchView('dashboard');
            } else {
                state.isAuthenticated = false;
                state.currentUser = null;
                switchView('auth');
            }
        } catch (err) {
            state.isAuthenticated = false;
            state.currentUser = null;
            switchView('auth');
        }
    }

    // Network Online/Offline Listeners & Multi-Device Sync
    function updateConnectionStatus(isOnline) {
        const bar = document.getElementById('conn-status-bar');
        const text = document.getElementById('conn-status-text');
        const pill = document.getElementById('cloud-sync-pill');
        const pillText = document.getElementById('cloud-sync-text');

        if (!isOnline) {
            if (bar) bar.classList.remove('hidden');
            if (text) text.textContent = "You are currently offline. Changes are saved locally and will auto-sync when reconnected.";
            if (pillText) pillText.textContent = "Offline Mode";
            if (pill) {
                pill.className = "hidden sm:flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-bold bg-amber-50 dark:bg-amber-950/40 text-amber-700 dark:text-amber-400 border border-amber-200 dark:border-amber-800";
            }
        } else {
            if (bar) bar.classList.add('hidden');
            if (pillText) pillText.textContent = "Cloud Synced";
            if (pill) {
                pill.className = "hidden sm:flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-bold bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-800";
            }
            // Auto-flush offline queue
            API.flushOfflineQueue().then(synced => {
                if (synced > 0) {
                    showToast(`🟢 Synchronized ${synced} attendance changes with cloud!`, 'success');
                    if (state.currentView === 'today') loadTodayAttendance();
                    else if (state.currentView === 'dashboard') loadDashboard();
                }
            });
        }
    }

    window.addEventListener('online', () => updateConnectionStatus(true));
    window.addEventListener('offline', () => updateConnectionStatus(false));
    updateConnectionStatus(navigator.onLine);

    // Multi-device sync on tab focus
    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'visible' && state.isAuthenticated) {
            if (state.currentView === 'today') loadTodayAttendance();
            else if (state.currentView === 'dashboard') loadDashboard();
        }
    });

    // Initial Auth Check on launch
    await checkAuthSession();
});

