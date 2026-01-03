import eel
import yt_dlp
import json
import os
import threading
import urllib.request
import logging
from datetime import datetime
from pathlib import Path
import time
import re
import sys

# Initialize Eel
eel.init('web')

# Configuration
CONFIG_FILE = 'config.json'
HISTORY_FILE = 'history.json'
DOWNLOAD_DIR = 'downloads'

# Create necessary directories
Path(DOWNLOAD_DIR).mkdir(exist_ok=True)
Path(os.path.join(DOWNLOAD_DIR, 'thumbnails')).mkdir(exist_ok=True)

# Global download queue and cancellation
active_downloads = {}  # download_id -> {'thread': thread, 'cancelled': bool}
downloads_lock = threading.Lock()

# Logging setup
logging.basicConfig(
    filename='app.log',
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Helper for bundled resources (PyInstaller)
def get_resource_path(relative_path):
    """Get absolute path to resource, works for dev and PyInstaller"""
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.getcwd()
    return os.path.join(base_path, relative_path)

os.environ["PHANTOMJS_BIN"] = get_resource_path("phantomjs/phantomjs.exe")

# Configuration management
def load_config():
    """Load configuration from file or return defaults"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logging.exception("Failed loading config, using defaults")
    
    return {
        'credentials': {},
        'download_path': DOWNLOAD_DIR,
        'max_retries': 5,
        'retry_delay': 3
    }

def save_config(config):
    """Save configuration to file"""
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        logging.info("Configuration saved successfully")
    except Exception:
        logging.exception("Failed to save configuration")

# History management
def load_history():
    """Load download history from file"""
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            logging.exception("Failed loading history, returning empty")
    return []

def save_history(history):
    """Save download history to file"""
    try:
        with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(history, f, indent=2, ensure_ascii=False)
        logging.info("History saved successfully")
    except Exception:
        logging.exception("Failed to save history")

def add_to_history(video_info, thumbnail_url):
    """Add a completed download to history"""
    try:
        history = load_history()
        history.insert(0, {
            'title': video_info.get('title', 'Unknown'),
            'url': video_info.get('webpage_url', ''),
            'thumbnail': thumbnail_url,
            'duration': video_info.get('duration', 0),
            'timestamp': datetime.now().isoformat(),
            'format': video_info.get('format_selected', 'Unknown'),
            'filesize': video_info.get('filesize', 0)
        })
        # Keep only last 100 items
        history = history[:100]
        save_history(history)
    except Exception:
        logging.exception("Failed to add entry to history")

# Utility functions
def sanitize_filename(filename):
    """Remove invalid characters from filename"""
    # Remove invalid filesystem characters
    filename = re.sub(r'[<>:"/\\|?*]', '', filename)
    # Remove leading/trailing spaces and dots
    filename = filename.strip('. ')
    return filename[:200]  # Limit length

def download_thumbnail(url, title):
    """Download thumbnail and save with video title name"""
    try:
        if not url:
            return None
        
        thumb_dir = os.path.join(DOWNLOAD_DIR, 'thumbnails')
        Path(thumb_dir).mkdir(exist_ok=True)
        
        safe_title = sanitize_filename(title)
        thumb_path = os.path.join(thumb_dir, f'{safe_title}.jpg')
        
        if not os.path.exists(thumb_path):
            urllib.request.urlretrieve(url, thumb_path)
            logging.info(f"Thumbnail downloaded: {safe_title}.jpg")
        
        return thumb_path
    except Exception:
        logging.warning(f"Thumbnail download failed for: {title}")
        return None

def format_error_message(error_str):
    """Convert technical errors to user-friendly messages"""
    error_lower = str(error_str).lower()
    
    # Check for specific error patterns
    error_mappings = {
        ('cancelled', 'canceled', 'killed'): "Download cancelled by user",
        ('http error 403', 'forbidden'): "Access denied. The video might be private, region-blocked, or require authentication.",
        ('http error 404', 'not found'): "Video not found. The URL might be incorrect or the video was removed.",
        ('http error 429', 'too many requests', 'rate limit'): "Too many requests. The website is rate-limiting. Please wait and try again.",
        ('private video',): "This is a private video. You need proper access permissions.",
        ('sign in', 'login', 'authentication'): "This video requires login. Please add credentials in Settings.",
        ('copyright',): "This video is copyright protected and cannot be downloaded.",
        ('unavailable',): "Video unavailable. It might be deleted, private, or region-restricted.",
        ('network', 'connection'): "Network error. Check your internet connection.",
        ('timeout', 'timed out'): "Connection timeout. The server took too long to respond.",
        ('format not available',): "Requested format not available. Try a different quality.",
        ('ffmpeg', 'ffprobe'): "FFmpeg error. The video processing failed.",
    }
    
    for keywords, message in error_mappings.items():
        if any(keyword in error_lower for keyword in keywords):
            return message
    
    # Generic error with truncated message
    return f"Download failed: {str(error_str)[:150]}"

def is_cancelled(download_id):
    """Check if download has been cancelled"""
    with downloads_lock:
        if download_id not in active_downloads:
            return True
        return active_downloads[download_id].get('cancelled', False)

# Exposed Eel functions
@eel.expose
def get_video_info(url):
    """Fetch video metadata without downloading"""
    try:
        config = load_config()
        
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'socket_timeout': 30,
            'no_check_certificate': False,
        }
        
        # Set FFmpeg location for bundled app
        ffmpeg_path = get_resource_path('ffmpeg')
        if os.path.exists(ffmpeg_path):
            ydl_opts['ffmpeg_location'] = ffmpeg_path
        
        # Add credentials if available
        if config.get('credentials', {}).get('username'):
            ydl_opts['username'] = config['credentials']['username']
            ydl_opts['password'] = config['credentials']['password']
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            video_id = info.get('id', 'unknown')
            thumbnail_url = info.get('thumbnail', '')
            
            # Extract available formats
            formats = []
            format_dict = {}
            
            # First pass: Look for combined video+audio formats
            for f in info.get('formats', []):
                if f.get('vcodec') != 'none' and f.get('acodec') != 'none':
                    resolution = f.get('height', 0)
                    if resolution >= 720:
                        key = f"{resolution}p"
                        if key not in format_dict:
                            format_dict[key] = {
                                'format_id': f['format_id'],
                                'resolution': key,
                                'ext': f.get('ext', 'mp4'),
                                'filesize': f.get('filesize', 0) or f.get('filesize_approx', 0),
                                'fps': f.get('fps', 30),
                                'vcodec': f.get('vcodec', 'unknown'),
                                'acodec': f.get('acodec', 'unknown')
                            }
            
            # Second pass: If no combined formats, estimate from separate streams
            if not format_dict:
                video_formats = {}
                best_audio_size = 0
                
                for f in info.get('formats', []):
                    resolution = f.get('height', 0)
                    
                    # Collect video streams
                    if f.get('vcodec') != 'none' and resolution >= 720:
                        key = f"{resolution}p"
                        if key not in video_formats:
                            video_formats[key] = {
                                'format_id': f['format_id'],
                                'resolution': key,
                                'ext': f.get('ext', 'mp4'),
                                'filesize': f.get('filesize', 0) or f.get('filesize_approx', 0),
                                'fps': f.get('fps', 30),
                                'vcodec': f.get('vcodec', 'unknown'),
                                'acodec': 'merged'
                            }
                    
                    # Find best audio stream size
                    elif f.get('acodec') != 'none' and f.get('vcodec') == 'none':
                        fsize = f.get('filesize', 0) or f.get('filesize_approx', 0)
                        if fsize > best_audio_size:
                            best_audio_size = fsize
                
                # Combine video + audio sizes
                for key, fmt in video_formats.items():
                    fmt['filesize'] = fmt.get('filesize', 0) + best_audio_size
                    format_dict[key] = fmt
            
            # Sort formats by resolution
            formats = sorted(format_dict.values(), key=lambda x: int(x['resolution'][:-1]))
            
            logging.info(f"Fetched info for: {info.get('title', 'Unknown')}")
            
            return {
                'success': True,
                'title': info.get('title', 'Unknown'),
                'thumbnail': thumbnail_url,
                'duration': info.get('duration', 0),
                'uploader': info.get('uploader', 'Unknown'),
                'description': info.get('description', '')[:300],
                'formats': formats,
                'url': url,
                'video_id': video_id,
                'view_count': info.get('view_count', 0),
                'upload_date': info.get('upload_date', '')
            }
            
    except Exception as e:
        logging.exception(f"Failed to fetch video info for: {url}")
        error_msg = format_error_message(str(e))
        return {
            'success': False,
            'error': error_msg,
            'technical_error': str(e)
        }

@eel.expose
def download_video(url, format_choice, quality, download_id):
    """Start video download in background thread"""
    
    def progress_hook(d):
        """Called by yt-dlp during download to report progress"""
        # Check cancellation on every progress update
        if is_cancelled(download_id):
            raise yt_dlp.utils.DownloadError("CANCELLED")
        
        if d['status'] == 'downloading':
            downloaded = d.get('downloaded_bytes', 0)
            total = d.get('total_bytes', 0) or d.get('total_bytes_estimate', 0)
            speed = d.get('speed', 0)
            eta = d.get('eta', 0)
            
            if total > 0:
                percent = (downloaded / total) * 100
                try:
                    eel.update_progress(download_id, {
                        'percent': percent,
                        'downloaded': downloaded,
                        'total': total,
                        'speed': speed or 0,
                        'eta': eta or 0,
                        'status': 'downloading'
                    })
                except:
                    pass
                    
        elif d['status'] == 'finished':
            try:
                eel.update_progress(download_id, {
                    'percent': 100,
                    'status': 'processing',
                    'message': 'Merging video and audio streams...'
                })
            except:
                pass
    
    def download_thread():
        """Background thread for download execution"""
        config = load_config()
        max_retries = config.get('max_retries', 5)
        retry_delay = config.get('retry_delay', 3)
        
        for attempt in range(max_retries):
            # Check if cancelled before starting attempt
            if is_cancelled(download_id):
                logging.info(f"Download {download_id} cancelled before attempt {attempt + 1}")
                cleanup_download(download_id, 'cancelled')
                return
            
            try:
                # Show retry message if not first attempt
                if attempt > 0:
                    try:
                        eel.update_progress(download_id, {
                            'status': 'retrying',
                            'message': f'Retry attempt {attempt + 1} of {max_retries}...',
                            'retry_count': attempt + 1
                        })
                    except:
                        pass
                    time.sleep(retry_delay)
                
                download_path = config.get('download_path', DOWNLOAD_DIR)
                Path(download_path).mkdir(parents=True, exist_ok=True)
                
                # Configure yt-dlp options
                ydl_opts = {
                    'format': f'bestvideo[height<={quality}][ext=mp4]+bestaudio[ext=m4a]/best[height<={quality}]',
                    'outtmpl': os.path.join(download_path, '%(title)s.%(ext)s'),
                    'progress_hooks': [progress_hook],
                    'merge_output_format': 'mp4',
                    'concurrent_fragment_downloads': 8,
                    'http_chunk_size': 524288,  # 512KB chunks for faster cancellation response
                    'retries': 10,
                    'fragment_retries': 10,
                    'skip_unavailable_fragments': True,
                    'socket_timeout': 5,
                    'quiet': True,
                    'no_warnings': True,
                    'prefer_ffmpeg': True,
                    'keepvideo': False,
                    'postprocessor_args': ['-threads', '4'],
                    'noprogress': False,
                    'restrictfilenames': False,
                }
                
                # Set FFmpeg location for bundled app
                ffmpeg_path = get_resource_path('ffmpeg')
                if os.path.exists(ffmpeg_path):
                    ydl_opts['ffmpeg_location'] = ffmpeg_path
                
                # Audio-only configuration
                if format_choice == 'audio':
                    ydl_opts['format'] = 'bestaudio/best'
                    ydl_opts['postprocessors'] = [{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'mp3',
                        'preferredquality': '192',
                    }]
                
                # Add credentials if configured
                if config.get('credentials', {}).get('username'):
                    ydl_opts['username'] = config['credentials']['username']
                    ydl_opts['password'] = config['credentials']['password']
                
                # Execute download
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    logging.info(f"Starting download {download_id} (attempt {attempt + 1})")
                    info = ydl.extract_info(url, download=True)
                
                # Check if cancelled after download completes
                if is_cancelled(download_id):
                    logging.info(f"Download {download_id} cancelled after completion")
                    cleanup_download(download_id, 'cancelled')
                    return
                
                # Download thumbnail
                title = info.get('title', 'Unknown')
                thumbnail_url = info.get('thumbnail', '')
                if thumbnail_url:
                    download_thumbnail(thumbnail_url, title)
                
                # Prepare info for history
                info['format_selected'] = f"{quality}p {format_choice}"
                info['filesize'] = info.get('filesize', 0) or info.get('filesize_approx', 0)
                
                # Save to history
                add_to_history(info, thumbnail_url)
                
                # Notify completion
                try:
                    eel.update_progress(download_id, {
                        'percent': 100,
                        'status': 'completed',
                        'message': '✓ Download completed successfully!'
                    })
                except:
                    pass
                
                # Cleanup
                with downloads_lock:
                    active_downloads.pop(download_id, None)
                
                logging.info(f"Download {download_id} completed successfully")
                return
                    
            except Exception as e:
                error_str = str(e)
                
                # Check if it was a cancellation
                if 'CANCELLED' in error_str or is_cancelled(download_id):
                    logging.info(f"Download {download_id} cancelled during execution")
                    cleanup_download(download_id, 'cancelled')
                    return
                
                error_msg = format_error_message(error_str)
                logging.error(f"Download {download_id} attempt {attempt + 1} failed: {error_str}")
                
                # Retry or fail
                if attempt < max_retries - 1:
                    continue
                else:
                    # Max retries reached
                    try:
                        eel.update_progress(download_id, {
                            'status': 'error',
                            'message': error_msg,
                            'technical_error': error_str,
                            'retry_count': attempt + 1
                        })
                    except:
                        pass
                    
                    with downloads_lock:
                        active_downloads.pop(download_id, None)
                    
                    logging.error(f"Download {download_id} failed after {attempt + 1} attempts")
                    return
    
    # Start download thread
    thread = threading.Thread(target=download_thread, daemon=True, name=f"Download-{download_id}")
    
    with downloads_lock:
        active_downloads[download_id] = {'thread': thread, 'cancelled': False}
    
    thread.start()
    logging.info(f"Download thread started for {download_id}")
    
    return {'success': True, 'download_id': download_id}

def cleanup_download(download_id, status='cancelled'):
    """Clean up download and notify UI"""
    with downloads_lock:
        active_downloads.pop(download_id, None)
    
    try:
        eel.update_progress(download_id, {
            'status': status,
            'message': 'Download cancelled by user' if status == 'cancelled' else 'Download stopped'
        })
    except:
        pass

@eel.expose
def cancel_download(download_id):
    """Cancel an active download"""
    with downloads_lock:
        if download_id in active_downloads:
            # Mark as cancelled
            active_downloads[download_id]['cancelled'] = True
            logging.info(f"Download {download_id} marked for cancellation")
            
            try:
                eel.update_progress(download_id, {
                    'status': 'cancelling',
                    'message': 'Cancelling download...'
                })
            except:
                pass
            
            return {'success': True}
        else:
            logging.warning(f"Cancel requested for unknown download: {download_id}")
            return {'success': False, 'error': 'Download not found'}

@eel.expose
def get_history():
    """Get download history"""
    return load_history()

@eel.expose
def clear_history():
    """Clear all download history"""
    save_history([])
    logging.info("Download history cleared")
    return {'success': True}

@eel.expose
def get_settings():
    """Get current settings"""
    return load_config()

@eel.expose
def save_settings(settings):
    """Save user settings"""
    save_config(settings)
    return {'success': True}

@eel.expose
def select_folder():
    """Open native folder selection dialog"""
    try:
        import tkinter as tk
        from tkinter import filedialog
        
        root = tk.Tk()
        root.withdraw()
        root.wm_attributes('-topmost', 1)
        
        folder_path = filedialog.askdirectory(
            title='Select Download Folder',
            initialdir=os.getcwd()
        )
        
        root.destroy()
        
        if folder_path:
            logging.info(f"Folder selected: {folder_path}")
            return folder_path
        return None
        
    except Exception as e:
        logging.exception("Error opening folder dialog")
        return None

# Application entry point
if __name__ == '__main__':
    try:
        logging.info("=" * 50)
        logging.info("Application starting...")
        logging.info(f"Download directory: {os.path.abspath(DOWNLOAD_DIR)}")
        logging.info(f"Config file: {os.path.abspath(CONFIG_FILE)}")
        logging.info(f"History file: {os.path.abspath(HISTORY_FILE)}")
        logging.info("=" * 50)
        
        eel.start('index.html', size=(1400, 900), port=8080)
        
    except Exception:
        logging.exception("Failed to start application")
        raise
