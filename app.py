from flask import Response, Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.utils import secure_filename
import sqlite3, os

app = Flask(__name__)
app.secret_key = os.environ.get("MOVIE4BOX_SECRET") or "movie4box-local-secret-change-me"
DB = "moviebox.db"
UPLOAD_FOLDER = "static/uploads"
ALLOWED_EXTENSIONS = {"mp4", "webm", "mov", "m4v"}
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024 * 1024
ADMIN_USER = os.environ.get("MOVIE4BOX_ADMIN_USER")
ADMIN_PASS = os.environ.get("MOVIE4BOX_ADMIN_PASS")

def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    con = db()
    con.execute("""CREATE TABLE IF NOT EXISTS movies(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        description TEXT,
        poster TEXT,
        video_url TEXT,
        language TEXT,
        year TEXT,
        genre TEXT,
        quality TEXT
    )""")
    con.execute("""CREATE TABLE IF NOT EXISTS movie_qualities(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        movie_id INTEGER NOT NULL,
        quality TEXT NOT NULL,
        video_url TEXT NOT NULL,
        UNIQUE(movie_id, quality)
    )""")
    con.commit()
    con.close()

@app.route("/")
def home():
    q = request.args.get("q","").strip()
    category = request.args.get("category","").strip()
    con = db()
    if category:
        movies = con.execute("SELECT * FROM movies WHERE category=? ORDER BY id DESC", (category,)).fetchall()
    elif q:
        movies = con.execute("SELECT * FROM movies WHERE title LIKE ? OR genre LIKE ? OR category LIKE ? ORDER BY id DESC",
                             (f"%{q}%", f"%{q}%", f"%{q}%")).fetchall()
    else:
        movies = con.execute("SELECT * FROM movies ORDER BY id DESC").fetchall()
    con.close()
    return render_template("index.html", movies=movies, q=q)

@app.route("/movie/<int:movie_id>")
def movie(movie_id):
    con = db()
    m = con.execute("SELECT * FROM movies WHERE id=?", (movie_id,)).fetchone()
    qualities = con.execute(
        "SELECT * FROM movie_qualities WHERE movie_id=? ORDER BY CASE quality WHEN '480p' THEN 1 WHEN '720p' THEN 2 WHEN '1080p' THEN 3 WHEN '4K' THEN 4 ELSE 5 END",
        (movie_id,)
    ).fetchall()
    if not m:
        con.close()
        return "Movie not found", 404

    related = con.execute(
        """SELECT * FROM movies
           WHERE id != ?
           AND category = ?
           ORDER BY id DESC
           LIMIT 4""",
        (movie_id, m["category"])
    ).fetchall()

    con.close()
    return render_template(
        "movie.html",
        movie=m,
        qualities=qualities,
        related=related
    )

@app.route("/admin", methods=["GET","POST"])
def admin():
    if request.method == "POST":
        if request.form.get("username")==ADMIN_USER and request.form.get("password")==ADMIN_PASS:
            session["admin"] = True
            return redirect(url_for("admin"))
        flash("Invalid login")
    if not session.get("admin"):
        return render_template("login.html")
    con = db()
    movies = con.execute("SELECT * FROM movies ORDER BY id DESC").fetchall()
    con.close()
    return render_template("admin.html", movies=movies)

@app.post("/admin/add")
def add_movie():
    if not session.get("admin"):
        return redirect(url_for("admin"))

    poster_file = request.files.get("poster_file")
    poster_url = request.form.get("poster", "").strip()

    if poster_file and poster_file.filename:
        ext = poster_file.filename.rsplit(".", 1)[-1].lower()
        if ext in {"jpg", "jpeg", "png", "webp"}:
            poster_name = secure_filename(poster_file.filename)
            poster_name = f"poster_{poster_name}"
            poster_file.save(os.path.join(UPLOAD_FOLDER, poster_name))
            poster_url = url_for("static", filename=f"uploads/{poster_name}")

    data = {
        k: request.form.get(k, "").strip()
        for k in ["title","description","video_url","language","year","genre","quality","category",
                  "duration","starcast","file_size"]
    }
    data["poster"] = poster_url

    if not data["title"]:
        flash("Title is required")
        return redirect(url_for("admin"))

    con = db()
    con.execute(
        """INSERT INTO movies(title,description,poster,video_url,language,year,genre,quality,category,duration,starcast,file_size)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            data["title"], data["description"], data["poster"],
            data["video_url"], data["language"], data["year"],
            data["genre"], data["quality"], data["category"],
            data["duration"], data["starcast"], data["file_size"]
        )
    )
    con.commit()
    con.close()

    return redirect(url_for("admin"))

@app.post("/admin/upload/<int:movie_id>")
def upload_video(movie_id):
    if not session.get("admin"):
        return redirect(url_for("admin"))

    file = request.files.get("video")
    if not file or not file.filename:
        flash("Video file select karo")
        return redirect(url_for("admin"))

    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        flash("Sirf MP4, WebM, MOV ya M4V video allowed hai")
        return redirect(url_for("admin"))

    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    filename = secure_filename(file.filename)
    filename = f"{movie_id}_{filename}"
    path = os.path.join(UPLOAD_FOLDER, filename)
    file.save(path)

    video_url = url_for("static", filename=f"uploads/{filename}")
    con = db()
    con.execute("UPDATE movies SET video_url=? WHERE id=?", (video_url, movie_id))
    con.commit()
    con.close()

    flash("Video upload ho gaya")
    return redirect(url_for("admin"))

@app.route("/admin/edit/<int:movie_id>", methods=["GET", "POST"])
def edit_movie(movie_id):
    if not session.get("admin"):
        return redirect(url_for("admin"))

    con = db()

    if request.method == "POST":
        data = {
            k: request.form.get(k, "").strip()
            for k in ["title", "description", "poster", "video_url",
                      "language", "year", "genre", "quality", "category",
                      "duration", "starcast", "file_size"]
        }

        if not data["title"]:
            flash("Title is required")
            con.close()
            return redirect(url_for("edit_movie", movie_id=movie_id))

        con.execute("""
            UPDATE movies
            SET title=?, description=?, poster=?, video_url=?,
                language=?, year=?, genre=?, quality=?, category=?,
                duration=?, starcast=?, file_size=?
            WHERE id=?
        """, (
            data["title"], data["description"], data["poster"],
            data["video_url"], data["language"], data["year"],
            data["genre"], data["quality"], data["category"],
            data["duration"], data["starcast"], data["file_size"],
            movie_id
        ))

        con.commit()
        con.close()

        flash("Movie updated successfully")
        return redirect(url_for("admin"))

    movie = con.execute(
        "SELECT * FROM movies WHERE id=?",
        (movie_id,)
    ).fetchone()

    con.close()

    if not movie:
        return "Movie not found", 404

    return render_template("edit_movie.html", movie=movie)


@app.post("/admin/delete/<int:movie_id>")
def delete_movie(movie_id):
    if not session.get("admin"): return redirect(url_for("admin"))
    con=db(); con.execute("DELETE FROM movies WHERE id=?", (movie_id,)); con.commit(); con.close()
    return redirect(url_for("admin"))


@app.post("/admin/upload-quality/<int:movie_id>")
def upload_quality_video(movie_id):
    if not session.get("admin"):
        return redirect(url_for("admin"))

    quality = request.form.get("quality", "").strip()
    video = request.files.get("video")

    allowed_quality = {"480p", "720p", "1080p", "4K"}

    if quality not in allowed_quality or not video or not video.filename:
        flash("Please select a valid quality and video.")
        return redirect(url_for("admin"))

    filename = secure_filename(video.filename)
    filename = f"{movie_id}_{quality}_{filename}"
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    video.save(filepath)

    video_url = url_for("static", filename=f"uploads/{filename}")

    con = db()
    con.execute("""
        INSERT INTO movie_qualities(movie_id, quality, video_url)
        VALUES(?,?,?)
        ON CONFLICT(movie_id, quality)
        DO UPDATE SET video_url=excluded.video_url
    """, (movie_id, quality, video_url))
    con.commit()
    con.close()

    return redirect(url_for("admin"))

@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


@app.route("/about")
def about():
    return render_template("about.html")

@app.route("/contact")
def contact():
    return render_template("contact.html")

@app.route("/privacy")
def privacy():
    return render_template("privacy.html")

@app.route("/terms")
def terms():
    return render_template("terms.html")



@app.route("/robots.txt")
def robots():
    return app.send_static_file("robots.txt")


@app.route("/sitemap.xml")
def sitemap():
    pages = [
        url_for("home", _external=True),
        url_for("about", _external=True),
        url_for("contact", _external=True),
        url_for("privacy", _external=True),
        url_for("terms", _external=True),
    ]

    con = db()
    movies = con.execute("SELECT id FROM movies ORDER BY id DESC").fetchall()
    con.close()

    pages += [
        url_for("movie", movie_id=m["id"], _external=True)
        for m in movies
    ]

    xml = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']

    for page in pages:
        xml.append(f"<url><loc>{page}</loc></url>")

    xml.append("</urlset>")

    return Response("\n".join(xml), mimetype="application/xml")


@app.errorhandler(404)
def page_not_found(error):
    return render_template("404.html"), 404



init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
