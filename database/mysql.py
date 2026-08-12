import pymysql
from werkzeug.security import generate_password_hash
from config import Config

# ============================
# Koneksi ke MySQL Server
# ============================

def get_server_connection():
    return pymysql.connect(
        host=Config.DB_HOST,
        port=Config.DB_PORT,
        user=Config.DB_USER,
        password=Config.DB_PASSWORD,
        autocommit=True,
        cursorclass=pymysql.cursors.DictCursor
    )


# ============================
# Koneksi ke Database
# ============================

def get_connection():
    return pymysql.connect(
        host=Config.DB_HOST,
        port=Config.DB_PORT,
        user=Config.DB_USER,
        password=Config.DB_PASSWORD,
        database=Config.DB_NAME,
        autocommit=True,
        cursorclass=pymysql.cursors.DictCursor
    )


# ============================
# Inisialisasi Database
# ============================

def initialize_database():

    server = get_server_connection()
    cursor = server.cursor()

    # Buat Database
    cursor.execute(f"""
        CREATE DATABASE IF NOT EXISTS {Config.DB_NAME}
        CHARACTER SET utf8mb4
        COLLATE utf8mb4_unicode_ci;
    """)

    server.close()

    db = get_connection()
    cursor = db.cursor()

    # ============================
    # USERS
    # ============================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users(
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            username VARCHAR(50) UNIQUE NOT NULL,
            password VARCHAR(255) NOT NULL,
            role ENUM(
                'santri',
                'pengasuhan',
                'koordinator'
            ) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ============================
    # BORROW REQUEST
    # ============================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS borrow_requests(
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            friend_user_id INT NULL,
            reason TEXT NOT NULL,
            files JSON NULL,
            start_datetime DATETIME NULL,
            end_datetime DATETIME NULL,
            status ENUM(
                'PENDING',
                'APPROVED',
                'REJECTED',
                'FINISHED',
                'LOADING',
                'CANCELLED'
            ) DEFAULT 'PENDING',
            pengasuhan_note TEXT NULL,
            approved_by INT NULL,
            approved_at DATETIME NULL,
            rejected_by INT NULL,
            rejected_at DATETIME NULL,
            finished_by INT NULL,
            finished_at DATETIME NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        
            FOREIGN KEY(user_id) REFERENCES users(id),        
            FOREIGN KEY(approved_by) REFERENCES users(id),
            FOREIGN KEY(rejected_by) REFERENCES users(id),
            FOREIGN KEY(finished_by) REFERENCES users(id),
            FOREIGN KEY(friend_user_id) REFERENCES users(id),
            
            INDEX idx_friend_loading (friend_user_id, status)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS forbidden_time_rules(
            id INT AUTO_INCREMENT PRIMARY KEY,
            title VARCHAR(100) NOT NULL,
            start_time TIME NOT NULL,
            end_time TIME NOT NULL,
            reason TEXT NOT NULL,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS late_recaps(
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            date DATE NOT NULL,
            late_minutes INT NOT NULL DEFAULT 0,
            updated_at TIMESTAMP
                DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP,
        
            UNIQUE KEY uk_user_date(user_id, date),
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
    """)

    # ============================
    # (Pengajuan Izin Keluar Pondok)
    # ============================

    cursor.execute("""
           CREATE TABLE IF NOT EXISTS exit_permits(
               id INT AUTO_INCREMENT PRIMARY KEY,
               user_id INT NOT NULL,

               departure_date DATE NOT NULL,
               departure_time TIME NOT NULL,
               reason TEXT NOT NULL,

               agreement_accepted BOOLEAN NOT NULL DEFAULT FALSE,
               agreement_accepted_at DATETIME NULL,

               status ENUM(
                   'PENDING',
                   'APPROVED',
                   'REJECTED',
                   'FINISHED'
               ) DEFAULT 'PENDING',

               admin_note TEXT NULL,

               return_deadline DATETIME NULL,

               approved_by INT NULL,
               approved_at DATETIME NULL,

               rejected_by INT NULL,
               rejected_at DATETIME NULL,

               returned_at DATETIME NULL,
               finished_by INT NULL,

               created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

               FOREIGN KEY(user_id) REFERENCES users(id),
               FOREIGN KEY(approved_by) REFERENCES users(id),
               FOREIGN KEY(rejected_by) REFERENCES users(id),
               FOREIGN KEY(finished_by) REFERENCES users(id),

               INDEX idx_exit_permit_user_status (user_id, status)
           )
       """)

    # ============================
    # (Konfigurasi default batas waktu kembali)
    # ============================

    cursor.execute("""
           CREATE TABLE IF NOT EXISTS exit_permit_settings(
               id INT PRIMARY KEY DEFAULT 1,
               default_return_hours INT NOT NULL DEFAULT 4,
               updated_at TIMESTAMP
                   DEFAULT CURRENT_TIMESTAMP
                   ON UPDATE CURRENT_TIMESTAMP
           )
       """)

    # ============================
    # Dummy User
    # ============================

    cursor.execute("SELECT COUNT(*) total FROM users")
    total = cursor.fetchone()["total"]
    if total == 0:

        users = [

            (
                "Santri",
                "santri",
                generate_password_hash("123456"),
                "santri"
            ),

            (
                "Pengasuhan",
                "pengasuhan",
                generate_password_hash("123456"),
                "pengasuhan"
            ),

            (
                "Koordinator",
                "koordinator",
                generate_password_hash("123456"),
                "koordinator"
            )

        ]

        cursor.executemany("""
            INSERT INTO users(
                name,
                username,
                password,
                role
            )
            VALUES(%s,%s,%s,%s)
        """, users)

        print("Dummy User berhasil dibuat.")

    # ============================
    # Dummy Permit
    # ============================
    
    cursor.execute("SELECT COUNT(*) total FROM exit_permit_settings")
    total = cursor.fetchone()["total"]

    if total == 0:
        cursor.execute("""
               INSERT INTO exit_permit_settings(id, default_return_hours)
               VALUES (1, 4)
               """)

    db.close()
    print("Database berhasil diinisialisasi.")