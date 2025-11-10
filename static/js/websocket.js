/**
 * WebSocketHandler - Manages WebSocket connection and violation display
 */
const WebSocketHandler = (function() {
    // Private variables
    let violationsLog = null;
    let snapshotContainer = null;
    let logPlaceholder = null;
    let statusDot = null;
    let statusPing = null;
    let statusText = null;
    let ws = null;
    let reconnectDelay = 3000;
    const maxReconnectDelay = 60000;
    const violationDataStore = {};

    /**
     * Get snapshot URL
     * @param {string} relativePath - Relative path to snapshot
     * @returns {string} Full URL
     */
    function getSnapshotUrl(relativePath) { 
        return `/${relativePath}`; 
    }

    /**
     * Update connection status UI
     * @param {boolean} connected - Connection status
     */
    function updateConnectionStatus(connected) {
        if (connected) {
            statusText.textContent = 'Connected';
            statusDot.classList.remove('bg-red-500');
            statusDot.classList.add('bg-green-500');
            statusPing.classList.remove('bg-red-400');
            statusPing.classList.add('bg-green-400');
            reconnectDelay = 3000;
        } else {
            statusText.textContent = 'Disconnected';
            statusDot.classList.add('bg-red-500');
            statusDot.classList.remove('bg-green-500');
            statusPing.classList.add('bg-red-400');
            statusPing.classList.remove('bg-green-400');
        }
    }

    /**
     * Handle new violation data
     * @param {Object} data - Violation data from server
     */
    function handleViolation(data) {
        // Store violation data
        violationDataStore[data.track_id] = data;
        
        // Remove placeholder
        if (logPlaceholder) {
            logPlaceholder.remove();
        }
        
        // Trigger alert (sound + notification)
        if (typeof NotificationManager !== 'undefined') {
            NotificationManager.triggerAlert(data);
        }

        // Update main snapshot view
        const imageUrl = `${getSnapshotUrl(data.snapshot_file)}?t=${new Date().getTime()}`;
        snapshotContainer.innerHTML = `<img src="${imageUrl}" alt="Violation snapshot for ID ${data.track_id}" class="rounded-lg max-w-full h-auto shadow-md">`;

        // Add to violation log
        const logEntry = document.createElement('div');
        logEntry.className = 'bg-gray-700 p-4 rounded-lg border border-gray-600 transition-all duration-300 transform scale-95 opacity-0 cursor-pointer hover:bg-gray-600';
        logEntry.dataset.trackId = data.track_id;
        logEntry.innerHTML = `
            <p class="font-semibold text-red-400">New Violation: ID ${data.track_id}</p>
            <p class="text-sm text-gray-300">Zone: <span class="font-medium text-white">${data.zone_name}</span></p>
            <p class="text-sm text-gray-300">Class: <span class="font-medium text-white">${data.class_label}</span></p>
            <p class="text-sm text-gray-300">Time: <span class="font-medium text-white">${data.timestamp}</span></p>
        `;
        violationsLog.prepend(logEntry);
        
        // Animate entry
        setTimeout(() => logEntry.classList.remove('scale-95', 'opacity-0'), 10);
    }

    /**
     * Handle log entry click
     * @param {Event} event - Click event
     */
    function handleLogClick(event) {
        const logEntry = event.target.closest('[data-track-id]');
        if (!logEntry) return;

        // Remove highlight from previously selected item
        const currentlySelected = violationsLog.querySelector('.selected-log');
        if (currentlySelected) {
            currentlySelected.classList.remove('selected-log', 'bg-blue-900/50', 'border-blue-400');
            currentlySelected.classList.add('hover:bg-gray-600');
        }

        // Add highlight to clicked item
        logEntry.classList.add('selected-log', 'bg-blue-900/50', 'border-blue-400');
        logEntry.classList.remove('hover:bg-gray-600');

        // Display selected violation snapshot
        const trackId = logEntry.dataset.trackId;
        const violationData = violationDataStore[trackId];
        if (violationData) {
            const imageUrl = `${getSnapshotUrl(violationData.snapshot_file)}?t=${new Date().getTime()}`;
            snapshotContainer.innerHTML = `<img src="${imageUrl}" alt="Violation snapshot for ID ${violationData.track_id}" class="rounded-lg max-w-full h-auto shadow-md">`;
        }
    }

    /**
     * Connect to WebSocket server
     */
    function connect() {
        const wsProtocol = window.location.protocol === "https:" ? "wss:" : "ws:";
        const wsHost = window.location.host;
        ws = new WebSocket(`${wsProtocol}//${wsHost}/ws`);

        ws.onopen = () => {
            console.log('WebSocket connected');
            updateConnectionStatus(true);
        };

        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                handleViolation(data);
            } catch (e) { 
                console.error('Failed to parse message:', event.data, e); 
            }
        };

        ws.onclose = () => {
            console.log(`WebSocket disconnected. Reconnecting in ${reconnectDelay / 1000}s...`);
            updateConnectionStatus(false);
            setTimeout(connect, reconnectDelay);
            reconnectDelay = Math.min(reconnectDelay * 2, maxReconnectDelay);
        };

        ws.onerror = (err) => { 
            console.error('WebSocket error:', err); 
            ws.close(); 
        };
    }

    /**
     * Initialize WebSocket handler
     */
    function init() {
        // Get DOM elements
        violationsLog = document.getElementById('violations-log');
        snapshotContainer = document.getElementById('snapshot-container');
        logPlaceholder = document.getElementById('log-placeholder');
        statusDot = document.getElementById('status-dot');
        statusPing = document.getElementById('status-ping');
        statusText = document.getElementById('status-text');

        // Attach event listener for log clicks
        if (violationsLog) {
            violationsLog.addEventListener('click', handleLogClick);
        }

        // Start WebSocket connection
        connect();
    }

    // Public API
    return {
        init: init
    };
})();
