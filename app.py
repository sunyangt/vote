import logging
import os
from datetime import timedelta


from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from functools import wraps
import random
import json


logging.basicConfig(level=logging.ERROR)

app = Flask(__name__)
app.secret_key = 'applevotesys'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=12)

vote_data = {}
current_person = None
voting_active = False

access_codes = {}



def load_access_codes():
    global access_codes
    try:
        with open("access_codes.json", 'r') as f:
            access_codes = json.load(f)
    except Exception as e:
        print(f"Error loading access codes: {e}")

def generate_access_codes():
    global access_codes
    codes = set()
    while len(codes) < 220:
        code = str(random.randint(10000, 99999))
        codes.add(code)

    access_codes = {code: {'used': False} for code in codes}

    with open("access_codes.json", 'w') as f:
        json.dump(access_codes, f)

    logging.info("Access codes generated and saved to access_codes.json")


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    global voting_active, current_person
    if not session.get('access_code'):
        message = '暂时不需要投票，请耐心等待投票通道开启'
        alert_class = 'alert-info'
        return render_template('vote.html', person=current_person, message=message, alert_class=alert_class)
    if not voting_active or not current_person:
        message = '你已投过票了，请等下一次投票通道开启'
        alert_class = 'alert-info'
        return render_template('vote.html', person=current_person, message=message, alert_class=alert_class)
    # Check if the user has already voted during this session
    if session.get(f'voted_{current_person}'):
        return jsonify({'status': 'error', 'message': 'already voted'})
    return render_template('vote.html', person=current_person)

@app.route('/vote', methods=['POST'])
def vote():
    global access_codes, voting_active, current_person
    if not session.get('access_code'):
        return jsonify({'status': 'error', 'message': 'Not authenticated.'})

    if not voting_active:
        return jsonify({'status': 'error', 'message': 'Voting is not active.'})

    user_access_code = session.get('access_code')

    code_info = access_codes.get(user_access_code)
    # Check if the user has already voted during this session
    if session.get(f'voted_{current_person}') or (code_info and code_info['used']) :
        return jsonify({'status': 'error', 'message': 'You have already voted.'})

    vote_type = request.form.get('vote_type')

    # Record the vote
    if vote_type in ['like', 'dislike']:
        vote_data.setdefault(current_person, {'like': 0, 'dislike': 0})
        vote_data[current_person][vote_type] += 1

        # Mark the user as having voted
        session[f'voted_{current_person}'] = True

        # Mark the access code as used in memory

        if code_info:
            code_info['used'] = True
        else:
            return jsonify({'status': 'error', 'message': 'Invalid access code.'})

        return jsonify({'status': 'success', 'message': 'Your vote has been recorded.'})
    else:
        return jsonify({'status': 'error', 'message': 'Invalid vote type.'})




@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        password = request.form.get('password')
        if password == 'adminpassword':
            session['admin_logged_in'] = True
            return redirect(url_for('admin_dashboard'))
        else:
            return "Incorrect password.", 403
    return render_template('admin_login.html')

@app.route('/admin/dashboard', methods=['GET', 'POST'])
@login_required
def admin_dashboard():
    global current_person, voting_active, vote_data
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'start':
            person = request.form.get('person')
            if person:
                current_person = person
                voting_active = True
                vote_data[current_person] = {'like': 0, 'dislike': 0}

                # Clear previous voting session flags
                session_keys = [key for key in session.keys() if key.startswith('voted_')]
                for key in session_keys:
                    session.pop(key)

                # Reset access codes to unused in memory
                for code in access_codes:
                    access_codes[code]['used'] = False
            else:
                return "Please enter a person's name.", 400
        elif action == 'stop':
            voting_active = False
            save_vote_data()
            current_person = None
            # Clear the in-memory vote data
            vote_data.clear()
        elif action == 'refresh_codes':
            generate_access_codes()
            return render_template('admin_dashboard.html', voting_active=voting_active, current_person=current_person, message='Access codes refreshed.')
    return render_template('admin_dashboard.html', voting_active=voting_active, current_person=current_person)



@app.route('/admin/logout')
@login_required
def admin_logout():
    session.clear()
    return redirect(url_for('admin_login'))

def save_vote_data():
    global vote_data, current_person
    try:
        with open('vote.json', 'r') as f:
            all_votes = json.load(f)
    except FileNotFoundError:
        all_votes = {}

    person_votes = vote_data.get(current_person, {'like': 0, 'dislike': 0})
    total_votes = person_votes['like'] + person_votes['dislike']
    percentage = (person_votes['like'] / total_votes) if total_votes > 0 else 0

    all_votes[current_person] = {
        'like': person_votes['like'],
        'dislike': person_votes['dislike'],
        'percentage': percentage
    }

    with open('vote.json', 'w') as f:
        json.dump(all_votes, f)

@app.route('/results')
def results():
    try:
        with open('vote.json', 'r') as f:
            all_votes = json.load(f)
    except FileNotFoundError:
        all_votes = {}
    return render_template('results.html', all_votes=all_votes)

@app.route('/login', methods=['GET', 'POST'])
def user_login():
    global access_codes
    if request.method == 'POST':
        access_code = request.form.get('access_code')
        if access_code:
            code_info = access_codes.get(access_code)
            if code_info:
                session['access_code'] = access_code
                session.permanent = True
                return redirect(url_for('index'))
            else:
                return render_template('user_login.html', error='Invalid or used access code.')
        else:
            return render_template('user_login.html', error='Please enter an access code.')
    return render_template('user_login.html')

@app.route('/admin/access_codes')
@login_required
def admin_access_codes():
    global access_codes
    if access_codes == {} :
        load_access_codes()
    return render_template('admin_access_codes.html', access_codes=access_codes)

@app.route('/admin/read_file', methods=['GET'])
@login_required
def admin_read_file():
    return render_template('admin_read_file.html')

@app.route('/admin/get')
@login_required
def admin_get():
    # Get the global parameter name from the query string
    param_name = request.args.get('param', None)

    if param_name is None:
        return "No parameter specified", 400

    # Access the global parameter dynamically using globals()
    global_variable = globals().get(param_name, None)

    if global_variable is None:
        return f"Global parameter '{param_name}' not found", 404

    return jsonify({param_name: global_variable})


@app.route('/admin/read_file_result', methods=['POST'])
@login_required
def admin_read_file_result():
    filename = request.form.get('filename')
    if not filename:
        return render_template('admin_read_file.html', error='Please enter a file name.')

    # Security: Prevent directory traversal attacks
    if '..' in filename or filename.startswith('/'):
        return render_template('admin_read_file.html', error='Invalid file name.')

    try:
        # Ensure the file exists in the specified directory
        if not os.path.isfile(filename):
            raise FileNotFoundError(f"File '{filename}' not found.")

        # Read the file content
        with open(filename, 'r', encoding='utf-8') as file:
            content = file.read()

        return render_template('admin_read_file_result.html', filename=filename, content=content)
    except Exception as e:
        # Log the error (optional)
        logging.error(f"Error reading file '{filename}': {e}")
        # Display a generic error message to the user
        return render_template('admin_read_file.html', error=f"Error reading file '{filename}': {e}")


if __name__ == '__main__':
    app.run(debug=False)

