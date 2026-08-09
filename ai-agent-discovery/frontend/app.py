import atexit
import os
import sys

from flask import Flask, redirect, render_template, url_for

# Add backend to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))

import admin
import config
import request_log
import security
from api import api_bp, register_error_handlers
from embeddings import save_cache
from logging_setup import configure

configure()

app = Flask(__name__,
            static_folder='static',
            template_folder='templates')

app.register_blueprint(api_bp)
register_error_handlers(app)
app.register_blueprint(admin.admin_bp)
admin.register_error_handler(app)
request_log.register(app)
security.register(app)

@app.context_processor
def inject_flags():
    """Template globals. admin_enabled gates the nav link."""
    return {"admin_enabled": config.ENABLE_ADMIN}

@app.route('/')
def index():
    return render_template('index.html', page='search')

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html', page='dashboard')

@app.route('/compare')
def compare():
    """Side-by-side comparison; the agents come from ?names=."""
    return render_template('compare.html', page='compare')

@app.route('/collections')
def collections():
    """Saved shortlists. Entirely client-side; the server stores nothing."""
    return render_template('collections.html', page='collections')

@app.route('/admin')
def admin_page():
    """Catalogue editor. The page itself always renders; the API refuses
    writes unless ENABLE_ADMIN is set, and the page says so."""
    return render_template('admin.html', page='admin')

@app.route('/agent/<path:name>')
def agent_detail(name):
    """Detail page. The agent itself is fetched client-side from the API."""
    return render_template('agent.html', page='search', name=name)

@app.route('/favicon.ico')
def favicon():
    """Browsers request this path directly, regardless of the <link> tag."""
    return redirect(url_for('static', filename='img/favicon.svg'), code=301)

# Flush the query-embedding cache on shutdown so the next start benefits.
atexit.register(save_cache)

if __name__ == '__main__':
    app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG)
