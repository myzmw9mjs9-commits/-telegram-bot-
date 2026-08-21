import os
import sqlite3

# 1. حذف ملف قاعدة البيانات القديمة بالكامل إن وجد
db_file = "bot_database.db"
if os.path.exists(db_file):
    os.remove(db_file)
    print("تم حذف قاعدة البيانات بالكامل بنجاح.")

# 2. إنشاء قاعدة بيانات جديدة ونظيفة من الصفر
conn = sqlite3.connect(db_file)
cursor = conn.cursor()

cursor.execute('''
    CREATE TABLE wallets (
        user_id INTEGER PRIMARY KEY,
        usdt REAL,
        btc REAL
    )
''')

cursor.execute('''
    CREATE TABLE trades (
        user_id INTEGER PRIMARY KEY,
        entry_price REAL,
        btc_bought REAL,
        tp REAL,
        sl REAL,
        trailing_step INTEGER DEFAULT 0
    )
''')

cursor.execute('''
    CREATE TABLE auto_users (
        user_id INTEGER PRIMARY KEY
    )
''')

cursor.execute('''
    CREATE TABLE history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        entry_price REAL,
        exit_price REAL,
        pnl REAL,
        timestamp TEXT
    )
''')

conn.commit()
conn.close()

print("تم إعادة إنشاء قاعدة البيانات وتصفير جميع السجلات والمحافظ.")
