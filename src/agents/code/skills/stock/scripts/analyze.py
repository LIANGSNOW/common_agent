"""
Stock Analysis Utilities

This module provides analysis functions for stock historical data
returned by get_stock_historical_data function.
"""

import pandas as pd
import numpy as np
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)


def analyze_price_trend(historical_data: pd.DataFrame) -> Dict:
    """
    Analyze price trend from historical stock data.
    
    This function calculates price changes, volatility, and trend indicators
    based on the historical data returned by get_stock_historical_data.
    
    Args:
        historical_data (pd.DataFrame): Historical stock data with columns:
            - 日期 (date)
            - 开盘 (open)
            - 收盘 (close)
            - 最高 (high)
            - 最低 (low)
            - 成交量 (volume)
    
    Returns:
        dict: Analysis results containing:
            - price_change_pct: Percentage change from first to last close price
            - avg_price: Average closing price
            - price_volatility: Standard deviation of closing prices
            - max_price: Maximum closing price
            - min_price: Minimum closing price
            - price_range: Price range (max - min)
            - trend: 'up' if price increased, 'down' if decreased, 'stable' otherwise
    """
    try:
        if historical_data is None or historical_data.empty:
            logger.warning("Empty or None historical data provided")
            return {"error": "No data provided"}
        
        # Ensure we have the required columns
        required_columns = ['收盘', '最高', '最低']
        if not all(col in historical_data.columns for col in required_columns):
            logger.error(f"Missing required columns. Available: {historical_data.columns.tolist()}")
            return {"error": "Missing required columns"}
        
        # Calculate price metrics
        close_prices = historical_data['收盘']
        first_price = close_prices.iloc[0]
        last_price = close_prices.iloc[-1]
        
        price_change_pct = ((last_price - first_price) / first_price) * 100
        avg_price = close_prices.mean()
        price_volatility = close_prices.std()
        max_price = close_prices.max()
        min_price = close_prices.min()
        price_range = max_price - min_price
        
        # Determine trend
        if price_change_pct > 2:
            trend = "up"
        elif price_change_pct < -2:
            trend = "down"
        else:
            trend = "stable"
        
        result = {
            "price_change_pct": round(price_change_pct, 2),
            "avg_price": round(avg_price, 2),
            "price_volatility": round(price_volatility, 2),
            "max_price": round(max_price, 2),
            "min_price": round(min_price, 2),
            "price_range": round(price_range, 2),
            "trend": trend,
            "first_price": round(first_price, 2),
            "last_price": round(last_price, 2)
        }
        
        logger.info(f"Price trend analysis completed. Trend: {trend}, Change: {price_change_pct:.2f}%")
        return result
        
    except Exception as e:
        logger.error(f"Error analyzing price trend: {str(e)}")
        return {"error": str(e)}


def analyze_volume_pattern(historical_data: pd.DataFrame) -> Dict:
    """
    Analyze trading volume patterns from historical stock data.
    
    This function calculates volume statistics and identifies volume trends
    based on the historical data returned by get_stock_historical_data.
    
    Args:
        historical_data (pd.DataFrame): Historical stock data with columns:
            - 日期 (date)
            - 开盘 (open)
            - 收盘 (close)
            - 最高 (high)
            - 最低 (low)
            - 成交量 (volume)
    
    Returns:
        dict: Analysis results containing:
            - avg_volume: Average trading volume
            - max_volume: Maximum trading volume
            - min_volume: Minimum trading volume
            - volume_volatility: Standard deviation of volumes
            - recent_volume_avg: Average volume of last 5 days
            - volume_trend: 'increasing', 'decreasing', or 'stable'
            - high_volume_days: Number of days with volume above average
    """
    try:
        if historical_data is None or historical_data.empty:
            logger.warning("Empty or None historical data provided")
            return {"error": "No data provided"}
        
        # Ensure we have the volume column
        if '成交量' not in historical_data.columns:
            logger.error(f"Missing '成交量' column. Available: {historical_data.columns.tolist()}")
            return {"error": "Missing '成交量' column"}
        
        volumes = historical_data['成交量']
        avg_volume = volumes.mean()
        max_volume = volumes.max()
        min_volume = volumes.min()
        volume_volatility = volumes.std()
        
        # Calculate recent volume (last 5 days or all if less than 5)
        recent_days = min(5, len(volumes))
        recent_volume_avg = volumes.tail(recent_days).mean()
        
        # Determine volume trend by comparing first half vs second half
        mid_point = len(volumes) // 2
        first_half_avg = volumes.iloc[:mid_point].mean() if mid_point > 0 else avg_volume
        second_half_avg = volumes.iloc[mid_point:].mean() if mid_point < len(volumes) else avg_volume
        
        volume_change_pct = ((second_half_avg - first_half_avg) / first_half_avg) * 100 if first_half_avg > 0 else 0
        
        if volume_change_pct > 10:
            volume_trend = "increasing"
        elif volume_change_pct < -10:
            volume_trend = "decreasing"
        else:
            volume_trend = "stable"
        
        # Count high volume days (above average)
        high_volume_days = (volumes > avg_volume).sum()
        
        result = {
            "avg_volume": round(avg_volume, 2),
            "max_volume": round(max_volume, 2),
            "min_volume": round(min_volume, 2),
            "volume_volatility": round(volume_volatility, 2),
            "recent_volume_avg": round(recent_volume_avg, 2),
            "volume_trend": volume_trend,
            "high_volume_days": int(high_volume_days),
            "total_days": len(volumes),
            "volume_change_pct": round(volume_change_pct, 2)
        }
        
        logger.info(f"Volume pattern analysis completed. Trend: {volume_trend}")
        return result
        
    except Exception as e:
        logger.error(f"Error analyzing volume pattern: {str(e)}")
        return {"error": str(e)}

