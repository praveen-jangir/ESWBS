# File: api/index.py

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import yfinance as yf
import requests
from bs4 import BeautifulSoup
from difflib import get_close_matches

# ----------------------------
# Initialize FastAPI App
# ----------------------------
app = FastAPI(
    title="Excellent Mirror - Stock Analysis API",
    description="An API to fetch financial data and news for a single company.",
    version="1.0.0"
)

# Add CORS middleware to allow cross-origin requests (e.g., from your frontend)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# ----------------------------
# Helper Functions
# ----------------------------

def search_ticker(company_name: str):
    """Searches for the most relevant stock ticker for a given company name."""
    url = f"https://query2.finance.yahoo.com/v1/finance/search?q={company_name}"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        res = requests.get(url, headers=headers, timeout=10)
        res.raise_for_status()
        data = res.json()
        quotes = data.get('quotes', [])
        if not quotes:
            return None
        
        # Find the best match using difflib
        names = [q.get('longname') or q.get('shortname', '') for q in quotes]
        best_match_name = get_close_matches(company_name, names, n=1, cutoff=0.6)
        
        if not best_match_name:
            # If no good match, default to the first result
            return quotes[0].get('symbol')

        for quote in quotes:
            if (quote.get('longname') or quote.get('shortname')) == best_match_name[0]:
                return quote.get('symbol')
        
        return quotes[0].get('symbol') # Fallback to first symbol
        
    except requests.exceptions.RequestException as e:
        print(f"Error fetching ticker for {company_name}: {e}")
        return None

def get_stock_data(ticker: str):
    """Fetches comprehensive stock data from yfinance."""
    stock = yf.Ticker(ticker)
    try:
        info = stock.info
        if not info or info.get('trailingPE') is None: # Check if info is empty
             return None
             
        hist = stock.history(period="1y")
        hist_data = [
            {"date": str(index.date()), "close": round(row['Close'], 2)}
            for index, row in hist.iterrows()
        ]

        return {
            "ticker": ticker,
            "company_name": info.get('longName', 'N/A'),
            "exchange": info.get('exchange', 'N/A'),
            "sector": info.get('sector', 'N/A'),
            "industry": info.get('industry', 'N/A'),
            "summary": info.get('longBusinessSummary', 'N/A'),
            "current_price": info.get('currentPrice'),
            "market_cap": info.get('marketCap'),
            "fifty_two_week_range": f"{info.get('fiftyTwoWeekLow')} - {info.get('fiftyTwoWeekHigh')}",
            "pe_ratio": info.get('trailingPE'),
            "eps": info.get('trailingEps'),
            "dividend_yield": info.get('dividendYield'),
            "recommendation": info.get('recommendationKey', 'N/A').replace('_', ' ').title(),
            "target_mean_price": info.get('targetMeanPrice'),
            "historical_prices": hist_data,
        }
    except Exception as e:
        print(f"Error fetching data for ticker {ticker}: {e}")
        return None

def get_news(company_name: str, num_articles: int = 5):
    """Scrapes top news articles from Google News."""
    headers = {"User-Agent": "Mozilla/5.0"}
    url = f"https://news.google.com/search?q={company_name.replace(' ', '%20')}&hl=en-IN&gl=IN"
    try:
        res = requests.get(url, headers=headers, timeout=10)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "html.parser")
        articles = soup.select('article')[:num_articles]
        
        news_results = []
        for a in articles:
            title_tag = a.select_one('h3')
            link_tag = a.select_one('a')
            source_tag = a.select_one('div[data-n-tid]')
            
            if title_tag and link_tag and source_tag:
                title = title_tag.get_text()
                link = "https://news.google.com" + link_tag['href'][1:]
                source = source_tag.get_text()
                news_results.append({"title": title, "link": link, "source": source})
        return news_results
    except requests.exceptions.RequestException as e:
        print(f"Error fetching news for {company_name}: {e}")
        return []

# ----------------------------
# API Endpoint
# ----------------------------

@app.get("/api/analyze", tags=["Stock Analysis"])
def analyze_company(company_name: str = Query(..., description="The name of the company to analyze.")):
    """
    Provides a full financial analysis for a single company by its name.
    """
    if not company_name:
        raise HTTPException(status_code=400, detail="Company name cannot be empty.")

    # 1. Find the best ticker symbol
    ticker = search_ticker(company_name)
    if not ticker:
        raise HTTPException(status_code=404, detail=f"Could not find a stock ticker for '{company_name}'.")

    # 2. Get stock financial data
    stock_data = get_stock_data(ticker)
    if not stock_data:
        raise HTTPException(status_code=404, detail=f"Could not retrieve financial data for ticker '{ticker}'. The company might be delisted or data is unavailable.")

    # 3. Get recent news
    news = get_news(stock_data.get('company_name', company_name))

    # 4. Combine and return the results
    response_data = {
        "query": company_name,
        "financial_data": stock_data,
        "recent_news": news
    }
    
    return JSONResponse(content=response_data)

# Health check endpoint for Vercel
@app.get("/api/health", tags=["Health Check"])
def health_check():
    return {"status": "ok"}
