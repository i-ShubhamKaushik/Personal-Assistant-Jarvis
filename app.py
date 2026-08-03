from flask import Flask, render_template, request, jsonify
import threading

# Import your existing Jarvis functions
# Rename main(1).py to main.py before using this.
import main

app = Flask(__name__)

# ----------------------------
# Start Jarvis backend once
# ----------------------------
jarvis_started = False


def start_jarvis():
    """
    Starts the existing Jarvis voice assistant.
    Your main.py should contain a function called start().
    """
    main.start()


@app.before_request
def launch_backend():
    global jarvis_started

    if not jarvis_started:
        threading.Thread(target=start_jarvis, daemon=True).start()
        jarvis_started = True


# ----------------------------
# Routes
# ----------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/command", methods=["POST"])
def command():
    data = request.get_json()

    command = data.get("command", "").strip()

    if not command:
        return jsonify({
            "success": False,
            "message": "No command received."
        })

    try:
        # Uses your existing command processor
        main.processCommand(command)

        return jsonify({
            "success": True,
            "message": "Command executed."
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        })


@app.route("/health")
def health():
    return jsonify({
        "status": "running"
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)