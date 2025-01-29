import streamlit as st
import pandas as pd
import yfinance as yf

# -----------------------------
# 1) HELPER FUNCTIONS (FIXED)
# -----------------------------

def calculate_balances(
    initial_investment, 
    withdrawal_rate, 
    annual_returns, 
    dividend_yields, 
    reinvest_dividends
):
    """Fixed version: Properly handles dividend non-reinvestment"""
    balance = initial_investment
    balances = []
    withdrawals = []
    percentage_changes = []
    dividend_yields_usd = []
    total_withdrawals_and_dividends = []

    for i in range(len(annual_returns)):
        # 1) Dividend in USD
        dividend_yield_usd = balance * (dividend_yields[i] / 100)
        dividend_yields_usd.append(dividend_yield_usd)

        # 2) Withdrawal (skips first year)
        withdrawal = balance * (withdrawal_rate / 100) if i > 0 else 0
        withdrawals.append(withdrawal)

        # 3) Adjust balance (FIXED HERE)
        if reinvest_dividends:
            balance -= withdrawal
            balance += dividend_yield_usd  # Reinvest dividends
        else:
            balance -= withdrawal  # Only subtract withdrawal (NOT dividends)

        # 4) Track totals
        total_withdrawal_and_dividend = withdrawal + (0 if reinvest_dividends else dividend_yield_usd)
        total_withdrawals_and_dividends.append(total_withdrawal_and_dividend)

        # 5) Apply annual return
        prev_balance = balance
        balance *= (1 + annual_returns[i] / 100)
        balances.append(balance)

        # 6) % change calculation
        percentage_change = ((balance - prev_balance) / prev_balance * 100) if prev_balance != 0 else 0
        percentage_changes.append(percentage_change)

    return (
        balances,
        withdrawals,
        percentage_changes,
        dividend_yields_usd,
        total_withdrawals_and_dividends
    )

# -----------------------------
# REST OF THE CODE REMAINS UNCHANGED
# -----------------------------

def get_annual_returns(ticker):
    """Unchanged original function"""
    data = yf.Ticker(ticker)
    hist = data.history(period="max", auto_adjust=False)
    hist.index = pd.to_datetime(hist.index)
    hist['Year'] = hist.index.year
    annual_returns = hist['Close'].resample('Y').ffill().pct_change() * 100
    dividend_yields = (
        hist['Dividends'].resample('Y').sum() /
        hist['Close'].resample('Y').ffill()
    ) * 100
    annual_returns = annual_returns.dropna()
    dividend_yields = dividend_yields.dropna()
    year_list = annual_returns.index.year.unique().tolist()
    return annual_returns, dividend_yields, year_list

def get_crypto_annual_returns(ticker):
    """Unchanged original function"""
    data = yf.Ticker(f"{ticker}-USD")
    hist = data.history(period="max")
    hist.index = pd.to_datetime(hist.index)
    hist['Year'] = hist.index.year
    annual_returns = hist['Close'].resample('Y').ffill().pct_change() * 100
    annual_returns = annual_returns.dropna()
    year_list = annual_returns.index.year.unique().tolist()
    return annual_returns, year_list

def combine_returns_and_dividends(tickers, allocations, asset_types):
    """Unchanged original function"""
    df_combined = pd.DataFrame(columns=["annual_return", "dividend_yield"], dtype=float)
    df_combined.index.name = "year"
    for ticker, allocation, asset_type in zip(tickers, allocations, asset_types):
        if asset_type == 'Crypto':
            annual_returns, ticker_years = get_crypto_annual_returns(ticker)
            dividend_yields = pd.Series([0]*len(annual_returns), index=annual_returns.index)
        else:
            annual_returns, dividend_yields, ticker_years = get_annual_returns(ticker)
        idx_union = annual_returns.index.union(dividend_yields.index)
        annual_returns = annual_returns.reindex(idx_union, fill_value=0)
        dividend_yields = dividend_yields.reindex(idx_union, fill_value=0)
        df_ticker = pd.DataFrame(index=idx_union)
        df_ticker["annual_return"] = annual_returns.values
        df_ticker["dividend_yield"] = dividend_yields.values
        df_ticker["annual_return"] *= (allocation / 100.0)
        df_ticker["dividend_yield"] *= (allocation / 100.0)
        df_ticker.index = df_ticker.index.year
        df_combined = df_combined.reindex(df_combined.index.union(df_ticker.index), fill_value=0)
        df_ticker = df_ticker.reindex(df_combined.index, fill_value=0)
        df_combined["annual_return"] += df_ticker["annual_return"]
        df_combined["dividend_yield"] += df_ticker["dividend_yield"]
    df_combined.sort_index(inplace=True)
    final_annual_returns = df_combined["annual_return"]
    final_dividend_yields = df_combined["dividend_yield"]
    years = df_combined.index.tolist()
    return final_annual_returns, final_dividend_yields, years

# -----------------------------
# 2) STREAMLIT APP (UNCHANGED)
# -----------------------------
st.title("Interactive Investment Balance Calculator")
initial_investment = st.number_input("Initial Investment (USD)", value=100000)
withdrawal_rate = st.number_input("Annual Withdrawal Rate (%)", value=4.0)
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
        allocation = st.number_input(
            f"Allocation {i + 1} (%)", 
            min_value=0.0, 
            max_value=100.0, 
            value=100.0 / num_assets
        )
    with col3:
        asset_type = st.selectbox(f"Type {i + 1}", options=["Stock", "Crypto"])
    tickers.append(ticker)
    allocations.append(allocation)
    asset_types.append(asset_type)

if 'start_year' not in st.session_state:
    st.session_state['start_year'] = None
if 'end_year' not in st.session_state:
    st.session_state['end_year'] = None

try:
    annual_returns, dividend_yields, years = combine_returns_and_dividends(
        tickers, allocations, asset_types
    )
    if len(annual_returns) == 0:
        st.error("No data available for the provided tickers.")
    else:
        col1, col2 = st.columns(2)
        with col1:
            start_year_input = st.number_input(
                "Start Year",
                min_value=min(years),
                max_value=max(years),
                value=st.session_state['start_year'] if st.session_state['start_year'] else min(years),
                step=1
            )
        with col2:
            end_year_input = st.number_input(
                "End Year",
                min_value=min(years),
                max_value=max(years),
                value=st.session_state['end_year'] if st.session_state['end_year'] else max(years),
                step=1
            )
        start_year, end_year = st.select_slider(
            "Select year range",
            options=years,
            value=(start_year_input, end_year_input)
        )
        st.session_state['start_year'] = start_year
        st.session_state['end_year'] = end_year
        selected_returns = annual_returns.loc[(annual_returns.index >= start_year) & (annual_returns.index <= end_year)]
        selected_divs = dividend_yields.loc[(dividend_yields.index >= start_year) & (dividend_yields.index <= end_year)]
        filtered_years = selected_returns.index.tolist()
        balances, withdrawals, pct_changes, divs_usd, total_wd_divs = calculate_balances(
            initial_investment,
            withdrawal_rate,
            selected_returns.tolist(),
            selected_divs.tolist(),
            reinvest_dividends
        )
        results_df = pd.DataFrame({
            "Year": filtered_years,
            "Balance (USD)": balances,
            "Percentage Change (%)": pct_changes,
            "Dividend Yield (USD)": divs_usd,
            "Withdrawal (USD)": withdrawals,
            "Total Withdrawal + Dividend (USD)": total_wd_divs
        })
        numeric_df = results_df.copy()
        results_df["Balance (USD)"] = results_df["Balance (USD)"].apply(lambda x: f"{x:,.2f}")
        results_df["Withdrawal (USD)"] = results_df["Withdrawal (USD)"].apply(lambda x: f"{x:,.2f}")
        results_df["Dividend Yield (USD)"] = results_df["Dividend Yield (USD)"].apply(lambda x: f"{x:,.2f}")
        results_df["Total Withdrawal + Dividend (USD)"] = results_df["Total Withdrawal + Dividend (USD)"].apply(lambda x: f"{x:,.2f}")
        def highlight_changes(val):
            color = 'green' if val > 0 else 'red'
            return f'color: {color}'
        styled_df = results_df.style.applymap(highlight_changes, subset=['Percentage Change (%)'])
        st.write(styled_df.to_html(), unsafe_allow_html=True)
        chart_data = numeric_df.set_index("Year")[
            [
                "Balance (USD)",
                "Withdrawal (USD)",
                "Dividend Yield (USD)",
                "Total Withdrawal + Dividend (USD)"
            ]
        ]
        st.line_chart(chart_data)
except Exception as e:
    st.error(f"Error fetching data for the provided tickers: {e}")
