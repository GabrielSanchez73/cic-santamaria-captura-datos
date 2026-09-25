import sqlite3

c = sqlite3.connect("concentrador.db")
for (tabla,) in c.execute("select name from sqlite_master where type='table'"):
    cols = [x[1] for x in c.execute(f"PRAGMA table_info({tabla})")]
    print(tabla, "->", cols)