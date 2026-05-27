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
USERS_FILE = "users.json"

def load_users():
    """Load users from JSON file."""
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r") as f:
            return json.load(f)
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
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("logged_in"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "Not authenticated"}), 401
            return redirect(url_for("login_page"))
        return f(*args, **kwargs)
    return decorated_function

# Groq client
groq_client = None
try:
    from groq import Groq
    if GROQ_API_KEY:
        groq_client = Groq(api_key=GROQ_API_KEY)
except Exception:
    pass


# --- Professional AI System Prompt ---
SYSTEM_PROMPT = """You are WorkBot — a highly intelligent, professional AI assistant built for creators, video editors, and professionals.

You are as capable as Claude or ChatGPT. You can do EVERYTHING they can:

## YOUR CORE CAPABILITIES:
1. **Code & Programming** — Write, debug, explain code in any language (Python, JavaScript, HTML/CSS, After Effects expressions, FFmpeg commands, shell scripts, etc.)
2. **Video Editing Help** — DaVinci Resolve, Premiere Pro, After Effects, CapCut, color grading, transitions, effects, export settings, codecs, frame rates, LUTs
3. **Content Creation** — YouTube scripts, thumbnails ideas, titles, descriptions, tags, hooks, storytelling
4. **Writing** — Emails, proposals, captions, blogs, client messages, professional communication
5. **Task & Project Management** — Plan shoots, manage deadlines, organize workflow, track projects
6. **Business & Freelancing** — Pricing, client management, invoicing, portfolio tips, upwork/fiverr strategies
7. **Learning & Research** — Explain concepts, tutorials, comparisons, recommendations
8. **Creative Ideas** — Brainstorming, mood boards, visual concepts, editing styles, trending formats
9. **Problem Solving** — Debug errors, fix issues, find solutions, troubleshoot software
10. **General Knowledge** — Science, tech, history, current events, life advice, anything

## YOUR PERSONALITY:
- Professional but friendly — like a smart coworker
- Direct and concise — don't waste words
- Use formatting (headers, bullet points, code blocks) for clarity
- Understand Hindi, Punjabi, Hinglish naturally
- Give actionable answers, not vague advice
- When you write code, always explain what it does
- When giving suggestions, give specific examples

## TASK MANAGEMENT:
- You also manage the user's tasks/to-do list
- Detect when user wants to add/complete/delete tasks
- Help prioritize and plan their day

## RESPONSE FORMAT:
- Use **bold** for important terms
- Use `code` for technical terms
- Use bullet points for lists
- Use numbered steps for processes
- Keep responses focused — expand only when asked
- For code: always use proper formatting with language specified

You are not a basic chatbot. You are a PROFESSIONAL AI AGENT. Act like one."""


# --- AI Response ---
def get_ai_response(user_message, tasks, chat_history=None):
    """Get professional AI response."""
    if not groq_client:
        return {"response": "**Error:** GROQ_API_KEY not configured. Add it in Render Environment Variables.", "task_action": None}

    pending_tasks = [t for t in tasks if not t.get("done")]
    done_tasks = [t for t in tasks if t.get("done")]

    context = SYSTEM_PROMPT + f"""

## CURRENT USER TASKS:
- Pending: {len(pending_tasks)} tasks
- Completed: {len(done_tasks)} tasks
{"- Tasks: " + ", ".join([t['text'] for t in pending_tasks[:5]]) if pending_tasks else "- No pending tasks"}
"""

    messages = [{"role": "system", "content": context}]

    # Add chat history for context (last 6 messages)
    if chat_history:
        for msg in chat_history[-6:]:
            messages.append({"role": msg["role"], "content": msg["content"]})

    messages.append({"role": "user", "content": user_message})

    try:
        response = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=messages,
            temperature=0.7,
            max_tokens=1500,
        )
        ai_text = response.choices[0].message.content.strip()
    except Exception as e:
        print(f"AI Error: {e}")
        ai_text = "Sorry, server is overloaded. Try again in a moment."

    task_action = detect_task_action(user_message)
    return {"response": ai_text, "task_action": task_action}


def detect_task_action(message):
    """Detect task actions from message."""
    msg = message.lower().strip()

    add_patterns = ["add task", "add:", "new task", "task add", "add kar", "create task", "remind me to", "need to"]
    for pattern in add_patterns:
        if pattern in msg:
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
    if session.get("logged_in"):
        return redirect(url_for("home"))
    return render_template("login.html")


@app.route("/api/login", methods=["POST"])
def login():
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
        return jsonify({"success": False, "error": "Username already taken!"}), 400

    USERS[username] = password
    save_users(USERS)

    session["logged_in"] = True
    session["username"] = username
    return jsonify({"success": True, "username": username})


@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"success": True})


@app.route("/")
@login_required
def home():
    return render_template("index.html")


@app.route("/api/chat", methods=["POST"])
@login_required
def chat():
    data = request.json
    user_message = data.get("message", "").strip()
    tasks = data.get("tasks", [])
    chat_history = data.get("history", [])

    if not user_message:
        return jsonify({"error": "No message"}), 400

    result = get_ai_response(user_message, tasks, chat_history)
    return jsonify(result)


@app.route("/health")
def health():
    return jsonify({"status": "running", "ai": bool(groq_client)})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
