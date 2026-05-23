from __future__ import annotations

import argparse
from pathlib import Path

from app.real_data import fetch_real_market_frame, write_real_market_csv


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch real index and fund NAV data into a UTF-8 CSV file.")
    parser.add_argument("--start-date", default="2020-01-01")
    parser.add_argument("--output", default=str(Path(__file__).resolve().parents[1] / "data" / "real_market.csv"))
    args = parser.parse_args()

    frame = fetch_real_market_frame(start_date=args.start_date)
    write_real_market_csv(args.output, frame)
    print(f"wrote {len(frame)} rows to {args.output}")
    print(f"date range: {frame['date'].min()} -> {frame['date'].max()}")
    print(frame.groupby("sector").size().to_string())


if __name__ == "__main__":
    main()
