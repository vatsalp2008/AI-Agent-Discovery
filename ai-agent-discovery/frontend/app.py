import os
import sys

from flask import Flask, render_template

# Add backend to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))

import config
from api import api_bp, register_error_handlers
from logging_setup import configure

configure()

app = Flask(__name__,
            static_folder='static',
            template_folder='templates')

app.register_blueprint(api_bp)
register_error_handlers(app)

@app.route('/')
def index():
    return render_template('index.html', page='search')

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html', page='dashboard')

if __name__ == '__main__':
    app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG)
