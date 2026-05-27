import os
import json
import datetime
from flask import Flask, request, jsonify, render_template

app = Flask(__name__)

# --- Configuration ---
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

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
@app.route("/")
def home():
    """Serve the main app."""
    return render_template("index.html")


@app.route("/api/chat", methods=["POST"])
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
