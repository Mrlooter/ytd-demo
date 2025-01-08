from flask import Flask, request, render_template, jsonify, send_from_directory
from yt_dlp import YoutubeDL
import threading
import os
import re

app = Flask(__name__)

download_folder = "downloads"
os.makedirs(download_folder, exist_ok=True)

downloads = {}  # To track downloads with status and progress


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
        with YoutubeDL({"quiet": True}) as ydl:
            info = ydl.extract_info(url, download=False)

            # Extract the best thumbnail (if available)
            thumbnail = info.get("thumbnails", [{}])[-1].get("url", "")

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
    app.run(debug=True)
