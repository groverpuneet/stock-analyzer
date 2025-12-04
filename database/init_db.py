import psycopg2
from psycopg2 import sql
import os

DB_PARAMS = {
    'dbname': 'stock_analyzer',
    'user': os.environ.get('USER', 'puneetgrover'),
    'password': '',
    'host': 'localhost',
    'port': '5432'
}

def create_database():
    conn = psycopg2.connect(
        dbname='postgres',
        user=DB_PARAMS['user'],
        host=DB_PARAMS['host'],
        port=DB_PARAMS['port']
    )
    conn.autocommit = True
    cursor = conn.cursor()
    
    cursor.execute("SELECT 1 FROM pg_database WHERE datname='stock_analyzer'")
    exists = cursor.fetchone()
    
    if not exists:
        cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier('stock_analyzer')))
        print("✓ Database created")
    else:
        print("✓ Database already exists")
    
    cursor.close()
    conn.close()

def create_tables():
    conn = psycopg2.connect(**DB_PARAMS)
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stocks (
            id SERIAL PRIMARY KEY,
            instrument_token BIGINT UNIQUE NOT NULL,
            tradingsymbol VARCHAR(50) NOT NULL,
            name VARCHAR(200),
            exchange VARCHAR(10) NOT NULL,
            UNIQUE(exchange, tradingsymbol)
        )
    """)
    print("✓ Table stocks created")
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS daily_prices (
            id SERIAL PRIMARY KEY,
            stock_id INTEGER REFERENCES stocks(id),
            date DATE NOT NULL,
            open DECIMAL(12, 2),
            high DECIMAL(12, 2),
            low DECIMAL(12, 2),
            close DECIMAL(12, 2),
            volume BIGINT,
            UNIQUE(stock_id, date)
        )
    """)
    print("✓ Table daily_prices created")
    
    conn.commit()
    cursor.close()
    conn.close()

if __name__ == "__main__":
    print("\nSetting up database...\n")
    create_database()
    create_tables()
    print("\n✓ Setup complete!\n")
