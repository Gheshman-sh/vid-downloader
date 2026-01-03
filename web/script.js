let currentVideoInfo = null;
let downloadCounter = 0;

// Tab navigation
function showTab(tabName) {
    document.querySelectorAll('.tab-content').forEach(tab => {
        tab.classList.remove('active');
    });
    document.querySelectorAll('.nav-links').forEach(link => {
        link.classList.remove('active');
    });

    document.getElementById(`${tabName}-tab`).classList.add('active');
    event.target.closest('.nav-links').classList.add('active');

    if (tabName === 'history') {
        loadHistory();
    } else if (tabName === 'settings') {
        loadSettings();
    }
}

// Paste from clipboard
async function pasteFromClipboard() {
    try {
        const text = await navigator.clipboard.readText();
        document.getElementById('input-url').value = text;
        showNotification('URL pasted from clipboard', 'success');
    } catch (err) {
        showNotification('Failed to read clipboard. Please paste manually.', 'error');
    }
}

// Fetch video info
async function fetchVideoInfo(event) {
    event.preventDefault();
    const url = document.getElementById('input-url').value.trim();
    
    if (!url) return;

    const submitBtn = event.target.querySelector('button[type="submit"]');
    const originalHTML = submitBtn.innerHTML;
    submitBtn.innerHTML = `
        <svg class="spinner" width="16" height="16" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
            <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" fill="none" opacity="0.25"/>
            <path d="M12 2a10 10 0 0 1 10 10" stroke="currentColor" stroke-width="4" fill="none" stroke-linecap="round"/>
        </svg>
        Fetching...
    `;
    submitBtn.disabled = true;

    try {
        const result = await eel.get_video_info(url)();
        
        if (result.success) {
            currentVideoInfo = result;
            displayVideoPreview(result);
            showNotification('Video info loaded successfully!', 'success');
        } else {
            showNotification(result.error, 'error');
            const preview = document.getElementById('video-preview');
            preview.style.display = 'none';
        }
    } catch (err) {
        showNotification('Network error. Please check your connection.', 'error');
    } finally {
        submitBtn.innerHTML = originalHTML;
        submitBtn.disabled = false;
    }
}

// Display video preview
function displayVideoPreview(info) {
    const preview = document.getElementById('video-preview');
    const thumbnail = document.getElementById('video-thumbnail');
    const title = document.getElementById('video-title');
    const uploader = document.getElementById('video-uploader');
    const views = document.getElementById('video-views');
    const description = document.getElementById('video-description');
    const duration = document.getElementById('video-duration');
    const qualitySelect = document.getElementById('quality-select');

    // Set thumbnail - always use the URL from metadata
    if (info.thumbnail) {
        thumbnail.src = info.thumbnail;
        thumbnail.onerror = function() {
            this.src = 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="400" height="225"%3E%3Crect fill="%231a1a1a" width="400" height="225"/%3E%3Ctext fill="%23666" x="50%25" y="50%25" text-anchor="middle" dy=".3em" font-family="sans-serif" font-size="18"%3ENo Thumbnail%3C/text%3E%3C/svg%3E';
        };
    } else {
        thumbnail.src = 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="400" height="225"%3E%3Crect fill="%231a1a1a" width="400" height="225"/%3E%3Ctext fill="%23666" x="50%25" y="50%25" text-anchor="middle" dy=".3em" font-family="sans-serif" font-size="18"%3ENo Thumbnail%3C/text%3E%3C/svg%3E';
    }

    title.textContent = info.title;
    uploader.innerHTML = `
        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" fill="currentColor" viewBox="0 0 16 16">
            <path d="M11 6a3 3 0 1 1-6 0 3 3 0 0 1 6 0"/>
            <path fill-rule="evenodd" d="M0 8a8 8 0 1 1 16 0A8 8 0 0 1 0 8m8-7a7 7 0 0 0-5.468 11.37C3.242 11.226 4.805 10 8 10s4.757 1.225 5.468 2.37A7 7 0 0 0 8 1"/>
        </svg>
        ${info.uploader}
    `;
    
    if (info.view_count) {
        views.innerHTML = `
            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" fill="currentColor" viewBox="0 0 16 16">
                <path d="M16 8s-3-5.5-8-5.5S0 8 0 8s3 5.5 8 5.5S16 8 16 8M1.173 8a13 13 0 0 1 1.66-2.043C4.12 4.668 5.88 3.5 8 3.5s3.879 1.168 5.168 2.457A13 13 0 0 1 14.828 8q-.086.13-.195.288c-.335.48-.83 1.12-1.465 1.755C11.879 11.332 10.119 12.5 8 12.5s-3.879-1.168-5.168-2.457A13 13 0 0 1 1.172 8z"/>
                <path d="M8 5.5a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5M4.5 8a3.5 3.5 0 1 1 7 0 3.5 3.5 0 0 1-7 0"/>
            </svg>
            ${formatNumber(info.view_count)} views
        `;
    } else {
        views.textContent = '';
    }

    description.textContent = info.description || 'No description available';
    duration.textContent = formatDuration(info.duration);

    // Populate quality options with file sizes
    qualitySelect.innerHTML = '';
    if (info.formats && info.formats.length > 0) {
        info.formats.forEach(format => {
            const option = document.createElement('option');
            option.value = format.resolution.replace('p', '');
            const sizeText = format.filesize ? ` - ${formatFileSize(format.filesize)}` : '';
            option.textContent = `${format.resolution} (${format.ext})${sizeText}`;
            qualitySelect.appendChild(option);
        });
        qualitySelect.selectedIndex = qualitySelect.options.length - 1;
    } else {
        // Fallback options
        ['720', '1080', '1440', '2160'].forEach(res => {
            const option = document.createElement('option');
            option.value = res;
            option.textContent = `${res}p`;
            qualitySelect.appendChild(option);
        });
    }

    preview.style.display = 'block';
    preview.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

// Start download
async function startDownload() {
    if (!currentVideoInfo) return;

    const format = document.getElementById('format-select').value;
    const quality = document.getElementById('quality-select').value;
    const downloadId = `download_${++downloadCounter}`;

    createDownloadItem(downloadId, currentVideoInfo);

    try {
        const result = await eel.download_video(
            currentVideoInfo.url,
            format,
            quality,
            downloadId
        )();

        if (!result.success) {
            updateDownloadStatus(downloadId, 'error', 'Failed to start download');
        }
    } catch (err) {
        updateDownloadStatus(downloadId, 'error', err.toString());
    }
}

// Create download item UI
function createDownloadItem(downloadId, videoInfo) {
    const container = document.getElementById('downloads-container');
    
    const item = document.createElement('div');
    item.className = 'download-item';
    item.id = downloadId;
    
    item.innerHTML = `
        <div class="download-header">
            <div class="download-title">${videoInfo.title}</div>
            <div class="download-actions">
                <span class="download-status">Initializing...</span>
                <button class="cancel-btn" onclick="cancelDownload('${downloadId}')">
                    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" fill="currentColor" viewBox="0 0 16 16">
                        <path d="M16 8A8 8 0 1 1 0 8a8 8 0 0 1 16 0M5.354 4.646a.5.5 0 1 0-.708.708L7.293 8l-2.647 2.646a.5.5 0 0 0 .708.708L8 8.707l2.646 2.647a.5.5 0 0 0 .708-.708L8.707 8l2.647-2.646a.5.5 0 0 0-.708-.708L8 7.293z"/>
                    </svg>
                    Cancel
                </button>
            </div>
        </div>
        <div class="progress-bar">
            <div class="progress-fill" style="width: 0%"></div>
        </div>
        <div class="download-stats">
            <span class="download-speed">⚡ Speed: 0 MB/s</span>
            <span class="download-size">📦 Size: Calculating...</span>
            <span class="download-eta">⏱️ ETA: --:--</span>
            <span class="download-percent">📊 Progress: 0%</span>
        </div>
    `;
    
    container.insertBefore(item, container.firstChild);
}

// Update progress (called from Python)
eel.expose(update_progress);
function update_progress(downloadId, data) {
    const item = document.getElementById(downloadId);
    if (!item) return;

    const progressFill = item.querySelector('.progress-fill');
    const status = item.querySelector('.download-status');
    const speed = item.querySelector('.download-speed');
    const size = item.querySelector('.download-size');
    const eta = item.querySelector('.download-eta');
    const percent = item.querySelector('.download-percent');

    if (data.status === 'downloading') {
        const percentValue = data.percent.toFixed(1);
        progressFill.style.width = percentValue + '%';
        
        const speedMB = (data.speed / 1024 / 1024).toFixed(2);
        speed.textContent = `⚡ Speed: ${speedMB} MB/s`;
        
        const downloaded = formatFileSize(data.downloaded);
        const total = formatFileSize(data.total);
        size.textContent = `📦 Size: ${downloaded} / ${total}`;
        
        const etaMin = Math.floor(data.eta / 60);
        const etaSec = Math.floor(data.eta % 60);
        eta.textContent = `⏱️ ETA: ${etaMin}:${etaSec.toString().padStart(2, '0')}`;
        
        percent.textContent = `📊 Progress: ${percentValue}%`;
        
        status.textContent = 'Downloading...';
        status.style.color = '#3b82f6';
        status.style.background = 'rgba(59, 130, 246, 0.1)';
        
    } else if (data.status === 'processing') {
        progressFill.style.width = '100%';
        status.textContent = 'Processing...';
        status.style.color = '#f59e0b';
        status.style.background = 'rgba(245, 158, 11, 0.1)';
        
    } else if (data.status === 'retrying') {
        status.textContent = data.message || `Retrying (${data.retry_count})...`;
        status.style.color = '#f59e0b';
        status.style.background = 'rgba(245, 158, 11, 0.1)';
        
    } else if (data.status === 'completed') {
        progressFill.style.width = '100%';
        status.textContent = '✓ Completed!';
        status.style.color = '#10b981';
        status.style.background = 'rgba(16, 185, 129, 0.1)';
        item.querySelector('.cancel-btn').style.display = 'none';
        
        showNotification('Download completed successfully!', 'success');
        
        setTimeout(() => {
            item.style.opacity = '0';
            item.style.transform = 'translateX(100%)';
            setTimeout(() => item.remove(), 300);
        }, 5000);
        
    } else if (data.status === 'error') {
        status.textContent = '✗ Failed';
        status.style.color = '#ef4444';
        status.style.background = 'rgba(239, 68, 68, 0.1)';
        
        // Show detailed error
        const errorMsg = document.createElement('div');
        errorMsg.style.cssText = 'margin-top: 1rem; padding: 1rem; background: rgba(239, 68, 68, 0.1); border-radius: 8px; color: #ef4444; font-size: 0.9rem; line-height: 1.6;';
        errorMsg.innerHTML = `
            <strong>Error:</strong> ${data.message}<br>
            ${data.retry_count ? `<em>Retried ${data.retry_count} time(s)</em>` : ''}
        `;
        item.appendChild(errorMsg);
        
        showNotification(data.message, 'error');
        
        item.querySelector('.cancel-btn').textContent = 'Remove';
        item.querySelector('.cancel-btn').onclick = () => item.remove();
    }
}

// Cancel download
async function cancelDownload(downloadId) {
    await eel.cancel_download(downloadId)();
    const item = document.getElementById(downloadId);
    if (item) {
        const status = item.querySelector('.download-status');
        status.textContent = 'Cancelled';
        status.style.color = '#ef4444';
        status.style.background = 'rgba(239, 68, 68, 0.1)';
        setTimeout(() => item.remove(), 2000);
    }
}

// Load history
async function loadHistory() {
    const historyList = document.getElementById('history-list');
    historyList.innerHTML = '<div style="text-align: center; padding: 2rem; color: var(--text-secondary);">Loading history...</div>';
    
    try {
        const history = await eel.get_history()();
        
        if (history.length === 0) {
            historyList.innerHTML = `
                <div style="text-align: center; padding: 4rem; color: var(--text-secondary);">
                    <svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" fill="currentColor" viewBox="0 0 16 16" style="opacity: 0.3; margin-bottom: 1rem;">
                        <path d="M8.515 1.019A7 7 0 0 0 8 1V0a8 8 0 0 1 .589.022zm2.004.45a7 7 0 0 0-.985-.299l.219-.976q.576.129 1.126.342zm1.37.71a7 7 0 0 0-.439-.27l.493-.87a8 8 0 0 1 .979.654l-.615.789a7 7 0 0 0-.418-.302zm1.834 1.79a7 7 0 0 0-.653-.796l.724-.69q.406.429.747.91zm.744 1.352a7 7 0 0 0-.214-.468l.893-.45a8 8 0 0 1 .45 1.088l-.95.313a7 7 0 0 0-.179-.483m.53 2.507a7 7 0 0 0-.1-1.025l.985-.17q.1.58.116 1.17zm-.131 1.538q.05-.254.081-.51l.993.123a8 8 0 0 1-.23 1.155l-.964-.267q.069-.247.12-.501m-.952 2.379q.276-.436.486-.908l.914.405q-.24.54-.555 1.038zm-.964 1.205q.183-.183.35-.378l.758.653a8 8 0 0 1-.401.432z"/>
                        <path d="M8 1a7 7 0 1 0 4.95 11.95l.707.707A8.001 8.001 0 1 1 8 0z"/>
                        <path d="M7.5 3a.5.5 0 0 1 .5.5v5.21l3.248 1.856a.5.5 0 0 1-.496.868l-3.5-2A.5.5 0 0 1 7 9V3.5a.5.5 0 0 1 .5-.5"/>
                    </svg>
                    <p style="font-size: 1.1rem; margin-bottom: 0.5rem;">No download history yet</p>
                    <p style="font-size: 0.9rem;">Your completed downloads will appear here</p>
                </div>
            `;
            return;
        }

        historyList.innerHTML = '';
        history.forEach(item => {
            const historyItem = document.createElement('div');
            historyItem.className = 'history-item';
            
            const date = new Date(item.timestamp);
            const dateStr = date.toLocaleDateString('en-US', { 
                month: 'short', 
                day: 'numeric', 
                year: 'numeric',
                hour: '2-digit',
                minute: '2-digit'
            });
            
            const duration = formatDuration(item.duration);
            const filesize = item.filesize ? formatFileSize(item.filesize) : 'Unknown size';
            
            // Thumbnail is stored as original URL, display it directly
            const thumbSrc = item.thumbnail || 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="280" height="158"%3E%3Crect fill="%231a1a1a" width="280" height="158"/%3E%3Ctext fill="%23666" x="50%25" y="50%25" text-anchor="middle" dy=".3em" font-family="sans-serif"%3ENo Image%3C/text%3E%3C/svg%3E';
            
            historyItem.innerHTML = `
                <img src="${thumbSrc}" alt="Thumbnail" onerror="this.src='data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%22280%22 height=%22158%22%3E%3Crect fill=%22%231a1a1a%22 width=%22280%22 height=%22158%22/%3E%3Ctext fill=%22%23666%22 x=%2250%25%22 y=%2250%25%22 text-anchor=%22middle%22 dy=%22.3em%22 font-family=%22sans-serif%22%3ENo Image%3C/text%3E%3C/svg%3E'">
                <div class="history-item-info">
                    <h3>${item.title}</h3>
                    <p>📊 Format: ${item.format} • 💾 ${filesize}</p>
                    <p>⏱️ Duration: ${duration}</p>
                    <p>📅 Downloaded: ${dateStr}</p>
                    <p style="word-break: break-all; font-size: 0.85em; opacity: 0.6;">🔗 ${item.url}</p>
                </div>
            `;
            
            historyList.appendChild(historyItem);
        });
    } catch (err) {
        historyList.innerHTML = `
            <div style="text-align: center; padding: 2rem; color: var(--danger);">
                Error loading history. Please try again.
            </div>
        `;
    }
}

// Clear history
async function clearHistory() {
    if (confirm('Are you sure you want to clear all download history? This cannot be undone.')) {
        await eel.clear_history()();
        showNotification('History cleared successfully', 'success');
        loadHistory();
    }
}

// Load settings
async function loadSettings() {
    try {
        const settings = await eel.get_settings()();
        
        document.getElementById('download-path').value = settings.download_path || 'downloads';
        document.getElementById('max-retries').value = settings.max_retries || 5;
        document.getElementById('retry-delay').value = settings.retry_delay || 3;
        
        if (settings.credentials) {
            document.getElementById('username').value = settings.credentials.username || '';
            document.getElementById('password').value = settings.credentials.password || '';
        }
    } catch (err) {
        showNotification('Error loading settings', 'error');
    }
}

// Select download folder
async function selectDownloadFolder() {
    try {
        const path = await eel.select_folder()();
        if (path) {
            document.getElementById('download-path').value = path;
            showNotification('Download location updated', 'success');
        }
    } catch (err) {
        showNotification('Error selecting folder', 'error');
    }
}

// Save settings
async function saveSettings() {
    const settings = {
        download_path: document.getElementById('download-path').value || 'downloads',
        max_retries: parseInt(document.getElementById('max-retries').value) || 5,
        retry_delay: parseInt(document.getElementById('retry-delay').value) || 3,
        credentials: {
            username: document.getElementById('username').value,
            password: document.getElementById('password').value
        }
    };

    try {
        await eel.save_settings(settings)();
        showNotification('Settings saved successfully!', 'success');
    } catch (err) {
        showNotification('Error saving settings', 'error');
    }
}

// Helper functions
function formatDuration(seconds) {
    if (!seconds) return 'Unknown';
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);
    
    if (hours > 0) {
        return `${hours}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    }
    return `${minutes}:${secs.toString().padStart(2, '0')}`;
}

function formatFileSize(bytes) {
    if (!bytes || bytes === 0) return 'Unknown';
    const gb = bytes / (1024 * 1024 * 1024);
    if (gb >= 1) {
        return gb.toFixed(2) + ' GB';
    }
    const mb = bytes / (1024 * 1024);
    if (mb >= 1) {
        return mb.toFixed(2) + ' MB';
    }
    const kb = bytes / 1024;
    return kb.toFixed(2) + ' KB';
}

function formatNumber(num) {
    if (num >= 1000000) {
        return (num / 1000000).toFixed(1) + 'M';
    } else if (num >= 1000) {
        return (num / 1000).toFixed(1) + 'K';
    }
    return num.toString();
}

function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.style.cssText = `
        position: fixed;
        top: 2rem;
        right: 2rem;
        padding: 1rem 1.5rem;
        background: ${type === 'success' ? 'rgba(16, 185, 129, 0.9)' : type === 'error' ? 'rgba(239, 68, 68, 0.9)' : 'rgba(59, 130, 246, 0.9)'};
        color: white;
        border-radius: 12px;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
        z-index: 10000;
        animation: slideInRight 0.3s ease;
        max-width: 400px;
        backdrop-filter: blur(10px);
    `;
    notification.textContent = message;
    
    document.body.appendChild(notification);
    
    setTimeout(() => {
        notification.style.animation = 'slideOutRight 0.3s ease';
        setTimeout(() => notification.remove(), 300);
    }, 3000);
}

// Add CSS animations
const style = document.createElement('style');
style.textContent = `
    @keyframes slideInRight {
        from { transform: translateX(100%); opacity: 0; }
        to { transform: translateX(0); opacity: 1; }
    }
    @keyframes slideOutRight {
        from { transform: translateX(0); opacity: 1; }
        to { transform: translateX(100%); opacity: 0; }
    }
    .spinner {
        animation: spin 1s linear infinite;
    }
    @keyframes spin {
        to { transform: rotate(360deg); }
    }
`;
document.head.appendChild(style);

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    console.log('ytdlp WebUI loaded - Enhanced version');
});