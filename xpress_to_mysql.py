"""
xpress_to_mysql.py
อ่านไฟล์ .DBF จากโปรแกรม Xpress แล้วนำเข้า MySQL
หรือ export เป็น CSV
"""

import os
import csv
import sys
from datetime import date, datetime

# --- ตั้งค่าที่นี่ ---
DBF_FOLDER = os.path.dirname(os.path.abspath(__file__))  # folder เดียวกับไฟล์นี้
ENCODING = "tis620"   # encoding ของ Xpress (TIS-620 / cp874)

# MySQL config (แก้ตามเครื่องของคุณ)
MYSQL_CONFIG = {
    "host":     "localhost",
    "port":     3306,
    "user":     "root",
    "password": "your_password",
    "database": "xpress_db",
}

# เลือก mode: "csv" หรือ "mysql"
MODE = "csv"   # เปลี่ยนเป็น "mysql" เมื่อต้องการนำเข้า MySQL

# folder เก็บ CSV output
CSV_OUTPUT_DIR = os.path.join(DBF_FOLDER, "csv_export")


# -------------------------------------------------------

try:
    from dbfread import DBF
except ImportError:
    sys.exit("กรุณาติดตั้ง dbfread ก่อน:  pip3 install dbfread")


def safe_value(v):
    """แปลงค่าให้เป็น string ที่ MySQL/CSV รับได้"""
    if v is None:
        return None
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    if isinstance(v, float) and (v != v):   # NaN
        return None
    return v


def read_dbf(path):
    """อ่าน DBF พร้อมจัดการ encoding error"""
    try:
        table = DBF(
            path,
            encoding=ENCODING,
            char_decode_errors="replace",   # แทน ? ถ้า decode ไม่ได้
            ignore_missing_memofile=True,
        )
        fields = [f.name for f in table.fields]
        records = []
        for rec in table:
            records.append({k: safe_value(v) for k, v in rec.items()})
        return fields, records
    except Exception as e:
        print(f"  [ERROR] อ่านไม่ได้: {e}")
        return [], []


# ===== MODE: CSV =====

def export_all_to_csv():
    os.makedirs(CSV_OUTPUT_DIR, exist_ok=True)
    dbf_files = sorted(f for f in os.listdir(DBF_FOLDER) if f.upper().endswith(".DBF"))
    print(f"พบไฟล์ .DBF ทั้งหมด {len(dbf_files)} ไฟล์\n")

    for fname in dbf_files:
        path = os.path.join(DBF_FOLDER, fname)
        table_name = os.path.splitext(fname)[0].lower()
        print(f"กำลังอ่าน {fname} ...", end=" ")

        fields, records = read_dbf(path)
        if not fields:
            continue

        csv_path = os.path.join(CSV_OUTPUT_DIR, f"{table_name}.csv")
        with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(records)

        print(f"{len(records):,} records  →  {csv_path}")

    print(f"\nเสร็จแล้ว! ไฟล์ CSV อยู่ใน: {CSV_OUTPUT_DIR}")


# ===== MODE: MySQL =====

def mysql_type(dbf_type):
    mapping = {
        "C": "TEXT",
        "N": "DOUBLE",
        "B": "DOUBLE",      # Binary/Float ใน Xpress
        "D": "DATE",
        "L": "TINYINT(1)",
        "M": "LONGTEXT",
        "I": "INT",
        "F": "DOUBLE",
        "Y": "DECIMAL(18,4)",
    }
    return mapping.get(dbf_type, "TEXT")


def import_all_to_mysql():
    try:
        import mysql.connector
    except ImportError:
        sys.exit("กรุณาติดตั้ง mysql-connector:  pip3 install mysql-connector-python")

    conn = mysql.connector.connect(**MYSQL_CONFIG)
    cur = conn.cursor()
    print(f"เชื่อมต่อ MySQL สำเร็จ: {MYSQL_CONFIG['host']}/{MYSQL_CONFIG['database']}\n")

    dbf_files = sorted(f for f in os.listdir(DBF_FOLDER) if f.upper().endswith(".DBF"))
    print(f"พบไฟล์ .DBF ทั้งหมด {len(dbf_files)} ไฟล์\n")

    for fname in dbf_files:
        path = os.path.join(DBF_FOLDER, fname)
        table_name = os.path.splitext(fname)[0].lower()
        print(f"กำลังนำเข้า {fname} → ตาราง `{table_name}` ...", end=" ")

        try:
            table_dbf = DBF(
                path,
                encoding=ENCODING,
                char_decode_errors="replace",
                ignore_missing_memofile=True,
            )
            fields = table_dbf.fields
            records = []
            for rec in table_dbf:
                records.append(tuple(safe_value(v) for v in rec.values()))
        except Exception as e:
            print(f"[ERROR] {e}")
            continue

        if not fields:
            print("ไม่มี field")
            continue

        # สร้างตาราง (DROP ถ้ามีอยู่แล้ว)
        col_defs = ", ".join(
            f"`{f.name}` {mysql_type(f.type)}" for f in fields
        )
        cur.execute(f"DROP TABLE IF EXISTS `{table_name}`")
        cur.execute(f"CREATE TABLE `{table_name}` ({col_defs}) CHARACTER SET utf8mb4")

        # INSERT
        if records:
            placeholders = ", ".join(["%s"] * len(fields))
            sql = f"INSERT INTO `{table_name}` VALUES ({placeholders})"
            cur.executemany(sql, records)

        conn.commit()
        print(f"{len(records):,} records")

    cur.close()
    conn.close()
    print("\nนำเข้า MySQL เสร็จแล้ว!")


# ===== MAIN =====

if __name__ == "__main__":
    # รับ argument จาก command line ได้  เช่น:  python3 xpress_to_mysql.py csv
    if len(sys.argv) > 1:
        MODE = sys.argv[1].lower()

    print(f"=== Xpress DBF Reader  (mode: {MODE}) ===\n")

    if MODE == "csv":
        export_all_to_csv()
    elif MODE == "mysql":
        import_all_to_mysql()
    else:
        print("mode ที่รองรับ:  csv  หรือ  mysql")
        print("ตัวอย่าง:")
        print("  python3 xpress_to_mysql.py csv")
        print("  python3 xpress_to_mysql.py mysql")
