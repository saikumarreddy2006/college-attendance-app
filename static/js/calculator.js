/**
 * Attendance Calculator Engine
 * Handles all mathematical calculations, predictions, and edge cases.
 */

export const AttendanceCalculator = {
    /**
     * Calculate core attendance statistics
     * @param {number} attended - Number of attended classes
     * @param {number} total - Total classes conducted
     * @param {number} required - Required attendance percentage (e.g. 75)
     */
    calculateStats(attended, total, required = 75.0) {
        attended = Number(attended) || 0;
        total = Number(total) || 0;
        required = Number(required) || 75.0;

        if (total <= 0) {
            return {
                attended: 0,
                absent: 0,
                total: 0,
                percentage: 0.0,
                canMiss: 0,
                needToAttend: 0,
                isTargetAchieved: true,
                status: 'Good'
            };
        }

        const absent = Math.max(0, total - attended);
        const percentage = Math.round((attended / total) * 10000) / 100; // 2 decimal places
        const r = required / 100.0;

        // How many classes can be safely missed: floor(A/r - T)
        let canMiss = 0;
        if (percentage >= required && r > 0) {
            canMiss = Math.max(0, Math.floor((attended / r) - total));
        }

        // How many consecutive classes needed to reach target: ceil((r*T - A) / (1 - r))
        let needToAttend = 0;
        let isImpossible = false;

        if (percentage < required) {
            if (r >= 1.0) {
                // If target is 100% and student already missed a class, impossible in finite steps
                needToAttend = -1;
                isImpossible = true;
            } else {
                const diff = (r * total) - attended;
                needToAttend = Math.max(0, Math.ceil(diff / (1.0 - r)));
            }
        }

        return {
            attended,
            absent,
            total,
            percentage,
            canMiss,
            needToAttend,
            isImpossible,
            isTargetAchieved: percentage >= required
        };
    },

    /**
     * What-if Attendance Simulator
     * Simulates future percentage if student attends next X and misses next Y classes
     */
    simulateFuture(attended, total, futureAttend = 0, futureMiss = 0) {
        attended = Number(attended) || 0;
        total = Number(total) || 0;
        futureAttend = Math.max(0, Number(futureAttend) || 0);
        futureMiss = Math.max(0, Number(futureMiss) || 0);

        const newAttended = attended + futureAttend;
        const newTotal = total + futureAttend + futureMiss;

        if (newTotal <= 0) {
            return { newAttended: 0, newTotal: 0, newPercentage: 0.0 };
        }

        const newPercentage = Math.round((newAttended / newTotal) * 10000) / 100;
        return {
            newAttended,
            newTotal,
            newPercentage
        };
    },

    /**
     * Determine status badge based on configurable thresholds
     */
    getStatusBadge(percentage, total, warnThreshold = 75.0, critThreshold = 65.0) {
        if (total === 0) return 'Good';
        if (percentage >= warnThreshold) return 'Good';
        if (percentage >= critThreshold) return 'Warning';
        return 'Critical';
    }
};
