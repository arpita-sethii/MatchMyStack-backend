import sqlite3
import os

db_path = "app.db"
backup_folder = "backups"
os.makedirs(backup_folder, exist_ok=True)

backup_file = os.path.join(backup_folder, "app_dump.sql")

con = sqlite3.connect(db_path)
with open(backup_file, "w", encoding="utf-8") as f:
    for line in con.iterdump():
        f.write("%s\n" % line)
con.close()

print(f"✅ Backup complete! File saved at: {backup_file}")
