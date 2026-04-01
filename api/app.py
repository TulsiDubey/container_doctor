from flask import Flask

app = Flask(__name__)

@app.route("/")
def home():
    return {"message": "API is running"}

@app.route("/crash")
def crash():
    raise Exception("Manual crash!")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
