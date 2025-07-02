from flask import Flask, render_template_string, request, jsonify, session, redirect, url_for
import random
import json
from sympy import isprime
import os
import datetime
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from collections import defaultdict

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Rate limiting
limiter = Limiter(get_remote_address, app=app, default_limits=["10 per minute"])

WORD_LENGTH = 5
MAX_ATTEMPTS = 10
PRIMES_FILE = "five_digit_primes.json"
LEADERBOARD_FILE = "leaderboard.json"
hint_cooldown = 1  # Allow 1 hint per game session

def generate_five_digit_primes():
    return [str(num) for num in range(10000, 100000) if isprime(num)]

def load_five_digit_primes():
    if os.path.exists(PRIMES_FILE):
        with open(PRIMES_FILE, "r") as f:
            return json.load(f)
    else:
        primes = generate_five_digit_primes()
        with open(PRIMES_FILE, "w") as f:
            json.dump(primes, f)
        return primes

FIVE_DIGIT_PRIMES = load_five_digit_primes()

# Deterministically select a prime based on a specific date
def get_daily_prime(for_date=None):
    if not for_date:
        for_date = datetime.date.today()
    index = for_date.toordinal() % len(FIVE_DIGIT_PRIMES)
    return FIVE_DIGIT_PRIMES[index]

def load_leaderboard():
    if os.path.exists(LEADERBOARD_FILE):
        with open(LEADERBOARD_FILE, "r") as f:
            return json.load(f)
    return {}

def save_leaderboard(data):
    with open(LEADERBOARD_FILE, "w") as f:
        json.dump(data, f, indent=2)

HTML_TEMPLATE = """
<!-- HTML template placeholder -->
"""

def get_feedback(guess, target):
    feedback = ['absent'] * len(guess)
    target_counts = {}

    for digit in target:
        target_counts[digit] = target_counts.get(digit, 0) + 1

    for i in range(len(guess)):
        if guess[i] == target[i]:
            feedback[i] = 'correct'
            target_counts[guess[i]] -= 1

    for i in range(len(guess)):
        if feedback[i] == 'correct':
            continue
        if guess[i] in target_counts and target_counts[guess[i]] > 0:
            feedback[i] = 'present'
            target_counts[guess[i]] -= 1

    return feedback

@app.before_request
def initialize_game():
    if 'date' not in session:
        session['date'] = str(datetime.date.today())
    if 'target_number' not in session:
        session['target_number'] = get_daily_prime()
        session['guess_history'] = []
        session['hints_used'] = 0

@app.route("/")
def home():
    return render_template_string(HTML_TEMPLATE, max_attempts=MAX_ATTEMPTS)

@app.route("/guess", methods=["POST"])
@limiter.limit("10 per minute")
def guess():
    data = request.get_json()
    guess = data.get("guess", "")

    if len(guess) != WORD_LENGTH or not guess.isdigit():
        return jsonify({"error": "Please enter a 5-digit number."})
    if not isprime(int(guess)):
        return jsonify({"error": "Not a valid 5-digit prime number."})

    guess_history = session.get('guess_history', [])
    if len(guess_history) >= MAX_ATTEMPTS:
        return jsonify({"error": "No more attempts left!"})

    target_number = session['target_number']
    feedback = get_feedback(guess, target_number)
    guess_history.append((guess, feedback))
    session['guess_history'] = guess_history

    if guess == target_number:
        date_str = session['date']
        leaderboard = load_leaderboard()
        leaderboard.setdefault(date_str, []).append(len(guess_history))
        save_leaderboard(leaderboard)
        result_str = ''.join([f"[{f[0]}]" for f in guess_history])
        return jsonify({"guess": guess, "feedback": feedback, "message": "Congratulations! You guessed it! 🎉", "share": result_str})
    elif len(guess_history) >= MAX_ATTEMPTS:
        return jsonify({"guess": guess, "feedback": feedback, "message": f"Game Over! The number was {target_number}."})
    else:
        return jsonify({"guess": guess, "feedback": feedback, "message": "Try again!"})

@app.route("/hint")
@limiter.limit("3 per minute")
def hint():
    guess_history = session.get('guess_history', [])
    target_number = session.get('target_number')

    if session.get('hints_used', 0) >= hint_cooldown:
        return jsonify({"hint": "No more hints allowed for this game."})

    if len(guess_history) < 3:
        return jsonify({"hint": "Hints unlock after 3 attempts!"})

    unrevealed = [i for i in range(WORD_LENGTH) if all(g[i] != target_number[i] for g, _ in guess_history)]
    if unrevealed:
        i = random.choice(unrevealed)
        session['hints_used'] = session.get('hints_used', 0) + 1
        return jsonify({"hint": f"Digit {i+1} is {target_number[i]}"})
    return jsonify({"hint": "All digits have been revealed."})

@app.route("/leaderboard")
def leaderboard():
    board = load_leaderboard()
    today = str(datetime.date.today())
    entries = board.get(today, [])
    return jsonify({"date": today, "entries": entries})

@app.route("/game/<date>")
def game_by_date(date):
    try:
        target_date = datetime.datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        return "Invalid date format. Use YYYY-MM-DD."
    session.clear()
    session['target_number'] = get_daily_prime(target_date)
    session['guess_history'] = []
    session['hints_used'] = 0
    session['date'] = str(target_date)
    return redirect(url_for("home"))

if __name__ == "__main__":
    app.run(debug=True)
