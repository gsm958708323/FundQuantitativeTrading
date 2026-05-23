import pandas as pd

from app.real_data import build_sector_frame


def test_build_sector_frame_aligns_index_nav_and_price_percentile():
    index = pd.DataFrame(
        {
            "date": ["2024-01-01", "2024-01-02", "2024-01-03"],
            "close": [100.0, 110.0, 105.0],
        }
    )
    nav = pd.DataFrame(
        {
            "净值日期": ["2024-01-01", "2024-01-02", "2024-01-03"],
            "单位净值": [1.0, 1.1, 1.05],
        }
    )

    result = build_sector_frame(
        sector="科技",
        index_frame=index,
        nav_frame=nav,
        fund_start_date="2024-01-01",
        valuation_metric="PRICE_PERCENTILE",
    )

    assert result.columns.tolist() == [
        "date",
        "sector",
        "index_price",
        "fund_nav",
        "valuation_percentile",
        "attention_rank_pct",
        "fund_start_date",
        "valuation_metric",
    ]
    assert result["valuation_percentile"].between(0, 100).all()
    assert result.iloc[-1]["fund_nav"] == 1.05


def test_build_sector_frame_uses_real_pe_pb_ps_valuation_when_available():
    index = pd.DataFrame(
        {
            "date": ["2024-01-01", "2024-01-02", "2024-01-03"],
            "close": [100.0, 110.0, 105.0],
        }
    )
    nav = pd.DataFrame(
        {
            "净值日期": ["2024-01-01", "2024-01-02", "2024-01-03"],
            "单位净值": [1.0, 1.1, 1.05],
        }
    )
    valuation = pd.DataFrame(
        {
            "日期": ["2024-01-01", "2024-01-02", "2024-01-03"],
            "市净率": [2.0, 3.0, 1.0],
        }
    )

    result = build_sector_frame(
        sector="半导体",
        index_frame=index,
        nav_frame=nav,
        fund_start_date="2024-01-01",
        valuation_metric="PB",
        valuation_frame=valuation,
    )

    assert result["valuation_metric"].unique().tolist() == ["PB"]
    assert result["valuation_percentile"].tolist() == [100.0, 100.0, 33.33]
