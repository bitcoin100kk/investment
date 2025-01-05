
import streamlit as st
import pandas as pd
import yfinance as yf

# Function to calculate the yearly balances with withdrawals and percentage changes
def calculate_balances(initial_investment, withdrawal_rate, annual_returns, dividend_yields, reinvest_dividends):
    balance = initial_investment
    balances = []
    withdrawals = []
    percentage_changes = []
    dividend_yields_usd = []
    total_withdrawals_and_dividends = []

    for i in range(len(annual_returns)):
        # Calculate dividend yield in USD
        dividend_yield_usd = balance * (dividend_yields[i] / 100)
        dividend_yields_usd.append(dividend_yield_usd)
        
        # Calculate withdrawals
        withdrawal = balance * (withdrawal_rate / 100) if i > 0 else 0
        withdrawals.append(withdrawal)
        
        # Adjust balance for withdrawals and (optionally) reinvest dividends
        total_withdrawal_and_dividend = withdrawal + (0 if reinvest_dividends else dividend_yield_usd)
        balance -= total_withdrawal_and_dividend
        
        if reinvest_dividends:
            balance += dividend_yield_usd

        # Store total withdrawals and dividends as a separate entity for clarity
        total_withdrawals_and_dividends.append(total_withdrawal_and_dividend)
        
        # Update balance with annual returns
        prev_balance = balance
        balance *= (1 + annual_returns[i] / 100)
        balances.append(balance)
        
        # Calculate percentage change
        percentage_change = ((balance - prev_balance) / prev_balance) * 100 if prev_balance != 0 else 0
        percentage_changes.append(percentage_change)
    
    return balances, withdrawals, percentage_changes, dividend_yields_usd, total_withdrawals_and_dividends

# Function to get historical annual returns and dividend yields for stocks
def get_annual_returns(ticker):
    data = yf.Ticker(ticker)
    hist = data.history(period="max")
    hist.index = pd.to_datetime(hist.index)
    hist['Year'] = hist.index.year
    annual_returns = hist['Close'].resample('Y').ffill().pct_change() * 100
    dividend_yields = hist['Dividends'].resample('Y').sum() / hist['Close'].resample('Y').ffill() * 100
    return annual_returns.dropna(), dividend_yields.dropna(), annual_returns.index.year.dropna().unique().tolist()

# Function to get historical annual returns for crypto using Yahoo Finance
def get_crypto_annual_returns(ticker):
    data = yf.Ticker(f"{ticker}-USD")
    hist = data.history(period="max")
    hist.index = pd.to_datetime(hist.index)
    hist['Year'] = hist.index.year
    annual_returns = hist['Close'].resample('Y').ffill().pct_change() * 100
    return annual_returns.dropna(), annual_returns.index.year.dropna().unique().tolist()

# Function to combine returns and dividends based on allocations
def combine_returns_and_dividends(tickers, allocations, asset_types):
    combined_annual_returns = pd.Series(dtype=float)
    combined_dividend_yields = pd.Series(dtype=float)
    years = []

    for ticker, allocation, asset_type in zip(tickers, allocations, asset_types):
        if asset_type == 'Crypto':
            annual_returns, ticker_years = get_crypto_annual_returns(ticker)
            dividend_yields = pd.Series([0] * len(annual_returns), index=annual_returns.index)
        else:
            annual_returns, dividend_yields, ticker_years = get_annual_returns(ticker)

        if combined_annual_returns.empty:
            combined_annual_returns = annual_returns * (allocation / 100)
            combined_dividend_yields = dividend_yields * (allocation / 100)
            years = ticker_years
        else:
            combined_annual_returns = combined_annual_returns.add(annual_returns * (allocation / 100), fill_value=0)
            combined_dividend_yields = combined_dividend_yields.add(dividend_yields * (allocation / 100), fill_value=0)
            years = sorted(list(set(years).union(set(ticker_years))))

    return combined_annual_returns.dropna(), combined_dividend_yields.dropna(), years

# Streamlit user inputs
st.title("Interactive Investment Balance Calculator")
initial_investment = st.number_input("Initial Investment (USD)", value=100000)
withdrawal_rate = st.number_input("Annual Withdrawal Rate (%)", value=4.0)

# Add checkbox for reinvesting dividends
reinvest_dividends = st.checkbox("Reinvest Dividends", value=False)

num_assets = st.number_input("Number of Assets", min_value=1, max_value=10, value=1)
tickers = []
allocations = []
asset_types = []

for i in range(num_assets):
    col1, col2, col3 = st.columns(3)
    with col1:
        ticker = st.text_input(f"Ticker {i + 1}", value="").upper()
    with col2:
        allocation = st.number_input(f"Allocation {i + 1} (%)", min_value=0.0, max_value=100.0, value=100.0 / num_assets)
    with col3:
        asset_type = st.selectbox(f"Type {i + 1}", options=["Stock", "Crypto"])
    tickers.append(ticker)
    allocations.append(allocation)
    asset_types.append(asset_type)

# Initialize session state for years
if 'start_year' not in st.session_state:
    st.session_state['start_year'] = None
if 'end_year' not in st.session_state:
    st.session_state['end_year'] = None

# Fetch annual returns for the given tickers
try:
    annual_returns, dividend_yields, years = combine_returns_and_dividends(tickers, allocations, asset_types)

    if len(annual_returns) == 0:
        st.error("No data available for the provided tickers")
    else:
        # Set default year range if not already set
        if st.session_state['start_year'] is None or st.session_state['start_year'] not in years:
            st.session_state['start_year'] = years[0]
        if st.session_state['end_year'] is None or st.session_state['end_year'] not in years:
            st.session_state['end_year'] = years[-1]
        
        # Year range slider
        start_year, end_year = st.select_slider(
            "Select year range",
            options=years,
            value=(st.session_state['start_year'], st.session_state['end_year'])
        )
        
        # Update session state with selected years
        st.session_state['start_year'] = start_year
        st.session_state['end_year'] = end_year
        
        # Filter annual returns and dividend yields based on the selected year range
        annual_returns = annual_returns[(annual_returns.index.year >= start_year) & (annual_returns.index.year <= end_year)]
        dividend_yields = dividend_yields[(dividend_yields.index.year >= start_year) & (dividend_yields.index.year <= end_year)]
        filtered_years = annual_returns.index.year.tolist()
        
        # Calculate balances, withdrawals, percentage changes, and dividend yields in USD
        balances, withdrawals, percentage_changes, dividend_yields_usd, total_withdrawals_and_dividends = calculate_balances(
            initial_investment, withdrawal_rate, annual_returns.tolist(), dividend_yields.tolist(), reinvest_dividends)
        
        # Create DataFrame with corrected calculations
        withdrawals_df = pd.DataFrame({
            'Year': filtered_years, 
            'Balance (USD)': balances,
            'Percentage Change (%)': percentage_changes,
            'Dividend Yield (USD)': dividend_yields_usd,
            'Withdrawal (USD)': withdrawals,
            'Total Withdrawal + Dividend (USD)': total_withdrawals_and_dividends
        })

        # Keep original numeric columns for plotting
        numeric_withdrawals_df = withdrawals_df.copy()

        # Format the columns to include commas
        withdrawals_df['Balance (USD)'] = withdrawals_df['Balance (USD)'].apply(lambda x: f"{x:,.2f}")
        withdrawals_df['Withdrawal (USD)'] = withdrawals_df['Withdrawal (USD)'].apply(lambda x: f"{x:,.2f}")
        withdrawals_df['Dividend Yield (USD)'] = withdrawals_df['Dividend Yield (USD)'].apply(lambda x: f"{x:,.2f}")
        withdrawals_df['Total Withdrawal + Dividend (USD)'] = withdrawals_df['Total Withdrawal + Dividend (USD)'].apply(lambda x: f"{x:,.2f}")

        # Style the DataFrame
        def highlight_changes(val):
            color = 'green' if val > 0 else 'red'
            return f'color: {color}'

        styled_df = withdrawals_df.style.applymap(highlight_changes, subset=['Percentage Change (%)'])
        
        # Display the DataFrame
        st.write(styled_df.to_html(), unsafe_allow_html=True)
        
        # Display a line chart for balances, withdrawals, and total withdrawals + dividends
        st.line_chart(numeric_withdrawals_df.set_index('Year')[['Balance (USD)', 'Withdrawal (USD)', 'Dividend Yield (USD)', 'Total Withdrawal + Dividend (USD)']])
except Exception as e:
    st.error(f"Error fetching data for tickers: {e}")
