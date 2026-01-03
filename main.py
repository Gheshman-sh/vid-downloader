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
import subprocess
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
active_downloads = {}  # download_id -> {'thread': thread, 'process': subprocess, 'cancelled': bool}
downloads_lock = threading.Lock()

# Logging
logging.basicConfig(
    filename='app.log',
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            logging.exception("Failed loading config")
    return {
        'credentials': {},
        'download_path': DOWNLOAD_DIR,
        'max_retries': 5,
        'retry_delay': 3
    }

def save_config(config):
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=2)
    except Exception:
        logging.exception("Failed to save config")

def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            logging.exception("Failed loading history")
    return []

def save_history(history):
    try:
        with open(HISTORY_FILE, 'w') as f:
            json.dump(history, f, indent=2)
    except Exception:
        logging.exception("Failed to save history")

def sanitize_filename(filename):
    """Remove invalid characters from filename"""
    return re.sub(r'[<>:"/\\|?*]', '', filename)

def add_to_history(video_info, thumbnail_url):
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
        history = history[:100]
        save_history(history)
    except Exception:
        logging.exception("Failed to add to history")

def download_thumbnail(url, title):
    """Download thumbnail and save with video title name"""
    try:
        if not url:
            return None
        
        thumb_dir = os.path.join(DOWNLOAD_DIR, 'thumbnails')
        Path(thumb_dir).mkdir(exist_ok=True)
        
        safe_title = sanitize_filename(title)[:100]
        thumb_path = os.path.join(thumb_dir, f'{safe_title}.jpg')
        
        if not os.path.exists(thumb_path):
            urllib.request.urlretrieve(url, thumb_path)
        
        return thumb_path
    except Exception:
        logging.warning(f"Thumbnail download failed for {url}")
        return None

def format_error_message(error_str):
    """Convert technical errors to user-friendly messages"""
    error_lower = str(error_str).lower()
    
    if 'cancelled' in error_lower or 'canceled' in error_lower or 'killed' in error_lower:
        return "Download cancelled by user"
    elif 'http error 403' in error_lower or 'forbidden' in error_lower:
        return "Access denied. The video might be private, region-blocked, or require authentication. Try adding credentials in Settings."
    elif 'http error 404' in error_lower:
        return "Video not found. The URL might be incorrect or the video was removed."
    elif 'http error 429' in error_lower:
        return "Too many requests. The website is rate-limiting. Please wait a few minutes and try again."
    elif 'private video' in error_lower:
        return "This is a private video. You need proper access permissions to download it."
    elif 'sign in' in error_lower or 'login' in error_lower:
        return "This video requires login. Please add your credentials in Settings."
    elif 'copyright' in error_lower:
        return "This video is copyright protected and cannot be downloaded."
    elif 'unavailable' in error_lower:
        return "Video unavailable. It might be deleted, private, or not available in your region."
    elif 'network' in error_lower or 'connection' in error_lower:
        return "Network error. Check your internet connection and try again."
    elif 'timeout' in error_lower:
        return "Connection timeout. The server took too long to respond. Try again later."
    elif 'format' in error_lower:
        return "Requested format not available. Try selecting a different quality."
    elif 'ffmpeg' in error_lower or 'ffprobe' in error_lower:
        return "FFmpeg is not installed or not found in PATH. Please install FFmpeg to merge video and audio."
    else:
        return f"Download failed: {error_str[:150]}"

def is_cancelled(download_id):
    """Check if download is cancelled"""
    with downloads_lock:
        if download_id not in active_downloads:
            return True
        return active_downloads[download_id].get('cancelled', False)

@eel.expose
def get_video_info(url):
    try:
        config = load_config()
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'socket_timeout': 30,
        }
        
        if config.get('credentials', {}).get('username'):
            ydl_opts['username'] = config['credentials']['username']
            ydl_opts['password'] = config['credentials']['password']
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            video_id = info.get('id', 'unknown')
            thumbnail_url = info.get('thumbnail', '')
            
            formats = []
            format_dict = {}
            
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
            
            if not format_dict:
                video_formats = {}
                audio_size = 0
                
                for f in info.get('formats', []):
                    resolution = f.get('height', 0)
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
                    elif f.get('acodec') != 'none' and f.get('vcodec') == 'none':
                        fsize = f.get('filesize', 0) or f.get('filesize_approx', 0)
                        if fsize > audio_size:
                            audio_size = fsize
                
                for key, fmt in video_formats.items():
                    fmt['filesize'] = fmt.get('filesize', 0) + audio_size
                    format_dict[key] = fmt
            
            formats = sorted(format_dict.values(), key=lambda x: int(x['resolution'][:-1]))
            
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
        error_msg = format_error_message(str(e))
        return {'success': False, 'error': error_msg, 'technical_error': str(e)}

@eel.expose
def download_video(url, format_choice, quality, download_id):
    
    def progress_hook(d):
        # Check cancellation
        if is_cancelled(download_id):
            raise Exception("Download cancelled by user")
        
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
        config = load_config()
        max_retries = config.get('max_retries', 5)
        retry_delay = config.get('retry_delay', 3)
        
        for attempt in range(max_retries):
            if is_cancelled(download_id):
                logging.info(f"Download {download_id} cancelled before attempt {attempt + 1}")
                return
            
            try:
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
                
                # Optimized options
                ydl_opts = {
                    'format': f'bestvideo[height<={quality}][ext=mp4]+bestaudio[ext=m4a]/best[height<={quality}]',
                    'outtmpl': os.path.join(download_path, '%(title)s.%(ext)s'),
                    'progress_hooks': [progress_hook],
                    'merge_output_format': 'mp4',
                    'concurrent_fragment_downloads': 8,
                    'http_chunk_size': 10485760,
                    'retries': 10,
                    'fragment_retries': 10,
                    'skip_unavailable_fragments': True,
                    'socket_timeout': 30,
                    'quiet': True,
                    'no_warnings': True,
                    'prefer_ffmpeg': True,
                    'keepvideo': False,
                    'postprocessor_args': ['-threads', '4'],
                }
                
                if format_choice == 'audio':
                    ydl_opts['format'] = 'bestaudio/best'
                    ydl_opts['postprocessors'] = [{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'mp3',
                        'preferredquality': '192',
                    }]
                
                if config.get('credentials', {}).get('username'):
                    ydl_opts['username'] = config['credentials']['username']
                    ydl_opts['password'] = config['credentials']['password']
                
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                
                if is_cancelled(download_id):
                    logging.info(f"Download {download_id} cancelled after completion")
                    return
                
                # Download thumbnail
                title = info.get('title', 'Unknown')
                thumbnail_url = info.get('thumbnail', '')
                if thumbnail_url:
                    download_thumbnail(thumbnail_url, title)
                
                info['format_selected'] = f"{quality}p {format_choice}"
                info['filesize'] = info.get('filesize', 0) or info.get('filesize_approx', 0)
                
                add_to_history(info, thumbnail_url)
                
                try:
                    eel.update_progress(download_id, {
                        'percent': 100,
                        'status': 'completed',
                        'message': '✓ Download completed successfully!'
                    })
                except:
                    pass
                
                with downloads_lock:
                    active_downloads.pop(download_id, None)
                
                logging.info(f"Download {download_id} completed")
                return
                    
            except Exception as e:
                error_str = str(e)
                
                if 'cancelled' in error_str.lower() or is_cancelled(download_id):
                    with downloads_lock:
                        active_downloads.pop(download_id, None)
                    try:
                        eel.update_progress(download_id, {
                            'status': 'cancelled',
                            'message': 'Download cancelled by user'
                        })
                    except:
                        pass
                    logging.info(f"Download {download_id} cancelled")
                    return
                
                error_msg = format_error_message(error_str)
                
                if attempt < max_retries - 1:
                    logging.info(f"Download attempt {attempt + 1} failed: {error_str}")
                    continue
                else:
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
                    return
    
    thread = threading.Thread(target=download_thread, daemon=True, name=f"Download-{download_id}")
    
    with downloads_lock:
        active_downloads[download_id] = {'thread': thread, 'cancelled': False}
    
    thread.start()
    
    return {'success': True, 'download_id': download_id}

@eel.expose
def get_history():
    return load_history()

@eel.expose
def clear_history():
    save_history([])
    return {'success': True}

@eel.expose
def get_settings():
    return load_config()

@eel.expose
def save_settings(settings):
    save_config(settings)
    return {'success': True}

@eel.expose
def cancel_download(download_id):
    """Cancel download by setting cancelled flag"""
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
            return {'success': False, 'error': 'Download not found'}

@eel.expose
def select_folder():
    """Open folder selection dialog"""
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
        
        return folder_path if folder_path else None
    except Exception as e:
        logging.exception("Error selecting folder")
        return None

# Start the application
if __name__ == '__main__':
    eel.start('index.html', size=(1400, 900), port=8080)