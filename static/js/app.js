/**
 * App - Main entry point
 * Initializes all modules when DOM is ready
 */
document.addEventListener('DOMContentLoaded', () => {
    console.log('Parking Violation Dashboard initializing...');
    
    // Initialize all modules in order
    NotificationManager.init();
    DetectorControl.init();
    WebSocketHandler.init();
    SettingsModal.init();
    
    console.log('Dashboard ready!');
});
