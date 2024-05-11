from bottle import Bottle
from threading import Thread

app = Bottle(__name__)

@app.route('/')
def home():
    return "I'm running"

def run():
    app.run(host='0.0.0.0', port=8180)

def keep_alive():
    t = Thread(target=run)
    t.start()
