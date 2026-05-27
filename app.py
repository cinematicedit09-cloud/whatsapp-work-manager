import os
import json
import datetime
from functools import wraps
from flask import Flask, request, jsonify, render_template, session, redirect, url_for

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "workbot-secret-key-change-me")

# --- Configuration ---
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

# --- Multi-User Login System ---
# Users stored in a JSON file so anyone can sign up
USERS_FILE = "users.json"

# Load initial users from env (if any) + file
def load_users():
    """Load users from JSON file."""
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r") as f:
            return json.load(f)
    # First time: create from env variable or default admin
    users_str = os.environ.get("USERS", "admin:workbot123")
    users = {}
    for pair in users_str.split(","):
        if ":" in pair:
            u, p = pair.strip().split(":", 1)
            users[u.strip()] = p.strip()
    save_users(users)
    return users

def save_users(users):
    """Save users to JSON file."""
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)

USERS = load_users()


# --- Authentication ---
def login_required(f):
    """Decorator to protect routes with login."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("logged_in"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "Not authenticated"}), 401
            return redirect(url_for("login_page"))
        return f(*args, **kwargs)
    return decorated_function

# Lazy import groq to handle missing key gracefully
groq_client = None
try:
    from groq import Groq
    if GROQ_API_KEY:
        groq_client = Groq(api_key=GROQ_API_KEY)
except Exception:
    pass


# --- AI Chat Logic ---
def get_ai_response(user_message, tasks):
    """Get AI response for work management."""
    if not groq_client:
        return {"response": "Error: GROQ_API_KEY not set. Please add it in Render environment variables.", "task_action": None}

    pending_tasks = [t for t in tasks if not t.get("done")]
    done_tasks = [t for t in tasks if t.get("done")]

    system_prompt = f"""You are WorkBot - an intelligent AI personal work manager and productivity assistant.
You help users manage their work, tasks, schedule, and answer any questions they have.

You can understand English, Hindi, Hinglish, and Punjabi.

CURRENT TASKS:
Pending ({len(pending_tasks)}): {json.dumps(pending_tasks[:10], indent=1) if pending_tasks else "None"}
Completed ({len(done_tasks)}): {len(done_tasks)} tasks done

YOUR CAPABILITIES:
1. Answer ANY question the user asks (like ChatGPT/Claude)
2. Help manage tasks (add, complete, delete, prioritize)
3. Plan their day/week based on pending tasks
4. Give productivity advice and work strategies
5. Help with brainstorming, writing, coding questions
6. Summarize work status and progress

TASK DETECTION:
If the user wants to ADD a task, include in your response the task naturally AND return a task_action.
If they want to COMPLETE or DELETE a task, acknowledge it AND return a task_action.

RESPONSE STYLE:
- Be conversational, friendly, and helpful
- Keep responses focused and useful (not too long unless explaining something complex)
- Use emojis sparingly for readability
- Format lists and plans clearly
- If user asks a general question (coding, life, anything), answer it fully like a smart assistant

IMPORTANT: You are NOT just a task manager. You are a full AI assistant that ALSO manages tasks.
Answer coding questions, explain concepts, help with writing, give advice - do everything!"""

    try:
        response = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=0.7,
            max_tokens=1000,
        )
        ai_text = response.choices[0].message.content.strip()
    except Exception as e:
        print(f"AI Error: {e}")
        ai_text = "Sorry, having a brain freeze. Try again in a moment!"

    # Detect task actions
    task_action = detect_task_action(user_message)

    return {"response": ai_text, "task_action": task_action}


def detect_task_action(message):
    """Detect if user wants to add/complete/delete a task."""
    msg = message.lower().strip()

    # Add task patterns
    add_patterns = ["add task", "add:", "new task", "task add", "add kar", "create task", "remind me to", "need to"]
    for pattern in add_patterns:
        if pattern in msg:
            # Extract task text
            task_text = message
            for p in ["add task:", "add task", "add:", "new task:", "new task", "task add:", "create task:", "remind me to", "need to"]:
                if p.lower() in msg:
                    idx = msg.index(p.lower()) + len(p)
                    task_text = message[idx:].strip().strip(":-").strip()
                    break

            priority = "medium"
            if any(w in msg for w in ["urgent", "important", "high", "asap", "critical"]):
                priority = "high"
            elif any(w in msg for w in ["low", "later", "sometime", "optional"]):
                priority = "low"

            if task_text:
                return {"type": "add", "task": task_text, "priority": priority}

    # Complete task patterns
    done_patterns = ["done:", "done ", "complete:", "completed", "finished", "mark done", "ho gaya", "kar liya"]
    for pattern in done_patterns:
        if pattern in msg:
            text = message
            for p in ["done:", "done ", "complete:", "completed:", "finished:", "mark done:"]:
                if p.lower() in msg:
                    idx = msg.index(p.lower()) + len(p)
                    text = message[idx:].strip()
                    break
            if text:
                return {"type": "done", "text": text}

    # Delete task patterns
    del_patterns = ["delete task", "remove task", "cancel task", "delete:", "remove:"]
    for pattern in del_patterns:
        if pattern in msg:
            text = message
            for p in ["delete task:", "delete task", "remove task:", "remove task", "cancel task:", "delete:", "remove:"]:
                if p.lower() in msg:
                    idx = msg.index(p.lower()) + len(p)
                    text = message[idx:].strip()
                    break
            if text:
                return {"type": "delete", "text": text}

    return None


# --- Routes ---
@app.route("/login", methods=["GET"])
def login_page():
    """Show login page."""
    if session.get("logged_in"):
        return redirect(url_for("home"))
    return render_template("login.html")


@app.route("/api/login", methods=["POST"])
def login():
    """Handle login."""
    data = request.json
    username = data.get("username", "").strip()
    password = data.get("password", "")

    global USERS
    USERS = load_users()

    if username in USERS and USERS[username] == password:
        session["logged_in"] = True
        session["username"] = username
        return jsonify({"success": True, "username": username})
    return jsonify({"success": False, "error": "Wrong username or password"}), 401


@app.route("/api/signup", methods=["POST"])
def signup():
    """Handle sign up - create new account."""
    data = request.json
    username = data.get("username", "").strip()
    password = data.get("password", "")

    if not username or not password:
        return jsonify({"success": False, "error": "Username and password required"}), 400

    if len(username) < 3:
        return jsonify({"success": False, "error": "Username must be at least 3 characters"}), 400

    if len(password) < 4:
        return jsonify({"success": False, "error": "Password must be at least 4 characters"}), 400

    global USERS
    USERS = load_users()

    if username in USERS:
        return jsonify({"success": False, "error": "Username already taken! Try another."}), 400

    # Create account
    USERS[username] = password
    save_users(USERS)

    # Auto-login after signup
    session["logged_in"] = True
    session["username"] = username
    return jsonify({"success": True, "username": username})


@app.route("/api/logout", methods=["POST"])
def logout():
    """Handle logout."""
    session.clear()
    return jsonify({"success": True})


@app.route("/")
@login_required
def home():
    """Serve the main app."""
    return render_template("index.html")


@app.route("/api/chat", methods=["POST"])
@login_required
def chat():
    """Handle chat messages."""
    data = request.json
    user_message = data.get("message", "").strip()
    tasks = data.get("tasks", [])

    if not user_message:
        return jsonify({"error": "No message"}), 400

    result = get_ai_response(user_message, tasks)
    return jsonify(result)


@app.route("/health")
def health():
    """Health check."""
    return jsonify({"status": "running", "ai": bool(groq_client)})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
