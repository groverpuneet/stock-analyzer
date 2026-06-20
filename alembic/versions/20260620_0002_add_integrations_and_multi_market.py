"""Add integration tables and multi-market support.
Revision ID: 0002
Revises: 0001
"""
from alembic import op
revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None

def upgrade():
    op.execute("ALTER TABLE stocks ADD COLUMN IF NOT EXISTS market VARCHAR(10) NOT NULL DEFAULT 'NSE'")
    op.execute("CREATE INDEX IF NOT EXISTS idx_stocks_market ON stocks(market)")
    op.execute("""CREATE TABLE IF NOT EXISTS data_refresh_log (
        id SERIAL PRIMARY KEY, source VARCHAR(60) NOT NULL UNIQUE,
        tier VARCHAR(20) NOT NULL, started_at TIMESTAMP, completed_at TIMESTAMP,
        status VARCHAR(20) DEFAULT 'pending', rows_upserted INTEGER DEFAULT 0,
        error_message TEXT)""")
    sources = [
        ('kite_ohlcv','daily'),('kite_quotes','daily'),('tech_indicators','daily'),
        ('signals','daily'),('fii_dii','daily'),('news_sentiment','daily'),
        ('whatsapp','daily'),('nse_actions','event'),('bulk_deals','event'),
        ('screener','weekly'),('insider_trades','weekly'),('rbi_macro','weekly'),
        ('sector_indices','weekly'),('google_trends','weekly'),('fundamentals_full','quarterly'),
    ]
    for src, tier in sources:
        op.execute(f"INSERT INTO data_refresh_log (source,tier,status) VALUES ('{src}','{tier}','never_run') ON CONFLICT (source) DO NOTHING")
    tables = {
        'fii_dii_flows': """id SERIAL PRIMARY KEY, date DATE NOT NULL UNIQUE,
            fii_buy DECIMAL(16,2), fii_sell DECIMAL(16,2), fii_net DECIMAL(16,2),
            dii_buy DECIMAL(16,2), dii_sell DECIMAL(16,2), dii_net DECIMAL(16,2), source VARCHAR(40)""",
        'corporate_actions': """id SERIAL PRIMARY KEY,
            stock_id INTEGER REFERENCES stocks(id) ON DELETE CASCADE,
            ex_date DATE NOT NULL, record_date DATE, action_type VARCHAR(30) NOT NULL,
            details TEXT, ratio VARCHAR(20), amount DECIMAL(10,4), source VARCHAR(40),
            UNIQUE(stock_id, ex_date, action_type)""",
        'earnings_calendar': """id SERIAL PRIMARY KEY,
            stock_id INTEGER REFERENCES stocks(id) ON DELETE CASCADE,
            results_date DATE NOT NULL, quarter VARCHAR(10), period_end DATE,
            announced_at TIMESTAMP, revenue_actual DECIMAL(16,2), pat_actual DECIMAL(16,2),
            eps_actual DECIMAL(10,4), eps_estimate DECIMAL(10,4), surprise_pct DECIMAL(8,2),
            source VARCHAR(40), UNIQUE(stock_id, results_date, quarter)""",
        'news_sentiment': """id SERIAL PRIMARY KEY,
            stock_id INTEGER REFERENCES stocks(id) ON DELETE CASCADE,
            date DATE NOT NULL, headline TEXT NOT NULL, source VARCHAR(60), url TEXT,
            sentiment VARCHAR(10), sentiment_score DECIMAL(4,2), relevance_score DECIMAL(4,2),
            summary TEXT, scored_by VARCHAR(30), UNIQUE(stock_id, date, headline)""",
        'bulk_deals': """id SERIAL PRIMARY KEY,
            stock_id INTEGER REFERENCES stocks(id) ON DELETE CASCADE,
            date DATE NOT NULL, deal_type VARCHAR(10) NOT NULL, client_name VARCHAR(200),
            transaction VARCHAR(10), quantity BIGINT, price DECIMAL(12,2), source VARCHAR(40),
            UNIQUE(stock_id, date, deal_type, client_name, transaction)""",
        'insider_trades': """id SERIAL PRIMARY KEY,
            stock_id INTEGER REFERENCES stocks(id) ON DELETE CASCADE,
            date DATE NOT NULL, person_name VARCHAR(200), person_category VARCHAR(60),
            transaction VARCHAR(10), quantity BIGINT, price DECIMAL(12,2),
            post_trade_pct DECIMAL(6,2), source VARCHAR(40),
            UNIQUE(stock_id, date, person_name, transaction, quantity)""",
        'macro_indicators': """id SERIAL PRIMARY KEY, date DATE NOT NULL,
            market VARCHAR(10) NOT NULL DEFAULT 'IN', indicator VARCHAR(60) NOT NULL,
            value DECIMAL(12,4), unit VARCHAR(20), period VARCHAR(20), source VARCHAR(40),
            UNIQUE(date, market, indicator)""",
        'whatsapp_messages': """id SERIAL PRIMARY KEY, group_name VARCHAR(200) NOT NULL,
            sender VARCHAR(200), sent_at TIMESTAMP NOT NULL, message TEXT NOT NULL,
            export_file VARCHAR(200), processed BOOLEAN DEFAULT FALSE,
            UNIQUE(group_name, sender, sent_at, message)""",
    }
    for tname, cols in tables.items():
        op.execute(f"CREATE TABLE IF NOT EXISTS {tname} ({cols})")
    for col, typ in [
        ('revenue_ttm','DECIMAL(16,2)'),('net_profit_ttm','DECIMAL(16,2)'),
        ('operating_profit_ttm','DECIMAL(16,2)'),('opm_pct','DECIMAL(8,2)'),
        ('npm_pct','DECIMAL(8,2)'),('roce_pct','DECIMAL(8,2)'),
        ('promoter_holding_pct','DECIMAL(6,2)'),('pledged_pct','DECIMAL(6,2)'),
        ('current_ratio','DECIMAL(8,2)'),('quick_ratio','DECIMAL(8,2)'),
        ('peg_ratio','DECIMAL(8,2)'),('ev_ebitda','DECIMAL(8,2)'),
        ('dividend_yield_pct','DECIMAL(6,2)'),('book_value','DECIMAL(12,2)'),
        ('face_value','DECIMAL(10,2)'),('screener_url','TEXT'),('source','VARCHAR(40)')]:
        op.execute(f"ALTER TABLE fundamentals ADD COLUMN IF NOT EXISTS {col} {typ}")
    for col, typ in [
        ('ema_12','DECIMAL(12,2)'),('ema_26','DECIMAL(12,2)'),
        ('macd','DECIMAL(12,4)'),('macd_signal','DECIMAL(12,4)'),
        ('macd_histogram','DECIMAL(12,4)'),('bollinger_upper','DECIMAL(12,2)'),
        ('bollinger_middle','DECIMAL(12,2)'),('bollinger_lower','DECIMAL(12,2)')]:
        op.execute(f"ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS {col} {typ}")

def downgrade():
    for t in ['whatsapp_messages','macro_indicators','insider_trades','bulk_deals',
              'news_sentiment','earnings_calendar','corporate_actions',
              'fii_dii_flows','data_refresh_log']:
        op.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
    op.execute("DROP INDEX IF EXISTS idx_stocks_market")
    op.execute("ALTER TABLE stocks DROP COLUMN IF EXISTS market")
