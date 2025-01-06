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
    
    # Aggregate by year and calculate annual returns and dividend yields
    annual_returns = hist.groupby('Year')['Close'].last().pct_change() * 100
    dividend_yields = (hist.groupby('Year')['Dividends'].sum() / hist.groupby('Year')['Close'].last()) * 100

    return annual_returns.dropna(), dividend_yields.dropna(), annual_returns.index.tolist()

# Function to get historical annual returns for crypto using Yahoo Finance
def get_crypto_annual_returns(ticker):
    data = yf.Ticker(f"{ticker}-USD")
    hist = data.history(period="max")
    hist.index = pd.to_datetime(hist.index)
    hist['Year'] = hist.index.year

    # Aggregate by year and calculate annual returns
    annual_returns = hist.groupby('Year')['Close'].last().pct_change() * 100
    return annual_returns.dropna(), annual_returns.index.tolist()

# Function to combine returns and dividends based on allocations
def combine_returns_and_dividends(tickers, allocations, asset_types):
    combined_annual_returns = pd.Series(dtype=float)
    combined_dividend_yields = pd.Series(dtype=float)
    all_years = set()

    annual_data = []

    for ticker, allocation, asset_type in zip(tickers, allocations, asset_types):
        if asset_type == 'Crypto':
            annual_returns, ticker_years = get_crypto_annual_returns(ticker)
            dividend_yields = pd.Series([0] * len(annual_returns), index=annual_returns.index)
        else:
            annual_returns, dividend_yields, ticker_years = get_annual_returns(ticker)

        # Align all years
        all_years.update(ticker_years)
        annual_data.append((annual_returns, dividend_yields, allocation))

    # Create aligned series for all years
    all_years = sorted(all_years)
    for annual_returns, dividend_yields, allocation in annual_data:
        annual_returns = annual_returns.reindex(all_years, fill_value=0)
        dividend_yields = dividend_yields.reindex(all_years, fill_value=0)

        if combined_annual_returns.empty:
            combined_annual_returns = annual_returns * (allocation / 100)
            combined_dividend_yields = dividend_yields * (allocation / 100)
        else:
            combined_annual_returns = combined_annual_returns.add(annual_returns * (allocation / 100), fill_value=0)
            combined_dividend_yields = combined_dividend_yields.add(dividend_yields * (allocation / 100), fill_value=0)

    return combined_annual_returns, combined_dividend_yields, all_years

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

# Fetch annual returns for the given tickers
try:
    annual_returns, dividend_yields, years = combine_returns_and_dividends(tickers, allocations, asset_types)

    if len(annual_returns) == 0:
        st.error("No data available for the provided tickers")
    else:
        # Year range slider
        start_year, end_year = st.select_slider(
            "Select year range",
            options=years,
            value=(years[0], years[-1])
        )

        # Filter annual returns and dividend yields based on the selected year range
        annual_returns = annual_returns[(annual_returns.index >= start_year) & (annual_returns.index <= end_year)]
        dividend_yields = dividend_yields[(dividend_yields.index >= start_year) & (dividend_yields.index <= end_year)]
        filtered_years = annual_returns.index.tolist()

        # Calculate balances, withdrawals, percentage changes, and dividend yields in USD
        balances, withdrawals, percentage_changes, dividend_yields_usd, total_withdrawals_and_dividends = calculate_balances(
            initial_investment, withdrawal_rate, annual_returns.tolist(), dividend_yields.tolist(), reinvest_dividends)

        # Create DataFrame with corrected calculations
        withdrawals_df = pd.DataFrame({
            'Year': filtered_years,
            'Bal (USD)': balances,
            '% Chg': percentage_changes,
            'Div (USD)': dividend_yields_usd,
            'Wdraw (USD)': withdrawals,
            'Tot W+D (USD)': total_withdrawals_and_dividends
        })

        # Display the DataFrame
        st.write(withdrawals_df.style.format(
            {
                'Bal (USD)': "${:,.2f}",
                '% Chg': "{:.2f}",
                'Div (USD)': "${:,.2f}",
                'Wdraw (USD)': "${:,.2f}",
                'Tot W+D (USD)': "${:,.2f}"
            }
        ))

        # Display a line chart for balances, withdrawals, and total withdrawals + dividends
        st.line_chart(
            withdrawals_df.set_index('Year')[['Bal (USD)', 'Wdraw (USD)', 'Div (USD)', 'Tot W+D (USD)']]
            .applymap(lambda x: round(x, 2))
        )
except Exception as e:
    st.error(f"Error fetching data for tickers: {e}")
