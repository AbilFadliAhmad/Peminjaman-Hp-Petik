from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
send_from_directory
)
import json
import os
from werkzeug.security import generate_password_hash
from functools import wraps
from werkzeug.security import check_password_hash
from config import Config
from database.mysql import initialize_database, get_connection
from werkzeug.utils import secure_filename
import uuid
from datetime import datetime, timedelta
from markupsafe import Markup



app = Flask(__name__)

app.config.from_object(Config)

# ==========================================================
# Flask Configuration
# ==========================================================

app = Flask(__name__)
app.config.from_object(Config)

# ==========================================================
# Initialize Database
# ==========================================================

initialize_database()

# ==========================================================
# Application Constants
# ==========================================================

STATUS_PENDING = "PENDING"
STATUS_APPROVED = "APPROVED"
STATUS_REJECTED = "REJECTED"
STATUS_FINISHED = "FINISHED"
STATUS_LOADING = "LOADING"
STATUS_CANCELLED = "CANCELLED"

ROLE_SANTRI = "santri"
ROLE_PENGASUHAN = "pengasuhan"
ROLE_KOORDINATOR = "koordinator"

UPLOAD_BORROW_DIR = os.path.join(
    "static",
    "uploads",
    "borrow"
)

# ==========================================================
# Sidebar Menu
# ==========================================================

SIDEBAR_MENUS = {
    ROLE_SANTRI: [
        {
            "title": "Izin Hp",
            "endpoint": "santri_izin_hp",
            "icon": "📱"
        },
        {
            "title": "Izin Keluar",
            "endpoint": "santri_izin_keluar",
            "icon": "🚪"
        }
    ],

    ROLE_PENGASUHAN: [
        {
            "title": "Dashboard",
            "endpoint": "pengasuhan_dashboard",
            "icon": "🏠"
        },
        {
            "title": "Pengajuan Hp",
            "endpoint": "pengasuhan_requests",
            "icon": "📋"
        },
        {
            "title": "Pengajuan Keluar",
            "endpoint": "pengasuhan_permits",
            "icon": "🚪"
        },
        {
            "title": "Santri",
            "endpoint": "pengasuhan_users",
            "icon": "👨‍🎓"
        }
    ],

    ROLE_KOORDINATOR: [

        {
            "title": "Dashboard",
            "endpoint": "koordinator_dashboard",
            "icon": "🏠"
        },

        {
            "title": "Peminjaman Aktif",
            "endpoint": "koordinator_requests",
            "icon": "📱"
        }

    ]
}

# ==========================================================
# User Helper
# ==========================================================

def get_all_santri():

    return query(
        """
        SELECT *
        FROM users
        WHERE role=%s
        ORDER BY name ASC
        """,
        (ROLE_SANTRI,),
        fetchall=True
    )

def save_borrow_files(files):

    """
    Menyimpan seluruh file pendukung pengajuan.

    Return:
    [
        {
            "original_name": "...",
            "name": "...",
            "path": "...",
            "size": 12345,
            "mime": "..."
        }
    ]
    """

    os.makedirs(
        UPLOAD_BORROW_DIR,
        exist_ok=True
    )

    uploaded = []

    for file in files:

        if not file:
            continue

        if file.filename == "":
            continue

        original_name = file.filename

        filename = secure_filename(original_name)

        extension = os.path.splitext(filename)[1].lower()

        unique_name = f"{uuid.uuid4().hex}{extension}"

        save_path = os.path.join(
            UPLOAD_BORROW_DIR,
            unique_name
        )

        file.save(save_path)

        uploaded.append({
            "original_name": original_name,
            "name": unique_name,
            "path": save_path.replace("\\", "/"),
            "size": os.path.getsize(save_path),
            "mime": file.mimetype
        })

    return uploaded

# ==========================================================
# Borrow Request Helper
# ==========================================================

def has_active_borrow(user_id):

    data = query(
        """
        SELECT COUNT(*) total
        FROM borrow_requests
        WHERE user_id=%s
        AND status IN (%s,%s)
        """,
        (
            user_id,
            STATUS_PENDING,
            STATUS_APPROVED
        ),
        one=True
    )

    return data["total"] > 0

def latest_borrow(user_id):

    return query(
        """
        SELECT *
        FROM borrow_requests
        WHERE user_id=%s
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (user_id,),
        one=True
    )

def latest_history(user_id, limit=5):

    return query(
        """
        SELECT
            id,
            reason,
            borrow_date,
            start_time,
            end_time,
            status,
            created_at
        FROM borrow_requests
        WHERE user_id=%s
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (user_id, limit)
    )

def get_history(user_id):

    return query(
        """
        SELECT
            id,
            reason,
            borrow_date,
            start_time,
            end_time,
            status,
            pengasuhan_note,
            created_at
        FROM borrow_requests
        WHERE user_id=%s
        ORDER BY borrow_date DESC,
                 start_time DESC
        """,
        (user_id,)
    )

def get_pending_requests():

    return query(
        """
        SELECT
            br.id,
            u.name,
            br.reason,
            br.borrow_date,
            br.start_time,
            br.end_time,
            br.status,
            br.created_at
        FROM borrow_requests br
        JOIN users u
            ON u.id = br.user_id
        WHERE br.status=%s
        ORDER BY br.created_at ASC
        """,
        (STATUS_PENDING,)
    )

def approve_borrow(request_id, approved_by, pengasuhan_note):

    execute(
        """
        UPDATE borrow_requests
        SET
            status=%s,
            approved_by=%s,
            approved_at=NOW(),
            pengasuhan_note = %s
        WHERE id=%s
        """,
        (
            STATUS_APPROVED,
            approved_by,
            pengasuhan_note,
            request_id
        )
    )

def reject_borrow(request_id, rejected_by, reason):

    execute(
        """
        UPDATE borrow_requests
        SET
            status=%s,
            pengasuhan_note=%s,
            rejected_by=%s,
            rejected_at=NOW()
        WHERE id=%s
        """,
        (
            STATUS_REJECTED,
            reason,
            rejected_by,
            request_id
        )
    )

def get_request_by_id(request_id):

    data = query(
        """
        SELECT
            br.*,
            u.name,
            approver.name AS approved_name,
            rejector.name AS rejected_name,
            finisher.name AS finished_name
        FROM borrow_requests br

        JOIN users u
            ON u.id = br.user_id

        LEFT JOIN users approver
            ON approver.id = br.approved_by

        LEFT JOIN users rejector
            ON rejector.id = br.rejected_by

        LEFT JOIN users finisher
            ON finisher.id = br.finished_by

        WHERE br.id=%s
        """,
        (request_id,),
        one=True
    )

    if not data:
        return None

    raw_files = data.get("files")

    if raw_files:
        try:
            raw_files = json.loads(raw_files)
        except Exception:
            raw_files = []

    else:
        raw_files = []

    data["files"] = raw_files
    return data

def get_all_requests(status=None):

    sql = """
        SELECT

            br.id,
            u.name,
            br.reason,
            br.borrow_date,
            br.start_time,
            br.end_time,
            br.status,
            br.created_at,
            br.approved_at,
            br.rejected_at

        FROM borrow_requests br
        JOIN users u
            ON u.id = br.user_id
    """

    params = []

    if status:

        sql += " WHERE br.status=%s "
        params.append(status)

    sql += """

        ORDER BY

            br.created_at DESC

    """

    return query(
        sql,
        tuple(params)
    )

def latest_requests(limit=5):

    return query(
        """
        SELECT

            br.id,

            u.name,

            br.status,

            br.borrow_date,

            br.created_at

        FROM borrow_requests br

        JOIN users u
            ON u.id = br.user_id

        ORDER BY br.created_at DESC

        LIMIT %s
        """,
        (limit,)
    )

# ==========================================================
# Statistic Helper
# ==========================================================

def total_santri():

    result = query(
        """
        SELECT COUNT(*) total
        FROM users
        WHERE role=%s
        """,
        (ROLE_SANTRI,),
        one=True
    )

    return result["total"]

def total_pending():

    result = query(
        """
        SELECT COUNT(*) total
        FROM borrow_requests
        WHERE status=%s
        """,
        (STATUS_PENDING,),
        one=True
    )

    return result["total"]

def total_active():

    result = query(
        """
        SELECT COUNT(*) total
        FROM borrow_requests
        WHERE status=%s
        """,
        (STATUS_APPROVED,),
        one=True
    )

    return result["total"]

def total_finished_today():

    result = query(
        """
        SELECT COUNT(*) total
        FROM borrow_requests
        WHERE DATE(finished_at)=CURDATE()
        """
        ,
        one=True
    )

    return result["total"]

def pengasuhan_statistics():

    stats = {}

    stats["today"] = query(
        """
        SELECT COUNT(*) total
        FROM borrow_requests
        WHERE borrow_date = CURDATE()
        """,
        one=True
    )["total"]

    stats["today_summary"] = query("""
        SELECT
            SUM(status='PENDING')   AS pending,
            SUM(status='APPROVED')  AS approved,
            SUM(status='REJECTED')  AS rejected,
            SUM(status='FINISHED')  AS finished
        FROM borrow_requests
        WHERE borrow_date = CURDATE()
        """, one=True)

    stats["late_chart"] = query("""
        WITH RECURSIVE dates AS (
            SELECT CURDATE() - INTERVAL 6 DAY AS date

            UNION ALL

            SELECT date + INTERVAL 1 DAY
            FROM dates
            WHERE date < CURDATE()
        )

        SELECT
            dates.date,
            COALESCE(COUNT(l.id), 0) AS total
        FROM dates
        LEFT JOIN late_recaps l
            ON l.date = dates.date
        GROUP BY dates.date
        ORDER BY dates.date
        """)

    return stats

# ==========================================================
# Koordinator Helper
# ==========================================================

def koordinator_statistics():

    stats = {}

    stats["active"] = query(
        """
        SELECT COUNT(*) total
        FROM borrow_requests
        WHERE status=%s
        """,
        (STATUS_APPROVED,),
        one=True
    )["total"]

    stats["finished"] = query(
        """
        SELECT COUNT(*) total
        FROM borrow_requests
        WHERE status=%s
        """,
        (STATUS_FINISHED,),
        one=True
    )["total"]

    stats["today"] = query(
        """
        SELECT COUNT(*) total
        FROM borrow_requests
        WHERE status=%s
        AND DATE(created_at)=CURDATE()
        """,
        (STATUS_APPROVED,),
        one=True
    )["total"]

    return stats

def latest_active(limit=5):

    return query(
        """
        SELECT

            br.id,

            u.name,

            br.borrow_date,

            br.status,

            br.approved_at

        FROM borrow_requests br

        JOIN users u

            ON u.id=br.user_id

        WHERE br.status=%s

        ORDER BY br.approved_at DESC

        LIMIT %s
        """,
        (
            STATUS_APPROVED,
            limit
        )
    )

def get_koordinator_requests(status=None):

    sql = """
        SELECT

            br.id,

            u.name,

            br.reason,

            br.borrow_date,

            br.start_time,

            br.end_time,

            br.status,

            br.approved_at,

            br.created_at

        FROM borrow_requests br

        JOIN users u
            ON u.id = br.user_id

        WHERE br.status IN (%s,%s)
    """

    params = [
        STATUS_APPROVED,
        STATUS_FINISHED
    ]

    if status:

        sql += " AND br.status=%s "
        params.append(status)

    sql += """

        ORDER BY

            br.borrow_date DESC,

            br.start_time DESC

    """

    return query(
        sql,
        tuple(params)
    )

# ==========================================================
# Pengasuhan Helper
# ==========================================================

def get_all_users():

    return query("""
        SELECT
            id,
            name,
            username,
            role,
            created_at
        FROM users
        ORDER BY created_at DESC
    """)

def get_user_by_id(user_id):

    return query("""
        SELECT
            id,
            name,
            username,
            role
        FROM users
        WHERE id = %s
    """, (
        user_id,
    ), one=True)

def create_user(
    name,
    username,
    password,
    role="santri"
):

    return execute("""
        INSERT INTO users
        (
            name,
            username,
            password,
            role
        )
        VALUES
        (
            %s,
            %s,
            %s,
            %s
        )
    """, (
        name,
        username,
        generate_password_hash(password),
        role
    ))

def update_user(
    user_id,
    name,
    username,
    role
):

    execute("""
        UPDATE users
        SET
            name = %s,
            username = %s,
            role = %s
        WHERE id = %s
    """, (
        name,
        username,
        role,
        user_id
    ))

def update_password(
    user_id,
    password
):

    execute("""
        UPDATE users
        SET
            password = %s
        WHERE id = %s
    """, (
        generate_password_hash(password),
        user_id
    ))

def get_user_by_username(
    username,
    exclude_id=None
):

    sql = """
        SELECT * FROM users
        WHERE username = %s
    """

    params = [username]

    if exclude_id is not None:

        sql += " AND id != %s"

        params.append(exclude_id)

    return query(
        sql,
        tuple(params),
        one=True
    )

# ==========================================================
# Helper Function
# ==========================================================

def query(sql, params=None, one=False):
    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(sql, params or ())

            if one:
                return cursor.fetchone()

            return cursor.fetchall()

    finally:
        connection.close()

def execute(sql, params=None):
    connection = get_connection()

    try:

        with connection.cursor() as cursor:

            cursor.execute(sql, params or ())

            connection.commit()

            return cursor.lastrowid

    finally:

        connection.close()

@app.template_filter("format_late")
def format_late(minutes):
    minutes = int(minutes)

    months = minutes // (60 * 24 * 30)
    minutes %= 60 * 24 * 30

    weeks = minutes // (60 * 24 * 7)
    minutes %= 60 * 24 * 7

    days = minutes // (60 * 24)
    minutes %= 60 * 24

    hours = minutes // 60
    minutes %= 60

    parts = []

    if months:
        parts.append(f"{months} Bulan")

    if weeks:
        parts.append(f"{weeks} Minggu")

    if days:
        parts.append(f"{days} Hari")

    if hours:
        parts.append(f"{hours} Jam")

    if minutes:
        parts.append(f"{minutes} Menit")

    return " ".join(parts) if parts else "Tidak Terlambat"


# ==========================================================
# Session Helper
# ==========================================================

def current_user():

    return {
        "id": session.get("user_id"),
        "name": session.get("name"),
        "username": session.get("username"),
        "role": session.get("role")
    }

# ==========================================================
# Global Template Variable
# ==========================================================

@app.context_processor
def inject_global():

    role = session.get("role")

    return {

        "current_user": current_user(),
        "menus": SIDEBAR_MENUS.get(role, []),
        "current_endpoint": request.endpoint

    }

# ==========================================================
# Jinja Filters
# ==========================================================

@app.template_filter("status_badge")
def status_badge(status):

    badges = {

        STATUS_PENDING:
            '<span class="px-3 py-1 rounded-full bg-yellow-100 text-yellow-700 text-xs font-medium">Pending</span>',

        STATUS_APPROVED:
            '<span class="px-3 py-1 rounded-full bg-blue-100 text-blue-700 text-xs font-medium">Approved</span>',

        STATUS_REJECTED:
            '<span class="px-3 py-1 rounded-full bg-red-100 text-red-700 text-xs font-medium">Rejected</span>',

        STATUS_FINISHED:
            '<span class="px-3 py-1 rounded-full bg-green-100 text-green-700 text-xs font-medium">Finished</span>'

    }

    return Markup(
        badges.get(
            status,
            f'<span class="px-3 py-1 rounded-full bg-gray-100 text-gray-700 text-xs">{status}</span>'
        )
    )


@app.template_filter("format_date")
def format_date(value):

    if not value:
        return "-"

    if isinstance(value, datetime):
        return value.strftime("%d-%m-%Y")

    return str(value)


@app.template_filter("format_time")
def format_time(value):

    if not value:
        return "-"

    if hasattr(value, "strftime"):
        return value.strftime("%H:%M")

    text = str(value)

    return text[:5]

@app.template_filter("status_class")
def status_class(status):

    return {
        STATUS_PENDING: "text-yellow-600",
        STATUS_APPROVED: "text-blue-600",
        STATUS_REJECTED: "text-red-600",
        STATUS_FINISHED: "text-green-600",
    }.get(status, "text-gray-600")

# ==========================================================
# Login Required
# ==========================================================

def login_required(func):

    @wraps(func)

    def wrapper(*args, **kwargs):

        if "user_id" not in session:

            flash(
                "Silakan login terlebih dahulu.",
                "warning"
            )

            return dashboard_redirect()

        return func(*args, **kwargs)

    return wrapper


# ==========================================================
# Role Required
# ==========================================================

def role_required(role):

    def decorator(func):

        @wraps(func)

        def wrapper(*args, **kwargs):

            if "role" not in session:

                flash(
                    "Silakan login.",
                    "warning"
                )

                return redirect(url_for("login"))

            if session["role"] != role:

                flash(
                    "Anda tidak memiliki akses.",
                    "danger"
                )

                return redirect(url_for("dashboard"))

            return func(*args, **kwargs)

        return wrapper

    return decorator


# ==========================================================
# Redirect Dashboard
# ==========================================================

def dashboard_redirect():

    role = session.get("role")

    if role == ROLE_SANTRI:
        return redirect(url_for("santri_izin_hp"))

    if role == ROLE_PENGASUHAN:
        return redirect(url_for("pengasuhan_dashboard"))

    if role == ROLE_KOORDINATOR:
        return redirect(url_for("koordinator_dashboard"))

    return redirect(url_for("login"))

@app.route("/")
def index():

    return redirect(url_for('login'))

# ==========================================================
# Login
# ==========================================================

@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user()["id"]:
        return dashboard_redirect()

    if request.method == "GET":
        return render_template("auth/login.html")

    username = request.form.get("username", "").strip()
    password = request.form.get("password", "").strip()

    if not username or not password:
        flash("Username dan Password wajib diisi.", "warning")
        return redirect(url_for("login"))

    user = get_user_by_username(username)
    print('user: ', user)

    if not user or not check_password_hash(user["password"], password):
        flash("Username atau Password salah.", "danger")
        return redirect(url_for("login"))

    session.update({
        "user_id": user["id"],
        "name": user["name"],
        "username": user["username"],
        "role": user["role"]
    })

    flash(f"Selamat datang, {user['name']}.", "success")

    return dashboard_redirect()

# ==========================================================
# Logout
# ==========================================================

@app.route("/logout")
@login_required
def logout():

    session.clear()

    flash(
        "Berhasil logout.",
        "success"
    )

    return redirect(url_for("login"))


# ==========================================================
# Dashboard Santri
# ==========================================================


@app.route("/santri/izin-hp")
@login_required
@role_required(ROLE_SANTRI)
def santri_izin_hp():
    user = current_user()
    borrow_id = session.get("borrow_request_id")
    if borrow_id:
        borrow_detail = query(
            """
            SELECT
                br.*,
                u.name AS friend_name
            FROM borrow_requests br
            LEFT JOIN users u
                ON u.id = br.friend_user_id
            WHERE br.id=%s
            """,
            (borrow_id,),
            one=True
        )

        if not borrow_detail:
            session.pop("borrow_request_id", None)
    else:
        borrow_detail = query(
            """
            SELECT
                br.*,
                u.name AS friend_name
            FROM borrow_requests br
            LEFT JOIN users u
                ON u.id = br.friend_user_id
            WHERE
                br.user_id=%s
                AND br.status IN (%s,%s,%s)
            ORDER BY br.created_at DESC
            LIMIT 1
            """,
            (
                user["id"],
                STATUS_LOADING,
                STATUS_PENDING,
                STATUS_APPROVED
            ),
            one=True
        )

        if borrow_detail:
            session["borrow_request_id"] = borrow_detail["id"]

    friend_requests = query(
        """
        SELECT
            br.id,
            br.reason,
            u.name AS borrower_name
        FROM borrow_requests br
        JOIN users u
            ON u.id = br.user_id
        WHERE
            br.friend_user_id=%s
            AND br.status=%s
        ORDER BY br.created_at DESC
        """,
        (
            session["user_id"],
            STATUS_LOADING
        )
    )

    return render_template(
        "santri/dashboard.html",
        user=user,
        borrow_detail=borrow_detail,
        friend_requests=friend_requests
    )

@app.route("/santri/izin-hp-history")
@login_required
@role_required(ROLE_SANTRI)
def santri_history():
    user = current_user()
    history = get_history(user["id"])

    return render_template(
        "santri/history.html",
        user=user,
        history=history
    )

@app.route("/santri/izin-keluar")
@login_required
@role_required(ROLE_SANTRI)
def santri_izin_keluar():
    user = current_user()
    permit_id = session.get("permit_id")
    if permit_id:
        permit = query(
            """
            SELECT *
            FROM exit_permits
            WHERE
                id=%s
                AND user_id=%s
            """,
            (
                permit_id,
                user["id"]
            ),
            one=True
        )
        if not permit:
            session.pop("permit_id", None)

    else:
        permit = query(
            """
            SELECT *
            FROM exit_permits
            WHERE
                user_id=%s
                AND status IN (%s,%s)
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (
                user["id"],
                STATUS_PENDING,
                STATUS_APPROVED
            ),
            one=True
        )
        if permit:
            session["permit_id"] = permit["id"]

    return render_template(
        "santri/permit.html",
        permit=permit
    )

@app.route("/santri/izin-keluar-history")
@login_required
@role_required(ROLE_SANTRI)
def santri_izin_keluar_history():
    history = query("SELECT * FROM exit_permits WHERE user_id=%s ORDER BY id DESC", (session["user_id"],))

    return render_template(
        "santri/permit_history.html",
        history=history
    )

@app.post("/change-password")
@login_required
def change_password():

    new_password = request.form.get(
        "new_password",
        ""
    ).strip()

    confirm_password = request.form.get(
        "confirm_password",
        ""
    ).strip()

    if not new_password or not confirm_password:

        flash(
            "Seluruh field wajib diisi.",
            "warning"
        )

        return redirect(request.referrer)

    if new_password != confirm_password:

        flash(
            "Konfirmasi password tidak sama.",
            "danger"
        )

        return redirect(request.referrer)

    execute(
        """
        UPDATE users
        SET password=%s
        WHERE id=%s
        """,
        (
            generate_password_hash(new_password),
            session["user_id"]
        )
    )

    flash(
        "Password berhasil diperbarui.",
        "success"
    )

    return redirect(request.referrer)

@app.post("/friend-request/<int:request_id>/<action>")
@login_required
@role_required(ROLE_SANTRI)
def friend_request_action(request_id, action):
    print(request_id, action, 'kata gw')

    if action not in ("approve", "reject"):
        flash(
            "Aksi tidak valid.",
            "warning"
        )

        return redirect(
            url_for("santri_izin_hp")
        )

    borrow = query(
        """
        SELECT id
        FROM borrow_requests
        WHERE
            id=%s
            AND friend_user_id=%s
            AND status=%s
        """,
        (
            request_id,
            session["user_id"],
            STATUS_LOADING
        ),
        one=True
    )

    if not borrow:
        flash(
            "Permintaan tidak ditemukan atau sudah diproses.",
            "warning"
        )

        return redirect(
            url_for("santri_izin_hp")
        )


    if action == "approve":
        status = STATUS_PENDING
        message = (
            "Anda telah menyetujui permintaan teman."
        )

    else:
        status = STATUS_CANCELLED
        message = (
            "Anda menolak permintaan teman."
        )

    execute(
        """
        UPDATE borrow_requests
        SET
            status=%s
        WHERE id=%s
        """,
        (
            status,
            request_id
        )
    )

    flash(
        message,
        "success"
    )
    return redirect(
        url_for("santri_izin_hp")
    )

@app.route("/santri/borrow", methods=["GET", "POST"])
@login_required
@role_required(ROLE_SANTRI)
def santri_borrow():
    user = current_user()

    if has_active_borrow(user["id"]):
        flash("Anda masih memiliki pengajuan atau peminjaman yang aktif.", "warning")
        return redirect(url_for("santri_izin_hp"))

    if request.method == "POST":
        reason = request.form.get("reason", "").strip()
        borrow_date = request.form.get("borrow_date")
        start_time = request.form.get("start_time")
        end_time = request.form.get("end_time")
        friend_user_id = request.form.get("friend_user_id") or None
        print(friend_user_id, 'n;opc')

        # Ambil file dari request. Dropzone multiple menggunakan "files[]", form biasa menggunakan "files"
        uploaded_files = request.files.getlist("files") or request.files.getlist("files[]")

        if not reason or not borrow_date or not start_time or not end_time:
            flash("Semua field wajib diisi.", "warning")
            return redirect(url_for("santri_borrow"))

        saved_files = []
        if uploaded_files:
            saved_files = save_borrow_files(uploaded_files)

        borrow_id = execute(
            """
            INSERT INTO borrow_requests
            (
                user_id,
                reason,
                files,
                borrow_date,
                start_time,
                end_time,
                status,
                friend_user_id
            )
            VALUES
            (%s,%s,%s,%s,%s,%s,%s, %s)
            """,
            (
                user["id"],
                reason,
                json.dumps(saved_files),
                borrow_date,
                start_time,
                end_time,
                STATUS_LOADING if friend_user_id else STATUS_PENDING,
                friend_user_id
            )
        )
        session["borrow_request_id"] = borrow_id

        flash("Pengajuan berhasil dikirim.", "success")
        return redirect(url_for("santri_izin_hp"))

    users = query("""
    SELECT
        id,
        name
    FROM users
    WHERE
        role='santri'
        AND id != %s
    ORDER BY name
    """, (session["user_id"],))
    return render_template("santri/borrow.html", user=user, users=users)

@app.route("/santri/borrow/edit", methods=["GET", "POST"])
@login_required
@role_required(ROLE_SANTRI)
def santri_edit_borrow():
    borrow_id = session.get("borrow_request_id")
    if not borrow_id:
        flash(
            "Tidak ada pengajuan yang dapat diedit.",
            "warning"
        )
        return redirect(
            url_for("santri_izin_hp")
        )

    borrow = query(
        """
        SELECT *
        FROM borrow_requests
        WHERE
            id=%s
            AND user_id=%s
            AND status=%s
        """,
        (
            borrow_id,
            session["user_id"],
            STATUS_PENDING
        ),
        one=True
    )

    if not borrow:
        session.pop(
            "borrow_request_id",
            None
        )
        flash(
            "Pengajuan sudah diproses sehingga tidak dapat diubah lagi.",
            "warning"
        )
        return redirect(
            url_for("santri_izin_hp")
        )

    if request.method == "POST":
        reason = request.form.get(
            "reason",
            ""
        ).strip()
        borrow_date = request.form.get(
            "borrow_date"
        )
        start_time = request.form.get(
            "start_time"
        )
        end_time = request.form.get(
            "end_time"
        )
        friend_user_id = request.form.get('friend_user_id') or None
        uploaded_files = (
                request.files.getlist("files")
                or
                request.files.getlist("files[]")
        )
        if (
                not reason or
                not borrow_date or
                not start_time or
                not end_time
        ):
            flash(
                "Semua field wajib diisi.",
                "warning"
            )

            return redirect(
                url_for("santri_edit_borrow")
            )
        files = json.loads(borrow["files"]) if borrow["files"] else []

        if uploaded_files:
            files = save_borrow_files(uploaded_files)

        execute(
            """
            UPDATE borrow_requests
            SET
                reason=%s,
                files=%s,
                borrow_date=%s,
                start_time=%s,
                end_time=%s,
                friend_user_id=%s
            WHERE id=%s
            """,
            (
                reason,
                json.dumps(files),
                borrow_date,
                start_time,
                end_time,
                friend_user_id,
                borrow["id"]
            )
        )

        flash(
            "Pengajuan berhasil diperbarui.",
            "success"
        )
        return redirect(
            url_for("santri_izin_hp")
        )

    users = query("""
        SELECT
            id,
            name
        FROM users
        WHERE
            role='santri'
            AND id != %s
        ORDER BY name
        """, (session["user_id"],))

    return render_template(
        "santri/borrow.html",
        borrow=borrow,
        users=users
    )

@app.get("/santri/borrow/<int:request_id>/delete")
@login_required
@role_required(ROLE_SANTRI)
def santri_delete_borrow(request_id):

    borrow = query(
        """
        SELECT id
        FROM borrow_requests
        WHERE
            id=%s
            AND user_id=%s
            AND status=%s
        """,
        (
            request_id,
            session["user_id"],
            STATUS_PENDING
        ),
        one=True
    )

    if not borrow:

        flash(
            "Pengajuan tidak dapat dihapus.",
            "warning"
        )

        return redirect(
            url_for("santri_izin_hp")
        )

    execute(
        """
        DELETE
        FROM borrow_requests
        WHERE id=%s
        """,
        (request_id,)
    )

    session.pop(
        "borrow_request_id",
        None
    )

    flash(
        "Pengajuan berhasil dihapus.",
        "success"
    )

    return redirect(
        url_for("santri_izin_hp")
    )

@app.route("/santri/izin-keluar-pengajuan", methods=["GET", "POST"])
@login_required
@role_required(ROLE_SANTRI)
def santri_izin_keluar_pengajuan():
    permit = query(
        """
        SELECT COUNT(*) total
        FROM exit_permits
        WHERE user_id=%s
        AND status IN (%s,%s)
        """,
        (
            session["user_id"],
            STATUS_PENDING,
            STATUS_APPROVED
        ),
        one=True
    )
    if (permit["total"] > 0):
        flash(
            "Anda masih memiliki pengajuan izin keluar yang aktif.",
            "warning"
        )
        return redirect(url_for("santri_izin_keluar"))

    if request.method == "GET":

        DISCLAIMER_TEXT = (
            "Segala bentuk penyelundupan barang terlarang ke wilayah pondok "
            "akan berimbas kepada kebijakan yang tidak menguntungkan santri."
        )
        return render_template(
            "santri/permit_form.html",
            disclaimer_text=DISCLAIMER_TEXT
        )

    # POST
    departure_date = request.form.get("departure_date", "").strip()
    departure_time = request.form.get("departure_time", "").strip()
    reason = request.form.get("reason", "").strip()
    agreement = request.form.get("agreement")

    if not departure_date or not departure_time or not reason:
        flash("Seluruh data wajib diisi.", "warning")
        return redirect(url_for("santri_izin_keluar_pengajuan"))

    if not agreement:
        flash(
            "Anda wajib menyetujui Syarat & Ketentuan sebelum mengirim pengajuan.",
            "danger"
        )
        return redirect(url_for("santri_izin_keluar_pengajuan"))

    permit_id = execute(
        """
        INSERT INTO exit_permits
        (
            user_id,
            departure_date,
            departure_time,
            reason,
            agreement_accepted,
            agreement_accepted_at,
            status
        )
        VALUES
        (%s,%s,%s,%s,%s,NOW(),%s)
        """,
        (
            session["user_id"],
            departure_date,
            departure_time,
            reason,
            True,
            STATUS_PENDING
        )
    )
    session["permit_id"] = permit_id
    flash("Pengajuan izin keluar berhasil dikirim.", "success")
    return redirect(url_for("santri_izin_keluar"))

@app.route("/izin-keluar/<int:id>/hapus")
@login_required
@role_required(ROLE_SANTRI)
def santri_izin_keluar_hapus(id):
    execute('DELETE FROM exit_permits WHERE id = %s', (id))
    flash("Pengajuan izin keluar berhasil dihapus.", "success")
    return redirect(url_for("santri_izin_keluar"))

# ==========================================================
# Dashboard Pengasuhan
# ==========================================================

@app.route("/pengasuhan/dashboard")
@login_required
@role_required(ROLE_PENGASUHAN)
def pengasuhan_dashboard():
    stats = pengasuhan_statistics()
    latest = latest_requests()

    return render_template(
        "pengasuhan/dashboard.html",
        stats=stats,
        latest=latest
    )

@app.route("/pengasuhan/approve/<int:request_id>", methods=["POST"])
@login_required
@role_required(ROLE_PENGASUHAN)
def approve_request(request_id):

    data = get_request_by_id(request_id)
    pengasuhan_note = request.form.get("pengasuhan_note","").strip()

    if not data:
        flash(
            "Pengajuan tidak ditemukan.",
            "danger"
        )
        return redirect(
            url_for("pengasuhan_dashboard")
        )

    if data["status"] != STATUS_PENDING:
        flash(
            "Pengajuan sudah diproses.",
            "warning"
        )
        return redirect(
            url_for("pengasuhan_dashboard")
        )

    approve_borrow(
        request_id,
        current_user()["id"],
        pengasuhan_note
    )

    flash(
        "Pengajuan berhasil disetujui.",
        "success"
    )

    return redirect(
        url_for("pengasuhan_requests")
    )

@app.route(
    "/pengasuhan/reject/<int:request_id>",
    methods=["GET", "POST"]
)
@login_required
@role_required(ROLE_PENGASUHAN)
def reject_request(request_id):
    data = get_request_by_id(request_id)
    if not data:
        flash(
            "Pengajuan tidak ditemukan.",
            "danger"
        )
        return redirect(
            url_for("pengasuhan_dashboard")
        )

    if data["status"] != STATUS_PENDING:
        flash(
            "Pengajuan sudah diproses.",
            "warning"
        )
        return redirect(
            url_for("pengasuhan_dashboard")
        )

    pengasuhan_note = request.form.get(
        "pengasuhan_note",
        ""
    ).strip()

    if not pengasuhan_note:
        flash(
            "Alasan penolakan wajib diisi.",
            "warning"
        )
        return redirect(
            url_for("pengasuhan_requests")
        )

    reject_borrow(
        request_id,
        current_user()["id"],
        pengasuhan_note
    )

    flash(
        "Pengajuan berhasil ditolak.",
        "success"
    )

    return redirect(
        url_for("pengasuhan_requests")
    )

@app.route("/pengasuhan/requests")
@login_required
@role_required(ROLE_PENGASUHAN)
def pengasuhan_requests():

    status = request.args.get("status")

    if status not in (
        None,
        STATUS_PENDING,
        STATUS_APPROVED,
        STATUS_REJECTED,
        STATUS_FINISHED
    ):
        status = None

    requests = get_all_requests(status)

    return render_template(
        "pengasuhan/requests.html",
        requests=requests,
        current_status=status
    )

@app.route("/pengasuhan/permits")
@login_required
@role_required(ROLE_PENGASUHAN)
def pengasuhan_permits():
    status = request.args.get("status")

    if status not in (
        None,
        "PENDING",
        "APPROVED",
        "REJECTED",
        "FINISHED"
    ):
        status = None

    if status:
        permits = query(
            """
            SELECT
                ep.*,
                u.name
            FROM exit_permits ep
            JOIN users u
                ON u.id = ep.user_id
            WHERE ep.status=%s
            ORDER BY ep.created_at DESC
            """,
            (status,)
        )
    else:
        permits = query(
            """
            SELECT
                ep.*,
                u.name
            FROM exit_permits ep
            JOIN users u
                ON u.id = ep.user_id
            ORDER BY ep.created_at DESC
            """
        )

    settings = query(
        """
        SELECT *
        FROM exit_permit_settings
        LIMIT 1
        """,
        one=True
    )

    return render_template(
        "pengasuhan/permits.html",
        permits=permits,
        current_status=status,
        settings=settings
    )

@app.post("/pengasuhan/permit/update-settings")
@login_required
@role_required(ROLE_PENGASUHAN)
def pengasuhan_permit_update_settings():
    hours = request.form.get(
        "default_return_hours",
        ""
    ).strip()
    if not hours.isdigit() or int(hours) <= 0:
        flash(
            "Batas waktu default tidak valid.",
            "warning"
        )

        return redirect(
            url_for("keluar_pondok.admin_requests")
        )
    execute(
        """
        UPDATE exit_permit_settings
        SET
            default_return_hours=%s
        WHERE id=1
        """,
        (
            int(hours),
        )
    )
    flash(
        "Pengaturan default batas waktu kembali berhasil diperbarui.",
        "success"
    )
    return redirect(
        url_for("pengasuhan_permits")
    )

@app.route("/pengasuhan/permit/<int:permit_id>")
@login_required
@role_required(ROLE_PENGASUHAN)
def pengasuhan_permit_detail(permit_id):
    data = query(
        """
        SELECT
            ep.*,
            u.name
        FROM exit_permits ep
        JOIN users u
            ON u.id = ep.user_id
        WHERE ep.id=%s
        """,
        (permit_id,),
        one=True
    )

    if not data:
        flash(
            "Pengajuan tidak ditemukan.",
            "danger"
        )
        return redirect(
            url_for("pengasuhan_permits")
        )

    settings = query(
        """
        SELECT *
        FROM exit_permit_settings
        LIMIT 1
        """,
        one=True
    )

    suggested_deadline = None

    if data["status"] == "PENDING":
        departure_dt = (
                datetime.combine(
                    data["departure_date"],
                    datetime.min.time()
                )
                +
                data["departure_time"]
        )

        suggested_deadline = departure_dt + timedelta(
            hours=settings["default_return_hours"]
        )

    late_minutes = None

    if (
        data["returned_at"]
        and
        data["return_deadline"]
    ):

        diff = int(
            (
                data["returned_at"]
                -
                data["return_deadline"]
            ).total_seconds() // 60
        )

        if diff > 0:
            late_minutes = diff

    return render_template(
        "pengasuhan/permit_detail.html",
        data=data,
        suggested_deadline=suggested_deadline,
        late_minutes=late_minutes
    )

@app.post("/pengasuhan/permit/approve")
@login_required
@role_required(ROLE_PENGASUHAN)
def pengasuhan_permit_approve():
    print(request.form)
    permit_id = request.form.get("permit_id")

    data = query(
        """
        SELECT *
        FROM exit_permits
        WHERE id=%s
        """,
        (permit_id,),
        one=True
    )
    print('datalang: ', data)

    if not data or data["status"] != STATUS_PENDING:
        flash(
            "Status pengajuan sudah berubah.",
            "warning"
        )

        return redirect(
            url_for("pengasuhan_permits")
        )

    return_deadline = request.form.get(
        "return_deadline",
        ""
    ).strip()

    admin_note = request.form.get(
        "admin_note",
        ""
    ).strip()

    if not return_deadline:
        flash(
            "Batas waktu wajib kembali harus diisi.",
            "warning"
        )

        return redirect(
            url_for(
                "pengasuhan_permit_detail",
                permit_id=permit_id
            )
        )

    execute(
        """
        UPDATE exit_permits
        SET
            status=%s,
            return_deadline=%s,
            admin_note=%s,
            approved_by=%s,
            approved_at=NOW()
        WHERE id=%s
        """,
        (
            STATUS_APPROVED,
            return_deadline,
            admin_note,
            session["user_id"],
            permit_id
        )
    )

    flash(
        "Pengajuan izin keluar disetujui.",
        "success"
    )

    return redirect(
        url_for("pengasuhan_permits")
    )

@app.post("/pengasuhan/permit/reject")
@login_required
@role_required(ROLE_PENGASUHAN)
def pengasuhan_permit_reject():

    permit_id = request.form.get("permit_id")

    data = query(
        """
        SELECT *
        FROM exit_permits
        WHERE id=%s
        """,
        (permit_id,),
        one=True
    )

    if not data or data["status"] != STATUS_PENDING:
        flash(
            "Status pengajuan sudah berubah.",
            "warning"
        )

        return redirect(
            url_for("pengasuhan_permits")
        )

    admin_note = request.form.get(
        "admin_note",
        ""
    ).strip()

    execute(
        """
        UPDATE exit_permits
        SET
            status=%s,
            admin_note=%s,
            rejected_by=%s,
            rejected_at=NOW()
        WHERE id=%s
        """,
        (
            STATUS_REJECTED,
            admin_note,
            session["user_id"],
            permit_id
        )
    )

    flash(
        "Pengajuan izin keluar ditolak.",
        "success"
    )

    return redirect(
        url_for("pengasuhan_permits")
    )

@app.post("/pengasuhan/permit/finish")
@login_required
@role_required(ROLE_PENGASUHAN)
def pengasuhan_permit_finish():

    permit_id = request.form.get("permit_id")
    data = query(
        """
        SELECT *
        FROM exit_permits
        WHERE id=%s
        """,
        (permit_id,),
        one=True
    )

    if not data or data["status"] != STATUS_APPROVED:
        flash(
            "Status pengajuan sudah berubah.",
            "warning"
        )
        return redirect(
            url_for("pengasuhan_permits")
        )

    returned_at = request.form.get("returned_at")
    execute(
        """
        UPDATE exit_permits
        SET
            status=%s,
            returned_at=%s,
            finished_by=%s
        WHERE id=%s
        """,
        (
            STATUS_FINISHED,
            returned_at,
            session["user_id"],
            permit_id
        )
    )

    flash(
        "Santri berhasil ditandai sudah kembali ke pondok.",
        "success"
    )
    return redirect(
        url_for("pengasuhan_permits")
    )

@app.route("/pengasuhan/requests/<int:request_id>")
@login_required
@role_required(ROLE_PENGASUHAN)
def pengasuhan_request_detail(request_id):
    data = get_request_by_id(request_id)
    if not data:
        flash(
            "Pengajuan tidak ditemukan.",
            "danger"
        )
        return redirect(
            url_for("pengasuhan_requests")
        )

    # Check waktu telat jika ada
    late_minutes = None
    if data["finished_at"]:
        deadline = (
                datetime.combine(
                    data["borrow_date"],
                    datetime.min.time()
                )
                + data["end_time"]
        )
        late_minutes = max(
            0,
            int((data["finished_at"] - deadline).total_seconds() // 60)
        )

    late_summary = query(
        """
        SELECT
            COUNT(*) total_late,
            COALESCE(SUM(late_minutes),0) total_minutes,
            COALESCE(MAX(late_minutes),0) max_minutes,
            COALESCE(AVG(late_minutes),0) avg_minutes
        FROM late_recaps
        WHERE user_id=%s
        """,
        (data["user_id"],),
        one=True
    )

    total_late = late_summary["total_late"] or 0
    total_minutes = late_summary["total_minutes"] or 0

    if total_late == 0:
        recommendation = {
            "level": "good",
            "title": "Riwayat Sangat Baik",
            "color": "green",
            "message": (
                "Mahasantri belum pernah tercatat terlambat "
                "mengembalikan HP."
            )
        }

    elif total_minutes <= 180:
        recommendation = {
            "level": "good",
            "title": "Layak Dipertimbangkan",
            "color": "green",
            "message": (
                "Riwayat keterlambatan masih tergolong rendah. "
                "Pengajuan dapat dipertimbangkan seperti biasa."
            )
        }

    elif total_minutes <= 1440:
        recommendation = {
            "level": "warning",
            "title": "Perlu Perhatian",
            "color": "yellow",
            "message": (
                "Mahasantri pernah beberapa kali terlambat. "
                "Disarankan memberikan pengingat agar HP "
                "dikembalikan tepat waktu."
            )
        }

    elif total_minutes <= 4320:
        recommendation = {
            "level": "danger",
            "title": "Perlu Pertimbangan",
            "color": "orange",
            "message": (
                "Total keterlambatan sudah cukup tinggi. "
                "Sebaiknya pertimbangkan kembali sebelum "
                "menyetujui pengajuan ini."
            )
        }

    else:
        recommendation = {
            "level": "critical",
            "title": "Risiko Tinggi",
            "color": "red",
            "message": (
                "Riwayat keterlambatan sangat tinggi. "
                "Disarankan melakukan evaluasi lebih lanjut "
                "atau meminta alasan tambahan sebelum "
                "memberikan persetujuan."
            )
        }

    return render_template(
        "pengasuhan/detail.html",
        data=data,
        current_user_role=session["role"],
        late_minutes=late_minutes,
        late_summary=late_summary,
        recommendation=recommendation

    )

@app.route("/pengasuhan/users")
@login_required
@role_required(ROLE_PENGASUHAN)
def pengasuhan_users():

    users = get_all_users()
    return render_template(
        "pengasuhan/users.html",
        users=users,
        current_user_id=session["user_id"]
    )

@app.post("/pengasuhan/users/create")
@login_required
@role_required(ROLE_PENGASUHAN)
def pengasuhan_users_create():
    name = request.form.get("name", "").strip()

    username = request.form.get("username", "").strip()

    password = request.form.get("password", "").strip()

    role = request.form.get("role", "santri")

    if not name:
        flash("Nama wajib diisi.", "warning")

        return redirect(
            url_for("pengasuhan_users")
        )

    if get_user_by_username(username):
        flash(
            "Username sudah digunakan.",
            "danger"
        )

        return redirect(
            url_for("pengasuhan_users")
        )

    create_user(
        name,
        username,
        password,
        role
    )

    flash(
        "Santri berhasil ditambahkan.",
        "success"
    )

    return redirect(
        url_for("pengasuhan_users")
    )

@app.post("/pengasuhan/users/update/<int:user_id>")
@login_required
@role_required(ROLE_PENGASUHAN)
def pengasuhan_users_update(user_id):

    user = get_user_by_id(user_id)

    if not user:

        flash(
            "Data santri tidak ditemukan.",
            "danger"
        )

        return redirect(
            url_for("pengasuhan_users")
        )

    name = request.form.get(
        "name",
        ""
    ).strip()

    username = request.form.get(
        "username",
        ""
    ).strip()

    password = request.form.get(
        "password",
        ""
    ).strip()

    role = request.form.get(
        "role",
        "santri"
    )

    if not name:

        flash(
            "Nama wajib diisi.",
            "warning"
        )

        return redirect(
            url_for("pengasuhan_users")
        )

    if not username:

        flash(
            "Username wajib diisi.",
            "warning"
        )

        return redirect(
            url_for("pengasuhan_users")
        )

    if role not in ["santri", "koordinator"]:

        flash(
            "Role tidak valid.",
            "warning"
        )

        return redirect(
            url_for("pengasuhan_users")
        )

    username_owner = get_user_by_username(username)

    if username_owner and username_owner["id"] != user_id:

        flash(
            "Username sudah digunakan.",
            "danger"
        )

        return redirect(
            url_for("pengasuhan_users")
        )

    update_user(
        user_id,
        name,
        username,
        role
    )

    if password:

        update_password(
            user_id,
            password
        )

    flash(
        "Data santri berhasil diperbarui.",
        "success"
    )

    return redirect(
        url_for("pengasuhan_users")
    )
# ==========================================================
# Dashboard Koordinator
# ==========================================================

@app.route("/koordinator/dashboard")
@login_required
@role_required(ROLE_KOORDINATOR)
def koordinator_dashboard():

    stats = koordinator_statistics()

    latest = latest_active()

    return render_template(

        "koordinator/dashboard.html",

        stats=stats,

        latest=latest

    )

@app.route("/koordinator/requests")
@login_required
@role_required(ROLE_KOORDINATOR)
def koordinator_requests():

    status = request.args.get("status")
    if status not in (
        None,
        STATUS_APPROVED,
        STATUS_FINISHED
    ):
        status = None

    requests = get_koordinator_requests(status)

    return render_template(

        "koordinator/requests.html",

        requests=requests,
        current_status=status

    )

@app.route("/koordinator/requests/<int:request_id>")
@login_required
@role_required(ROLE_KOORDINATOR)
def koordinator_request_detail(request_id):

    data = get_request_by_id(request_id)

    if not data:

        flash(
            "Data tidak ditemukan.",
            "danger"
        )

        return redirect(
            url_for("koordinator_requests")
        )

    return render_template(
        "koordinator/detail.html",
        data=data
    )

@app.route("/koordinator/finish/<int:request_id>", methods=["POST"])
@login_required
@role_required(ROLE_KOORDINATOR)
def finish_request(request_id):
    print(request.form)
    data = get_request_by_id(request_id)
    finished_at = request.form.get("finished_at")
    if not data:
        flash(
            "Data tidak ditemukan.",
            "danger"
        )

        return redirect(
            url_for("koordinator_requests")
        )

    if data["status"] != STATUS_APPROVED:
        flash(
            "Status peminjaman sudah berubah.",
            "warning"
        )

        return redirect(
            url_for("koordinator_requests")
        )

    execute(
        """
        UPDATE borrow_requests
        SET
            status=%s,
            finished_by=%s,
            finished_at=%s
        WHERE
            id=%s
        """,
        (
            STATUS_FINISHED,
            session["user_id"],
            finished_at,
            request_id
        )
    )

    borrow_end = datetime.strptime(
        f"{data['borrow_date']} {data['end_time']}",
        "%Y-%m-%d %H:%M:%S"
    )

    finished = datetime.strptime(finished_at,"%Y-%m-%d %H:%M:%S")
    late_minutes = int((finished - borrow_end).total_seconds() // 60)
    if late_minutes > 0:
        execute(
            """
            INSERT INTO late_recaps
            (
                user_id,
                date,
                late_minutes
            )
            VALUES
            (%s,%s,%s)
            ON DUPLICATE KEY UPDATE
                late_minutes = late_minutes + VALUES(late_minutes)
            """,
            (
                data["user_id"],
                data["borrow_date"],
                late_minutes
            )
        )

    flash(
        "Pengembalian berhasil dikonfirmasi.",
        "success"
    )

    return redirect(
        url_for("koordinator_requests")
    )

@app.get("/borrow-files/view/<path:file_path>")
@login_required
def borrow_file_view(file_path):
    directory = os.path.dirname(file_path)
    filename = os.path.basename(file_path)
    return send_from_directory(
        directory,
        filename,
        as_attachment=False
    )

@app.get("/borrow-files/download/<path:file_path>")
@login_required
def borrow_file_download(file_path):
    directory = os.path.dirname(file_path)
    filename = os.path.basename(file_path)
    return send_from_directory(
        directory,
        filename,
        as_attachment=True
    )

# ==========================================================
# Error Handler
# ==========================================================

@app.errorhandler(403)
def forbidden(error):

    return render_template(
        "errors/403.html"
    ), 403


@app.errorhandler(404)
def not_found(error):

    return render_template(
        "errors/404.html"
    ), 404


@app.errorhandler(500)
def server_error(error):

    return render_template(
        "errors/500.html"
    ), 500

from datetime import datetime

MONTHS = {
    1: "Januari",
    2: "Februari",
    3: "Maret",
    4: "April",
    5: "Mei",
    6: "Juni",
    7: "Juli",
    8: "Agustus",
    9: "September",
    10: "Oktober",
    11: "November",
    12: "Desember",
}


@app.template_filter("format_datetime")
def format_datetime(value):
    if not value:
        return "-"

    return (
        f"{value.day} "
        f"{MONTHS[value.month]} "
        f"{value.year} "
        f"{value.strftime('%H:%M')}"
    )


# ==========================================================
# Run App
# ==========================================================

if __name__ == "__main__":

    app.run(
        debug=True
    )