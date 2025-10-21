from flask import Flask, render_template, request, redirect, flash
import pandas as pd
import os
import re
from datetime import datetime
import matplotlib.pyplot as plt

# ============================================================
# 🔧 APP CONFIGURATION
# ============================================================

app = Flask(__name__)
app.secret_key = "supersecretkey"  # for flash messages
UPLOAD_FOLDER = "data"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = {"csv"}

# ============================================================
# 📂 HELPER FUNCTIONS
# ============================================================

def allowed_file(filename):
    """Check if uploaded file has valid extension."""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def load_timetable():
    """Load and clean timetable CSV into a DataFrame."""
    csv_path = os.path.join(app.config["UPLOAD_FOLDER"], "timetable.csv")
    if not os.path.exists(csv_path):
        return pd.DataFrame()  # empty dataframe if file not found

    df = pd.read_csv(csv_path)
    df.columns = df.columns.str.strip().str.title()

    def clean_hall_name(name):
        if pd.isna(name):
            return None
        name = str(name).upper()
        name = re.sub(r"\s+", " ", name)
        name = name.replace("( ", "(").replace(" )", ")")
        name = name.replace("A B", "AB").replace("E B", "EB")
        return name.strip()

    if "Lecture Hall" in df.columns:
        df["Lecture Hall"] = df["Lecture Hall"].apply(clean_hall_name)

    if "Day" in df.columns:
        df["Day"] = df["Day"].astype(str).str.strip().str.title()

    if "Time" in df.columns:
        df["Time"] = df["Time"].astype(str).str.strip()

    return df


def get_free_halls(df, day, time):
    """Return lists of free and occupied halls for a given day/time."""
    if df.empty:
        return [], []

    day = day.strip().title()
    time = time.strip()

    occupied = df[(df["Day"] == day) & (df["Time"].str.contains(time, case=False, na=False))]
    occupied_halls = sorted(set(occupied["Lecture Hall"].dropna()))
    all_halls = sorted(set(df["Lecture Hall"].dropna()))
    free_halls = sorted(set(all_halls) - set(occupied_halls))
    return free_halls, occupied_halls


def detect_conflicts(df):
    """Detect halls double-booked for same day/time."""
    if df.empty:
        return []

    conflicts = (
        df.groupby(["Day", "Time", "Lecture Hall"])
        .size()
        .reset_index(name="Count")
    )
    conflicts = conflicts[conflicts["Count"] > 1]
    if conflicts.empty:
        return []

    details = pd.merge(df, conflicts[["Day", "Time", "Lecture Hall"]],
                       on=["Day", "Time", "Lecture Hall"], how="inner")

    grouped = details.groupby(["Day", "Time", "Lecture Hall"])["Course Code"].apply(list).reset_index()
    return grouped.to_dict(orient="records")


def generate_chart(df):
    """Generate and save a hall usage frequency chart."""
    if df.empty:
        return
    hall_counts = df["Lecture Hall"].value_counts()
    plt.figure(figsize=(10, 5))
    hall_counts.plot(kind="bar")
    plt.title("Lecture Hall Usage Frequency")
    plt.xlabel("Lecture Halls")
    plt.ylabel("Number of Lectures")
    plt.tight_layout()
    os.makedirs("static", exist_ok=True)
    plt.savefig("static/hall_usage.png")
    plt.close()


def get_last_updated():
    """Return last modified time of timetable file."""
    csv_path = os.path.join(app.config["UPLOAD_FOLDER"], "timetable.csv")
    if not os.path.exists(csv_path):
        return "No timetable file found"
    return datetime.fromtimestamp(os.path.getmtime(csv_path)).strftime("%d %B %Y, %I:%M %p")


# ============================================================
# 🌐 ROUTES
# ============================================================

@app.route("/", methods=["GET", "POST"])
def index():
    df = load_timetable()
    free_halls, occupied_halls, conflicts = [], [], []
    day = time = ""

    # Dropdown options
    day_options = sorted(df["Day"].dropna().unique()) if "Day" in df else []
    time_options = sorted(df["Time"].dropna().unique()) if "Time" in df else []
    last_updated = get_last_updated()

    # --- 📊 Stats Section ---
    total_courses = len(df)
    total_halls = df["Lecture Hall"].nunique() if "Lecture Hall" in df else 0
    most_used = df["Lecture Hall"].mode()[0] if total_halls > 0 else "N/A"
    least_used = (
        df["Lecture Hall"].value_counts().idxmin() if total_halls > 0 else "N/A"
    )

    if request.method == "POST":
        day = request.form.get("day", "")
        time = request.form.get("time", "")
        free_halls, occupied_halls = get_free_halls(df, day, time)
        conflicts = detect_conflicts(df)

    return render_template(
        "index.html",
        free_halls=free_halls,
        occupied_halls=occupied_halls,
        conflicts=conflicts,
        day=day,
        time=time,
        day_options=day_options,
        time_options=time_options,
        last_updated=last_updated,
        total_courses=total_courses,
        total_halls=total_halls,
        most_used=most_used,
        least_used=least_used
    )


@app.route("/upload", methods=["POST"])
def upload_file():
    """Handle timetable uploads and auto-refresh data/chart."""
    if "file" not in request.files:
        flash("No file part in request.")
        return redirect("/")

    file = request.files["file"]
    if file.filename == "":
        flash("No file selected.")
        return redirect("/")

    if file and allowed_file(file.filename):
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], "timetable.csv")
        file.save(filepath)
        flash("✅ Timetable uploaded successfully!")

        # Reload CSV and regenerate chart
        df = load_timetable()
        generate_chart(df)
        flash("📊 Hall usage chart updated.")
        return redirect("/")
    else:
        flash("❌ Invalid file type. Please upload a CSV file.")
        return redirect("/")


# ============================================================
# 🚀 RUN APP
# ============================================================

from flask import jsonify

@app.route("/chart-data")
def chart_data():
    df = load_timetable()
    if df.empty or "Lecture Hall" not in df.columns:
        return jsonify({"labels": [], "values": []})

    hall_counts = df["Lecture Hall"].value_counts()
    labels = hall_counts.index.tolist()
    values = hall_counts.values.tolist()
    return jsonify({"labels": labels, "values": values})


if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    app.run(debug=True)
