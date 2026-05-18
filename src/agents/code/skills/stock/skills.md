# Stock Skills Documentation

This document describes all available functions in `stock/scripts/get_stock_data.py` and `stock/scripts/analyze.py`.

## Functions in get_stock_data.py

### `get_stock_basic_info(symbol: str) -> Optional[pd.DataFrame]`
Get basic information about a stock.

**Parameters:**
- `symbol` (str): Stock symbol (e.g., '000001' for Ping An Bank)

**Returns:**
- `Optional[pd.DataFrame]`: Basic stock information, or None if error occurs

---

### `get_stock_realtime_quote(symbol: str) -> Optional[pd.DataFrame]`
Get real-time stock quote.

**Parameters:**
- `symbol` (str): Stock symbol

**Returns:**
- `Optional[pd.DataFrame]`: Real-time stock quote data, or None if error occurs

---

### `get_stock_historical_data(symbol: str, period: str = "daily", start_date: Optional[str] = None, end_date: Optional[str] = None) -> Optional[pd.DataFrame]`
Get historical stock data.

**Parameters:**
- `symbol` (str): Stock symbol
- `period` (str): Data period ('daily', 'weekly', 'monthly'). Default is "daily"
- `start_date` (Optional[str]): Start date in format 'YYYYMMDD'. Default is 365 days ago
- `end_date` (Optional[str]): End date in format 'YYYYMMDD'. Default is today

**Returns:**
- `Optional[pd.DataFrame]`: Historical stock data with columns: 日期, 开盘, 收盘, 最高, 最低, 成交量, or None if error occurs

---

### `get_stock_list() -> Optional[pd.DataFrame]`
Get list of all stocks.

**Returns:**
- `Optional[pd.DataFrame]`: List of all stocks with basic information, or None if error occurs

---

### `search_stock_by_name(name: str) -> Optional[pd.DataFrame]`
Search stocks by name.

**Parameters:**
- `name` (str): Stock name or partial name (case insensitive)

**Returns:**
- `Optional[pd.DataFrame]`: Matching stocks, or None if error occurs

---

### `prepare_stock_data_for_analysis(symbol: str, days: int = 30) -> Optional[Dict]`
Prepare stock data for basic analysis.

**Parameters:**
- `symbol` (str): Stock symbol
- `days` (int): Number of days of historical data to retrieve. Default is 30

**Returns:**
- `Optional[Dict]`: Dictionary containing:
  - `symbol`: Stock symbol
  - `basic_info`: Basic stock information
  - `realtime_quote`: Real-time quote data
  - `historical_data`: Historical data DataFrame
  - `prepared_at`: Timestamp when data was prepared
  - `statistics`: Basic statistics (if historical data available)
    - `price_range`: min, max, avg prices
    - `volume_stats`: avg_volume, max_volume
    - `price_change`: total_change, percent_change
  Or None if error occurs

---

### `get_top_stocks_by_volume(limit: int = 10) -> Optional[pd.DataFrame]`
Get top stocks by trading volume.

**Parameters:**
- `limit` (int): Number of top stocks to return. Default is 10

**Returns:**
- `Optional[pd.DataFrame]`: Top stocks by volume, or None if error occurs

---

### `calculate_simple_moving_average(data: pd.DataFrame, window: int = 5) -> pd.Series`
Calculate simple moving average.

**Parameters:**
- `data` (pd.DataFrame): Stock data with '收盘' (close) column
- `window` (int): Moving average window. Default is 5

**Returns:**
- `pd.Series`: Simple moving average values, or empty Series if error occurs

---

## Functions in analyze.py

### `analyze_price_trend(historical_data: pd.DataFrame) -> Dict`
Analyze price trend from historical stock data.

**Parameters:**
- `historical_data` (pd.DataFrame): Historical stock data with columns:
  - 日期 (date)
  - 开盘 (open)
  - 收盘 (close)
  - 最高 (high)
  - 最低 (low)
  - 成交量 (volume)

**Returns:**
- `Dict`: Analysis results containing:
  - `price_change_pct`: Percentage change from first to last close price
  - `avg_price`: Average closing price
  - `price_volatility`: Standard deviation of closing prices
  - `max_price`: Maximum closing price
  - `min_price`: Minimum closing price
  - `price_range`: Price range (max - min)
  - `trend`: 'up' if price increased >2%, 'down' if decreased <-2%, 'stable' otherwise
  - `first_price`: First closing price
  - `last_price`: Last closing price
  Or `{"error": str}` if error occurs

---

### `analyze_volume_pattern(historical_data: pd.DataFrame) -> Dict`
Analyze trading volume patterns from historical stock data.

**Parameters:**
- `historical_data` (pd.DataFrame): Historical stock data with columns:
  - 日期 (date)
  - 开盘 (open)
  - 收盘 (close)
  - 最高 (high)
  - 最低 (low)
  - 成交量 (volume)

**Returns:**
- `Dict`: Analysis results containing:
  - `avg_volume`: Average trading volume
  - `max_volume`: Maximum trading volume
  - `min_volume`: Minimum trading volume
  - `volume_volatility`: Standard deviation of volumes
  - `recent_volume_avg`: Average volume of last 5 days
  - `volume_trend`: 'increasing', 'decreasing', or 'stable'
  - `high_volume_days`: Number of days with volume above average
  - `total_days`: Total number of days in data
  - `volume_change_pct`: Percentage change in volume between first and second half
  Or `{"error": str}` if error occurs

