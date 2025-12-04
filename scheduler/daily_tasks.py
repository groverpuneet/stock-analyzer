from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_collectors.collect_watchlist_data import collect_data
from analysis.calculate_indicators import process_all_watchlist_stocks

def daily_data_collection():
    print("\n" + "="*60)
    print(f"DAILY DATA COLLECTION - {datetime.now()}")
    print("="*60)
    
    try:
        collect_data(watchlist_name='Default', days=5, include_quotes=True)
        print("✓ Data collection successful")
    except Exception as e:
        print(f"✗ Data collection failed: {e}")

def daily_indicator_calculation():
    print("\n" + "="*60)
    print(f"INDICATOR CALCULATION - {datetime.now()}")
    print("="*60)
    
    try:
        process_all_watchlist_stocks()
        print("✓ Indicator calculation successful")
    except Exception as e:
        print(f"✗ Indicator calculation failed: {e}")

def test_tasks():
    print("\nTESTING SCHEDULED TASKS")
    print("="*60)
    
    daily_data_collection()
    daily_indicator_calculation()
    
    print("\n" + "="*60)
    print("✓ Test complete!")

def start_scheduler():
    scheduler = BlockingScheduler()
    
    scheduler.add_job(
        daily_data_collection,
        CronTrigger(hour=16, minute=0, timezone='Asia/Kolkata'),
        id='daily_data_collection',
        name='Collect daily stock data',
        replace_existing=True
    )
    
    scheduler.add_job(
        daily_indicator_calculation,
        CronTrigger(hour=16, minute=15, timezone='Asia/Kolkata'),
        id='daily_indicator_calculation',
        name='Calculate technical indicators',
        replace_existing=True
    )
    
    print("\n" + "="*60)
    print("SCHEDULER STARTED")
    print("="*60)
    print("\nScheduled tasks:")
    print("  - Data collection: Daily at 4:00 PM IST")
    print("  - Indicator calculation: Daily at 4:15 PM IST")
    print("\nPress Ctrl+C to stop")
    print("="*60 + "\n")
    
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("\n\nScheduler stopped")

if __name__ == "__main__":
    if '--test' in sys.argv:
        test_tasks()
    else:
        start_scheduler()
