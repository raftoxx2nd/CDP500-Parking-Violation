/**
 * NotificationManager - Handles alert sounds and push notifications
 */
const NotificationManager = (function() {
    // Private variables
    let alertSound = null;
    let enableNotificationsBtn = null;
    let canPlaySound = true;
    const COOLDOWN_MS = 30000; // 30 seconds

    /**
     * Request browser notification permission
     */
    function requestNotificationPermission() {
        if (!("Notification" in window)) {
            alert("This browser does not support desktop notification");
            return;
        }

        if (Notification.permission === "granted") {
            // Notifications are already enabled
            new Notification("Alerts Enabled!", { 
                body: "You will now receive push notifications for new violations." 
            });
        } else if (Notification.permission !== "denied") {
            Notification.requestPermission().then(permission => {
                if (permission === "granted") {
                    new Notification("Alerts Enabled!", { 
                        body: "You will now receive push notifications for new violations." 
                    });
                }
            });
        }
    }

    /**
     * Trigger alert (sound + notification) for a violation
     * @param {Object} violationData - The violation data object
     */
    function triggerAlert(violationData) {
        // 1. Play sound with cooldown
        if (canPlaySound && alertSound) {
            alertSound.play().catch(e => 
                console.error("Audio play failed. User interaction might be required first.", e)
            );
            canPlaySound = false;
            setTimeout(() => { canPlaySound = true; }, COOLDOWN_MS);
        }

        // 2. Send push notification if permission is granted and tab is not active
        if (Notification.permission === "granted" && document.hidden) {
            const notificationBody = `Vehicle ID ${violationData.track_id} detected in zone '${violationData.zone_name}'.`;
            new Notification("Parking Violation Detected!", {
                body: notificationBody,
                icon: "/static/icon.png"
            });
        }
    }

    /**
     * Initialize the notification manager
     */
    function init() {
        alertSound = document.getElementById('alert-sound');
        enableNotificationsBtn = document.getElementById('enable-notifications-btn');

        if (enableNotificationsBtn) {
            enableNotificationsBtn.addEventListener('click', requestNotificationPermission);
        }
    }

    // Public API
    return {
        init: init,
        triggerAlert: triggerAlert
    };
})();
