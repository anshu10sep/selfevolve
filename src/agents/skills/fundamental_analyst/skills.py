import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

def evaluate_company_news(company_ticker: str, news_articles: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Evaluates recent news articles for a specific company to determine fundamental impact.
    
    Args:
        company_ticker (str): The stock ticker symbol of the company.
        news_articles (List[Dict[str, Any]]): A list of dictionaries containing news data 
                                              (e.g., 'title', 'content', 'date', 'source').
                                              
    Returns:
        Dict[str, Any]: A dictionary containing the sentiment score, key themes, and overall impact.
    """
    logger.info(f"Evaluating company news for {company_ticker}. Total articles: {len(news_articles)}")
    
    # Placeholder for actual NLP/Sentiment analysis logic
    positive_keywords = ['growth', 'profit', 'beat', 'upgrade', 'dividend', 'acquisition', 'expansion', 'record']
    negative_keywords = ['loss', 'miss', 'downgrade', 'lawsuit', 'debt', 'bankruptcy', 'layoffs', 'decline']
    
    sentiment_score = 0
    key_themes = set()
    
    for article in news_articles:
        content = str(article.get('content', '')).lower()
        title = str(article.get('title', '')).lower()
        full_text = f"{title} {content}"
        
        for word in positive_keywords:
            if word in full_text:
                sentiment_score += 1
                key_themes.add(word)
                
        for word in negative_keywords:
            if word in full_text:
                sentiment_score -= 1
                key_themes.add(word)
                
    impact = "Neutral"
    if sentiment_score > 2:
        impact = "Positive"
    elif sentiment_score < -2:
        impact = "Negative"
        
    return {
        "ticker": company_ticker,
        "sentiment_score": sentiment_score,
        "impact": impact,
        "key_themes": list(key_themes),
        "articles_analyzed": len(news_articles)
    }

def analyze_financial_statements(company_ticker: str, income_statement: Dict[str, Any], 
                                 balance_sheet: Dict[str, Any], cash_flow: Dict[str, Any]) -> Dict[str, Any]:
    """
    Analyzes a company's financial statements to assess its financial health and valuation.
    
    Args:
        company_ticker (str): The stock ticker symbol of the company.
        income_statement (Dict[str, Any]): Data from the income statement (e.g., revenue, net_income).
        balance_sheet (Dict[str, Any]): Data from the balance sheet (e.g., total_assets, total_liabilities, equity).
        cash_flow (Dict[str, Any]): Data from the cash flow statement (e.g., operating_cash_flow).
        
    Returns:
        Dict[str, Any]: A dictionary containing calculated financial ratios, health score, and valuation metrics.
    """
    logger.info(f"Analyzing financial statements for {company_ticker}")
    
    # Extract basic metrics with defaults
    revenue = income_statement.get('revenue', 0)
    net_income = income_statement.get('net_income', 0)
    
    total_assets = balance_sheet.get('total_assets', 0)
    total_liabilities = balance_sheet.get('total_liabilities', 0)
    equity = balance_sheet.get('equity', 0)
    
    operating_cash_flow = cash_flow.get('operating_cash_flow', 0)
    
    # Calculate Ratios
    profit_margin = (net_income / revenue) if revenue else 0
    debt_to_equity = (total_liabilities / equity) if equity else 0
    return_on_assets = (net_income / total_assets) if total_assets else 0
    return_on_equity = (net_income / equity) if equity else 0
    
    # Determine Health Score (0 to 100)
    health_score = 50
    if profit_margin > 0.15:
        health_score += 15
    elif profit_margin < 0:
        health_score -= 20
        
    if debt_to_equity < 1.0:
        health_score += 15
    elif debt_to_equity > 2.0:
        health_score -= 15
        
    if operating_cash_flow > net_income:
        health_score += 10
        
    if return_on_equity > 0.15:
        health_score += 10
        
    health_score = max(0, min(100, health_score))
    
    return {
        "ticker": company_ticker,
        "ratios": {
            "profit_margin": round(profit_margin, 4),
            "debt_to_equity": round(debt_to_equity, 4),
            "return_on_assets": round(return_on_assets, 4),
            "return_on_equity": round(return_on_equity, 4)
        },
        "health_score": health_score,
        "is_healthy": health_score >= 60
    }

def assess_economic_indicators(indicators: Dict[str, Any]) -> Dict[str, Any]:
    """
    Assesses macroeconomic indicators to determine the broader economic environment's impact on markets.
    
    Args:
        indicators (Dict[str, Any]): A dictionary of economic indicators 
                                     (e.g., 'gdp_growth', 'inflation_rate', 'unemployment_rate', 'interest_rate').
        
    Returns:
        Dict[str, Any]: A dictionary containing the economic outlook, risk level, and sector recommendations.
    """
    logger.info("Assessing macroeconomic indicators")
    
    gdp_growth = indicators.get('gdp_growth', 0.0)
    inflation_rate = indicators.get('inflation_rate', 0.0)
    unemployment_rate = indicators.get('unemployment_rate', 0.0)
    interest_rate = indicators.get('interest_rate', 0.0)
    
    outlook = "Neutral"
    risk_level = "Medium"
    recommended_sectors = []
    
    # Basic logic for economic assessment
    if gdp_growth > 2.5 and inflation_rate < 3.0 and unemployment_rate < 5.0:
        outlook = "Expansionary"
        risk_level = "Low"
        recommended_sectors = ["Technology", "Consumer Discretionary", "Industrials"]
    elif gdp_growth < 1.0 or inflation_rate > 5.0 or unemployment_rate > 6.0:
        outlook = "Contractionary"
        risk_level = "High"
        recommended_sectors = ["Utilities", "Consumer Staples", "Healthcare"]
    else:
        outlook = "Stable"
        risk_level = "Medium"
        recommended_sectors = ["Financials", "Materials", "Energy"]
        
    # Interest rate impact
    if interest_rate > 4.0:
        if "Financials" not in recommended_sectors:
            recommended_sectors.append("Financials")
            
    return {
        "outlook": outlook,
        "risk_level": risk_level,
        "recommended_sectors": recommended_sectors,
        "indicators_analyzed": {
            "gdp_growth": gdp_growth,
            "inflation_rate": inflation_rate,
            "unemployment_rate": unemployment_rate,
            "interest_rate": interest_rate
        }
    }
