# File: api/index.py

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import yfinance as yf
import requests
from bs4 import BeautifulSoup
from difflib import get_close_matches
from urllib.parse import unquote

# ----------------------------
# Initialize FastAPI App
# ----------------------------
app = FastAPI(
    title="Excellent Mirror - Advanced Stock Analysis API",
    description="An API to fetch financial data and categorized news for a single company.",
    version="2.0.0"
)

# Add CORS middleware to allow cross-origin requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
        
        names = [q.get('longname') or q.get('shortname', '') for q in quotes]
        best_match_name = get_close_matches(company_name, names, n=1, cutoff=0.6)
        
        if not best_match_name:
            return quotes[0].get('symbol')

        for quote in quotes:
            if (quote.get('longname') or quote.get('shortname')) == best_match_name[0]:
                return quote.get('symbol')
        
        return quotes[0].get('symbol')
        
    except requests.exceptions.RequestException as e:
        print(f"Error fetching ticker for {company_name}: {e}")
        return None

def get_stock_data(ticker: str):
    """Fetches comprehensive stock data from yfinance for the last month."""
    stock = yf.Ticker(ticker)
    try:
        info = stock.info
        if not info or info.get('trailingPE') is None:
             return None
             
        # MODIFIED: Changed period from "1y" to "1mo"
        hist = stock.history(period="1mo") 
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

def web_search(query: str, num_results: int = 5):
    """
    NEW: Performs a web search using DuckDuckGo and returns structured results.
    """
    url = f"https://duckduckgo.com/html/?q={query}"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        res = requests.get(url, headers=headers, timeout=10)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "html.parser")

        results = []
        for result in soup.select('.result')[:num_results]:
            title_tag = result.select_one('.result__a')
            link_tag = result.select_one('.result__a')
            snippet_tag = result.select_one('.result__snippet')

            if not (title_tag and link_tag and snippet_tag):
                continue
                
            title = title_tag.get_text()
            # Clean up the DDG redirect link
            raw_link = link_tag['href']
            cleaned_link = unquote(raw_link.split('/l/?uddg=')[-1].split('&rut=')[0])
            snippet = snippet_tag.get_text()
            
            results.append({"title": title, "link": cleaned_link, "snippet": snippet})
        
        return results
    except requests.exceptions.RequestException as e:
        print(f"Error performing web search for '{query}': {e}")
        return []

# ----------------------------
# API Endpoint
# ----------------------------

@app.get("/api/analyze", tags=["Stock Analysis"])
def analyze_company(company_name: str = Query(..., description="The name of the company to analyze.")):
    """
    Provides a full financial analysis for a single company by its name, 
    including categorized news from a web search.
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

    # 3. Get official company name for better search results
    official_name = stock_data.get('company_name', company_name)

    # 4. Perform categorized news searches
    news_analysis = {
        "company_news": web_search(f"news about {official_name}"),
        "financial_news": web_search(f"{official_name} financial news OR earnings"),
        "investor_relations": web_search(f"investors of {official_name} OR shareholder updates"),
        "market_outlook": web_search(f"{official_name} market analysis and future outlook")
    }

    # 5. Combine and return the results
    response_data = {
        "query": company_name,
        "financial_data": stock_data,
        "news_analysis": news_analysis
    }
    
    return JSONResponse(content=response_data)

# Health check endpoint for Vercel
@app.get("/api/health", tags=["Health Check"])
def health_check():
    return {"status": "ok"}
