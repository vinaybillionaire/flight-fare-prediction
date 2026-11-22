"""
Live Database Viewer & Evaluator Audit Utility
Run while the website is active to demonstrate live database operations for 5 Marks.

Usage:
    python view_database.py          (Displays latest records)
    python view_database.py --watch  (Live continuous monitor - updates as website is clicked)
"""

import os
import sys
import time

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from database.db import fetch_recent_predictions, get_database_status, SessionLocal, FlightPredictionRecord

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def render_table(limit=15):
    db_info = get_database_status()
    session = SessionLocal()
    total_count = session.query(FlightPredictionRecord).count()
    session.close()

    records = fetch_recent_predictions(limit=limit)

    print("=" * 105)
    print("                      AEROPRICE - LIVE DATABASE RECORD AUDITOR (5 MARKS DELIVERABLE)")
    print("=" * 105)
    print(f" Engine Status  : {db_info['status'].upper()}")
    print(f" Active Database: {db_info['db_type']}")
    print(f" Total Logged   : {total_count} transactions recorded")
    print(f" Current Time   : {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("-" * 105)
    
    header = f"{'ID':<6} | {'TIME':<19} | {'AIRLINE':<16} | {'ROUTE':<22} | {'STOPS':<8} | {'DURATION':<9} | {'PREDICTED FARE':<15}"
    print(header)
    print("-" * 105)

    if not records:
        print(" [No prediction records found yet. Submit a flight search on http://127.0.0.1:8000]")
    else:
        for r in records:
            dur = f"{r['duration_mins']//60}h {r['duration_mins']%60}m"
            stops = "Direct" if r['total_stops'] == 0 else f"{r['total_stops']} stop"
            route = f"{r['source']} -> {r['destination']}"
            fare = f"Rs. {r['predicted_fare']:,.2f}"
            print(f"#{r['id']:<5} | {r['timestamp']:<19} | {r['airline'][:15]:<16} | {route:<22} | {stops:<8} | {dur:<9} | {fare:<15}")

    print("=" * 105)

if __name__ == "__main__":
    is_watch = "--watch" in sys.argv
    if is_watch:
        print("Starting Live Watch Mode... Press CTRL+C to exit.\n")
        try:
            while True:
                clear_screen()
                render_table(limit=15)
                print("\n[*] Live Watch Mode Active: Submit queries on the website to see them appear here instantly.")
                time.sleep(2)
        except KeyboardInterrupt:
            print("\nExiting live watch.")
    else:
        render_table(limit=15)
        print("\nTip: Run 'python view_database.py --watch' for a live auto-updating monitor during viva.")
