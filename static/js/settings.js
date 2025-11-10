/**
 * SettingsModal - Manages settings modal, video source, and zone editor
 */
const SettingsModal = (function() {
    // Private variables - Modal elements
    let settingsBtn = null;
    let settingsModal = null;
    let closeModalBtn = null;
    let tabBtns = null;
    let tabContents = null;

    // Video Source Tab elements
    let videoSourceInput = null;
    let saveSettingsBtn = null;
    let settingsFeedback = null;
    let unsavedIndicator = null;
    let fileBrowserDropdown = null;
    let hasUnsavedChanges = false;

    // Zone Editor Tab elements
    let roiBgImage = null;
    let roiCanvas = null;
    let finishZoneBtn = null;
    let clearZonesBtn = null;
    let saveZonesBtn = null;
    let zonesFeedback = null;
    let roiCtx = null;

    // Zone editor state
    let zones = {};
    let currentPoints = [];
    let sourceImageSize = { w: 0, h: 0 };

    /**
     * Open settings modal
     */
    function openModal() {
        settingsModal.classList.remove('hidden');
        settingsModal.classList.add('flex');
    }

    /**
     * Close settings modal
     */
    function closeModal() {
        settingsModal.classList.add('hidden');
        settingsModal.classList.remove('flex');
    }

    /**
     * Switch between tabs
     * @param {string} tabName - Tab identifier
     */
    function switchTab(tabName) {
        tabBtns.forEach(b => b.classList.remove('bg-gray-700'));
        const clickedBtn = document.querySelector(`.tab-btn[data-tab="${tabName}"]`);
        if (clickedBtn) {
            clickedBtn.classList.add('bg-gray-700');
        }
        tabContents.forEach(c => c.classList.add('hidden'));
        const tabContent = document.getElementById(`${tabName}-tab`);
        if (tabContent) {
            tabContent.classList.remove('hidden');
        }
    }

    // ==================== VIDEO SOURCE TAB ====================

    /**
     * Load current settings from API
     */
    async function loadCurrentSettings() {
        try {
            const response = await fetch('/api/settings');
            const data = await response.json();
            if (data.video_source) {
                videoSourceInput.value = data.video_source;
            }
            hasUnsavedChanges = false;
            updateUnsavedIndicator();
        } catch (e) { 
            console.error("Failed to load settings:", e); 
        }
    }

    /**
     * Load available input files
     */
    async function loadInputFiles() {
        try {
            const response = await fetch('/api/input-files');
            const data = await response.json();
            
            fileBrowserDropdown.innerHTML = '<option value="">-- Select a video --</option>';
            if (data.files && data.files.length > 0) {
                data.files.forEach(file => {
                    const option = document.createElement('option');
                    option.value = `input/${file}`;
                    option.textContent = file;
                    fileBrowserDropdown.appendChild(option);
                });
            } else {
                const option = document.createElement('option');
                option.textContent = 'No video files found in input/ directory';
                option.disabled = true;
                fileBrowserDropdown.appendChild(option);
            }
        } catch (e) {
            console.error("Failed to load input files:", e);
            fileBrowserDropdown.innerHTML = '<option value="">-- Error loading files --</option>';
        }
    }

    /**
     * Update unsaved indicator
     */
    function updateUnsavedIndicator() {
        if (hasUnsavedChanges) {
            unsavedIndicator.classList.remove('hidden');
        } else {
            unsavedIndicator.classList.add('hidden');
        }
    }

    /**
     * Save video source settings
     */
    async function saveSettings() {
        try {
            const response = await fetch('/api/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ video_source: videoSourceInput.value })
            });
            const result = await response.json();
            settingsFeedback.textContent = result.message || result.error;
            hasUnsavedChanges = false;
            updateUnsavedIndicator();

            // Automatically switch to zone editor tab and refresh
            if (response.ok) {
                switchTab('zones');
                loadZoneEditor();
            }

            setTimeout(() => settingsFeedback.textContent = '', 3000);
        } catch (e) { 
            console.error("Failed to save settings:", e); 
        }
    }

    // ==================== ZONE EDITOR TAB ====================

    /**
     * Load zone editor with frame and zones
     */
    async function loadZoneEditor() {
        // Fetch and set background image
        roiBgImage.src = `/api/frame?t=${new Date().getTime()}`;
        roiBgImage.onload = () => {
            // Set canvas dimensions to match image
            sourceImageSize = { w: roiBgImage.naturalWidth, h: roiBgImage.naturalHeight };
            roiCanvas.width = roiBgImage.naturalWidth;
            roiCanvas.height = roiBgImage.naturalHeight;
            roiCtx = roiCanvas.getContext('2d');
            
            // Fetch existing zones and draw
            loadAndDrawZones();
        };
        roiBgImage.onerror = () => {
            zonesFeedback.textContent = "Failed to load frame. Is the video source correct?";
        };
    }

    /**
     * Load and draw zones from API
     */
    async function loadAndDrawZones() {
        try {
            const response = await fetch('/api/zones');
            const data = await response.json();
            zones = data.zones || {};
            drawAll();
        } catch (e) { 
            console.error("Failed to load zones:", e); 
            zones = {}; 
        }
    }

    /**
     * Draw all zones and current points
     */
    function drawAll() {
        if (!roiCtx) return;
        roiCtx.clearRect(0, 0, roiCanvas.width, roiCanvas.height);
        
        // Draw existing saved zones
        Object.entries(zones).forEach(([name, points]) => {
            drawPolygon(points, 'rgba(255, 0, 0, 0.5)', 'red');
            
            // Draw zone name
            const text = name;
            const fontSize = 16;
            roiCtx.font = `${fontSize}px Arial`;
            const textWidth = roiCtx.measureText(text).width;
            const textX = points[0][0];
            const textY = points[0][1] - 15;
            roiCtx.fillStyle = 'rgba(0,0,0,0.7)';
            roiCtx.fillRect(textX - 4, textY - fontSize, textWidth + 8, fontSize + 6);
            roiCtx.fillStyle = 'white';
            roiCtx.fillText(text, textX, textY);
        });
        
        // Draw current unsaved polygon
        if (currentPoints.length > 0) {
            drawPolygon(currentPoints, 'rgba(0, 255, 0, 0.5)', 'lime');
        }
        
        // Draw a dot for the very first point
        if (currentPoints.length === 1) {
            const point = currentPoints[0];
            roiCtx.fillStyle = 'lime';
            roiCtx.beginPath();
            roiCtx.arc(point[0], point[1], 5, 0, 2 * Math.PI);
            roiCtx.fill();
        }
        
        updateSaveZonesBtnState();
    }

    /**
     * Draw a polygon on canvas
     * @param {Array} points - Array of [x, y] coordinates
     * @param {string} fillStyle - Fill color
     * @param {string} strokeStyle - Stroke color
     */
    function drawPolygon(points, fillStyle, strokeStyle) {
        if (points.length === 0) return;
        roiCtx.fillStyle = fillStyle;
        roiCtx.strokeStyle = strokeStyle;
        roiCtx.lineWidth = 4;
        roiCtx.beginPath();
        roiCtx.moveTo(points[0][0], points[0][1]);
        for (let i = 1; i < points.length; i++) {
            roiCtx.lineTo(points[i][0], points[i][1]);
        }
        if (points.length > 2) roiCtx.closePath();
        roiCtx.fill();
        roiCtx.stroke();
    }

    /**
     * Handle canvas click to add point
     * @param {Event} e - Mouse event
     */
    function handleCanvasClick(e) {
        const rect = roiCanvas.getBoundingClientRect();
        const scaleX = roiCanvas.width / rect.width;
        const scaleY = roiCanvas.height / rect.height;
        const x = (e.clientX - rect.left) * scaleX;
        const y = (e.clientY - rect.top) * scaleY;
        currentPoints.push([Math.round(x), Math.round(y)]);
        drawAll();
    }

    /**
     * Finish current zone
     */
    function finishZone() {
        if (currentPoints.length > 2) {
            let zoneName = prompt("Enter a name for this zone:", `zone_${Object.keys(zones).length + 1}`);
            if (zoneName && zoneName.trim().length > 0) {
                zones[zoneName.trim()] = currentPoints;
                currentPoints = [];
                drawAll();
            } else {
                alert("Zone name cannot be empty.");
            }
        } else {
            alert("A zone must have at least 3 points.");
        }
    }

    /**
     * Clear all zones
     */
    function clearZones() {
        if (confirm("Are you sure you want to clear all zones? This cannot be undone.")) {
            zones = {};
            currentPoints = [];
            drawAll();
        }
    }

    /**
     * Update save zones button state
     */
    function updateSaveZonesBtnState() {
        if (currentPoints.length > 0) {
            saveZonesBtn.disabled = true;
            saveZonesBtn.classList.add('opacity-50', 'cursor-not-allowed');
            saveZonesBtn.title = "Finish the current zone before saving.";
        } else {
            saveZonesBtn.disabled = false;
            saveZonesBtn.classList.remove('opacity-50', 'cursor-not-allowed');
            saveZonesBtn.title = "";
        }
    }

    /**
     * Save zones to API
     */
    async function saveZones() {
        if (saveZonesBtn.disabled) return;
        try {
            const payload = {
                source_image_width: sourceImageSize.w,
                source_image_height: sourceImageSize.h,
                zones: zones
            };
            const response = await fetch('/api/zones', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const result = await response.json();
            zonesFeedback.textContent = result.message || result.error;
            setTimeout(() => zonesFeedback.textContent = '', 3000);
        } catch (e) { 
            console.error("Failed to save zones:", e); 
        }
    }

    /**
     * Initialize settings modal
     */
    function init() {
        // Get modal elements
        settingsBtn = document.getElementById('settings-btn');
        settingsModal = document.getElementById('settings-modal');
        closeModalBtn = document.getElementById('close-modal-btn');
        tabBtns = document.querySelectorAll('.tab-btn');
        tabContents = document.querySelectorAll('.tab-content');

        // Get video source tab elements
        videoSourceInput = document.getElementById('video-source-input');
        saveSettingsBtn = document.getElementById('save-settings-btn');
        settingsFeedback = document.getElementById('settings-feedback');
        unsavedIndicator = document.getElementById('unsaved-indicator');
        fileBrowserDropdown = document.getElementById('file-browser-dropdown');

        // Get zone editor tab elements
        roiBgImage = document.getElementById('roi-bg-image');
        roiCanvas = document.getElementById('roi-canvas');
        finishZoneBtn = document.getElementById('finish-zone-btn');
        clearZonesBtn = document.getElementById('clear-zones-btn');
        saveZonesBtn = document.getElementById('save-zones-btn');
        zonesFeedback = document.getElementById('zones-feedback');

        // Attach event listeners - Modal
        if (settingsBtn) {
            settingsBtn.addEventListener('click', () => {
                openModal();
                loadCurrentSettings();
                loadInputFiles();
                loadZoneEditor();
            });
        }
        if (closeModalBtn) {
            closeModalBtn.addEventListener('click', closeModal);
        }

        // Attach event listeners - Tabs
        tabBtns.forEach(btn => {
            btn.addEventListener('click', () => {
                switchTab(btn.dataset.tab);
            });
        });

        // Attach event listeners - Video Source
        if (videoSourceInput) {
            videoSourceInput.addEventListener('input', () => {
                hasUnsavedChanges = true;
                updateUnsavedIndicator();
            });
        }
        if (fileBrowserDropdown) {
            fileBrowserDropdown.addEventListener('change', (e) => {
                if (e.target.value) {
                    videoSourceInput.value = e.target.value;
                    hasUnsavedChanges = true;
                    updateUnsavedIndicator();
                    settingsFeedback.textContent = `✓ Selected: ${e.target.options[e.target.selectedIndex].text}. Click "Apply Source & Update Editor" to apply.`;
                    setTimeout(() => settingsFeedback.textContent = '', 3000);
                }
            });
        }
        if (saveSettingsBtn) {
            saveSettingsBtn.addEventListener('click', saveSettings);
        }

        // Attach event listeners - Zone Editor
        if (roiCanvas) {
            roiCanvas.addEventListener('mousedown', handleCanvasClick);
        }
        if (finishZoneBtn) {
            finishZoneBtn.addEventListener('click', finishZone);
        }
        if (clearZonesBtn) {
            clearZonesBtn.addEventListener('click', clearZones);
        }
        if (saveZonesBtn) {
            saveZonesBtn.addEventListener('click', saveZones);
        }
    }

    // Public API
    return {
        init: init
    };
})();
