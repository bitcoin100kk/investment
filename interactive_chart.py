import time
import random
import streamlit as st
import pandas as pd
import yfinance as yf

# -----------------------------
# 1) HELPER FUNCTIONS
# -----------------------------

def calculate_balances(
    initial_investment,
    withdrawal_rate,
    annual_returns,
    dividend_yields,
    reinvest_dividends,
):
    """Properly handles dividend non-reinvestment."""
    balance = float(initial_investment)
    balances = []
    withdrawals = []
    percentage_changes = []
    dividend_yields_usd = []
    total_withdrawals_and_dividends = []

    for i in range(len(annual_returns)):
        # 1) Dividend in USD
        dividend_yield_usd = balance * (dividend_yields[i] / 100.0)
        dividend_yields_usd.append(dividend_yield_usd)

        # 2) Withdrawal (skips first year)
        withdrawal = balance * (withdrawal_rate / 100.0) if i > 0 else 0.0
        withdrawals.append(withdrawal)

        # 3) Adjust balance
        if reinvest_dividends:
            balance -= withdrawal
            balance += dividend_yield_usd
        else:
            balance -= withdrawal

        # 4) Track totals
        total_withdrawal_and_dividend = withdrawal + (0.0 if reinvest_dividends else dividend_yield_usd)
        total_withdrawals_and_dividends.append(total_withdrawal_and_dividend)

        # 5) Apply annual return
        prev_balance = balance
        balance *= (1.0 + annual_returns[i] / 100.0)
        balances.append(balance)

        # 6) % change calculation
        percentage_change = ((balance - prev_balance) / prev_balance * 100.0) if prev_balance != 0 else 0.0
        percentage_changes.append(percentage_change)

    return balances, withdrawals, percentage_changes, dividend_yields_usd, total_withdrawals_and_dividends


# -----------------------------
# 2) DATA FETCHING (RATE-LIMIT SAFE)
# -----------------------------

def _is_rate_limit_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return ("too many requests" in msg) or ("rate limit" in msg) or ("429" in msg)

@st.cache_data(ttl=6 * 60 * 60, show_spinner=False)  # cache 6 hours
def fetch_history(ticker: str, crypto: bool) -> pd.DataFrame:
    """
    Fetches full history for a ticker with retries + backoff.
    Cached to avoid repeated Yahoo hits on every widget change.
    """
    symbol = f"{ticker}-USD" if crypto else ticker
    # yfinance can throw transient network errors and rate limits
    last_exc = None
    for attempt in range(6):
        try:
            data = yf.Ticker(symbol)
            hist = data.history(period="max", auto_adjust=False)
            if hist is None or hist.empty:
                return pd.DataFrame()
            hist.index = pd.to_datetime(hist.index)
            return hist
        except Exception as e:
            last_exc = e
            # Exponential backoff, add jitter
            base = 1.5 ** attempt
            sleep_s = min(30.0, base + random.random())
            if _is_rate_limit_error(e):
                # If rate-limited, wait a bit longer
                sleep_s = min(60.0, sleep_s * 2.0)
            time.sleep(sleep_s)
    raise last_exc  # type: ignore


def get_annual_returns(ticker: str):
    hist = fetch_history(ticker, crypto=False)
    if hist.empty:
        return pd.Series(dtype=float), pd.Series(dtype=float), []

    # Use 'YE' (year-end) instead of deprecated 'Y'
    annual_returns = hist["Close"].resample("YE").ffill().pct_change() * 100.0
    dividend_yields = (hist.get("Dividends", 0).resample("YE").sum() / hist["Close"].resample("YE").ffill()) * 100.0

    annual_returns = annual_returns.dropna()
    dividend_yields = dividend_yields.dropna()
    years = annual_returns.index.year.unique().tolist()
    return annual_returns, dividend_yields, years


def get_crypto_annual_returns(ticker: str):
    hist = fetch_history(ticker, crypto=True)
    if hist.empty:
        return pd.Series(dtype=float), []

    annual_returns = hist["Close"].resample("YE").ffill().pct_change() * 100.0
    annual_returns = annual_returns.dropna()
    years = annual_returns.index.year.unique().tolist()
    return annual_returns, years


def combine_returns_and_dividends(tickers, allocations, asset_types):
    df_combined = pd.DataFrame(columns=["annual_return", "dividend_yield"], dtype=float)
    df_combined.index.name = "year"

    # slight delay between tickers to be nicer to Yahoo
    for idx, (ticker, allocation, asset_type) in enumerate(zip(tickers, allocations, asset_types)):
        if idx > 0:
            time.sleep(0.3)

        if asset_type == "Crypto":
            annual_returns, _years = get_crypto_annual_returns(ticker)
            dividend_yields = pd.Series([0] * len(annual_returns), index=annual_returns.index, dtype=float)
        else:
            annual_returns, dividend_yields, _years = get_annual_returns(ticker)

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
    return df_combined["annual_return"], df_combined["dividend_yield"], df_combined.index.tolist()


# -----------------------------
# 3) STREAMLIT APP
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
        ticker = st.text_input(f"Ticker {i + 1}", value="").strip().upper()
    with col2:
        allocation = st.number_input(
            f"Allocation {i + 1} (%)",
            min_value=0.0,
            max_value=100.0,
            value=100.0 / num_assets,
        )
    with col3:
        asset_type = st.selectbox(f"Type {i + 1}", options=["Stock", "Crypto"])
    tickers.append(ticker)
    allocations.append(allocation)
    asset_types.append(asset_type)

# Prevent calling Yahoo on every tiny UI change:
# Only fetch when the user clicks the button.
fetch_clicked = st.button("Fetch / Update Data")

# Store last successful fetch in session_state
if "combined" not in st.session_state:
    st.session_state["combined"] = None
if "fetch_error" not in st.session_state:
    st.session_state["fetch_error"] = None

if fetch_clicked:
    # filter out empty tickers
    clean = [(t, a, ty) for t, a, ty in zip(tickers, allocations, asset_types) if t]
    if not clean:
        st.session_state["combined"] = None
        st.session_state["fetch_error"] = "Enter at least one ticker."
    else:
        tickers2, allocations2, asset_types2 = map(list, zip(*clean))
        try:
            annual_returns, dividend_yields, years = combine_returns_and_dividends(
                tickers2, allocations2, asset_types2
            )
            if len(annual_returns) == 0:
                st.session_state["combined"] = None
                st.session_state["fetch_error"] = "No data available for the provided tickers."
            else:
                st.session_state["combined"] = (annual_returns, dividend_yields, years)
                st.session_state["fetch_error"] = None
        except Exception as e:
            st.session_state["combined"] = None
            st.session_state["fetch_error"] = str(e)

if st.session_state["fetch_error"]:
    st.error(f"Error fetching data: {st.session_state['fetch_error']}")
    st.info("Tip: Yahoo Finance sometimes rate-limits. Wait 1–2 minutes and click 'Fetch / Update Data' again.")

combined = st.session_state["combined"]
if combined:
    annual_returns, dividend_yields, years = combined

    if "start_year" not in st.session_state:
        st.session_state["start_year"] = None
    if "end_year" not in st.session_state:
        st.session_state["end_year"] = None

    col1, col2 = st.columns(2)
    with col1:
        start_year_input = st.number_input(
            "Start Year",
            min_value=min(years),
            max_value=max(years),
            value=st.session_state["start_year"] if st.session_state["start_year"] else min(years),
            step=1,
        )
    with col2:
        end_year_input = st.number_input(
            "End Year",
            min_value=min(years),
            max_value=max(years),
            value=st.session_state["end_year"] if st.session_state["end_year"] else max(years),
            step=1,
        )

    start_year, end_year = st.select_slider(
        "Select year range",
        options=years,
        value=(start_year_input, end_year_input),
    )
    st.session_state["start_year"] = start_year
    st.session_state["end_year"] = end_year

    selected_returns = annual_returns.loc[(annual_returns.index >= start_year) & (annual_returns.index <= end_year)]
    selected_divs = dividend_yields.loc[(dividend_yields.index >= start_year) & (dividend_yields.index <= end_year)]
    filtered_years = selected_returns.index.tolist()

    balances, withdrawals, pct_changes, divs_usd, total_wd_divs = calculate_balances(
        initial_investment,
        withdrawal_rate,
        selected_returns.tolist(),
        selected_divs.tolist(),
        reinvest_dividends,
    )

    results_df = pd.DataFrame(
        {
            "Year": filtered_years,
            "Balance (USD)": balances,
            "Percentage Change (%)": pct_changes,
            "Dividend Yield (USD)": divs_usd,
            "Withdrawal (USD)": withdrawals,
            "Total Withdrawal + Dividend (USD)": total_wd_divs,
        }
    )

    numeric_df = results_df.copy()

    # Pretty formatting
    results_df["Balance (USD)"] = results_df["Balance (USD)"].apply(lambda x: f"{x:,.2f}")
    results_df["Withdrawal (USD)"] = results_df["Withdrawal (USD)"].apply(lambda x: f"{x:,.2f}")
    results_df["Dividend Yield (USD)"] = results_df["Dividend Yield (USD)"].apply(lambda x: f"{x:,.2f}")
    results_df["Total Withdrawal + Dividend (USD)"] = results_df["Total Withdrawal + Dividend (USD)"].apply(lambda x: f"{x:,.2f}")

    def highlight_changes(val):
        color = "green" if val > 0 else "red"
        return f"color: {color}"

    styled_df = results_df.style.applymap(highlight_changes, subset=["Percentage Change (%)"])
    st.write(styled_df.to_html(), unsafe_allow_html=True)

    chart_data = numeric_df.set_index("Year")[
        ["Balance (USD)", "Withdrawal (USD)", "Dividend Yield (USD)", "Total Withdrawal + Dividend (USD)"]
    ]
    st.line_chart(chart_data)
else:
    st.info("Enter your tickers and click **Fetch / Update Data** to load data.")
