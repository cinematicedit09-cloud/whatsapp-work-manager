import os
import json
import datetime
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from groq import Groq

app = Flask(__name__)

# --- Configuration ---
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
groq_client = Groq(api_key=GROQ_API_KEY)

# --- Simple JSON File Database ---
DB_FILE = "tasks.json"


def load_tasks():
    """Load tasks from JSON file."""
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f:
            return json.load(f)
    return []


def save_tasks(tasks):
    """Save tasks to JSON file."""
    with open(DB_FILE, "w") as f:
        json.dump(tasks, f, indent=2)


def add_task(task_text, priority="medium"):
    """Add a new task."""
    tasks = load_tasks()
    task = {
        "id": len(tasks) + 1,
        "text": task_text,
        "priority": priority,
        "done": False,
        "created": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    tasks.append(task)
    save_tasks(tasks)
    return task


def complete_task(task_identifier):
    """Mark a task as done by ID or text match."""
    tasks = load_tasks()
    for task in tasks:
        if str(task["id"]) == str(task_identifier) or task_identifier.lower() in task["text"].lower():
            task["done"] = True
            save_tasks(tasks)
            return task
    return None


def delete_task(task_identifier):
    """Delete a task by ID or text match."""
    tasks = load_tasks()
    for i, task in enumerate(tasks):
        if str(task["id"]) == str(task_identifier) or task_identifier.lower() in task["text"].lower():
            removed = tasks.pop(i)
            save_tasks(tasks)
            return removed
    return None


def get_pending_tasks():
    """Get all pending tasks."""
    tasks = load_tasks()
    return [t for t in tasks if not t["done"]]


def get_all_tasks():
    """Get all tasks."""
    return load_tasks()


def get_summary():
    """Get a summary of tasks."""
    tasks = load_tasks()
    total = len(tasks)
    done = len([t for t in tasks if t["done"]])
    pending = total - done
    return {"total": total, "done": done, "pending": pending}


# --- AI Message Understanding ---
def understand_message(user_message):
    """Use Groq AI to understand what the user wants."""
    system_prompt = """You are a WhatsApp task manager assistant. 
    Understand the user's message and respond with a JSON action.
    
    The user may write in English, Hindi, Hinglish, or Punjabi.
    
    Possible actions:
    1. {"action": "add", "task": "task description", "priority": "high/medium/low"}
    2. {"action": "done", "identifier": "task id or text"}
    3. {"action": "delete", "identifier": "task id or text"}
    4. {"action": "list", "filter": "all/pending/done"}
    5. {"action": "summary"}
    6. {"action": "help"}
    7. {"action": "chat", "response": "your friendly response"}
    
    Examples:
    - "add meeting at 5pm" -> {"action": "add", "task": "meeting at 5pm", "priority": "medium"}
    - "urgent: finish report" -> {"action": "add", "task": "finish report", "priority": "high"}
    - "done meeting" -> {"action": "done", "identifier": "meeting"}
    - "delete task 3" -> {"action": "delete", "identifier": "3"}
    - "show tasks" / "meri tasks dikha" -> {"action": "list", "filter": "pending"}
    - "all tasks" -> {"action": "list", "filter": "all"}
    - "summary" / "status" -> {"action": "summary"}
    - "help" -> {"action": "help"}
    - "hello" / "hi" -> {"action": "chat", "response": "Hey! I'm your work manager. Send me tasks or say 'help' to see what I can do!"}
    
    ONLY respond with valid JSON. Nothing else."""

    try:
        response = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=0.1,
            max_tokens=200,
        )
        result = response.choices[0].message.content.strip()
        # Clean up response if needed
        if result.startswith("```"):
            result = result.split("\n", 1)[1].rsplit("```", 1)[0]
        return json.loads(result)
    except Exception as e:
        print(f"AI Error: {e}")
        return {"action": "chat", "response": "Sorry, I didn't understand that. Type 'help' for options."}


# --- Format Responses ---
def format_task_list(tasks, title="Your Tasks"):
    """Format tasks as a nice WhatsApp message."""
    if not tasks:
        return "No tasks found! You're all clear. Add one by sending a task."

    msg = f"*{title}*\n\n"
    for task in tasks:
        status = "done" if task["done"] else "pending"
        priority_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(task["priority"], "🟡")
        check = "✅" if task["done"] else "⬜"
        msg += f"{check} *#{task['id']}* {priority_emoji} {task['text']}\n"
        msg += f"    📅 {task['created']} | Status: {status}\n\n"
    return msg


def get_help_message():
    """Return help message."""
    return """*🤖 WhatsApp Work Manager - Help*

Here's what I can do:

*📝 Add Tasks:*
• "Add: buy groceries"
• "urgent: finish report by tomorrow"
• "meeting at 5pm add kar"

*✅ Complete Tasks:*
• "Done: meeting"
• "Complete task 2"
• "task 3 ho gaya"

*🗑️ Delete Tasks:*
• "Delete task 1"
• "Remove meeting"

*📋 View Tasks:*
• "Show my tasks"
• "List all"
• "Pending tasks dikha"

*📊 Summary:*
• "Summary"
• "Status"
• "Kinna kaam baaki hai?"

*💡 Tips:*
• I understand English, Hindi, Hinglish & Punjabi!
• Use "urgent" or "important" for high priority
• Refer to tasks by number or name

Just send me a message naturally! 💬"""


# --- Main WhatsApp Webhook ---
@app.route("/webhook", methods=["POST"])
def webhook():
    """Handle incoming WhatsApp messages from Twilio."""
    incoming_msg = request.values.get("Body", "").strip()
    sender = request.values.get("From", "")

    print(f"Message from {sender}: {incoming_msg}")

    # Understand the message using AI
    action_data = understand_message(incoming_msg)
    action = action_data.get("action", "chat")

    # Process the action
    if action == "add":
        task_text = action_data.get("task", incoming_msg)
        priority = action_data.get("priority", "medium")
        task = add_task(task_text, priority)
        priority_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(priority, "🟡")
        reply = f"✅ Task added!\n\n{priority_emoji} *#{task['id']}* {task['text']}\nPriority: {priority}\n\nSend 'show tasks' to see all."

    elif action == "done":
        identifier = action_data.get("identifier", "")
        task = complete_task(identifier)
        if task:
            reply = f"🎉 Great job! Task completed:\n\n✅ *#{task['id']}* {task['text']}\n\nKeep it up! 💪"
        else:
            reply = "❌ Task not found. Send 'show tasks' to see your task list."

    elif action == "delete":
        identifier = action_data.get("identifier", "")
        task = delete_task(identifier)
        if task:
            reply = f"🗑️ Task deleted:\n\n*#{task['id']}* {task['text']}"
        else:
            reply = "❌ Task not found. Send 'show tasks' to see your task list."

    elif action == "list":
        filter_type = action_data.get("filter", "pending")
        if filter_type == "all":
            tasks = get_all_tasks()
            reply = format_task_list(tasks, "All Tasks")
        elif filter_type == "done":
            tasks = [t for t in get_all_tasks() if t["done"]]
            reply = format_task_list(tasks, "Completed Tasks")
        else:
            tasks = get_pending_tasks()
            reply = format_task_list(tasks, "Pending Tasks")

    elif action == "summary":
        s = get_summary()
        reply = f"""*📊 Work Summary*

📋 Total Tasks: {s['total']}
✅ Completed: {s['done']}
⏳ Pending: {s['pending']}

{'🎉 All done! Great work!' if s['pending'] == 0 and s['total'] > 0 else '💪 Keep going, you got this!' if s['pending'] > 0 else '📝 No tasks yet. Send me a task to get started!'}"""

    elif action == "help":
        reply = get_help_message()

    else:
        reply = action_data.get("response", "I'm your work manager! Send 'help' to see what I can do.")

    # Send response via Twilio
    resp = MessagingResponse()
    resp.message(reply)
    return str(resp)


@app.route("/", methods=["GET"])
def home():
    """Health check endpoint."""
    return "WhatsApp Work Manager Bot is running! 🤖"


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
