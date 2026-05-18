from prophet import Prophet
import pandas as pd
import akshare as ak


def prophet_predict(df, periods=10):
    """
    Predict future stock prices using Facebook Prophet.
    
    Args:
        df (pd.DataFrame): DataFrame with columns ['日期', '收盘']
        periods (int): Number of days to forecast
        
    Returns:
        pd.DataFrame: DataFrame with forecast results
    """
    
    # Prepare data for Prophet
    prophet_df = df.rename(columns={"日期": "ds", "收盘": "y"})
    
    # Initialize and fit the model
    model = Prophet(daily_seasonality=True)
    model.fit(prophet_df)
    
    # Create future dataframe for prediction
    future = model.make_future_dataframe(periods=periods)
    future = future.tail(periods) 

    # Make predictions
    forecast = model.predict(future)
    
    # Return the forecast dataframe with selected columns
    result = forecast[['ds', 'yhat', 'yhat_lower', 'yhat_upper']]
    result = result.rename(columns={"ds": "日期", "yhat": "预测值", 
                                   "yhat_lower": "预测下限", "yhat_upper": "预测上限"})
    
    return df,result

def get_stock_data(stock_code: str, days: int = 180):
    try:
        current_date = pd.Timestamp.now().strftime('%Y%m%d')
        start_date = (pd.Timestamp(current_date) - pd.Timedelta(days=days)).strftime('%Y%m%d')

        df = ak.stock_zh_a_hist(symbol=stock_code, period="daily", start_date=start_date, end_date=current_date, adjust="")
        df["日期"] = pd.to_datetime(df["日期"])
        return df[["日期", "收盘"]]
    except Exception as e:
        print(f"Error fetching data: {e}")
        return pd.DataFrame()

def predict(stock_code: str, days: int = 180, periods: int = 5):
    df = get_stock_data(stock_code, days)
    return prophet_predict(df, periods)

if __name__ == "__main__":

    stock_code = "300750"
    df = get_stock_data(stock_code)
    print(df)
    
    df,forecast = prophet_predict(df)
    print(forecast)
    
    # stock_data = ak.stock_zh_a_daily(symbol="300750", start_date="2024-04-23", end_date="2025-04-23")
