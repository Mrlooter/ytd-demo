from flask import Flask, request, jsonify
from yt_dlp import YoutubeDL
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
import time
import pickle
import os

app = Flask(__name__)

download_folder = "downloads"
os.makedirs(download_folder, exist_ok=True)

downloads = {}  # To track downloads with status and progress

# Function to simulate login and fetch cookies using Selenium
def get_cookies_from_browser():
    # Set up the Selenium WebDriver (use the appropriate path for your browser driver)
    driver = webdriver.Chrome(executable_path='/path/to/chromedriver')

    # Open the login page (replace with the actual login URL)
    driver.get('https://example.com/login')

    # Simulate login (replace with your own login fields and credentials)
    username = driver.find_element(By.ID, 'username_field')
    password = driver.find_element(By.ID, 'password_field')

    # Replace with your credentials
    username.send_keys('your_username')
    password.send_keys('your_password')
    password.send_keys(Keys.RETURN)

    # Wait for the login to complete (adjust the time as needed)
    time.sleep(5)

    # Now, fetch the cookies
    cookies = driver.get_cookies()

    # Close the driver
    driver.quit()

    return cookies

# Function to save cookies to a file
def save_cookies(cookies, filename="cookies.pkl"):
    with open(filename, 'wb') as file:
        pickle.dump(cookies, file)

# Function to load cookies from a file
def load_cookies(filename="cookies.pkl"):
    if os.path.exists(filename):
        with open(filename, 'rb') as file:
            return pickle.load(file)
    return None

def download_video(url, quality, download_id):
    try:
        options = {
            "format": f"bestvideo[height<={quality}]+bestaudio/best[height<={quality}]",
            "outtmpl": os.path.join(download_folder, "%(title)s.%(ext)s"),
            "progress_hooks": [lambda d: handle_progress(d, download_id)],
        }
        with YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=False)
            downloads[download_id]["filename"] = ydl.prepare_filename(info)
            ydl.download([url])
        downloads[download_id]["status"] = "completed"
    except Exception as e:
        downloads[download_id]["status"] = "error"
        downloads[download_id]["error"] = str(e)


def handle_progress(d, download_id):
    if d["status"] == "downloading":
        # Remove ANSI escape sequences from the progress string
        percent_str = d.get("_percent_str", "0%")
        percent_str = re.sub(
            r"\x1b\[[0-9;]*m", "", percent_str
        )  # Remove ANSI escape codes
        percent = percent_str.strip("%")
        try:
            downloads[download_id]["progress"] = float(percent)
        except ValueError:
            downloads[download_id]["progress"] = 0.0  # Default to 0% if parsing fails
    elif d["status"] == "finished":
        downloads[download_id]["progress"] = 100


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/fetch", methods=["POST"])
def fetch_video():
    url = request.json.get("url")
    try:
        # Check if cookies already exist
        cookies = load_cookies()

        if not cookies:
            # If no cookies, simulate login and save cookies
            cookies = get_cookies_from_browser()
            save_cookies(cookies)
            
        # Define yt-dlp options
        ydl_opts = {
            'cookies_from_browser': True,  # Extract cookies directly from the browser
            'quiet': True,                 # Suppress logs
            'nocheckcertificate': True,    # Skip SSL certificate verification (optional)
        }
        
        # Fetch video info
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

            # Extract the best thumbnail (if available)
            thumbnail = info.get("thumbnails", [{}])[-1].get("url", "")

            # Filter formats for those with a minimum height of 480
            formats = [
                {
                    "format_id": f["format_id"],
                    "height": f.get("height", "N/A"),
                    "format_note": f.get("format_note", ""),
                    "filesize": f.get("filesize") or f.get("filesize_approx", None),
                }
                for f in info["formats"]
                if f.get("height") and f["height"] >= 480
            ]

            # Sort formats by height (descending)
            formats.sort(key=lambda x: x["height"], reverse=True)

            # Return the response
            return jsonify(
                {
                    "title": info["title"],
                    "id": info["id"],
                    "thumbnail": thumbnail,
                    "formats": formats,
                }
            )
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/download", methods=["POST"])
def download_video_request():
    url = request.json.get("url")
    quality = request.json.get("quality")
    download_id = request.json.get("id")

    downloads[download_id] = {"status": "downloading", "progress": 0}
    threading.Thread(target=download_video, args=(url, quality, download_id)).start()
    return jsonify({"download_id": download_id})


@app.route("/progress/<download_id>")
def get_progress(download_id):
    return jsonify(downloads.get(download_id, {"status": "unknown"}))


@app.route("/file/<download_id>")
def serve_file(download_id):
    if download_id not in downloads or downloads[download_id]["status"] != "completed":
        return jsonify({"error": "File not ready for download."}), 400

    filename = downloads[download_id]["filename"]
    return send_from_directory(
        download_folder, os.path.basename(filename), as_attachment=True
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
