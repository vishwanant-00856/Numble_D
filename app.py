from flask import Flask, render_template_string, request, jsonify, session
import random
import json
from sympy import isprime
import os
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Rate limiting
limiter = Limiter(get_remote_address, app=app, default_limits=["10 per minute"])

WORD_LENGTH = 5
MAX_ATTEMPTS = 10
PRIMES_FILE = "five_digit_primes.json"

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

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Numble</title>
    <style>
        body { background: #121213; color: white; font-family: Arial, sans-serif; text-align: center; }
        .grid { display: grid; grid-template-columns: repeat(5, 60px); gap: 10px; justify-content: center; margin-top: 40px; }
        .cell { width: 60px; height: 60px; font-size: 36px; font-weight: bold; background: #3a3a3c; color: white; display: flex; align-items: center; justify-content: center; border-radius: 4px; }
        .correct { background: #6aaa64; }
        .present { background: #c9b458; }
        .absent { background: #787c7e; }
        input { font-size: 20px; padding: 10px; width: 200px; margin-top: 20px; }
        button { padding: 10px 20px; font-size: 16px; background-color: #538d4e; color: white; border: none; cursor: pointer; }
    </style>
</head>
<body>
    <h1>Numble</h1>
    <div id="grid"></div>
    <input type="text" id="guess" maxlength="5" placeholder="Enter 5-digit prime">
    <button onclick="submitGuess()">Guess</button>
    <button onclick="getHint()">Hint</button>
    <p id="message"></p>

    <script>
        let attempts = 0;
        const maxAttempts = {{ max_attempts }};

        function createRow(guess, feedback) {
            const grid = document.getElementById('grid');
            const row = document.createElement('div');
            row.className = 'grid';
            for (let i = 0; i < guess.length; i++) {
                const cell = document.createElement('div');
                cell.className = 'cell ' + feedback[i];
                cell.innerText = guess[i];
                row.appendChild(cell);
            }
            grid.appendChild(row);
        }

        function submitGuess() {
            const guess = document.getElementById('guess').value;
            fetch('/guess', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ guess })
            })
            .then(res => res.json())
            .then(data => {
                if (data.error) {
                    document.getElementById('message').innerText = data.error;
                    return;
                }
                createRow(data.guess, data.feedback);
                document.getElementById('message').innerText = data.message;
                document.getElementById('guess').value = '';
            });
        }

        function getHint() {
            fetch('/hint')
            .then(res => res.json())
            .then(data => {
                document.getElementById('message').innerText = data.hint;
            });
        }
    </script>
</body>
</html>
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
    if 'target_number' not in session:
        session['target_number'] = random.choice(FIVE_DIGIT_PRIMES)
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
        return jsonify({"guess": guess, "feedback": feedback, "message": "Congratulations! You guessed it! 🎉"})
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

if __name__ == "__main__":
    app.run(debug=True)
