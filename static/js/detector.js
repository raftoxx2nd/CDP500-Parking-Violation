/**
 * DetectorControl - Manages detector start/stop and status updates
 */
const DetectorControl = (function() {
    // Private variables
    let detectorStatusDot = null;
    let detectorStatusText = null;
    let detectorToggleBtn = null;
    let playIcon = null;
    let stopIcon = null;
    let toggleText = null;
    let detectorRunning = false;
    let statusCheckInterval = null;

    /**
     * Update the detector status UI
     * @param {Object} status - Status object from API
     */
    function updateDetectorStatusUI(status) {
        detectorRunning = status.status === 'running';
        
        if (detectorRunning) {
            // Running state
            detectorStatusText.textContent = `Running (PID: ${status.pid})`;
            detectorStatusDot.classList.remove('bg-gray-500', 'bg-red-500', 'bg-yellow-500');
            detectorStatusDot.classList.add('bg-green-500');
            
            // Update button
            playIcon.classList.add('hidden');
            stopIcon.classList.remove('hidden');
            toggleText.textContent = 'Stop Deteksi';
            detectorToggleBtn.classList.remove('bg-green-600', 'hover:bg-green-700');
            detectorToggleBtn.classList.add('bg-red-600', 'hover:bg-red-700');
        } else {
            // Stopped state
            detectorStatusText.textContent = 'Stopped';
            detectorStatusDot.classList.remove('bg-gray-500', 'bg-green-500', 'bg-yellow-500');
            detectorStatusDot.classList.add('bg-red-500');
            
            // Update button
            stopIcon.classList.add('hidden');
            playIcon.classList.remove('hidden');
            toggleText.textContent = 'Mulai Deteksi';
            detectorToggleBtn.classList.remove('bg-red-600', 'hover:bg-red-700');
            detectorToggleBtn.classList.add('bg-green-600', 'hover:bg-green-700');
        }
    }

    /**
     * Fetch detector status from API
     */
    async function getDetectorStatus() {
        try {
            const response = await fetch('/api/detection/status');
            if (!response.ok) throw new Error('Failed to fetch status');
            const status = await response.json();
            updateDetectorStatusUI(status);
        } catch (e) {
            console.error("Error getting detector status:", e);
            detectorStatusText.textContent = 'Error';
            detectorStatusDot.classList.remove('bg-green-500', 'bg-red-500');
            detectorStatusDot.classList.add('bg-yellow-500');
        }
    }

    /**
     * Toggle detector on/off
     */
    async function toggleDetector() {
        try {
            const endpoint = detectorRunning ? '/api/detection/stop' : '/api/detection/start';
            const response = await fetch(endpoint, { method: 'POST' });
            if (!response.ok) throw new Error('Failed to toggle detector');
            const status = await response.json();
            updateDetectorStatusUI(status);
        } catch (e) { 
            console.error("Error toggling detection:", e);
            detectorStatusText.textContent = 'Error - Check console';
        }
    }

    /**
     * Initialize detector control
     */
    function init() {
        // Get DOM elements
        detectorStatusDot = document.getElementById('detector-status-dot');
        detectorStatusText = document.getElementById('detector-status-text');
        detectorToggleBtn = document.getElementById('detector-toggle-btn');
        playIcon = document.getElementById('play-icon');
        stopIcon = document.getElementById('stop-icon');
        toggleText = document.getElementById('toggle-text');

        // Attach event listener
        if (detectorToggleBtn) {
            detectorToggleBtn.addEventListener('click', toggleDetector);
        }

        // Initial status check
        getDetectorStatus();
        
        // Periodic status checks every 5 seconds
        statusCheckInterval = setInterval(getDetectorStatus, 5000);
    }

    // Public API
    return {
        init: init,
        getStatus: getDetectorStatus
    };
})();
