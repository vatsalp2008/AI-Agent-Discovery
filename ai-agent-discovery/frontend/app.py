import os
import sys

from flask import Flask, redirect, render_template, url_for

# Add backend to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))

import config
import request_log
from api import api_bp, register_error_handlers
from logging_setup import configure

configure()

app = Flask(__name__,
            static_folder='static',
            template_folder='templates')

app.register_blueprint(api_bp)
register_error_handlers(app)
request_log.register(app)

@app.route('/')
def index():
    return render_template('index.html', page='search')

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html', page='dashboard')

@app.route('/favicon.ico')
def favicon():
    """Browsers request this path directly, regardless of the <link> tag."""
    return redirect(url_for('static', filename='img/favicon.svg'), code=301)

if __name__ == '__main__':
    app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG)
