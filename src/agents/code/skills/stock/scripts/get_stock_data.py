"""
Akshare Stock Data Utilities

This module provides utility functions for retrieving basic stock information
using the akshare package. It includes functions for getting stock basic info,
real-time quotes, historical data, and simple data preparation.
"""

import akshare as ak
import pandas as pd
import numpy as np
from typing import Optional, Dict, List, Tuple
import logging
from datetime import datetime, timedelta

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_stock_basic_info(symbol: str) -> Optional[pd.DataFrame]:
    """
    Get basic information about a stock
    
    Args:
        symbol (str): Stock symbol (e.g., '000001' for Ping An Bank)
        
    Returns:
        pd.DataFrame: Basic stock information
    """
    try:
        # Get stock basic info
        stock_info = ak.stock_individual_info_em(symbol=symbol)
        logger.info(f"Successfully retrieved basic info for stock {symbol}")
        return stock_info
    except Exception as e:
        logger.error(f"Error getting basic info for stock {symbol}: {str(e)}")
        return None


def get_stock_realtime_quote(symbol: str) -> Optional[pd.DataFrame]:
    """
    Get real-time stock quote
    
    Args:
        symbol (str): Stock symbol
        
    Returns:
        pd.DataFrame: Real-time stock quote data
    """
    try:
        quote = ak.stock_zh_a_spot_em()
        # Filter for specific symbol
        filtered_quote = quote[quote['代码'] == symbol]
        if not filtered_quote.empty:
            logger.info(f"Successfully retrieved real-time quote for stock {symbol}")
            return filtered_quote
        else:
            logger.warning(f"No real-time data found for stock {symbol}")
            return None
    except Exception as e:
        logger.error(f"Error getting real-time quote for stock {symbol}: {str(e)}")
        return None


def get_stock_historical_data(symbol: str, period: str = "daily", 
                            start_date: Optional[str] = None, 
                            end_date: Optional[str] = None) -> Optional[pd.DataFrame]:
    """
    Get historical stock data
    
    Args:
        symbol (str): Stock symbol
        period (str): Data period ('daily', 'weekly', 'monthly')
        start_date (str): Start date in format 'YYYYMMDD'
        end_date (str): End date in format 'YYYYMMDD'
        
    Returns:
        pd.DataFrame: Historical stock data
    """
    try:
        if not start_date:
            start_date = (datetime.now() - timedelta(days=365)).strftime('%Y%m%d')
        if not end_date:
            end_date = datetime.now().strftime('%Y%m%d')
        
        # Get historical data
        hist_data = ak.stock_zh_a_hist(symbol=symbol, period=period, 
                                     start_date=start_date, end_date=end_date, 
                                     adjust="qfq")
        
        if not hist_data.empty:
            logger.info(f"Successfully retrieved historical data for stock {symbol}")
            return hist_data
        else:
            logger.warning(f"No historical data found for stock {symbol}")
            return None
    except Exception as e:
        logger.error(f"Error getting historical data for stock {symbol}: {str(e)}")
        return None


def get_stock_list() -> Optional[pd.DataFrame]:
    """
    Get list of all stocks
    
    Returns:
        pd.DataFrame: List of all stocks with basic information
    """
    try:
        stock_list = ak.stock_zh_a_spot_em()
        logger.info("Successfully retrieved stock list")
        return stock_list
    except Exception as e:
        logger.error(f"Error getting stock list: {str(e)}")
        return None


def search_stock_by_name(name: str) -> Optional[pd.DataFrame]:
    """
    Search stocks by name
    
    Args:
        name (str): Stock name or partial name
        
    Returns:
        pd.DataFrame: Matching stocks
    """
    try:
        stock_list = get_stock_list()
        if stock_list is not None:
            # Search by name (case insensitive)
            matching_stocks = stock_list[
                stock_list['名称'].str.contains(name, case=False, na=False)
            ]
            logger.info(f"Found {len(matching_stocks)} stocks matching '{name}'")
            return matching_stocks
        return None
    except Exception as e:
        logger.error(f"Error searching stocks by name '{name}': {str(e)}")
        return None


def prepare_stock_data_for_analysis(symbol: str, days: int = 30) -> Optional[Dict]:
    """
    Prepare stock data for basic analysis
    
    Args:
        symbol (str): Stock symbol
        days (int): Number of days of historical data to retrieve
        
    Returns:
        dict: Dictionary containing prepared data for analysis
    """
    try:
        # Get basic info
        basic_info = get_stock_basic_info(symbol)
        
        # Get real-time quote
        realtime_quote = get_stock_realtime_quote(symbol)
        
        # Get historical data
        end_date = datetime.now().strftime('%Y%m%d')
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y%m%d')
        hist_data = get_stock_historical_data(symbol, start_date=start_date, end_date=end_date)
        
        # Prepare analysis data
        analysis_data = {
            'symbol': symbol,
            'basic_info': basic_info,
            'realtime_quote': realtime_quote,
            'historical_data': hist_data,
            'prepared_at': datetime.now().isoformat()
        }
        
        # Add basic statistics if historical data is available
        if hist_data is not None and not hist_data.empty:
            analysis_data['statistics'] = {
                'price_range': {
                    'min': hist_data['最低'].min(),
                    'max': hist_data['最高'].max(),
                    'avg': hist_data['收盘'].mean()
                },
                'volume_stats': {
                    'avg_volume': hist_data['成交量'].mean(),
                    'max_volume': hist_data['成交量'].max()
                },
                'price_change': {
                    'total_change': hist_data['收盘'].iloc[-1] - hist_data['收盘'].iloc[0],
                    'percent_change': ((hist_data['收盘'].iloc[-1] - hist_data['收盘'].iloc[0]) / hist_data['收盘'].iloc[0]) * 100
                }
            }
        
        logger.info(f"Successfully prepared analysis data for stock {symbol}")
        return analysis_data
        
    except Exception as e:
        logger.error(f"Error preparing analysis data for stock {symbol}: {str(e)}")
        return None


def get_top_stocks_by_volume(limit: int = 10) -> Optional[pd.DataFrame]:
    """
    Get top stocks by trading volume
    
    Args:
        limit (int): Number of top stocks to return
        
    Returns:
        pd.DataFrame: Top stocks by volume
    """
    try:
        stock_list = get_stock_list()
        
        if stock_list is not None:
            # Sort by volume and get top stocks
            top_stocks = stock_list.nlargest(limit, '成交量')
            logger.info(f"Successfully retrieved top {limit} stocks by volume")
            return top_stocks
        return None
    except Exception as e:
        logger.error(f"Error getting top stocks by volume: {str(e)}")
        return None


def calculate_simple_moving_average(data: pd.DataFrame, window: int = 5) -> pd.Series:
    """
    Calculate simple moving average
    
    Args:
        data (pd.DataFrame): Stock data with '收盘' column
        window (int): Moving average window
        
    Returns:
        pd.Series: Simple moving average
    """
    try:
        if '收盘' in data.columns:
            sma = data['收盘'].rolling(window=window).mean()
            logger.info(f"Successfully calculated {window}-day SMA")
            return sma
        else:
            logger.error("Data does not contain '收盘' column")
            return pd.Series()
    except Exception as e:
        logger.error(f"Error calculating moving average: {str(e)}")
        return pd.Series()


# Example usage and testing functions
def example_usage():
    """Example usage of the akshare stock utilities"""
    
    print("=== Akshare Stock Utilities Example ===\n")
    
    # Example stock symbol (Ping An Bank)
    symbol = "000001"
    
    print(f"1. Getting basic info for stock {symbol}:")
    basic_info = get_stock_basic_info(symbol)
    if basic_info is not None:
        print(basic_info.head())
    print()
    
    print(f"2. Getting real-time quote for stock {symbol}:")
    realtime = get_stock_realtime_quote(symbol)
    if realtime is not None:
        print(realtime[['代码', '名称', '最新价', '涨跌幅', '成交量']].head())
    print()
    
    print(f"3. Getting historical data for stock {symbol} (last 30 days):")
    hist_data = get_stock_historical_data(symbol, start_date="20241201", end_date="20241231")
    if hist_data is not None:
        print(hist_data[['日期', '开盘', '收盘', '最高', '最低', '成交量']].head())
    print()
    
    print("4. Searching stocks by name '平安':")
    search_results = search_stock_by_name("平安")
    if search_results is not None:
        print(search_results[['代码', '名称', '最新价']].head())
    print()
    
    print("5. Getting top 5 stocks by volume:")
    top_stocks = get_top_stocks_by_volume(5)
    if top_stocks is not None:
        print(top_stocks[['代码', '名称', '最新价', '成交量']].head())
    print()
    
    print("6. Preparing analysis data:")
    analysis_data = prepare_stock_data_for_analysis(symbol, days=30)
    if analysis_data is not None and 'statistics' in analysis_data:
        print("Statistics:")
        print(f"  Price range: {analysis_data['statistics']['price_range']}")
        print(f"  Volume stats: {analysis_data['statistics']['volume_stats']}")
        print(f"  Price change: {analysis_data['statistics']['price_change']}")


if __name__ == "__main__":
    example_usage()
